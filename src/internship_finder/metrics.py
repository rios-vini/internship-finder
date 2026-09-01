"""Metricas de execucao persistidas em JSONL (uma linha por registro).

Nao e um banco de dados: um arquivo de texto append-only, uma linha JSON por
tenant coletado + uma linha de resumo do run. Cada execucao do modo coleta
grava o estado de cada tenant (SUCCESS/EMPTY/TIMEOUT/ERROR/SKIP/NOT_FOUND,
erro, duracao) e o resumo do pipeline (filtered/dedup/eligible), para
auditoria e deteccao de regressao sem depender de stdout.

Formato (JSONL, utf-8, uma linha por registro):

  {"type": "tenant", "run_id": ..., "timestamp": ..., "company": ...,
   "source": ..., "ats": ...,
   "status": "ok|empty|timeout|error|skipped|not_found",
   "collected": int, "error": null|str, "error_code": null|str,
   "duration": float|null}

  {"type": "run", "run_id": ..., "timestamp": ..., "total_collected": int,
   "filtered": int, "eligible": int, "dedup_removed": int}

``error_code`` (P1 #7) e opcional: quando presente, traz o codigo estruturado
de ``internship_finder.errors`` (ex.: ``TIMEOUT``, ``CONNECTION_ERROR``),
acompanhando o ``error`` legivel; ``null`` em estados ok/empty/skipped ou em
registros antigos (append-only, o JSONL existente continua valido).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def utcnow_iso() -> str:
    """Timestamp UTC atual em ISO 8601 (usado como ``run_id``/``timestamp``)."""
    return datetime.now(UTC).isoformat()


def write_metrics(path: Path | str, records: list[dict]) -> None:
    """Append dos ``records`` como JSONL em ``path`` (cria dir/arquivo se preciso).

    Aceita ``Path`` ou ``str``. Nao valida o schema: registros sao dicts
    serializaveis. ``ensure_ascii=False`` preserva caracteres nao-ASCII
    (ex.: nomes em alemao).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_metrics(path: Path | str) -> list[dict]:
    """Le todos os registros JSONL de ``path`` (lista de dicts)."""
    path = Path(path)
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records