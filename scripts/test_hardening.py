"""Testes de regressao do hardening (scripts/test_hardening.py).

Cobre os comportamentos corrigidos nos achados ACH-01..ACH-09, de forma
offline e deterministico (mocks para os estados de coleta, sem rede):

1. external_id igual em tenants diferentes NAO colide (ACH-01).
2. external_id igual no MESMO tenant continua deduplicando (ACH-01).
3. jobs sem URL/external_id distintos nao colapsam indevidamente (ACH-08).
4. jobs sem titulo nao colapsam indevidamente (ACH-09).
5. tenant SUCCESS (>=1 vaga) e reportado em ``ok``.
6. tenant EMPTY (0 vagas) e reportado em ``empty`` (nao em ``ok``).
7. tenant ERROR e reportado em ``failed``.
8. tenant TIMEOUT e reportado em ``timeout`` (nao em ``failed``).
9. falha parcial de coleta -> exit code degradado (ACH-02).
10. coverage.py roda sobre o output atual (sem ranked_jobs.json) (ACH-05/06).
11. metricas JSONL persistidas e legiveis (ACH-03).
12. P0: application_deadline segue presente/None.
13. cascata de filtros mantem o funil quando nao ha erro (sem regressao).
14. ranking determinístico (mesma entrada -> mesma ordem/score).

Uso:  .venv/bin/python scripts/test_hardening.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.models.company import Company  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def make_company() -> Company:
    return Company(name="Acme", ats="successfactors", slug="acme", url="https://careers.acme")


# ---------------------------------------------------------------------------
# 1-4. dedup / adapter
# ---------------------------------------------------------------------------

def test_dedup_external_id_scope() -> None:
    print("== ACH-01: external_id escopado por tenant ==")
    a = {"id": "1", "source": "successfactors:acme", "external_id": "12345",
         "title": "Intern", "company": "Acme", "url": "https://a/1", "location": "Berlin, DE"}
    b = {"id": "2", "source": "smartrecruiters:other", "external_id": "12345",
         "title": "Intern", "company": "Other", "url": "https://b/2", "location": "Munich, DE"}
    out, _, _ = deduplicate([a, b])
    check("1. external_id iguais em tenants diff -> 2 vagas", len(out) == 2)

    c = {"id": "3", "source": "successfactors:acme", "external_id": "12345",
         "title": "Intern", "company": "Acme", "url": "https://a/3", "location": "Berlin, DE"}
    out, _, _ = deduplicate([a, c])
    check("2. external_id igual no mesmo tenant -> 1 vaga", len(out) == 1)


def test_ach08_no_url_id() -> None:
    print("== ACH-08: jobs sem URL/external_id ==")
    c = Company(name="Acme", ats="greenhouse", slug="acme", url=None)
    adapter = AtsJobAdapter()
    j1 = adapter.to_job({"title": "Intern A", "location": "Berlin"}, c)
    j2 = adapter.to_job({"title": "Intern B", "location": "Munich"}, c)
    j3 = adapter.to_job({"title": "Intern A", "location": "Berlin"}, c)  # repete j1
    check("3a. sem URL: titulos distintos -> ids distintos", j1.id != j2.id)
    check("3b. sem URL: mesmo job repetido -> mesmo id", j1.id == j3.id)
    check("3c. sem URL/external_id: url vazio (nao fabrica careers)", j1.url == "")
    out, _, _ = deduplicate([j1.to_dict(), j2.to_dict(), j3.to_dict()])
    check("3d. 2 distintos + 1 dup sem URL -> 2 vagas", len(out) == 2)

    # com external_id, o ID e preservado (nao-regressao)
    je = adapter.to_job({"title": "Intern", "url": "https://x/1", "external_id": "R7"}, c)
    check("3e. com external_id, id = source:external_id", je.id == "greenhouse:acme:R7")


def test_ach09_sem_titulo() -> None:
    print("== ACH-09: jobs sem titulo ==")
    c = Company(name="Acme", ats="greenhouse", slug="acme", url=None)
    adapter = AtsJobAdapter()
    j1 = adapter.to_job({"location": "Berlin"}, c)
    j2 = adapter.to_job({"location": "Munich"}, c)
    check("4a. sem titulo -> titulo vazio (sem placeholder)", j1.title == "")
    check("4b. sem titulo, loc diff -> ids distintos", j1.id != j2.id)
    out, _, _ = deduplicate([j1.to_dict(), j2.to_dict()])
    check("4c. sem titulo, loc diff -> 2 vagas", len(out) == 2)


# ---------------------------------------------------------------------------
# 5-8. estados de coleta (mock do fetch)
# ---------------------------------------------------------------------------

def _mock_collect_company(fetch_side_effect) -> tuple[list, dict]:
    """Executa ``collect_company`` com CompanyCollector fake e fetch mockado."""
    from internship_finder import collectors
    from internship_finder.collectors import ats_scraper

    fake_company = make_company()
    class _FakeCollector:
        def find_company(self, name):
            return [fake_company]
        def has_scraper(self, company):
            return True

    with patch.object(ats_scraper, "CompanyCollector", _FakeCollector), \
         patch.object(ats_scraper, "fetch_with_timeout", side_effect=fetch_side_effect):
        return ats_scraper.collect_company("Acme", timeout=10)


def test_collect_states() -> None:
    print("== ACH-04: estados SUCCESS/EMPTY/ERROR/TIMEOUT ==")
    from internship_finder.models.job import Job
    from internship_finder.collectors import ats_scraper

    # 5. SUCCESS: fetch devolve 1 job
    job_dict = {
        "id": "s:1", "source": "successfactors:acme", "title": "Intern",
        "company": "Acme", "url": "https://a/1", "collected_at": "2026-08-01T00:00:00Z",
    }
    jobs, summary = _mock_collect_company(lambda *a, **k: [job_dict])
    check("5. SUCCESS: 1 vaga em ok", len(jobs) == 1 and len(summary["ok"]) == 1)

    # 6. EMPTY: fetch devolve lista vazia
    jobs, summary = _mock_collect_company(lambda *a, **k: [])
    check("6. EMPTY: 0 vagas em empty, nao em ok",
          len(jobs) == 0 and len(summary["empty"]) == 1 and len(summary["ok"]) == 0)

    # 7. ERROR: fetch levanta excecao generica
    jobs, summary = _mock_collect_company(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    check("7. ERROR: em failed, nao em ok/empty/timeout",
          len(summary["failed"]) == 1 and len(summary["ok"]) == 0
          and len(summary["empty"]) == 0 and len(summary["timeout"]) == 0)

    # 8. TIMEOUT: fetch levanta TimeoutError
    jobs, summary = _mock_collect_company(
        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("nao respondeu")))
    check("8. TIMEOUT: em timeout, nao em failed",
          len(summary["timeout"]) == 1 and len(summary["failed"]) == 0)


# ---------------------------------------------------------------------------
# 9. exit code de falha parcial (ACH-02)
# ---------------------------------------------------------------------------

def test_partial_failure_exit() -> None:
    print("== ACH-02: coleta parcial com falha -> exit degradado ==")
    from internship_finder import cli

    job_dict = {
        "id": "s:1", "source": "successfactors:acme", "title": "Praktikum Einkauf",
        "company": "Acme", "url": "https://a/1", "location": "Berlin, DE",
        "collected_at": "2026-08-01T00:00:00Z",
    }

    def _collect_ok(name, **kw):
        summary = {"ok": [("successfactors:acme", 1, "1.0s")], "empty": [], "timeout": [],
                   "failed": [], "skipped": [], "not_found": False}
        return [job_dict], summary

    def _collect_partial(name, **kw):
        summary = {"ok": [("successfactors:acme", 1, "1.0s")], "empty": [], "timeout": [],
                   "failed": [("smartrecruiters:other", "RuntimeError: boom")],
                   "skipped": [], "not_found": False}
        return [job_dict], summary

    tmp = tempfile.mkdtemp()
    with patch.object(cli, "collect_company", side_effect=_collect_ok):
        rc = cli.main(["--companies", "Acme", "--output", f"{tmp}/j.json",
                       "--filter-output", f"{tmp}/e.json"])
    check("9a. coleta sem falha -> exit 0", rc == 0, f"rc={rc}")

    with patch.object(cli, "collect_company", side_effect=_collect_partial):
        rc = cli.main(["--companies", "Acme", "--output", f"{tmp}/j2.json",
                       "--filter-output", f"{tmp}/e2.json"])
    check("9b. coleta parcial com erro -> exit != 0", rc != 0, f"rc={rc}")
    check("9c. output gravado mesmo com falha parcial", Path(f"{tmp}/j2.json").exists())


# ---------------------------------------------------------------------------
# 10. coverage.py offline (ACH-05/06)
# ---------------------------------------------------------------------------

def test_coverage_offline() -> None:
    print("== ACH-05/06: coverage.py sobre o output atual ==")
    root = Path(__file__).resolve().parent.parent
    if not (root / "data" / "jobs.json").exists() or not (root / "data" / "eligible_jobs.json").exists():
        check("10. dados de exemplo ausentes (pulado)", True, "sem data/ para rodar")
        return
    import subprocess
    r = subprocess.run(
        [sys.executable, str(root / "scripts" / "coverage.py")],
        capture_output=True, text=True, cwd=root,
    )
    check("10. coverage.py exit 0 (sem ranked_jobs.json)", r.returncode == 0,
          f"rc={r.returncode}")


# ---------------------------------------------------------------------------
# 11. metricas JSONL (ACH-03)
# ---------------------------------------------------------------------------

def test_metrics_roundtrip() -> None:
    print("== ACH-03: metricas JSONL ==")
    from internship_finder.metrics import read_metrics, write_metrics
    from internship_finder.cli import _tenant_record

    path = Path(tempfile.mktemp(suffix=".jsonl"))
    write_metrics(path, [
        _tenant_record("runX", "Acme", "successfactors:acme", "ok", 761, "4.2s"),
        _tenant_record("runX", "Acme", "smartrecruiters:other", "error", 0, None, "boom"),
        _tenant_record("runX", "Acme", "", "not_found", 0, None, "sem match exato"),
    ])
    write_metrics(path, [{"type": "run", "run_id": "runX", "timestamp": "t",
                          "total_collected": 761, "filtered": 10, "dedup_removed": 3,
                          "eligible": 10}])
    records = read_metrics(path)
    path.unlink()
    check("11a. 4 registros persistidos", len(records) == 4)
    tenants = [r for r in records if r["type"] == "tenant"]
    runs = [r for r in records if r["type"] == "run"]
    check("11b. tenant ok com ats/status/duracao",
          tenants[0]["ats"] == "successfactors" and tenants[0]["status"] == "ok"
          and tenants[0]["collected"] == 761)
    check("11c. tenant erro carrega mensagem", tenants[1]["error"] == "boom")
    check("11d. run record com dedup_removed",
          runs[0]["total_collected"] == 761 and runs[0]["dedup_removed"] == 3)


# ---------------------------------------------------------------------------
# 15-16. metricas: not_found e duration numerico
# ---------------------------------------------------------------------------

def test_metrics_not_found_and_duration() -> None:
    print("== metricas: status not_found e duration numerico ==")
    from internship_finder.cli import _tenant_record

    # PROBLEMA 1: empresa sem match exato -> status "not_found"
    rec = _tenant_record("runX", "Acme", "", "not_found", 0, None, "sem match exato")
    check("15a. not_found com status correto", rec["status"] == "not_found")
    check("15b. not_found com source vazio", rec["source"] == "" and rec["ats"] == "")
    check("15c. not_found com error 'sem match exato'", rec["error"] == "sem match exato")
    check("15d. not_found duration null", rec["duration"] is None)

    # PROBLEMA 2: duration deve ser float (segundos), nao string
    success = _tenant_record("runX", "Acme", "successfactors:acme", "ok", 10, "0.4s")
    check("16a. SUCCESS duration numerico", isinstance(success["duration"], float)
          and success["duration"] == 0.4, f"duration={success['duration']!r}")

    empty = _tenant_record("runX", "Acme", "successfactors:acme", "empty", 0, "1.2s")
    check("16b. EMPTY duration numerico", isinstance(empty["duration"], float)
          and empty["duration"] == 1.2, f"duration={empty['duration']!r}")

    timeout = _tenant_record("runX", "Acme", "successfactors:acme", "timeout", 0, None, "boom")
    check("16c. TIMEOUT duration null", timeout["duration"] is None)

    error = _tenant_record("runX", "Acme", "successfactors:acme", "error", 0, None, "boom")
    check("16d. ERROR duration null", error["duration"] is None)

    not_found = _tenant_record("runX", "Acme", "", "not_found", 0, None, "sem match exato")
    check("16e. NOT_FOUND duration null", not_found["duration"] is None)

    # campos preservados (timestamp UTC, run_id, source, ats, company, status,
    # collected, error)
    check("16f. run_id/source/company preservados",
          success["run_id"] == "runX" and success["source"] == "successfactors:acme"
          and success["company"] == "Acme")
    ts = success["timestamp"]
    check("16g. timestamp UTC (termina em +00:00 ou Z)",
          ts.endswith("+00:00") or ts.endswith("Z"), f"ts={ts!r}")


# ---------------------------------------------------------------------------
# 12-14. sem regressao (P0, filtros, ranking)
# ---------------------------------------------------------------------------

def test_p0_deadline() -> None:
    print("== P0: application_deadline ==")
    from internship_finder.models.job import Job
    from datetime import datetime, UTC
    c = make_company()
    adapter = AtsJobAdapter()
    with_d = adapter.to_job({"title": "Intern", "url": "https://a/1",
                             "external_id": "R1", "application_deadline": "2026-09-30"}, c)
    without_d = adapter.to_job({"title": "Intern", "url": "https://a/2",
                                "external_id": "R2"}, c)
    check("12a. deadline explicito presente",
          with_d.application_deadline == datetime(2026, 9, 30))
    check("12b. ausente -> None", without_d.application_deadline is None)


def test_filter_rank_no_regression() -> None:
    print("== sem regressao: filtros e ranking ==")
    from internship_finder.filters import is_student_role, matches_country, parse_country_spec
    from internship_finder.ranking import score_job

    check("13a. Praktikum segue aceito", is_student_role("Praktikum im Einkauf"))
    check("13b. JMP segue rejeitado",
          not is_student_role("Junior Managers Program (Trainee) - Purchasing"))
    check("13c. country de segue reconhecido",
          matches_country(country_iso="de", location="Berlin, DE", remote=None,
                          spec=parse_country_spec("de")))

    base = {"id": "1", "source": "s", "title": "Praktikum Einkauf Data",
            "company": "Acme", "location": "Berlin, DE", "url": "https://a/1",
            "external_id": "R1", "collected_at": "2026-08-01T00:00:00Z"}
    a = score_job(base)
    b = score_job(base)
    check("14. ranking determinístico (mesma entrada -> mesmo score)", a == b)


def main() -> int:
    test_dedup_external_id_scope()
    test_ach08_no_url_id()
    test_ach09_sem_titulo()
    test_collect_states()
    test_partial_failure_exit()
    test_coverage_offline()
    test_metrics_roundtrip()
    test_metrics_not_found_and_duration()
    test_p0_deadline()
    test_filter_rank_no_regression()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())