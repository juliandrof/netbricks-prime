# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Vector Search — Índices (catálogo + central de ajuda)
# MAGIC Cria os dois índices Delta Sync que o **agente híbrido** usa:
# MAGIC - `catalogo_index` sobre `catalogo.sinopse` → descoberta/recomendação
# MAGIC - `ajuda_index` sobre `central_ajuda_kb.conteudo` → suporte (RAG)

# COMMAND ----------

# MAGIC %pip install --quiet databricks-vectorsearch
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "main", "Catálogo (deve existir)")
dbutils.widgets.text("schema", "netbricks_prime", "Schema")
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()

VS_ENDPOINT = f"netbricks_vs_{SCHEMA}"  # endpoint por schema (evita colisão entre labs)
EMB = "databricks-gte-large-en"
IDX_CAT = f"{CATALOG}.{SCHEMA}.catalogo_index"
IDX_AJU = f"{CATALOG}.{SCHEMA}.ajuda_index"
SRC_CAT = f"{CATALOG}.{SCHEMA}.catalogo"
SRC_AJU = f"{CATALOG}.{SCHEMA}.central_ajuda_kb"

# COMMAND ----------

from databricks.vector_search.client import VectorSearchClient
vsc = VectorSearchClient(disable_notice=True)

# Cria o endpoint se ainda não existir (nome dinâmico por schema)
endpoints = [e["name"] for e in vsc.list_endpoints().get("endpoints", [])]
if VS_ENDPOINT not in endpoints:
    print(f"Criando endpoint {VS_ENDPOINT} ...")
    vsc.create_endpoint(name=VS_ENDPOINT, endpoint_type="STANDARD")
vsc.wait_for_endpoint(VS_ENDPOINT, verbose=True)

def criar_ou_sync(index_name, source, pk, emb_col):
    existentes = [i["name"] for i in vsc.list_indexes(VS_ENDPOINT).get("vector_indexes", [])]
    if index_name not in existentes:
        print(f"Criando {index_name} ...")
        vsc.create_delta_sync_index(
            endpoint_name=VS_ENDPOINT, index_name=index_name, source_table_name=source,
            pipeline_type="TRIGGERED", primary_key=pk,
            embedding_source_column=emb_col, embedding_model_endpoint_name=EMB)
    else:
        print(f"{index_name} já existe — sincronizando")
        vsc.get_index(VS_ENDPOINT, index_name).sync()

criar_ou_sync(IDX_CAT, SRC_CAT, "content_id", "sinopse")
criar_ou_sync(IDX_AJU, SRC_AJU, "doc_id", "conteudo")

# COMMAND ----------

import time
for idx in (IDX_CAT, IDX_AJU):
    o = vsc.get_index(VS_ENDPOINT, idx)
    for _ in range(60):
        st = o.describe().get("status", {})
        if st.get("ready"):
            print(f"✅ {idx} pronto ({st.get('indexed_row_count')} linhas)"); break
        print(f"… {idx}: {st.get('message','')[:60]}"); time.sleep(20)

# COMMAND ----------

# Teste de busca semântica no catálogo
res = vsc.get_index(VS_ENDPOINT, IDX_CAT).similarity_search(
    query_text="ficção científica espacial com reviravoltas",
    columns=["titulo", "genero_principal", "nota_media"], num_results=5)
for r in res.get("result", {}).get("data_array", []):
    print("•", r[0], "|", r[1], "| nota", r[2])
