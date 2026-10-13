# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///

# COMMAND ----------

# MAGIC %md
# MAGIC # 99 · Limpar ambiente (cleanup) — Netbricks Prime
# MAGIC
# MAGIC Remove **tudo** que o lab cria, na ordem correta de dependência:
# MAGIC
# MAGIC | Ordem | Objeto | Onde vive |
# MAGIC |------:|--------|-----------|
# MAGIC | 1 | **App** `chat-netbricks` | Databricks Apps |
# MAGIC | 2 | **Endpoint do agente** `netbricks_agent_<schema>` | Model Serving |
# MAGIC | 3 | **Índices de Vector Search** `catalogo_index`, `ajuda_index` | Vector Search |
# MAGIC | 4 | **Endpoint de Vector Search** `netbricks_vs_<schema>` | Vector Search |
# MAGIC | 5 | **Genie Agent** `Netbricks Prime — Genie de Dados` | Genie |
# MAGIC | 6 | **Dados e modelos** (tabelas + modelos UC do schema) | Unity Catalog |
# MAGIC | 7 | **Experimentos MLflow** `netbricks_prime_{agent,churn,upgrade}_<schema>` | MLflow |
# MAGIC
# MAGIC > ⚠️ **Ação destrutiva e irreversível.** Nada é apagado enquanto o widget **`confirmar`** não
# MAGIC > estiver em **`sim`**. Catálogo e schema vêm do **`_config`** — confirme que apontam para o
# MAGIC > ambiente certo antes de rodar. O **catálogo não é tocado** (só o schema do lab).

# COMMAND ----------

# MAGIC %pip install --quiet -U databricks-sdk databricks-vectorsearch
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

dbutils.widgets.dropdown("confirmar", "nao", ["nao", "sim"], "Confirmar exclusão")
dbutils.widgets.dropdown("drop_schema", "sim", ["sim", "nao"], "Apagar o schema inteiro")
dbutils.widgets.text("app_name", "chat-netbricks", "Nome do App")
dbutils.widgets.text("genie_space_name", "Netbricks Prime — Genie de Dados", "Nome do Genie Agent")
dbutils.widgets.text("genie_space_id", "", "Genie Agent ID (opcional)")

APP_NAME = dbutils.widgets.get("app_name").strip()
GENIE_NAME = dbutils.widgets.get("genie_space_name").strip()
GENIE_ID = dbutils.widgets.get("genie_space_id").strip()
DROP_SCHEMA = dbutils.widgets.get("drop_schema") == "sim"

AGENT_ENDPOINT = f"netbricks_agent_{SCHEMA}"
IDX_CAT = f"{CATALOG}.{SCHEMA}.catalogo_index"
IDX_AJU = f"{CATALOG}.{SCHEMA}.ajuda_index"
TABELAS = ["catalogo", "usuarios", "eventos_visualizacao", "central_ajuda_kb",
           "features_usuarios", "scores_churn", "scores_upgrade"]
MODELOS = [f"netbricks_agent_{SCHEMA}", f"modelo_churn_{SCHEMA}", f"modelo_upgrade_{SCHEMA}"]
# Experimentos MLflow (um por workload) — vivem em /Users, não são tocados pelo DROP SCHEMA.
_user = spark.sql("SELECT current_user()").first()[0]
EXPERIMENTOS = [f"/Users/{_user}/netbricks_prime_agent_{SCHEMA}",
                f"/Users/{_user}/netbricks_prime_churn_{SCHEMA}",
                f"/Users/{_user}/netbricks_prime_upgrade_{SCHEMA}"]

print(f"Alvo do cleanup → {CATALOG}.{SCHEMA}")
print(f"  App: {APP_NAME} | Genie: {GENIE_NAME} | VS endpoint: {VS_ENDPOINT} | Agent endpoint: {AGENT_ENDPOINT}")
print(f"  Apagar schema inteiro: {'SIM' if DROP_SCHEMA else 'não (só tabelas/modelos conhecidos)'}")

# COMMAND ----------

# Gate de segurança: sem confirmar=sim o notebook para aqui, sem apagar nada.
if dbutils.widgets.get("confirmar") != "sim":
    dbutils.notebook.exit(
        "Cleanup NÃO executado. Para apagar os objetos, defina o widget 'confirmar' = 'sim' e rode de novo.")

# COMMAND ----------

from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

