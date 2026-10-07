# Databricks notebook source
# MAGIC %md
# MAGIC # 🎬 Netbricks Prime — Geração de Dados (streaming)
# MAGIC
# MAGIC Notebook **único** e parametrizado que gera toda a massa de dados do lab Netbricks Prime,
# MAGIC em escala, usando **Spark nativo** (distribuído):
# MAGIC
# MAGIC | Tabela | Volume padrão | Descrição |
# MAGIC |--------|--------------:|-----------|
# MAGIC | `catalogo` | **10.000** | Títulos com **sinopse rica** (PK + CDF) — base p/ AI Search de descoberta |
# MAGIC | `usuarios` | **120.000** | Assinantes (plano, status/churn, país, dispositivo) |
# MAGIC | `eventos_visualizacao` | **1.000.000** | Play/pause/complete por usuário e título |
# MAGIC | `central_ajuda_kb` | ~12 | Central de ajuda em chunks (PK + CDF) — base p/ AI Search de suporte |
# MAGIC
# MAGIC **Parâmetros:** catálogo e schema (o **schema é criado**; o **catálogo NÃO**), além dos volumes.
# MAGIC
# MAGIC > ⚠️ Dados 100% fictícios, gerados aleatoriamente.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Parâmetros

# COMMAND ----------

dbutils.widgets.text("catalog", "jsfws_catalog", "Catálogo (deve existir)")
dbutils.widgets.text("schema", "netbricks_prime", "Schema (será criado)")
dbutils.widgets.text("n_usuarios", "120000", "Qtd. usuários")
dbutils.widgets.text("n_titulos", "10000", "Qtd. títulos")
dbutils.widgets.text("n_eventos", "1000000", "Qtd. eventos de visualização")

CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip()
N_USERS = int(dbutils.widgets.get("n_usuarios"))
N_TITLES = int(dbutils.widgets.get("n_titulos"))
N_EVENTS = int(dbutils.widgets.get("n_eventos"))

TBL_CAT = f"{CATALOG}.{SCHEMA}.catalogo"
TBL_USR = f"{CATALOG}.{SCHEMA}.usuarios"
TBL_EVT = f"{CATALOG}.{SCHEMA}.eventos_visualizacao"
TBL_KB = f"{CATALOG}.{SCHEMA}.central_ajuda_kb"

print(f"Catálogo/Schema: {CATALOG}.{SCHEMA}")
print(f"Usuários: {N_USERS:,} | Títulos: {N_TITLES:,} | Eventos: {N_EVENTS:,}")

# COMMAND ----------

# Cria SOMENTE o schema (o catálogo deve existir previamente)
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
print(f"✅ Schema pronto: {CATALOG}.{SCHEMA}")

# COMMAND ----------

from pyspark.sql import functions as F

