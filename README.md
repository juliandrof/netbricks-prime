# 🎬 Netbricks Prime — Lab de Streaming no Databricks

Lab fim-a-fim de uma plataforma de streaming fictícia (**Netbricks Prime**, da **XPTO Company**)
sobre a Lakehouse. Cobre **geração de dados em escala → engenharia de atributos → dois modelos
de ML (churn e propensão de upgrade) → Vector Search → um agente híbrido (Mosaic AI Agent
Framework)**.

> Nenhum dado é real: usuários, títulos, e-mails (`@netbricksprime.com`) e artigos de ajuda são
> todos sintéticos e gerados de forma determinística.

---

## Ambiente

| Item | Valor |
|------|-------|
| Workspace | `fevm-jsfws` — https://fevm-jsfws.cloud.databricks.com |
| Catálogo | `jsfws_catalog` |
| Schema | `netbricks_prime` *(criado pelo notebook 0; o catálogo **não** é criado)* |
| Compute | Serverless notebooks / jobs |
| LLM | `databricks-claude-sonnet-5` |
| Embeddings | `databricks-gte-large-en` |
| Vector Search endpoint | `netbricks_vs_endpoint` |

Todos os notebooks têm **widgets `catalog` e `schema`** (padrão `jsfws_catalog` / `netbricks_prime`),
então o lab pode ser recriado em qualquer catálogo existente apenas trocando os parâmetros.

---

## Pré-requisitos

- Acesso ao workspace com permissão de criar schema/tabelas no catálogo escolhido.
- Serverless compute habilitado.
- Vector Search habilitado no workspace.
- Para o **deploy** do agente (notebook 05): cota de *service principals* disponível na conta
  (ver [caveat](#-caveat-do-deploy-do-agente)).

---

## Passo a passo (ordem de execução)

| # | Notebook | O que faz | Saídas principais |
|---|----------|-----------|-------------------|
| **0** | `netbricks_prime_gerar_dados.py` | Gera toda a base de forma determinística e com **sinal comportamental** (engajamento latente governa plano, churn e volume de eventos). Cria o schema. | `catalogo` (10k títulos, PK + CDF), `usuarios` (120k), `eventos_visualizacao` (1M, particionado), `central_ajuda_kb` (12 artigos, PK + CDF) |
| **1** | `01_feature_engineering.py` | Agrega eventos por usuário e junta com o perfil. | `features_usuarios` |
| **2** | `02_modelo_churn.py` | Treina classificador de **churn** (`status = 'Cancelado'`), registra no UC e escora toda a base. | modelo `modelo_churn`, tabela `scores_churn` (prob + faixa de risco) |
| **3** | `03_modelo_upgrade.py` | Treina **propensão de upgrade** (`is_pago`) e aplica aos usuários **Free** — os de maior probabilidade são os melhores alvos de conversão. | modelo `modelo_upgrade`, tabela `scores_upgrade` |
| **4** | `04_vector_search.py` | Cria o endpoint VS e dois índices Delta Sync. | `catalogo_index` (sinopse), `ajuda_index` (conteúdo) |
| **5** | `05_deploy_agent.py` | Loga `agent.py` com os *resources* que acessa, registra no UC e faz deploy em Model Serving. | modelo `netbricks_agent` *(deploy — ver caveat)* |
| **6** | `06_teste_agente.py` | Executa o `agent.py` **localmente no notebook** (credenciais do usuário, sem SP) e valida as 3 ferramentas. | respostas das 3 perguntas de teste |

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
lab — roda tanto no notebook (06) quanto no serving (05).

---

## ⚠️ Caveat do deploy do agente

O deploy em Model Serving (notebook 05) pode falhar com:

```
RESOURCE_EXHAUSTED: Cannot have more than 100000 users and service principals in one account.
```

Isso é um **limite da conta compartilhada do FEVM**, não um problema de código: o `agents.deploy`
precisa criar uma *service principal* para o endpoint, e a conta está no teto de 100k principais.
O código do agente está **validado e funcionando** (notebook 06). Opções para publicar:

- tentar novamente mais tarde (conforme SPs forem liberadas na conta);
- liberar SPs / solicitar aumento de cota (ação de admin da conta);
- usar outro workspace/conta fora do limite;
- enquanto isso, rodar o agente via notebook/job (como no notebook 06).

---

## Objetos criados em `jsfws_catalog.netbricks_prime`

**Tabelas:** `catalogo`, `usuarios`, `eventos_visualizacao`, `central_ajuda_kb`,
`features_usuarios`, `scores_churn`, `scores_upgrade`
**Modelos (UC):** `modelo_churn`, `modelo_upgrade`, `netbricks_agent`
**Vector Search:** endpoint `netbricks_vs_endpoint` + índices `catalogo_index`, `ajuda_index`

---

*Lab construído por um Field Engineer da Databricks para fins de demonstração.*
