# Camada de Enrichment LLM — Fase 2 (incremental, automática, operacionalmente segura)

**Fase**: enrichment v2 (branch `feature/enrichment-fase2`, base = Fase 1 /
PR #81). A camada continua **isolada por design**: nenhum módulo do pipeline
importa `internship_finder.enrichment`. A LLM é opcional e não-crítica —
enriquece com evidência, NUNCA decide eligibility, score ou ranking.

Novidades da Fase 2 sobre a v1: **delta incremental** (somente o que mudou
vai à LLM), **execução automática após o refresh** (`refresh_daily.py
--enrichment`), **corte do ranking** (`--top-n`, default 30 — só o topo do
dia entra no plano), **limite de carga por run** (`--limit`), **lock de
concorrência** (flock, exit 3), **preservação com pendência** (falha de
conteúdo novo nunca apaga o último sucesso válido) e **health file**
(`enrichment_status.json`).

## Arquitetura e fluxo

```
refresh diário (cron 09:00 UTC)
  → coleta → eligibility → ranking → outputs (Pages/Telegram)   [fluxo existente]
  → refresh_daily.py --enrichment --enrichment-limit 24 --enrichment-top-n 30
      → scripts/enrichment_run.py (subprocesso standalone)
          → planejamento (corte do ranking: as --top-n mais bem ranqueadas,
            ordem (score desc, id desc); default 30)
              sem record → new | falha → retry | sucesso → seen
              vagas fora do corte NUNCA entram no backlog (records
              preservados; cobertura ao reentrar no corte)
          → fetch sweep do corte (fetch + normalize_html + SHA-256, 1 tentativa,
            pausa --sleep-fetch entre fetches)
          → delta: seen + (job_id, final_url, content_hash) idêntico ao record
            e SEM pendência → cache_hit (zero LLM, zero escrita)
          → pool p/ LLM: retry → new → changed/changed_source (score desc em
            cada bloco), cap --limit sobre CHAMADAS LLM; excedente =
            pending_backlog (próximo run continua)
          → GLM-5.3-Flash sequencial (3 tentativas, backoff 30/60s,
            isolamento por vaga)
          → EnrichmentStore.upsert (JSONL atômico; preservação/pendência)
          → resumo no stdout + data/enrichment/enrichment_status.json
```

Módulos (`src/internship_finder/enrichment/`):

- **`schema.py`** — inalterado da v1 (EnrichmentRecord, guardas, fields_from_llm).
- **`fetch.py`** — inalterado (fetch_page 1 tentativa, classify_page 8 estados).
- **`html_norm.py`** — inalterado.
- **`llm.py`** — inalterado (GLM-5.3-Flash fixo, retry 3×, key só de env).
- **`runner.py`** — reescrito na fase 2: `plan_jobs` (buckets), `classify_seen`
  (delta pós-fetch), `run_incremental` (sweep + pool + LLM + métricas),
  `acquire_lock` (flock), `format_summary`, `_write_run_status`, `run`.
- **`store.py`** — upsert com preservação unificada (ver "Preservação e
  pendência").

## Planejamento e delta (o que significa "mudou")

Para cada vaga elegível, na ordem `(score desc, id desc)`:

- **Caso A — já enriquecida, página não mudou**: `job_id` + `final_url` +
  `content_hash` idênticos ao record de sucesso e **sem pendência** →
  `cache_hit`. Nenhuma chamada LLM, nenhuma escrita.
- **Caso B — vaga nova** (sem record): bucket `new`.
- **Caso C — conteúdo mudou** (`content_hash` diferente): `changed`.
- **Caso D — record de falha** (`extracted_at=None`, inclui fetch falho e
  LLM falho): bucket `retry` — tentar de novo.
- **Caso E — vaga sumiu de `eligible_jobs.json`**: nada é apagado — o
  record fica no store para auditoria/cache (seção 2 da spec).

A chave de delta é a da Fase 1: `job_id + final_url + content_hash`, onde
`content_hash` = SHA-256 do texto normalizado. `final_url` diferente →
`changed_source` (a origem mudou; reprocessar). Sem versionamento além
disso.

## Preservação e pendência (spec seção 9)

Regra central: **uma falha nova NUNCA apaga um enrichment válido anterior.**

- Falha + sucesso anterior + hash IGUAL ou hash `None` (fetch falho,
  conteúdo desconhecido) → sucesso preservado; a falha fica auditável em
  `last_error`/`last_failed_at` no próprio record.
- Falha + sucesso anterior + hash DIFERENTE → sucesso preservado **com
  pendência**: o hash novo é registrado em `pending_content_hash` e nada
  do sucesso é apagado (o sucesso é o último enrichment VÁLIDO).
- O planejador considera a pendência: `cache_hit` só se o hash atual ==
  `content_hash` do sucesso E não há pendência; hash atual ==
  `pending_content_hash` → bucket `retry` (a versão pendente voltou);
  diferente de ambos → `changed`.
- Re-extração pendente bem-sucedida → upsert normal (pendência some).
  **Novo sucesso sempre substitui** (regra da v1).

## Execução manual e diária

```bash
# plano pré-fetch, SEM rede, SEM lock:
.venv/bin/python scripts/enrichment_run.py --dry-run

# incremental manual (key exclusivamente do env — nunca em arquivo):
export NVIDIA_API_KEY="..."
.venv/bin/python scripts/enrichment_run.py --top-n 30 --limit 24
```

**Diária (produção)**: o `refresh_daily.py` ganhou `--enrichment`
(default OFF — preserva o comportamento atual e o `--dry-run`),
`--enrichment-limit N` (default 24) e `--enrichment-top-n N` (default
30, corte do ranking — decisão do dono 26/09). No fim do `main()`, após TODOS os
dados principais (rotate → coleta → backup → health → publish → digest →
mensagem → run_info), se `--enrichment` e o gate
`publish_pages.publication_allowed(exit_code, eligible)` liberarem
(exit 0/2 com eligible > 0 — a MESMA decisão da publicação), o refresh
roda `scripts/enrichment_run.py --limit N --top-n N` como subprocesso. A key é
montada no env do subprocesso: `NVIDIA_API_KEY` de `os.environ` OU do
`.env` (via `load_env_config`); ausente em ambos → log "enrichment
pulado: NVIDIA_API_KEY ausente" e o refresh segue (NUNCA é erro).
Qualquer exit (1/2/3) ou exceção do enrichment vira UMA linha de log —
o exit code do refresh NUNCA muda (P1.3 preservado).

O cron de produção (orquestrador edita pós-merge) roda às **09:00 UTC**,
fora da janela degradada da API NVIDIA (~19:30–21:30 UTC). Nada de
segundo scheduler: é a mesma linha do refresh diário.

## Controle de carga e backlog

- **Sequencial**, uma vaga por vez (latência 16–290s/vaga; paralelismo
  esbarraria em rate limit). `--sleep-fetch` (default 2s) entre fetches.
- **Corte do ranking (`--top-n N` / `--enrichment-top-n N`, default 30)**
  — decisão do dono 26/09: SOMENTE as N vagas mais bem ranqueadas do dia
  entram no plano (sweep, pool e backlog operam sobre o corte). Vagas fora
  do corte **nunca** entram no backlog por serem novas; seus records
  (sucessos, falhas, pendências) ficam preservados no store e a vaga é
  coberta no dia em que reentrar no corte. O custo diário fica limitado
  pelo corte, não pelo corpus (~406 vagas hoje). `--top-n 0` = corte
  vazio (plano vazio); o default do projeto é 30.
- **`--limit N`** (default 24) = cap de CHAMADAS LLM por run, sobre o pool
  `retry → new → changed/changed_source` do corte. O excedente fica
  `pending_backlog` e é pego naturalmente pelo próximo run (com o corte
  em 30, o backlog máximo é ~30 — um run de cap 24 quase sempre esvazia
  no dia seguinte).
- Uma vaga nunca bloqueia as demais: exceção vira record de erro
  (`runner_error:<Tipo>`) e o lote segue.

## Retry

- **LLM** (reuso da v1): máx. 3 tentativas, backoff 30/60s. Retryáveis:
  `http_429`, `http_5xx`, `request_error` (timeout/rede), `empty_content`,
  `parse_error`. Não-retryáveis (1 tentativa): demais 4xx. Sequência
  anormal de falhas de API não destrói resultados anteriores (isolamento
  por vaga + preservação do store).
- **Fetch**: UMA tentativa por URL (martelar servidor de carreira não é
  aceitável); a vaga volta no próximo run pelo bucket `retry`.

## Concorrência

`enrichment_run.py` (modo real) adquire `fcntl.flock LOCK_EX|LOCK_NB` em
`<dir do --output>/.enrichment.lock` e segura o fd até o fim do run.
Segunda execução: print `execução concorrente detectada — saindo` +
**exit 3**, sem tocar o store. flock do SO: processo morto libera
sozinho (sem stale lock, sem cleanup manual). `--dry-run` não trava
(read-only). O flock do refresh (cron) já impede refresh sobre refresh.

## Métricas e health

Resumo impresso no stdout ao fim de cada run (todas as linhas caem no log
do cron):

```
== Resumo do enrichment (fase 2) ==
vagas elegiveis: N
corte do ranking: top N
cache hits: N
pool: new N | retry N | changed N | changed_source N
selecionadas p/ LLM: N (cap N) | backlog pendente: N
LLM: chamadas N | retries N | ok N | falha N
fetch: falhas N (timeouts N) | HTTP errors N | js_rendered N | skipped N
preservados (falha não apagou sucesso): N
tokens: in N out N
tempos (s): total N | fetch medio N | LLM medio N
```

**Status file** `data/enrichment/enrichment_status.json` (escrita atômica,
mesmo padrão do store): `{last_run_at, last_success_at, last_exit_code,
model, counts{...}, last_error, duration_s}`. É o health mínimo para
detectar "o enrichment parou de funcionar" (ex.: `last_success_at` parado
no tempo, `last_exit_code` != 0 recorrente, `last_error` persistente).
Nenhuma stack de observabilidade nova; nada vai ao Telegram.

## Artefatos (todos em `data/`, gitignored — nunca ao GitHub/Pages)

- `data/enrichment/enrichment_results.jsonl` — store (1 record/linha,
  key=job_id, escrita atômica tmp+os.replace).
- `data/enrichment/enrichment_status.json` — health do último run.
- `data/enrichment/.enrichment.lock` — lock de concorrência (fd do flock).

## Exit codes (`enrichment_run.py`)

- `0` — run concluído (falha individual de vaga é dado, não erro);
- `1` — erro de setup (input ilegível, eligible vazio, key ausente,
  modelo indisponível);
- `2` — nenhuma vaga processada (ex.: `--limit 0` com pool pendente);
- `3` — execução concorrente detectada.

O refresh NÃO propaga nenhum deles: exit do enrichment é dado operacional.

## Comportamento em falha da API NVIDIA

- Refresh sempre válido: coleta/ranking/Pages/Telegram independem do
  enrichment; `refresh exit 0` + `enrichment parcialmente falho` é estado
  operacionalmente aceitável.
- Dentro do enrichment: falhas retryáveis esgotam 3 tentativas com
  backoff; a vaga vira record de falha (bucket `retry` no próximo run);
  sucesso anterior preservado (com pendência se o conteúdo mudou).
- Rajada de falhas (janela degradada): o lote segue vaga a vaga, nada é
  perdido, `last_error`/counts registram o estado.

## Schema do record

Inalterado da v1 (ver git history / PR #81 para o contrato completo:
identidade/origem, processamento, 8 campos WA + conteúdo com
evidence/confidence, `schema_version` 1). Fase 2 adiciona apenas campos
de auditoria FORA do schema Pydantic, gravados pelo store no dict
persistido: `last_error`, `last_failed_at`, `pending_content_hash`.

## Limitações conhecidas

- **JS-render fora de escopo** (~7% no spike): ficam `js_rendered`.
- **Sweep diário de fetch do corte** (30 GETs com pausa de 2s ≈ 1 min no
  corte default; ~406 GETs ≈ 14 min apenas com `--top-n` alto): é o custo
  de detectar mudança por hash; com o corte em 30 deixa de ser gargalo.
- **`glm-5.3` (não-flash) proibido**: queima max_tokens em reasoning
  (A/B 5/5 no spike); o flash é o único modelo suportado.
- Com o corte em 30, o backlog máximo é ~30 vagas/dia: um run de cap 24
  quase sempre esvazia no dia seguinte (vagas fora do corte não acumulam
  backlog por serem novas). `--enrichment-limit` e `--enrichment-top-n`
  ajustam vazão e abrangência.
- O condicional `oder` é tratado só no prompt (decisão de taxonomia v1).

## Fase 3 — integração aos produtos (26/09)

**Regra arquitetural (inalterável):** *Deterministic pipeline decides. LLM
enrichment informs.* A camada agora alimenta os produtos EXISTENTES —
ranking HTML, Candidate Fit e Telegram Daily Digest — apenas como
**contexto de apresentação**: nunca decide elegibilidade, nunca
altera/cria score, nunca reordena, nunca exclui vaga, nunca bloqueia
publicação.

### Módulo de apresentação (`src/internship_finder/enrichment/present.py`)

Ponto de CONTATO ÚNICO entre os produtos e a camada. Somente
`scripts/interface.py` e `scripts/ranking_digest.py` importam este módulo
(read-only); `ranking.py`, `filters.py`, `materials_ranking.py`, `dedup.py`,
`app_intel.py`, `cli.py`, adapters e coleta seguem SEM importar nada do
pacote — score/eligibilidade intactos **por construção**. Funções puras:

- `load_enrichment(path)` — reusa `EnrichmentStore.load()`; qualquer
  exceção → `{}` (nunca derruba render/digest; aviso no stderr);
- `is_usable(record)` — `extracted_at` presente E
  `page_is_job_posting.value is True` (PIP=false → **invisível**: o texto
  extraído não é do anúncio);
- `is_stale(record)` — `pending_content_hash` presente (sucesso preservado
  de conteúdo antigo, Fase 2);
- `view(record)` — record utilizável → dict de campos PRONTOS com labels
  PT-BR decididos uma vez (salary_text, work_mode, location, german,
  english, student_status, wa por conceito, internship_compatible,
  deadline_date, evidences dos campos prioritários, stale, confidence);
  não-utilizável → `None`. `view_map(records)` filtra tudo de uma vez;
- `fit_lines(view)` — linhas `{"key","kind","detail"}` para o Candidate
  Fit (prioridade eu_citizenship > student_status > internship_compatible
  > idiomas > WA; máx. 6).

### Semântica obrigatória (spec §5/§8)

`not_mentioned` NUNCA vira "não"/false — vira omissão, ou a ausência
EXPLÍCITA "nada mencionado sobre autorização de trabalho na página" quando
todos os 8 conceitos são ausentes (nunca lida como negativa). `unclear`
NUNCA vira conclusão — vira "incerto". Record de não-extração nunca é
exibido e nunca vira `not_mentioned`. Ausência de evidência nunca vira
negativa. Os 8 conceitos de work authorization são exibidos SEPARADOS
(student status ≠ work authorization ≠ sponsorship ≠ EU citizenship...).

### Ranking HTML (`scripts/interface.py`)

- Flag `--enrichment PATH` (default: auto-detect
  `data/enrichment/enrichment_results.jsonl` do CWD — mesmo padrão do
  `--db-join`; ausente não é erro). O auto-detect é o que faz a página
  pública ganhar o bloco sem tocar `publish_pages.py`/`refresh_daily.py`
  (zero diff em ambos).
- `render_html(..., enrichment_map=None)`: `None` = SEM bloco (HTML
  idêntico ao da Fase 8 — compat garantida); map id→view liga, por vaga:
  chip discreto `🔎 LLM` sempre visível + `<details>` "🔎 Análise da
  página oficial (LLM)" com campos compactos, bloco WA com conceitos
  separados, `<details>` aninhado "ver trecho da página oficial" (citação
  literal escapada, apenas campos prioritários: WA/sponsorship/student
  status/idioma/deadline/salary), nota de staleness quando
  `pending_content_hash` e rodapé fixo "não entram no score nem na
  elegibilidade".
- Candidate Fit: `present.fit_lines` ADICIONA linhas depois dos sinais
  determinísticos (`app_intel.py` intocado — nunca substitui, sem nova
  pontuação). `eu_citizenship_required=true` → ⚠ alerta (bloqueador real
  para um candidato brasileiro).
- Segurança: TODO texto do record passa por `html.escape`; o view NÃO
  carrega `content_hash`/`final_url`/`http_status`/`usage`/model/prompts/
  resposta bruta (teste dedicado). O gate `publish_pages.check_public_safe`
  segue o mesmo.

### Telegram Daily Digest (`scripts/ranking_digest.py`)

`digest_sections(..., enrichment_path=None)`: `None` = AUTO
`<dir do current>/enrichment/enrichment_results.jsonl` (layout `data/` da
Fase 2 — `refresh_daily.py` e o `main()` do digest NÃO mudaram). Nova
seção `🔎 Enrichment — dados da página oficial (Top 5 com análise)`:
até 5 vagas do Top 30 com view utilizável, na ordem do ranking, 1 linha
por vaga apenas com campos presentes. Store ausente/corrompido → seção
inteira some (enrichment NUNCA obrigatório). Evidências ficam no HTML
(tamanho). `stale` → sufixo "(extração antiga)". Se a mensagem final
estourar 4096, o compactador existente preserva base+link e a seção some
(mesmo comportamento documentado das seções pessoais).

### Staleness (spec §9)

Política = a existente: metadados `content_hash`/`fetched_at`/
`extracted_at` + `pending_content_hash` (Fase 2) como marcador interno.
NENHUMA política de expiração nova. Record stale é exibido como o ÚLTIMO
enriquecimento válido, com nota de que a página mudou desde a extração —
nunca como extração da versão atual da página.

### Cobertura medida (26/09, 9 records com extração)

salary 22% · work mode 22% (33% contando `unclear`) · location 78% ·
student status 78% · internship compatible 78% · english 78% · german
56% · employer deadline **0%** · algum conceito WA 78% (quase todo o valor
vem de `eu_citizenship_required` 22% + student status). Ferramenta:
`scripts/enrichment_coverage.py` (offline, read-only, uso manual — não
entra no CI).

### O que a Fase 3 NÃO faz

Não cria score LLM, não substitui o score determinístico, não deixa a LLM
decidir elegibilidade/excluir vagas, não altera filtros de país/employment
type, não altera a lógica de deadline, não adiciona JS client-side, não
cria política de expiração nova, não expõe dados privados do tracker. A
decisão de usar campos do enrichment no RANKING fica para fase posterior,
com dados (§12 do relatório da fase).

### Testes

`scripts/test_enrichment_present.py` (novo, 35º do CI — 75 checks):
semântica not_mentioned/unclear, PIP=false, stale, evidência literal,
is_usable, view, fit_lines, segurança do view, fallback de store ilegível.
`scripts/test_interface.py` ganha `test_enrichment_render` (bloco/chips/
escape com `<script>` na evidência, staleness, compat sem map, sequências
`data-score`/`data-job-id` IDÊNTICAS com vs sem enrichment, auto-detect,
store malformado). `scripts/test_digest.py` ganha `test_enrichment_section`
(seção presente/ausente, ≤5 linhas, PIP=false fora, stale, determinismo,
limite 4096). Todos OFFLINE — zero rede, zero API NVIDIA no CI.
