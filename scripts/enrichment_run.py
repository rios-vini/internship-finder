#!/usr/bin/env python3
"""Enrichment LLM incremental — runner standalone da camada de enriquecimento.

Fase 2: o enrichment virou INCREMENTAL, automatico e operacionalmente
seguro. Fluxo: planejamento deterministico sobre TODAS as elegiveis
(``new``/``retry``/``seen``) -> fetch sweep de todas (fetch + normalize +
SHA-256) -> ``seen`` identico ao record e sem pendencia = ``cache_hit``
(zero LLM) -> pool ``retry -> new -> changed/changed_source`` (score desc)
com cap de CHAMADAS LLM por run -> extracao GLM-5.3-Flash sequencial ->
upsert atomico (falha nova NUNCA apaga sucesso anterior; conteudo novo
com falha vira ``pending_content_hash`` no record preservado) -> resumo
operacional + status file ``data/enrichment/enrichment_status.json``.
Continua STANDALONE: nenhum modulo do pipeline chama isto; a camada pode
falhar por completo sem afetar coleta, eligibility, dedup, ranking,
Telegram ou publicacao.

Uso:

    .venv/bin/python scripts/enrichment_run.py --dry-run   # plano pre-fetch, SEM rede
    .venv/bin/python scripts/enrichment_run.py              # incremental (precisa NVIDIA_API_KEY no env)
    .venv/bin/python scripts/enrichment_run.py --limit 24   # cap de extracoes LLM do run
    .venv/bin/python scripts/enrichment_run.py --input data/eligible_jobs.json \\
        --output data/enrichment/enrichment_results.jsonl

A key vem EXCLUSIVAMENTE da env var ``NVIDIA_API_KEY`` (nunca em arquivo,
nunca em log). Sem key (exceto ``--dry-run``): mensagem clara + exit 1.
Modelo fixo ``z-ai/glm-5.3-flash`` (o 5.3 queima todo o max_tokens em
raciocinio interno — medido no spike A/B 5/5 falhas; NAO trocar).

Concorrencia (spec secao 14): o modo real adquire flock exclusivo em
``<dir do --output>/.enrichment.lock``; segunda execucao concorrente sai
com exit 3 sem tocar o store. ``--dry-run`` e read-only e nao trava.

Exit codes: 0 = run concluido (falha individual de vaga e dado, nao erro);
1 = erro de setup (input ilegivel, eligible vazio, key ausente, modelo
indisponivel); 2 = nenhuma vaga processada (ex.: pool pendente com
``--limit 0``); 3 = execucao concorrente detectada.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.enrichment import runner  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Camada de enrichment LLM incremental (fetch + GLM-5.3-Flash)"
    )
    parser.add_argument(
        "--limit", type=int, default=runner.DEFAULT_LIMIT,
        help="cap de extracoes LLM deste run (default 24); o backlog "
        "restante fica pendente para o proximo run",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="somente plano pre-fetch (counts new/retry/seen + cap) — SEM rede",
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
        "--sleep-fetch", type=float, default=runner.DEFAULT_SLEEP_FETCH,
        help="pausa em segundos entre fetches do sweep (default 2.0)",
    )
    return parser


def main() -> int:
    return runner.run(build_parser().parse_args())


if __name__ == "__main__":
    sys.exit(main())
