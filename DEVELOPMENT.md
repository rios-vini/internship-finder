# Development Guide

## Requirements

- Python >= 3.12
- Git
- Virtual environment recommended

The project has been tested with Python 3.12, 3.13 and 3.14.

## Setup

Create the virtual environment:

    python3 -m venv .venv

Install the project:

    .venv/bin/pip install -e .

## Running

Run the default filtering pipeline:

    .venv/bin/internship-finder

Collect jobs for specific companies:

    .venv/bin/internship-finder --companies "Bosch,SAP"

The repository README contains the current full collection command and available CLI flags.

## Tests

Before changing test commands, inspect `pyproject.toml` and the existing test structure.

Run the project's existing test suite using the currently configured test runner.

For a focused change, run the most relevant tests first.

## Code quality

Use the tools already configured by the project.

Do not add a new formatter, linter or test framework unless there is a concrete need.

## Development workflow

1. Read `AGENTS.md`.
2. Read the relevant architecture documentation.
3. Inspect the existing implementation.
4. Identify affected files.
5. Implement the smallest complete change.
6. Add or update tests.
7. Run relevant tests.
8. Run the broader test suite when appropriate.
9. Review the diff for unrelated changes.
10. Report the result.

## Git workflow

Use focused branches and commits for meaningful tasks.

Do not mix unrelated features in the same commit.

Do not commit:

- API keys
- passwords
- `.env` files
- credentials
- local virtual environments
- generated files unless they are intentionally tracked project artifacts

## Generated data

Before modifying generated data files, determine whether they are intentionally version-controlled and whether the task actually requires updating them.

Do not regenerate large datasets unnecessarily.

## Important rule

Do not assume that an existing dependency lacks functionality.

Inspect the installed dependency and current project usage before adding a package or implementing replacement functionality.