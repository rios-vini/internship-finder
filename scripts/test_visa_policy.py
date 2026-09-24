"""Testes standalone — Item 11 da auditoria pós-Fases 1–8: visa_policy.

Cobre, de forma DETERMINISTICA e offline (sem rede, sem data/):

1. **Estados**: ``visa_policy_state`` nos 5 estados válidos; campo
   ausente/inválido/None -> ``not_verified`` (analogia exata com
   ``pathway_state``).
2. **Curadoria**: as 12 empresas do arquivo real têm ``visa_policy``
   (10 ``not_verified`` + 2 ``unclear``); as 2 ``unclear`` têm fonte
   com url+quality+checked; as 10 ``not_verified`` têm a nota de
   rastreabilidade (``visa_policy_note``).
3. **Independência (crítico)**: ``visa_policy`` (EMPRESA) e
   ``work_authorization`` (VAGA) nunca se derivam um do outro — job com
   WA ``existing_required`` + empresa ``explicit_support`` mantém AMBOS
   preservados e distintos; ``visa_policy`` NÃO entra no score
   (data-score/data-scores idênticos com e sem visa_policy preenchida).
4. **Interface**: render com partial intel (1 empresa com visa_policy +
   11 sem) não quebra; rótulo PT-BR presente para a empresa curada;
   render SEM Company Intelligence (mapa {}) gera HTML OK.
5. **Ranking INALTERADO**: a página gerada do snapshot (quando o bloco
   real roda) mantém ordem+scores idênticos antes/depois de preencher
   visa_policy (comparação por id + score).

Padrao dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_visa_policy.py
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import interface  # noqa: E402  (mesmo script de renderizacao da pagina)
from internship_finder import app_intel, opportunity_intel as oi  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _job(**overrides) -> dict:
    base = {
        "id": "t:1", "source": "test:source", "title": "Vaga", "company": "TestCo",
        "location": "Berlin, DE", "country_iso": "de", "url": "https://example.org/j",
        "description": "", "collected_at": "2026-09-23T06:00:00Z",
        "score": 9.5,
        "score_breakdown": {"area": 6.0, "skills": 0.75, "language": 2.0,
                            "type": 1.0, "location": 1.0, "penalties": 0.0},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Estados válidos / default not_verified
# ---------------------------------------------------------------------------


def test_states() -> None:
    print("== visa_policy_state: 5 estados + default not_verified ==")
    for state in oi.VISA_POLICY_STATES:
        check(f"estado válido '{state}'",
              oi.visa_policy_state({"visa_policy": state}) == state)
    check("campo ausente -> not_verified",
          oi.visa_policy_state({"company": "X"}) == "not_verified")
    check("campo inválido 'maybe' -> not_verified",
          oi.visa_policy_state({"visa_policy": "maybe"}) == "not_verified")
    check("campo inválido 123 -> not_verified",
          oi.visa_policy_state({"visa_policy": 123}) == "not_verified")
    check("intel None -> not_verified", oi.visa_policy_state(None) == "not_verified")
    check("intel vazio {} -> not_verified", oi.visa_policy_state({}) == "not_verified")
    check("estados canônicos completos",
          oi.VISA_POLICY_STATES == ("explicit_support", "explicit_no_support",
                                    "candidate_must_have_authorization",
                                    "unclear", "not_verified"))
    # determinismo
    entry = {"visa_policy": "unclear"}
    check("determinismo (100x)",
          len({oi.visa_policy_state(entry) for _ in range(100)}) == 1)


# ---------------------------------------------------------------------------
# 2. Arquivo curado: 12 empresas, 10 not_verified + 2 unclear com fonte
# ---------------------------------------------------------------------------


def test_curated_file() -> None:
    print("== arquivo curado: 12 empresas (2 unclear c/ fonte, 10 not_verified) ==")
    ci = ROOT / "company_intel" / "company_intelligence.json"
    if not ci.exists():
        check("arquivo curado presente", False)
        return
    m = oi.load_company_intel(ci)
    # dedup por entrada (aliases apontam para a MESMA entrada)
    entries = {id(v): v for v in m.values()}.values()
    entries = list(entries)
    check("12 empresas curadas", len(entries) == 12)
    by_state: dict[str, int] = {}
    for e in entries:
        st = str(e.get("visa_policy") or "sem_campo")
        by_state[st] = by_state.get(st, 0) + 1
    check("10 not_verified", by_state.get("not_verified") == 10)
    check("2 unclear", by_state.get("unclear") == 2)
    # as 2 unclear têm fonte válida em sources_for.visa_policy
    for e in entries:
        if e.get("visa_policy") == "unclear":
            vp = (e.get("sources_for") or {}).get("visa_policy")
            ok = (isinstance(vp, list) and vp
                  and vp[0].get("url", "").startswith("http")
                  and vp[0].get("quality") in oi.SOURCE_QUALITIES
                  and vp[0].get("checked"))
            check(f"fonte visa_policy válida ({e['company']})", bool(ok))
    # nenhuma promoted além do curado
    check("nenhuma explicit_support (curadoria honesta)",
          by_state.get("explicit_support") is None)
    # as 10 not_verified têm nota de rastreabilidade
    notes = [e for e in entries if e.get("visa_policy") == "not_verified"
             and e.get("visa_policy_note")]
    check("10 not_verified com visa_policy_note", len(notes) == 10)


# ---------------------------------------------------------------------------
# 3. Independência visa_policy (empresa) × work_authorization (vaga)
# ---------------------------------------------------------------------------


def test_independence() -> None:
    print("== independência: visa_policy (empresa) ≠ work_authorization (vaga) ==")
    # vaga exige autorização existente; empresa tem política explícita de
    # suporte — AMBOS os estados são preservados e distintos.
    entry = {"company": "TestCo", "visa_policy": "explicit_support",
             "sources_for": {"visa_policy": [
                 {"text": "Careers FAQ", "url": "https://example.org/faq",
                  "quality": "primary", "checked": "2026-09-23"}]}}
    job = _job(description="You must have existing work authorization.",
               company="TestCo")
    wa = app_intel.work_authorization(
        f"{job['title']} {job['description']}")["state"]
    vp = oi.visa_policy_state(entry)
    check("WA da vaga = existing_required", wa == "existing_required")
    check("visa_policy da empresa = explicit_support", vp == "explicit_support")
    check("estados distintos e ambos preservados", wa != vp)

    # visa_policy NÃO deriva do texto da vaga (curada, não detectada):
    # a MESMA entrada com qualquer job devolve o MESMO estado.
    job2 = _job(description="We sponsor visas!", company="TestCo")
    check("visa_policy não muda com texto de suporte na vaga",
          oi.visa_policy_state(entry) == "explicit_support"
          and app_intel.work_authorization(
              f"{job2['title']} {job2['description']}")["state"] == "support")

    # work_authorization NÃO deriva da empresa: sem texto de WA, a vaga é
    # not_mentioned mesmo com empresa explicit_no_support.
    entry_no = {"company": "OtherCo", "visa_policy": "explicit_no_support"}
    job3 = _job(description="Great team, nice office.", company="OtherCo")
    check("WA da vaga not_mentioned mesmo c/ empresa explicit_no_support",
          app_intel.work_authorization(
              f"{job3['title']} {job3['description']}")["state"]
          == "not_mentioned"
          and oi.visa_policy_state(entry_no) == "explicit_no_support")


# ---------------------------------------------------------------------------
# 4. Interface: partial intel, sem intel, rótulo PT-BR, fonte na página
# ---------------------------------------------------------------------------

FIXTURE_JOBS = [
    {"id": "sap:1", "title": "Working Student Analytics (f/m/d)", "company": "SAP",
     "location": "Walldorf, DE", "country_iso": "de", "url": "https://example.org/1",
     "score": 9.5,
     "score_breakdown": {"area": 6.0, "skills": 0.75, "language": 2.0, "type": 1.0,
                         "location": 1.0, "penalties": 0.0},
     "description": "Dashboards.", "collected_at": "2026-09-23T06:00:02Z"},
    {"id": "bosch:1", "title": "Praktikum Logistik (m/w/d)", "company": "Bosch",
     "location": "Stuttgart, DE", "country_iso": "de", "url": "https://example.org/2",
     "score": 7.2,
     "score_breakdown": {"area": 4.0, "skills": 0.0, "language": 1.5, "type": 1.0,
                         "location": 1.0, "penalties": -0.3},
     "description": "Support the team.", "collected_at": "2026-09-23T06:00:02Z"},
    {"id": "other:1", "title": "Werkstudent Data", "company": "Nope GmbH",
     "location": "Berlin, DE", "country_iso": "de", "url": "https://example.org/3",
     "score": 5.4,
     "score_breakdown": {"area": 2.0, "skills": 0.0, "language": 1.5, "type": 1.0,
                         "location": 1.0, "penalties": 0.0},
     "description": "RPA bots.", "collected_at": "2026-09-23T06:00:02Z"},
]


def _partial_intel_map() -> dict[str, dict]:
    """1 empresa com visa_policy + fontes; demais sem o campo."""
    return {
        "sap": {
            "company": "SAP", "industry": "Software",
            "visa_policy": "unclear",
            "sources_for": {"visa_policy": [
                {"text": "SAP Careers — Privacy Statement",
                 "url": "https://jobs.sap.com/en/sap-privacy-statement-careers?locale=en_US",
                 "quality": "primary", "checked": "2026-09-23"}]},
            "checked": "2026-09-23", "sources": [],
        },
        "bosch": {"company": "Bosch", "industry": "Engenharia",
                  "checked": "2026-09-23", "sources": []},
    }


def test_interface_render() -> None:
    print("== interface: render parcial/sem intel; rótulo PT-BR; score intocado ==")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        ci_path = Path(td) / "ci.json"
        ci_path.write_text(json.dumps({"companies": list(_partial_intel_map().values())}),
                           encoding="utf-8")
        ci = oi.load_company_intel(ci_path)
        before = copy.deepcopy(FIXTURE_JOBS)
        page = interface.render_html(
            FIXTURE_JOBS, total=3, source_label="fixture", filters_desc=[],
            generated_at="2026-09-23T06:00:00Z", stats=None, top_n=30,
            company_intel_map=ci, loc_map={},
        )
        check("seção Política de visto presente",
              page.count("Política de visto (empresa)") == 3)
        check("rótulo PT-BR da empresa curada (unclear)",
              "Política condicional/não clara (fonte oficial)" in page)
        check("fonte da empresa curada na página (URL)",
              "sap-privacy-statement-careers" in page)
        check("default not_verified exibido para empresa sem campo",
              "Não verificado" in page)
        check("render não quebra com partial intel (3 vagas)",
              page.count("Oportunidade — empresa, localização") == 3)
        check("dados de origem não mutados", before == FIXTURE_JOBS)

        # Score NÃO alterado: data-score idêntico ao fixture.
        scores = re.findall(r'data-score="([0-9.]+)"', page)
        check("data-score == scores do fixture",
              sorted(float(s) for s in scores)
              == sorted(float(j["score"]) for j in FIXTURE_JOBS))

    # Render SEM Company Intelligence (mapa vazio) — não quebra.
    page2 = interface.render_html(
        FIXTURE_JOBS, total=3, source_label="fixture", filters_desc=[],
        generated_at="2026-09-23T06:00:00Z", stats=None, top_n=30,
        company_intel_map={}, loc_map={},
    )
    check("sem Company Intelligence -> página OK (3 vagas, not_verified)",
          page2.count("Oportunidade — empresa, localização") == 3
          and "Não verificado" in page2)

    # INDEPENDÊNCIA no HTML: mesma vaga com WA existing_required no texto e
    # empresa com visa_policy explicit_support — os DOIS aparecem, distintos.
    with tempfile.TemporaryDirectory() as td:
        ci_path = Path(td) / "ci.json"
        entry = {"company": "TestCo", "visa_policy": "explicit_support",
                 "checked": "2026-09-23", "sources": []}
        ci_path.write_text(json.dumps({"companies": [entry]}), encoding="utf-8")
        ci = oi.load_company_intel(ci_path)
        jobs = [_job(description="You must have existing work authorization.",
                     company="TestCo")]
        page3 = interface.render_html(
            jobs, total=1, source_label="fixture", filters_desc=[],
            generated_at="2026-09-23T06:00:00Z", stats=None, top_n=30,
            company_intel_map=ci, loc_map={},
        )
        check("WA da vaga (existing_required) na página",
              "Requer autorização de trabalho existente" in page3)
        check("visa_policy da empresa (explicit_support) na página",
              "Suporte explícito ao processo de visto (fonte oficial)" in page3)

    # visa_policy NÃO entra no score: data-score idênticos com e sem o campo.
    with tempfile.TemporaryDirectory() as td:
        p_no = Path(td) / "no.json"
        p_yes = Path(td) / "yes.json"
        p_no.write_text(json.dumps({"companies": [
            {"company": "TestCo", "checked": "2026-09-23", "sources": []}]}),
            encoding="utf-8")
        p_yes.write_text(json.dumps({"companies": [
            {"company": "TestCo", "visa_policy": "explicit_support",
             "checked": "2026-09-23", "sources": []}]}), encoding="utf-8")
        page_no = interface.render_html(
            FIXTURE_JOBS, total=3, source_label="f", filters_desc=[],
            generated_at="2026-09-23T06:00:00Z", stats=None, top_n=30,
            company_intel_map=oi.load_company_intel(p_no), loc_map={})
        page_yes = interface.render_html(
            FIXTURE_JOBS, total=3, source_label="f", filters_desc=[],
            generated_at="2026-09-23T06:00:00Z", stats=None, top_n=30,
            company_intel_map=oi.load_company_intel(p_yes), loc_map={})

        def score_attrs(page: str) -> list[list[tuple[str, str]]]:
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.DOTALL)
            out = []
            for r in rows:
                attrs = re.findall(r'(data-(?:score|salary|lang|wa|ready))="([^"]*)"',
                                   r)
                out.append(attrs)
            return out
        check("data-attrs de score IDÊNTICOS com/sem visa_policy",
              score_attrs(page_no) == score_attrs(page_yes))


# ---------------------------------------------------------------------------
# 5. Ranking inalterado no snapshot real (SKIP sem data/, padrão do projeto)
# ---------------------------------------------------------------------------


def test_real_ranking_unchanged() -> None:
    print("== bloco real (data/eligible_jobs.json; SKIP sem o arquivo) ==")
    rp = ROOT / "data" / "eligible_jobs.json"
    if not rp.exists():
        print("  [SKIP] sem data/eligible_jobs.json (runner limpo do CI)")
        return
    jobs = json.loads(rp.read_text(encoding="utf-8"))
    ci = oi.load_company_intel(ROOT / "company_intel" / "company_intelligence.json")
    # Ordem + scores do snapshot são a fonte de verdade; gerar a página com
    # a curadoria nova e conferir que o ranking exibido == ranking do arquivo.
    snapshot_scores = [(str(j.get("id")), float(j.get("score"))) for j in jobs]
    page = interface.render_html(
        jobs, total=len(jobs), source_label="real", filters_desc=[],
        generated_at="2026-09-23T06:00:00Z", stats=None,
        top_n=len(jobs), company_intel_map=ci,
        loc_map=oi.load_location_intel(ROOT / "company_intel" / "location_intel.json"),
    )
    # data-score por data-job-id
    pairs = re.findall(
        r'data-job-id="([^"]*)"[^>]*data-score="([0-9.-]+)"', page)
    # o atributo score vem antes do job-id na linha — capturar na ordem inversa
    rows = re.findall(r'<tr[^>]*?data-job-id="([^"]*)"[^>]*>', page)
    scores_in_page = re.findall(r'data-score="([0-9.-]+)"', page)
    check("página tem os 391 ids do snapshot", len(rows) == len(jobs))
    # ordem preservada: primeiros 3 e últimos 3 ids
    check("ordem de ranking preservada (topo)",
          [r for r in rows[:3]] == [str(j.get("id")) for j in jobs[:3]])
    check("ordem de ranking preservada (cauda)",
          [r for r in rows[-3:]] == [str(j.get("id")) for j in jobs[-3:]])
    # scores idênticos, multiset
    check("scores idênticos ao snapshot (multiset)",
          sorted(float(s) for s in scores_in_page)
          == sorted(s for _i, s in snapshot_scores))
    # visa_policy presente nas vagas das empresas curadas (SAP/Bosch)
    sap_jobs = sum(1 for j in jobs if "SAP" in str(j.get("company") or ""))
    bosch_jobs = sum(1 for j in jobs if "Bosch" in str(j.get("company") or ""))
    if sap_jobs or bosch_jobs:
        check("rótulo unclear exibido para vagas SAP/Bosch",
              page.count("Política condicional/não clara (fonte oficial)")
              >= 1)
    # WA: distribuição esperada pós-item 10 (23/4/364) — invariante da VAGA
    from collections import Counter
    wa = Counter(app_intel.work_authorization(
        f"{j.get('title') or ''} {j.get('description') or ''}")["state"]
        for j in jobs)
    check("WA (vaga) permanece detector da VAGA (23 existing / 4 unclear / 364 nm)",
          wa.get("existing_required") == 23 and wa.get("unclear") == 4
          and wa.get("not_mentioned") == 364)


def main() -> int:
    test_states()
    test_curated_file()
    test_independence()
    test_interface_render()
    test_real_ranking_unchanged()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
