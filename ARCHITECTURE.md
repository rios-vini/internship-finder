# Architecture — Internship Finder

## Purpose

Internship Finder collects internship / working-student job postings from company ATS platforms and produces filtered, deduplicated and ranked opportunities.

## High-level flow

Company
→ company matching
→ ATS identification
→ scraper
→ adapter
→ normalized Job
→ filtering
→ deduplication
→ ranking
→ JSON / CSV output

## Company discovery

Companies are resolved through the `ats-scrapers` company database.

Company matching must be exact when selecting a company to avoid false matches between similarly named companies.

## Collection

The collector identifies the company's ATS and invokes the appropriate scraper.

Scrapers may run as subprocesses with timeouts so that one problematic tenant does not block the complete collection.

Raw collected data is preserved before downstream processing.

## Normalization

ATS-specific responses are converted into the project's normalized `Job` model.

ATS-specific logic should remain inside the appropriate adapter/collector layer.

The rest of the pipeline should operate on the normalized `Job` representation.

## Filtering

Eligibility is determined through the existing filtering cascade.

Current concepts:

- collected: all collected postings
- filtered: postings passing individual filters
- eligible: postings passing the complete eligibility cascade
- deduplicated: eligible postings after duplicate removal
- ranked: deduplicated postings ordered by profile relevance
- best matches: top ranked results

Do not create additional conceptual layers unless there is a concrete architectural reason.

## Deduplication

Current deduplication uses available job identifiers / URLs and company + title + location where applicable.

Do not change deduplication semantics without investigating existing behavior and tests first.

## Ranking

Ranking is applied after eligibility and deduplication.

The ranking produces a score based on the user's target profile.

Ranking should not silently change eligibility rules.

## Output

The current application produces JSON and CSV outputs.

The output layer should consume normalized/processed jobs rather than implementing ATS-specific logic.

## Data fields

A field should represent the actual meaning of its source data.

Important distinctions include:

- `posted_at`: when the job was posted
- `fetched_at`: when the system collected the job
- `application_deadline`: explicit deadline for applications, when available

Do not use one field as a substitute for another.

## Error handling

A failure from one company, ATS tenant or scraper should not unnecessarily prevent collection from other companies.

Existing timeout and subprocess behavior should be preserved unless the task specifically requires changing it.

## Architecture rules

- Keep ATS-specific behavior isolated.
- Keep filtering independent from collection.
- Keep ranking independent from collection.
- Keep normalized job data independent from ATS response formats.
- Prefer existing project abstractions over new ones.
- Avoid speculative abstractions.