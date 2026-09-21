# Project Status

Last updated: 2026-09-20

## Current state

The project has a working company-oriented ATS collection pipeline (collection →
filtering → dedup → ranking), with SQLite persistence, structured error codes,
observability (health), CI and standardized requirement tracking in
`MASTER_PLAN.md`. Since the **Fase 4 (19/09)**, the eligible set feeds **two
independent rankings**: the main profile (`ranking.py` — Supply Chain /
Procurement / BI / Analytics / Automation) and the **Materials Engineering
profile** (`materials_ranking.py` — `materials_score`/`materials_breakdown`
own components; the main score is never touched and never summed). Same 476
eligible jobs, no new collection/filters/dedup; the public page has a
profile switcher and the Telegram digest a compact "Perfil Materials
Engineering" section. Details in the MASTER_PLAN log (19/09, FASE 4) and
`docs/relatorio_fase4_perfil_materials.md`.

Current collection scope includes **101 evaluated/operational companies**
(12 initial + 27 E2 expansion + 25 added 08/09, P3 #23 — Lote A: 8 DE
(Allianz, Adidas, Puma, Hella, Fraunhofer, Merck, Boehringer Ingelheim,
HelloFresh; Otto removed 15/09 — false positive); Lote B: 17 NL/CH/AT (Philips,
ING, Heineken, Adyen,
Nestlé, Novartis, ABB, Red Bull, Roche, Swiss Re, Schindler, Shell,
Unilever, AkzoNobel, Rabobank, NXP, OMV); all validated with
`verify_companies.py --fetch` — match exato + scraper + fetch OK)
+ **17 added 15/09** (cobertura: Liebherr, STIHL, Simon-Kucher, BAUHAUS/bahagag,
BCG, MediaMarkt/mediasatur, Tchibo, HORNBACH, About You, Hager Group, Lanxess,
Linde, Sonepar, Flix, Kuehne+Nagel, Vattenfall, 4flow)
+ **6 added 16/09** (auditoria próxima onda: BMW AG, SMA, Jobs Festo, Wacker,
Webasto Jobportal, Roland Berger — nomes exatos do manifest; `successfactors:jobs`
compartilhado desambiguado por URL)
+ **9 added 17/09** (auditoria próxima fronteira: Picnic, cbs Corporate Business
Solutions, AIXTRON SE, Holzland Becker, CarOnSale, CURRENTA GRUPPE, Miebach
Consulting, Engelhart, audibene/hear.com — nomes canônicos = nomes exatos do
manifest)
+ **5 added 18/09** (última onda de cobertura: Sungrow EMEA, AutoScout24, Huawei
Research Center Germany, EAT HAPPY GROUP, VDI Technologiezentrum GmbH).
+ **Fase 6 (20/09)**: **Candidate Fit + Application Intelligence + Mobile UX** —
  conceitos separados do score de relevância (score = SÓ relevância; sinais de
  candidatura nunca entram nele). Novo `app_intel.py` (puro/determinístico):
  alemão por EXIGÊNCIA detectada no TEXTO (required −2,0 / preferred −0,5 /
  plus e sem menção neutros — fim do bônus por "conter alemão"; EN +1,5
  inalterado; `german_level` com negação explícita, CEFR, "von Vorteil",
  "English required, German is a plus"→preferido; "Deutsche Bahn"/"Deutschland"
  não contam), `work_authorization` (5 estados SÓ com evidência; 444/474 `not
  mentioned`), `deadline_kind` (employer vs validade do feed SuccessFactors
  [`g:expiration_date` = collected+30d, validado 295/295] vs none — SF nunca
  vira prazo/urgência/"vagas expirando"), urgency 🟢>14/🟡7–14/🟠3–6/🔴≤2,
  `candidate_fit`/`possible_problems`/`quality_flags`/`application_readiness`.
  Interface: chips por vaga, bloco "sinais de candidatura e possíveis
  problemas", seção "Como este ranking funciona" com PESOS REAIS das
  constantes (nada duplicado), filtros novos (vagas expirando ≤2/≤7/≤14 — só
  deadline confiável; work auth; idioma; Top 30; quality flags; contador
  "Filtros (N)"), **mobile: tabela → card <760px** sem scroll horizontal,
  dark mode, `--ref-date`/`--db-join` (freshness first/last_seen). Ranking
  real (run 20/09, 474 vs archive 19/09, 476): 448 comuns; **278 (62%)
  mudaram** (deltas −2,5×148, −2,0×30, −1,0×73, −0,5×27); Top 30: 23 ficam,
  7 saem/7 entram (saídas = alemão exigido). Suíte local **28/28**, CI 27→28
