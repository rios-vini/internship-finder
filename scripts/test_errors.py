"""Script standalone — P1 #7: codigos de erro estruturados.

Cobre o item do MASTER_PLAN #7: codigos fixos
``TIMEOUT / CONNECTION_ERROR / FETCH_ERROR / NORMALIZATION_ERROR / UNKNOWN``
no lugar de TEXTO LIVRE na queue de coleta.

Verifica:
- classificacao por tipo de excecao (um caso por codigo);
- payload da queue no ``fetch_worker`` ESTRUTURADO (sem texto livre) em erro de
  fetch, erro de adaptacao e sucesso (com mocks);
- ``collect_company``: summary ``failed``/``timeout`` carregando ``code``+``detail``;
- ``_tenant_record`` com ``error_code`` e round-trip JSONL (``error`` preservado);
- CLI ``--companies``: falha parcial -> exit code 2 e registro com ``error_code``
  no JSONL temporario (fora de ``data/``);
- regressao: ``build_health_report`` (P1 #6) consumindo registros com
  ``error_code`` continua valido.

Nao depende de ``data/`` e nao faz coleta real (mocks obrigatorios); usa
``tempfile`` para qualquer arquivo temporario e limpa ao final. Padrao dos
demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK`` (exit 0) ou
``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_errors.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from internship_finder.errors import (  # noqa: E402
    CONNECTION_ERROR,
    FETCH_ERROR,
    FETCH_STAGE,
    NORMALIZATION_ERROR,
    NORMALIZE_STAGE,
    TIMEOUT,
    UNKNOWN,
    CollectionError,
    classify_exception,
)
from internship_finder.models.company import Company  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  [OK] {name}")
    else:
        print(f"  [FAIL] {name} {detail}")
        FAILURES.append(name)


def make_company() -> Company:
    return Company(name="Acme", ats="smartrecruiters", slug="acme", query="Acme")


# ---------------------------------------------------------------------------
# 1. classificacao por tipo de excecao
# ---------------------------------------------------------------------------

def test_classify_by_type() -> None:
    print("== P1#7: classificacao por tipo de excecao ==")

    code, detail = classify_exception(TimeoutError("nao respondeu"))
    check("1a. TimeoutError -> TIMEOUT", code == TIMEOUT, f"code={code}")
    check("1b. detail legivel preservado", "TimeoutError: nao respondeu" in detail,
          f"detail={detail!r}")

    import socket
    code, _ = classify_exception(socket.timeout("conn"))
    check("1c. socket.timeout -> TIMEOUT", code == TIMEOUT, f"code={code}")

    code, _ = classify_exception(ConnectionError("conexao recusada"))
    check("1d. builtin ConnectionError -> CONNECTION_ERROR", code == CONNECTION_ERROR,
          f"code={code}")

    import requests
    code, _ = classify_exception(requests.exceptions.ConnectionError("refused"))
    check("1e. requests.ConnectionError -> CONNECTION_ERROR", code == CONNECTION_ERROR,
          f"code={code}")

    # Falha de fetch via estagio (HTTP/ScraperError-like, nao-conexao).
    code, detail = classify_exception(RuntimeError("boom"), stage=FETCH_STAGE)
    check("1f. RuntimeError(fetch stage) -> FETCH_ERROR", code == FETCH_ERROR,
          f"code={code}")
    check("1g. detail legivel em fetch", "RuntimeError: boom" in detail, f"detail={detail!r}")

    code, detail = classify_exception(ValueError("bad"), stage=NORMALIZE_STAGE)
    check("1h. ValueError(normalize stage) -> NORMALIZATION_ERROR",
          code == NORMALIZATION_ERROR, f"code={code}")

    code, _ = classify_exception(ValueError("desconhecido"))
    check("1i. excecao desconhecida (sem stage) -> UNKNOWN", code == UNKNOWN,
          f"code={code}")

    # classificador com entrada inesperada nunca levanta (fallback obrigatorio).
    try:
        code, _ = classify_exception("uma string nao-excecao")
        check("1j. entrada invalida -> UNKNOWN (nao crasha)", code == UNKNOWN,
              f"code={code}")
    except Exception as exc:  # noqa: BLE001
        check("1j. entrada invalida -> UNKNOWN (nao crasha)", False, f"levantou {exc}")


# ---------------------------------------------------------------------------
# 2. fetch_worker: payload da queue ESTRUTURADO (mocks)
# ---------------------------------------------------------------------------

def test_fetch_worker_payload() -> None:
    print("== P1#7: payload da queue estruturado (fetch_worker) ==")
    import queue as queue_mod
    from unittest.mock import MagicMock, patch

    from internship_finder.collectors import ats_scraper

    company = make_company()
    q = queue_mod.Queue()

    # 2a. SUCESSO: payload continua ("ok", result)
    job_dict = {"id": "s:1", "source": "smartrecruiters:acme", "title": "Intern"}
    fake_scraper = MagicMock()
    fake_scraper.fetch.return_value = [object()]  # to_job e mockado abaixo
    fake_adapter = MagicMock()
    fake_adapter.to_job.return_value.to_dict.return_value = job_dict
    with patch.object(ats_scraper, "get_scraper", return_value=fake_scraper), \
         patch.object(ats_scraper, "AtsJobAdapter", return_value=fake_adapter), \
         patch.object(ats_scraper, "flush_cache"):
        ats_scraper.fetch_worker(company, timeout=10, include_descriptions=False, queue=q)
    status, payload = q.get()
    check("2a. sucesso -> ('ok', result)", status == "ok" and payload == [job_dict],
          f"payload={payload!r}")

    # 2b. ERRO DE FETCH: payload estruturado, sem texto livre como 1o campo
    q = queue_mod.Queue()
    fake_scraper = MagicMock()
    fake_scraper.fetch.side_effect = RuntimeError("boom")
    with patch.object(ats_scraper, "get_scraper", return_value=fake_scraper), \
         patch.object(ats_scraper, "AtsJobAdapter", return_value=MagicMock()), \
         patch.object(ats_scraper, "flush_cache"):
        ats_scraper.fetch_worker(company, timeout=10, include_descriptions=False, queue=q)
    item = q.get()
    check("2b. erro de fetch -> tupla 3 com '-error'", len(item) == 3 and item[0] == "-error",
          f"item={item!r}")
    check("2c. erro de fetch -> code estruturado", item[1] == FETCH_ERROR, f"code={item[1]!r}")
    check("2d. erro de fetch -> detail legivel", item[2] == "RuntimeError: boom",
          f"detail={item[2]!r}")
    check("2e. payload NAO e texto livre", not (isinstance(item, str)), "payload str?")

    # 2c. ERRO DE ADAPTACAO: NORMALIZATION_ERROR
    q = queue_mod.Queue()
    fake_scraper = MagicMock()
    fake_scraper.fetch.return_value = [object()]
    fake_adapter = MagicMock()
    fake_adapter.to_job.side_effect = ValueError("campo inesperado")
    with patch.object(ats_scraper, "get_scraper", return_value=fake_scraper), \
         patch.object(ats_scraper, "AtsJobAdapter", return_value=fake_adapter), \
         patch.object(ats_scraper, "flush_cache"):
        ats_scraper.fetch_worker(company, timeout=10, include_descriptions=False, queue=q)
    item = q.get()
    check("2f. erro de adaptacao -> '-error'", len(item) == 3 and item[0] == "-error",
          f"item={item!r}")
    check("2g. erro de adaptacao -> NORMALIZATION_ERROR", item[1] == NORMALIZATION_ERROR,
          f"code={item[1]!r}")
    check("2h. erro de adaptacao -> detail legivel", "campo inesperado" in item[2],
          f"detail={item[2]!r}")


# ---------------------------------------------------------------------------
# 3. collect_company: summary failed/timeout com code+detail
# ---------------------------------------------------------------------------

def test_collect_summary_code() -> None:
    print("== P1#7: collect_company summary com code ==")
    from unittest.mock import patch

    from internship_finder.collectors import ats_scraper

    def _run(side_effect) -> tuple[list, dict]:
        class _FakeCollector:
            def find_company(self, name):
                return [make_company()]
            def has_scraper(self, company):
                return True
        with patch.object(ats_scraper, "CompanyCollector", _FakeCollector), \
             patch.object(ats_scraper, "fetch_with_timeout", side_effect=side_effect):
            return ats_scraper.collect_company("Acme", timeout=10)

    # 3a. erro propagado como CollectionError -> failed com code
    jobs, summary = _run(lambda *a, **k: (_ for _ in ()).throw(CollectionError("FETCH_ERROR", "RuntimeError: boom")))
    check("3a. failed carrega (source, code, detail)",
          len(summary["failed"]) == 1 and summary["failed"][0][0] == "smartrecruiters:acme"
          and summary["failed"][0][1] == "FETCH_ERROR"
          and "RuntimeError: boom" in summary["failed"][0][2],
          f"failed={summary['failed']!r}")

    # 3b. timeout (CollectionError code==TIMEOUT) -> timeout com code
    jobs, summary = _run(lambda *a, **k: (_ for _ in ()).throw(CollectionError("TIMEOUT", "nao respondeu em 35s")))
    check("3b. timeout carrega (source, code, detail)",
          len(summary["timeout"]) == 1 and summary["timeout"][0][0] == "smartrecruiters:acme"
          and summary["timeout"][0][1] == "TIMEOUT"
          and "nao respondeu" in summary["timeout"][0][2],
          f"timeout={summary['timeout']!r}")

    # 3c. TimeoutError builtin -> timeout com code TIMEOUT (classificado)
    jobs, summary = _run(lambda *a, **k: (_ for _ in ()).throw(TimeoutError("pista")))
    check("3c. TimeoutError builtin -> timeout com code",
          len(summary["timeout"]) == 1 and summary["timeout"][0][1] == "TIMEOUT",
          f"timeout={summary['timeout']!r}")

    # 3d. excecao generica -> failed com UNKNOWN (fallback)
    jobs, summary = _run(lambda *a, **k: (_ for _ in ()).throw(ValueError("ops")))
    check("3d. excecao generica -> failed com UNKNOWN",
          len(summary["failed"]) == 1 and summary["failed"][0][1] == "UNKNOWN",
          f"failed={summary['failed']!r}")


# ---------------------------------------------------------------------------
# 4. _tenant_record com error_code + round-trip JSONL
# ---------------------------------------------------------------------------

def test_tenant_record_roundtrip() -> None:
    print("== P1#7: _tenant_record error_code + round-trip JSONL ==")
    from internship_finder.cli import _tenant_record
    from internship_finder.metrics import read_metrics, write_metrics

    ok = _tenant_record("runX", "Acme", "smartrecruiters:acme", "ok", 5, "1.0s")
    check("4a. ok sem error -> error_code null", ok.get("error_code") is None,
          f"error_code={ok['error_code']!r}")

    rec = _tenant_record(
        "runX", "Acme", "smartrecruiters:acme", "error", 0, None,
        "RuntimeError: boom", error_code="FETCH_ERROR",
    )
    check("4b. error carrega error_code", rec["error_code"] == "FETCH_ERROR",
          f"error_code={rec['error_code']!r}")
    check("4c. error legivel preservado", rec["error"] == "RuntimeError: boom",
          f"error={rec['error']!r}")

    timeout_rec = _tenant_record(
        "runX", "Acme", "successfactors:acme", "timeout", 0, None,
        "nao respondeu", error_code="TIMEOUT",
    )
    check("4d. timeout carrega error_code", timeout_rec["error_code"] == "TIMEOUT")

    # JSONL round-trip: error_code e error persistidos/relidos.
    path = Path(tempfile.mktemp(suffix=".jsonl"))
    write_metrics(path, [rec, timeout_rec, ok])
    records = read_metrics(path)
    path.unlink()
    tenants = [r for r in records if r["type"] == "tenant"]
    by_code = {r.get("error_code"): r for r in tenants}
    check("4e. round-trip: error_code+error persistidos",
          by_code.get("FETCH_ERROR") is not None
          and by_code["FETCH_ERROR"]["error"] == "RuntimeError: boom"
          and by_code.get("TIMEOUT") is not None
          and by_code["TIMEOUT"]["error"] == "nao respondeu",
          f"tenants={tenants!r}")
    check("4f. round-trip: ok sem error_code vira null",
          ok["error_code"] is None and by_code[None]["error"] is None)


# ---------------------------------------------------------------------------
# 5. CLI --companies: falha parcial -> exit 2 e registro com error_code
# ---------------------------------------------------------------------------

def test_cli_partial_failure_code() -> None:
    print("== P1#7: CLI falha parcial -> exit 2 e error_code no JSONL ==")
    from unittest.mock import patch

    from internship_finder import cli

    job_dict = {
        "id": "s:1", "source": "smartrecruiters:acme", "title": "Praktikum Einkauf",
        "company": "Acme", "url": "https://a/1", "location": "Berlin, DE",
        "collected_at": "2026-08-01T00:00:00Z",
    }

    def _collect_partial(name, **kw):
        summary = {
            "ok": [("smartrecruiters:acme", 1, "1.0s")],
            "empty": [],
            "timeout": [("successfactors:b", "TIMEOUT", "nao respondeu")],
            "failed": [("greenhouse:c", "CONNECTION_ERROR", "requests...ConnectionError")],
            "skipped": [],
            "not_found": False,
        }
        return [job_dict], summary

    tmp = tempfile.mkdtemp()
    out = f"{tmp}/jobs.json"
    metrics_path = f"{tmp}/metrics.jsonl"
    with patch.object(cli, "collect_company", side_effect=_collect_partial):
        rc = cli.main(["--companies", "Acme", "--output", out,
                       "--filter-output", f"{tmp}/eligible.json",
                       "--metrics", metrics_path])
    check("5a. falha parcial -> exit 2", rc == 2, f"rc={rc}")

    err_records = [
        r for r in read_metrics_lazy(metrics_path)
        if r.get("type") == "tenant" and r.get("status") in ("timeout", "error")
    ]
    codes = {r.get("error_code") for r in err_records}
    errs = {r.get("error") for r in err_records}
    check("5b. JSONL tem error_code TIMEOUT e CONNECTION_ERROR",
          "TIMEOUT" in codes and "CONNECTION_ERROR" in codes,
          f"codes={codes}")
    check("5c. error legivel preservado no JSONL",
          any("nao respondeu" in e for e in errs) and
          any("ConnectionError" in e for e in errs),
          f"errs={errs}")


def read_metrics_lazy(path: str) -> list[dict]:
    recs: list[dict] = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


# ---------------------------------------------------------------------------
# 6. regressao: health consumindo error_code (P1 #6)
# ---------------------------------------------------------------------------

def test_health_with_error_code() -> None:
    print("== P1#6 regressao: build_health_report com error_code ==")
    from internship_finder.cli import _tenant_record
    from internship_finder.health import build_health_report

    rows = [
        _tenant_record("r1", "Acme", "smartrecruiters:acme", "ok", 10, "0.4s"),
        _tenant_record("r1", "Acme", "smartrecruiters:acme", "error", 0, None,
                       "RuntimeError: boom", error_code="FETCH_ERROR"),
        _tenant_record("r1", "Acme", "smartrecruiters:acme", "timeout", 0, None,
                       "nao respondeu", error_code="TIMEOUT"),
        _tenant_record("r1", "Acme", "smartrecruiters:acme", "ok", 12, "0.5s"),
    ]
    # garante ordenacao por run_id/timestamp senao as linhas podem embaralhar:
    # build_health_report ordena apenas por _sort_key; como tudo tem o mesmo
    # run_id, usamos timestamps crescentes explicitos para previsibilidade.
    for i, r in enumerate(rows):
        r["timestamp"] = f"2026-08-0{i + 1}T00:00:00+00:00"
    rows.sort(key=lambda r: r["timestamp"])

    warnings: list[str] = []
    report = build_health_report(rows, warnings)
    check("6a. relatorio serializavel (dict)", isinstance(report, dict))

    # o tenant error_code nao confunde a contagem: 4 linhas, 2 ok / 2 falhas.
    src = report["sources"][0]
    check("6b. sources conta ok_runs=2 num total de 4",
          src["total_runs"] == 4 and src["ok_runs"] == 2, f"{src}")
    check("6c. ats resume com error_code presente (nao quebra)",
          any(s["last_status"] in ("timeout", "error") for s in report["sources"])
          or "ats" in report, f"rep_keys={sorted(report.keys())}")


# ---------------------------------------------------------------------------

def main() -> int:
    test_classify_by_type()
    test_fetch_worker_payload()
    test_collect_summary_code()
    test_tenant_record_roundtrip()
    test_cli_partial_failure_code()
    test_health_with_error_code()

    if FAILURES:
        print("\nFALHAS:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nTUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())