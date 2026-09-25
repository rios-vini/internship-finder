# Camada de Enrichment LLM (isolada) — v1

**Fase**: enrichment v1 (branch `feature/enrichment-layer`). Primeira versão
permanente da camada de enriquecimento por LLM, deliberadamente **isolada**:
nenhum módulo do pipeline importa o pacote `internship_finder.enrichment` —
ela é uma ferramenta standalone (`scripts/enrichment_run.py`). A camada pode
falhar por completo sem impedir: coleta, eligibility, dedup, ranking, geração
do ranking, Telegram ou publicação.

Base: spike de 24/09 (`/home/ubuntu/internship-finder-spike`, veredito SIM
com condições). Os fatos medidos no spike são reutilizados; os 2 falsos
positivos reais que o spike expôs viraram few-shots obrigatórios no prompt e
guardas determinísticas no normalizador.

## Arquitetura e fluxo

```
eligible/ranked jobs (data/eligible_jobs.json)
  → select_sample (determinística: top 16 + 4 WA + 4 sem description)
  → fetch_page (requests, 1 tentativa, redirects, timeout (10, 30))
  → normalize_html (BeautifulSoup → texto)
  → classify_page (page_status)
  → [cache] store: job_id + final_url + content_hash → skip da LLM
  → extração GLM-5.3-Flash (JSON estruturado com evidências)
  → EnrichmentRecord (pydantic, schema_version 1)
  → EnrichmentStore.upsert (JSONL, escrita atômica, incremental)
```

Módulos (`src/internship_finder/enrichment/`):

- **`schema.py`** — contrato de dados: `EnrichmentRecord`, enums (`WAValue`,
  `PageStatus`, confiança), shapes por campo (value/evidence/confidence),
  normalização do JSON da LLM (`fields_from_llm`) com guardas determinísticas,
  confiança record-level (`compute_record_confidence`).
- **`fetch.py`** — fetch da página oficial: `fetch_page` (uma tentativa,
  exceções capturadas por tipo), `classify_page` (8 estados), `title_match`
  (threshold 0.5, do spike), `looks_js_rendered`. Transport HTTP injetável
  (`Transport`/`RequestsTransport`).
- **`html_norm.py`** — HTML → texto: remove script/style/noscript/template/
  svg/head, nav/footer e header boilerplate (header com `<nav>`); entidades
  decodificadas; sem markdown.
- **`llm.py`** — cliente GLM-5.3-Flash: key exclusivamente de
  `NVIDIA_API_KEY`; `validate_model` (fail fast); `extract` (máx. 3
  tentativas, backoff injetável, erros sanitizados); `parse_llm_json`
  (tolerante: think-blocks, fences, texto envolvente, `raw_decode`);
  `EXTRACTION_PROMPT` (conservador, 3 few-shots obrigatórios).
- **`runner.py`** — `select_sample` (determinística), `should_skip` (cache),
  `process_job` (fluxo por vaga), `process_batch` (isolamento por vaga,
  resumo), `run` (entry point com exit codes).
- **`store.py`** — `EnrichmentStore`: JSONL key=job_id, escrita atômica
  (tmp + `os.replace`), upsert incremental, preservação de sucessos, `load`
  tolerante a linhas malformadas.

## Schema do record

Identidade/origem: `job_id`, `company`, `title`, `source`, `original_url`,
`final_url`, `fetched_at` (ISO UTC), `http_status`, `page_status` ∈
`ok | redirected | not_found | empty_content | js_rendered | http_error |
timeout | fetch_error`.

Processamento: `content_hash` (SHA-256 do texto normalizado), `extractor`
(constante `llm-glm-5.3-flash`), `model`, `extracted_at`, `confidence`
(high/medium/low/None), `error`, `attempts`, `latency_s`, `usage` (tokens
in/out), `content_truncated`, `schema_version` (constante 1).

Extração (shape `value | evidence | confidence`):

- **8 campos WA** (`WAValue` = `true | false | not_mentioned | unclear`):
  `student_status_required`, `work_authorization_required`,
  `existing_work_authorization_required`, `work_permit_required`,
  `residence_permit_required`, `visa_sponsorship`,
  `international_candidates_explicitly_accepted`, `eu_citizenship_required` —
  mais `internship_compatible`.
