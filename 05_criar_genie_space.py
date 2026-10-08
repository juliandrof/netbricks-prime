# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Criar o Genie Space (ferramenta de dados do agente)
# MAGIC
# MAGIC A ferramenta `consultar_dados` do agente (notebooks 06/07) responde perguntas sobre os
# MAGIC **números da plataforma** chamando um **Genie Space via MCP gerenciado** do Databricks.
# MAGIC Este notebook prepara os dados e traz o **passo a passo** para criar esse Genie Space na UI.
# MAGIC
# MAGIC > O Genie Space é criado **pela interface** (não há criação confiável por API). Este notebook
# MAGIC > (1) adiciona as **chaves PK/FK** que ajudam o Genie a inferir os *joins* e (2) te dá as
# MAGIC > tabelas, instruções e perguntas de exemplo prontas para colar.

# COMMAND ----------

# MAGIC %run ./_config

# COMMAND ----------

FQ = f"{CATALOG}.{SCHEMA}"
print("Schema do lab:", FQ)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1) Chaves PK/FK (ajudam o Genie a entender os relacionamentos)
# MAGIC No Unity Catalog essas constraints são **informativas** (`NOT ENFORCED`/`RELY`): não validam
# MAGIC dados, mas o Genie as usa como dica de *join*. A célula é idempotente (ignora se já existem).

# COMMAND ----------

constraints = [
    # PK em usuarios (catalogo já recebe PK no notebook 00)
    f"ALTER TABLE {FQ}.usuarios ALTER COLUMN user_id SET NOT NULL",
    f"ALTER TABLE {FQ}.usuarios ADD CONSTRAINT pk_usuarios PRIMARY KEY (user_id)",
    # FKs dos eventos -> usuarios / catalogo
    f"ALTER TABLE {FQ}.eventos_visualizacao ADD CONSTRAINT fk_evt_user "
    f"FOREIGN KEY (user_id) REFERENCES {FQ}.usuarios(user_id)",
    f"ALTER TABLE {FQ}.eventos_visualizacao ADD CONSTRAINT fk_evt_content "
    f"FOREIGN KEY (content_id) REFERENCES {FQ}.catalogo(content_id)",
    # FKs das tabelas analíticas -> usuarios
    f"ALTER TABLE {FQ}.features_usuarios ALTER COLUMN user_id SET NOT NULL",
    f"ALTER TABLE {FQ}.features_usuarios ADD CONSTRAINT fk_feat_user "
    f"FOREIGN KEY (user_id) REFERENCES {FQ}.usuarios(user_id)",
    f"ALTER TABLE {FQ}.scores_churn ADD CONSTRAINT fk_churn_user "
    f"FOREIGN KEY (user_id) REFERENCES {FQ}.usuarios(user_id)",
    f"ALTER TABLE {FQ}.scores_upgrade ADD CONSTRAINT fk_upgrade_user "
    f"FOREIGN KEY (user_id) REFERENCES {FQ}.usuarios(user_id)",
]
for sql in constraints:
    try:
        spark.sql(sql)
        print("✓", sql.split("ADD CONSTRAINT")[-1].split("REFERENCES")[0].strip()[:60] or "NOT NULL")
    except Exception as e:
        msg = str(e)
        if "already" in msg.lower() or "exists" in msg.lower() or "ALREADY_EXISTS" in msg:
            print("• já existe:", sql.split("CONSTRAINT")[-1].split("FOREIGN")[0].strip()[:50])
        else:
            print("⚠️", sql[:70], "->", msg[:120])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2) Tabelas (data sets) para adicionar ao Genie Space
