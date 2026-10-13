# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///

# COMMAND ----------

# MAGIC %md
# MAGIC # 02 · Deploy do Agente Híbrido — Netbricks Prime
# MAGIC Loga o `agent.py`, registra no Unity Catalog e faz deploy em Model Serving.
# MAGIC
# MAGIC > O `agent.py` é um **`ResponsesAgent`** (interface OpenAI Responses API), compatível ao mesmo
# MAGIC > tempo com o **AI Playground** e com o template de **App "Chat UI for existing Agent"** (que
# MAGIC > envia `input` + blocos `input_text`) — sem ajuste no cliente.
# MAGIC
# MAGIC > Usa **MLflow 3** (`mlflow[databricks]>=3.1`), o que habilita o **tracing em tempo real**
# MAGIC > do agente no endpoint (os spans `@mlflow.trace` do `agent.py` aparecem no experimento/Review App).
# MAGIC
# MAGIC ## Autenticação
# MAGIC - **Credenciais de sistema** (service principal do endpoint) para Vector Search e embeddings
# MAGIC   — declarados como *resources* e autorizados automaticamente no deploy.
# MAGIC - **On-behalf-of-user (OBO)** para o **LLM** (via Unity Gateway, `/ai-gateway/mlflow/v1`) e o
# MAGIC   **Genie** — chamados como o usuário que invoca o agente (escopos `model-serving`,
# MAGIC   `ai-gateway` e `genie`).
# MAGIC
# MAGIC > ⚠️ **Pré-requisito (admin do workspace):** habilite o preview
# MAGIC > **"Agent Framework: On-Behalf-Of-User Authorization"** em *(seu usuário) → Previews* antes do deploy.

# COMMAND ----------

# MAGIC %pip install --quiet -U "mlflow[databricks]>=3.1" databricks-vectorsearch databricks-agents databricks-sdk databricks-ai-bridge "openai>=1.109.1,<3"
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# CATALOG, SCHEMA e VS_ENDPOINT vêm do _config. Aqui só o que é específico do deploy.
dbutils.widgets.text("genie_space_id", "", "Genie Space ID (obrigatório)")
# Modelo do LLM pelo nome de 3 partes no Unity Catalog (model service do Unity Gateway),
# chamado pela API unificada do gateway (/ai-gateway/mlflow/v1).
# Default: system.ai.claude-opus-4-8. Troque por outro model service (ex.: system.ai.claude-sonnet-4-5
# ou um catalog.schema.nome do seu catálogo).
dbutils.widgets.text("llm", "system.ai.claude-opus-4-8", "Modelo do LLM (nome UC de 3 partes)")
GENIE_SPACE_ID = dbutils.widgets.get("genie_space_id").strip()

IDX_CAT = f"{CATALOG}.{SCHEMA}.catalogo_index"
IDX_AJU = f"{CATALOG}.{SCHEMA}.ajuda_index"
LLM = dbutils.widgets.get("llm").strip()
EMB = "databricks-gte-large-en"
AGENT_MODEL = f"{CATALOG}.{SCHEMA}.netbricks_agent_{SCHEMA}"  # nome com schema, isolado por participante
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
from importlib.metadata import version

mlflow.set_registry_uri("databricks-uc")

# Experimento MLflow explícito e idempotente — não depende do experimento padrão do notebook
# (que, se estiver na lixeira, causa "lifecycle stage is: deleted" ao reexecutar o lab).
from mlflow.entities import ViewType
from mlflow.tracking import MlflowClient

_exp_nome = f"/Users/{spark.sql('SELECT current_user()').first()[0]}/netbricks_prime_agent_{SCHEMA}"
_cli = MlflowClient()
_achados = _cli.search_experiments(view_type=ViewType.ALL, filter_string=f"name = '{_exp_nome}'")
if _achados and _achados[0].lifecycle_stage == "deleted":
    _cli.restore_experiment(_achados[0].experiment_id)
mlflow.set_experiment(_exp_nome)

# AUTENTICAÇÃO HÍBRIDA:
#  - SystemAuthPolicy (resources): VS (índices catálogo/ajuda) e embeddings usam as credenciais
#    de sistema (SP do endpoint), autorizadas automaticamente no deploy.
#  - UserAuthPolicy (api_scopes): LLM e Genie são chamados via OBO (como o usuário):
#    o LLM via Unity Gateway (/ai-gateway/...) usa model-serving + ai-gateway;
#    genie cobre o Genie Space.
system_policy = SystemAuthPolicy(resources=[
    DatabricksVectorSearchIndex(index_name=IDX_CAT),
    DatabricksVectorSearchIndex(index_name=IDX_AJU),
    DatabricksServingEndpoint(endpoint_name=EMB),
])
user_policy = UserAuthPolicy(api_scopes=["model-serving", "ai-gateway", "genie"])
auth_policy = AuthPolicy(system_auth_policy=system_policy, user_auth_policy=user_policy)
# input_example no formato Responses API (input + role/content) — o que o App e o Playground enviam.
input_example = {"input": [{"role": "user", "content": "me recomenda uma ficção científica leve"}]}

# COMMAND ----------

with mlflow.start_run(run_name="netbricks_agent"):
    logged = mlflow.pyfunc.log_model(
        name="agent", python_model="agent.py",
        input_example=input_example, auth_policy=auth_policy,
        pip_requirements=[f"mlflow[databricks]=={version('mlflow')}",
                          f"databricks-vectorsearch=={version('databricks-vectorsearch')}",
                          f"databricks-sdk=={version('databricks-sdk')}",
                          f"databricks-ai-bridge=={version('databricks-ai-bridge')}",
                          f"openai=={version('openai')}"],
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
