# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Feature Engineering — Netbricks Prime
# MAGIC
# MAGIC Consolida, por usuário, features de **engajamento** (a partir de 1M de eventos) +
# MAGIC atributos de perfil. Essa tabela alimenta os modelos de **churn** e **propensão de
# MAGIC upgrade**.

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

TBL_USR = f"{CATALOG}.{SCHEMA}.usuarios"
TBL_EVT = f"{CATALOG}.{SCHEMA}.eventos_visualizacao"
TBL_CAT = f"{CATALOG}.{SCHEMA}.catalogo"
TBL_FEAT = f"{CATALOG}.{SCHEMA}.features_usuarios"
print(f"Features -> {TBL_FEAT}")

# COMMAND ----------

# Agrega features de engajamento por usuário e junta com o perfil.
spark.sql(f"""
CREATE OR REPLACE TABLE {TBL_FEAT} AS
WITH eng AS (
  SELECT
    e.user_id,
    COUNT(*)                                             AS total_eventos,
    SUM(e.watch_time_min)                                AS watch_total_min,
    AVG(e.watch_time_min)                                AS watch_medio_min,
    AVG(e.pct_assistido)                                 AS pct_assistido_medio,
    AVG(CASE WHEN e.evento = 'complete' THEN 1.0 ELSE 0 END) AS taxa_conclusao,
    COUNT(DISTINCT c.genero_principal)                   AS n_generos,
    COUNT(DISTINCT e.dispositivo)                        AS n_dispositivos,
    DATEDIFF(current_date(), MAX(DATE(e.data_hora)))     AS recencia_dias
  FROM {TBL_EVT} e
  LEFT JOIN {TBL_CAT} c USING (content_id)
  GROUP BY e.user_id
)
SELECT
  u.user_id,
  u.plano,
  u.uf,
  u.faixa_etaria,
  u.dispositivo_principal,
  DATEDIFF(current_date(), u.data_assinatura)  AS dias_casa,
  u.status,
  COALESCE(eng.total_eventos, 0)               AS total_eventos,
  COALESCE(eng.watch_total_min, 0)             AS watch_total_min,
  COALESCE(eng.watch_medio_min, 0)             AS watch_medio_min,
  COALESCE(eng.pct_assistido_medio, 0)         AS pct_assistido_medio,
  COALESCE(eng.taxa_conclusao, 0)              AS taxa_conclusao,
  COALESCE(eng.n_generos, 0)                   AS n_generos,
  COALESCE(eng.n_dispositivos, 0)              AS n_dispositivos,
  COALESCE(eng.recencia_dias, 999)             AS recencia_dias
FROM {TBL_USR} u
LEFT JOIN eng USING (user_id)
""")

n = spark.table(TBL_FEAT).count()
print(f"✅ {n:,} linhas em {TBL_FEAT}")
display(spark.sql(f"SELECT * FROM {TBL_FEAT} LIMIT 10"))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Sanidade: features de engajamento por status (deve haver diferença clara)

# COMMAND ----------

display(spark.sql(f"""
  SELECT status, COUNT(*) usuarios,
         ROUND(AVG(total_eventos),1) ev_medio,
         ROUND(AVG(watch_total_min),0) watch_total,
         ROUND(AVG(taxa_conclusao),3) conclusao
  FROM {TBL_FEAT} GROUP BY status
"""))
