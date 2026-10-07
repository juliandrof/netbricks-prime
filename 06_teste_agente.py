# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Teste do Agente Híbrido (local, sem deploy)
# MAGIC Executa o `agent.py` com credenciais do notebook e valida as 3 ferramentas.

# COMMAND ----------

# MAGIC %pip install --quiet -U mlflow databricks-vectorsearch databricks-sdk
# MAGIC %restart_python

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
