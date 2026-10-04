#!/usr/bin/env python3
"""Testes standalone — F7: expansão multi-países (LU + NL + FI + BE).

Cobre, de forma DETERMINÍSTICA e offline (sem rede, sem data/):

1. **parse_country_spec multi-ISO**: "de,lu,nl,fi,be" -> frozenset com os
   5 ISOs; matches_country aceita vaga de cada país-alvo e rejeita fora
   (ex.: FR). TARGET_COUNTRIES = a tupla canônica (DE primeiro).
2. **Prefilter parametrizado** (dataset_source.is_country_row): row
   LU/NL/FI/BE passa; row FR não; ISO vazio + marcador de location casa
   ("NL (NL126)", "Belgien"); default sem argumento = só DE
   (retrocompat total: is_de_row preservado); _prefilter_slice com
   country_isos multi filtra o CSV fixture por país.
3. **EURES pós-fetch**: _eures_search_body com location_codes ->
   locationCodes = lista (OR); item com locationMap NL -> country_iso nl
   (o campo país desce do feed); fetch_eures_praktikum com http_json
   injetado conta jobs_by_country; default None = ["de"] (retrocompat F4).
4. **visa_policy por país**: arquivo curado tem country em TODAS as
   entries (16 DE + novas); empresa nova LU (Amazon EU) com visa_policy
   unclear -> visa_friendly True; AB InBev candidate_must_have_auth ->
   False; toda entrada nova tem sources não-vazio + checked; estado
   inválido rejeitado (visa_policy_state).
   Derivação explicit_support -> visa_friendly True por FIXTURE (o arquivo
   real não tem explicit_support — curadoria honesta).
5. **CLI/produção**: _country_isos_for_stages deriva ISOs do --country;
   collection_command passa --country de,lu,nl,fi,be (TARGET_COUNTRIES);
   BA permanece DE (não forçada a outros países).
6. **Página mínima**: vaga NL aparece com país visível (🇳🇱 NL no meta);
   vaga DE sem badge; badge 🛂 funciona para empresa LU (Amazon EU);
   tamanho continua < 150 KB.
7. **Digest top-5**: vaga NL ganha bandeira 🇳🇱 na linha; DE sem bandeira;
   formato preservado.

Padrão dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_f7.py
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from internship_finder import opportunity_intel as oi  # noqa: E402
from internship_finder.countries import (  # noqa: E402
    TARGET_COUNTRIES,
    matches_country,
    parse_country_spec,
)
from internship_finder.dataset_source import (  # noqa: E402
    _prefilter_slice,
    is_country_row,
    is_de_row,
    row_to_job,
)
from internship_finder.direct_fetch import (  # noqa: E402
    _eures_item_to_job,
    _eures_search_body,
    fetch_eures_praktikum,
)

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _row(**over) -> dict:
    base = {
        "title": "Praktikum Data Analytics",
        "company": "TestCo",
        "url": "https://example.org/j/1",
        "ats_id": "a1",
        "country_iso": "",
        "location": "Berlin, DE, 10587",
        "description": "internship",
        "employment_type": "",
        "posted_at": "2026-10-01T00:00:00Z",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# 1. parse_country_spec multi-ISO + filtro
# ---------------------------------------------------------------------------


def test_country_spec() -> None:
    print("== F7.1: parse_country_spec multi-ISO ==")
    spec = parse_country_spec("de,lu,nl,fi,be")
    check("spec de 5 ISOs -> frozenset com os 5",
          isinstance(spec, frozenset)
          and spec == {"de", "lu", "nl", "fi", "be"})
    check("TARGET_COUNTRIES = 5 paises, DE primeiro",
          tuple(TARGET_COUNTRIES) == ("de", "lu", "nl", "fi", "be"))
    for iso in ("de", "lu", "nl", "fi", "be"):
        check(f"vaga {iso.upper()} aceita",
              matches_country(iso, "X", None, spec))
    check("vaga FR rejeitada", not matches_country("fr", "Paris", None, spec))
    check("vaga sem ISO + location fora rejeitada",
          not matches_country(None, "Madrid, ES", None, spec))
    check("remote aceito como spec", parse_country_spec("remote") == "remote")
    try:
        parse_country_spec("de,xx")
        check("token inválido levanta ValueError", False)
    except ValueError:
        check("token inválido levanta ValueError", True)


# ---------------------------------------------------------------------------
# 2. Prefilter parametrizado
# ---------------------------------------------------------------------------


def test_prefilter() -> None:
    print("== F7.2: prefilter is_country_row parametrizado ==")
    isos5 = ("de", "lu", "nl", "fi", "be")
    for iso in ("lu", "nl", "fi", "be", "de"):
        check(f"row iso={iso} passa nos 5",
              is_country_row(iso, "", isos5))
    check("row iso=fr NAO passa", not is_country_row("fr", "", isos5))
    check("row FR por location NAO passa",
          not is_country_row("", "Paris, France", isos5))
    # ISO vazio + marcador de location (formatos medidos nas fatias)
    check("location 'LU' casa", is_country_row("", "LU", isos5))
    check("location 'NL (NL126)' casa", is_country_row("", "NL (NL126)", isos5))
    check("location 'Belgien' casa", is_country_row("", "Belgien", isos5))
    check("location 'Niederlande' casa", is_country_row("", "Niederlande", isos5))
    check("location 'Finland' casa", is_country_row("", "Finland", isos5))
    check("location 'Aarschot, BE, 3200' casa",
          is_country_row("", "Aarschot, BE, 3200", isos5))
    check("location DE casa no conjunto",
          is_country_row("", "Berlin, DE, 10587", isos5))
    # default: sem argumento = só DE (retrocompat F3/F4)
    check("default: row DE passa", is_country_row("de", ""))
    check("default: row NL NAO passa (retrocompat)", not is_country_row("nl", ""))
    check("default: location NL NAO passa", not is_country_row("", "Amsterdam",))
    check("is_de_row preservado (delega)", is_de_row("de", "")
          and not is_de_row("nl", ""))
    # case-insensitive
    check("ISO maiúsculo casa", is_country_row("NL", "", isos5))
    # lista vazia/None: nada casa (defensivo)
    check("isos vazios -> False", not is_country_row("de", "", ()))


def test_prefilter_slice() -> None:
    print("== F7.2b: _prefilter_slice com country_isos ==")
    # titulos no vocabulario REAL do projeto (Stage/Trainee/Traineeship NAO
    # sao marcadores — comportamento existente, fixtures seguem o padrao)
    rows = [
        _row(title="Praktikum A", company="CoDE", country_iso="de",
             location="Berlin", url="https://e.org/1", ats_id="1"),
        _row(title="Stagiaire B", company="CoNL", country_iso="nl",
             location="Utrecht", url="https://e.org/2", ats_id="2"),
        _row(title="Internship C", company="CoLU", country_iso="lu",
             location="Luxembourg", url="https://e.org/3", ats_id="3"),
        _row(title="Praktikum D", company="CoFR", country_iso="fr",
             location="Paris", url="https://e.org/4", ats_id="4"),
        _row(title="Werkstudent E", company="CoBE", country_iso="",
             location="Gent, Belgien", url="https://e.org/5", ats_id="5"),
    ]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "slice.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        jobs5, _r, kept5, _i = _prefilter_slice(path, "test", ("de", "lu", "nl", "fi", "be"))
        jobs_de, _r2, kept_de, _i2 = _prefilter_slice(path, "test")
    check("5 ISOs: kept = 4 (de+nl+lu+be-marker; FR fora)", kept5 == 4)
    check("5 ISOs: 4 jobs", len(jobs5) == 4)
    isos = sorted(j.country_iso or "" for j in jobs5)
    check("jobs por iso = be,de,lu,nl", isos == ["be", "de", "lu", "nl"])
    check("default (sem isos): kept = 1 (só DE)", kept_de == 1)
    check("default: 1 job DE", len(jobs_de) == 1
          and jobs_de[0].country_iso == "de")
    # row_to_job: iso desce inferido (canônico) — inclusive nome local
    j = row_to_job(_row(country_iso="nl", location="Amsterdam"), "test")
    check("row_to_job infere nl", j is not None and j.country_iso == "nl")
    j2 = row_to_job(_row(country_iso="", location="Gent, Belgien"), "test")
    check("row_to_job infere be de 'Belgien' (nome local)",
          j2 is not None and j2.country_iso == "be")


# ---------------------------------------------------------------------------
# 3. EURES pós-fetch
# ---------------------------------------------------------------------------


def test_eures() -> None:
    print("== F7.3: EURES locationCodes OR + country_iso do feed ==")
    body5 = _eures_search_body(1, 50, ("de", "lu", "nl", "fi", "be"))
    check("locationCodes = 5 paises (OR)",
          body5["locationCodes"] == ["de", "lu", "nl", "fi", "be"])
    body_default = _eures_search_body(1, 50)
    check("default sem location_codes = ['de'] (retrocompat F4)",
          body_default["locationCodes"] == ["de"])
    body_none = _eures_search_body(1, 50, None)
    check("location_codes=None -> ['de']", body_none["locationCodes"] == ["de"])
    check("keyword intacta", body5["keywords"] == [
        {"keyword": "Praktikum", "specificSearchCode": "EVERYWHERE"}])

    # item com locationMap NL -> Job com country_iso nl (o campo desce do feed)
    item_nl = {
        "id": "JV-NL-1", "title": "Traineeship Logistics",
        "employerName": "NLCo", "locationMap": {"NL": ["Utrecht"]},
        "description": "stage", "positionOfferingCode": "INTERNSHIP",
    }
    job_nl = _eures_item_to_job(item_nl)
    check("item NL -> country_iso nl", job_nl is not None
          and job_nl.country_iso == "nl")
    check("item NL -> country nl", job_nl is not None
          and job_nl.country == "nl")
    item_de = {
        "id": "JV-DE-1", "title": "Praktikum Data", "employerName": "DECo",
        "locationMap": {"DE": ["Berlin"]}, "description": "x",
    }
    job_de = _eures_item_to_job(item_de)
    check("item DE -> country_iso de", job_de is not None
          and job_de.country_iso == "de")

    # fetch com http_json injetado: contagem por pais
    pages = [
        {"jvs": [item_nl, item_de, dict(item_nl, id="JV-NL-2")]},
        {"jvs": []},
    ]
    calls = {"n": 0}

    def fake_json(method, url, payload=None, timeout=None):
        idx = calls["n"]
        calls["n"] += 1
        if payload is not None:
            check(f"busca {idx}: locationCodes multi no body",
                  payload["locationCodes"] == ["de", "lu", "nl", "fi", "be"])
        return pages[idx] if idx < len(pages) else {"jvs": []}

    jobs, stats = fetch_eures_praktikum(
        http_json=fake_json, max_jobs=10,
        location_codes=("de", "lu", "nl", "fi", "be"),
    )
    check("3 jobs coletados (2 NL + 1 DE)", len(jobs) == 3)
    check("jobs_by_country nl=2", stats["jobs_by_country"].get("nl") == 2)
    check("jobs_by_country de=1", stats["jobs_by_country"].get("de") == 1)
    check("stats location_codes registrados",
          stats["location_codes"] == ["de", "lu", "nl", "fi", "be"])
    # default: sem location_codes o body segue DE puro
    calls2 = {"n": 0}

    def fake_json2(method, url, payload=None, timeout=None):
        if calls2["n"] == 0 and payload is not None:
            check("default: body segue ['de']",
                  payload["locationCodes"] == ["de"])
        calls2["n"] += 1
        return {"jvs": [item_de]}

    jobs2, stats2 = fetch_eures_praktikum(http_json=fake_json2, max_jobs=1)
    check("default: coleta 1 job DE", len(jobs2) == 1
          and jobs2[0].country_iso == "de")
    check("default: stats location_codes ['de']",
          stats2["location_codes"] == ["de"])


# ---------------------------------------------------------------------------
# 4. visa_policy por pais (arquivo curado)
# ---------------------------------------------------------------------------


def test_visa_policy_countries() -> None:
    print("== F7.4: visa_policy por pais ==")
    ci = ROOT / "company_intel" / "company_intelligence.json"
    if not ci.exists():
        check("arquivo curado presente", False)
        return
    data = json.loads(ci.read_text(encoding="utf-8"))
    entries = data["companies"]
    m = oi.load_company_intel(ci)
    uniq = list({id(v): v for v in m.values()}.values())
    check("country presente em TODAS as entries", all(e.get("country") for e in uniq))
    by_country = {}
    for e in uniq:
        by_country.setdefault(e["country"], []).append(e)
    check("≥16 DE preservadas (F7: 16; F9 expandiu p/ 46 — nunca remover)",
          len(by_country.get("de", [])) >= 16)
    for iso in ("lu", "nl", "fi", "be"):
        got = len(by_country.get(iso, []))
        check(f"pais {iso.upper()} presente (got {got})", got > 0)

    # empresa LU nova (Amazon EU): unclear -> visa_friendly True
    lu_names = [e["company"] for e in by_country.get("lu", [])]
    check("Amazon EU S.à r.l. entre as LU", "Amazon EU S.à r.l." in lu_names)
    amz = m.get(oi._norm("Amazon EU S.à r.l."))
    check("Amazon EU: visa_policy unclear",
          amz is not None and amz["visa_policy"] == "unclear")
    check("Amazon EU: visa_friendly True", oi.visa_friendly(amz) is True)
    check("Amazon EU: sources_for.visa_policy com url http",
          (amz.get("sources_for") or {}).get("visa_policy", [{}])[0]
          .get("url", "").startswith("http"))

    # AB InBev: candidate_must_have_authorization -> NAO visa_friendly
    abi = m.get(oi._norm("AB InBev"))
    check("AB InBev: candidate_must_have_authorization",
          abi is not None
          and abi["visa_policy"] == "candidate_must_have_authorization")
    check("AB InBev: visa_friendly False", oi.visa_friendly(abi) is False)

    # toda entrada nova (não-DE): sources não-vazio + checked
    for e in uniq:
        if e["country"] != "de":
            ok = (isinstance(e.get("sources"), list) and e["sources"]
                  and e.get("checked"))
            check(f"curadoria honesta ({e['company']}): sources+checked", ok)
    # estado inválido rejeitado (regra existente)
    check("estado inválido -> not_verified",
          oi.visa_policy_state({"visa_policy": "talvez"}) == "not_verified")
    # DE existente: estado por empresa segue igual (SAP unclear -> True)
    sap = m.get(oi._norm("SAP"))
    check("SAP DE continua unclear/visa_friendly",
          sap is not None and oi.visa_friendly(sap) is True)
    vw = m.get(oi._norm("Volkswagen AG"))
    check("VW DE continua must_have/nao-friendly",
          vw is not None and oi.visa_friendly(vw) is False)
    # derivação explicit_support coberta por FIXTURE (arquivo real não tem)
    fixture = {"company": "X", "visa_policy": "explicit_support"}
    check("explicit_support (fixture) -> visa_friendly True",
          oi.visa_friendly(fixture) is True)
    # nenhuma explicit_support no arquivo real (honestidade)
    check("arquivo real: 0 explicit_support",
          all(e.get("visa_policy") != "explicit_support" for e in uniq))


# ---------------------------------------------------------------------------
# 5. CLI/produção: derivação de ISOs + collection_command
# ---------------------------------------------------------------------------


def test_cli_stages() -> None:
    print("== F7.5: CLI — ISOs por estágio + collection_command ==")
    from internship_finder import cli as cli_mod
    import refresh_daily as rd

    isos = cli_mod._country_isos_for_stages(
        parse_country_spec("de,lu,nl,fi,be"))
    check("derivação: 5 ISOs DE primeiro",
          isos == ("de", "lu", "nl", "fi", "be"))
    check("derivação: --country de -> ('de',)",
          cli_mod._country_isos_for_stages(parse_country_spec("de")) == ("de",))
    check("derivação: europe -> frozenset ordenado DE primeiro",
          cli_mod._country_isos_for_stages(parse_country_spec("europe"))[0] == "de")
    check("derivação: remote -> ('de',) (coleta default)",
          cli_mod._country_isos_for_stages("remote") == ("de",))
    all_isos = cli_mod._country_isos_for_stages(None)
    check("derivação: all -> todos os ISOs", len(all_isos) > 100)

    cmd = rd.collection_command(60)
    check("collection_command: --country de,lu,nl,fi,be",
          "--country" in cmd and cmd[cmd.index("--country") + 1] == "de,lu,nl,fi,be")
    from internship_finder.countries import TARGET_COUNTRIES as TC
    check("valor segue TARGET_COUNTRIES",
          cmd[cmd.index("--country") + 1] == ",".join(TC))

    # BA permanece DE: collect_direct_fetch só injeta location no EURES
    import inspect
    import internship_finder.direct_fetch as dfx
    sig = inspect.signature(dfx.collect_direct_fetch)
    check("collect_direct_fetch: só eures_location_codes (BA sem injeção)",
          "eures_location_codes" in sig.parameters
          and "ba_location" not in sig.parameters
          and "ba_fetch" in sig.parameters)
    ba_sig = inspect.signature(dfx.fetch_ba_praktikum)
    check("fetch_ba_praktikum: NÃO aceita location/country (DE puro)",
          not any("location" in p or "country" in p for p in ba_sig.parameters))


# ---------------------------------------------------------------------------
# 6. Página mínima: país visível no card
# ---------------------------------------------------------------------------

MINIMAL_JOBS = [
    {"id": "de:1", "title": "Praktikum Data", "company": "SAP",
     "location": "Walldorf, DE", "country_iso": "de",
     "url": "https://example.org/1", "score": 9.5, "visa_friendly": True,
     "description": "dashboards", "collected_at": "2026-10-03T06:00:00Z",
     "score_breakdown": {"area": 6.0, "skills": 0.75, "language": 2.0,
                         "type": 1.0, "location": 1.0, "penalties": 0.0}},
    {"id": "nl:1", "title": "Stage Supply Chain", "company": "Action",
     "location": "Utrecht, NL", "country_iso": "nl",
     "url": "https://example.org/2", "score": 9.0, "visa_friendly": False,
     "description": "stage", "collected_at": "2026-10-03T06:00:00Z",
     "score_breakdown": {"area": 6.0, "skills": 0.0, "language": 1.5,
                         "type": 1.0, "location": 1.0, "penalties": 0.0}},
    {"id": "lu:1", "title": "Intern Tax", "company": "Amazon EU S.à r.l.",
     "location": "Luxembourg, LU", "country_iso": "lu",
     "url": "https://example.org/3", "score": 8.8, "visa_friendly": True,
     "description": "tax intern", "collected_at": "2026-10-03T06:00:00Z",
     "score_breakdown": {"area": 6.0, "skills": 0.0, "language": 1.5,
                         "type": 1.0, "location": 1.0, "penalties": 0.0}},
]


def test_minimal_page() -> None:
    print("== F7.6: página mínima — país visível ==")
    import minimal_page as mp
    html = mp.render_minimal_html(MINIMAL_JOBS, total_eligible=3,
                                  generated_at="2026-10-03T06:00:00Z")
    check("vaga NL com bandeira 🇳🇱 no meta", "🇳🇱 NL" in html)
    check("vaga NL com cidade Utrecht", "Utrecht" in html)
    check("vaga DE SEM bandeira no meta", "🇩🇪" not in html)
    check("badge 🛂 presente (Amazon EU visa_friendly)", "🛂" in html)
    check("data-vf=1 na vaga LU", 'data-vf="1"' in html)
    check("tamanho < 150 KB", len(html) < 150_000)
    # fallback: vaga LU sem visa_friendly re-deriva do company_intel
    jobs_novf = [dict(j) for j in MINIMAL_JOBS]
    for j in jobs_novf:
        j.pop("visa_friendly", None)
    m = oi.load_company_intel(ROOT / "company_intel" / "company_intelligence.json")
    html2 = mp.render_minimal_html(jobs_novf, total_eligible=3,
                                  generated_at="2026-10-03T06:00:00Z",
                                  company_intel_map=m)
    check("fallback: Amazon EU re-deriva visa_friendly do intel (LU)",
          html2.count("🛂") >= 1)


# ---------------------------------------------------------------------------
# 7. Digest top-5: bandeira no Telegram
# ---------------------------------------------------------------------------


def test_digest_top5() -> None:
    print("== F7.7: digest top-5 — bandeira opcional ==")
    import ranking_digest as rdt
    text = rdt.format_top5(MINIMAL_JOBS)
    lines = text.splitlines()
    check("3 linhas (3 vagas)", len(lines) == 3)
    check("linha NL com 🇳🇱", any("🇳🇱" in ln and "Stage Supply Chain" in ln
                                   for ln in lines))
    check("linha LU com 🇱🇺", any("🇱🇺" in ln for ln in lines))
    check("linha DE sem bandeira", any(
        ln.startswith("1. Praktikum Data") for ln in lines))
    check("formato N. título — empresa — score — url preservado",
          " — " in lines[0] and lines[0].startswith("1. "))
    check("≤ 4096 chars", len(text) <= 4096)


def main() -> None:
    test_country_spec()
    test_prefilter()
    test_prefilter_slice()
    test_eures()
    test_visa_policy_countries()
    test_cli_stages()
    test_minimal_page()
    test_digest_top5()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("TUDO OK")


if __name__ == "__main__":
    main()
