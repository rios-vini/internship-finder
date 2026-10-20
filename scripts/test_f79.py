#!/usr/bin/env python3
"""F79 — Ensaio de restauracao automatizado: backup so e backup se restaura.

Drill manual provado 19/10 (backup 09:38 de 706 MB restaurado read-only
-> quick_check ok, 217.630 rows, schema identico de 21 colunas, abre em
1s, delta 0) vira teste continuo do CI.

Delimitacao honesta: o test_db_backup.py (PR #54) JA cobre criacao,
conteudo, independencia, origem intocada, falhas limpas, nomes, retencao
e uma restauracao minimalista (copia + leitura) sobre fixture BRINQUEDO
de 6 colunas. O drill de F79 adiciona o que falta, na forma das ancoras
medidas 19/10:

A. drill INTEGRAL com fixture REAL: banco construido pelo SqliteStore de
   producao (DDL real, WAL) e populado pela API publica (store.run);
   backup com o codigo existente (backup_jobs_db); restauracao = copia
   para destino novo; abertura read-only DENTRO de DRILL_TIMEOUT_S;
   quick_check ok; rows > 0; schema == esperado (21 colunas, ordem
   exata: id + JOB_COLUMNS + LIFECYCLE_COLUMNS) == origem; delta 0
   (linhas integrais, raw JSON incluido); artefato portatil
   (journal_mode=DELETE — a copia simples carrega TUDO).
B. read-only e read-only DE VERDADE: escrita no restaurado levanta
   OperationalError; stat (size/mtime/inode) identico antes/depois.
C. cenario de desastre: a origem morre ANTES da restauracao; a copia
   restaurada e a UNICA copia e serve leitura completa (conteudo
   especifico com raw JSON round-trip).
D. contrato do opcional B: scripts/drill_restore.py (drill VIVO do
   backup real mais recente) existe, declara o contrato manual/watchdog
   FORA do CI e NUNCA no caminho do cron, e fica fora do CI por
   construcao (nao casa com o glob test_*.py — mesmo precedente de
   manifest_probe.py). Membership: test_f79 descoberto pela
   auto-descoberta F78 e o README acompanha (contrato F73).

ZERO rede; data/ intocada; fixtures em tmp.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ (ci_discover_tests)

import ci_discover_tests  # noqa: E402
from internship_finder.models.job import Job  # noqa: E402
from internship_finder.storage.sqlite_backup import backup_jobs_db  # noqa: E402
from internship_finder.storage.sqlite_store import (  # noqa: E402
    JOB_COLUMNS,
    LIFECYCLE_COLUMNS,
    SqliteStore,
)

FAILURES: list[str] = []

# Limite do drill no CI: o drill manual abriu 706 MB em ~1s; fixture de
# alguns KB tem de ser ordens de magnitude mais rapida. O limite existe
# para apanhar hang/lock patologico (backup que nao abre), nao para medir
# performance.
DRILL_TIMEOUT_S = 10.0

# Schema esperado do jobs.db: derivado das constantes DO CODIGO (nunca
# literais soltos) — drift de schema acorda este teste em vez de passa-lo.
EXPECTED_COLUMNS = ["id", *JOB_COLUMNS, *LIFECYCLE_COLUMNS]

# Ancora medida 19/10 (drill manual vs producao): 21 colunas. Se o schema
# evoluir, bump CONSCIENTE aqui — o teste e o guarda-chuva da ancora.
EXPECTED_SCHEMA_COUNT = 21

README = Path(__file__).resolve().parent.parent / "README.md"
_RE_CI_SUITES = re.compile(r"\*\*(\d+)\*\* \| CI test suites")

# Timestamp do drill manual 19/10 (backup real 09:38) — reutilizado como ts
# deterministico das fixtures (mesma pratica do test_db_backup).
DRILL_TS = "20261019T093849Z"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------- fixtures

def _make_jobs(n: int = 25) -> list[Job]:
    """N Jobs validos no formato de identidade da producao (2 unidades)."""
    seen = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
    jobs: list[Job] = []
    for i in range(n):
        company = f"Company{i % 3}"
        source = f"source:fixture{i % 2}"
        jobs.append(Job(
            id=f"{company}|{source}:ext-{i:03d}",
            source=source,
            title=f"Working Student Procurement {i}",
            company=company,
            location="Munchen" if i % 2 == 0 else "Berlin",
            country="Germany",
            remote=True if i % 4 == 0 else None,
            url=f"https://example.com/job/{i:03d}",
            description=f"Beschreibung der Stelle {i}" if i % 2 == 0 else None,
            internship=True,
            posted_at=seen,
            collected_at=seen,
            application_deadline=seen if i % 7 == 0 else None,
            external_id=f"ext-{i:03d}",
            employment_type="Werkstudent" if i % 2 == 0 else None,
            country_iso="de",
            raw={"ats": "fixture", "i": i, "nested": {"k": i}} if i % 3 == 0 else None,
        ))
    return jobs


def _build_fixture(db: Path, n: int = 25) -> dict:
    """Fixture REAL: o mesmo caminho de producao (SqliteStore + store.run)."""
    jobs = _make_jobs(n)
    with SqliteStore(db) as store:
        result = store.run(jobs)
    return {"jobs": jobs, "inserted": result["inserted"]}


# ------------------------------------------------- leitores read-only (drill)

def _connect_ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _column_names(path: Path) -> list[str]:
    conn = _connect_ro(path)
    try:
        return [row[1] for row in conn.execute("PRAGMA table_info(jobs)")]
    finally:
        conn.close()


def _table_info(path: Path) -> list[tuple]:
    conn = _connect_ro(path)
    try:
        return conn.execute("PRAGMA table_info(jobs)").fetchall()
    finally:
        conn.close()


def _rows_all(path: Path) -> list[tuple]:
    conn = _connect_ro(path)
    try:
        return conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()
    finally:
        conn.close()


def _stat(path: Path) -> tuple[int, int, int]:
    st = path.stat()
    return (st.st_size, st.st_mtime_ns, st.st_ino)


# ------------------------------------------------------------------ grupos

def group_a_drill_integral() -> None:
    print("== A. drill integral: SqliteStore real -> backup -> restauracao ==")
    with tempfile.TemporaryDirectory(prefix="t_f79a_") as tmp:
        base = Path(tmp)
        db = base / "data" / "jobs.db"
        db.parent.mkdir(parents=True)
        info = _build_fixture(db)

        check("fixture populada pela API publica do store (25 inserts)",
              info["inserted"] == 25, f"inserted={info['inserted']}")
        check("fixture no modo WAL (como a producao; consolidacao do backup exercitada)",
              sqlite3.connect(f"file:{db}?mode=ro", uri=True)
              .execute("PRAGMA journal_mode").fetchone()[0] == "wal")

        backup = backup_jobs_db(db, backup_dir=base / "data" / "backups", ts=DRILL_TS)
        check("backup criado pelo codigo existente (backup_jobs_db)",
              backup.is_file() and backup.name == f"jobs-{DRILL_TS}.db")

        # restauracao = copia simples para destino novo (o drill manual)
        restored = base / "restored" / "jobs.db"
        restored.parent.mkdir(parents=True)
        t0 = time.monotonic()
        shutil.copy2(backup, restored)
        copy_s = time.monotonic() - t0

        # abre read-only DENTRO do timeout: abrir + quick_check + contar
        t0 = time.monotonic()
        conn = _connect_ro(restored)
        try:
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            rows = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        open_s = time.monotonic() - t0

        check("abre read-only + quick_check ok DENTRO do timeout",
              quick == "ok" and open_s <= DRILL_TIMEOUT_S,
              f"{open_s:.3f}s (copia {copy_s:.3f}s; limite {DRILL_TIMEOUT_S}s)")
        check("rows > 0 no restaurado", rows > 0, f"rows={rows}")
        check("rows do restaurado == rows da origem", rows == len(info["jobs"]))

        cols = _column_names(restored)
        check("schema do restaurado == esperado (id + JOB_COLUMNS + LIFECYCLE_COLUMNS)",
              cols == EXPECTED_COLUMNS, f"{len(cols)} colunas")
        check("ancora 19/10: schema de 21 colunas",
              len(EXPECTED_COLUMNS) == EXPECTED_SCHEMA_COUNT == len(cols) == 21,
              f"{len(cols)} colunas")
        check("schema do restaurado == schema da origem (table_info integral)",
              _table_info(restored) == _table_info(db))
        check("artefato portatil: restaurado em journal_mode=DELETE (copia carrega tudo)",
              mode == "delete", f"journal_mode={mode}")

        check("delta 0: TODAS as linhas do restaurado == origem (raw JSON incluido)",
              _rows_all(restored) == _rows_all(db), f"{rows} linhas comparadas")


def group_b_somente_leitura() -> None:
    print("== B. restaurado e SOMENTE leitura (drill nunca escreve) ==")
    with tempfile.TemporaryDirectory(prefix="t_f79b_") as tmp:
        base = Path(tmp)
        db = base / "data" / "jobs.db"
        db.parent.mkdir(parents=True)
        _build_fixture(db)
        backup = backup_jobs_db(db, backup_dir=base / "data" / "backups", ts=DRILL_TS)
        restored = base / "restored" / "jobs.db"
        restored.parent.mkdir(parents=True)
        shutil.copy2(backup, restored)

        st_before = _stat(restored)
        refused = False
        conn = _connect_ro(restored)
        try:
            try:
                conn.execute("DELETE FROM jobs")
            except sqlite3.OperationalError:
                refused = True  # esperado: attempt to write a readonly database
            conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
        finally:
            conn.close()

        check("escrita na copia read-only levanta OperationalError", refused)
        check("arquivo do restaurado intocado pelo drill (size/mtime/inode)",
              _stat(restored) == st_before)


def group_c_desastre() -> None:
    print("== C. desastre: origem morre ANTES; restaurada e a unica copia ==")
    with tempfile.TemporaryDirectory(prefix="t_f79c_") as tmp:
        base = Path(tmp)
        db = base / "data" / "jobs.db"
        db.parent.mkdir(parents=True)
        _build_fixture(db)
        backup = backup_jobs_db(db, backup_dir=base / "data" / "backups", ts=DRILL_TS)

        # a producao "morre" ANTES da restauracao — cenario real do drill
        for sidecar in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
            sidecar.unlink(missing_ok=True)
        check("origem removida; resta so o artefato de backup",
              not db.exists() and backup.is_file())

        restored = base / "restored" / "jobs.db"
        restored.parent.mkdir(parents=True)
        shutil.copy2(backup, restored)

        conn = _connect_ro(restored)
        try:
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            rows = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            row3 = conn.execute(
                "SELECT title, company, raw FROM jobs WHERE id LIKE '%:ext-003'"
            ).fetchone()
        finally:
            conn.close()

        check("unica copia legivel: quick_check ok + 25 rows",
              quick == "ok" and rows == 25, f"quick={quick} rows={rows}")
        check("schema da unica copia == esperado (21 colunas)",
              _column_names(restored) == EXPECTED_COLUMNS)

        import json
        raw = json.loads(row3[2]) if row3 is not None and row3[2] else None
        check("conteudo especifico legivel (raw JSON round-trip)",
              row3 is not None
              and row3[0] == "Working Student Procurement 3"
              and row3[1] == "Company0"
              and raw == {"ats": "fixture", "i": 3, "nested": {"k": 3}})


def group_d_contrato_drill_vivo() -> None:
    print("== D. opcional B: drill_restore.py VIVO — FORA do CI, nunca no cron ==")
    drill = Path(__file__).resolve().parent / "drill_restore.py"
    check("scripts/drill_restore.py existe", drill.is_file())
    text = drill.read_text(encoding="utf-8") if drill.is_file() else ""
    check("nao casa com o glob test_*.py (fora do CI por construcao)",
          drill.is_file() and not drill.name.startswith("test_"))
    check("docstring declara: manual/watchdog, FORA do CI, NUNCA no caminho do cron",
          all(m in text for m in ("watchdog", "FORA do CI", "cron", "read-only")))

    names = ci_discover_tests.discover_tests()
    check("membership: test_f79 descoberto pela auto-descoberta (roda no CI)",
          "test_f79" in names, f"{len(names)} suites descobertas")
    check("drill_restore NAO descoberto (fora do CI, como manifest_probe)",
          "drill_restore" not in names)
    check("floor: >= 111 suites (test_f79 e a 111a)", len(names) >= 111,
          f"{len(names)}")
    m = _RE_CI_SUITES.search(README.read_text(encoding="utf-8"))
    check("README doc-sync (contrato F73): N CI test suites == descobertas",
          m is not None and int(m.group(1)) == len(names),
          f"README={m.group(1) if m else 'ausente'} vs {len(names)} descobertas")


def main() -> int:
    group_a_drill_integral()
    print()
    group_b_somente_leitura()
    print()
    group_c_desastre()
    print()
    group_d_contrato_drill_vivo()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
