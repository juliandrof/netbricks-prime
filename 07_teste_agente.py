# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Teste do Agente Híbrido (local, sem deploy)
# MAGIC Executa o `agent.py` com credenciais do notebook e valida as 3 ferramentas
# MAGIC (a de dados usa o **Genie Space via MCP**).

# COMMAND ----------

# MAGIC %pip install --quiet -U mlflow databricks-vectorsearch databricks-sdk databricks-mcp openai
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

# CATALOG, SCHEMA e VS_ENDPOINT vêm do _config. Aqui só o que é específico do teste.
dbutils.widgets.text("genie_space_id", "", "Genie Space ID")
# Use o mesmo LLM do deploy (o endpoint/SP precisa ter EXECUTE nesse Foundation Model).
dbutils.widgets.text("llm", "databricks-llama-4-maverick", "Endpoint do LLM")

import os
os.environ["CATALOG"] = CATALOG
os.environ["SCHEMA"] = SCHEMA
os.environ["VS_ENDPOINT"] = VS_ENDPOINT
os.environ["GENIE_SPACE_ID"] = dbutils.widgets.get("genie_space_id").strip()
os.environ["LLM_MODEL"] = dbutils.widgets.get("llm").strip()

# COMMAND ----------

from agent import AGENT
from mlflow.types.agent import ChatAgentMessage

def perguntar(q):
    r = AGENT.predict(messages=[ChatAgentMessage(role="user", content=q, id="1")])
    return r.messages[0].content

perguntas = [
    "Me recomenda uma ficção científica, mas mais leve e curta.",
    "Como faço para cancelar minha assinatura? Tem multa?",
    "Quantos títulos vocês têm por gênero?",
]
saida = []
for q in perguntas:
    resp = perguntar(q)
    saida.append(f"👤 {q}\n🤖 {resp[:700]}")

resultado = "\n\n" + ("\n" + "-" * 60 + "\n").join(saida)
print(resultado)
dbutils.notebook.exit(resultado)
