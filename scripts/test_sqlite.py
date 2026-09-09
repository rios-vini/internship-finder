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


def make_unit_job(
    company: str,
    source: str,
    job_id: str,
    collected_at: datetime,
) -> Job:
    """Job pertencente a uma unidade (company, source) explicita (P1.2).

    O ``id`` segue a identidade P1.1 do pipeline real: ``<company>|<source>:<id>``.
    """
    return Job(
        id=f"{company}|{source}:{job_id}",
        source=source,
        title=f"Vaga {job_id}",
        company=company,
        url=f"https://jobs.test/{company}/{job_id}",
        collected_at=collected_at,
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


# ---------------------------------------------------------------------------
# P1.2 — lifecycle por unidade de coleta confiavel (company, source)
# ---------------------------------------------------------------------------
# Regra: coleta OK -> upsert + archive_not_seen SCOPED a unidade; timeout/erro
# -> NENHUM archive (a unidade nao e passada para run_units). A unidade usa a
# identidade P1.1 (company, source); empresas no MESMO tenant (source) nunca
# arquivam umas as outras.


def test_caso1_coleta_completa_arquiva_nao_vistos() -> None:
    print("Caso 1: coleta completa com sucesso -> nao-visto da unidade arquivado:")
    with tempfile.TemporaryDirectory() as td:
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        # Estado inicial: A: 1, 2, 3
        store.run_units([
            ("A", "ats:a", [make_unit_job("A", "ats:a", "1", t1),
                            make_unit_job("A", "ats:a", "2", t1),
                            make_unit_job("A", "ats:a", "3", t1)]),
        ])
        # Nova coleta: A: 1, 2, status OK
        store.run_units([("A", "ats:a", [make_unit_job("A", "ats:a", "1", t2),
                                         make_unit_job("A", "ats:a", "2", t2)])])
        rows = {r["id"]: r for r in store._conn.execute(
            "SELECT id, active, archived FROM jobs").fetchall()}
        store.close()
        check("1 -> ativo", rows["A|ats:a:1"]["active"] == 1)
        check("2 -> ativo", rows["A|ats:a:2"]["active"] == 1)
        check("3 -> arquivado", rows["A|ats:a:3"]["archived"] == 1
              and rows["A|ats:a:3"]["active"] == 0)


def test_caso2_timeout_nao_arquiva() -> None:
    print("Caso 2: timeout -> nenhuma vaga arquivada (estado preservado):")
    with tempfile.TemporaryDirectory() as td:
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        store.run_units([
            ("A", "ats:a", [make_unit_job("A", "ats:a", "1", t1),
                            make_unit_job("A", "ats:a", "2", t1),
                            make_unit_job("A", "ats:a", "3", t1)]),
        ])
        # Nova coleta: A timeout -> a unidade NAO e passada a run_units,
        # exatamente como o CLI faz (only OK/EMPTY viram unidades).
        store.run_units([])  # nenhuma unidade confiavel no run
        rows = {r["id"]: r for r in store._conn.execute(
            "SELECT id, active, archived FROM jobs").fetchall()}
        store.close()
        for i in ("1", "2", "3"):
            check(f"{i} continua ativo", rows[f"A|ats:a:{i}"]["active"] == 1
                  and rows[f"A|ats:a:{i}"]["archived"] == 0)


def test_caso3_erro_nao_arquiva() -> None:
    print("Caso 3: erro -> nenhuma vaga arquivada (estado preservado):")
    with tempfile.TemporaryDirectory() as td:
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        store.run_units([
            ("A", "ats:a", [make_unit_job("A", "ats:a", "1", t1),
                            make_unit_job("A", "ats:a", "2", t1),
                            make_unit_job("A", "ats:a", "3", t1)]),
        ])
        # Nova coleta: A error -> unidade nao passada (igual timeout).
        store.run_units([])
        rows = {r["id"]: r for r in store._conn.execute(
            "SELECT id, active, archived FROM jobs").fetchall()}
        store.close()
        for i in ("1", "2", "3"):
            check(f"{i} continua ativo", rows[f"A|ats:a:{i}"]["active"] == 1
                  and rows[f"A|ats:a:{i}"]["archived"] == 0)


def test_caso4_sucesso_de_A_mais_falha_de_B() -> None:
    print("Caso 4 (O MAIS IMPORTANTE): A OK + B timeout -> A atualizado, B preservado:")
    with tempfile.TemporaryDirectory() as td:
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        # Estado inicial: A: 1,2,3 ; B: 4,5,6
        store.run_units([
            ("A", "ats:a", [make_unit_job("A", "ats:a", "1", t1),
                            make_unit_job("A", "ats:a", "2", t1),
                            make_unit_job("A", "ats:a", "3", t1)]),
            ("B", "ats:b", [make_unit_job("B", "ats:b", "4", t1),
                            make_unit_job("B", "ats:b", "5", t1),
                            make_unit_job("B", "ats:b", "6", t1)]),
        ])
        # Nova coleta: A: 1,2 OK ; B: TIMEOUT (unidade B NAO entra)
        store.run_units([
            ("A", "ats:a", [make_unit_job("A", "ats:a", "1", t2),
                            make_unit_job("A", "ats:a", "2", t2)]),
        ])
        rows = {r["id"]: r for r in store._conn.execute(
            "SELECT id, active, archived FROM jobs").fetchall()}
        store.close()
        check("A: 1 ativo", rows["A|ats:a:1"]["active"] == 1)
        check("A: 2 ativo", rows["A|ats:a:2"]["active"] == 1)
        check("A: 3 arquivado", rows["A|ats:a:3"]["archived"] == 1)
        check("B: 4 continua ativo", rows["B|ats:b:4"]["active"] == 1
              and rows["B|ats:b:4"]["archived"] == 0)
        check("B: 5 continua ativo", rows["B|ats:b:5"]["active"] == 1
              and rows["B|ats:b:5"]["archived"] == 0)
        check("B: 6 continua ativo", rows["B|ats:b:6"]["active"] == 1
              and rows["B|ats:b:6"]["archived"] == 0)


def test_caso5_sucesso_com_zero_jobs() -> None:
    print("Caso 5: OK com zero jobs -> arquiva TODA a unidade:")
    with tempfile.TemporaryDirectory() as td:
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        store.run_units([
            ("A", "ats:a", [make_unit_job("A", "ats:a", "1", t1),
                            make_unit_job("A", "ats:a", "2", t1),
                            make_unit_job("A", "ats:a", "3", t1)]),
        ])
        # Nova coleta: A: [] status OK (EMPTY) -> unidade passada com 0 jobs
        store.run_units([("A", "ats:a", [])])
        rows = {r["id"]: r for r in store._conn.execute(
            "SELECT id, active, archived FROM jobs").fetchall()}
        store.close()
        for i in ("1", "2", "3"):
            check(f"{i} -> arquivado", rows[f"A|ats:a:{i}"]["archived"] == 1
                  and rows[f"A|ats:a:{i}"]["active"] == 0)


def test_caso6_unidades_compartilhando_tenant() -> None:
    print("Caso 6: A e B no MESMO tenant X -> falha de B nao arquiva A (e vice-versa):")
    with tempfile.TemporaryDirectory() as td:
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)
        store = SqliteStore(Path(td) / "jobs.db")
        # Empresa A -> tenant X ; Empresa B -> tenant X (mesmo source!)
        store.run_units([
            ("A", "X", [make_unit_job("A", "X", "1", t1),
                        make_unit_job("A", "X", "2", t1)]),
            ("B", "X", [make_unit_job("B", "X", "1", t1),
                        make_unit_job("B", "X", "2", t1)]),
        ])
        # Nova coleta: A OK (vem 1 apenas) ; B timeout (nao entra)
        store.run_units([
            ("A", "X", [make_unit_job("A", "X", "1", t2)]),
        ])
        rows = {r["id"]: r for r in store._conn.execute(
            "SELECT id, active, archived FROM jobs").fetchall()}
        store.close()
        check("A: 1 atualizado e ativo", rows["A|X:1"]["active"] == 1)
        check("A: 2 arquivado (A foi OK)", rows["A|X:2"]["archived"] == 1)
        check("B: 1 preservado", rows["B|X:1"]["active"] == 1
              and rows["B|X:1"]["archived"] == 0)
        check("B: 2 preservado", rows["B|X:2"]["active"] == 1
              and rows["B|X:2"]["archived"] == 0)


