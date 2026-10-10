# F4 — Bundesagentur + EURES com filtro de estágio (Praktikum)

**Data:** 2026-10-02 · **Branch:** `feature/f4-ba-eures` (base `main` `6c5536b` —
já contém a F3 mergeada) · **Status:** implementado; validação offline §4.4
executada (números abaixo)

## O que a F4 adiciona (sem duplicar a ingestão da F3)

A auditoria definiu a fase: as duas maiores fontes de estágio da Europa
estavam "mudas" — a Bundesagentur tem a facet `angebotsart` com bucket
PRAKTIKUM_TRAINEE e o EURES tem body com `keywords` pronto para preencher,
mas nenhum dos fetchers enviava filtro. A F3 (mergeada como PR #95) JÁ
ingere rows BA/EURES das fatias hospedadas (prefilter DE+estágio por
título; 10.920 BA + 1.484 EURES kept no A/B da F3). A F4 **não reescreve a
ingestão** — adiciona o que faltava:

1. **Filtros upstream (fork `rios-vini/ats-scrapers`, PR #293 ABERTO em
   `kalil0321/ats-scrapers`)**: kwargs opt-in nos dois scrapers.
   - `BundesagenturScraper(slug, angebotsart="34")`: a facet v6 usa
     **códigos numéricos** — `34` = PRAKTIKUM_TRAINEE (**14.325 rows ao
     vivo em 02/10**). O LABEL (`angebotsart=Praktikum`) retorna **0
     resultados** (armadilha medida; por isso a constante
     `ANGEBOTSART_PRAKTIKUM_TRAINEE = "34"` documentada). O filtro entra
     como `base_params` da recursão inteira (`_exhaust_query`).
   - `EuresScraper(slug, keywords=["Praktikum"])`: o body `keywords` aceita
     **objetos** `{"keyword": ..., "specificSearchCode": "EVERYWHERE"}` —
     lista de strings devolve `400 invalid-json` (medido). Valores do
     `specificSearchCode` observados no bundle oficial: EVERYWHERE/TITLE/
     DESCRIPTION/EMPLOYER. Medidas ao vivo (DE, "Praktikum"):
     EVERYWHERE 35.486 · TITLE 299 · DESCRIPTION 3.706. **Múltiplas entries
     são ANDadas** (3 keywords → 79 rows) — por isso a F4 usa 1 keyword por
     query. Default `None` = comportamento atual byte-idêntico (zero
     regressão upstream).
2. **Fonte nova `direct_fetch` no pipeline** (`src/internship_finder/direct_fetch.py`):
   amostra diária DIRETA das duas APIs públicas com o filtro nativo de cada
   fonte — a fatia hospeda o mundo inteiro mas só atualiza ~05h UTC e o
   prefilter F3 é por TÍTULO; o fetch direto traz (a) rows mais frescas
   (sort `veroeffdatum`), (b) alcance maior no EURES (35.486 rows por
   keyword vs 4.649 por título na fatia), (c) description garantida — BA
   via detail v4 (probe: 3/3 refnrs reais da fatia hidrataram com
   2.248–6.740 chars), EURES de graça na resposta da busca (1,1–1,7k
   chars por row, medido).
   - Identidade: `source = "direct:<ats>"` (escopo P1.1 distinto); a
     MESMA vaga no dataset e no direct tem a MESMA URL → o `deduplicate()`
     existente colapsa pela chave URL (comportamento validado no §4.4).
   - Rate limits conservadores (spec §3.3): 1 fetch/dia por fonte (o refresh
     roda 1×/día), cap **200 jobs por fonte por run** (ajustável
     `--direct-fetch-max-jobs`), páginas SEQUENCIAIS com size constante
     (offset estável — variar o size entre páginas recuaria o offset e
     re-leria rows), dedup interno por ats_id, timeout 20s/request, backoff
     em 429/5xx com Retry-After, hard caps de páginas (BA 20, EURES 8).
   - Degradação graciosa: falha de UMA fonte = `status: partial`; AMBAS =
     `failed`; registro JSONL `type: direct_fetch` gravado em qualquer
     caso; o run segue e o exit code NÃO muda (mesma regra do estágio
     dataset da F3).
3. **Hidratação estendida** (`hydration.py`): mapa single-source —
   `sf_dataset:bundesagentur` e `sf_dataset:eures` (e os `direct:*`) agora
   resolvem scraper para `get_description` (o `company_slug` é ignorado
   pelos scrapers single-tenant; stub fixo, nunca slug inventado). Isso
   destrava a maior lacuna da F3: os **10.920 jobs BA do dataset com 0%
   description** deixam de ser `unsupported_no_detail` e passam a hidratar
   pelo endpoint v4 (probe 3/3). Regra `_prefer` preservada: quem tem
   description vence o twin.
4. **CLI + refresh**: `--direct-fetch` (BooleanOptionalAction; default ON
   no `--registry`, OFF no `--companies` explícito; `--no-direct-fetch`
   reverte) + `--direct-fetch-max-jobs N`. `refresh_daily.collection_command()`
   passa `--direct-fetch` explicitamente (contrato visível; cron intocado —
   conferido: o cron chama o refresh sem flags de coleta).


## Validação offline (§4.4) — números medidos (02/10, fatias locais)

Amostras determinísticas (seed 20261002) das fatias hospedadas reais
(`bundesagentur.csv` 1,18 GB · `eures.csv` 3,52 GB — as mesmas que o
estágio dataset baixa), convertidas pelo caminho F3 (`row_to_job`), mais
jobs direct simulados das MESMAS rows (mesma URL, fonte `direct:*`) para
provar o colapso cross-fonte. Funil offline (`hydrate=False`, sem rede):

| Estágio | BA (dataset) | EURES (dataset) | Direct (simulado) | Consolidado |
|---|---|---|---|---|
| Rows in | 5.200 | 3.342 | 120 | 8.662 |
| Jobs criados | 5.200 | 2.449 (893 invalid: NES placeholder sem company) | 120 | 7.769 |
| `internship=True` (pós `is_student_role`) | 1.823 | 1.758 | — | 3.581 |
| Pós-cascata (student+área+DE) | — | — | — | **256** |
| Pós-dedup | 100 | 142 | 0 (todos colapsaram c/ twin dataset) | **242 eligible** |

Top-N consolidado (ranking do perfil): 1º Nanotec 14,5 · 2º Bosch 14,5 ·
3º accompio 13,5 · 4º Liebherr 12,5 · 5º Bosch 12,5 (Werkstudent
Supply-Chain/eBus). Distribuição por fonte no eligible: dataset:eures 142
· dataset:bundesagentur 100.

**Leitura honesta do "0 direct survivors"**: os 120 direct simulados são
rows JÁ PRESENTES na fatia do dia (por construção do teste) — dos 6 que
passam a cascata, todos colapsam com o twin do dataset que já tem
description (regra `_prefer`, primeiro vence). O valor do direct fetch em
produção é OUTRO: (a) frescor — rows publicadas após o corte ~05h UTC do
dataset; (b) alcance EURES — 35.486 rows por keyword vs 4.649 por título;
(c) hidratação BA — description viva via detail v4 (a fatia tem 0%). O
probe REAL do direct fetch (02/10): BA 30/30 jobs com description
(100%, mediana ~1,5k chars), EURES 30/30 com description embutida.

## Invariantes P0 (como cada uma foi garantida)

1. **Sem regressão**: `--no-direct-fetch` desliga o estágio (o pipeline
   sem as fontes novas é idêntico ao main); zero mudança em
   filters/dedup/mirror/ranking/countries; o diff confina-se a
   `direct_fetch.py` (novo), `hydration.py` (mapa + prefixo `direct:`),
   `cli.py` (flags + estágio), `refresh_daily.py` (contrato), `test_refresh.py`
   (contrato travado).
2. **Produção `data/` intocada**: a validação roda sobre cópias em /tmp;
   testes 100% offline.
3. **Cron/exit codes/publish gate**: cron não editado; falha do
   direct_fetch NÃO gera exit 2 (mesma regra F3 do dataset);
   `publication_allowed` intocado.
4. **`raw` é o contrato**: item cru preservado (menos description, padrão
   do adapter); F3 `row_to_job` intocado.
5. **Lifecycle SQLite**: jobs `direct:*` NÃO entram (mesma decisão §7.8 da
   F3: fonte efêmera re-derivada a cada run).
6. **`deduplicate()` zero-change**: colapso cross-fonte pela chave URL
   naturalmente (validado §4.4: 5 remoções por URL no consolidado).

## Limitações (declaradas, sem ação)

- O pacote instalado 0.3.0 (PyPI) NÃO tem os kwargs — o PR upstream #293
  os adiciona; o pipeline NÃO depende dele (o `direct_fetch.py` fala com
  as APIs diretamente via urllib; os kwargs são para o FUTURO release e
  para outros consumidores do pacote). Pós-release: `direct_fetch.py`
  pode migrar para o scraper com `angebotsart`/`keywords` (mesma API,
  mesmo shape) — pendência de baixo risco.
- O cap 200/fonte/dia é uma AMOSTRA do catálogo PRAKTIKUM (14,3k BA /
  35,5k EURES), não o universo — a fatia dataset continua sendo a fonte
  do volume; o direct cobre frescor + hidratação.
- BA detail v4 é 1 request/vaga (cap 200 → ≤200 requests/dia, ~0,75s
  cada — orçamento ~150s, dentro do budget 600s do estágio).
- EURES keyword "Praktikum" em `locationCodes: ["de"]` — rows de outros
  países ficam de fora do direct (a fatia cobre; o filtro de país do
  funil é `--country de`).

## Testes (`scripts/test_f4.py`, 48º do CI; 100% offline)

73 checks, 7 grupos A–G: parsing BA (item v6→Job, internship, location,
description do detail, invalids), parsing EURES (translations, epoch-ms,
HTML clean, locationMap), rate-limit/config (cap 200, size CONSTANTE entre
páginas — bug de overlap pego pelo teste e corrigido, dedup interno, budget
entre fontes), dedup cross-fonte (direct×dataset colapsa por URL; company
divergente não colapsa; tenant preservado), degradação graciosa (BA falha
→ EURES entrega; ambas falham → failed sem exceção; detail falha → vaga
sem description), hidratação (mapa single-source, regressão F3 workday,
unsupported preservado), registro JSONL + wiring CLI (contrato do refresh
travado). Array `ci.yml` editado NO MESMO commit (48º).