+ **Fase 7 (20/09)**: **Company & Location Intelligence** — camada de
+  desempate SEPARADA do score (Job Fit) e do Candidate Fit (Fase 6):
+  Opportunity Intelligence em `opportunity_intel.py` (funções puras) +
+  arquivos curados versionados `company_intel/*.json` (12 empresas e 12
+  cidades com fonte+qualidade+data). Empresa (setor/porte/sede/internacional/
+  áreas/site/carreiras), benefícios (só com fonte — nenhum presumido),
+  carreira (evidência oficial), Internship→Full-time (Explicitly supported/
+  Evidence available/Not mentioned/Unknown — nunca probabilidade), turnover
+  (fato com fonte e período), salário SOMENTE quando citado no anúncio
+  (18/474 no run 20/09: STIHL 2.117 €/mês, Bayer 2.280 €), work mode por
+  evidência (hybrid 91/remote 5/on_site 105), cidade real da string (108
+  cidades; "Germany" não vira cidade), custo de vida contexto (Numbeo
+  ago–set/2026, 12 cidades). Interface: seções recolhíveis por vaga
+  (Empresa/Benefícios/Carreira/Pathway/Localização/Salário/Turnover/Fontes)
+  + Compare opportunities (2–4 vagas; fatores; sem vencedor automático).
+  NADA entra no score; ranking intocado (data-scores idênticos ao snapshot);
+  zero rede em tempo de render (arquivo ausente → Not available, página
+  continua). Suíte local **29/29**, CI 28→29. Relatório:
+  `docs/relatorio_fase7_company_location_intel.md`.
  (`test_app_intel.py` novo; `test_interface` +11 casos node + Fase 6).
  Detalhes: `docs/relatorio_fase6_candidate_fit.md`. Status pessoal =
  evolução futura (página estática, sem backend); Company Intelligence
  (Fase 7) NÃO implementada.
+ **Fase 5 (19/09)**: camada **PT-BR determinística** na interface (`src/internship_finder/ptbr.py` — novo: glossário ≈80 entradas, `title_pt`, `detect_language`, `employment_type_pt`, `country_label`, `relevance_signals`); o HTML público mostra **título PT-BR como campo separado** (original sempre visível com tag `Original (EN/DE)`, 467/476 títulos traduzidos), tipo do anúncio e país em PT-BR, e o bloco **"por que esta vaga?"** explica cada componente REAL do breakdown do perfil ativo em PT-BR (penalidades separadas em "o que reduziu a nota"). SEM tradução integral de descrições, SEM LLM/API/serviço externo; `ranking.py`/`materials_ranking.py`/filtros/dedup/coleta **intocados**. Suíte local **27/27 scripts — 1.345 checks — 0 falhas** (test_ptbr: 59 checks, CI 26→27). Detalhes: `docs/relatorio_fase5_ptbr.md`.
+ **Fase 4 (19/09)**: segundo perfil **Materials Engineering** — `src/internship_finder/materials_ranking.py` (novo): o MESMO conjunto elegível (476) ganha `materials_score`/`materials_breakdown` próprios (materiais/metais/polímeros/cerâmicas/superfície/corrosão/ensaios + manufatura/processo; quality/R&D gated por contexto técnico; penalidades de função de negócio no título); `score` do principal intacto por id; interface com **seletor de perfil** (2 tabelas na mesma página, JS da Fase 3 reusado); digest do Telegram com seção "Perfil Materials Engineering" (Top 5 + novas no Top 30). Verificado: 476/476, rankings independentes, topo = polímero/beschichtung/verfahrenstechnik/bateria; suíte **26/26** (test_materials_ranking no CI).
+ **Fase 3 (18/09)**: interface do ranking reescrita (`scripts/interface.py` —
apresentação pura): a página pública mostra **todas as vagas elegíveis** (476)
com resumo no topo, **filtros/ordenação client-side** (JS vanilla embutido,
sem backend), posição = posição no ranking do pipeline, badge Top 30 e
"por que este score" com os componentes reais do `score_breakdown`;
pipeline/pesos/filtros/dedup intocados; `publish_pages.py`/`refresh_daily.py`
intocados (regeneração diária automática preservada). Detalhes no Log do
MASTER_PLAN (18/09, FASE 3).

Latest documented full runs (cron 06:00 UTC; reproduced offline by `scripts/coverage.py` and the current pipeline). **Current snapshot = 18/09 run** (1st with 101 companies); earlier runs below are historical records:

