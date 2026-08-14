# AGENTS.md — Internship Finder

## Project

Internship Finder is a Python application that collects and ranks internship / working-student opportunities, currently focused on Supply Chain, Procurement, BI, Analytics and Automation, with Germany as the primary target.

The project collects jobs from companies through ATS platforms and processes them through a filtering, deduplication and ranking pipeline.

## Current architecture

The main pipeline is:

Company
→ find_company (exact company matching)
→ ATS
→ scraper
→ adapter
→ Job (Pydantic)
→ output

The filtering pipeline is:

collected
→ filtered
→ eligible
→ deduplicated
→ ranked
→ best matches

Do not introduce new architectural layers unless there is a clear need.

## Development principles

- Prefer the simplest implementation that solves the current problem.
- Do not maintain obsolete compatibility layers.
- Do not add speculative abstractions or configuration.
- Reuse existing dependencies and project utilities before adding new packages.
- Prefer mature, maintained libraries.
- Keep responsibilities separated and components modular.
- Follow existing project patterns before creating new ones.
- Do not rewrite working components without a concrete reason.
- Do not change unrelated functionality while implementing a task.

## Scope control

Before modifying code:

1. Inspect the existing implementation.
2. Identify the smallest set of files that need to change.
3. Check existing tests and related code.
4. Implement only what the task requires.
5. Run the relevant tests.
6. Report any remaining limitations.

## Data integrity

- Never invent job information.
- Preserve source data when possible.
- Distinguish explicitly sourced fields from inferred fields.
- If a source does not provide a value, prefer `None` over fabricating a value.
- Do not infer an application deadline from the posting date unless explicitly required by the task and clearly documented.

## Jobs and internship scope

The project is specifically intended to find internship / working-student opportunities.

Do not broaden the project to ordinary full-time or part-time jobs unless explicitly requested.

## Testing

Every behavior change should have appropriate test coverage.

Prefer targeted tests first, followed by the broader test suite when practical.

Do not remove tests simply to make a change pass.

## Git

Work on a dedicated branch for each meaningful task when the platform supports branches.

Keep commits focused and descriptive.

Do not modify unrelated files.

Do not commit secrets, API keys, `.env` files or credentials.

## Documentation

When an architectural or behavioral decision changes, update the relevant documentation.

Do not duplicate information unnecessarily. Prefer linking to the authoritative document.

## Before finishing a task

Report:

- files changed
- what changed
- tests executed
- test results
- known limitations
- whether the task is fully complete