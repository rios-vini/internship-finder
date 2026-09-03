# Project Status

Last updated: 2026-09-03

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

## Next priorities

- **P1 #9 (this doc pass)** done; **P2 #11 and P2 #12 done** (see Completed). Next P2 backlog items:
  - **P2 #16**: decouple `test_ranking.py` from the 12/08 snapshot (5 known pre-existing failures — NOT a regression)
  - P2 dedup 2.0 (e.g. cross-source identity, dedup textual evolution)
  - P2 company registry / expanding DE coverage (39→60→100)
  - P2 zero-return + anomaly detection (after history accumulates)
  - P2 #16: decouple `test_ranking.py` from the 12/08 snapshot (5 known pre-existing failures — NOT a regression)
- Full ranked plan (P0–P4, status ✅/⏳): see `MASTER_PLAN.md` (source of truth).

## Known limitations

- Some Workday tenants do not expose country information clearly enough for the current country filter (documented; nothing fabricated). **Partially mitigated** by the optional `geocoding.py` fallback (OFF by default; +9 Workday DE when enabled; network geocoding only with the flag on).
- Some companies/ATS combinations currently fail or are excluded for documented reasons (Hager/Boehringer/Lanxess/Symrise — external limitations from parecer B).
- `scripts/test_ranking.py` reports **5 known pre-existing failures** (P2 #16): its sanity checks are coupled to a 12/08 data snapshot and look for jobs that no longer exist in the current dataset (e.g. "Logistik und Supply Chain Design", "SAP Analytics Cloud"). `ranking.py` has not changed since the MVP — the test breaks on data, not code.
- 7 degree-program titles in the tail (Schaeffler "Studium mit vertiefter Praxis", BASF Bachelor) are pre-existing, outside the approved F1 patterns — candidates for future pattern extension, not a regression.

Data in `data/` is local and gitignored: numbers serve as collection documentation, not as versioned files.

See `docs/` for detailed collection, correction and expansion reports (they are historical).
