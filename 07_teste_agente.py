# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Teste do Agente Híbrido (local, sem deploy)
# MAGIC Executa o `agent.py` com credenciais do notebook e valida as 3 ferramentas
# MAGIC (a de dados usa o **Genie Space via MCP**).

# COMMAND ----------

# MAGIC %pip install --quiet -U mlflow databricks-vectorsearch databricks-sdk databricks-mcp
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "netbricks_prime", "Catálogo")
dbutils.widgets.text("schema", "suas_iniciais_aqui", "Schema")
dbutils.widgets.text("genie_space_id", "", "Genie Space ID")

import os
os.environ["CATALOG"] = dbutils.widgets.get("catalog").strip()
os.environ["SCHEMA"] = dbutils.widgets.get("schema").strip()
os.environ["GENIE_SPACE_ID"] = dbutils.widgets.get("genie_space_id").strip()

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
