# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Conceder escopos ao App — Netbricks Prime
# MAGIC
# MAGIC Último passo do lab: concede ao **App** (`chat-netbricks`) os escopos de API que ele precisa
# MAGIC para chamar, **em nome do usuário**, o agente, o Genie e o Vector Search.
# MAGIC
# MAGIC Faz um `PATCH /api/2.0/apps/{APP_NAME}` atualizando os `user_api_scopes`. Rode **depois** de
# MAGIC criar o App apontando para o agente já publicado (notebook `02`).

# COMMAND ----------

# DBTITLE 1,Parâmetros
dbutils.widgets.text("APP_NAME", "chat-netbricks", "Nome do App")
APP_NAME = dbutils.widgets.get("APP_NAME").strip()

# COMMAND ----------

# DBTITLE 1,Atualizar escopos do app
import requests

host = spark.conf.get("spark.databricks.workspaceUrl")
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

response = requests.patch(
    f"https://{host}/api/2.0/apps/{APP_NAME}",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json={
        "user_api_scopes": [
            "sql",
            "genie",
            "dashboards.genie",
            "model-serving",
            "serving.serving-endpoints",
            "ai-gateway",
            "catalog.catalogs:read",
            "catalog.schemas:read",
            "catalog.tables:read",
            "vector-search",
        ]
    },
)

result = response.json()
print(f"Status: {response.status_code}")
print(f"Escopos aplicados: {result.get('user_api_scopes')}")
print(f"Escopos efetivos: {result.get('effective_user_api_scopes')}")
