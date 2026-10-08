# 🎬 Netbricks Prime — Lab de Streaming no Databricks

Lab fim-a-fim de uma plataforma de streaming fictícia (**Netbricks Prime**) sobre a Lakehouse.
Cobre **geração de dados em escala → engenharia de atributos → dois modelos de ML (churn e
propensão de upgrade) → Vector Search → um agente híbrido (Mosaic AI Agent Framework)**, com
a camada de GenAI governada por **Unity AI Gateway**.

> Nenhum dado é real: usuários, títulos, e-mails (`@netbricksprime.com`) e artigos de ajuda são
> todos sintéticos e gerados de forma determinística. O lab roda em **qualquer workspace
> Databricks** com os pré-requisitos abaixo — basta ajustar `catalog`/`schema` no `_config`.

---

## Ambiente

| Item | Valor |
|------|-------|
| Compute | Serverless notebooks / jobs |
| Catálogo | `CATALOG` no `_config` (padrão `netbricks_prime`) — **deve existir** |
| Schema | `SCHEMA` no `_config` (padrão `suas_iniciais_aqui`) — **criado pelo notebook 0** |
| Vector Search endpoint | `netbricks_vs_<schema>` (criado pelo notebook 4; nome inclui o schema para evitar colisão entre labs no mesmo workspace) |

**Configuração centralizada:** catálogo e schema ficam em **um único lugar** — o notebook
**`_config`**. Todos os notebooks (0–7) fazem `%run ./_config` no início e reaproveitam
`CATALOG`, `SCHEMA` e `VS_ENDPOINT`. Você edita o `_config` **uma vez** e não precisa repetir em
cada notebook. Em um hands-on com várias pessoas no mesmo workspace, o catálogo `netbricks_prime`
é compartilhado e **cada participante troca o `SCHEMA` pelas suas próprias iniciais** — assim
tabelas, modelos e o endpoint de Vector Search (`netbricks_vs_<schema>`) ficam isolados por
pessoa. O schema é criado automaticamente; o catálogo **não** é criado (deve existir e você
precisa ter permissão de uso).

> ⚠️ O `_config` precisa estar **na mesma pasta** dos notebooks (o `%run ./_config` é relativo).

### Modelos usados

| Papel | Modelo | Onde entra |
|-------|--------|------------|
| LLM do agente | `databricks-llama-4-maverick` (Foundation Model API) — **parametrizável** | raciocínio e *tool calling* do agente híbrido |
| Embeddings | `databricks-gte-large-en` (Foundation Model API) | geração de embeddings dos índices de Vector Search |
| ML clássico | scikit-learn `HistGradientBoostingClassifier` | modelos de churn e de propensão de upgrade |

> Os dois modelos de Foundation Model acima são endpoints de serving — é exatamente neles que o
> **Unity AI Gateway** é configurado (ver seção abaixo).

> **O LLM é um parâmetro (widget `llm`) nos notebooks 06 e 07.** O default é
> `databricks-llama-4-maverick` — um modelo de chat com *tool calling* disponível por padrão.
> Você pode trocar por qualquer endpoint de chat com *tool calling* em que tenha **EXECUTE**
> (ex.: `databricks-gpt-5-2`, ou `databricks-claude-sonnet-5` — este exige EXECUTE em
> `system.ai.databricks-claude-sonnet-5`, caso contrário o deploy falha com `403 PERMISSION_DENIED`).
> O agente usa o valor via a variável de ambiente `LLM_MODEL`.

---

## Pré-requisitos

- Workspace Databricks com **Serverless compute** habilitado.
- **Unity Catalog** com um catálogo onde você possa criar schema/tabelas/modelos.
- **Vector Search** habilitado no workspace.
- Acesso às **Foundation Model APIs** com **EXECUTE** no endpoint de LLM escolhido (widget `llm`;
  default `databricks-llama-4-maverick`) e no de embeddings (`databricks-gte-large-en`).
