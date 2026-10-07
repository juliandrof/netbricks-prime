# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Modelo de Propensão de Upgrade — Netbricks Prime
# MAGIC
# MAGIC Prevê a propensão de um assinante estar em **plano pago** (Standard/Premium) a partir
# MAGIC do comportamento de uso. O modelo é treinado em toda a base (alvo `is_pago`) e depois
# MAGIC **aplicado aos usuários Free** — os de maior probabilidade são os **melhores alvos de
# MAGIC upgrade** (parecem-se, no uso, com quem já é pagante).
# MAGIC
# MAGIC > Nota: `plano` NÃO entra como feature (é a base do alvo). Usamos apenas engajamento
# MAGIC > e perfil.

# COMMAND ----------

# MAGIC %pip install --quiet -U scikit-learn mlflow
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "main", "Catálogo (deve existir)")
dbutils.widgets.text("schema", "netbricks_prime", "Schema")
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()

TBL_FEAT = f"{CATALOG}.{SCHEMA}.features_usuarios"
TBL_SCORES = f"{CATALOG}.{SCHEMA}.scores_upgrade"
MODELO_UC = f"{CATALOG}.{SCHEMA}.modelo_upgrade"

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
pdf["is_pago"] = pdf["plano"].isin(["Standard", "Premium"]).astype(int)

NUM = ["total_eventos", "watch_total_min", "watch_medio_min", "pct_assistido_medio",
       "taxa_conclusao", "n_generos", "n_dispositivos", "recencia_dias", "dias_casa"]
CAT = ["uf", "faixa_etaria", "dispositivo_principal"]  # SEM 'plano' (é a base do alvo)

pdf[NUM] = pdf[NUM].astype("float64")  # evita Decimal (não serializável no MLflow)

X = pdf[NUM + CAT]
y = pdf["is_pago"]
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
print(f"Treino: {len(X_tr):,} | Teste: {len(X_te):,} | Taxa pago: {y.mean():.1%}")

# COMMAND ----------

pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CAT)],
                        remainder="passthrough")
pipe = Pipeline([("pre", pre),
                 ("clf", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=42))])

mlflow.sklearn.autolog(log_models=False)
with mlflow.start_run(run_name="upgrade_histgb"):
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
# MAGIC ### Scoring: propensão de upgrade dos usuários FREE

# COMMAND ----------

pdf["prob_upgrade"] = pipe.predict_proba(X)[:, 1]
free = pdf[pdf["plano"] == "Free"].copy()
free["faixa_propensao"] = pd.cut(free["prob_upgrade"], bins=[-0.01, 0.3, 0.6, 1.01],
                                 labels=["Baixa", "Média", "Alta"])
scores = free[["user_id", "plano", "prob_upgrade", "faixa_propensao"]].copy()
scores["prob_upgrade"] = scores["prob_upgrade"].round(4)
scores["faixa_propensao"] = scores["faixa_propensao"].astype(str)

(spark.createDataFrame(scores).write.format("delta").mode("overwrite")
   .option("overwriteSchema", "true").saveAsTable(TBL_SCORES))
print(f"✅ Scores (usuários Free) gravados em {TBL_SCORES}")
display(spark.sql(f"""
  SELECT faixa_propensao, COUNT(*) usuarios, ROUND(AVG(prob_upgrade),3) prob_media
  FROM {TBL_SCORES} GROUP BY faixa_propensao ORDER BY prob_media DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Top usuários Free com maior propensão de upgrade (alvos de conversão)

# COMMAND ----------

display(spark.sql(f"""
  SELECT user_id, prob_upgrade FROM {TBL_SCORES}
  ORDER BY prob_upgrade DESC LIMIT 15
"""))
