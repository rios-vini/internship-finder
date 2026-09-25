#!/usr/bin/env python3
"""Enrichment LLM isolado — runner standalone da camada de enriquecimento.

Primeira versao permanente da camada de enrichment por LLM (spec da fase,
baseada no spike 24/09): selecao deterministica de amostra do ranking
elegivel -> fetch da pagina oficial -> normalizacao HTML->texto ->
extracao GLM-5.3-Flash (JSON estruturado com evidencias) -> record
validado (pydantic) -> JSONL persistente com escrita atomica e upsert
incremental. Ferramenta STANDALONE: nenhum modulo do pipeline chama isto;
a camada pode falhar por completo sem afetar coleta, eligibility, dedup,
ranking, Telegram ou publicacao.

Uso:

    .venv/bin/python scripts/enrichment_run.py --dry-run   # plano da amostra, SEM rede
    .venv/bin/python scripts/enrichment_run.py              # carga real (precisa NVIDIA_API_KEY no env)
    .venv/bin/python scripts/enrichment_run.py --top 16 --extra-wa 4 --extra-nodesc 4
    .venv/bin/python scripts/enrichment_run.py --limit 5   # teto de vagas do run
    .venv/bin/python scripts/enrichment_run.py --input data/eligible_jobs.json \\
        --output data/enrichment/enrichment_results.jsonl

A key vem EXCLUSIVAMENTE da env var ``NVIDIA_API_KEY`` (nunca em arquivo,
nunca em log). Sem key (exceto ``--dry-run``): mensagem clara + exit 1.
Modelo fixo ``z-ai/glm-5.3-flash`` (o 5.3 queima todo o max_tokens em
raciocinio interno — medido no spike A/B 5/5 falhas; NAO trocar).

Exit codes: 0 = run concluido (falha individual de vaga e dado, nao erro);
1 = erro de setup (input ilegivel, amostra vazia, key ausente, modelo
indisponivel); 2 = nenhuma vaga processada.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.enrichment import runner  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Camada de enrichment LLM isolada (fetch + GLM-5.3-Flash)"
    )
    parser.add_argument(
        "--top", type=int, default=16,
        help="top N do ranking (score desc, id desc) na amostra (default 16)",
    )
    parser.add_argument(
        "--extra-wa", type=int, default=4,
        help="extras fora do top com work authorization no feed (default 4)",
    )
    parser.add_argument(
        "--extra-nodesc", type=int, default=4,
        help="extras fora do top sem description no feed (default 4)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="teto de vagas processadas neste run (default: sem teto)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="somente selecao + store + plano impresso — SEM rede nenhuma",
    )
    parser.add_argument(
        "--input", default="data/eligible_jobs.json",
        help="ranking elegivel de entrada (default data/eligible_jobs.json)",
    )
    parser.add_argument(
        "--output", default="data/enrichment/enrichment_results.jsonl",
        help="JSONL de records (default data/enrichment/enrichment_results.jsonl)",
    )
    parser.add_argument(
        "--sleep-fetch", type=float, default=2.0,
        help="pausa em segundos entre fetches (default 2.0)",
    )
    return parser


def main() -> int:
    return runner.run(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