- Um **Genie Space** sobre as tabelas do lab (ver [passo abaixo](#genie-space-para-a-ferramenta-de-dados)) — o agente o consome via MCP.

---

## Passo a passo (ordem de execução)

| # | Notebook | O que faz | Saídas principais |
|---|----------|-----------|-------------------|
| **0** | `00_netbricks_prime_gerar_dados.py` | Gera toda a base de forma determinística e com **sinal comportamental** (engajamento latente governa plano, churn e volume de eventos). Cria o schema. | `catalogo` (10k títulos, PK + CDF), `usuarios` (120k), `eventos_visualizacao` (1M, particionado), `central_ajuda_kb` (12 artigos, PK + CDF) |
| **1** | `01_feature_engineering.py` | Agrega eventos por usuário e junta com o perfil. | `features_usuarios` |
| **2** | `02_modelo_churn.py` | Treina classificador de **churn** (`status = 'Cancelado'`), registra no UC e escora toda a base. | modelo `modelo_churn`, tabela `scores_churn` (prob + faixa de risco) |
| **3** | `03_modelo_upgrade.py` | Treina **propensão de upgrade** (`is_pago`) e aplica aos usuários **Free** — os de maior probabilidade são os melhores alvos de conversão. | modelo `modelo_upgrade`, tabela `scores_upgrade` |
| **4** | `04_vector_search.py` | Cria o endpoint VS e dois índices Delta Sync. | `catalogo_index` (sinopse), `ajuda_index` (conteúdo) |
| **5** | `05_criar_genie_space.py` | Adiciona as chaves PK/FK (dicas de *join*) e traz o passo a passo + textos prontos para **criar o Genie Space na UI**. | constraints PK/FK; Genie Space criado manualmente → `genie_space_id` |
| **6** | `06_deploy_agent.py` | Loga `agent.py` com os *resources* que acessa, registra no UC e faz deploy em Model Serving. | modelo `netbricks_agent` + endpoint de serving |
| **7** | `07_teste_agente.py` | Executa o `agent.py` **localmente no notebook** (credenciais do usuário, sem deploy) e valida as 3 ferramentas. | respostas das 3 perguntas de teste |

> **Parâmetros:** ajuste `CATALOG`/`SCHEMA` **uma vez** no `_config` (todos os notebooks o
> reaproveitam via `%run ./_config`). A ordem **0 → 4 → 5 → 6 → 7** é obrigatória (cada etapa
> consome a saída da anterior); o `genie_space_id` criado no 5 é preenchido nos widgets dos
> notebooks 06 e 07.

---

## O agente híbrido (`agent.py`)

`ChatAgent` do Mosaic AI Agent Framework. O próprio LLM (Claude Sonnet) escolhe entre 3
ferramentas via *tool calling* (loop de até 5 rodadas):

| Ferramenta | Tipo | Para quê |
|------------|------|----------|
| `buscar_titulos` | Vector Search (`catalogo_index`) | Descoberta/recomendação por tema ou clima |
| `suporte` | RAG (`ajuda_index`) | Dúvidas de conta/plano/cobrança/cancelamento |
| `consultar_dados` | **Genie Space via MCP** | Perguntas em linguagem natural sobre os números da plataforma (o Genie gera e executa o SQL com governança) |

É um arquivo importável (`from agent import AGENT`), com defaults que já batem com os recursos do
lab — roda tanto no notebook (07) quanto no serving (06). A ferramenta `consultar_dados` chama o
**MCP gerenciado do Databricks para Genie** (`/api/2.0/mcp/genie/{space_id}`): o agente envia a
pergunta em linguagem natural e o Genie monta/executa a consulta — o agente **não** gera SQL. O
Genie Space usado é definido pela variável de ambiente `GENIE_SPACE_ID` (widget nos notebooks 06/07).

### Genie Space para a ferramenta de dados

1. Rode o notebook **`05_criar_genie_space.py`** — ele adiciona as chaves PK/FK (dicas de *join*)
   e traz o passo a passo da UI + os textos prontos (tabelas, instruções, perguntas de exemplo).
2. Siga as instruções do 05 para criar o Genie Space na UI apontando para as tabelas do schema.
3. Copie o **Space ID** da URL (`/genie/rooms/<space_id>`).
4. Informe esse ID no widget `genie_space_id` dos notebooks **06** (deploy) e **07** (teste).

> Como os dados são idênticos entre schemas (geração determinística), um **único Genie Space
> compartilhado** atende todos os participantes de um hands-on — basta todos usarem o mesmo
> `GENIE_SPACE_ID`.

---

## 🛡️ Onde entra o Unity AI Gateway

O **Unity AI Gateway** é a camada de governança que fica **na frente dos endpoints de model serving**
que o lab usa — principalmente o LLM do agente (`databricks-claude-sonnet-5`) e, se desejado, o
endpoint de embeddings. Ele adiciona, de forma centralizada e sem alterar o código do agente:

- **Guardrails de segurança/PII** — detecção e mascaramento (ou bloqueio) de dados sensíveis em
  prompts e respostas;
- **Rate limiting** — limites de requisição por usuário/endpoint;
- **Usage tracking & payload logging** — registro de todo o tráfego (inferência) em tabelas do
  Unity Catalog para auditoria e análise de custo;
- **Fallbacks** — roteamento para modelos alternativos.

**Como encaixar neste lab:** habilite o Unity AI Gateway no endpoint de Foundation Model que o agente
consome (`databricks-claude-sonnet-5`). Assim, cada chamada que o agente faz passa pelos
guardrails e é registrada — o agente continua idêntico, mas a camada de GenAI fica governada.

> **Observação importante:** os guardrails do Unity AI Gateway são configurados em endpoints de
> *pay-per-token*, *provisioned throughput* ou *external model* — **não** no endpoint do agente
> em si. Por isso a governança é aplicada ao **endpoint do LLM subjacente** que o agente chama,
> e não ao endpoint `netbricks_agent`.

---

## Sobre o deploy do agente (notebook 06)

O `agents.deploy` publica o agente em Model Serving e, para isso, **cria uma service principal**
para o endpoint. Requisitos: cota de service principals disponível na conta e os *resources*
declarados (índices de Vector Search, endpoints de FM e o Genie Space).

Se o deploy falhar por limite de recursos da conta (ex.: cota de service principals esgotada), o
agente continua **totalmente funcional via notebook/job** — use o **notebook 07** para rodá-lo
com suas próprias credenciais, sem criar endpoint. O modelo já fica registrado no Unity Catalog,
então o deploy pode ser refeito quando houver cota.

---

## Objetos criados em `<catalog>.<schema>`

**Tabelas:** `catalogo`, `usuarios`, `eventos_visualizacao`, `central_ajuda_kb`,
`features_usuarios`, `scores_churn`, `scores_upgrade`
**Modelos (UC):** `modelo_churn`, `modelo_upgrade`, `netbricks_agent`
**Vector Search:** endpoint `netbricks_vs_<schema>` + índices `catalogo_index`, `ajuda_index`

---

*Lab de demonstração — plataforma e dados fictícios.*
