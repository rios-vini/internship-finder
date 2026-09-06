"""Testes da persistencia SQLite (P1 #5).

Cobre o modulo ``internship_finder.storage.sqlite_store``:

- 1a insercao -> first_seen == last_seen == collected_at;
- re-run do mesmo job -> first_seen intacto e last_seen atualizado;
- job que deixa de vir -> active=0 e archived=1; volta -> active=1, archived=0;
- schema contem TODAS as colunas do Job canonico (incl. ``application_deadline``)
  + first_seen/last_seen/active/archived;
- ``application_deadline`` round-trip correto (datetime preservado);
- 2 runs sequenciais consistentes (contagem/first/last);
- falha de escrita (diretorio inacessivel) nao levanta excecao na coleta.

Uso:
    .venv/bin/python scripts/test_sqlite.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.models.job import Job  # noqa: E402
from internship_finder.storage.sqlite_store import (  # noqa: E402
    _from_iso,
    SqliteStore,
)

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def make_job(
    job_id: str,
    collected_at: datetime,
    deadline: datetime | None = None,
    url: str | None = None,
) -> Job:
    """Cria um Job canonico com a minima base para o teste."""
    return Job(
        id=job_id,
        source="test:source",
        title=f"Vaga {job_id}",
        company="TestCo",
        url=url or f"https://jobs.test/{job_id}",
        collected_at=collected_at,
        application_deadline=deadline,
    )


# Colunas esperadas: Job canonico (sem ``id``, que e a PK) + 4 de vida.
EXPECTED_COLUMNS = {
    "id", "source", "title", "company", "location", "country", "remote",
    "url", "description", "internship", "posted_at", "collected_at",
    "application_deadline", "external_id", "employment_type", "country_iso",
    "raw", "first_seen", "last_seen", "active", "archived",
}


def test_schema_columns() -> None:
    print("Schema contem todas as colunas do Job canonico + lifecycle:")
    with tempfile.TemporaryDirectory() as td:
        store = SqliteStore(Path(td) / "jobs.db")
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(jobs)")}
        store.close()
        missing = EXPECTED_COLUMNS - cols
        check("todas as colunas presentes", not missing)
        if missing:
            print(f"        faltando: {sorted(missing)}")


def test_first_insert() -> None:
    print("1a insercao -> first_seen == last_seen == collected_at:")
    with tempfile.TemporaryDirectory() as td:
        base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        store.run([make_job("j1", base)])
        row = store.get("j1")
        store.close()
        first = _from_iso(row["first_seen"])
        last = _from_iso(row["last_seen"])
        check("first_seen == collected_at", first == base)
        check("last_seen == collected_at", last == base)
        check("first_seen == last_seen", first == last)
        check("active==1 na insercao", row["active"] == 1)
        check("archived==0 na insercao", row["archived"] == 0)


def test_rerun_preserves_first_seen() -> None:
    print("Re-run mesmo job -> first_seen intacto e last_seen atualizado:")
    with tempfile.TemporaryDirectory() as td:
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        store.run([make_job("j1", t1)])
        store.run([make_job("j1", t2)])
        row = store.get("j1")
        store.close()
        check("first_seen intacto", _from_iso(row["first_seen"]) == t1)
        check("last_seen avancou", _from_iso(row["last_seen"]) == t2)
        check("active==1 no re-run", row["active"] == 1)
        check("archived==0 apos re-run", row["archived"] == 0)


def test_archive_and_reactivate() -> None:
    print("Job que deixa de vir -> archived=1; volta -> active=1, archived=0:")
    with tempfile.TemporaryDirectory() as td:
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)
        t3 = datetime(2026, 9, 3, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        store.run([make_job("j1", t1), make_job("j2", t1)])
        # run 2: j2 Some, j1 nao veio -> j1 arquivado
        store.run([make_job("j2", t2)])
        r1 = store.get("j1")
        check("j1 nao veio -> active=0", r1["active"] == 0)
        check("j1 nao veio -> archived=1", r1["archived"] == 1)
        check("j2 continua ativo", store.get("j2")["active"] == 1)
        # run 3: j1 volta -> reativado
        stats = store.run([make_job("j1", t3), make_job("j2", t3)])
        r1b = store.get("j1")
        store.close()
        check("reativado ==1 contabilizado", stats["reactivated"] == 1)
        check("j1 voltou -> active=1", r1b["active"] == 1)
        check("j1 voltou -> archived=0", r1b["archived"] == 0)
        check("j1 last_seen atualizado na reativacao", _from_iso(r1b["last_seen"]) == t3)


def test_deadline_roundtrip() -> None:
    print("application_deadline round-trip (datetime preservado):")
    with tempfile.TemporaryDirectory() as td:
        t = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        deadline = datetime(2026, 10, 15, 23, 59, 59, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        store.run([make_job("j1", t, deadline=deadline)])
        row = store.get("j1")
        store.close()
        check("deadline armazenado como texto", row["application_deadline"] is not None)
        check("deadline == valor original", _from_iso(row["application_deadline"]) == deadline)


def test_two_runs_consistency() -> None:
    print("2 runs sequenciais consistentes (contagem/first/last):")
    with tempfile.TemporaryDirectory() as td:
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        s1 = store.run([make_job(f"j{i}", t1) for i in range(3)])
        s2 = store.run([make_job(f"j{i}", t2) for i in range(3)])
        n = store._conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        rows = {
            f"j{i}": (_from_iso(store.get(f"j{i}")["first_seen"]),
                      _from_iso(store.get(f"j{i}")["last_seen"]))
            for i in range(3)
        }
        store.close()
        check("run1 inseriu 3", s1["inserted"] == 3)
        check("run2 nao inseriu novos", s2["inserted"] == 0)
        check("total no banco == 3", n == 3)
        for i in range(3):
            check(f"j{i} first==t1 last==t2",
                  rows[f"j{i}"] == (t1, t2))


def test_write_failure_does_not_raise() -> None:
    print("Falha de escrita (caminho inacessivel) nao derruba a coleta:")
    with tempfile.TemporaryDirectory() as td:
        base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        # Caminho cujo pai e um arquivo comum -> sqlite nao abre o banco.
        blocker = Path(td) / "blocked"
        blocker.write_text("arquivo ocupa o caminho do banco")
        # __init__ captura o sqlite3.Error da conexao; run() e vazio, nao lanca.
        store = SqliteStore(blocker / "jobs.db")
        raised = None
        try:
            stats = store.run([make_job("j1", base)])
        except BaseException as exc:  # noqa: BLE001 - run() nao pode vazar
            raised = exc
        store.close()
    check("conexao falhou (store sem conn)", store._conn is None)
    check("run() nao levantou excecao", raised is None)
    check("run() retornou contagens vazias", stats["inserted"] == 0)


def main() -> int:
    test_schema_columns()
    test_first_insert()
    test_rerun_preserves_first_seen()
    test_archive_and_reactivate()
    test_deadline_roundtrip()
    test_two_runs_consistency()
    test_write_failure_does_not_raise()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())