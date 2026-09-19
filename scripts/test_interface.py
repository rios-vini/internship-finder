"""Testes standalone — P3 #25 + Fase 3: interface do ranking (filtros, ordenação).

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
- ``render_html`` (Fase 3): pagina auto-contida (doctype, CSS inline, JS
  vanilla inline SEM atributo src), tudo escapado (titulo com ``<script>``
  nao injeta), URL clicavel com score/breakdown/empresa/local/tipo/pais/
  desde, resumo no topo (total/empresas/score max/top30/atualizado),
  data-attributes por linha para o JS client-side, badge Top 30, botao
  "abrir" e bloco "por que este score" com as componentes reais;
- ``_safe_url``/href (P2.3): so scheme http/https vira ``<a href>``
  (case-insensitive); javascript:/data:/file:/ftp:/mailto:/tel:, URL sem
  scheme e malformada viram titulo sem link; escaping HTML permanece
  depois da validacao;
- nucleo JS client-side (``if_filter_sort``/``if_match``/``if_sorter``):
  executado DE VERDADE em node quando disponivel (CI ubuntu tem node
  pre-instalado) — filtros por texto/empresa/tipo/pais/score minimo e as
  6 ordenacoes; sem node, o bloco e SKIP com mensagem;
- bloco REAL (Fase 3): com ``data/eligible_jobs.json`` presente, gera a
  pagina publica (mesmo comando do publish_pages) e confirma que TODAS as
  vagas elegiveis aparecem, Top 30 correto, data-rank == posicao do
  pipeline, resumo coerente e gate de seguranca (nada privado publicado).
  Sem ``data/``, SKIP (padrao do projeto para runner limpo);
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
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import interface  # noqa: E402
import publish_pages  # noqa: E402 (gate de seguranca do bloco real)
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

# Posicao (rank) no ranking por score desc — ordem esperada em toda a suite.
RANK_BY_ID = {
    "sap:1": 1, "sap:2": 2, "siemens:1": 3, "bosch:1": 4,
    "dhl:1": 5, "zf:1": 6, "attest:1": 7, "edge:1": 8,
}


def titles(jobs: list[dict]) -> list[str]:
    return [j["title"] for j in jobs]


def _core_row(job: dict, rank: int) -> dict:
    """Linha como o DOM glue da pagina enxerga (dataset -> objeto do nucleo JS)."""
    score = job.get("score")
    added = interface._added_date(job)
    return {
        "title": str(job.get("title") or ""),
        "company": str(job.get("company") or ""),
        "location": str(job.get("location") or ""),
        "type": str(job.get("employment_type") or ""),
        "country": str(job.get("country_iso") or ""),
        "score": str(score) if isinstance(score, (int, float)) else "",
        "rank": rank,
        "date": "" if added == "—" else added,
    }


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
    print("== render_html (Fase 3: auto-contido, escapado, resumo, data-attrs) ==")
    fx = interface.sort_ranked(FIXTURE)  # como o main faz antes de renderizar
    page = _render(fx[:3])  # sap1 9.5, sap2 9.0, siemens 8.1
    check("doctype + html + head", page.lstrip().lower().startswith("<!doctype html>")
          and "<html" in page and "<head>" in page)
    check("CSS inline e tabela", "<style>" in page and "<table>" in page and "tbody" in page)
    check("3 linhas de dados (thead + 3)", page.count("<tr class=") == 3 and page.count("</tr>") == 4)
    check("titulo e empresa presentes",
          "Working Student Supply Chain Analytics (f/m/d)" in page and "SAP SE" in page)
    check("URL clicavel (href + nova aba)",
          'href="https://jobs.example/sap-1"' in page and 'target="_blank"' in page)
    check("botao 'abrir' com link direto", 'class="open"' in page and 'abrir&nbsp;↗' in page)
    check("score formatado", "9.50" in page and "9.00" in page and "8.10" in page)
    check("composicao do score com componentes REAIS",
          '<span class="bd-l">Área</span><span class="bd-v">+6.00</span>' in page
          and '<span class="bd-l">Skills</span><span class="bd-v">+0.75</span>' in page
          and '<span class="bd-l">Idioma</span><span class="bd-v">+2.00</span>' in page)
    check("penalidade negativa exibida",
          '<span class="bd-l">Penalidades</span><span class="bd-v">-0.40</span>' in page)
    check("total do breakdown", "Total <b>9.50</b>" in page)
    check("deadline exibida", "candidaturas até 2026-10-01" in page)
    check("resumo no topo (stats)", 'vagas elegíveis' in page and 'empresas' in page
          and 'score máx' in page and 'no Top 30' in page and 'dados atualizados' in page)
    check("stats com valores reais", '<b>3</b><span>vagas elegíveis' in page
          and '<b>2</b><span>empresas' in page and '<b>9.50</b><span>score máx'
          and '<b>3</b><span>no Top 30')
    check("badge Top 30 presente (3 de 3 no top_n default)",
          '<span class="badge-top">Top 30</span>' in page and page.count('class="badge-top"') == 3)
    check("data-attributes por linha", 'data-rank="1"' in page and 'data-rank="3"' in page
          and 'data-score="9.5"' in page and 'data-date="2026-09-01"' in page
          and 'data-company="SAP SE"' in page and 'data-type="PART_TIME"' in page)
    check("filtro no browser: input #q e selects sem <script src=",
          'id="q"' in page and 'id="f-company"' in page and 'id="f-type"' in page
          and 'id="f-min-score"' in page and 'id="sort"' in page
          and "src=" not in page.split("<script>")[1].split("</script>")[0])
    check("contador de vagas", "3 de 3 vagas" in page)
    chips = _render([FIXTURE[0]], filters_desc=["empresa contem 'sap'", "pais: de"])
    check("chips de filtro renderizados (escapados)",
          '<span class="chip">empresa contem &#x27;sap&#x27;</span>' in chips
          and "pais: de" in chips)
    evil = {"id": "x", "title": "<script>alert(1)</script>", "company": "A&B",
            "location": "X", "country_iso": "de", "url": "https://e/x?a=1&b=2",
            "score": 1.0, "score_breakdown": None, "description": "<b>raw</b>"}
    page2 = _render([evil])
    check("titulo/empresa escapados (sem injecao)",
          "&lt;script&gt;alert(1)&lt;/script&gt;" in page2 and "<script>alert(1)</script>" not in page2)
    check("data-title escapado para atributo",
          'data-title="&lt;script&gt;alert(1)&lt;/script&gt;"' in page2)
    check("URL escapada (& -> &amp;)", 'href="https://e/x?a=1&amp;b=2"' in page2)
    dbrow = {"id": "d1", "title": "Vaga DB", "company": "Co", "location": "L",
             "country_iso": "de", "remote": 1, "first_seen": "2026-09-07T06:00:02.000000Z",
             "last_seen": "2026-09-07T06:00:02.000000Z", "url": "https://d/1",
             "score": None, "score_breakdown": None, "description": None,
             "employment_type": None, "internship": 1, "posted_at": None,
             "collected_at": None, "application_deadline": None}
    page3 = _render([dbrow])
    check("vaga sem score exibe '—' e ordem last_seen", "—" in page3 and "mais recentes (last_seen)" in page3)
    check("data first_seen exibida (desde) e como data-date", "2026-09-07" in page3 and 'data-date="2026-09-07"' in page3)
    check("vaga sem score nao tem data-score numerico", 'data-score=""' in page3)


def test_top_n_badge() -> None:
    print("== destaque Top 30 (apenas apresentacao, posicao do ranking) ==")
    fx = interface.sort_ranked(FIXTURE)
    page = _render(fx, top_n=4)
    body = page.split("<tbody>")[1].split("</tbody>")[0]
    ranks_with_badge = re.findall(r'<tr class="top30" data-rank="(\d+)"', body)
    check("badge nas 4 primeiras posicoes", ranks_with_badge == ["1", "2", "3", "4"])
    check("posicoes 5+ sem badge", 'class="" data-rank="5"' in body
          and page.count('class="badge-top"') == 4)
    page0 = _render(fx, top_n=0)
    check("top_n=0 desliga o destaque", 'class="badge-top"' not in page0
          and '<tr class="top30"' not in page0)
    page_all = _render(fx, top_n=30)
    check("top_n >= total destaca todas", page_all.count('class="badge-top"') == 8)


def test_rank_map() -> None:
    print("== rank_map: posicao no RANKING do pipeline (nao no filtrado) ==")
    fx = interface.sort_ranked(FIXTURE)
    rank_map = {str(j["id"]): i for i, j in enumerate(fx, 1)}
    # so dhl (rank 5 do pipeline) passa no filtro da geracao; a posicao exibida
    # deve continuar 5, nao 1.
    page = _render([fx[4]], total=1, rank_map=rank_map)
    check("posicao preservada do ranking global", 'data-rank="5"' in page
          and '<td class="score">5</td>' in page)
    check("sem badge (5 > top 4)", _render([fx[4]], total=1, rank_map=rank_map, top_n=4).count('class="badge-top"') == 0)
    page_pos = _render([fx[0]], total=1, rank_map=rank_map)
    check("topo do ranking global nao perde o badge", 'data-rank="1"' in page_pos
          and page_pos.count('class="badge-top"') == 1)


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
        "mailto:test@example.com", "tel:+491****5678",
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
    check("botao abrir ausente quando a URL e rejeitada",
          'class="act"><span class="mut">—</span>' in page)
    evil = {"id": "e", "title": "Escape", "company": "Co", "location": "L",
            "country_iso": "de", "url": "https://example.com/?next=javascript:alert(1)&x=1",
            "score": 1.0, "score_breakdown": None, "description": None}
    page2 = _render([evil])
    check("URL http/https com & continua escapada apos validar scheme",
          'href="https://example.com/?next=javascript:alert(1)&amp;x=1"' in page2)


def _job_row(url: str, title: str = "Vaga X") -> dict:
    """Dict minimo de vaga para exercitar o ``render_html`` (caminho render)."""
    return {"id": "x", "title": title, "company": "Co", "location": "L",
            "country_iso": "de", "url": url, "score": 1.0,
            "score_breakdown": None, "description": None}


def _extract_core_js(page: str) -> str:
    """Nucleo puro do JS client-side (ate o marcador de DOM glue)."""
    script = page.split("<script>")[1].split("</script>")[0]
    return script.split("/* ==== DOM glue")[0]


def test_client_js_core() -> None:
    print("== nucleo JS client-side executado em node (filtros e ordenacao) ==")
    if shutil.which("node") is None:
        print("  [SKIP] node ausente — nucleo JS nao executado (CI ubuntu-latest tem node)")
        return
    fx = interface.sort_ranked(FIXTURE)
    page = _render(fx)
    core = _extract_core_js(page)
    check("nucleo puro extraido (nao vazio)", len(core) > 500 and "if_filter_sort" in core)
    rows = [_core_row(j, RANK_BY_ID[j["id"]]) for j in fx]

    # (estado, ordenacao, ranks esperados) — ranks = posicao no ranking do fixture.
    cases = [
        # Filtros
        ({"q": "logistik"}, "score-desc", [4], "texto 'logistik'"),
        ({"q": "WORKING"}, "score-desc", [1, 6], "texto case-insensitive 'WORKING'"),
        ({"q": "xyz"}, "score-desc", [], "texto sem match"),
        ({"company": "SAP SE"}, "score-desc", [1, 2], "empresa 'SAP SE'"),
        ({"company": "DHL"}, "score-desc", [5], "empresa 'DHL' (selecao exata)"),
        ({"type": "FULL_TIME"}, "score-desc", [2, 7], "tipo FULL_TIME"),
        ({"type": "PART_TIME"}, "score-desc", [1, 3, 4, 5, 6], "tipo PART_TIME"),
        ({"country": "at"}, "score-desc", [7], "pais 'at'"),
        ({"location": "Munich, DE"}, "score-desc", [3], "local exato 'Munich, DE'"),
        ({"q": "vienna"}, "score-desc", [7], "texto encontra LOCAL (vienna)"),
        ({"minScore": "8"}, "score-desc", [1, 2, 3], "score minimo 8"),
        ({"minScore": "100"}, "score-desc", [], "score minimo sem match"),
        ({"minScore": ""}, "score-desc", [1, 2, 3, 4, 5, 6, 7, 8], "score minimo vazio"),
        ({"company": "SAP SE", "minScore": "9.2"}, "score-desc", [1], "combinado empresa+score"),
        ({"q": "logistik", "type": "PART_TIME"}, "score-desc", [4], "combinado texto+tipo"),
        ({"q": "procurement", "country": "de"}, "score-desc", [5], "combinado texto+pais"),
        # Ordenacoes
        ({}, "rank", [1, 2, 3, 4, 5, 6, 7, 8], "ordenar por posicao"),
        ({}, "score-desc", [1, 2, 3, 4, 5, 6, 7, 8], "ordenar score desc (padrao)"),
        ({}, "score", [8, 7, 6, 5, 4, 3, 2, 1], "ordenar score asc"),
        ({}, "company", [7, 4, 5, 8, 1, 2, 3, 6], "ordenar empresa"),
        ({}, "title", [5, 7, 2, 3, 4, 8, 6, 1], "ordenar titulo"),
        ({}, "location", [2, 5, 8, 3, 6, 4, 7, 1], "ordenar local"),
        ({}, "date", [7, 8, 6, 5, 3, 4, 1, 2], "ordenar data"),
    ]
    lines = [
        core,
        "var rows = " + json.dumps(rows, ensure_ascii=False) + ";",
        "var cases = " + json.dumps(cases) + ";",
        "var ok = 0;",
        "for (var i = 0; i < cases.length; i++) {",
        "  var st = cases[i][0], key = cases[i][1], exp = cases[i][2], label = cases[i][3];",
        "  var got = if_filter_sort(rows, st, key).map(function (r) { return r.rank; });",
        "  if (JSON.stringify(got) !== JSON.stringify(exp)) {",
        "    console.log('FAIL ' + label + ': got ' + JSON.stringify(got) + ' want ' + JSON.stringify(exp));",
        "    process.exitCode = 1;",
        "  } else { ok++; }",
        "}",
        "console.log('cases ok: ' + ok + '/' + cases.length);",
        "if (process.exitCode !== 1) console.log('TUDO OK');",
    ]
    try:
        proc = subprocess.run(
            ["node", "-"], input="\n".join(lines), capture_output=True,
            text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        check(f"node executa o nucleo JS ({type(exc).__name__})", False)
        return
    out = (proc.stdout or "") + (proc.stderr or "")
    check("node executa sem erro (exit 0)", proc.returncode == 0)
    check("nucleo JS: 23/23 casos de filtro+ordenacao OK",
          "cases ok: 23/23" in out and "TUDO OK" in out)
    if "FAIL" in out:
        for line in out.splitlines():
            if line.startswith("FAIL"):
                check(f"caso do nucleo JS: {line}", False)


def test_real_snapshot() -> None:
    print("== bloco real (data/eligible_jobs.json) — Fase 3 ==")
    json_path = ROOT / "data" / "eligible_jobs.json"
    if not json_path.exists():
        print("  [SKIP] data/eligible_jobs.json ausente (runner limpo) — bloco real nao roda")
        return
    data = json.loads(json_path.read_text(encoding="utf-8"))
    n = len(data)
    check("snapshot e lista nao vazia", isinstance(data, list) and n > 0)
    with tempfile.TemporaryDirectory(prefix="t_if_real_") as td:
        out = Path(td) / "index.html"
        # Mesmo chamado do publish_pages: --input RELATIVO (o rotulo da pagina
        # nao pode expor o caminho absoluto da VPS — o gate de seguranca detecta).
        rc = interface.main(["--input", "data/eligible_jobs.json", "--top", "100000", "--output", str(out)])
        page = out.read_text(encoding="utf-8")
    check("gera a pagina (rc 0)", rc == 0 and len(page) > 100_000)
    body = page.split("<tbody>")[1].split("</tbody>")[0]
    row_count = body.count("<tr class=")
    check(f"TODAS as vagas elegiveis na pagina ({row_count} == {n})", row_count == n)
    check("resumo: total == pipeline", f'<b>{n}</b><span>vagas elegíveis' in page)
    companies = len({str(j.get("company")) for j in data if j.get("company")})
    check(f"resumo: empresas == {companies}", f'<b>{companies}</b><span>empresas' in page)
    max_score = max(float(j["score"]) for j in data)
    check(f"resumo: score max == {max_score:.2f}", f'<b>{max_score:.2f}</b><span>score máx' in page)
    check("resumo: Top 30 == 30", '<b>30</b><span>no Top 30' in page)
    check("contador inicial 'N de N vagas'", f"{n} de {n} vagas" in page)
    ranks = [int(r) for r in re.findall(r'data-rank="(\d+)"', body)]
    check("data-rank 1..N consecutivo (posicao do pipeline)", ranks == list(range(1, n + 1)))
    titles_page = re.findall(r'data-title="([^"]*)"', body)
    expected = [html_escape(str(j.get("title") or "")) for j in data]
    check("ordem exibida == ordem do ranking do pipeline (mesmos titulos)",
          titles_page[:30] == expected[:30] and titles_page[-1] == expected[-1])
    badges = re.findall(r'<tr class="top30" data-rank="(\d+)"', body)
    check("badge Top 30 nas 30 primeiras posicoes",
          badges == [str(i) for i in range(1, 31)])
    check("posicao 31 SEM badge", 'data-rank="31"' in body
          and '<tr class="top30" data-rank="31"' not in body)
    check("botao 'abrir' em todas as vagas com URL", body.count('class="open"') == n)
    check("nenhuma linha sem URL necessaria (todas as URLs validas do pipeline)",
          body.count('<a href=') >= n)
    breakdown_labels = ("Área", "Skills", "Idioma", "Tipo", "Local", "Penalidades")
    check("componentes reais do breakdown na pagina",
          all(lbl in page for lbl in breakdown_labels))
    problems = publish_pages.check_public_safe(page)
    if problems:
        print(f"    gate problems: {problems}")
    check("gate de seguranca: nada privado no HTML publicado", problems == [])
    script = page.split("<script>")[1].split("</script>")[0]
    check("JS client-side sem src externo", "src=" not in script)
    check("nucleo puro presente na pagina publicada", "if_filter_sort" in script)


def html_escape(value: str) -> str:
    """Mesmo escape usado na pagina (atributo), para comparar data-title."""
    import html as _html
    return _html.escape(value, quote=True)


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
        check("posicoes exibidas = ranking global (data-rank 1..3)",
              'data-rank="1"' in page and 'data-rank="2"' in page and 'data-rank="3"' in page)

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
    test_top_n_badge()
    test_rank_map()
    test_url_scheme()
    test_client_js_core()
    test_real_snapshot()
    test_main()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())