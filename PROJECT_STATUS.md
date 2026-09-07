# Project Status

Last updated: 2026-09-06

## Current state

The project has a working company-oriented ATS collection pipeline (collection →
filtering → dedup → ranking), with SQLite persistence, structured error codes,
observability (health), CI and standardized requirement tracking in
`MASTER_PLAN.md`.

Current collection scope includes 39 evaluated/operational companies from the E2 expansion.

Latest documented full run (cron 06/09 06:00 UTC; reproduced offline by `scripts/coverage.py` and the current pipeline):

- 37,953 raw jobs
- 3,080 student-type jobs
- 752 target-area jobs
- 246 Germany-eligible jobs after country filter
- 222 eligible/ranked jobs after deduplication (24 removed, company+title+location)
- 24 companies / 20 tenants (source) with eligible jobs
  (SAP 71, BoschGroup 41, Volkswagen AG 20, BASF SE 17, Knorr-Bremse 16, ... — see README coverage table)

ATS (eligible): successfactors 150, smartrecruiters 41, eightfold 11, workday 8, phenom 5, ashby 3, greenhouse 3, cornerstone 1.

Scores (measured 06/09 on the current dataset): min 2.50 | mediana 6.75 | max 16.75 · 222/222 `country_iso='de'`.

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
- **P2 #10 — Zero-return + anomaly detection** (05/09): 3rd alert type in `health.py` (`_detect_zero_return`): a source whose most recent run (by `run_id`) is `empty` after ≥3 prior `ok` runs with jobs (`collected > 0`) → coverage regression; empty-consistent sources (`bamboohr:sap`, `smartrecruiters:sap`) never alert (anti-tests); gate mirrors the drop's spirit (1–2 oks = plausible fluctuation). `build_health_report` now emits drop + recurring_error + zero_return; `scripts/refresh_daily.py` formats it ("voltou a zero (empty) após N runs com vagas") — Telegram flows unchanged (anti-spam intact). Calibrated on the real history (4 runs): **0 zero-return alerts** (no source with ok>0 and empty — clean baseline); live health stays at the 1 factual alert. `scripts/test_zero_return.py` (offline, 20 checks) added to the CI array (now 15 scripts); suite 16/16 local; `data/` untouched (stat before==after).
- **P2 #17 — Daily refresh + alerts** (05/09): `scripts/refresh_daily.py` runs the real collection (`--registry --timeout 60`) daily with rotation of `data/` outputs into `data/archive/<ts>/` **before** the run (rollback = copy back), evaluates health via the existing `build_health_report` on the updated JSONL, and sends a Telegram alert **only on anomaly** (exit != 0 or drop/recurring-error alerts; 1 message per run, alerts deduped by source; `--always-notify` = optional daily digest; no token in `.env` → warning, no send, never crashes). `--dry-run` validates rotation+health+message in a synthetic tempdir without network or `data/` writes. Cron installed (05/09, 06:00 UTC, `flock -n` guard covering the whole run — absolute paths, corrected the same night after `flock ... cd ... &&` proved broken: flock execs via `execvp` and `cd` is a shell builtin; backups in `/tmp/crontab_backup_0509.txt` and `/tmp/crontab_backup_0509_v2.txt`). Tested offline (`scripts/test_refresh.py`, in CI — array now 14 scripts) and with one authorized real run: `2026-09-05T20:43:07` → 38.038 raw → 248 filtered → **224 eligible** (dedup −24), 43 ok / 2 empty / 1 timeout / 1 error tenants, health found the known `smartrecruiters:other` anomaly (70 runs) + a new real one (`successfactors:lidlstiftuP2`), Telegram answered `ok:true` (message_id 318). Rollback documented in README "Daily refresh". The metrics JSONL was sanitized the same night (05/09): only the 4 real runs' records kept (37.373 / 1.084 ×2 / 38.038 → 104 lines, 39 companies), removing mock junk (`smartrecruiters:other` 70×, `successfactors:acme` 140×); post-clean health shows one factual alert (`successfactors:lidlstiftuP2` — timeout 31/08 + 05/09).