- **Conteúdo**: `salary` (valor literal + período + moeda + evidência),
  `work_mode` (on_site/hybrid/remote/not_mentioned/unclear), `location`
  (declarado na página), `german_requirement`/`english_requirement`
  (none/conversational/fluent/business/native/not_mentioned/unclear),
  `employer_deadline` (data explicitamente declarada, YYYY-MM-DD),
  `page_is_job_posting` (bool, âncora company+title).

Regras de valor (contrato):

- `true`/`false` EXIGEM `evidence` (citação literal ≤200 chars) e
  `confidence` por campo — violação é rejeitada pelo schema.
- Ausência de informação → `not_mentioned` (NUNCA `false`).
- Evidência conflitante, insuficiente ou CONDICIONAL → `unclear`.
- `salary`/`employer_deadline` sem evidência → valor descartado (nunca
  inventado).
- Record de não-extração (fetch falhou/página inútil/LLM falhou): campos de
  extração ficam `None` — ausência de valor nunca vira `not_mentioned`.

**Confiança record-level (determinística)**: `high` = extração completa,
todo true/false com evidência, `page_is_job_posting=true`, sem truncamento;
`medium` = idem com truncamento; `low` = `page_is_job_posting=false` ou
true/false sem evidência; `None` = não extraído.

## Decisões de taxonomia (WA)

Os 8 conceitos são DISTINTOS, nunca sinônimos — cada campo é avaliado
INDEPENDENTEMENTE (a evidência de um não prova nada sobre os outros):

1. `student_status_required` — matrícula universitária (Immatrikulation).
   Comprovar matrícula NÃO comprova autorização/sponsorship/residence permit.
2. `work_authorization_required` — afirmação genérica, sem especificar qual.
3. `existing_work_authorization_required` — candidato JÁ POSSUA autorização
   válida. **Regra do condicional**: `ggf.` / `falls erforderlich` /
   `if applicable` etc. → `unclear` com a evidência, NUNCA `true` (FP real
   do spike: "sowie ggf. eine gültige Arbeits- und Aufenthaltserlaubnis" —
   prompt ensina E o normalizador confere).
4. `work_permit_required` — Arbeitserlaubnis/work permit como requisito
   (mesma regra do condicional).
5. `residence_permit_required` — Aufenthaltserlaubnis/residence permit como
   requisito (mesma regra).
6. `visa_sponsorship` — empregador patrocina/cobre/assiste visto. Ausência
   de promoção → `not_mentioned`, nunca `false`.
