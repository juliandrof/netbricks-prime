# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Preparar ambiente — Netbricks Prime
# MAGIC
# MAGIC Notebook **orquestrador**: roda, em ordem, toda a fase de preparação do lab (dados + ML +
# MAGIC Vector Search), que fica na pasta **`preparacao/`**. Depois dele, siga para os notebooks do
# MAGIC agente: **01** (Genie Space) → **02** (deploy) → **03** (teste).
# MAGIC
# MAGIC | Passo | Notebook (em `preparacao/`) | O que faz |
# MAGIC |------:|-----------------------------|-----------|
# MAGIC | 1 | `00_gerar_dados` | Gera a base sintética (catálogo, usuários, eventos, central de ajuda) e cria o schema |
# MAGIC | 2 | `01_feature_engineering` | Consolida features de engajamento + perfil por usuário |
# MAGIC | 3 | `02_modelo_churn` | Treina e aplica o modelo de churn |
# MAGIC | 4 | `03_modelo_upgrade` | Treina e aplica o modelo de propensão de upgrade |
# MAGIC | 5 | `04_vector_search` | Cria o endpoint de Vector Search e os dois índices |
# MAGIC
# MAGIC > Cada passo roda isolado via `dbutils.notebook.run` (lida com os `%pip`/`%restart_python`
# MAGIC > de cada notebook). Se um passo falhar, a execução para ali.
# MAGIC >
# MAGIC > ⚠️ Catálogo e schema vêm do **`_config`** (edite lá antes de rodar).

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

NOTEBOOKS = [
    "preparacao/00_gerar_dados",
    "preparacao/01_feature_engineering",
    "preparacao/02_modelo_churn",
    "preparacao/03_modelo_upgrade",
    "preparacao/04_vector_search",
]

print(f"Alvo: {CATALOG}.{SCHEMA}\n")
for i, nb in enumerate(NOTEBOOKS, 1):
    print(f"▶ [{i}/{len(NOTEBOOKS)}] rodando {nb} ...")
    # timeout_seconds=0 → sem limite (a geração de dados pode levar alguns minutos).
    dbutils.notebook.run(nb, 0)
    print(f"✅ [{i}/{len(NOTEBOOKS)}] {nb} concluído\n")

print(f"🎉 Preparação concluída em {CATALOG}.{SCHEMA}. "
      f"Siga para 01_criar_genie_space → 02_deploy_agent → 03_testar_agente.")
