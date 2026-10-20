#!/usr/bin/env python3
"""Drill VIVO de restauracao do jobs.db (F79, opcional B) — manual/watchdog.

"Backup so e backup se restaura." O scripts/test_f79.py prova o ciclo
OFFLINE no CI (fixture pequena em tmp); este script e o ensaio VIVO do
backup REAL mais recente (data/backups/jobs-<ts>.db): copia o backup para
um workdir temporario, abre a COPIA read-only e afirma o que o drill
manual de 19/10 provou — quick_check ok, rows > 0, schema de 21 colunas
== esperado, abre em segundos — comparando com o banco VIVO (read-only)
quando presente.

CONTRATO DE EXECUCAO (F79): manual/watchdog, FORA do CI (o nome nao casa
com o glob test_*.py do scripts/ci_discover_tests.py — mesmo precedente
do manifest_probe.py) e NUNCA no caminho do cron: o cron de producao
(09:00 UTC) nao conhece este script; adiciona-lo a crontab exige ordem
explicita do dono.

Seguranca (o drill nunca e o desastre):
- banco vivo e backups sao abertos SOMENTE read-only (file:...?mode=ro);
- NENHUMA escrita em data/ (backups incluidos): o "restore" e uma COPIA
  para o workdir (--workdir; default temporario sob /tmp, removido ao
  final a menos que --keep);
- restaurar "por cima" do banco vivo e operacao humana consciente com
  parada de cron — este drill JAMAIS escreve no banco vivo;
- backups sao artefatos atomicos (os.replace no sqlite_backup): o mais
  recente nunca esta "pela metade" — seguro rodar a qualquer hora.

Uso:

    .venv/bin/python scripts/drill_restore.py
    .venv/bin/python scripts/drill_restore.py --json    # + linha maquina no final
    .venv/bin/python scripts/drill_restore.py --keep     # preserva o workdir
    .venv/bin/python scripts/drill_restore.py --backups-dir data/backups --live-db data/jobs.db

Exit 0 = drill OK (o backup restaura); 2 = nenhum backup encontrado;
3 = drill FALHOU (quick_check/rows/schema/timeout/ilegivel);
1 = erro inesperado.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.storage.sqlite_backup import (  # noqa: E402
    BACKUP_DIR_NAME,
    _parse_backup_ts,
)
from internship_finder.storage.sqlite_store import (  # noqa: E402
    JOB_COLUMNS,
    LIFECYCLE_COLUMNS,
)

# Mesma derivacao do test_f79: schema esperado vem das constantes DO CODIGO.
EXPECTED_COLUMNS = ["id", *JOB_COLUMNS, *LIFECYCLE_COLUMNS]

# Generoso por design: o drill manual copiou + abriu 706 MB em ~7s. O
# temporizador existe para apanhar hang/lock patologico, nao para medir.
DEFAULT_MAX_SECONDS = 600.0


def repo_root() -> Path:
    """Raiz do repositorio (este script vive em scripts/)."""
    return Path(__file__).resolve().parents[1]


def _most_recent_backup(backups_dir: Path) -> Path | None:
    """Backup mais recente por timestamp do nome (formato travado no modulo)."""
    if not backups_dir.is_dir():
        return None
    best: tuple[datetime, Path] | None = None
    for child in sorted(backups_dir.iterdir()):
        if not child.is_file():
            continue
        ts = _parse_backup_ts(child.name)
        if ts is None:
            continue
        if best is None or ts > best[0]:
            best = (ts, child)
    return best[1] if best else None


def _connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _columns(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(jobs)")]


def _human_size(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB" if n >= 1024 * 1024 else f"{n} B"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="drill_restore.py",
        description="Drill vivo de restauracao (F79): backup real mais "
                    "recente -> copia read-only -> quick_check/rows/schema.",
    )
    root = repo_root()
    parser.add_argument("--backups-dir",
                        default=str(root / "data" / BACKUP_DIR_NAME),
                        help="diretorio dos backups (default: data/backups)")
    parser.add_argument("--live-db", default=str(root / "data" / "jobs.db"),
                        help="banco vivo p/ comparacao read-only (default: data/jobs.db)")
    parser.add_argument("--workdir", default=None,
                        help="destino da copia restaurada (default: temporario sob /tmp)")
    parser.add_argument("--keep", action="store_true",
                        help="nao remover o workdir ao final")
    parser.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS,
                        help=f"temporizador do drill completo (default {DEFAULT_MAX_SECONDS:.0f}s)")
    parser.add_argument("--json", action="store_true",
                        help="imprime tambem uma linha JSON maquina no final")
    args = parser.parse_args(argv)

    t0 = time.monotonic()
    backups_dir = Path(args.backups_dir)
    live_db = Path(args.live_db)
    report: dict = {"checked_at": datetime.now(UTC).isoformat()}

    backup = _most_recent_backup(backups_dir)
    if backup is None:
        print(f"DRILL FALHOU: nenhum backup jobs-<ts>.db em {backups_dir}",
              file=sys.stderr)
        return 2

    own_workdir = args.workdir is None
    workdir = (Path(args.workdir) if args.workdir
               else Path(tempfile.mkdtemp(prefix="drill_restore_")))
    workdir.mkdir(parents=True, exist_ok=True)
    restored = workdir / "jobs-restored.db"
    try:
        # 1. restauracao: copia simples — o artefato e standalone por construcao
        tc = time.monotonic()
        shutil.copy2(backup, restored)
        copy_s = time.monotonic() - tc

        # 2. abre a COPIA read-only e verifica (o que o drill manual provou 19/10)
        tv = time.monotonic()
        conn = _connect_ro(restored)
        try:
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            rows = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            cols = _columns(conn)
        finally:
            conn.close()
        verify_s = time.monotonic() - tv

        ok = True
        problems: list[str] = []
        if quick != "ok":
            ok = False
            problems.append(f"quick_check={quick!r}")
        if rows <= 0:
            ok = False
            problems.append(f"rows={rows}")
        if cols != EXPECTED_COLUMNS:
            ok = False
            problems.append(
                f"schema != esperado ({len(cols)} colunas: {cols})")

        # 3. comparacao com o banco VIVO (read-only), quando presente
        live_rows = None
        live_schema_ok = None
        if live_db.is_file():
            lconn = _connect_ro(live_db)
            try:
                live_rows = lconn.execute(
                    "SELECT COUNT(*) FROM jobs").fetchone()[0]
                live_schema_ok = _columns(lconn) == cols
            finally:
                lconn.close()
            if not live_schema_ok:
                ok = False
                problems.append("schema do restaurado != schema do banco vivo")

        total_s = time.monotonic() - t0
        if total_s > args.max_seconds:
            ok = False
            problems.append(
                f"timeout: {total_s:.1f}s > {args.max_seconds:.1f}s")

        size = backup.stat().st_size
        print(f"drill de restauracao (F79) — {report['checked_at']}")
        print(f"  backup:      {backup.name} ({_human_size(size)})")
        print(f"  restaurado:  {restored} (copia em {copy_s:.2f}s)")
        print(f"  quick_check: {quick}   rows: {rows}   colunas: {len(cols)}")
        if live_rows is not None:
            print(f"  banco vivo:  {live_rows} rows (delta {live_rows - rows:+d})"
                  f"   schema vivo == restaurado: "
                  f"{'sim' if live_schema_ok else 'NAO'}")
        else:
            print("  banco vivo:  ausente (modo desastre — validacao "
                  "standalone do backup)")
        print(f"  verificar (abrir+quick_check+contar): {verify_s:.2f}s"
              f"   drill total: {total_s:.1f}s (limite {args.max_seconds:.0f}s)")

        report.update({
            "status": "ok" if ok else "failed",
            "backup": str(backup), "backup_bytes": size,
            "restored": str(restored), "copy_seconds": round(copy_s, 3),
            "verify_seconds": round(verify_s, 3),
            "total_seconds": round(total_s, 2),
            "quick_check": quick, "rows": rows, "columns": len(cols),
            "schema_match": cols == EXPECTED_COLUMNS,
            "live_rows": live_rows, "live_schema_match": live_schema_ok,
            "problems": problems,
        })
        if args.json:
            print(json.dumps(report, ensure_ascii=False))

        if ok:
            print("DRILL OK — o backup mais recente restaura. "
                  "Backup e backup.")
            return 0
        print(f"DRILL FALHOU: {'; '.join(problems)}", file=sys.stderr)
        return 3
    except (sqlite3.DatabaseError, OSError) as exc:
        print(f"DRILL FALHOU: backup ilegivel — "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    finally:
        if own_workdir and not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
