"""
Agente Híbrido da Netbricks Prime (Mosaic AI Agent Framework — ChatAgent).

Três ferramentas, escolhidas pelo próprio LLM (tool calling):
  1. buscar_titulos   -> busca semântica no catálogo (Vector Search) = descoberta/recomendação
  2. suporte          -> RAG na central de ajuda (Vector Search)
  3. consultar_dados  -> métricas estruturadas do catálogo/usuários (SQL parametrizado seguro)

Defaults já batem com os recursos do lab; funciona no serving sem variáveis de ambiente.
"""
import json
import os
from typing import Any, Optional

import mlflow
from databricks.sdk import WorkspaceClient
from databricks.vector_search.client import VectorSearchClient
from mlflow.deployments import get_deploy_client
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import ChatAgentMessage, ChatAgentResponse

CATALOG = os.environ.get("CATALOG", "netbricks_prime")
SCHEMA = os.environ.get("SCHEMA", "suas_iniciais_aqui")
VS_ENDPOINT = os.environ.get("VS_ENDPOINT", f"netbricks_vs_{SCHEMA}")
IDX_CAT = os.environ.get("IDX_CAT", f"{CATALOG}.{SCHEMA}.catalogo_index")
IDX_AJU = os.environ.get("IDX_AJU", f"{CATALOG}.{SCHEMA}.ajuda_index")
LLM = os.environ.get("LLM_MODEL", "databricks-claude-sonnet-5")
# Vazio = descobre automaticamente um SQL warehouse disponível no workspace.
WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "")

SYSTEM_PROMPT = (
    "Você é o assistente da Netbricks Prime, uma plataforma de streaming. Responda SEMPRE "
    "em português do Brasil. Use as ferramentas disponíveis para: recomendar títulos "
    "(buscar_titulos), tirar dúvidas de conta/planos/cobrança (suporte) e responder "
    "perguntas sobre números da plataforma (consultar_dados). Baseie-se nos resultados das "
    "ferramentas; não invente títulos, valores ou políticas. Seja objetivo e simpático."
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
        "description": "Retorna métricas agregadas da plataforma.",
        "parameters": {"type": "object", "properties": {
            "metrica": {"type": "string",
                        "enum": ["titulos_por_genero", "usuarios_por_plano", "churn_por_plano", "total_titulos"],
                        "description": "Qual métrica consultar"},
        }, "required": ["metrica"]}}},
]

_QUERIES = {
    "titulos_por_genero": f"SELECT genero_principal, COUNT(*) n FROM {CATALOG}.{SCHEMA}.catalogo GROUP BY 1 ORDER BY n DESC LIMIT 20",
    "usuarios_por_plano": f"SELECT plano, COUNT(*) n FROM {CATALOG}.{SCHEMA}.usuarios GROUP BY 1 ORDER BY n DESC",
    "churn_por_plano": f"SELECT plano, ROUND(100.0*SUM(CASE WHEN status='Cancelado' THEN 1 ELSE 0 END)/COUNT(*),1) churn_pct FROM {CATALOG}.{SCHEMA}.usuarios GROUP BY 1 ORDER BY churn_pct DESC",
    "total_titulos": f"SELECT COUNT(*) total FROM {CATALOG}.{SCHEMA}.catalogo",
}


def _texto(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text") or ""
    return "" if content is None else str(content)


class NetbricksAgent(ChatAgent):
    def __init__(self):
        self._llm = get_deploy_client("databricks")
        self._vsc = None
        self._w = None
        self._wh_id = None

    @property
    def vsc(self):
        if self._vsc is None:
            self._vsc = VectorSearchClient(disable_notice=True)
        return self._vsc

    @property
    def w(self):
        if self._w is None:
            self._w = WorkspaceClient()
        return self._w

    # ---- ferramentas ----
    @mlflow.trace(span_type="RETRIEVER")
    def _buscar_titulos(self, consulta, genero=None):
        idx = self.vsc.get_index(VS_ENDPOINT, IDX_CAT)
        kwargs = dict(query_text=consulta,
                      columns=["titulo", "genero_principal", "ano", "nota_media", "sinopse"],
                      num_results=6)
        if genero:
            kwargs["filters"] = {"genero_principal": genero}
        rows = idx.similarity_search(**kwargs).get("result", {}).get("data_array", []) or []
        return [{"titulo": r[0], "genero": r[1], "ano": r[2], "nota": r[3],
                 "sinopse": (r[4] or "")[:180]} for r in rows]

    @mlflow.trace(span_type="RETRIEVER")
    def _suporte(self, pergunta):
        idx = self.vsc.get_index(VS_ENDPOINT, IDX_AJU)
        rows = idx.similarity_search(query_text=pergunta, columns=["titulo", "conteudo"],
                                     num_results=3).get("result", {}).get("data_array", []) or []
        return [{"topico": r[0], "conteudo": r[1]} for r in rows]

    def _warehouse(self):
        """Usa WAREHOUSE_ID se definido; senão descobre um warehouse disponível."""
        if WAREHOUSE_ID:
            return WAREHOUSE_ID
        if self._wh_id is None:
            whs = list(self.w.warehouses.list())
            if not whs:
                raise RuntimeError("Nenhum SQL warehouse disponível no workspace.")
            running = [x for x in whs if str(getattr(x.state, "value", x.state)) == "RUNNING"]
            self._wh_id = (running or whs)[0].id
        return self._wh_id

    @mlflow.trace(span_type="TOOL")
    def _consultar_dados(self, metrica):
        sql = _QUERIES.get(metrica)
        if not sql:
            return {"erro": "métrica desconhecida"}
        r = self.w.statement_execution.execute_statement(
            warehouse_id=self._warehouse(), statement=sql, wait_timeout="30s")
        data = r.result.data_array if r.result else []
        cols = [c.name for c in r.manifest.schema.columns]
        return [dict(zip(cols, row)) for row in (data or [])]

    def _exec_tool(self, name, args):
        try:
            if name == "buscar_titulos":
                return self._buscar_titulos(args.get("consulta", ""), args.get("genero"))
            if name == "suporte":
                return self._suporte(args.get("pergunta", ""))
            if name == "consultar_dados":
                return self._consultar_dados(args.get("metrica", ""))
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
            resp = self._llm.predict(endpoint=LLM,
                                     inputs={"messages": msgs, "tools": TOOLS, "max_tokens": 1024})
            msg = resp["choices"][0]["message"]
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                final = _texto(msg.get("content"))
                break
            msgs.append(msg)  # preserva os tool_calls
            for tc in tool_calls:
                fn = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except Exception:
                    args = {}
                result = self._exec_tool(fn, args)
                msgs.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": json.dumps(result, ensure_ascii=False)})

        return ChatAgentResponse(
            messages=[ChatAgentMessage(role="assistant", content=final or "(sem resposta)", id="1")])


from mlflow.models import set_model

AGENT = NetbricksAgent()
set_model(AGENT)