def step(label, fn):
    """Executa uma exclusão de forma idempotente, reportando o resultado."""
    try:
        fn()
        print(f"✅ {label}")
    except Exception as e:
        msg = str(e)
        if any(k in msg.lower() for k in
               ("not found", "does not exist", "resource_does_not_exist", "no such", "nonexistent")):
            print(f"• {label}: já não existe")
        else:
            print(f"⚠️ {label}: {msg[:160]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1) App `chat-netbricks`

# COMMAND ----------

step(f"App '{APP_NAME}' removido", lambda: w.apps.delete(name=APP_NAME))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2) Endpoint de serving do agente

# COMMAND ----------

step(f"Endpoint de serving '{AGENT_ENDPOINT}' removido",
     lambda: w.serving_endpoints.delete(name=AGENT_ENDPOINT))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3–4) Vector Search (índices + endpoint)

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient
vsc = VectorSearchClient(disable_notice=True)

for idx in (IDX_CAT, IDX_AJU):
    step(f"Índice VS '{idx}' removido",
         lambda idx=idx: vsc.delete_index(endpoint_name=VS_ENDPOINT, index_name=idx))

step(f"Endpoint VS '{VS_ENDPOINT}' removido", lambda: vsc.delete_endpoint(name=VS_ENDPOINT))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5) Genie Agent `Netbricks Prime — Genie de Dados`
# MAGIC Localiza o Space pelo nome (ou usa o ID informado no widget) e o remove via API. Se a API
# MAGIC não permitir a exclusão, o notebook indica como apagar pela UI.

# COMMAND ----------

def deletar_genie():
    alvo_id = GENIE_ID
    if not alvo_id:
        try:
            resp = w.genie.list_spaces()
            for sp in (getattr(resp, "spaces", None) or []):
                titulo = getattr(sp, "title", None) or getattr(sp, "name", "")
                if titulo == GENIE_NAME:
                    alvo_id = sp.space_id
                    break
        except Exception as e:
            print(f"⚠️ não consegui listar os Genie spaces ({str(e)[:100]}).")
            print(f"   Apague manualmente na UI: Genie → '{GENIE_NAME}' → ⋯ → Delete.")
            return
    if not alvo_id:
        print(f"• Genie Agent '{GENIE_NAME}' não encontrado (ou já removido).")
        return
    try:
        w.api_client.do("DELETE", f"/api/2.0/genie/spaces/{alvo_id}")
        print(f"✅ Genie Agent removido: '{GENIE_NAME}' (ID {alvo_id})")
    except Exception as e:
        print(f"⚠️ não foi possível remover o Genie Agent via API ({str(e)[:100]}).")
        print(f"   Apague manualmente na UI: Genie → '{GENIE_NAME}' → ⋯ → Delete (ID {alvo_id}).")

deletar_genie()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6) Dados e modelos no Unity Catalog
# MAGIC Com `drop_schema = sim`, remove o schema inteiro (tabelas + modelos) com `CASCADE`.
# MAGIC Com `nao`, remove apenas os objetos conhecidos do lab e preserva o schema.

# COMMAND ----------

if DROP_SCHEMA:
    step(f"Schema '{CATALOG}.{SCHEMA}' removido (CASCADE)",
         lambda: spark.sql(f"DROP SCHEMA IF EXISTS `{CATALOG}`.`{SCHEMA}` CASCADE"))
else:
    for m in MODELOS:
        step(f"Modelo UC '{m}' removido",
             lambda m=m: w.registered_models.delete(full_name=f"{CATALOG}.{SCHEMA}.{m}"))
    for t in TABELAS:
        step(f"Tabela '{t}' removida",
             lambda t=t: spark.sql(f"DROP TABLE IF EXISTS `{CATALOG}`.`{SCHEMA}`.`{t}`"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7) Experimentos MLflow
# MAGIC Remove os experimentos do lab (`agent`, `churn`, `upgrade`). Eles vivem em `/Users/...`,
# MAGIC então **não** são removidos pelo `DROP SCHEMA` — por isso são tratados aqui.

# COMMAND ----------

import mlflow
from mlflow.tracking import MlflowClient
_mcli = MlflowClient()

def deletar_experimento(nome):
    exp = _mcli.get_experiment_by_name(nome)
    if exp is None:
        raise Exception("does not exist")
    _mcli.delete_experiment(exp.experiment_id)

for exp_nome in EXPERIMENTOS:
    step(f"Experimento '{exp_nome}' removido", lambda n=exp_nome: deletar_experimento(n))

# COMMAND ----------

print(f"🧹 Cleanup concluído em {CATALOG}.{SCHEMA}.")
