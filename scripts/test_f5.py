"""Testes standalone — Fase F5: visa_friendly + dedup UTM/DE-EN + WEIGHT_AREA_DESC.

100% OFFLINE (zero rede, zero data/ de produção — fixtures sintéticas e o
arquivo curado versionado). O 49º script do CI.

Cobre os 4 entregáveis da spec F5:
1. **visa_friendly (sinal de EMPRESA)**: derivação dos estados
   (explicit_support/unclear → True; demais → False); wiring no pipeline
   (``_apply_visa_friendly`` adiciona o campo, NÃO altera score/ordem);
   CSV/JSON com o campo; badge + data-vf + filtro no HTML; NUCLEO JS do
   filtro executado em node (quando disponível); independência preservada
   (visa_policy da empresa ≠ work_authorization da vaga ≠ score).
2. **Curadoria expandida**: arquivo com 16 empresas; TODOS os estados
   verificados têm fonte (url/quality/checked); not_verified têm nota;
   candidate_must_have_authorization NÃO é visa_friendly (honestidade:
   Volkswagen/Mercedes/Siemens exigem permissão própria — negativo p/ BR).
3. **Dedup UTM**: ``normalize_url`` remove utm_*/gclid/fbclid/ref/source e
   PRESERVA params funcionais (pid, page, id...); mesma vaga com/sem utm
   FUNDE na chave URL; vagas diferentes com pid diferente NÃO fundem.
4. **Tier DE/EN (4a chave)**: Praktikum Logistik ↔ Logistics Internship na
   mesma empresa+cidade fundem (label company+title+location+de/en);
   empresa diferente NÃO funde; conteúdo diferente NÃO funde; cidade com
   alias (München/Munich) funde; snapshots antigos (sem visa_friendly)
   renderizam com fallback do opp_map.
5. **WEIGHT_AREA_DESC**: permanece 0.0 com o experimento documentado
   (τ +0.712→+0.732 em N=29 — evidência fraca; ver relatório F5); o
   valor não é lido de lugar nenhum além de ranking.py.

Uso:  .venv/bin/python scripts/test_f5.py
"""

from __future__ import annotations

import copy
import csv
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from internship_finder import opportunity_intel as oi  # noqa: E402
from internship_finder import ranking as rk  # noqa: E402
from internship_finder.cli import CSV_COLUMNS, _apply_visa_friendly, save_outputs  # noqa: E402
from internship_finder.dedup import (  # noqa: E402
    KEY_COMPANY_TITLE_LOCATION_DE_EN,
    _de_en_location_key,
    _de_en_title_key,
    candidate_keys,
    deduplicate,
    normalize_url,
)

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, ok: bool) -> None:
    global CHECKS
    CHECKS += 1
    tag = "[OK]" if ok else "[FAIL]"
    print(f"  {tag} {name}")
    if not ok:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# Fixture de vagas (dicts no formato eligible_jobs.json)
# ---------------------------------------------------------------------------


