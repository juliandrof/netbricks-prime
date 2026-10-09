"""
Agente Híbrido da Netbricks Prime (Mosaic AI Agent Framework — ChatAgent).

Três ferramentas, escolhidas pelo próprio LLM (tool calling):
  1. buscar_titulos   -> busca semântica no catálogo (Vector Search) = descoberta/recomendação
  2. suporte          -> RAG na central de ajuda (Vector Search)
  3. consultar_dados  -> perguntas em linguagem natural sobre os números da plataforma,
                         respondidas por um **Genie Space** via a API REST do Genie (SDK,
                         `w.genie`), chamado como o usuário (OBO). O Genie gera e executa o SQL
                         com governança — o agente não monta SQL diretamente.

Defaults já batem com os recursos do lab; informe o GENIE_SPACE_ID (env ou widget no deploy).
"""
import json
import os
from typing import Any, Optional

import mlflow
from databricks.sdk import WorkspaceClient
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse

CATALOG = os.environ.get("CATALOG", "netbricks_prime")
SCHEMA = os.environ.get("SCHEMA", "suas_iniciais_aqui")
VS_ENDPOINT = os.environ.get("VS_ENDPOINT", f"netbricks_vs_{SCHEMA}")
IDX_CAT = os.environ.get("IDX_CAT", f"{CATALOG}.{SCHEMA}.catalogo_index")
IDX_AJU = os.environ.get("IDX_AJU", f"{CATALOG}.{SCHEMA}.ajuda_index")
LLM = os.environ.get("LLM_MODEL", "databricks-llama-4-maverick")
# ID do Genie Space usado pela ferramenta consultar_dados (via API REST do SDK). Obrigatório p/ essa tool.
GENIE_SPACE_ID = os.environ.get("GENIE_SPACE_ID", "")

SYSTEM_PROMPT = (
    "Você é o assistente da Netbricks Prime, uma plataforma de streaming. Responda SEMPRE "
    "em português do Brasil. Use as ferramentas disponíveis para: recomendar títulos "
    "(buscar_titulos), tirar dúvidas de conta/planos/cobrança (suporte) e responder "
    "perguntas sobre números da plataforma (consultar_dados, que usa o Genie). Baseie-se nos "
    "resultados das ferramentas; não invente títulos, valores ou políticas. Seja objetivo e simpático."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "buscar_titulos",
        "description": "Busca semântica no catálogo por sinopse. Use para recomendar filmes/séries "
                       "por tema, clima ou similaridade (ex.: 'algo tipo ficção científica, mas leve').",
        "parameters": {"type": "object", "properties": {
            "consulta": {"type": "string", "description": "Descrição do que o usuário quer assistir"},
            "genero": {"type": "string", "description": "Gênero para filtrar (opcional)"},
        }, "required": ["consulta"]}}},
    {"type": "function", "function": {
        "name": "suporte",
        "description": "Consulta a central de ajuda (planos, preços, cobrança, cancelamento, "
                       "downloads, telas, 4K, controle dos pais). Use para dúvidas de conta/serviço.",
        "parameters": {"type": "object", "properties": {
            "pergunta": {"type": "string", "description": "A dúvida do usuário sobre o serviço"},
        }, "required": ["pergunta"]}}},
    {"type": "function", "function": {
        "name": "consultar_dados",
        "description": "Responde perguntas sobre os NÚMEROS da plataforma (títulos, usuários, planos, "
                       "churn, engajamento) consultando o Genie Space via linguagem natural. Use para "
                       "qualquer métrica/agregação (ex.: 'quantos títulos por gênero?', "
                       "'qual o churn por plano?', 'quantos usuários Premium?').",
        "parameters": {"type": "object", "properties": {
            "pergunta": {"type": "string",
                         "description": "Pergunta em linguagem natural sobre os dados da plataforma"},
        }, "required": ["pergunta"]}}},
]


