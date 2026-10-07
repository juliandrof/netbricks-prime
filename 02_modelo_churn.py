# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Modelo de Churn — Netbricks Prime
# MAGIC
# MAGIC Prevê a probabilidade de um assinante **cancelar** (`status = 'Cancelado'`), a partir
# MAGIC das features de engajamento + perfil. Treino com scikit-learn, rastreamento no MLflow,
# MAGIC registro no Unity Catalog e **scoring** de toda a base.

# COMMAND ----------

# MAGIC %pip install --quiet -U scikit-learn mlflow
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "main", "Catálogo (deve existir)")
dbutils.widgets.text("schema", "netbricks_prime", "Schema")
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()

TBL_FEAT = f"{CATALOG}.{SCHEMA}.features_usuarios"
TBL_SCORES = f"{CATALOG}.{SCHEMA}.scores_churn"
MODELO_UC = f"{CATALOG}.{SCHEMA}.modelo_churn"

# COMMAND ----------

import mlflow
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

mlflow.set_registry_uri("databricks-uc")

pdf = spark.table(TBL_FEAT).toPandas()
pdf["is_churn"] = (pdf["status"] == "Cancelado").astype(int)

NUM = ["total_eventos", "watch_total_min", "watch_medio_min", "pct_assistido_medio",
       "taxa_conclusao", "n_generos", "n_dispositivos", "recencia_dias", "dias_casa"]
CAT = ["plano", "uf", "faixa_etaria", "dispositivo_principal"]  # plano é feature legítima p/ churn

pdf[NUM] = pdf[NUM].astype("float64")  # evita Decimal (não serializável no MLflow)

X = pdf[NUM + CAT]
y = pdf["is_churn"]
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
print(f"Treino: {len(X_tr):,} | Teste: {len(X_te):,} | Taxa de churn: {y.mean():.1%}")

# COMMAND ----------

pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CAT)],
                        remainder="passthrough")
pipe = Pipeline([("pre", pre),
                 ("clf", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=42))])

mlflow.sklearn.autolog(log_models=False)
with mlflow.start_run(run_name="churn_histgb") as run:
    pipe.fit(X_tr, y_tr)
    proba_te = pipe.predict_proba(X_te)[:, 1]
    auc = roc_auc_score(y_te, proba_te)
    mlflow.log_metric("test_auc", auc)
    print(f"AUC (teste): {auc:.3f}")
    print(classification_report(y_te, (proba_te >= 0.5).astype(int)))

    signature = mlflow.models.infer_signature(X_tr, pipe.predict_proba(X_tr)[:, 1])
    mlflow.sklearn.log_model(pipe, "model", signature=signature,
                             input_example=X_tr.head(3),
                             serialization_format="cloudpickle",
                             registered_model_name=MODELO_UC)
print(f"✅ Modelo registrado em {MODELO_UC} | AUC={auc:.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Scoring de toda a base

# COMMAND ----------

pdf["prob_churn"] = pipe.predict_proba(X)[:, 1]
pdf["faixa_risco"] = pd.cut(pdf["prob_churn"], bins=[-0.01, 0.3, 0.6, 1.01],
                            labels=["Baixo", "Médio", "Alto"])
scores = pdf[["user_id", "plano", "status", "prob_churn", "faixa_risco"]].copy()
scores["prob_churn"] = scores["prob_churn"].round(4)
scores["faixa_risco"] = scores["faixa_risco"].astype(str)

(spark.createDataFrame(scores).write.format("delta").mode("overwrite")
   .option("overwriteSchema", "true").saveAsTable(TBL_SCORES))
print(f"✅ Scores gravados em {TBL_SCORES}")
display(spark.sql(f"""
  SELECT faixa_risco, COUNT(*) usuarios, ROUND(AVG(prob_churn),3) prob_media
  FROM {TBL_SCORES} GROUP BY faixa_risco ORDER BY prob_media DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Top clientes ATIVOS com maior risco de churn (alvos de retenção)

# COMMAND ----------

display(spark.sql(f"""
  SELECT user_id, plano, prob_churn FROM {TBL_SCORES}
  WHERE status = 'Ativo' ORDER BY prob_churn DESC LIMIT 15
"""))
