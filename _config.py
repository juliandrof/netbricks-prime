# Databricks notebook source
# MAGIC %md
# MAGIC # ⚙️ _config · Configuração central do lab Netbricks Prime
# MAGIC **Edite só aqui** o catálogo e o schema. Todos os notebooks fazem `%run ./_config`
# MAGIC no início e reaproveitam `CATALOG`, `SCHEMA` e `VS_ENDPOINT` — não precisa repetir em cada um.
# MAGIC
# MAGIC > Em notebooks que instalam libs (`%pip` + `%restart_python`), o `%run ./_config`
# MAGIC > vem **depois** do restart (senão o restart apaga as variáveis).

# COMMAND ----------

# ╔══════════════════════ EDITE AQUI ══════════════════════╗
CATALOG = "netbricks_prime"      # catálogo (deve existir previamente)
SCHEMA  = "suas_iniciais_aqui"   # use suas iniciais p/ não colidir com outros labs
# ╚═════════════════════════════════════════════════════════╝

# COMMAND ----------

# Derivados compartilhados (não precisa editar)
VS_ENDPOINT = f"netbricks_vs_{SCHEMA}"  # endpoint de Vector Search, por schema (evita colisão)

print(f"✅ config carregada → {CATALOG}.{SCHEMA} | VS endpoint: {VS_ENDPOINT}")