# Helper: escolhe deterministicamente um item de uma lista Python, por linha.
# Usa hash(chave, salt) para variar entre colunas de forma reprodutível.
def pick(bank, salt, key=F.col("n")):
    arr = F.array(*[F.lit(x) for x in bank])
    idx = F.pmod(F.abs(F.hash(key, F.lit(salt))), F.lit(len(bank)))
    return F.element_at(arr, (idx + F.lit(1)).cast("int"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1) Catálogo (10k títulos com sinopse rica)

# COMMAND ----------

TITULO_PREFIXO = ["O Último", "A Última", "Códigos de", "O Império de", "Sombras de",
    "Crônicas de", "Além de", "O Segredo de", "Noites de", "A Ascensão de", "Ecos de",
    "O Legado de", "Fúria de", "O Reino de", "Herança de", "O Preço de", "A Lenda de",
    "Caçadores de", "O Despertar de", "Vozes de", "Fronteiras de", "O Silêncio de",
    "Guardiões de", "A Queda de", "Renascer de", "O Último Trem para", "Prisioneiros de"]
TITULO_NUCLEO = ["Aurora", "Ferro", "Cristal", "Neon", "Silêncio", "Fogo", "Vidro",
    "Marte", "Éden", "Titã", "Prata", "Abismo", "Verão", "Inverno", "Tempestade",
    "Cinzas", "Ouro", "Zero", "Meia-Noite", "Esperança", "Vingança", "Areia", "Névoa",
    "Aço", "Sombra", "Luz", "Trovão", "Oceano", "Deserto", "Império", "Babel", "Órion"]
TITULO_SUFIXO = ["", "", "", ": Origens", ": O Retorno", ": Renascimento", " II",
    ": Capítulo Final", ": A Nova Era", " - Parte 1"]

GENEROS = ["Ação", "Comédia", "Drama", "Ficção Científica", "Terror", "Romance",
    "Suspense", "Documentário", "Animação", "Fantasia", "Crime", "Aventura",
    "Mistério", "Guerra", "Faroeste", "Musical", "Biografia", "Histórico"]
TIPOS = ["Filme", "Filme", "Filme", "Série", "Série"]
CLASSIF = ["Livre", "10", "12", "14", "16", "18"]
IDIOMAS = ["Português", "Inglês", "Espanhol", "Coreano", "Japonês", "Francês", "Alemão"]
PAISES = ["Brasil", "EUA", "Reino Unido", "Coreia do Sul", "Japão", "França",
    "Espanha", "Alemanha", "Canadá", "Argentina"]
NOMES_ELENCO = ["Ana Prado", "Léo Martins", "Marina Dias", "Rafael Souza", "Clara Nunes",
    "Bruno Rocha", "Helena Costa", "Diego Lima", "Sofia Alves", "Igor Mendes",
    "Júlia Ramos", "Caio Ferreira", "Alice Moraes", "Théo Barros", "Lara Pinto"]

# Blocos de sinopse (cláusulas completas p/ concatenar de forma legível)
ABERTURA = ["Em um futuro dominado pela tecnologia,", "Numa metrópole que nunca dorme,",
    "No coração de uma floresta isolada,", "Durante uma guerra que parecia interminável,",
    "Em uma pacata cidade litorânea,", "Num reino esquecido pelo tempo,",
    "Após um colapso global,", "Nos bastidores de um grande império,",
    "Em uma estação espacial à deriva,", "Numa vila cercada por montanhas,",
    "Sob o brilho das luzes de uma capital,", "Em um vilarejo assombrado por lendas,"]
PROTAGONISTA = ["uma cientista brilhante descobre algo que não deveria existir.",
    "um detetive atormentado aceita um último caso.",
    "dois estranhos veem seus destinos se cruzarem.",
    "uma jovem comum desperta um poder adormecido.",
    "um ex-soldado busca redenção pelo passado.",
    "uma família tenta recomeçar do zero.",
    "um grupo de amigos enfrenta o impensável.",
    "uma jornalista persegue uma verdade perigosa.",
    "um artista fracassado ganha uma segunda chance.",
    "uma líder relutante assume um fardo impossível."]
DESENVOLVIMENTO = ["À medida que os segredos vêm à tona, nada é o que parece.",
    "Cada escolha os aproxima de uma verdade perigosa.",
    "A linha entre aliado e inimigo se torna tênue.",
    "O tempo se esgota enquanto o mundo observa.",
    "Laços são testados e ninguém sai ileso.",
    "Uma conspiração maior do que se imagina começa a ruir.",
    "Entre perdas e descobertas, tudo muda para sempre."]
FECHO = ["Uma história eletrizante sobre coragem e sacrifício.",
    "Um drama intenso sobre amor, perda e recomeço.",
    "Uma aventura que desafia os limites da imaginação.",
    "Um suspense de tirar o fôlego até o último minuto.",
    "Uma jornada emocionante sobre identidade e pertencimento.",
    "Uma trama cheia de reviravoltas surpreendentes."]

cat = spark.range(1, N_TITLES + 1).withColumnRenamed("id", "n")

genero_p = pick(GENEROS, "gen")
cat = (cat
    .withColumn("content_id", F.concat(F.lit("NBP"), F.lpad(F.col("n").cast("string"), 6, "0")))
    .withColumn("titulo", F.trim(F.concat_ws(" ", pick(TITULO_PREFIXO, "pfx"),
                                             F.concat(pick(TITULO_NUCLEO, "nuc"), pick(TITULO_SUFIXO, "sfx")))))
    .withColumn("tipo", pick(TIPOS, "tipo"))
    .withColumn("genero_principal", pick(GENEROS, "gen"))
    .withColumn("genero_secundario", pick(GENEROS, "gen2"))
    .withColumn("ano", (F.lit(1990) + F.pmod(F.abs(F.hash("n", F.lit("ano"))), F.lit(36))).cast("int"))
    .withColumn("classificacao", pick(CLASSIF, "cls"))
    .withColumn("idioma", pick(IDIOMAS, "idi"))
    .withColumn("pais_origem", pick(PAISES, "pais"))
    .withColumn("diretor", pick(NOMES_ELENCO, "dir"))
    .withColumn("elenco", F.concat_ws(", ", pick(NOMES_ELENCO, "e1"),
                                      pick(NOMES_ELENCO, "e2"), pick(NOMES_ELENCO, "e3")))
    .withColumn("nota_media", F.round(F.lit(5.0) + F.rand(11) * 5.0, 1))
    .withColumn("temporadas", F.when(F.col("tipo") == "Série",
                (F.lit(1) + F.pmod(F.abs(F.hash("n", F.lit("temp"))), F.lit(8))).cast("int")).otherwise(F.lit(None).cast("int")))
    .withColumn("duracao_min", F.when(F.col("tipo") == "Filme",
                (F.lit(80) + F.pmod(F.abs(F.hash("n", F.lit("dur"))), F.lit(90))).cast("int")).otherwise(F.lit(None).cast("int")))
    .withColumn("sinopse", F.concat_ws(" ",
                pick(ABERTURA, "ab"), pick(PROTAGONISTA, "pr"),
                pick(DESENVOLVIMENTO, "dv"), pick(FECHO, "fe"),
                F.concat(F.lit("Um título de"), F.lit(" "), pick(GENEROS, "gen"), F.lit("."))))
    .drop("n")
)

(cat.write.format("delta").mode("overwrite")
   .option("delta.enableChangeDataFeed", "true")
   .option("overwriteSchema", "true").saveAsTable(TBL_CAT))

# PK para o índice de Vector Search / AI Search
spark.sql(f"ALTER TABLE {TBL_CAT} ALTER COLUMN content_id SET NOT NULL")
spark.sql(f"ALTER TABLE {TBL_CAT} ADD CONSTRAINT pk_catalogo PRIMARY KEY (content_id)")

print(f"✅ {spark.table(TBL_CAT).count():,} títulos em {TBL_CAT}")
display(spark.sql(f"SELECT content_id, titulo, tipo, genero_principal, ano, nota_media, sinopse FROM {TBL_CAT} LIMIT 8"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2) Usuários (120k assinantes)

# COMMAND ----------

PRIMEIRO = ["Ana", "Carlos", "Mariana", "Rafael", "Juliana", "Bruno", "Patrícia",
    "Fernando", "Camila", "Thiago", "Larissa", "Gustavo", "Renata", "Marcelo", "Aline",
    "Diego", "Vanessa", "Rodrigo", "Débora", "Leonardo", "Priscila", "André", "Fernanda",
    "Vinícius", "Tatiane", "Eduardo", "Sabrina", "Felipe", "Natália", "Márcio",
    "Beatriz", "Henrique", "Isabela", "Lucas", "Gabriela", "Pedro", "Amanda", "Guilherme"]
ULTIMO = ["Souza", "Lima", "Costa", "Santos", "Rocha", "Dias", "Martins", "Melo",
    "Nunes", "Pinto", "Freitas", "Lopes", "Ramos", "Monteiro", "Cruz", "Pires",
    "Azevedo", "Cunha", "Moraes", "Reis", "Campos", "Barros", "Nogueira", "Franco"]
DISPOSITIVOS = ["Smart TV", "Celular", "Notebook", "Tablet", "Console"]
UF = ["SP", "RJ", "MG", "PR", "SC", "RS", "BA", "PE", "DF", "CE", "GO", "PA"]
FAIXA = ["18-24", "25-34", "35-44", "45-54", "55+"]

# Engajamento latente por usuário (0..1) — NÃO é gravado na tabela.
# Ele governa: (a) volume de eventos, (b) probabilidade de plano pago, (c) churn.
# Assim as features derivadas dos eventos passam a ter SINAL para os modelos de ML.
eng = (F.pmod(F.abs(F.hash("n", F.lit("eng"))), F.lit(1000)) / F.lit(1000.0))

pnome = pick(PRIMEIRO, "pn")
unome = pick(ULTIMO, "un")

usr = (spark.range(1, N_USERS + 1).withColumnRenamed("id", "n")
    .withColumn("eng", eng)
    .withColumn("user_id", F.concat(F.lit("U"), F.lpad(F.col("n").cast("string"), 7, "0")))
    .withColumn("nome", F.concat_ws(" ", pnome, unome))
    .withColumn("email", F.concat(F.lower(pnome), F.lit("."), F.lower(unome),
                                  F.col("n").cast("string"), F.lit("@netbricksprime.com")))
    .withColumn("uf", pick(UF, "uf"))
    .withColumn("faixa_etaria", pick(FAIXA, "faixa"))
    .withColumn("dispositivo_principal", pick(DISPOSITIVOS, "disp"))
    .withColumn("data_assinatura", F.expr("date_sub(current_date(), cast(rand(7)*1825 as int))"))
    # PLANO: mais engajado -> mais provável ser pago (Standard/Premium)
    .withColumn("_sp", F.lit(0.65) * F.col("eng") + F.lit(0.35) * F.rand(21))
    .withColumn("plano", F.when(F.col("_sp") < 0.42, "Free")
                          .when(F.col("_sp") < 0.75, "Standard").otherwise("Premium"))
    # CHURN: menos engajado e plano Free -> mais chance de cancelar
    .withColumn("_cp", F.lit(0.32) - F.lit(0.26) * F.col("eng")
                        + F.when(F.col("plano") == "Free", F.lit(0.15)).otherwise(F.lit(0.0)))
    .withColumn("status", F.when(F.rand(22) < F.col("_cp"), "Cancelado").otherwise("Ativo"))
    # nº de eventos por usuário ~ proporcional ao engajamento (usado na seção 3).
    # Média por usuário calibrada para ~N_EVENTS no total.
    .withColumn("n_ev", F.greatest(F.lit(0),
                F.round(F.lit(float(N_EVENTS) / N_USERS)
                        * (F.lit(0.25) + F.lit(1.5) * F.col("eng"))
                        * (F.lit(0.6) + F.lit(0.8) * F.rand(23))).cast("int")))
)

# Grava usuarios SEM as colunas latentes/auxiliares
cols_usr = ["user_id", "nome", "email", "plano", "uf", "faixa_etaria",
            "dispositivo_principal", "data_assinatura", "status"]
(usr.select(*cols_usr).write.format("delta").mode("overwrite")
   .option("overwriteSchema", "true").saveAsTable(TBL_USR))

print(f"✅ {spark.table(TBL_USR).count():,} usuários em {TBL_USR}")
display(spark.sql(f"""
  SELECT plano, COUNT(*) AS total,
         ROUND(100.0*SUM(CASE WHEN status='Cancelado' THEN 1 ELSE 0 END)/COUNT(*),1) AS churn_pct
  FROM {TBL_USR} GROUP BY plano ORDER BY total DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3) Eventos de Visualização (1M)

# COMMAND ----------

OUTROS_EVENTOS = ["play", "play", "pause", "stop"]
DISPOSITIVOS_EVT = ["Smart TV", "Celular", "Notebook", "Tablet", "Console"]

# Cada usuário gera n_ev eventos (explode). Assim o VOLUME por usuário e a
# COMPLETUDE/watch time correlacionam com o engajamento latente -> sinal p/ ML.
kv = F.concat_ws("_", F.col("n"), F.col("k"))  # chave por-evento (usuário + índice)

evt = (usr.filter(F.col("n_ev") >= 1)
    .select("n", "eng", "n_ev")
    .withColumn("k", F.explode(F.expr("sequence(1, n_ev)")))
    .withColumn("event_id", F.concat(F.lit("EVT"), F.col("n").cast("string"),
                                     F.lit("-"), F.col("k").cast("string")))
    .withColumn("user_id", F.concat(F.lit("U"), F.lpad(F.col("n").cast("string"), 7, "0")))
    .withColumn("content_id", F.concat(F.lit("NBP"),
                F.lpad(((F.pmod(F.abs(F.hash("n", "k", F.lit("c"))), F.lit(N_TITLES))) + 1).cast("string"), 6, "0")))
    .withColumn("data_hora", F.expr("current_timestamp() - make_dt_interval(cast(rand(31)*365 as int), cast(rand(32)*24 as int), cast(rand(33)*60 as int), 0)"))
    # engajados concluem mais; os demais dão play/pause/stop
    .withColumn("evento", F.when(F.rand(34) < (F.lit(0.15) + F.lit(0.55) * F.col("eng")), F.lit("complete"))
                           .otherwise(pick(OUTROS_EVENTOS, "evt", key=kv)))
    .withColumn("dispositivo", pick(DISPOSITIVOS_EVT, "dispe", key=kv))
    # % assistido e watch time crescem com o engajamento
    .withColumn("pct_assistido", F.round(F.least(F.lit(100.0),
                (F.lit(20) + F.lit(80) * F.col("eng")) * (F.lit(0.5) + F.rand(35))), 1))
    .withColumn("watch_time_min", F.greatest(F.lit(1),
                ((F.lit(5) + F.lit(110) * F.col("eng")) * (F.lit(0.5) + F.rand(36))).cast("int")))
    .select("event_id", "user_id", "content_id", "data_hora", "evento",
            "dispositivo", "pct_assistido", "watch_time_min")
)

(evt.write.format("delta").mode("overwrite")
   .option("overwriteSchema", "true")
   .partitionBy("evento").saveAsTable(TBL_EVT))

print(f"✅ {spark.table(TBL_EVT).count():,} eventos em {TBL_EVT}")
display(spark.sql(f"""
  SELECT evento, COUNT(*) AS total, ROUND(AVG(watch_time_min),1) AS media_min
  FROM {TBL_EVT} GROUP BY evento ORDER BY total DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Top 10 títulos mais assistidos (join de 1M eventos com catálogo)

# COMMAND ----------

display(spark.sql(f"""
  SELECT c.titulo, c.genero_principal, COUNT(*) AS visualizacoes
  FROM {TBL_EVT} e JOIN {TBL_CAT} c USING (content_id)
  GROUP BY c.titulo, c.genero_principal
  ORDER BY visualizacoes DESC LIMIT 10
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4) Central de Ajuda — Knowledge Base (chunks)
# MAGIC PK (`doc_id`) + Change Data Feed → pronto p/ **AI Search index manual** sobre `conteudo`.

# COMMAND ----------

from pyspark.sql import Row

AJUDA = [
    ("Planos e preços", "A Netbricks Prime oferece três planos: Free (gratuito, com anúncios, "
     "qualidade SD e 1 tela); Standard (R$ 29,90/mês, Full HD, 2 telas simultâneas e "
     "downloads); Premium (R$ 44,90/mês, 4K HDR, 4 telas simultâneas, downloads e áudio "
     "espacial). A troca de plano vale a partir do próximo ciclo de cobrança."),
    ("Formas de pagamento", "Aceitamos cartão de crédito, PIX e boleto. A cobrança do PIX e "
     "boleto é mensal e antecipada; no cartão, é recorrente na data de assinatura. Em caso "
     "de falha de pagamento, a conta entra em suspensão após 5 dias."),
    ("Como cancelar", "Você pode cancelar a qualquer momento em Conta > Assinatura > Cancelar. "
     "O acesso continua até o fim do período já pago, sem multa. Assinaturas contratadas via "
     "lojas de aplicativos devem ser canceladas na própria loja."),
    ("Reembolso", "Para planos pagos via cartão ou PIX, oferecemos reembolso integral se "
     "solicitado em até 7 dias após a contratação (direito de arrependimento, CDC). Após esse "
     "prazo, não há reembolso proporcional do período em uso."),
    ("Telas simultâneas", "Free permite 1 tela; Standard, 2 telas; Premium, 4 telas ao mesmo "
     "tempo. Cada conta pode ter até 5 perfis independentes, com recomendações separadas."),
    ("Qualidade de vídeo (SD, HD, 4K)", "A qualidade máxima depende do plano: Free em SD (480p), "
     "Standard em Full HD (1080p) e Premium em 4K com HDR. A qualidade real também depende da "
     "velocidade da internet e do dispositivo compatível."),
    ("Downloads offline", "Disponível nos planos Standard e Premium, no app para celular e "
     "tablet. O plano Free NÃO permite downloads. Os títulos baixados expiram conforme a "
     "licença de cada conteúdo."),
    ("Controle dos pais", "É possível criar um perfil infantil com catálogo filtrado por "
     "classificação etária e proteger perfis adultos com PIN de 4 dígitos em Conta > Controle "
     "dos Pais."),
    ("Dispositivos suportados", "Smart TVs (principais fabricantes), celulares e tablets "
     "(Android/iOS), navegadores web, consoles e streaming sticks. Um mesmo perfil pode ser "
     "usado em vários dispositivos, respeitando o limite de telas simultâneas do plano."),
    ("Problemas de reprodução e buffering", "Se o vídeo travar: verifique a conexão (mínimo "
     "recomendado de 5 Mbps para HD e 25 Mbps para 4K), reinicie o app e o dispositivo, e "
     "confirme se o app está atualizado. Buffering frequente costuma indicar rede instável."),
    ("Perfis e recomendações", "Cada perfil recebe recomendações personalizadas com base no "
     "histórico de visualização. É possível limpar o histórico em Conta > Perfil > Histórico "
     "para reiniciar as sugestões."),
    ("Alterar plano", "A mudança para um plano superior é imediata, com cobrança proporcional; "
     "a mudança para um plano inferior passa a valer no próximo ciclo. Não há taxa para trocar "
     "de plano."),
]

kb_rows = []
for i, (titulo, conteudo) in enumerate(AJUDA, start=1):
    kb_rows.append(Row(doc_id=f"AJU-{i:03d}", ordem=i, titulo=titulo, conteudo=conteudo,
                       fonte="Central de Ajuda Netbricks Prime", data_atualizacao="2026-09-01"))

df_kb = spark.createDataFrame(kb_rows)
(df_kb.write.format("delta").mode("overwrite")
   .option("delta.enableChangeDataFeed", "true")
   .option("overwriteSchema", "true").saveAsTable(TBL_KB))
spark.sql(f"ALTER TABLE {TBL_KB} ALTER COLUMN doc_id SET NOT NULL")
spark.sql(f"ALTER TABLE {TBL_KB} ADD CONSTRAINT pk_ajuda_kb PRIMARY KEY (doc_id)")

print(f"✅ {df_kb.count()} artigos em {TBL_KB} (PK=doc_id, CDF habilitado)")
display(spark.sql(f"SELECT doc_id, titulo, conteudo FROM {TBL_KB} ORDER BY ordem"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## ✅ Pronto
# MAGIC - `catalogo` (10k), `usuarios` (120k), `eventos_visualizacao` (1M), `central_ajuda_kb`.
# MAGIC
# MAGIC ### Próximo passo (manual): criar o AI Search / Vector Search index
# MAGIC **Para descoberta/recomendação** → índice sobre `catalogo`:
# MAGIC Primary key = `content_id` · Embedding source = `sinopse` · Modelo = `databricks-gte-large-en`.
# MAGIC
# MAGIC **Para o agente de suporte** → índice sobre `central_ajuda_kb`:
# MAGIC Primary key = `doc_id` · Embedding source = `conteudo` · Modelo = `databricks-gte-large-en`.
