# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Deploy do Agente Híbrido — Netbricks Prime
# MAGIC Loga o `agent.py`, registra no Unity Catalog e faz deploy em Model Serving.
# MAGIC A ferramenta de dados usa um **Genie Space** (API REST do SDK, via OBO).
# MAGIC
# MAGIC ## Autenticação híbrida (importante)
# MAGIC - **Credenciais de sistema** (service principal do endpoint) para Vector Search e embeddings
# MAGIC   — declarados como *resources* e autorizados automaticamente no deploy.
# MAGIC - **On-behalf-of-user (OBO)** para o **LLM** e o **Genie**:
# MAGIC   - `databricks-llama-4-maverick` é um Foundation Model pay-per-token em `system.ai` e exige
# MAGIC     que **quem chama** tenha `USE CATALOG on system`.
# MAGIC   - O **Genie** executa o SQL como quem chama, então precisa de acesso às tabelas/warehouse.
# MAGIC   - O SP do endpoint não tem nenhum dos dois; o usuário do lab tem. Então LLM e Genie são
# MAGIC     chamados como o usuário (escopos `serving.serving-endpoints` e `dashboards.genie`).
# MAGIC
# MAGIC > ⚠️ **Pré-requisito único (admin do workspace):** habilite o preview
# MAGIC > **"Agent Framework: On-Behalf-Of-User Authorization"** em *(seu usuário) → Previews*.
# MAGIC > Sem isso o Model Serving não encaminha o token do usuário e o LLM falha com 403.

# COMMAND ----------

# MAGIC %pip install --quiet -U mlflow databricks-vectorsearch databricks-agents databricks-sdk databricks-ai-bridge openai
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# CATALOG, SCHEMA e VS_ENDPOINT vêm do _config. Aqui só o que é específico do deploy.
dbutils.widgets.text("genie_space_id", "", "Genie Space ID (obrigatório)")
# Endpoint de LLM: Foundation Model com tool calling. Chamado via OBO (como o usuário), então
# NÃO precisa de EXECUTE em system.ai para o SP — basta o usuário do lab ter acesso ao modelo.
# Default: databricks-llama-4-maverick. Troque se quiser (ex.: databricks-gpt-5-2, databricks-claude-sonnet-5).
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
from mlflow.models.auth_policy import AuthPolicy, SystemAuthPolicy, UserAuthPolicy
from mlflow.models.resources import DatabricksVectorSearchIndex, DatabricksServingEndpoint
from pkg_resources import get_distribution

mlflow.set_registry_uri("databricks-uc")

# AUTENTICAÇÃO HÍBRIDA:
#  - SystemAuthPolicy (resources): VS (índices catálogo/ajuda) e embeddings usam as credenciais
#    de sistema (SP do endpoint), autorizadas automaticamente no deploy.
#  - UserAuthPolicy (api_scopes): LLM e Genie são chamados via OBO (como o usuário). O escopo
#    serving.serving-endpoints cobre o Foundation Model em system.ai; dashboards.genie cobre o
#    Genie Space (que executa o SQL como o usuário, com acesso às tabelas/warehouse do lab).
system_policy = SystemAuthPolicy(resources=[
    DatabricksVectorSearchIndex(index_name=IDX_CAT),
    DatabricksVectorSearchIndex(index_name=IDX_AJU),
    DatabricksServingEndpoint(endpoint_name=EMB),
])
user_policy = UserAuthPolicy(api_scopes=["serving.serving-endpoints", "dashboards.genie"])
auth_policy = AuthPolicy(system_auth_policy=system_policy, user_auth_policy=user_policy)
input_example = {"messages": [{"role": "user", "content": "me recomenda uma ficção científica leve"}]}

# COMMAND ----------

with mlflow.start_run(run_name="netbricks_agent"):
    logged = mlflow.pyfunc.log_model(
        artifact_path="agent", python_model="agent.py",
        input_example=input_example, auth_policy=auth_policy,
        pip_requirements=[f"mlflow=={get_distribution('mlflow').version}",
                          f"databricks-vectorsearch=={get_distribution('databricks-vectorsearch').version}",
                          f"databricks-sdk=={get_distribution('databricks-sdk').version}",
                          f"databricks-ai-bridge=={get_distribution('databricks-ai-bridge').version}",
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
