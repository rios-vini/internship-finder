# Project Status

Last updated: 2026-08-13

## Current state

The project has a working company-oriented ATS collection pipeline.

Current collection scope includes 39 evaluated/operational companies from the latest E2 expansion.

Latest documented full run:

- 56,810 raw jobs
- 4,995 student-type jobs
- 914 target-area jobs
- 406 Germany-eligible jobs before deduplication
- 389 eligible/ranked jobs after deduplication
- 18 companies with eligible jobs

The current pipeline and results are documented in the README and existing `docs/` reports.

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

- Some Workday tenants do not expose country information clearly enough for the current country filter.
- Some companies/ATS combinations currently fail or are excluded for documented reasons.
- Application deadlines are not yet represented as a normalized field.

See the existing documentation under `docs/` for detailed collection and expansion reports.

## Next priorities

1. P0 — Application deadline tracking
2. Improve coverage of useful international internship sources
3. Address important data-quality limitations identified during collection
4. Continue improving ranking only when evidence shows it is needed