- **P3 #20 — ACH validations, measured first** (06/09): (ACH-18) CSV contract decided — **JSON = complete source, CSV = tabular view**; `remote` column added to `CSV_COLUMNS` (was absent in 38.038/38.038 `jobs.csv` rows and 224/224 eligible rows; `description`/`raw`/`score_breakdown` intentionally stay CSV-out); (ACH-14) `--limit` semantics confirmed post-fetch per tenant (limit=2 → 2/tenant via mock) and the CLI now rejects `--timeout <= 0` / `--limit < 0` with a clear exit-2 error before collection (undefined behavior before: deadline=only margin, `[:-k]` slice); new offline `scripts/test_collect_flags.py` (19 checks) in CI (array 15→16); (ACH-16) `remote` field never populated by any ATS (0/38.038) — filter works via location text (101 markers, 1 remote-eligible), documented no-op; (ACH-17) country vs country_iso 0/38.038 mismatches (same inferred value by adapter construction), measured no-op; (ACH-20) 0 dates in DD.MM.YYYY anywhere (eligible + raw) — "no measured need", no parser; (ACH-19) BY removed from `EUROPE_COUNTRIES` (code contradicted the documented "RU/BY out" rule; 0 real `by` jobs). Local suite 17/17 TUDO OK from scratch cwd; `data/` untouched (stat before==after); funnel reproduced 38.038→224 identical.
- **P3 #21 — Dead code (ACH-13), reference audit** (06/09): every public symbol in `src/` (73 across 17 modules) and every non-test script was grep-audited repo-wide (src/, scripts/, .github/, docs, README, AGENTS — word-boundary) plus a pyflakes pass (throwaway /tmp venv, project venv untouched). No public symbol ended with 0 references — the minimum was `Score.to_dict` (0 call sites; real serialization is `d["score"] = score.total` / `score_breakdown`). Removed 16 zero-reference items, all behavior-neutral: `Score.to_dict`; unused `import json` in `health.py`; 4 dead re-export names in `filters.py` (`EUROPE_COUNTRIES`, `COUNTRY_NAMES`, `_country_name_from_location`, `_iso_token_from_location` — consumers import from `countries`; `COUNTRY_CODES`/`is_remote` kept, exercised by `test_compat_re_export`); unused imports/locals in 6 test files + `refresh_daily.py` (including `keys_w = dict(candidate_keys_for_audit := {})` walrus junk in test_dedup). Deliberate `# noqa: F401` imports kept (author intent); `CompanyResolver`/`company_status` kept (tested + documented public APIs); `__version__` kept (package convention). CI array unchanged (16); local suite 17/17 TUDO OK before and after from scratch cwd; `data/` untouched (stat before==after). Observation: README states `company_status` is "exposed by `--health`" but `cli.py` does not call it (doc≠code, out of scope).

- **P3 #31 — Corrections batch** (PR #31, merged 06/09, main `c2fcfb2`): Apprentice/Apprenticeship (EN learning programs) excluded like the DE Ausbildung rule (2 real VW jobs left eligible); `trainee` removed from `STUDENT_EMPLOYMENT_TYPES` (generic trainee no longer passes on `employment_type` alone; 0 jobs affected, measured); `read_metrics` skips malformed JSONL lines instead of crashing; `company_status` orders by `(run_id, timestamp)` instead of file position; `--health` now exposes `company_status` under the `companies` key (doc minus code gap closed). Funnel measured: 37,953 -> 3,080 -> 752 -> 246 -> **222** (before the fix: 248 -> 224). Suite 17/17 OK before/after; `data/` untouched.
- **P3 #30 — Operations batch** (PR #30, merged 06/09, main `d0a3ea1`): daily refresh now collects with `--sqlite data/jobs.db` (first_seen/last_seen/active/archived persisted in production; the `.db` is not rotated); archive cleanup with `--retention-days` (default 14, 0 = off, runs after each rotation); disk usage >80% adds a "⚠️ Disco: N% usado" line to the Telegram message; collection subprocess inherits the caller env; `requirements-lock.txt` added (reproducibility, outside CI). `test_refresh` 43->60 asserts; suite 17/17; `data/` untouched.
- **P2 #29 — Docs consolidation** (PR #29, merged 06/09, main `9477339`): P1 #5 SQLite registered as implemented (documental drift fixed) + P3 #30 gate checks 15:01 and 19:47 UTC (path B - gate not fired, PyPI still 0.3.0), both recorded in MASTER_PLAN log.

## Next priorities

- **P3 #20/#21/#29/#30/#31 complete** (06/09 - see Completed). Backlog remainders:
  - **P3 #22**: data/code separation + Parquet when volume justifies (archive now auto-cleaned - see #30)
  - **P3 #23**: international expansion + more DE companies (39→60→100) - needs owner scope decision
  - **P3 #24**: aggregators (LinkedIn/Indeed/Glassdoor) - needs owner scope decision
  - **P3 #25**: simple interface (top jobs, filters, link) - SQLite is now fed by the daily refresh (prerequisite ready)
  - **P3 #30**: stays monitored - re-check when upstream releases >=0.4.0 or an install/import failure appears (last check 06/09 19:47 UTC: gate not fired, range kept)
- Full ranked plan (P0–P4, status ✅/⏳): see `MASTER_PLAN.md` (source of truth).

## Known limitations

- Some Workday tenants do not expose country information clearly enough for the current country filter (documented; nothing fabricated). **Partially mitigated** by the optional `geocoding.py` fallback (OFF by default; +9 Workday DE when enabled; network geocoding only with the flag on).
- Some companies/ATS combinations currently fail or are excluded for documented reasons (Hager/Boehringer/Lanxess/Symrise — external limitations from parecer B).
- Eligible count (current, documented): the daily cron regenerates `data/eligible_jobs.json` (06/09 run: **222** eligible). Older numbers in docs (236/232 from the 31/08 snapshot) are historical; the pipeline output over the current snapshot with the current code is the source of truth (**222**).
- 7 degree-program titles in the tail (Schaeffler "Studium mit vertiefter Praxis", BASF Bachelor) are pre-existing, outside the approved F1 patterns — candidates for future pattern extension, not a regression.

Data in `data/` is local and gitignored: numbers serve as collection documentation, not as versioned files.

See `docs/` for detailed collection, correction and expansion reports (they are historical).
