#!/usr/bin/env python3
"""Backup manual do ``jobs.db`` (P3 — snapshot SQLite via stdlib).

Backup simples e seguro do historico SQLite usando a backup API do sqlite3
(``src/internship_finder/storage/sqlite_backup.py``): snapshot consistente
(mesmo com o banco em uso), artefato standalone ``data/backups/jobs-<ts>.db``
(sem sidecars WAL), escrita atomica e validacao minima (``quick_check``) antes
do nome final. O banco principal nunca e alterado.

Uso:

    .venv/bin/python scripts/backup_db.py                       # data/jobs.db -> data/backups/
    .venv/bin/python scripts/backup_db.py --db PATH             # outro banco
    .venv/bin/python scripts/backup_db.py --retention-days 14   # aplica retencao (apos o backup)
    .venv/bin/python scripts/backup_db.py --dry-run             # mostra o que seria feito, sem tocar em nada

Exit 0 = backup criado (imprime o caminho); 2 = falha com mensagem clara no
stderr. A retencao e OPICIONAL (default 0 = nao apaga nada): no refresh diario
a limpeza roda automaticamente com ``--backup-retention-days`` (default 14) —
aqui, um backup manual nao deve apagar historico por surpresa.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.storage.sqlite_backup import (  # noqa: E402
    BACKUP_DIR_NAME,
    cleanup_backups,
    backup_jobs_db,
)

log = logging.getLogger("backup_db")


def repo_root() -> Path:
    """Raiz do repositorio (este script vive em ``scripts/``)."""
    return Path(__file__).resolve().parents[1]


def _non_negative_int(value: str) -> int:
    """Tipo argparse: inteiro >= 0 (negativo rejeitado com erro claro)."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"valor invalido: {value!r} (esperado inteiro nao negativo)")
    if parsed < 0:
        raise argparse.ArgumentTypeError(
            f"retencao negativa ({parsed}) nao faz sentido; use 0 para desligar")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backup_db.py",
        description="Backup manual do jobs.db (snapshot SQLite via backup API, stdlib).",
    )
    parser.add_argument("--db", default=None, metavar="PATH",
                        help="banco a copiar (default: data/jobs.db na raiz do repo)")
    parser.add_argument("--retention-days", type=_non_negative_int, default=0,
                        metavar="N",
                        help="aplica a retencao de backups apos o snapshot "
                             "(default 0 = nao apaga nada; 14 espelha o refresh)")
    parser.add_argument("--dry-run", action="store_true",
                        help="so calcula e imprime o destino; nao escreve nada")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    root = repo_root()
    db_path = Path(args.db) if args.db else root / "data" / "jobs.db"
    backup_dir = db_path.parent / BACKUP_DIR_NAME

    if args.dry_run:
        print(f"banco:            {db_path}")
        print(f"diretorio backup: {backup_dir}")
        print("(dry-run: nada foi escrito)")
        return 0

    try:
        backup = backup_jobs_db(db_path, backup_dir=backup_dir)
    except Exception as exc:  # noqa: BLE001 — CLI manual reporta e sai
        print(f"ERRO: backup falhou — {type(exc).__name__}: {exc}", file=sys.stderr)
        print("O banco principal nao foi alterado.", file=sys.stderr)
        return 2

    print(f"backup criado: {backup}")
    print(f"tamanho:       {backup.stat().st_size} bytes")

    if args.retention_days:
        removed = cleanup_backups(backup_dir, args.retention_days)
        print(f"retencao ({args.retention_days}d): {len(removed)} backup(s) removido(s)"
              if removed else f"retencao ({args.retention_days}d): nada a remover")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())