7. `international_candidates_explicitly_accepted` — aceitação EXPLÍCITA na
   VAGA. Frase genérica de DEI da EMPRESA ("Bayer begrüßt Bewerbungen aller
   Menschen ungeachtet ... nationaler Herkunft") NÃO conta → `not_mentioned`
   (FP real do spike, few-shot + guarda).
8. `eu_citizenship_required` — cidadania UE explicitamente exigida.

Nota sobre `oder`: o prompt lista "oder" como marcador condicional (quando
conecta o termo de autorização a uma alternativa), mas a guarda
determinística NÃO usa `oder` sozinho — "Arbeitserlaubnis oder
Aufenthaltstitel erforderlich" permanece requisito duro. `oder` exigiria
análise sintática que o normalizador não faz; errar para `unclear` em toda
frase com "oder" destruiria precisão (o termo aparece em qualquer texto).

## Cache/idempotência

Antes da chamada LLM (após fetch — a chave de cache precisa de
`final_url` + `content_hash`): existe record bem-sucedido com mesmo
`job_id` + `final_url` + `content_hash` → **skip** (log `cache_hit`), LLM
não é chamada. Conteúdo mudou (`content_hash` diferente) → novo enrichment
(upsert). Record anterior é falha → retry permitido. Store vazio → processa
tudo da amostra. Sem políticas de expiração (deliberado).

## Retry (camada LLM)

- **Retryáveis** (máx. 3 tentativas, backoff injetável default 30s/60s):
  `http_429`, `http_5xx`, `request_error` (timeout/rede), `empty_content`
  (resposta vazia), `parse_error` (JSON picado em janela degradada — medido
  no spike).
- **Não-retryáveis** (1 tentativa, erro registrado): outros 4xx (auth/
  request inválido não se resolve esperando).
- Fetch: UMA tentativa por URL — retry na camada de fetch martelaria
  servidores de carreira; a vaga volta no próximo run.
- Runner: sequencial (latência 16–290s/vaga; paralelismo esbarraria em rate
  limit), isolamento por vaga (exceção de uma vaga = record de erro, lote
  segue).

## Persistência

- Arquivo: `data/enrichment/enrichment_results.jsonl` — 1 record por linha,
  key = `job_id`. `data/` é gitignored: nunca vai ao GitHub/Pages.
- Escrita ATÔMICA (tmp no mesmo diretório + `os.replace`), mesmo padrão do
  `_write_atomic` do cli.py.
- Upsert incremental: cada record salvo logo após sua extração (crash no
  meio não perde o que já foi). Reprocessar uma vaga substitui o record do
  mesmo `job_id`.
- **Preservação**: record bem-sucedido anterior NUNCA é apagado por falha
  nova do MESMO conteúdo (`content_hash` idêntico → falha descartada).
  Falha de conteúdo novo (hash diferente) é gravada — o estado atual da
  página (ex.: not_found) é dado válido.
- `load()` tolerante: linha malformada pula com aviso, nunca crasha.

## Como rodar a carga inicial

```bash
# plano da amostra, SEM rede nenhuma:
.venv/bin/python scripts/enrichment_run.py --dry-run

# carga real (a key vem EXCLUSIVAMENTE do env — nunca em arquivo):
export NVIDIA_API_KEY="..."   # no shell/cron, nunca versionado
.venv/bin/python scripts/enrichment_run.py
```

Flags: `--top 16`, `--extra-wa 4`, `--extra-nodesc 4`, `--limit N` (teto de
vagas do run), `--input` (default `data/eligible_jobs.json`), `--output`
(default `data/enrichment/enrichment_results.jsonl`), `--sleep-fetch 2.0`.
Exit: 0 = run concluído (falha individual é dado); 1 = erro de setup (input,
amostra vazia, key, modelo); 2 = nenhuma vaga processada.

O runner valida o modelo no início (`GET /v1/models`, fail fast) e loga por
vaga `[i/N] status empresa título`. Resumo final: counts por `page_status`,
extrações ok/falha, cache_hits, latências (min/med/max), tokens totais.

## Amostra

Determinística (`(score desc, id desc)`): top 16 do ranking + primeiras 4
fora do top com work authorization detectada no feed (detector atual,
read-only) + primeiras 4 sem `description` no feed (a página oficial é a
única fonte para elas). Duas chamadas idênticas → mesmo resultado; ids
únicos. Amostra representativa (múltiplos ATS, redirect, sem description,
WA, salário, DE, EN) — não processa as ~400 vagas indiscriminadamente
(latência/tokens medidos no spike tornam isso inviável e desnecessário).

## O que NÃO faz (deliberadamente fora desta fase)

- Não altera eligibility/score/ranking; não coloca LLM dentro do modelo
  `Job`; não usa LLM como filtro/decisor; não substitui detectores
  determinísticos.
- Browser/headless (páginas JS-render ficam `js_rendered` — fora de escopo).
- Não enriquece todas as vagas indiscriminadamente.
- Sem PostgreSQL/Redis/DuckDB/ORM/Docker.
- Sem integração ao HTML/Telegram/ranking/GitHub Pages.
- Sem políticas complexas de expiração de cache.

## Limitações conhecidas

- **JS-render fora de escopo** (~7% das páginas no spike): ficam
  `js_rendered` e não são extraídas.
- **Latência real 16–290s/vaga** (API NVIDIA free tier): 24 vagas ≈ 30–90
  min sequenciais; janela degradada pode esgotar retries (record de falha,
  retriable no próximo run).
- **Amostra ≠ corpus**: 24 vagas do topo + WA + sem-description; a taxa de
  extração em vagas de score baixo não foi medida.
- **`glm-5.3` (não-flash) é inviável** para JSON estrito (queima todo o
  max_tokens em reasoning — A/B 5/5 no spike); o flash é o único modelo
  suportado pela camada.
- O condicional `oder` é tratado só no prompt (não na guarda — ver decisão
  de taxonomia acima).
