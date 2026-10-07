# 🎬 Netbricks Prime — Lab de Streaming no Databricks

Lab fim-a-fim de uma plataforma de streaming fictícia (**Netbricks Prime**) sobre a Lakehouse.
Cobre **geração de dados em escala → engenharia de atributos → dois modelos de ML (churn e
propensão de upgrade) → Vector Search → um agente híbrido (Mosaic AI Agent Framework)**, com
a camada de GenAI governada por **Unity AI Gateway**.

> Nenhum dado é real: usuários, títulos, e-mails (`@netbricksprime.com`) e artigos de ajuda são
> todos sintéticos e gerados de forma determinística. O lab roda em **qualquer workspace
> Databricks** com os pré-requisitos abaixo — basta ajustar os parâmetros `catalog`/`schema`.

---

## Ambiente

| Item | Valor |
|------|-------|
| Compute | Serverless notebooks / jobs |
| Catálogo | parâmetro `catalog` (padrão `main`) — **deve existir** |
| Schema | parâmetro `schema` (padrão `netbricks_prime`) — **criado pelo notebook 0** |
| Vector Search endpoint | `netbricks_vs_<schema>` (criado pelo notebook 4; nome inclui o schema para evitar colisão entre labs no mesmo workspace) |

Todos os notebooks têm **widgets `catalog` e `schema`**, então o lab pode ser recriado em
qualquer catálogo existente só trocando os parâmetros. O schema é criado automaticamente; o
catálogo **não** é criado (informe um que você já tenha permissão de uso).

### Modelos usados

| Papel | Modelo | Onde entra |
|-------|--------|------------|
| LLM do agente | `databricks-claude-sonnet-5` (Foundation Model API, pay-per-token) | raciocínio e *tool calling* do agente híbrido |
| Embeddings | `databricks-gte-large-en` (Foundation Model API) | geração de embeddings dos índices de Vector Search |
| ML clássico | scikit-learn `HistGradientBoostingClassifier` | modelos de churn e de propensão de upgrade |

> Os dois modelos de Foundation Model acima são endpoints de serving — é exatamente neles que o
> **Unity AI Gateway** é configurado (ver seção abaixo).

---

## Pré-requisitos

- Workspace Databricks com **Serverless compute** habilitado.
- **Unity Catalog** com um catálogo onde você possa criar schema/tabelas/modelos.
- **Vector Search** habilitado no workspace.
- Acesso às **Foundation Model APIs** (`databricks-claude-sonnet-5`, `databricks-gte-large-en`).
- Um **SQL Warehouse** (o agente descobre um automaticamente se nenhum ID for informado).

---

## Passo a passo (ordem de execução)

| # | Notebook | O que faz | Saídas principais |
|---|----------|-----------|-------------------|
| **0** | `netbricks_prime_gerar_dados.py` | Gera toda a base de forma determinística e com **sinal comportamental** (engajamento latente governa plano, churn e volume de eventos). Cria o schema. | `catalogo` (10k títulos, PK + CDF), `usuarios` (120k), `eventos_visualizacao` (1M, particionado), `central_ajuda_kb` (12 artigos, PK + CDF) |
| **1** | `01_feature_engineering.py` | Agrega eventos por usuário e junta com o perfil. | `features_usuarios` |
| **2** | `02_modelo_churn.py` | Treina classificador de **churn** (`status = 'Cancelado'`), registra no UC e escora toda a base. | modelo `modelo_churn`, tabela `scores_churn` (prob + faixa de risco) |
| **3** | `03_modelo_upgrade.py` | Treina **propensão de upgrade** (`is_pago`) e aplica aos usuários **Free** — os de maior probabilidade são os melhores alvos de conversão. | modelo `modelo_upgrade`, tabela `scores_upgrade` |
| **4** | `04_vector_search.py` | Cria o endpoint VS e dois índices Delta Sync. | `catalogo_index` (sinopse), `ajuda_index` (conteúdo) |
| **5** | `05_deploy_agent.py` | Loga `agent.py` com os *resources* que acessa, registra no UC e faz deploy em Model Serving. | modelo `netbricks_agent` + endpoint de serving |
| **6** | `06_teste_agente.py` | Executa o `agent.py` **localmente no notebook** (credenciais do usuário, sem deploy) e valida as 3 ferramentas. | respostas das 3 perguntas de teste |

> **Parâmetros:** em cada notebook, ajuste os widgets `catalog` e `schema` antes de rodar.
> A ordem **0 → 6** é obrigatória (cada etapa consome a saída da anterior).

---

## O agente híbrido (`agent.py`)

`ChatAgent` do Mosaic AI Agent Framework. O próprio LLM (Claude Sonnet) escolhe entre 3
ferramentas via *tool calling* (loop de até 5 rodadas):

| Ferramenta | Tipo | Para quê |
|------------|------|----------|
| `buscar_titulos` | Vector Search (`catalogo_index`) | Descoberta/recomendação por tema ou clima |
| `suporte` | RAG (`ajuda_index`) | Dúvidas de conta/plano/cobrança/cancelamento |
| `consultar_dados` | SQL parametrizado seguro | Métricas agregadas (títulos por gênero, usuários por plano, churn por plano, total de títulos) |

É um arquivo importável (`from agent import AGENT`), com defaults que já batem com os recursos do
lab — roda tanto no notebook (06) quanto no serving (05). O warehouse para `consultar_dados` é
descoberto automaticamente; para fixar um, defina a variável de ambiente `WAREHOUSE_ID` (ou o
widget no notebook 05).

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

## Sobre o deploy do agente (notebook 05)

O `agents.deploy` publica o agente em Model Serving e, para isso, **cria uma service principal**
para o endpoint. Requisitos: cota de service principals disponível na conta e os *resources*
declarados (índices de Vector Search, endpoints de FM e um SQL warehouse).

Se o deploy falhar por limite de recursos da conta (ex.: cota de service principals esgotada), o
agente continua **totalmente funcional via notebook/job** — use o **notebook 06** para rodá-lo
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
