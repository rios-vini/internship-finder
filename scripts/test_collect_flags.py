"""Testes standalone — P3 #20 (ACH-14/ACH-18): flags de coleta e CSV.

Cobre:

- ``--limit`` (collect_company): slicing por TENANT aplicado APOS a coleta;
  ``limit=0`` = sem limite; ``limit`` valido por tenant (nao por nome de
  empresa). Mocks obrigatorios (sem rede, sem data/).
- CLI: ``--timeout <= 0`` e ``--limit < 0`` -> erro claro (SystemExit 2),
  ANTES de qualquer coleta; valores validos NAO sao bloqueados.
- ``save_outputs`` (contrato do CSV, ACH-18): coluna ``remote`` presente
  (antes ausente em 38.038/38.038 linhas de jobs.csv e 224/224 de
  eligible_jobs.csv); ``description``/``raw``/``score_breakdown`` ficam de
  fora de proposito (JSON = fonte completa); JSON mantem todos os campos.

Nao depende de ``data/`` e nao faz coleta real; usa ``tempfile`` e limpa ao
final. Padrao dos demais scripts: ``[OK]``/``[FAIL]`` e termina com
``TUDO OK`` (exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_collect_flags.py
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder import cli  # noqa: E402
from internship_finder.cli import save_outputs  # noqa: E402
from internship_finder.collectors import ats_scraper  # noqa: E402
from internship_finder.models.company import Company  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def make_company(ats: str, slug: str, name: str = "Acme") -> Company:
    return Company(name=name, ats=ats, slug=slug, query=name)


def job_dict(src: str, n: int) -> dict:
    return {
        "id": f"{src}:{n}",
        "source": src,
        "title": f"Intern {n}",
        "company": "Acme",
        "url": f"https://acme.example/job/{n}",
        "collected_at": "2026-09-05T20:43:07+00:00",
    }


EMPTY_SUMMARY = {
    "ok": [], "empty": [], "timeout": [], "failed": [], "skipped": [],
    "not_found": False,
}


# ---------------------------------------------------------------------------
# 1. collect_company: --limit por tenant, pos-coleta
# ---------------------------------------------------------------------------

def test_limit_semantics() -> None:
    print("== ACH-14: limit por tenant (pos-coleta) ==")
    from unittest.mock import patch

    c1 = make_company("smartrecruiters", "acme-a")
    c2 = make_company("smartrecruiters", "acme-b")

    class _FakeCollector:
        def find_company(self, name):
            return [c1, c2]

        def has_scraper(self, company):
            return True

    def _run(limit: int) -> tuple[list, dict]:
        with patch.object(ats_scraper, "CompanyCollector", _FakeCollector), \
             patch.object(
                 ats_scraper, "fetch_with_timeout",
                 return_value=[job_dict(c1.source, 1), job_dict(c1.source, 2),
                               job_dict(c2.source, 3)],
             ):
            return ats_scraper.collect_company("Acme", timeout=10, limit=limit)

    # Sem limite (0 = default): tudo que voltou do fetch, dos 2 tenants.
    jobs, summary = _run(limit=0)
    check("limit=0: coleta os 2 tenants sem corte (3+3)",
          len(jobs) == 6 and len(summary["ok"]) == 2
          and summary["ok"][0][0] == c1.source and summary["ok"][1][0] == c2.source)

    # limit=2: 2 vagas POR TENANT (4 no total), nao 2 no total.
    jobs, summary = _run(limit=2)
    check("limit=2: 2 vagas por tenant (4 total)",
          len(jobs) == 4 and len(summary["ok"]) == 2
          and summary["ok"][0][1] == 2 and summary["ok"][1][1] == 2)

    # limit=1: 1 vaga por tenant.
    jobs, _ = _run(limit=1)
    check("limit=1: 1 vaga por tenant (2 total)", len(jobs) == 2)

    # limit aplicado APOS o fetch (fetch retorna intacto; corte e no resultado).
    with patch.object(ats_scraper, "CompanyCollector", _FakeCollector), \
         patch.object(
             ats_scraper, "fetch_with_timeout",
             return_value=[job_dict(c1.source, 1), job_dict(c1.source, 2),
                           job_dict(c2.source, 3)],
         ) as mocked_fetch:
        ats_scraper.collect_company("Acme", timeout=10, limit=1)
        check("limit nao reduz o fetch (coleta ocorre antes do corte)",
              mocked_fetch.call_count == 2)


# ---------------------------------------------------------------------------
# 2. CLI: validacao de --timeout/--limit (erro claro, antes de coletar)
# ---------------------------------------------------------------------------

def test_cli_flag_validation() -> None:
    print("== ACH-14: CLI rejeita --timeout <= 0 e --limit < 0 ==")
    # A validacao roda ANTES da coleta (mesmo ponto da validacao de
    # --country, P2 #15): nao toca rede, nao le input.
    for args, token in (
        (["--companies", "Acme", "--timeout", "0"], "--timeout"),
        (["--companies", "Acme", "--timeout", "-5"], "--timeout"),
        (["--companies", "Acme", "--limit", "-1"], "--limit"),
        (["--timeout", "0", "--input", "/tmp/x.json"], "--timeout"),
    ):
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                cli.main(args + ["--output", "/tmp/p3_20_out.json",
                             "--metrics", "/tmp/p3_20_m.jsonl"])
        except SystemExit as exc:
            check(f"cli {args[1:]} -> SystemExit 2", exc.code == 2)
            msg = err.getvalue().lower()
            check(f"cli {args[1:]} -> mensagem clara cita a flag",
                  token.lower() in msg and ">" in msg or ">=" in msg)
        else:
            check(f"cli {args[1:]} -> SystemExit 2", False)

    # Valores validos NAO dispararram a validacao: com coleta mockada, o erro
    # passa a ser de fluxo ("nenhuma vaga", exit 1) — nao da flag.
    from unittest.mock import patch

    err = io.StringIO()
    try:
        with patch.object(cli, "collect_company",
                          return_value=([], EMPTY_SUMMARY)), \
             contextlib.redirect_stderr(err):
            rc = cli.main(["--companies", "Acme", "--timeout", "10", "--limit", "2",
                           "--output", "/tmp/p3_20_v.json",
                           "--metrics", "/tmp/p3_20_v.jsonl",
                           "--filter-output", "/tmp/p3_20_vf.json"])
    except SystemExit:
        check("cli --timeout 10 --limit 2 validos: sem SystemExit", False)
    else:
        check("cli --timeout 10 --limit 2 validos: sem SystemExit", True)
        check("cli validos: fluxo segue (exit 1 = nenhuma vaga, nao da flag)",
              rc == 1 and "--timeout" not in err.getvalue()
              and "--limit" not in err.getvalue())


# ---------------------------------------------------------------------------
# 3. save_outputs: contrato do CSV (ACH-18)
# ---------------------------------------------------------------------------

def test_csv_contract() -> None:
    print("== ACH-18: CSV ganha 'remote'; JSON segue completo ==")
    jobs = [
        {"id": "s:1", "source": "smartrecruiters:acme", "title": "Intern A",
         "company": "Acme", "location": "Remote (Germany)", "country": "de",
         "country_iso": "de", "remote": True, "url": "https://a/j1",
         "description": "desc A", "raw": {"foo": "bar"},
         "collected_at": "2026-09-05T20:43:07+00:00"},
        {"id": "s:2", "source": "smartrecruiters:acme", "title": "Intern B",
         "company": "Acme", "location": "Stuttgart", "country": "de",
         "country_iso": "de", "remote": False, "url": "https://a/j2",
         "score": 3.5, "score_breakdown": {"area": 1.0},
         "collected_at": "2026-09-05T20:43:07+00:00"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "jobs.json"
        save_outputs(jobs, out)
        csv_path = out.with_suffix(".csv")

        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        header = list(rows[0].keys()) if rows else []

        check("CSV tem a coluna 'remote'", "remote" in header)
        check("CSV preserva remote True", rows[0]["remote"] == "True")
        check("CSV preserva remote False", rows[1]["remote"] == "False")
        check("CSV sem 'description' (tabular)", "description" not in header)
        check("CSV sem 'raw' (aninhado)", "raw" not in header)
        check("CSV sem 'score_breakdown' (aninhado)",
              "score_breakdown" not in header)
        check("CSV mantem 'score' (escalar)", "score" in header)

        # JSON segue COMPLETO (fonte de verdade): todos os campos presentes.
        saved = json.loads(out.read_text(encoding="utf-8"))
        check("JSON preserva description/raw/score_breakdown",
              saved[0]["description"] == "desc A" and saved[0]["raw"] == {"foo": "bar"}
              and saved[1]["score_breakdown"] == {"area": 1.0})


def main() -> int:
    test_limit_semantics()
    test_cli_flag_validation()
    test_csv_contract()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())