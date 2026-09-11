"""Manutencao do benchmark do ranking (P2.5) — build/refresh/validate.

O arquivo versionado ``benchmarks/ranking_benchmark_v1.json`` guarda a parte
HUMANA (rotulos + justificativas) e o congelamento do snapshot (rank, score,
score_breakdown). Esta ferramenta:

- ``refresh``: re-extrai score/breakdown/titulo/empresa/local/url de um
  ``eligible_jobs.json`` novo usando os ids como chave estavel e recomputa as
  posicoes com a chave oficial; rotulos e justificativas ficam intactos;
  vagas que sairam do snapshot sao removidas com aviso. NUNCA grava um
  benchmark invalido (valida antes de escrever).
- ``validate``: confere schema e invariantes (labels validas, soma do
  breakdown == score, ranks == chave oficial de ordenacao, justificativa
  presente em toda vaga) e devolve exit 0/1.

Nao altera pesos nem regras do ranking. Uso:

    .venv/bin/python scripts/make_ranking_benchmark.py validate
    .venv/bin/python scripts/make_ranking_benchmark.py refresh \
        --snapshot data/eligible_jobs.json --run-date 2026-09-12 \
        --output benchmarks/ranking_benchmark_v1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.ranking_benchmark import (  # noqa: E402
    refresh_benchmark,
    validate_benchmark,
)

DEFAULT_BENCHMARK = ROOT / "benchmarks" / "ranking_benchmark_v1.json"
DEFAULT_SNAPSHOT = ROOT / "data" / "eligible_jobs.json"


def _load_json(path: str | Path) -> dict | list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_validate(args) -> int:
    data = _load_json(args.benchmark)
    assert isinstance(data, dict)
    errors = validate_benchmark(data)
    if errors:
        print(f"INVALIDO — {len(errors)} problema(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK — benchmark valido ({len(data['jobs'])} vagas rotuladas).")
    return 0


def cmd_refresh(args) -> int:
    data = _load_json(args.benchmark)
    assert isinstance(data, dict)
    snap = _load_json(args.snapshot)
    assert isinstance(snap, list), "snapshot precisa ser uma lista de vagas"

    new_data, dropped, kept = refresh_benchmark(
        data, snap, run_date=args.run_date, source_file=args.snapshot
    )
    out = Path(args.output)
    out.write_text(json.dumps(new_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK — {len(kept)} vagas mantidas, {len(dropped)} removidas (sumiram do snapshot).")
    if dropped:
        print("  removidas:")
        for i, d in enumerate(dropped, 1):
            print(f"    {i}. {d}")
    print(f"gravado: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_validate = sub.add_parser("validate", help="valida o benchmark versionado")
    p_validate.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK))
    p_validate.set_defaults(func=cmd_validate)
    p_refresh = sub.add_parser("refresh", help="re-extrai score/rank de um snapshot novo (rotulos intactos)")
    p_refresh.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK))
    p_refresh.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    p_refresh.add_argument("--run-date", required=True, help="data do run que gerou o snapshot (ex.: 2026-09-12)")
    p_refresh.add_argument("--output", default=str(DEFAULT_BENCHMARK),
                           help="destino (default: sobrescreve o proprio benchmark)")
    p_refresh.set_defaults(func=cmd_refresh)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())