def test_cli_pipeline_parcial_e2e() -> None:
    """E2E: cli.main (coleta mockada) + --sqlite — A OK + B timeout.

    Prova que a informacao de sucesso/falha do summary atravessa o CLI e
    chega ao SQLite como unidades: A tem lifecycle atualizado, B preservado.
    """
    from unittest.mock import patch

    from internship_finder import cli

    print("E2E cli.main: A OK + B timeout -> A arquivado-so-nao-visto, B preservado:")
    t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)

    def _collect_both(name, **kw):
        # 1º run: A 1,2,3 OK; B 4,5,6 OK
        if name == "A":
            summary = {"ok": [("ats:a", 3, "1.0s")], "empty": [], "timeout": [],
                       "failed": [], "skipped": [], "not_found": False,
                       "companies": {"ats:a": "A"}}
            return [make_unit_job("A", "ats:a", i, t1) for i in ("1", "2", "3")], summary
        summary = {"ok": [("ats:b", 3, "1.0s")], "empty": [], "timeout": [],
                   "failed": [], "skipped": [], "not_found": False,
                   "companies": {"ats:b": "B"}}
        return [make_unit_job("B", "ats:b", i, t1) for i in ("4", "5", "6")], summary

    def _collect_partial(name, **kw):
        # 2º run: A 1,2 OK; B TIMEOUT (sem jobs, unidade nao confiavel)
        if name == "A":
            summary = {"ok": [("ats:a", 2, "1.0s")], "empty": [], "timeout": [],
                       "failed": [], "skipped": [], "not_found": False,
                       "companies": {"ats:a": "A"}}
            return [make_unit_job("A", "ats:a", i, t2) for i in ("1", "2")], summary
        summary = {"ok": [], "empty": [], "timeout": [("ats:b", "TIMEOUT", "boom")],
                   "failed": [], "skipped": [], "not_found": False,
                   "companies": {"ats:b": "B"}}
        return [], summary

    def _run_collection(side_effect, tmp: Path):
        db = tmp / "jobs.db"
        with patch.object(cli, "collect_company", side_effect=side_effect):
            cli.main([
                "--companies", "A,B",
                "--output", str(tmp / "jobs.json"),
                "--filter-output", str(tmp / "eligible.json"),
                "--metrics", str(tmp / "metrics.jsonl"),
                "--sqlite", str(db),
                "--no-rank",
            ])
        assert db.exists()
        store = SqliteStore(db)
        rows = {r["id"]: r for r in store._conn.execute(
            "SELECT id, active, archived FROM jobs").fetchall()}
        store.close()
        return rows

    tmp = Path(tempfile.mkdtemp())
    rows = _run_collection(_collect_both, tmp)     # estado inicial A 1,2,3 / B 4,5,6
    check("init: A e B ativos", all(rows[i]["active"] == 1 for i in
          ("A|ats:a:1", "A|ats:a:2", "A|ats:a:3", "B|ats:b:4", "B|ats:b:5", "B|ats:b:6")))
    rows = _run_collection(_collect_partial, tmp)  # A 1,2 OK / B TIMEOUT
    check("A: 1 ativo", rows["A|ats:a:1"]["active"] == 1)
    check("A: 2 ativo", rows["A|ats:a:2"]["active"] == 1)
    check("A: 3 arquivado (A foi OK, nao veio)", rows["A|ats:a:3"]["archived"] == 1)
    check("B: 4 preservado (B timeout)", rows["B|ats:b:4"]["active"] == 1
          and rows["B|ats:b:4"]["archived"] == 0)
    check("B: 5 preservado (B timeout)", rows["B|ats:b:5"]["active"] == 1
          and rows["B|ats:b:5"]["archived"] == 0)
    check("B: 6 preservado (B timeout)", rows["B|ats:b:6"]["active"] == 1
          and rows["B|ats:b:6"]["archived"] == 0)


