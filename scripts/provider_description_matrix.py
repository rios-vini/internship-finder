#!/usr/bin/env python3
"""F75 — Matriz provider×descrição: cobertura de description por ATS provider.

Relatório OFFLINE (padrão F45/funnel_report): determinístico, zero HTTP,
zero LLM, stdout + exit-code, SÓ LÊ — nunca escreve em ``data/``.

O QUE MEDE (spec F75 item 1, prioridade P2 "Qualidade/expansão"): sobre o
ELEGÍVEL publicado (default ``data/eligible_jobs.json``), por ATS
PROVIDER (o ATS efetivo do ``source`` — MESMA regra da hidratação:
``hydration._effective_ats``; ``sf_dataset:successfactors`` ->
``successfactors``, ``direct:eures`` -> ``eures``, ``ats:slug`` ->
``ats``, resto -> o próprio source):

- ``vagas``    — quantas vagas do elegível vêm daquele provider;
- ``c/desc``   — com ``description`` não-vazia (presença);
- ``cobertura`` — % de presença (c/desc sobre vagas);
- ``mediana``  — mediana do comprimento (chars) das descriptions PRESENTES
  (qualidade: teaser de ~200 chars é outra vaga que descrição plena);
- ``curtas``   — descriptions presentes com < SHORT_DESCRIPTION_LIMIT
  chars (régua do refresh: ``HYDRATION_SHORT_LIMIT`` — hidratação F11
  considera "texto curto" abaixo disso; PINADA em teste, padrão F62);
- ``fontes``   — breakdown de ``description_source`` (feed/hydration/…):
  DE ONDE vem a descrição daquele provider, não só se existe.

PARA QUÊ (decisões que a matriz informa): expansão de país/ATS (um
provider com 0% de descrição rankeia só por título — bundesagentur na
F3), prioridade de hidratação (curtas) e saúde do feed por ATS.

Uso::

    python scripts/provider_description_matrix.py
    python scripts/provider_description_matrix.py --input data/eligible_jobs.json
    python scripts/provider_description_matrix.py --input ... --json

Exit: 0 = relatório com dados; 1 = nenhuma vaga legível (nada a medir).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_SRC = _SCRIPTS.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ATS efetivo do source — MESMA regra da hidratação (uma fonte de
# verdade; F3/F4: prefixo ``sf_dataset:``/``direct:`` é marcador de
# FONTE, o sufixo é o ATS).
from internship_finder.hydration import _effective_ats  # noqa: E402

DEFAULT_ELIGIBLE = "data/eligible_jobs.json"

# Régua de "descrição curta" (teaser): o MESMO corte que o refresh usa
# para decidir hidratar (HYDRATION_SHORT_LIMIT). Sincronia PINADA em
# teste (padrão F62 do IMMEDIATE_LABEL): se um lado mudar a régua, o
# test_f75 acusa antes das duas medidas divergirem em silêncio.
SHORT_DESCRIPTION_LIMIT = 500


def load_jobs(eligible_path: str | Path) -> list[dict]:
    """Vagas do ranking (tolerante: lista JSON de dicts; formato ruim = [])."""
    path = Path(eligible_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return [j for j in data if isinstance(j, dict)]
    return []


def _description_text(job: dict) -> str:
    """Description da vaga como texto (ausente/não-str = vazia)."""
    value = job.get("description")
    return value.strip() if isinstance(value, str) else ""


def provider_of(job: dict) -> str:
    """ATS provider efetivo (``_effective_ats`` da hidratação; nunca lança)."""
    try:
        return _effective_ats(str(job.get("source") or "")) or "?"
    except Exception:  # noqa: BLE001 — vaga sem source legível
        return "?"


def matrix_rows(jobs: list[dict]) -> list[dict]:
    """Matriz provider×descrição sobre o elegível — uma linha por provider.

    Pura e determinística: mesma entrada, mesma saída (ordem por vagas
    desc, depois nome asc — o maior provider primeiro, ties estáveis).
    """
    by_provider: dict[str, list[dict]] = {}
    for job in jobs:
        by_provider.setdefault(provider_of(job), []).append(job)

    rows: list[dict] = []
    for provider in sorted(by_provider):
        group = by_provider[provider]
        texts = [_description_text(j) for j in group]
        present = [t for t in texts if t]
        lengths = [len(t) for t in present]
        sources = Counter(
            str(j.get("description_source") or "?")
            for j in group if _description_text(j))
        rows.append({
            "provider": provider,
            "jobs": len(group),
            "with_description": len(present),
            "coverage_pct": round(100.0 * len(present) / len(group), 1)
            if group else 0.0,
            "median_chars": int(statistics.median(lengths))
            if lengths else None,
            "short": sum(1 for n in lengths if n < SHORT_DESCRIPTION_LIMIT),
            "description_sources": dict(sources),
        })
    rows.sort(key=lambda r: (-r["jobs"], r["provider"]))
    return rows


def format_matrix(rows: list[dict]) -> list[str]:
    """Linhas de texto do relatório (stdout). Pura sobre ``rows``."""
    lines = ["== Matriz provider×descrição (F75) =="]
    if not rows:
        lines.append("(sem vagas legíveis)")
        return lines
    total_jobs = sum(r["jobs"] for r in rows)
    total_desc = sum(r["with_description"] for r in rows)
    lines.append(f"elegível: {total_jobs} vagas · {len(rows)} providers · "
                 f"cobertura global {100.0 * total_desc / total_jobs:.1f}% "
                 f"({total_desc}/{total_jobs})")
    lines.append(f"régua de 'curta': < {SHORT_DESCRIPTION_LIMIT} chars "
                 "(mesma do refresh/HYDRATION_SHORT_LIMIT)")
    lines.append("")
    header = (f"{'provider':<18} {'vagas':>6} {'c/desc':>7} {'cobertura':>9} "
              f"{'mediana':>8} {'curtas':>7}")
    lines.append(header)
    lines.append("-" * len(header))
    for row in rows:
        median = "—" if row["median_chars"] is None else str(row["median_chars"])
        lines.append(
            f"{row['provider']:<18} {row['jobs']:>6} "
            f"{row['with_description']:>7} {row['coverage_pct']:>8.1f}% "
            f"{median:>8} {row['short']:>7}"
        )
    lines.append("")
    lines.append("fontes de description (provenance) por provider:")
    for row in rows:
        if row["description_sources"]:
            parts = " · ".join(f"{k}: {v}" for k, v in
                               sorted(row["description_sources"].items(),
                                      key=lambda kv: -kv[1]))
            lines.append(f"  {row['provider']}: {parts}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Matriz provider×descrição: cobertura e qualidade da "
                    "description por ATS provider sobre o elegível "
                    "(offline, determinístico; padrão F45).")
    parser.add_argument("--input", default=DEFAULT_ELIGIBLE,
                        help=f"ranking vivo (default: {DEFAULT_ELIGIBLE})")
    parser.add_argument("--json", action="store_true",
                        help="saída estruturada (1 objeto JSON)")
    args = parser.parse_args(argv)

    jobs = load_jobs(args.input)
    rows = matrix_rows(jobs)
    if not rows:
        print("matriz: nenhuma vaga legível (arquivo ausente/vazio?)")
        return 1
    if args.json:
        print(json.dumps({
            "input": str(Path(args.input)),
            "short_description_limit": SHORT_DESCRIPTION_LIMIT,
            "total_jobs": sum(r["jobs"] for r in rows),
            "providers": rows,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print("\n".join(format_matrix(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
