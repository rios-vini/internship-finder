"""Testes do backup do jobs.db (scripts/test_db_backup.py) — P3.

Standalone e OFFLINE (tempfile, sem rede, sem tocar em ``data/`` real): cobre
os 6 cenarios obrigatorios da tarefa — (1) backup a partir de SQLite valido;
(2) backup contem os dados esperados; (3) backup e banco SQLite independente
(le com conexao nova, integridade ok, sem sidecars WAL, sobrevive a remocao
da origem); (4) backup nao altera o banco original (dados + stat antes==depois);
(5) falha de backup nao destroi/substitui o banco principal (origem ausente,
origem invalida, diretorio bloqueado: nenhum temporario/final residual e a
origem permanece byte-identica); (6) nomes distintos quando executados em
momentos diferentes. Extra: retencao simples (``cleanup_backups``) e o fluxo
de restauracao manual documentado (copia do backup -> banco novo utilizavel).

Uso:

    .venv/bin/python scripts/test_db_backup.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.storage.sqlite_backup import (  # noqa: E402
    backup_filename,
    backup_jobs_db,
    cleanup_backups,
    _parse_backup_ts,
)

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _make_db(path: Path, n: int = 50, *, wal: bool = True) -> None:
    """Cria um banco no estilo do SqliteStore (WAL quando pedido) com N linhas."""
    conn = sqlite3.connect(str(path))
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT NOT NULL,
            company TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
            collected_at TEXT NOT NULL
        )
    """)
    rows = [
        (f"id{i:03d}", f"source:{i % 7}", f"Working Student {i}",
         f"Company{i % 5}", 1, "2026-09-13T06:00:00.000000Z")
        for i in range(n)
    ]
    conn.executemany("INSERT INTO jobs VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def _rows(path: Path) -> list[tuple]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()
    finally:
        conn.close()


def _quick_check(path: Path) -> str:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        conn.close()


def _files_in(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def test_backup_valido() -> None:
    print("== 1. backup a partir de um SQLite valido ==")
    with tempfile.TemporaryDirectory(prefix="t_bk1_") as tmp:
        base = Path(tmp)
        db = base / "jobs.db"
        _make_db(db)
        out = backup_jobs_db(db, backup_dir=base / "backups", ts="20260913T060000Z")
        check("arquivo de backup existe no diretorio indicado",
              out.exists() and out.is_file())
        check("nome no formato jobs-<ts>.db",
              out.name == "jobs-20260913T060000Z.db")
        check("backup nao vazio", out.stat().st_size > 0)
        check("quick_check ok no backup", _quick_check(out) == "ok")
        check("mesmo numero de linhas da origem",
              _rows(out) == _rows(db) and len(_rows(out)) == 50)


def test_backup_conteudo() -> None:
    print("== 2. backup contem os dados esperados ==")
    with tempfile.TemporaryDirectory(prefix="t_bk2_") as tmp:
        base = Path(tmp)
        db = base / "jobs.db"
        expected = [
            ("id007", "source:0", "Working Student 7", "Company2", 1,
             "2026-09-13T06:00:00.000000Z"),
            ("id042", "source:0", "Working Student 42", "Company2", 1,
             "2026-09-13T06:00:00.000000Z"),
        ]
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT NOT NULL,
                company TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                collected_at TEXT NOT NULL
            )
        """)
        conn.executemany("INSERT INTO jobs VALUES (?,?,?,?,?,?)", expected)
        conn.commit()
        conn.close()

        out = backup_jobs_db(db, backup_dir=base / "backups", ts="20260913T060000Z")
        rows = _rows(out)
        check("linhas esperadas presentes no backup",
              sorted(rows) == sorted(expected))
        check("campos individuais corretos",
              rows[0][2] == "Working Student 7" and rows[1][1] == "source:0")

        # validacao minimamente mais forte no artefato (integridade das paginas)
        conn = sqlite3.connect(str(out))
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        check("integrity_check ok no backup", integ == "ok")


def test_backup_independente() -> None:
    print("== 3. backup e banco SQLite independente ==")
    with tempfile.TemporaryDirectory(prefix="t_bk3_") as tmp:
        base = Path(tmp)
        db = base / "jobs.db"
        _make_db(db)
        out = backup_jobs_db(db, backup_dir=base / "backups", ts="20260913T060000Z")

        # conexao NOVA, sem qualquer conexao com a origem aberta
        conn = sqlite3.connect(str(out))
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        title = conn.execute(
            "SELECT title FROM jobs WHERE id='id010'").fetchone()[0]
        conn.close()
        check("leitura com conexao propria (sem depender da origem)",
              count == 50 and title == "Working Student 10")

        # artefato standalone: sem sidecars WAL ao lado do arquivo
        check("sem sidecars -wal/-shm junto ao backup",
              not (base / "backups" / "jobs-20260913T060000Z.db-wal").exists()
              and not (base / "backups" / "jobs-20260913T060000Z.db-shm").exists())

        # sobrevive a remocao da origem: prova a independencia de verdade
        db.unlink()
        conn = sqlite3.connect(str(out))
        check("backup utilizavel depois de a origem sumir",
              conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 50)
        conn.close()


def test_backup_nao_altera_origem() -> None:
    print("== 4. backup nao altera o banco original ==")
    with tempfile.TemporaryDirectory(prefix="t_bk4_") as tmp:
        base = Path(tmp)
        db = base / "jobs.db"
        _make_db(db)
        before_rows = _rows(db)
        st_before = db.stat()

        backup_jobs_db(db, backup_dir=base / "backups", ts="20260913T060000Z")

        after_rows = _rows(db)
        st_after = db.stat()
        check("dados da origem identicos antes/depois", before_rows == after_rows)
        check("arquivo da origem intacto (size+mtime iguais)",
              st_before.st_size == st_after.st_size
              and st_before.st_mtime_ns == st_after.st_mtime_ns)
        check("origem segue um SQLite valido", _quick_check(db) == "ok")


def test_falha_nao_destroi_banco_principal() -> None:
    print("== 5. falha de backup nao destroi/substitui o banco principal ==")

    # 5a: origem ausente -> erro claro, sem artefatos
    with tempfile.TemporaryDirectory(prefix="t_bk5a_") as tmp:
        base = Path(tmp)
        missing = base / "jobs.db"
        try:
            backup_jobs_db(missing, backup_dir=base / "backups", ts="20260913T060000Z")
            check("origem ausente levanta FileNotFoundError", False)
        except FileNotFoundError:
            check("origem ausente levanta FileNotFoundError", True)
        check("5a: nenhum arquivo criado (nem backup nem temporario)",
              _files_in(base) == [] or not (base / "backups").exists())

    # 5b: origem nao-e-SQLite -> DatabaseError; origem byte-identica
    with tempfile.TemporaryDirectory(prefix="t_bk5b_") as tmp:
        base = Path(tmp)
        fake = base / "jobs.db"
        fake.write_bytes(b"isto nao e um sqlite" * 100)
        before = fake.read_bytes()
        try:
            backup_jobs_db(fake, backup_dir=base / "backups", ts="20260913T060000Z")
            check("origem invalida levanta sqlite3.DatabaseError", False)
        except sqlite3.DatabaseError:
            check("origem invalida levanta sqlite3.DatabaseError", True)
        check("5b: origem byte-identica apos falha", fake.read_bytes() == before)
        check("5b: nenhum temporario/final residual no diretorio",
              _files_in(base / "backups") == [])

    # 5c: destino bloqueado (diretorio sem permissao) -> falha limpa
    if os.geteuid() != 0:  # root ignora permissao; CI/runner sao non-root
        with tempfile.TemporaryDirectory(prefix="t_bk5c_") as tmp:
            base = Path(tmp)
            db = base / "jobs.db"
            _make_db(db)
            blocked = base / "backups"
            blocked.mkdir()
            blocked.chmod(0o500)  # sem permissao de escrita (non-root)
            try:
                backup_jobs_db(db, backup_dir=blocked, ts="20260913T060000Z")
                check("diretorio sem permissao levanta OSError", False)
            except OSError:
                check("diretorio sem permissao levanta OSError", True)
            blocked.chmod(0o700)  # devolve antes de inspecionar/limpar
            check("5c: nenhum backup final criado",
                  _files_in(blocked) == [])
            check("5c: banco principal intacto (dados + quick_check)",
                  len(_rows(db)) == 50 and _quick_check(db) == "ok")
    else:
        print("  (skip 5c: rodando como root)")

    # 5d: banco principal valido com falha no backup -> continua utilizavel
    with tempfile.TemporaryDirectory(prefix="t_bk5d_") as tmp:
        base = Path(tmp)
        db = base / "jobs.db"
        _make_db(db)
        (base / "backups").mkdir()
        before = db.stat().st_mtime_ns
        try:
            backup_jobs_db(base / "inexistente.db",
                           backup_dir=base / "backups", ts="20260913T060000Z")
        except FileNotFoundError:
            pass
        check("5d: banco principal intocado apos falha externa",
              db.stat().st_mtime_ns == before and len(_rows(db)) == 50)


def test_nomes_distintos_por_momento() -> None:
    print("== 6. nomes distintos quando executados em momentos diferentes ==")
    with tempfile.TemporaryDirectory(prefix="t_bk6_") as tmp:
        base = Path(tmp)
        db = base / "jobs.db"
        _make_db(db)
        t1 = backup_jobs_db(db, backup_dir=base / "backups", ts="20260913T060000Z")
        t2 = backup_jobs_db(db, backup_dir=base / "backups", ts="20260914T060000Z")
        check("nomes diferentes para momentos diferentes", t1 != t2)
        check("ambos os backups existem (historico preservado)",
              t1.exists() and t2.exists())
        check("ambos validos e com os mesmos dados",
              _quick_check(t1) == "ok" and _quick_check(t2) == "ok"
              and _rows(t1) == _rows(t2) == _rows(db))
        check("nome default usa o timestamp UTC agora (formato correto)",
              backup_jobs_db(db, backup_dir=base / "backups").name
              .startswith("jobs-") and backup_jobs_db(
                  db, backup_dir=base / "backups").name.endswith(".db"))


def test_retencao() -> None:
    print("== retencao simples (cleanup_backups) ==")
    now = datetime(2026, 9, 13, 6, 0, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory(prefix="t_bkret_") as tmp:
        bdir = Path(tmp) / "backups"
        bdir.mkdir()
        old = bdir / backup_filename("20260801T060000Z")
        old.write_bytes(b"x")  # artefatos falsos, so o nome importa
        recent = bdir / backup_filename("20260912T060000Z")
        recent.write_bytes(b"y")
        weird = bdir / "not-a-backup.txt"
        weird.write_bytes(b"z")

        removed = cleanup_backups(bdir, 14, now=now)
        check("antigo (>14d) removido", old in removed and not old.exists())
        check("recente mantido", recent.exists() and recent not in removed)
        check("nome fora do formato preservado",
              weird.exists() and weird not in removed)

        removed2 = cleanup_backups(bdir, 0, now=now)
        check("retencao 0 nao remove nada",
              not removed2 and recent.exists() and weird.exists())

    check("diretorio inexistente -> nada a limpar, sem crash",
          cleanup_backups(Path("/tmp/nao_existe_bkdir_xyz"), 14, now=now) == [])

    # round-trip nome <-> timestamp
    check("backup_filename/parse round-trip",
          _parse_backup_ts(backup_filename("20260913T060000Z"))
          == datetime(2026, 9, 13, 6, 0, 0, tzinfo=UTC))
    check("nome fora do formato -> None",
          _parse_backup_ts("jobs.db") is None
          and _parse_backup_ts("jobs-abc.db") is None
          and _parse_backup_ts("archive/2026.db") is None)


def test_restauracao() -> None:
    print("== restauracao manual (fluxo documentado: copiar backup por cima) ==")
    with tempfile.TemporaryDirectory(prefix="t_bkrest_") as tmp:
        base = Path(tmp)
        db = base / "jobs.db"
        _make_db(db)
        out = backup_jobs_db(db, backup_dir=base / "backups", ts="20260913T060000Z")

        # simulacao de banco 'corrompido'/'perdido': sobrescrever com o backup
        db.unlink()
        import shutil
        shutil.copy2(out, db)
        check("restaurado: arquivo abre e contem os dados",
              _quick_check(db) == "ok" and len(_rows(db)) == 50)
        conn = sqlite3.connect(str(db))
        conn.execute("SELECT * FROM jobs")  # utilizavel normalmente
        conn.close()
        check("restaurado: leitura de vaga especifica",
              _rows(db)[10][2] == "Working Student 10")


def main() -> int:
    test_backup_valido()
    test_backup_conteudo()
    test_backup_independente()
    test_backup_nao_altera_origem()
    test_falha_nao_destroi_banco_principal()
    test_nomes_distintos_por_momento()
    test_retencao()
    test_restauracao()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())