def test_cli_pipeline_empty_arquiva() -> None:
    """E2E: EMPTY (OK, 0 vagas) arquiva a unidade; outra unidade OK preservada.

    Complemento do caso 5 no pipeline real do CLI: zero jobs observados com
    sucesso (status EMPTY) arquiva a unidade inteira; unidade OK que continuou
    com vagas e preservada. (Com total == 0 o CLI retorna antes do sqlite —
    guard pre-existente — entao o cenario usa B OK para o run processar.)
    """
    from unittest.mock import patch

    from internship_finder import cli

    print("E2E cli.main: A EMPTY (OK, 0 vagas) -> unidade arquivada; B OK preservada:")
    t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)

    def _collect_seed(name, **kw):
        summary = {"ok": [("ats:a", 2, "1.0s") if name == "A" else ("ats:b", 2, "1.0s")],
                   "empty": [], "timeout": [], "failed": [], "skipped": [],
                   "not_found": False,
                   "companies": {"ats:a": "A"} if name == "A" else {"ats:b": "B"}}
        jobs = [make_unit_job(name, f"ats:{name.lower()}", i, t1) for i in ("1", "2")]
        return jobs, summary

    def _collect_empty_ok(name, **kw):
        if name == "A":
            # EMPTY: tenant respondeu, 0 vagas — sucesso observado
            summary = {"ok": [], "empty": [("ats:a", "1.0s")], "timeout": [],
                       "failed": [], "skipped": [], "not_found": False,
                       "companies": {"ats:a": "A"}}
            return [], summary
        # B OK: continua com as mesmas 2 vagas
        summary = {"ok": [("ats:b", 2, "1.0s")], "empty": [], "timeout": [],
                   "failed": [], "skipped": [], "not_found": False,
                   "companies": {"ats:b": "B"}}
        return [make_unit_job("B", "ats:b", i, t2) for i in ("1", "2")], summary

    tmp = Path(tempfile.mkdtemp())
    db = tmp / "jobs.db"
    with patch.object(cli, "collect_company", side_effect=_collect_seed):
        cli.main(["--companies", "A,B", "--output", str(tmp / "j1.json"),
                  "--filter-output", str(tmp / "e1.json"),
                  "--metrics", str(tmp / "m1.jsonl"), "--sqlite", str(db), "--no-rank"])
    with patch.object(cli, "collect_company", side_effect=_collect_empty_ok):
        cli.main(["--companies", "A,B", "--output", str(tmp / "j2.json"),
                  "--filter-output", str(tmp / "e2.json"),
                  "--metrics", str(tmp / "m2.jsonl"), "--sqlite", str(db), "--no-rank"])
    store = SqliteStore(db)
    rows = {r["id"]: r for r in store._conn.execute(
        "SELECT id, active, archived FROM jobs").fetchall()}
    store.close()
    check("EMPTY: A/1 arquivado", rows["A|ats:a:1"]["archived"] == 1)
    check("EMPTY: A/2 arquivado", rows["A|ats:a:2"]["archived"] == 1)
    check("B OK: B/1 preservada", rows["B|ats:b:1"]["active"] == 1
          and rows["B|ats:b:1"]["archived"] == 0)
    check("B OK: B/2 preservada", rows["B|ats:b:2"]["active"] == 1
          and rows["B|ats:b:2"]["archived"] == 0)


def main() -> int:
    test_schema_columns()
    test_first_insert()
    test_rerun_preserves_first_seen()
    test_archive_and_reactivate()
    test_deadline_roundtrip()
    test_two_runs_consistency()
    test_write_failure_does_not_raise()
    # P1.2 — lifecycle por unidade de coleta confiavel
    test_caso1_coleta_completa_arquiva_nao_vistos()
    test_caso2_timeout_nao_arquiva()
    test_caso3_erro_nao_arquiva()
    test_caso4_sucesso_de_A_mais_falha_de_B()
    test_caso5_sucesso_com_zero_jobs()
    test_caso6_unidades_compartilhando_tenant()
    test_cli_pipeline_parcial_e2e()
    test_cli_pipeline_empty_arquiva()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())