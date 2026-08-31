# Project Status

Last updated: 2026-08-13

## Current state

The project has a working company-oriented ATS collection pipeline.

Current collection scope includes 39 evaluated/operational companies from the latest E2 expansion.

Latest documented full run (after corrections F1–F3, see `docs/relatorio_final_pos_correcoes.md`):

- 56,810 raw jobs
- 3,428 student-type jobs
- 777 target-area jobs
- 309 Germany-eligible jobs after country filter
- 293 eligible/ranked jobs after deduplication
- 20 companies with eligible jobs (SAP 91, Lidl 48, Bosch 39, VW 25, Knorr 18, BASF 18, Schaeffler 12, and 13 more)

Scores: min 2.00 | median 6.00 | max 16.00 · 293/293 `country_iso='de'`.

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
- Post-audit corrections F1–F3 (parecer A, 2026-08-13):
  - F1 type-noise: `TYPE_EXCLUSION_PATTERNS` (Duales Studium/Ausbildung/Schülerpraktikum/FSJ-BFD excluded; 389 → 283 eligible)
  - F2 Phenom/DHL country: `COUNTRY_NAMES` + `_country_name_from_location` (283 → 293; DHL 0 → 4; 496 fake ISO codes corrected)
  - F3 Workday: `_iso_token_from_location` (2-letter token only in reliable position; 168 fake ISOs eliminated; Workday limitation documented — API does not expose country)
  - Final verdict: **parecer A** — dataset of 293 correctly represents "eligible"; Top 20 identical to baseline (13A/5B/1C/1D); suite 7/7 green; deterministic

## High priority

### P0 — Application deadline tracking

Goal:

Add explicit application deadline information to jobs whenever the source provides it.

Requirements:

- Investigate which current ATS sources expose application deadlines.
- Determine where the deadline exists in each relevant raw response.
- Add a normalized `application_deadline` field to `Job`.
- Preserve `None` when the source does not provide an explicit deadline.
- Update affected adapters/collectors.
- Update JSON/CSV output.
- Add tests.
- Do not infer a deadline from `posted_at`.
- Do not fabricate deadlines.

First step:

Analyze the current ATS sources and determine the exact implementation required before modifying production code.

## Known limitations

- Some Workday tenants do not expose country information clearly enough for the current country filter (documented; nothing fabricated).
- Some companies/ATS combinations currently fail or are excluded for documented reasons (Hager/Boehringer/Lanxess/Symrise — external limitations from parecer B).
- Application deadlines are not yet represented as a normalized field.
- 7 degree-program titles in the tail (Schaeffler "Studium mit vertiefter Praxis", BASF Bachelor) are pre-existing, outside the approved F1 patterns — candidates for future pattern extension, not a regression.

See the existing documentation under `docs/` for detailed collection, correction and expansion reports.

## Next priorities

1. P0 — Application deadline tracking (backlog `55b78b63`; first step: analyze ATS sources)
2. Improve coverage of useful international internship sources
3. Address important data-quality limitations identified during collection
4. Continue improving ranking only when evidence shows it is needed

> SQLite persistence + active/expired status (backlog `aa5996fe`): **desbloqueado pelo
> dono em 2026-08-31** — entra no MASTER_PLAN como P1 #5 (schema via `sqlite3` stdlib,
> `application_deadline` + first_seen/last_seen/active).
