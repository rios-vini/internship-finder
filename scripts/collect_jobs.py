#!/usr/bin/env python3
"""Atalho para rodar o CLI sem instalar o pacote:

    python scripts/collect_jobs.py --companies "Bosch,SAP" --output data/jobs.json

A implementacao real do CLI esta em ``src/internship_finder/cli.py`` (entry
point ``internship-finder`` do pyproject.toml).
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from internship_finder.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
