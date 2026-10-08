# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Deploy do Agente Híbrido — Netbricks Prime
# MAGIC Loga o `agent.py` (com os *resources* que ele acessa), registra no Unity Catalog e
# MAGIC faz deploy em Model Serving. A ferramenta de dados usa um **Genie Space via MCP**.

# COMMAND ----------

# MAGIC %pip install --quiet -U mlflow databricks-vectorsearch databricks-agents databricks-sdk databricks-mcp openai
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# CATALOG, SCHEMA e VS_ENDPOINT vêm do _config. Aqui só o que é específico do deploy.
dbutils.widgets.text("genie_space_id", "", "Genie Space ID (obrigatório)")
# Endpoint de LLM: precisa ser um Foundation Model (com tool calling) em que o SP do endpoint
# tenha EXECUTE em system.ai. Default: databricks-llama-4-maverick. Troque se quiser outro
# (ex.: databricks-gpt-5-2, databricks-claude-sonnet-5).
dbutils.widgets.text("llm", "databricks-llama-4-maverick", "Endpoint do LLM")
GENIE_SPACE_ID = dbutils.widgets.get("genie_space_id").strip()

IDX_CAT = f"{CATALOG}.{SCHEMA}.catalogo_index"
IDX_AJU = f"{CATALOG}.{SCHEMA}.ajuda_index"
LLM = dbutils.widgets.get("llm").strip()
EMB = "databricks-gte-large-en"
AGENT_MODEL = f"{CATALOG}.{SCHEMA}.netbricks_agent"
AGENT_ENDPOINT = f"netbricks_agent_{SCHEMA}"  # serving endpoint é global no workspace

import os
# Config que o agent.py lê de variáveis de ambiente. Precisa valer TANTO aqui (log/validação)
# QUANTO no container de serving — por isso é passada em environment_vars no agents.deploy.
ENV = {"VS_ENDPOINT": VS_ENDPOINT, "IDX_CAT": IDX_CAT, "IDX_AJU": IDX_AJU,
       "LLM_MODEL": LLM, "GENIE_SPACE_ID": GENIE_SPACE_ID,
       "CATALOG": CATALOG, "SCHEMA": SCHEMA}
os.environ.update(ENV)

# COMMAND ----------

import mlflow
from mlflow.models.resources import (DatabricksVectorSearchIndex, DatabricksServingEndpoint,
                                      DatabricksGenieSpace)
from pkg_resources import get_distribution

mlflow.set_registry_uri("databricks-uc")

# AUTENTICAÇÃO POR CREDENCIAIS DE SISTEMA (service principal do endpoint):
# os resources declarados abaixo são autorizados automaticamente no deploy —
#   - Vector Search (índices catálogo/ajuda) e endpoint de embeddings
#   - Genie Space (ferramenta de dados via MCP)
#   - o endpoint do LLM (Foundation Model) → SP recebe CAN_QUERY.
# OBS: para Foundation Models em system.ai, o SP também precisa de EXECUTE em
# system.ai.<modelo> (ex.: databricks-llama-4-maverick). Isso é concedido no setup do lab
# por um metastore admin — o auto-grant não delega privilégios de system.ai.
resources = [
    DatabricksVectorSearchIndex(index_name=IDX_CAT),
    DatabricksVectorSearchIndex(index_name=IDX_AJU),
    DatabricksServingEndpoint(endpoint_name=EMB),
    DatabricksServingEndpoint(endpoint_name=LLM),
    DatabricksGenieSpace(genie_space_id=GENIE_SPACE_ID),
]
input_example = {"messages": [{"role": "user", "content": "me recomenda uma ficção científica leve"}]}

# COMMAND ----------

with mlflow.start_run(run_name="netbricks_agent"):
    logged = mlflow.pyfunc.log_model(
        artifact_path="agent", python_model="agent.py",
        input_example=input_example, resources=resources,
        pip_requirements=[f"mlflow=={get_distribution('mlflow').version}",
                          f"databricks-vectorsearch=={get_distribution('databricks-vectorsearch').version}",
                          f"databricks-sdk=={get_distribution('databricks-sdk').version}",
                          f"databricks-mcp=={get_distribution('databricks-mcp').version}",
                          f"openai=={get_distribution('openai').version}"],
    )
print("✅ logado:", logged.model_uri)

# COMMAND ----------

reg = mlflow.register_model(model_uri=logged.model_uri, name=AGENT_MODEL)
print(f"✅ registrado {AGENT_MODEL} v{reg.version}")

# COMMAND ----------

from databricks import agents
# environment_vars propaga a config para o container de serving (sem isso o agente usa defaults).
agents.deploy(model_name=AGENT_MODEL, model_version=reg.version,
              endpoint_name=AGENT_ENDPOINT, scale_to_zero=True,
              environment_vars=ENV)
print(f"✅ deploy iniciado: {AGENT_ENDPOINT}")
