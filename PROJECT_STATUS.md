# Project Status

Last updated: 2026-09-04

## Current state

The project has a working company-oriented ATS collection pipeline (collection →
filtering → dedup → ranking), with SQLite persistence, structured error codes,
observability (health), CI and standardized requirement tracking in
`MASTER_PLAN.md`.

Current collection scope includes 39 evaluated/operational companies from the E2 expansion.

Latest documented full run (collection of 31/08, reproduced offline by `scripts/coverage.py`):

- 37,373 raw jobs
- 2,982 student-type jobs
- 754 target-area jobs
- 258 Germany-eligible jobs after country filter
- 236 eligible/ranked jobs after deduplication (22 removed)
- 19 companies / 14 tenants (source) with eligible jobs
  (SAP 84, BoschGroup 40, Volkswagen AG 26, Knorr-Bremse 18, BASF SE 15, Bayer 8, Schaeffler 8, Infineon 7, B. Braun 6, Telekom Growthhub 4, Brose 4, careers.dhl.com 4, Uniper 2, Kaufland 2, ZF 2, MAHLE 2, celonis 2, henkel 1, KraussMaffei 1)

ATS (eligible): successfactors 175, smartrecruiters 40, eightfold 14, phenom 4, greenhouse 2, cornerstone 1.

Scores (measured by `scripts/test_ranking.py` on the current dataset): min 2.00 | mediana 6.38 | max 16.75 · 236/236 `country_iso='de'`.

With `INTERNSHIP_FINDER_GEOCODING=1` (Workday fallback, OFF by default): 245 eligible (+9 Workday DE).

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
- JSON output
- CSV output
- E2 company expansion
- Current 39-company collection scope
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
- **P2 #13 — Company Registry operacional** (PR #20, merged 04/09, main `e7604db`, CI run `33840628495` green): `src/internship_finder/registry.py` is the single source of truth for the 39 collection companies in code (canonical name + reference ATS/tenant + `enabled`); `--registry` CLI flag collects the ENABLED entries (`--registry --companies "Bosch,SAP"` restricts to a subset, order preserved; plain `--companies` still works); per-company status is derived from the metrics JSONL via `company_status` (read-only, malformed records never crash) — design decision: **registry = configuration, JSONL = status**; `test_registry.py` added to CI (array now 13 scripts); README gained a "Registry de empresas" section.
- **P2 #15 — `--country` standardized and validated** (05/09): `parse_country_spec` now raises `ValueError` for non-ISO tokens or an empty spec (e.g. `de,xx`, `,`); the CLI converts it to `parser.error` (clear message, exit 2) before reading input/collecting. Previously an invalid value silently produced 0 jobs (`--country xx`) or ignored bad tokens (`de,xx`). Filter behavior unchanged for valid specs: baseline `--country de` → 232 identical ids (list-by-list); `europe` 371 / `all` 31006 / `remote` 1 unchanged. `test_countries.py` +21 checks (spec validation + CLI error block); suite 14/14, `data/` untouched.

## Next priorities

- **P2 #11, #12, #13, #14, #15 and #16 are done** (see Completed). Next P2 backlog items:
  - **P2 #17**: daily refresh + alerts (Telegram?); after health check — detection first, notification later
  - **P2 #10**: zero-return + anomaly detection — gate: ≥5 completed collection runs (history today: 1 full run 31/08 + targeted validations)
- Full ranked plan (P0–P4, status ✅/⏳): see `MASTER_PLAN.md` (source of truth).

## Known limitations

- Some Workday tenants do not expose country information clearly enough for the current country filter (documented; nothing fabricated). **Partially mitigated** by the optional `geocoding.py` fallback (OFF by default; +9 Workday DE when enabled; network geocoding only with the flag on).
- Some companies/ATS combinations currently fail or are excluded for documented reasons (Hager/Boehringer/Lanxess/Symrise — external limitations from parecer B).
- Eligible count drift (known, documented): the snapshot in `data/eligible_jobs.json` (collection 31/08) = **236**; the current pipeline with dedup 2.0 (P2 #14) = **232** (4 TRUE duplicates removed by company+title+location — see MASTER_PLAN #14). Snapshot vs pipeline are not comparable 1:1 without re-running collection.
- 7 degree-program titles in the tail (Schaeffler "Studium mit vertiefter Praxis", BASF Bachelor) are pre-existing, outside the approved F1 patterns — candidates for future pattern extension, not a regression.

Data in `data/` is local and gitignored: numbers serve as collection documentation, not as versioned files.

See `docs/` for detailed collection, correction and expansion reports (they are historical).