# MAGIC Adicione estas tabelas do schema do lab:
# MAGIC
# MAGIC | Tabela | Papel | Grão / chave |
# MAGIC |--------|-------|--------------|
# MAGIC | `usuarios` | perfil do assinante | 1 linha por `user_id` (PK) |
# MAGIC | `catalogo` | catálogo de títulos | 1 linha por `content_id` (PK) |
# MAGIC | `eventos_visualizacao` | eventos de play/complete | 1 linha por `event_id` |
# MAGIC | `features_usuarios` | engajamento consolidado por usuário | 1 linha por `user_id` |
# MAGIC | `scores_churn` | probabilidade de churn (ML) | 1 linha por `user_id` |
# MAGIC | `scores_upgrade` | propensão de upgrade (ML, só Free) | 1 linha por `user_id` |
# MAGIC
# MAGIC > `central_ajuda_kb` **não** entra no Genie (é base de texto para o Vector Search / RAG).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3) Relacionamentos (joins) — cole nas *Instructions* do Genie
# MAGIC
# MAGIC ```
# MAGIC -- eventos de um usuário
# MAGIC eventos_visualizacao.user_id   = usuarios.user_id
# MAGIC -- título assistido em cada evento
# MAGIC eventos_visualizacao.content_id = catalogo.content_id
# MAGIC -- engajamento consolidado do usuário
# MAGIC features_usuarios.user_id      = usuarios.user_id
# MAGIC -- score de churn do usuário
# MAGIC scores_churn.user_id           = usuarios.user_id
# MAGIC -- score de propensão de upgrade (apenas usuários Free)
# MAGIC scores_upgrade.user_id         = usuarios.user_id
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4) Texto de *General Instructions* (cole no Genie, em PT-BR)
# MAGIC
# MAGIC ```
# MAGIC Este Space responde perguntas sobre a Netbricks Prime, uma plataforma de streaming.
# MAGIC Responda sempre em português do Brasil.
# MAGIC
# MAGIC Definições de negócio:
# MAGIC - usuarios.status = 'Cancelado' significa CHURN (cancelou); 'Ativo' = assinante atual.
# MAGIC - usuarios.plano assume: 'Free', 'Standard', 'Premium'. "Pagantes" = Standard ou Premium.
# MAGIC - eventos_visualizacao.evento = 'complete' indica que o título foi assistido até o fim;
# MAGIC   demais valores: 'play', 'pause', 'stop'.
# MAGIC - eventos_visualizacao.watch_time_min = minutos assistidos; pct_assistido = % assistido (0-100).
# MAGIC - taxa de conclusão = média de (evento = 'complete').
# MAGIC - scores_churn.prob_churn em [0,1]; faixa_risco em {Baixo, Médio, Alto}.
# MAGIC - scores_upgrade.prob_upgrade em [0,1] (somente usuários Free); faixa_propensao em {Baixa, Média, Alta}.
# MAGIC
# MAGIC Regras de join (use sempre que precisar cruzar tabelas):
# MAGIC - eventos_visualizacao.user_id = usuarios.user_id
# MAGIC - eventos_visualizacao.content_id = catalogo.content_id
# MAGIC - features_usuarios.user_id = usuarios.user_id
# MAGIC - scores_churn.user_id = usuarios.user_id
# MAGIC - scores_upgrade.user_id = usuarios.user_id
# MAGIC
# MAGIC Para "quantos títulos por gênero", agrupe catalogo por genero_principal.
# MAGIC Para "churn por plano", use usuarios agrupado por plano com a definição de churn acima.
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5) Perguntas de exemplo (cole em *Sample Questions*)
# MAGIC
# MAGIC - Quantos títulos temos por gênero?
# MAGIC - Qual a taxa de churn por plano?
# MAGIC - Quantos usuários temos em cada plano?
# MAGIC - Quais os 10 títulos mais assistidos (por minutos)?
# MAGIC - Qual o tempo médio assistido por plano?
# MAGIC - Quantos usuários Free têm alta propensão de upgrade?

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6) Passo a passo na UI
# MAGIC 1. Menu lateral → **Genie** → **New** (ou **Genie space**).
# MAGIC 2. Selecione um **SQL Warehouse**.
# MAGIC 3. Em **Data**, adicione as tabelas da seção 2 (do schema `catalog.schema` deste lab).
# MAGIC 4. Em **Instructions**, cole o texto da seção 4 (e os joins da seção 3, se quiser reforçar).
# MAGIC 5. Em **Sample questions**, cole as perguntas da seção 5.
# MAGIC 6. Dê um título (ex.: "Netbricks Prime — Genie de Dados") e **salve**.
# MAGIC 7. Teste uma pergunta no próprio Space para validar.
# MAGIC 8. Copie o **Space ID** da URL: `/genie/rooms/<SPACE_ID>`.
# MAGIC 9. Cole esse `SPACE_ID` no widget **`genie_space_id`** dos notebooks **06** (deploy) e **07** (teste).
# MAGIC
# MAGIC > Em um hands-on com várias pessoas, um **único Genie Space compartilhado** atende a todos
# MAGIC > (os dados são idênticos entre schemas) — todos usam o mesmo `SPACE_ID`.

# COMMAND ----------

print("Pronto. Crie o Genie Space na UI (seções acima) e cole o Space ID nos notebooks 06 e 07.")
