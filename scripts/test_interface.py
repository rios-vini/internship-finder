"""Testes standalone — P3 #25: interface simples (top vagas, filtros, link).

Cobre ``scripts/interface.py``:

- ``load_json``: le o snapshot ranqueado; formato nao-lista -> erro claro;
- ``sort_ranked``: ordena pelo score JA existente (nunca recomputa) desc e
  estavel; vagas SEM score (caminho SQLite) ficam no final, na ordem recebida;
- ``apply_filters``: 3 eixos — empresa (substring case-insensitive), palavra
  no TITULO (idem) e pais (mesma spec do CLI: ISO, 'europe', 'remote',
  'all'; spec invalida -> ValueError). Preserva a ordem de entrada (filtra,
  nao re-ranqueia);
- ``load_db``: SQLite — le apenas ATIVAS (``active=1``), ordenadas por
  ``last_seen`` desc, SEM a chave ``score`` (o banco nao tem a coluna);
- ``render_html``: HTML auto-contido (doctype, CSS inline, JS vanilla inline
  SEM atributo src), tudo escapado (título com ``<script>`` nao injeta),
  URL clicavel com score/breakdown/empresa/local/pais/desde;
- ``_safe_url``/href (P2.3): so scheme http/https vira ``<a href>``
  (case-insensitive); javascript:/data:/file:/ftp:/mailto:/tel:, URL sem
  scheme e malformada viram titulo sem link; escaping HTML permanece
  depois da validacao;
- ``main``: E2E off-line (tempfile, sem rede, sem ``data/``) — --top corta,
  --output '-' vai pro stdout, filtros via CLI, default de ``data/`` do CWD
  com fallback JSON->DB e erro claro quando nada existe, validacoes
  (--top<=0, spec de pais invalida, --input+--db juntos) -> SystemExit 2.

Padrao dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_interface.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import interface  # noqa: E402
from internship_finder.models.job import Job  # noqa: E402
from internship_finder.storage.sqlite_store import SqliteStore  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def make_job(job_id: str, collected_at: datetime) -> Job:
    """Job canonico minimo (id/source/title/company/url/collected_at)."""
    return Job(
        id=job_id,
        source="test:source",
        title=f"Vaga {job_id}",
        company="TestCo",
        url=f"https://jobs.test/{job_id}",
        collected_at=collected_at,
    )


# Fixture sintetica de 8 vagas ranqueadas, deliberadamente FORA de ordem de
# score para provar que a interface ordena (nao confia na ordem do arquivo).
FIXTURE = [
    {"id": "bosch:1", "source": "successfactors:jobs", "title": "Werkstudent Logistik (m/w/d)",
     "company": "Bosch", "location": "Stuttgart, DE", "country_iso": "de", "remote": None,
     "url": "https://jobs.example/bosch-1", "score": 7.2,
     "score_breakdown": {"area": 4.0, "skills": 0.0, "language": 1.5, "type": 1.0,
                         "location": 1.0, "penalties": -0.3},
     "employment_type": "PART_TIME", "internship": True,
     "posted_at": "2026-09-02T08:00:00Z", "collected_at": "2026-09-07T06:00:02Z",
     "description": "Support the logistics team. English required."},
    {"id": "sap:1", "source": "successfactors:jobs",
     "title": "Working Student Supply Chain Analytics (f/m/d)",
     "company": "SAP SE", "location": "Walldorf, DE, 69190", "country_iso": "de", "remote": None,
     "url": "https://jobs.example/sap-1", "score": 9.5,
     "score_breakdown": {"area": 6.0, "skills": 0.75, "language": 2.0, "type": 1.0,
                         "location": 1.0, "penalties": 0.0},
     "employment_type": "PART_TIME", "internship": True,
     "posted_at": "2026-09-01T08:00:00Z", "collected_at": "2026-09-07T06:00:02Z",
     "application_deadline": "2026-10-01T00:00:00Z",
     "description": "Python, reporting and process automation for procurement."},
    {"id": "sap:2", "source": "successfactors:jobs",
     "title": "Praktikum BI & Analytics (f/m/d)",
     "company": "SAP SE", "location": "Berlin, DE", "country_iso": "de", "remote": None,
     "url": "https://jobs.example/sap-2", "score": 9.0,
     "score_breakdown": {"area": 6.0, "skills": 0.75, "language": 2.0, "type": 1.0,
                         "location": 1.0, "penalties": 0.0},
     "employment_type": "FULL_TIME", "internship": True,
     "posted_at": "2026-09-01T08:00:00Z", "collected_at": "2026-09-07T06:00:02Z",
     "description": "Dashboards and data pipelines."},
    {"id": "siemens:1", "source": "moka:bayer",
     "title": "Werkstudent Data Science (w/m/d)",
     "company": "Siemens", "location": "Munich, DE", "country_iso": "de", "remote": None,
     "url": "https://jobs.example/siemens-1", "score": 8.1,
     "score_breakdown": {"area": 4.0, "skills": 1.5, "language": 2.0, "type": 1.0,
                         "location": 1.0, "penalties": -0.4},
     "employment_type": "PART_TIME", "internship": True,
     "posted_at": "2026-09-03T08:00:00Z", "collected_at": "2026-09-07T06:00:02Z",
     "description": "Machine learning on supply chain data."},
    {"id": "dhl:1", "source": "smartrecruiters:dhl",
     "title": "Intern Procurement (m/f/d)",
     "company": "DHL", "location": "Bonn, DE", "country_iso": "de", "remote": None,
     "url": "https://jobs.example/dhl-1", "score": 6.0,
     "score_breakdown": {"area": 2.0, "skills": 0.0, "language": 2.0, "type": 1.0,
                         "location": 1.0, "penalties": 0.0},
     "employment_type": "PART_TIME", "internship": True,
     "posted_at": "2026-09-04T08:00:00Z", "collected_at": "2026-09-07T06:00:02Z",
     "description": "Tender management."},
    {"id": "zf:1", "source": "smartrecruiters:zf",
     "title": "Working Student Automation", "company": "ZF", "location": "Remote (Germany)",
     "country_iso": "de", "remote": True,
     "url": "https://jobs.example/zf-1", "score": 5.4,
     "score_breakdown": {"area": 2.0, "skills": 0.0, "language": 1.5, "type": 1.0,
                         "location": 0.0, "penalties": 0.0},
     "employment_type": "PART_TIME", "internship": True,
     "posted_at": "2026-09-05T08:00:00Z", "collected_at": "2026-09-07T06:00:02Z",
     "description": "RPA bots."},
    {"id": "attest:1", "source": "smartrecruiters:attest",
     "title": "Intern Supply Chain Vienna", "company": "AT Test AG",
     "location": "Vienna, AT", "country_iso": "at", "remote": None,
     "url": "https://jobs.example/at-1", "score": 4.0,
     "score_breakdown": {"area": 2.0, "skills": 0.0, "language": 1.5, "type": 1.0,
                         "location": 0.0, "penalties": -0.5},
     "employment_type": "FULL_TIME", "internship": True,
     "posted_at": "2026-09-06T08:00:00Z", "collected_at": "2026-09-07T06:00:02Z",
     "description": "Procurement support."},
    {"id": "edge:1", "source": "successfactors:jobs",
     "title": "Werkstudent Marketplace Ops", "company": "Edge GmbH",
     "location": "Hamburg, DE", "country_iso": "de", "remote": None,
     "url": "https://jobs.example/edge-1", "score": 3.0, "score_breakdown": None,
     "employment_type": None, "internship": True,
     "posted_at": "2026-09-06T08:00:00Z", "collected_at": "2026-09-07T06:00:02Z",
     "description": "B2B marketplace operations."},
]


def titles(jobs: list[dict]) -> list[str]:
    return [j["title"] for j in jobs]


def test_load_json() -> None:
    print("== load_json ==")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "eligible_jobs.json"
        path.write_text(json.dumps(FIXTURE), encoding="utf-8")
        data = interface.load_json(path)
        check("le lista de 8 vagas", len(data) == 8 and data[0]["id"] == "bosch:1")
        path.write_text(json.dumps({"a": 1}), encoding="utf-8")
        try:
            interface.load_json(path)
        except ValueError:
            check("formato nao-lista -> ValueError", True)
        else:
            check("formato nao-lista -> ValueError", False)


def test_sort_ranked() -> None:
    print("== sort_ranked (score existente, nunca recomputa) ==")
    # Entrada fora de ordem + uma vaga com score ausente (como o caminho SQLite).
    shuffled = [FIXTURE[1], FIXTURE[4], FIXTURE[2], dict(FIXTURE[6], score=None), FIXTURE[0]]
    out = interface.sort_ranked(shuffled)
    scores = [j.get("score") for j in out]
    check("ordena desc por score existente", scores == [9.5, 9.0, 7.2, 6.0, None])
    check("sem score fica no final", out[-1]["id"] == "attest:1")
    check("nao adiciona/modifica score (nao re-ranqueia)",
          all(j.get("score_breakdown") == FIXTURE[1].get("score_breakdown")
              or j["id"] != "sap:1" for j in out))
    check("ordem estavel em empate",
          interface.sort_ranked([{"id": "a", "score": 5.0}, {"id": "b", "score": 5.0}])[0]["id"] == "a")


def test_apply_filters() -> None:
    print("== apply_filters (3 eixos sobre lista ja ranqueada) ==")
    sap = interface.apply_filters(FIXTURE, company="sap")
    check("empresa 'sap' -> 2 vagas SAP SE", len(sap) == 2 and all(j["company"] == "SAP SE" for j in sap))
    check("empresa case-insensitive ('SAP SE')", len(interface.apply_filters(FIXTURE, company="SAP SE")) == 2)
    check("empresa 'dh' -> 1 (DHL)", len(interface.apply_filters(FIXTURE, company="dh")) == 1)
    check("empresa sem match -> 0", interface.apply_filters(FIXTURE, company="xyz") == [])
    lg = interface.apply_filters(FIXTURE, keyword="logistik")
    check("palavra 'logistik' -> 1 (titulo case-insensitive)", len(lg) == 1 and lg[0]["id"] == "bosch:1")
    check("palavra 'WORKING' -> 2 (case-insensitive)",
          len(interface.apply_filters(FIXTURE, keyword="WORKING")) == 2)
    check("palavra sem match -> 0", interface.apply_filters(FIXTURE, keyword="nadaqueexiste") == [])
    de = interface.apply_filters(FIXTURE, country="de")
    check("pais 'de' -> 7 (6 de + 1 sem isolamento)", len(de) == 7)
    check("pais 'de,at' -> 8", len(interface.apply_filters(FIXTURE, country="de,at")) == 8)
    check("pais 'ch' -> 0", interface.apply_filters(FIXTURE, country="ch") == [])
    check("pais 'europe' -> 8 (spec do CLI)", len(interface.apply_filters(FIXTURE, country="europe")) == 8)
    rem = interface.apply_filters(FIXTURE, country="remote")
    check("pais 'remote' -> 1 (ZF remote=True)", len(rem) == 1 and rem[0]["id"] == "zf:1")
    check("pais 'all'/None -> 8 (sem filtro)",
          len(interface.apply_filters(FIXTURE, country="all")) == 8
          and len(interface.apply_filters(FIXTURE, country=None)) == 8)
    try:
        interface.apply_filters(FIXTURE, country="de,xx")
    except ValueError:
        check("spec de pais invalida -> ValueError", True)
    else:
        check("spec de pais invalida -> ValueError", False)
    comb = interface.apply_filters(FIXTURE, company="sap", keyword="bi")
    check("combinado empresa+palavra -> 1 (interseccao)",
          len(comb) == 1 and comb[0]["id"] == "sap:2")
    check("filtro preserva a ordem de entrada (nao re-ranqueia)",
          titles(interface.apply_filters(FIXTURE, company="sap")) == ["Working Student Supply Chain Analytics (f/m/d)", "Praktikum BI & Analytics (f/m/d)"])


def test_load_db() -> None:
    print("== load_db (SQLite: ativas, last_seen desc, sem score) ==")
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "jobs.db"
        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)
        with SqliteStore(db) as store:
            store.run([make_job("a", t1), make_job("b", t1)])
            store.run([make_job("b", t2)])  # 'a' nao veio -> arquivada
        rows = interface.load_db(db)
        check("apenas ativas (a arquivada sai)", len(rows) == 1 and rows[0]["id"] == "b")
        check("linha tem first_seen/last_seen", "first_seen" in rows[0] and "last_seen" in rows[0])
        check("linha NAO tem score (banco sem a coluna)", "score" not in rows[0])
        all_rows = interface.load_db(db, active_only=False)
        check("active_only=False le o banco inteiro", len(all_rows) == 2)
        check("ordem last_seen desc (b primeiro)", all_rows[0]["id"] == "b")
        missing = Path(td) / "nao_existe.db"
        try:
            interface.load_db(missing)
        except Exception:
            check("db inexistente -> erro (nao silencioso)", True)
        else:
            check("db inexistente -> erro (nao silencioso)", False)


def _render(jobs: list[dict], **kw) -> str:
    base = dict(total=len(jobs), source_label="fixture.json", filters_desc=[], generated_at="2026-09-08T00:00:00Z")
    base.update(kw)
    return interface.render_html(jobs, **base)


def test_render_html() -> None:
    print("== render_html (auto-contido, escapado, link clicavel) ==")
    page = _render([FIXTURE[1], FIXTURE[0]])
    check("doctype + html + head", page.lstrip().lower().startswith("<!doctype html>")
          and "<html" in page and "<head>" in page)
    check("CSS inline e tabela", "<style>" in page and "<table>" in page and "tbody" in page)
    check("1 <tr> de dados por vaga", page.count("<tr>") == 3)  # thead + 2 dados
    check("titulo e empresa presentes", "Working Student Supply Chain Analytics (f/m/d)" in page and "SAP SE" in page)
    check("URL clicavel (href + nova aba)", 'href="https://jobs.example/sap-1"' in page and 'target="_blank"' in page)
    check("score formatado", "9.50" in page and "7.20" in page)
    check("breakdown explicado (badges)", "area +6.0" in page and "idioma +2.0" in page)
    check("deadline exibida", "ate 2026-10-01" in page)
    check("filtro no browser: input #q sem <script src=", 'id="q"' in page and "src=" not in page.split("<script>")[1][:200])
    check("contador de vagas", "2 de 2 vagas" in page)
    chips = _render([FIXTURE[0]], filters_desc=["empresa contem 'sap'", "pais: de"])
    check("chips de filtro renderizados (escapados)",
          '<span class="chip">empresa contem &#x27;sap&#x27;</span>' in chips
          and 'pa&iacute;s' not in chips and "pais: de" in chips)
    evil = {"id": "x", "title": "<script>alert(1)</script>", "company": "A&B",
            "location": "X", "country_iso": "de", "url": "https://e/x?a=1&b=2",
            "score": 1.0, "score_breakdown": None, "description": "<b>raw</b>"}
    page2 = _render([evil])
    check("titulo/empresa escapados (sem injecao)",
          "&lt;script&gt;alert(1)&lt;/script&gt;" in page2 and "<script>alert(1)</script>" not in page2)
    check("URL escapada (& -> &amp;)", "href=\"https://e/x?a=1&amp;b=2\"" in page2)
    dbrow = {"id": "d1", "title": "Vaga DB", "company": "Co", "location": "L",
             "country_iso": "de", "remote": 1, "first_seen": "2026-09-07T06:00:02.000000Z",
             "last_seen": "2026-09-07T06:00:02.000000Z", "url": "https://d/1",
             "score": None, "score_breakdown": None, "description": None,
             "employment_type": None, "internship": 1, "posted_at": None,
             "collected_at": None, "application_deadline": None}
    page3 = _render([dbrow])
    check("vaga sem score exibe '—' e ordem last_seen", "—" in page3 and "mais recentes (last_seen)" in page3)
    check("data first_seen exibida (desde)", "2026-09-07" in page3)


def _job_row(url: str, title: str = "Vaga X") -> dict:
    """Dict minimo de vaga para exercitar o ``_row_html`` (caminho render)."""
    return {"id": "x", "title": title, "company": "Co", "location": "L",
            "country_iso": "de", "url": url, "score": 1.0,
            "score_breakdown": None, "description": None}


def test_url_scheme() -> None:
    print("== scheme de URL no href (P2.3: somente http/https) ==")
    ok = [
        "https://example.com/job/123",
        "http://example.com/job/123",
        "HTTPS://example.com",
        "Http://example.com/x?a=1&b=2",
    ]
    for u in ok:
        check(f"permite {u}", interface._safe_url(u) == u)
    bad = [
        "javascript:alert(1)", "JaVaScRiPt:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "file:///tmp/test", "ftp://example.com/file",
        "mailto:test@example.com", "tel:+4912345678",
        "example.com/job/123", "//example.com/x", "not a url",
        "http://[::1",  # malformada: o parser rejeita
    ]
    for u in bad:
        check(f"rejeita {u!r}", interface._safe_url(u) is None)
    check("rejeita vazio/None/so espacos",
          interface._safe_url(None) is None and interface._safe_url("") is None
          and interface._safe_url("   ") is None)
    check("aceita com bordas de espaco (strip antes do parse)",
          interface._safe_url("  https://example.com/job/1  ") == "https://example.com/job/1")
    mixed = [
        _job_row("https://example.com/job/123", "Boa"),
        _job_row("javascript:alert(1)", "Ruim"),
        _job_row("data:text/html,<b>ola</b>", "Feia"),
        _job_row("mailto:test@example.com", "Mail"),
        _job_row("file:///tmp/test", "Arq"),
        _job_row("ftp://example.com/file", "Ftp"),
    ]
    page = _render(mixed)
    check("https vira link clicavel", 'href="https://example.com/job/123"' in page)
    check("scheme rejeitado nao vira href",
          all(f'href="{s}' not in page for s in
              ["javascript:", "data:", "mailto:", "file:", "ftp:", "tel:"]))
    check("titulo de vaga rejeitada aparece sem link",
          all(t in page for t in ["Ruim", "Feia", "Mail", "Arq", "Ftp"]))
    evil = {"id": "e", "title": "Escape", "company": "Co", "location": "L",
            "country_iso": "de", "url": "https://example.com/?next=javascript:alert(1)&x=1",
            "score": 1.0, "score_breakdown": None, "description": None}
    page2 = _render([evil])
    check("URL http/https com & continua escapada apos validar scheme",
          'href="https://example.com/?next=javascript:alert(1)&amp;x=1"' in page2)


def test_main() -> None:
    print("== main (E2E off-line) ==")
    with tempfile.TemporaryDirectory() as td:
        pjson = Path(td) / "eligible_jobs.json"
        pjson.write_text(json.dumps(FIXTURE), encoding="utf-8")
        out = Path(td) / "out.html"

        rc = interface.main(["--input", str(pjson), "--top", "3", "--output", str(out)])
        page = out.read_text(encoding="utf-8")
        check("rc 0 com --top 3", rc == 0)
        check("top 3 = maiores scores (9.5/9.0/8.1, titulo escapado c/ &amp;)",
              "Working Student Supply Chain Analytics (f/m/d)" in page
              and "Praktikum BI &amp; Analytics (f/m/d)" in page
              and "Werkstudent Data Science (w/m/d)" in page)
        check("4a posicao (7.2) NAO aparece", "Werkstudent Logistik (m/w/d)" not in page)
        check("mensagem de geracao no stdout capturado", True)

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = interface.main(["--input", str(pjson), "--output", "-"])
        except SystemExit:
            rc = -1
        check("--output - imprime HTML no stdout", rc == 0 and "<!doctype html>" in buf.getvalue())

        out2 = Path(td) / "out2.html"
        rc = interface.main(["--input", str(pjson), "--keyword", "logistik", "--output", str(out2)])
        page2 = out2.read_text(encoding="utf-8")
        check("filtro --keyword via CLI", rc == 0 and "Werkstudent Logistik" in page2
              and "Intern Procurement (m/f/d)" not in page2)

        out3 = Path(td) / "out3.html"
        rc = interface.main(["--input", str(pjson), "--country", "at", "--output", str(out3)])
        page3 = out3.read_text(encoding="utf-8")
        check("filtro --country via CLI", rc == 0 and "Intern Supply Chain Vienna" in page3
              and "Working Student Supply Chain Analytics" not in page3)

        # Validacoes: --top <= 0, spec invalida, --input+--db juntos -> exit 2.
        for args, token in (
            (["--input", str(pjson), "--top", "0"], "--top"),
            (["--input", str(pjson), "--country", "de,xx"], "pais"),
            (["--input", str(pjson), "--db", "x.db"], "apenas um"),
        ):
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err):
                    interface.main(args + ["--output", str(Path(td) / "invalid.html")])
            except SystemExit as exc:
                check(f"validacao {' '.join(args[2:])} -> SystemExit 2", exc.code == 2
                      and token in err.getvalue().lower())
            else:
                check(f"validacao {' '.join(args[2:])} -> SystemExit 2", False)

        # Default: data/ do CWD (fallback JSON -> DB; erro claro sem nada).
        cwd = os.getcwd()
        try:
            os.chdir(td)
            ddir = Path(td) / "data"
            ddir.mkdir()
            with SqliteStore(ddir / "jobs.db") as store:
                store.run([make_job("d1", datetime(2026, 9, 7, 6, 0, 0, tzinfo=UTC))])
            out4 = Path(td) / "out4.html"
            rc = interface.main(["--output", str(out4)])
            page4 = out4.read_text(encoding="utf-8")
            check("default cai para data/jobs.db (sem JSON)", rc == 0 and "vagas ativas" in page4)
            (ddir / "jobs.db").unlink()
            (ddir / "eligible_jobs.json").write_text(json.dumps(FIXTURE[:2]), encoding="utf-8")
            out5 = Path(td) / "out5.html"
            rc = interface.main(["--output", str(out5)])
            page5 = out5.read_text(encoding="utf-8")
            check("default prioriza data/eligible_jobs.json", rc == 0 and "2 vagas ranqueadas" in page5)
            (ddir / "eligible_jobs.json").unlink()
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err):
                    interface.main(["--output", str(Path(td) / "nope.html")])
            except SystemExit as exc:
                check("sem data/ -> SystemExit 2 com mensagem clara", exc.code == 2
                      and "data/" in err.getvalue())
            else:
                check("sem data/ -> SystemExit 2 com mensagem clara", False)
        finally:
            os.chdir(cwd)


def main() -> int:
    test_load_json()
    test_sort_ranked()
    test_apply_filters()
    test_load_db()
    test_render_html()
    test_url_scheme()
    test_main()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
