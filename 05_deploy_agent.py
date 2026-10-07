# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Deploy do Agente Híbrido — Netbricks Prime
# MAGIC Loga o `agent.py` (com os *resources* que ele acessa), registra no Unity Catalog e
# MAGIC faz deploy em Model Serving.

# COMMAND ----------

# MAGIC %pip install --quiet -U mlflow databricks-vectorsearch databricks-agents databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "main", "Catálogo (deve existir)")
dbutils.widgets.text("schema", "netbricks_prime", "Schema")
dbutils.widgets.text("warehouse_id", "", "SQL Warehouse ID (vazio = auto)")
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()

VS_ENDPOINT = f"netbricks_vs_{SCHEMA}"
IDX_CAT = f"{CATALOG}.{SCHEMA}.catalogo_index"
IDX_AJU = f"{CATALOG}.{SCHEMA}.ajuda_index"
LLM = "databricks-claude-sonnet-5"
EMB = "databricks-gte-large-en"

# Warehouse: usa o informado no widget; senão descobre um disponível no workspace.
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id").strip()
if not WAREHOUSE_ID:
    from databricks.sdk import WorkspaceClient
    _whs = list(WorkspaceClient().warehouses.list())
    assert _whs, "Nenhum SQL warehouse disponível neste workspace."
    _run = [w for w in _whs if str(getattr(w.state, "value", w.state)) == "RUNNING"]
    WAREHOUSE_ID = (_run or _whs)[0].id
print("SQL Warehouse:", WAREHOUSE_ID)

AGENT_MODEL = f"{CATALOG}.{SCHEMA}.netbricks_agent"
AGENT_ENDPOINT = f"netbricks_agent_{SCHEMA}"  # serving endpoint é global no workspace

import os
os.environ.update({"VS_ENDPOINT": VS_ENDPOINT, "IDX_CAT": IDX_CAT, "IDX_AJU": IDX_AJU,
                   "LLM_MODEL": LLM, "WAREHOUSE_ID": WAREHOUSE_ID,
                   "CATALOG": CATALOG, "SCHEMA": SCHEMA})

# COMMAND ----------

import mlflow
from mlflow.models.resources import (DatabricksVectorSearchIndex, DatabricksServingEndpoint,
                                      DatabricksSQLWarehouse)
from pkg_resources import get_distribution

mlflow.set_registry_uri("databricks-uc")

resources = [
    DatabricksVectorSearchIndex(index_name=IDX_CAT),
    DatabricksVectorSearchIndex(index_name=IDX_AJU),
    DatabricksServingEndpoint(endpoint_name=LLM),
    DatabricksServingEndpoint(endpoint_name=EMB),
    DatabricksSQLWarehouse(warehouse_id=WAREHOUSE_ID),
]
input_example = {"messages": [{"role": "user", "content": "me recomenda uma ficção científica leve"}]}

# COMMAND ----------

with mlflow.start_run(run_name="netbricks_agent"):
    logged = mlflow.pyfunc.log_model(
        artifact_path="agent", python_model="agent.py",
        input_example=input_example, resources=resources,
        pip_requirements=[f"mlflow=={get_distribution('mlflow').version}",
                          f"databricks-vectorsearch=={get_distribution('databricks-vectorsearch').version}",
                          f"databricks-sdk=={get_distribution('databricks-sdk').version}"],
    )
print("✅ logado:", logged.model_uri)

# COMMAND ----------

reg = mlflow.register_model(model_uri=logged.model_uri, name=AGENT_MODEL)
print(f"✅ registrado {AGENT_MODEL} v{reg.version}")

# COMMAND ----------

from databricks import agents
agents.deploy(model_name=AGENT_MODEL, model_version=reg.version,
              endpoint_name=AGENT_ENDPOINT, scale_to_zero=True)
print(f"✅ deploy iniciado: {AGENT_ENDPOINT}")