- **18/09 (current): 72,866 raw → 6,635 student-type → 1,411 target-area → 507 Germany → 476 eligible (dedup −31)** — registry at **101 companies**; CI suite **23/23 scripts — 1033 checks — 0 failures** (re-run 18/09, on the #65 head); 65 companies / 50 tenants with eligible jobs (BMW AG 81, SAP 74, BoschGroup 48, Volkswagen AG 23, teampicnic 20, Fraunhofer-Gesellschaft 19, Knorr-Bremse 15, Liebherr-International S.A. 13, BASF SE 13, STIHL 12); ATS (eligible): successfactors 296, smartrecruiters 54, greenhouse 33, phenom 24, workday 16, recruitee 14, eightfold 12, cornerstone 10, softgarden 6, ashby 4, personio 4, teamtailor 3; scores min 1.0 | median 6.25 | max 17.5; health: 3 alerts (all documented external/legitimate: Lidl timeout ×15, Kuehne+Nagel cornerstone ×3, SMA oracle homonym ×2)
- **17/09 (histórico): 71,735 raw → 414 eligible** — registry at 96 companies (1st run with 96)
- **16/09 (histórico): 69,586 raw → 5,813 student-type → 1,167 target-area → 355 Germany → 331 eligible (dedup −24)** — registry at 87 companies; 47 companies / 35 tenants with eligible jobs
- **14/09 (histórico): 60,222 raw → 281 filtered → 257 eligible (dedup −24)** — registry at 65 companies; CI suite 23/23 — 958 checks
- 06/09 (histórico): 37,953 raw → 3,080 student-type → 752 target-area → 246 Germany-eligible → **222 eligible** (dedup −24)
- 07/09 (histórico): **37,957 raw → 220 eligible** (dedup −24; 43 tenants ok / 2 empty / 1 timeout / 1 error — falhas recorrentes conhecidas: moka Bayer + Lidl timeout, ver MASTER_PLAN P3 #36)
- Companies/tenants with eligible jobs and the ATS breakdown below were measured on the 06/09–07/09 runs (histórico; the ATS figures sum to the 06/09 total of 222):
  - 24 companies / 20 tenants (source) with eligible jobs (SAP 71, BoschGroup 41, Volkswagen AG 20, BASF SE 17, Knorr-Bremse 16, ... — see README coverage table)
  - ATS (eligible): successfactors 150, smartrecruiters 41, eightfold 11, workday 8, phenom 5, ashby 3, greenhouse 3, cornerstone 1.

Scores (measured 06/09 — histórico): min 2.50 | mediana 6.75 | max 16.75 · 222/222 `country_iso='de'`.

With `INTERNSHIP_FINDER_GEOCODING=1` (Workday fallback, OFF by default): historical measurement over the 31/08 snapshot was 245 eligible (+9 Workday DE).

## Completed

- Company-based ATS discovery
- Exact company matching
- ATS scraper execution
- Subprocess timeout protection
- ATS-specific adapters
- Normalized `Job` model
- Internship/student filtering
- Target-area filtering
- Country filtering
- Deduplication
- Ranking
- JSON output (atomic write)
- CSV output (atomic write)
- E2 company expansion
- 39-company collection scope (E2 expansion, 2026-08-12 — **historical**; expanded to 65 on 08/09, P3 #23; registry today: **101** after the 15/09 → 18/09 waves)
- Post-audit corrections F1–F3 (parecer A, 2026-08-13)
- **P0 — Application deadline + hardening ACH-01..09** (PR #8, merged 31/08): `Job.application_deadline` (`datetime|None`, never inferred from `posted_at`), dedup per tenant, IDs without URL, JSONL metrics, exit code 2 on partial failure.
- **P0.1 — Workday Country/Location Resolver** (PR #9, merged 01/09): `geocoding.py`, cache-first, flag `INTERNSHIP_FINDER_GEOCODING` (OFF), adapter fallback after `infer_country_iso`; +9 Workday DE recovered with the flag on.
- **P1 #5 — SQLite persistence** (PR #10): `storage/sqlite_store.py`, flag `--sqlite PATH` (stdlib `sqlite3`), canonical Job schema + `first_seen`/`last_seen`/`active`/`archived`.
- **P1 #3 — CI GitHub Actions** (PR #11): `.github/workflows/ci.yml` runs the standalone suite (`scripts/test_*.py`) on a clean Python 3.12 runner; exit 0 = TUDO OK.
- **P1 #6 — Observability** (PR #12): `health.py`, flag `--health [PATH]` — JSON report per tenant/ATS over the JSONL + drop/recurring-error alerts.
- **P1 #7 — Structured error codes** (PR #13): `errors.py` (`CollectionError` + codes), structured queue payload, `error_code` in the JSONL.
- **P1 #8 — Multiprocessing lifecycle** (PR #14, merged 02/09): `fetch_with_timeout` with 4 outcomes (timeout / dead worker / erro / success), cleanup in `finally`.
- **P3 #18 — venv synced with `ats-scrapers` pin `ae0ad53`**: reinstall from the pin; SAP exposes `application_deadline` (1086/1086).
- **P2 #11 — Job validation forte** (PR #16, merged 03/09): pydantic validators on `Job` (empty `title`/`url` = validation error; empty optionals → `None`), `normalize_job_dict` for the filter path, adapter rejects missing titles (`NORMALIZATION_ERROR`, defensive), `test_validation.py` in CI.
- **P2 #12 — Country/domain module** (PR #17, merged 03/09): country/location logic extracted from `filters.py` into `countries.py` (constants + inference + spec functions, moved verbatim, behavior unchanged); `filters.py` re-exports the symbols (consumers untouched); `test_countries.py` in CI.
- **P2 #16 — test_ranking decoupled from the data snapshot** (PR #18, merged 03/09): fixed synthetic `FIXTURE` (18 jobs) + `test_fixture_ranking()` validating the ranking rules at rank level (top = target area, no senior in top, A-grade per area in TOP N, presales SCM preserved, SAP Analytics Cloud masked, marketing w/o area out of top 25%, JMP/trainee penalized); `test_real_data()` reduced to format invariants + observability; suite 16/16 local, deterministic; the 5 pre-existing failures are gone.
- **P2 #14 — Dedup 2.0 textual** (PR #19, merged 03/09): measured first on the real dataset (12 candidate EN/DE pairs, 4 TRUE duplicates of the same job escaping as `Praktikant`≈`Working Student`, `Intern`≈`Working Student`, `Internship`≈`Praktikum`); `TYPE_EQUIVALENCES` extended with word-boundary regex + repeated-token collapse in the bag; `Pflichtpraktikum`/`trainee` NOT touched (anti-tests); description kept OUT of the fingerprint (decided); baseline 236→**232** (4 TRUE dups, company+title+location); `test_countries` decoupled from the magic number 236 (subset invariant + delta observability); suite 16/16 local, CI run `33799148404` green.
- **P2 #13 — Company Registry operacional** (PR #20, merged 04/09, main `e7604db`, CI run `33840628495` green): `src/internship_finder/registry.py` is the single source of truth for the collection companies in code (39 when merged; the registry SEED now holds 65 — canonical name + reference ATS/tenant + `enabled`); `--registry` CLI flag collects the ENABLED entries (`--registry --companies "Bosch,SAP"` restricts to a subset, order preserved; plain `--companies` still works); per-company status is derived from the metrics JSONL via `company_status` (read-only, malformed records never crash) — design decision: **registry = configuration, JSONL = status**; `test_registry.py` added to CI (array now 13 scripts); README gained a "Registry de empresas" section.
- **P2 #15 — `--country` standardized and validated** (05/09): `parse_country_spec` now raises `ValueError` for non-ISO tokens or an empty spec (e.g. `de,xx`, `,`); the CLI converts it to `parser.error` (clear message, exit 2) before reading input/collecting. Previously an invalid value silently produced 0 jobs (`--country xx`) or ignored bad tokens (`de,xx`). Filter behavior unchanged for valid specs: baseline `--country de` → 232 identical ids (list-by-list); `europe` 371 / `all` 31006 / `remote` 1 unchanged. `test_countries.py` +21 checks (spec validation + CLI error block); suite 14/14, `data/` untouched.
- **P2 #10 — Zero-return + anomaly detection** (05/09): 3rd alert type in `health.py` (`_detect_zero_return`): a source whose most recent run (by `run_id`) is `empty` after ≥3 prior `ok` runs with jobs (`collected > 0`) → coverage regression; empty-consistent sources (`bamboohr:sap`, `smartrecruiters:sap`) never alert (anti-tests); gate mirrors the drop's spirit (1–2 oks = plausible fluctuation). `build_health_report` now emits drop + recurring_error + zero_return; `scripts/refresh_daily.py` formats it ("voltou a zero (empty) após N runs com vagas") — Telegram flows unchanged (anti-spam intact). Calibrated on the real history (4 runs): **0 zero-return alerts** (no source with ok>0 and empty — clean baseline); live health stays at the 1 factual alert. `scripts/test_zero_return.py` (offline, 20 checks) added to the CI array (now 15 scripts); suite 16/16 local; `data/` untouched (stat before==after).
- **P2 #17 — Daily refresh + alerts** (05/09): `scripts/refresh_daily.py` runs the real collection (`--registry --timeout 60`) daily with rotation of `data/` outputs into `data/archive/<ts>/` **before** the run (rollback = copy back), evaluates health via the existing `build_health_report` on the updated JSONL, and sends a Telegram alert **only on anomaly** (exit != 0 or drop/recurring-error alerts; 1 message per run, alerts deduped by source; `--always-notify` = optional daily digest; no token in `.env` → warning, no send, never crashes). `--dry-run` validates rotation+health+message in a synthetic tempdir without network or `data/` writes. Cron installed (05/09, 06:00 UTC, `flock -n` guard covering the whole run — absolute paths, corrected the same night after `flock ... cd ... &&` proved broken: flock execs via `execvp` and `cd` is a shell builtin; backups in `/tmp/crontab_backup_0509.txt` and `/tmp/crontab_backup_0509_v2.txt`). Tested offline (`scripts/test_refresh.py`, in CI — array now 14 scripts) and with one authorized real run: `2026-09-05T20:43:07` → 38.038 raw → 248 filtered → **224 eligible** (dedup −24), 43 ok / 2 empty / 1 timeout / 1 error tenants, health found the known `smartrecruiters:other` anomaly (70 runs) + a new real one (`successfactors:lidlstiftuP2`), Telegram answered `ok:true` (message_id 318). Rollback documented in README "Daily refresh". The metrics JSONL was sanitized the same night (05/09): only the 4 real runs' records kept (37.373 / 1.084 ×2 / 38.038 → 104 lines, 39 companies), removing mock junk (`smartrecruiters:other` 70×, `successfactors:acme` 140×); post-clean health shows one factual alert (`successfactors:lidlstiftuP2` — timeout 31/08 + 05/09).

- **P3 #20 — ACH validations, measured first** (06/09): (ACH-18) CSV contract decided — **JSON = complete source, CSV = tabular view**; `remote` column added to `CSV_COLUMNS` (was absent in 38.038/38.038 `jobs.csv` rows and 224/224 eligible rows; `description`/`raw`/`score_breakdown` intentionally stay CSV-out); (ACH-14) `--limit` semantics confirmed post-fetch per tenant (limit=2 → 2/tenant via mock) and the CLI now rejects `--timeout <= 0` / `--limit < 0` with a clear exit-2 error before collection (undefined behavior before: deadline=only margin, `[:-k]` slice); new offline `scripts/test_collect_flags.py` (19 checks) in CI (array 15→16); (ACH-16) `remote` field never populated by any ATS (0/38.038) — filter works via location text (101 markers, 1 remote-eligible), documented no-op; (ACH-17) country vs country_iso 0/38.038 mismatches (same inferred value by adapter construction), measured no-op; (ACH-20) 0 dates in DD.MM.YYYY anywhere (eligible + raw) — "no measured need", no parser; (ACH-19) BY removed from `EUROPE_COUNTRIES` (code contradicted the documented "RU/BY out" rule; 0 real `by` jobs). Local suite 17/17 TUDO OK from scratch cwd; `data/` untouched (stat before==after); funnel reproduced 38.038→224 identical.
- **P3 #21 — Dead code (ACH-13), reference audit** (06/09): every public symbol in `src/` (73 across 17 modules) and every non-test script was grep-audited repo-wide (src/, scripts/, .github/, docs, README, AGENTS — word-boundary) plus a pyflakes pass (throwaway /tmp venv, project venv untouched). No public symbol ended with 0 references — the minimum was `Score.to_dict` (0 call sites; real serialization is `d["score"] = score.total` / `score_breakdown`). Removed 16 zero-reference items, all behavior-neutral: `Score.to_dict`; unused `import json` in `health.py`; 4 dead re-export names in `filters.py` (`EUROPE_COUNTRIES`, `COUNTRY_NAMES`, `_country_name_from_location`, `_iso_token_from_location` — consumers import from `countries`; `COUNTRY_CODES`/`is_remote` kept, exercised by `test_compat_re_export`); unused imports/locals in 6 test files + `refresh_daily.py` (including `keys_w = dict(candidate_keys_for_audit := {})` walrus junk in test_dedup). Deliberate `# noqa: F401` imports kept (author intent); `CompanyResolver`/`company_status` kept (tested + documented public APIs); `__version__` kept (package convention). CI array unchanged (16); local suite 17/17 TUDO OK before and after from scratch cwd; `data/` untouched (stat before==after). Observation: README states `company_status` is "exposed by `--health`" but `cli.py` does not call it (doc≠code, out of scope).

- **P3 #31 — Corrections batch** (PR #31, merged 06/09, main `c2fcfb2`): Apprentice/Apprenticeship (EN learning programs) excluded like the DE Ausbildung rule (2 real VW jobs left eligible); `trainee` removed from `STUDENT_EMPLOYMENT_TYPES` (generic trainee no longer passes on `employment_type` alone; 0 jobs affected, measured); `read_metrics` skips malformed JSONL lines instead of crashing; `company_status` orders by `(run_id, timestamp)` instead of file position; `--health` now exposes `company_status` under the `companies` key (doc minus code gap closed). Funnel measured: 37,953 -> 3,080 -> 752 -> 246 -> **222** (before the fix: 248 -> 224). Suite 17/17 OK before/after; `data/` untouched.
- **P3 #30 — Operations batch** (PR #30, merged 06/09, main `d0a3ea1`): daily refresh now collects with `--sqlite data/jobs.db` (first_seen/last_seen/active/archived persisted in production; the `.db` is not rotated); archive cleanup with `--retention-days` (default 14, 0 = off, runs after each rotation); disk usage >80% adds a "⚠️ Disco: N% usado" line to the Telegram message; collection subprocess inherits the caller env; `requirements-lock.txt` added (snapshot of the resolved environment via pip freeze; reproducibility only — outside CI and the standard install; pyproject.toml remains the source of truth for declared dependencies). `test_refresh` 43->60 asserts; suite 17/17; `data/` untouched.
- **P2 #29 — Docs consolidation** (PR #29, merged 06/09, main `9477339`): P1 #5 SQLite registered as implemented (documental drift fixed) + P3 #30 gate checks 15:01 and 19:47 UTC (path B - gate not fired, PyPI still 0.3.0), both recorded in MASTER_PLAN log.
- **P3 #35 — Mensagem do Telegram didática** (07/09): template em linguagem natural ("X de Y fontes falharam", nomes de empresa via `company` do JSONL, códigos de erro traduzidos, "recorrente há N runs"); `test_refresh` +4 checks didáticos.
- **P3 #36 — Falhas recorrentes do refresh** (07/09): `pycryptodome>=3.20` no pyproject resolve `moka:bayer/148387` (Bayer — validação real na coleta do cron seguinte); Lidl timeout aceito como limitação monitorada.
- **Ata da auditoria 06/09** (07/09): `docs/ata_auditoria_0609.md` — registro permanente dos achados A1–A9 e ações (antes só na conversa).

- **P3 #22 — Data/code separation + Parquet + chunking: measured, no action** (08/09; full numbers in the MASTER_PLAN log): `jobs.json` is 114MB (37,957 jobs, ~3KB/job) and loads in 828ms; 3 consecutive runs show ~0% daily growth (38,038→37,953→37,957; churn ~116 ids/day, net ~0 — only the cumulative `jobs.db` grows, ~+0.13GB/year); real format measurements: gzip −9 = 14.4MB, parquet-zstd = 12.2MB, SQLite read 358ms, parquet-zstd read 52ms. Fixed thresholds declared before measuring (parquet only if JSON ≥1GB or read >10s; data repo only if `data/` ≥10GB or disk >75%; chunking only if a future #25 interface payload >10MB) — none hit, so no new dependency (pyarrow/pandas/duckdb stay out), JSON/CSV/SQLite contracts untouched, cron/refresh untouched. Reopen condition recorded in MASTER_PLAN #22. `data/` untouched; suite 17/17 OK from scratch cwd.
- **P2.5 — Benchmark do ranking: medido, NÃO alterado** (11/09; PR #45): `benchmarks/ranking_benchmark_v1.json` (59 vagas reais do run 11/09 rotuladas manualmente: 5 ótima / 22 boa / 15 aceitável / 5 ruim / 12 falso positivo; justificativa + URL por vaga) + análise stdlib reproduzível. **Resultado**: universo 260 eligible (run 11/09/2026) com **96,5% das vagas empatadas** (39 scores distintos; maior grupo 7.5×33); concordância ordinal **82,5%** em 1.289 pares (tau +0,651 — o ranking tem sinal real); **67% das vagas empatadas da amostra em grupos com qualidade humana diferente** (até 3 níveis no mesmo score). **Decisão: Caso C — baixa resolução real**, sem evidência para redesign; hipóteses de calibração (H1 descrição ausente custa 3,0–3,75 pts na mesma vaga; H2 `language` não discrimina — FP 1,33 ≈ ótima 1,40; H3 desempate alfabético arbitrário; H4 FPs = gap de FILTRO, fora do ranking) em `docs/ranking_benchmark.md`. Ferramentas: `scripts/ranking_benchmark.py` (relatório determinístico), `scripts/make_ranking_benchmark.py` (refresh/validate — nunca grava benchmark inválido); `scripts/test_ranking_benchmark.py` no CI (19→20 scripts). Suíte local 20/20 TUDO OK de cwd scratch; `data/` intocada. Nenhum peso/formula/regra alterado.
- **Batch 12–13/09 (PRs #48–#53, merged)**: CI passa a instalar dependências via `pyproject.toml` — sem lista manual nem `--no-deps` (#48); papel do `requirements-lock.txt` documentado como snapshot, não lock declarativo (#49); `test_manifest.py` renomeado para `manifest_probe.py` — probe manual (rede), fora da suíte do CI (#50); `coverage.py` suporta zero vagas elegíveis sem `IndexError` (#51); escopo do registry consolidado 39/60 → 65 + `RegistryEntry.source` removido (#52); detecção de drift entre tenant do registry e tenant resolvido (#53). Com P3 #40 (backup do jobs.db, 13/09) e o README pós-auditoria com a suite 23/23 (#55), fecham a leva P1–P3 desta auditoria.
- **Fase 1 — GitHub Pages + cron 06:00 America/Sao_Paulo** (18/09; PRs #67 + #68; main `d36791c`; CI 24/24 — 1.062 checks): o ranking HTML local ganhou **publicação automática no GitHub Pages** — URL estável **https://rios-vini.github.io/internship-finder/** (repo público, source branch `gh-pages`/root; a branch contém só `index.html`, 472 KB). Fluxo: refresh diário → `scripts/interface.py` (mesmo HTML do uso local) → **`scripts/publish_pages.py`** (novo: gate `check_public_safe`, escrita atômica no clone de deploy `/home/ubuntu/internship-finder-ghpages`, commit+push da `gh-pages`; `--dry-run` para ensaio) → Pages. O refresh ganhou a flag **`--pages-dir`** (default OFF; habilitada no cron): publica só após o run com exit 0 + eligible > 0; falha de deploy não derruba o run (`publish_error` na mensagem Telegram/`run_info.json`) e a página anterior permanece no ar. **Cron**: era `0 6 * * *` UTC (= 03:00 BRT) → **`0 9 * * *` UTC = 06:00 America/Sao_Paulo** (UTC-3 fixo, sem DST no Brasil desde 2019; Vixie 3.0pl1 local **não suporta `CRON_TZ`** — testado com probe; comentário no crontab + README). Watchdogs `*/5` intactos. Segurança: `check_public_safe` + verificação do blob publicado (0 matches de `ghp_|TELEGRAM_BOT_TOKEN|/home/ubuntu|jobs.db`). Documentação: README (seção GitHub Pages + Cron corrigido), `docs/architecture.md`. Testes novos: `scripts/test_publish_pages.py` (28 checks), `test_refresh.py` +16.
- **Fase 2 — Telegram Daily Digest** (18/09; PR #70; CI 25/25 — 1.163 checks): o Telegram virou o **resumo diário do estado da busca** (ranking completo segue no GitHub Pages). Novo `scripts/ranking_digest.py` (funções puras, zero infra nova): compara o ranking do run contra o **snapshot da própria rotação** (`data/archive/<ts>/eligible_jobs.json` — estado anterior já copiado antes da coleta desde o P2 #17; nenhum arquivo/banco novo). Seções anexadas à mensagem única do refresh_daily: perfil/critérios ativos (**pesos lidos das constantes vivas** de ranking.py/filters.py — nada duplicado), **novas vagas no Top 30** (id ausente do ranking elegível anterior; "nova" ≠ "subiu" — vaga antiga que entrou vai para "Entraram no Top 30"), Top 5 atual, mudanças (entradas/saídas + movimentos ≥ 5 posições), link do GitHub Pages (sempre a última linha). Gates: digest só com exit 0; falha ao montar nunca derruba o run; **limite do Telegram (4096 chars)** — run com muitas anomalias preserva a mensagem base e o digest vira 1 linha compacta com o link. **Cron**: linha ganhou `--always-notify` (digest diário todos os dias). Testes: novo `scripts/test_digest.py` no CI (24→25), `test_refresh.py` +2 blocos, e **testes órfãos da Fase 1 registrados** (com fix de fixture em `test_pages_dir_integrado`: type:run gravado DURANTE a coleta fake, como o CLI real — antes o snapshot de linhas zerava o resumo e `publish_ranking` recebia eligible 0). Suíte local 25/25, 1.163 checks, 0 falhas; mensagem real (18/09: 476 vs 414 → 5 novas no Top 30) enviada ao Telegram **ok:true**. [ver MASTER_PLAN Log 18/09]
- **Fase 4 — Segundo perfil Materials Engineering** (19/09; PR #73; main `9ad6bf8`; CI 26/26): o MESMO conjunto elegível é classificado por dois rankings independentes — `src/internship_finder/materials_ranking.py` adiciona `materials_score`/`materials_breakdown` próprios (núcleo de materiais + adjacentes industriais + contexto quality/R&D gated por contexto técnico no título + tipo + local + penalidades de função de negócio no título); `score`/`score_breakdown` do principal INTACTOS (nunca somados); elegibilidade/coleta/dedup inalteradas. Interface (`scripts/interface.py`): seletor de perfil `[Procurement / Supply Chain | Materials Engineering]`, duas tabelas na mesma página reusando o JS da Fase 3 (filtros/ordenação por perfil); `render_html` sem `materials` = página da Fase 3 idêntica. Digest (`ranking_digest.py`): seção "Perfil Materials Engineering" (Top 5 + novas no Top 30 Materials) na mesma mensagem, link continua última linha. Testes: `test_materials_ranking.py` no CI (25→26), interface +22 checks, digest +9; suíte local 26/26. Validação real (run 19/09, 476): mesma quantidade, business intacto por id, Top 30s independentes, vagas de polímero/beschichtung/verfahrenstechnik/bateria no topo, topo do principal cai para #215 no materials; DOM real (jsdom) 25/25 checks; docs em README/architecture/MASTER_PLAN/PROJECT_STATUS + `docs/relatorio_fase4_perfil_materials.md`. [ver MASTER_PLAN Log 19/09]

## Next priorities

- **P1–P3 desta leva: fechados e comprovados (auditoria 14/09)** — não existe defeito técnico conhecido em aberto. O que permanece abaixo é **monitoramento** de itens externos/operacionais (Lidl timeout, gate de versão do `ats-scrapers`) e **decisões futuras de escopo/produto** (P3 #24, próximas ondas de expansão) — não dívida técnica aberta. Expansões concluídas desde então: **65→87→96→101** (ondas 15/09 a 18/09, PRs #59, #62, #65; 18/09 = ondas de cobertura encerradas por decisão do dono).
- **P3 #20/#21/#29/#30/#31 complete** (06/09 - see Completed). Backlog remainders:
  - **P3 #22**: DONE (08/09) — measured, no action (see Completed); reopen if jobs.json > 1GB or read > 10s or data/ > 10GB
  - **P3 #23**: international expansion + more DE companies (39→60→100) — **DONE 08/09** (39→65, 26 validated; 22 rejected with evidence; 65→87 on 15/09+16/09 waves, PR #59; 87→96 on 17/09, PR #62; 96→101 on 18/09, PR #65 — **expansão de cobertura encerrada por decisão do dono em 18/09**) — see MASTER_PLAN #23
  - **P3 #24**: aggregators (LinkedIn/Indeed/Glassdoor) - needs owner scope decision
  - **P3 #25**: simple interface (top jobs, filters, link) — **DONE 08/09**: `scripts/interface.py` (HTML auto-contido, stdlib, zero deps novas) + `scripts/test_interface.py` no CI (array 16→17) — see MASTER_PLAN #25
  - **P3 #37**: health agora agrega por (source, company) — **DONE 08/09** (PR #39): elimina falsos drops em tenants compartilhados (phenom:nan 6 companies; successfactors:jobs 9); run 08/09 pós-fix: 1 alerta (só Lidl); CI 17 scripts. See MASTER_PLAN #37
  - **P3 #40**: backup simples do jobs.db — **DONE 13/09** (PR #54, squash `e07b7e9`): snapshot via backup API do sqlite3 (stdlib) pós-coleta no refresh (`data/backups/jobs-<ts>.db`, artefato standalone sem sidecars WAL), manual via `scripts/backup_db.py`, retenção `--backup-retention-days` (default 14), falha reportada no Telegram sem derrubar o run; `scripts/test_db_backup.py` no CI (22→23); RESTAURAR = `cp data/backups/jobs-<ts>.db data/jobs.db`. See MASTER_PLAN #40
  - **P3 #30**: stays monitored - re-check when upstream releases >=0.4.0 or an install/import failure appears (last check 06/09 19:47 UTC: gate not fired, range kept)
- **P3 #36 (lidl)**: timeout 85s aceito como limitação monitorada — reavaliar quando o ats-scrapers ganhar timeout por fonte ou a Lidl mudar de tenant.
- Full ranked plan (P0–P4, status ✅/⏳): see `MASTER_PLAN.md` (source of truth).

## Known limitations

- Nenhum item abaixo é defeito técnico conhecido em aberto — são limitações documentadas, fatores externos ou itens de monitoramento (comprovado pela auditoria final de 14/09).
- Some Workday tenants do not expose country information clearly enough for the current country filter (documented; nothing fabricated). **Partially mitigated** by the optional `geocoding.py` fallback (OFF by default; +9 Workday DE when enabled; network geocoding only with the flag on).
- **`application_deadline` em tenants SuccessFactors (P1.4, provado por origem — NÃO é bug):** o feed RSS de Google Merchant (`<host>/sitemal.xml`) publica `g:expiration_date` com **um único valor por feed, igual a `data do feed + 30 dias`, aplicado a todas** as vagas (ex.: feed 11/09 → `2026-10-11`). Trata-se de um horizonte de validade gerado pela própria plataforma (a fonte), não de um prazo de candidatura definido pelo empregador. **O valor VEM DA FONTE**: ats-scrapers 0.3.0 só parseia `g:expiration_date` e o adapter deste projeto só mapeia/parseia — nenhuma camada soma +30 dias nem aplica default. Verificado por reprodução em 4 feeds (SAP/Kaufland/ZF/AkzoNobel) e por auditoria de código. Por isso **não se remove** o valor por heurística de `+30 dias`/frequência (um prazo real que coincida com +30 seria apagado); a interface deve tratar esse campo em SuccessFactors como "providenciado pela fonte", não como prazo garantido do empregador.
- Some companies/ATS combinations currently fail or are excluded for documented reasons (Siemens/teamtailor inativo; re-probe pós-release do PR #285 upstream; Mercedes-Benz/ThyssenKrupp/Kärcher/Heraeus/Aurubis/Rheinmetall/Nordex/SEW/Lenze/Beckhoff/Arvato/BLG/Dachser/Bechtle/Jungheinrich/KUKA sem match real no manifest 17/09 — nunca no SEED; BMW entra somente como "BMW AG" desde 16/09 — a consulta "BMW" sozinha continua FP (`join_com:bmw-kuehnert`); Hager Group e Lanxess foram ADICIONADAS ao SEED em 15/09 (coletam OK no ats-scrapers 0.3.0 — "XML malformado" era limitação do pin antigo); Symrise/ifm/Kerkhoff/Efficio seguem bloqueadas pela API join.com 422 (reconfirmado 17/09); GFT: FP icims:gannettfleming (283 vagas EUA) e workable:gft EMPTY; tenant real da GFT é `sf:jobs` jobs.gft.com (0 eligible DE medido 17/09; exigiria nome canônico longo); Rhenus exige fix `URL_SLUG_ATS`+"adp" (medido pós-fix: 3 raw, 0 eligible)).
- **3 falhas recorrentes DOCUMENTADAS e legítimas (continuam no health/refresh de propósito — não silenciar; investigadas 17/09, PR #64)**: Lidl `successfactors:lidlstiftuP2` timeout ×15 runs (feed externo enorme sob demanda); Kuehne+Nagel `cornerstone:kuehne-nagel` NXDOMAIN (empresa válida coletada via phenom:nan); SMA `oracle:fa-exow-saasfaprod1/cx_1` homônimo externo (sem exclusão específica, decisão 17/09).
- Eligible count (current, documented): the daily cron regenerates `data/eligible_jobs.json` (**18/09 run: 476 eligible** — 72,866 raw → 6,635 → 1,411 area → 507 DE, dedup −31, registry 101). Historical figures: 17/09 → 414 (71,735 raw, registry 96), 16/09 → 331 (69,586 raw, registry 87), 14/09 → 257 (60,222 raw), 07/09 → 220 and 06/09 → 222 (the 222→220 drift was documented in the 07/09 update); older numbers in docs (236/232 from the 31/08 snapshot) are historical. The 476 number is the eligible count of the supported ATS/registry universe — **not** an estimate of the entire German market.
- Eligible tail (measured 18/09): **0 formal bachelor-degree titles** (Bachelor of.../Praxisverbund rules since 16/09 — PR #61; SmVdP since 15/09) + **27 academic-thesis titles** (Abschlussarbeit/Bachelor-/Masterarbeit/Thesis — accepted by the 15/09 thesis rule, not a regression); candidates for future pattern extension.

Data in `data/` is local and gitignored: numbers serve as collection documentation, not as versioned files.

See `docs/` for detailed collection, correction and expansion reports (they are historical).