def _job(**kw) -> dict:
    base = {
        "id": "x|sf:1",
        "title": "Praktikum (m/w/d)",
        "company": "Test GmbH",
        "location": "Berlin, DE",
        "country_iso": "de",
        "url": "https://example.org/1",
        "source": "successfactors:jobs",
        "score": 5.0,
        "score_breakdown": {"area": 2.0, "skills": 0.0, "language": 1.0,
                            "type": 1.0, "location": 1.0, "penalties": 0.0},
        "description": "",
        "collected_at": "2026-10-03T06:00:02Z",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# 1. Derivação visa_friendly (estados → bool)
# ---------------------------------------------------------------------------


def test_visa_friendly_derivation() -> None:
    section("F5.1 visa_friendly: derivação dos estados (empresa)")
    check("explicit_support → True",
          oi.visa_friendly({"visa_policy": "explicit_support"}) is True)
    check("unclear → True (critério da auditoria: histórico/programa)",
          oi.visa_friendly({"visa_policy": "unclear"}) is True)
    check("candidate_must_have_authorization → False (não é friendly)",
          oi.visa_friendly({"visa_policy": "candidate_must_have_authorization"}) is False)
    check("explicit_no_support → False",
          oi.visa_friendly({"visa_policy": "explicit_no_support"}) is False)
    check("not_verified → False",
          oi.visa_friendly({"visa_policy": "not_verified"}) is False)
    check("intel None → False", oi.visa_friendly(None) is False)
    check("intel vazio → False", oi.visa_friendly({}) is False)
    check("estado inválido → False", oi.visa_friendly({"visa_policy": "maybe"}) is False)
    check("VISA_FRIENDLY_STATES == (explicit_support, unclear)",
          oi.VISA_FRIENDLY_STATES == ("explicit_support", "unclear"))
    # determinismo (função pura)
    check("determinístico (100 chamadas iguais)",
          len({oi.visa_friendly({"visa_policy": "unclear"}) for _ in range(100)}) == 1)


def test_pipeline_wiring() -> None:
    section("F5.2 pipeline: _apply_visa_friendly (aditivo; score/ordem intactos)")
    jobs = [
        _job(id="a|sf:1", company="SAP"),
        _job(id="b|sf:2", company="BoschGroup"),
        _job(id="c|sf:3", company="Sem Intel GmbH"),
        _job(id="d|sf:4", company="Volkswagen AG"),
    ]
    before = copy.deepcopy(jobs)
    n = _apply_visa_friendly(jobs)
    check("visa_friendly=True só para SAP/Bosch (arquivo curado real)",
          n == 2
          and jobs[0]["visa_friendly"] is True
          and jobs[1]["visa_friendly"] is True)
    check("empresa sem intel → False (não None)",
          jobs[2]["visa_friendly"] is False)
    check("Volkswagen (must_have_authorization) → False",
          jobs[3]["visa_friendly"] is False)
    # ordem/score intactos
    check("ordem preservada",
          [j["id"] for j in jobs] == [j["id"] for j in before])
    check("scores idênticos",
          all(j["score"] == b["score"] for j, b in zip(jobs, before)))
    # arquivo ausente → 0 e SEM campo (best-effort)
    with tempfile.TemporaryDirectory() as td:
        cwd = Path.cwd()
        try:
            os.chdir(td)  # company_intel/ ausente → load {} → 0
            jobs2 = [_job(id="a|sf:1", company="SAP")]
            n2 = _apply_visa_friendly(jobs2)
            check("arquivo curado ausente → 0 e sem campo (best-effort)",
                  n2 == 0 and "visa_friendly" not in jobs2[0])
        finally:
            os.chdir(cwd)


def test_csv_json_output() -> None:
    section("F5.3 CSV/JSON: campo visa_friendly no contrato de saída")
    check("CSV_COLUMNS termina com visa_friendly (aditivo no fim)",
          CSV_COLUMNS[-1] == "visa_friendly" and "visa_friendly" in CSV_COLUMNS)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "eligible.json"
        jobs = [_job(id="a|sf:1", company="SAP", visa_friendly=True),
                _job(id="b|sf:2", company="X GmbH", visa_friendly=False)]
        save_outputs(jobs, out)
        rows = json.loads(out.read_text(encoding="utf-8"))
        check("JSON preserva visa_friendly", rows[0]["visa_friendly"] is True)
        with (out.with_suffix(".csv")).open(encoding="utf-8") as fh:
            csv_rows = list(csv.DictReader(fh))
        check("CSV header inclui visa_friendly",
              "visa_friendly" in csv_rows[0])
        check("CSV linha True renderiza 'True'",
              csv_rows[0]["visa_friendly"] == "True")
        check("CSV linha False renderiza 'False'",
              csv_rows[1]["visa_friendly"] == "False")
        # dict SEM o campo (retrocompat): CSV escreve vazio, não quebra
        jobs_old = [_job(id="c|sf:3")]
        save_outputs(jobs_old, out)
        with (out.with_suffix(".csv")).open(encoding="utf-8") as fh:
            csv_rows2 = list(csv.DictReader(fh))
        check("CSV retrocompat: sem campo → célula vazia",
              csv_rows2[0]["visa_friendly"] == "")


# ---------------------------------------------------------------------------
# 2. HTML: badge + data-vf + filtro (núcleo JS em node quando disponível)
# ---------------------------------------------------------------------------


def test_html_badge_and_filter() -> None:
    section("F5.4 HTML: badge visa_friendly + data-vf + filtro + JS")
    import interface

    jobs = [
        _job(id="sap:1", title="Working Student Analytics (f/m/d)",
             company="SAP", location="Walldorf, DE", visa_friendly=True),
        _job(id="other:1", title="Werkstudent Data",
             company="Nope GmbH", location="Berlin, DE", visa_friendly=False),
    ]
    page = interface.render_html(
        jobs, total=2, source_label="fixture", filters_desc=[],
        generated_at="2026-10-03T06:00:00Z", stats=None, top_n=30,
        company_intel_map={}, loc_map={},
    )
    check("badge 🛂 visa friendly presente (1× — só SAP)",
          page.count("🛂 visa friendly</span>") == 1)
    check('data-vf="1" na linha da SAP', 'data-vf="1"' in page)
    check('data-vf vazio na linha sem sinal', 'data-vf=""' in page)
    check('checkbox id="f-vf" no painel de filtros', 'id="f-vf"' in page)
    check("JS if_match lê st.vf", "st.vf && row.vf" in page)
    check("JS state() inclui vf", "vf: els['f-vf']" in page)
    check("JS badgeCount conta f-vf", "'f-vf'" in page)

    # fallback: snapshot ANTIGO (sem campo) re-deriva do opp_map (retrocompat)
    jobs_old = [
        _job(id="sap:2", company="SAP", location="Walldorf, DE"),
    ]
    intel_map = oi.load_company_intel(
        ROOT / "company_intel" / "company_intelligence.json")
    page_old = interface.render_html(
        jobs_old, total=1, source_label="fixture-old", filters_desc=[],
        generated_at="2026-10-03T06:00:00Z", stats=None, top_n=30,
        company_intel_map=intel_map, loc_map={},
    )
    check("retrocompat: snapshot sem campo re-deriva do intel (badge SAP)",
          page_old.count("🛂 visa friendly</span>") == 1)

    # núcleo JS executado em node (mesmo método do test_interface)
    if shutil.which("node") is None:
        print("  [SKIP] node ausente — núcleo JS não executado (CI tem node)")
        return
    marker = "/* ==== DOM glue"
    core = page.split(marker)[0]
    start = core.index("function if_cmp_num")
    js_core = core[start:]
    cases = [
        # (row, state, esperado)
        ({"vf": "1"}, {"vf": True}, True),
        ({"vf": "1"}, {"vf": False}, True),
        ({"vf": ""}, {"vf": True}, False),
        ({"vf": "1", "score": "5"}, {"vf": True, "minScore": "3"}, True),
        ({"vf": "", "score": "5"}, {"vf": True, "minScore": "3"}, False),
        ({"vf": "1"}, {}, True),
        ({}, {"vf": True}, False),
    ]
    lines = [js_core]
    for i, (row, st, want) in enumerate(cases):
        lines.append(
            f"if (if_match({json.dumps(row)}, {json.dumps(st)}) !== "
            f"{'true' if want else 'false'}) "
            f"{{ console.log('CASE_FAIL {i}'); }}"
        )
    lines.append("console.log('JS_OK');")
    import subprocess
    proc = subprocess.run(
        ["node", "-"], input="\n".join(lines), capture_output=True,
        text=True, timeout=30,
    )
    check("node executa o núcleo JS com o filtro vf (exit 0)",
          proc.returncode == 0 and "JS_OK" in proc.stdout)
    check("núcleo JS: 7 casos de filtro vf OK (0 CASE_FAIL)",
          "CASE_FAIL" not in proc.stdout)


# ---------------------------------------------------------------------------
# 3. Dedup UTM
# ---------------------------------------------------------------------------


def test_dedup_utm() -> None:
    section("F5.5 dedup UTM: strip de tracking, preserva params funcionais")
    base = "https://jobs.example.com/careers/12345"
    u1 = normalize_url(f"{base}?utm_source=linkedin&utm_campaign=intl")
    check("mesma URL com utm == URL limpa", u1 == normalize_url(base))
    check("strip utm deixa URL sem query", u1 == base)
    u2 = normalize_url(f"{base}?pid=5638&utm_medium=social")
    check("param funcional (pid) preservado com utm junto",
          u2 == f"{base}?pid=5638")
    u3 = normalize_url(f"{base}?gclid=abc&fbclid=x&ref=li&source=tw")
    check("gclid/fbclid/ref/source stripped", u3 == base)
    u4 = normalize_url(f"{base}?page=2&id=99&utm_term=x")
    check("page/id preservados (funcionais)", u4 == f"{base}?page=2&id=99")
    u5 = normalize_url(f"{base}?pid=5638&utm_campaign=y#frag")
    check("fragmento + utm: só pid sobra", u5 == f"{base}?pid=5638")
    # 8fold: pid É identidade — pids diferentes nunca fundem
    p1 = normalize_url("https://infineon.eightfold.ai/careers/job/private?pid=563808971367597")
    p2 = normalize_url("https://infineon.eightfold.ai/careers/job/private?pid=563808971810705")
    check("pids diferentes continuam distintos (não funde)", p1 != p2)
    # mesmo pid com utm diferente FUNDE agora (o buraco fechado)
    p3 = normalize_url("https://infineon.eightfold.ai/careers/job/private?pid=563808971367597&utm_source=fb")
    check("mesmo pid com/sem utm funde (buraco F5 fechado)", p1 == p3)
    # casefold/ordem de params não é normalizada além disso (comportamento mantido)
    check("casefold mantido", normalize_url("https://X.COM/A") == "https://x.com/a")

    # end-to-end: deduplicate funde a mesma vaga com/sem utm pela chave URL
    jobs = [
        _job(id="a|sf:1", url="https://jobs.example.com/careers/12345?pid=7",
             description="texto"),
        _job(id="b|sf:2", url="https://jobs.example.com/careers/12345?pid=7&utm_source=li",
             description=""),
    ]
    out, stats, removed = deduplicate(jobs)
    check("mesma vaga com/sem utm FUNDE (1 sobrevive)", len(out) == 1)
    check("estatística registra fusão por URL", stats.get("url") == 1)
    check("vencedora é a com description", bool(out[0]["description"]))


# ---------------------------------------------------------------------------
# 4. Tier DE/EN (4a chave candidata)
# ---------------------------------------------------------------------------


def test_tier_de_en() -> None:
    section("F5.6 tier DE/EN: Praktikum↔Internship + Logistik↔Logistics + cidade")
    t_de = _de_en_title_key("Praktikum Logistik (m/w/d)")
    t_en = _de_en_title_key("Logistics Internship")
    check("título DE/EN converge pós-tradução", t_de == t_en and t_de)
    check("chave de título é bag (ordenada)",
          t_de == " ".join(sorted(t_de.split())))
    t_ws = _de_en_title_key("Werkstudent Einkauf (m/w/d)")
    t_ws_en = _de_en_title_key("Purchasing Working Student")
    check("Werkstudent/Einkauf ↔ Working Student/Purchasing",
          t_ws == t_ws_en)
    l1 = _de_en_location_key("München, BY, de")
    l2 = _de_en_location_key("Munich, Bavaria, DE")
    l3 = _de_en_location_key("Munich")
    check("cidade alias EN/DE converge (munchen)",
          l1 == l2 == l3 == "munchen")
    check("cidade sem alias fica como está",
          _de_en_location_key("Stuttgart, BW, de") == "stuttgart")
    check("local vazio → chave vazia", _de_en_location_key("") == "")
    check("título vazio → chave vazia", _de_en_title_key(None) == "")

    # tier 4 presente nas candidate_keys e DEPOIS do tier 3
    keys = candidate_keys(
        _job(title="Praktikum Logistik", location="München, DE"))
    labels = [k[0] for k in keys]
    check("4 chaves candidatas (ext_id+id, url, c+t+l, c+t+l+de/en)",
          KEY_COMPANY_TITLE_LOCATION_DE_EN in labels
          and labels.index(KEY_COMPANY_TITLE_LOCATION_DE_EN) > labels.index("company+title+location"))

    # end-to-end: mesma vaga DE + EN funde no tier 4 (tiers 1-3 não batem)
    jobs = [
        _job(id="a|sf:1", title="Praktikum Logistik (m/w/d)",
             location="München, BY, de", url="https://example.org/de",
             external_id="", description="texto"),
        _job(id="b|sf:2", title="Logistics Internship",
             location="Munich, Bavaria, DE", url="https://example.org/en",
             external_id="", description=""),
    ]
    out, stats, removed = deduplicate(jobs)
    check("mesma vaga DE/EN funde (1 sobrevive)", len(out) == 1)
    check("estatística registra o label do tier de/en",
          stats.get(KEY_COMPANY_TITLE_LOCATION_DE_EN) == 1)
    check("vencedora tem description (regra _prefer)", bool(out[0]["description"]))

    # negativos: empresa diferente NÃO funde; conteúdo diferente NÃO funde
    jobs2 = [
        _job(id="a|sf:1", title="Praktikum Logistik", location="München, DE",
             url="https://example.org/1", description="x"),
        _job(id="b|sf:2", title="Logistics Internship", location="München, DE",
             url="https://example.org/2", description="x",
             company="Outra GmbH"),
        _job(id="c|sf:3", title="Praktikum Marketing", location="München, DE",
             url="https://example.org/3", description="x"),
    ]
    out2, stats2, _ = deduplicate(jobs2)
    check("empresa/conteúdo diferente não funde (3 preservadas, 0 fusões)",
          len(out2) == 3 and not stats2)
    # cidade diferente não funde
    jobs3 = [
        _job(id="a|sf:1", title="Praktikum Logistik", location="München, DE",
             url="https://example.org/1", description="x"),
        _job(id="b|sf:2", title="Logistics Internship", location="Hamburg, DE",
             url="https://example.org/2", description="x"),
    ]
    out3, stats3, _ = deduplicate(jobs3)
    check("cidade diferente não funde", len(out3) == 2)
    # tiers 1-3 inalterados: mesma URL ainda funde (comportamento preservado)
    jobs4 = [
        _job(id="a|sf:1", url="https://example.org/same", description="x"),
        _job(id="b|sf:2", url="https://example.org/same", description=""),
    ]
    out4, stats4, _ = deduplicate(jobs4)
    check("tier URL intacto (fusão por URL igual)", len(out4) == 1
          and stats4.get("url") == 1)


# ---------------------------------------------------------------------------
# 5. WEIGHT_AREA_DESC — experimento documentado, valor mantido
# ---------------------------------------------------------------------------


def test_weight_area_desc() -> None:
    section("F5.7 WEIGHT_AREA_DESC: 0.0 mantido (experimento no relatório)")
    check("WEIGHT_AREA_DESC == 0.0 (mantido pós-experimento)",
          rk.WEIGHT_AREA_DESC == 0.0)
    check("WEIGHT_AREA_TITLE intacto (2.0)", rk.WEIGHT_AREA_TITLE == 2.0)
    # o score NÃO lê visa_friendly (independência do sinal novo)
    j = _job(company="SAP", visa_friendly=True, description="data reporting")
    s1 = rk.score_job(j)
    j2 = dict(j)
    j2["visa_friendly"] = False
    s2 = rk.score_job(j2)
    check("score_job ignora visa_friendly (True vs False idênticos)",
          s1.total == s2.total)
    # breakdown sem chave visa (nunca entra no score)
    check("breakdown sem componente visa",
          "visa" not in " ".join(s1.breakdown.keys()))
    # descrição não pontua area (W=0 efetivo)
    j3 = _job(description="supply chain data analytics procurement")
    j4 = _job(description="")
    check("description não altera area (W=0 efetivo)",
          rk.score_job(j3).breakdown["area"] == rk.score_job(j4).breakdown["area"])


# ---------------------------------------------------------------------------
# 6. Curadoria expandida (arquivo real, regras paramétricas)
# ---------------------------------------------------------------------------


def test_curadoria_f5() -> None:
    section("F5.8 curadoria: invariantes paramétricas (F7 expandiu 16 → 36; "
            "contagens exatas deram lugar a REGRAS — mesma evolução do "
            "test_visa_policy na F5)")
    ci = ROOT / "company_intel" / "company_intelligence.json"
    m = oi.load_company_intel(ci)
    entries = list({id(v): v for v in m.values()}.values())
    # F5 adicionou 4 (VW/BASF/Allianz/Telekom/Mercedes/Siemens sobre as 12);
    # F7 expandiu para LU/NL/FI/BE — o arquivo cresce com a curadoria.
    check("≥16 empresas curadas (F5: 16; F7: 36)",
          len(entries) >= 16)
    states = {}
    for e in entries:
        states[e.get("visa_policy")] = states.get(e.get("visa_policy"), 0) + 1
    # F5 (histórico): 3 unclear (SAP, Bosch, BASF) + 3 must_have (VW,
    # Mercedes, Siemens) + 10 not_verified. F7 adicionou unclear/not_verified
    # de outros países — as contagens SÓ PODEM CRESCER (regra paramétrica).
    check("≥3 unclear (SAP, Bosch, BASF da F5)",
          states.get("unclear", 0) >= 3)
    check("≥3 candidate_must_have_authorization (VW, Mercedes, Siemens da F5)",
          states.get("candidate_must_have_authorization", 0) >= 3)
    check("≥10 not_verified", states.get("not_verified", 0) >= 10)
    check("0 explicit_support (honestidade: nenhuma declaração incondicional)",
          states.get("explicit_support") is None)
    # F7: todas as entries têm campo country (16 'de' + novas por país)
    check("campo country presente em TODAS as entries (F7)",
          all(e.get("country") for e in entries))
    de_count = sum(1 for e in entries if e.get("country") == "de")
    # F9 expandiu as DE (30 entries novas, onda 1): a regra é "as 16
    # históricas JAMAIS somem" — a contagem só pode CRESCER (mesma
    # evolução paramétrica que a F7 aplicou às contagens da F5).
    check("≥16 entries DE preservadas (F7: 16; F9: 46)",
          de_count >= 16)
    # estados verificados SEMPRE têm fonte com citação
    for e in entries:
        if e.get("visa_policy") in ("unclear", "candidate_must_have_authorization",
                                    "explicit_support", "explicit_no_support"):
            vp = (e.get("sources_for") or {}).get("visa_policy")
            ok = (isinstance(vp, list) and vp
                  and str(vp[0].get("url", "")).startswith("http")
                  and vp[0].get("quality") in oi.SOURCE_QUALITIES
                  and vp[0].get("checked")
                  and bool(vp[0].get("note")))
            check(f"fonte com citação textual ({e['company']})", bool(ok))
    # aliases das novas empresas cobrem os nomes do dataset
    for alias in ("careers.allianz.com", "Telekom Growthhub", "Daimler"):
        check(f"alias '{alias}' presente no mapa", oi._norm(alias) in m)


def main() -> None:
    print("== F5: visa_friendly + dedup utm/DE-EN + WEIGHT_AREA_DESC ==")
    test_visa_friendly_derivation()
    test_pipeline_wiring()
    test_csv_json_output()
    test_html_badge_and_filter()
    test_dedup_utm()
    test_tier_de_en()
    test_weight_area_desc()
    test_curadoria_f5()
    print()
    if FAILURES:
        print(f"({CHECKS - len(FAILURES)}/{CHECKS} OK) FALHAS:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"({CHECKS}/{CHECKS}) TUDO OK (test_f5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