def _texto(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text") or ""
    return "" if content is None else str(content)


def _in_model_serving() -> bool:
    """True quando rodando dentro de um endpoint de Model Serving (variáveis setadas pelo runtime)."""
    v = (os.environ.get("IS_IN_DB_MODEL_SERVING_ENV")
         or os.environ.get("IS_IN_DATABRICKS_MODEL_SERVING_ENV") or "")
    return v.lower() == "true"


def _user_workspace_client():
    """Cliente OBO (on-behalf-of-user): chama LLM e Genie com a credencial de quem invoca o agente.

    No serving, resolve o token do usuário via ``ModelServingUserCredentials``; fora do serving
    (notebook 03), usa as credenciais padrão do notebook. VS e embeddings seguem em credenciais de
    sistema (resources declarados)."""
    if _in_model_serving():
        try:
            from databricks_ai_bridge import ModelServingUserCredentials
        except Exception:
            from databricks.sdk.credentials_provider import ModelServingUserCredentials
        return WorkspaceClient(credentials_strategy=ModelServingUserCredentials())
    return WorkspaceClient()


class NetbricksAgent(ChatAgent):
    def __init__(self):
        self._w = None
        self._uw = None

    @property
    def w(self):
        # Credenciais de SISTEMA (service principal do endpoint): usadas pelo Vector Search,
        # que são resources declarados (SystemAuthPolicy) e autorizados automaticamente no deploy.
        if self._w is None:
            self._w = WorkspaceClient()
        return self._w

    @property
    def user_w(self):
        # Credenciais do USUÁRIO (OBO): usadas pelo LLM e pelo Genie. A estratégia resolve o token
        # do invocador a cada request, então cachear o objeto cliente é ok.
        if self._uw is None:
            self._uw = _user_workspace_client()
        return self._uw

    @property
    def oai(self):
        # Cliente OpenAI do serving com credenciais do usuário (OBO). Reconstruído a cada acesso
        # para usar o token do request atual.
        return self.user_w.serving_endpoints.get_open_ai_client()

    def _vs_query(self, index_name, columns, query_text, num_results, filters=None):
        """Consulta um índice de Vector Search via SDK (credenciais de sistema)."""
        kwargs = dict(index_name=index_name, columns=columns,
                      query_text=query_text, num_results=num_results)
        if filters:
            kwargs["filters_json"] = json.dumps(filters)
        resp = self.w.vector_search_indexes.query_index(**kwargs)
        return (resp.result.data_array if resp.result else None) or []

    # ---- ferramentas ----
    @mlflow.trace(span_type="RETRIEVER")
    def _buscar_titulos(self, consulta, genero=None):
        rows = self._vs_query(
            IDX_CAT, ["titulo", "genero_principal", "ano", "nota_media", "sinopse"],
            consulta, 6, filters={"genero_principal": genero} if genero else None)
        return [{"titulo": r[0], "genero": r[1], "ano": r[2], "nota": r[3],
                 "sinopse": (r[4] or "")[:180]} for r in rows]

    @mlflow.trace(span_type="RETRIEVER")
    def _suporte(self, pergunta):
        rows = self._vs_query(IDX_AJU, ["titulo", "conteudo"], pergunta, 3)
        return [{"topico": r[0], "conteudo": r[1]} for r in rows]

    @mlflow.trace(span_type="TOOL")
    def _consultar_dados(self, pergunta):
        """Encaminha a pergunta ao Genie Space via API REST do SDK, como o usuário (OBO).

        O Genie gera e executa o SQL com governança — o agente não monta SQL. Requer o escopo
        ``dashboards.genie`` no deploy."""
        if not GENIE_SPACE_ID:
            return {"erro": "GENIE_SPACE_ID não configurado — defina a variável de ambiente."}
        msg = self.user_w.genie.start_conversation_and_wait(GENIE_SPACE_ID, pergunta)
        partes = []
        for att in (msg.attachments or []):
            texto = getattr(getattr(att, "text", None), "content", None)
            if texto:
                partes.append(texto)
            if getattr(att, "query", None) is not None:
                q = att.query
                if getattr(q, "description", None):
                    partes.append(q.description)
                linhas = self._genie_rows(msg, att.attachment_id)
                if linhas:
                    partes.append(json.dumps(linhas, ensure_ascii=False))
        return {"resposta": "\n".join(partes) if partes else "(sem resposta do Genie)"}

    def _genie_rows(self, msg, attachment_id):
        """Busca as linhas do resultado de um attachment de query do Genie (máx. 50 linhas)."""
        try:
            res = self.user_w.genie.get_message_attachment_query_result(
                GENIE_SPACE_ID, msg.conversation_id, msg.id, attachment_id)
            sr = res.statement_response
            if not (sr and sr.result and sr.result.data_array):
                return None
            cols = []
            if sr.manifest and sr.manifest.schema and sr.manifest.schema.columns:
                cols = [c.name for c in sr.manifest.schema.columns]
            linhas = sr.result.data_array[:50]
            return {"colunas": cols, "linhas": linhas} if cols else {"linhas": linhas}
        except Exception as e:
            return {"erro_resultado": str(e)[:200]}

    def _exec_tool(self, name, args):
        try:
            if name == "buscar_titulos":
                return self._buscar_titulos(args.get("consulta", ""), args.get("genero"))
            if name == "suporte":
                return self._suporte(args.get("pergunta", ""))
            if name == "consultar_dados":
                return self._consultar_dados(args.get("pergunta", ""))
            return {"erro": f"ferramenta desconhecida: {name}"}
        except Exception as e:
            return {"erro": str(e)[:300]}

    @mlflow.trace(span_type="AGENT")
    def predict(self, messages, context=None, custom_inputs=None) -> ChatAgentResponse:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in messages:
            msgs.append({"role": m.role, "content": m.content})

        final = ""
        for _ in range(5):  # limite de rodadas de tool calling
            resp = self.oai.chat.completions.create(
                model=LLM, messages=msgs, tools=TOOLS, max_tokens=1024)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                final = msg.content or ""
                break
            # preserva a mensagem do assistant com os tool_calls (como dict, p/ a próxima rodada)
            msgs.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name,
                                             "arguments": tc.function.arguments}}
                               for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                result = self._exec_tool(tc.function.name, args)
                msgs.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, ensure_ascii=False)})

        return ChatAgentResponse(
            messages=[ChatAgentMessage(role="assistant", content=final or "(sem resposta)", id="1")])


from mlflow.models import set_model

AGENT = NetbricksAgent()
set_model(AGENT)
