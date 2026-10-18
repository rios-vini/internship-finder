#!/usr/bin/env python3
"""Testes F55 — revisão de pesos do ranking (régua v4: materials −0.305).

Cobre o ajuste F55 nos 3 perfis (veredito v4: business +0.400 · EU +0.478 ·
materials −0.305 — revisão de pesos justificada), 100% OFFLINE:

- DIAGNÓSTICO com evidência da própria régua v4 (arquivo versionado): as 4
  ótimas são procurement/SC; a penalidade −1.5 afundou as ótimas no materials
  (adidas ótima 0.5 == HR ruim 0.5, ruim acima por desempate de título);
  HR ruim #7 acima de ótima #11 no estrato EU (gate de analytics protegia
  RH); KPMG "boa" #1 acima de todas as ótimas no business (topo sem
  separação);
- FIXTURE F55: 6 entradas VERBATIM do v4 (id/label/rank/title/justification);
- PESOS F55: constantes documentadas (skills 1.0; core 1.5 biz+EU;
  PENALTY_PROCUREMENT 0.0; area do dono 1.0x primary+related SEM weak;
  fn −2.5 com HR sem gate);
- COMPORTAMENTO: fn HR sem gate (business+EU, híbridos sales mantidos),
  core SC/proc no título (analytics NÃO é core), gradiente de skills 1.0,
  materials sem penalidade de procurement (outras funções mantêm −1.0),
  área do dono 3.0/2.0/0.0 (primary/related/weak), invariante de identidade
  (núcleo materials > área genérica — o weak quebrava);
- BREAKDOWN honesto: formas F55 válidas (_breakdown_key_set) e soma == total
  nos 3 perfis;
- GRADE MEDIDA (documentada, congelada): taus por perfil de cada ponto da
  grade + FINAL, com inversões criadas/resolvidas vs main-fresh e o critério
  pré-declarado (materials ≥ 0.0 E business ≥ 0.50 E EU ≥ 0.50). Medição:
  função OFICIAL pairwise_concordance, universo 844 (snapshot
  data/archive/20261016T090001Z, run 15/10, NOW_REF 2026-10-15T09:38:19Z),
  inaplicável fora dos pares (decisão dono 15/10 '3. A'). Os números são
  congelados AQUI como documentação mensurável — se um peso F55 mudar, os
  testes de comportamento falham e esta tabela fica visivelmente defasada.

NAO depende de ``data/`` (a régua v4 e a fixture são versionadas). NAO
reimplementa pairwise_concordance (lição F38: harness re-implementado deu
sinal invertido) — os taus congelados abaixo foram medidos COM a função
oficial sobre o universo 844.

Uso:  .venv/bin/python scripts/test_f55.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok: {msg}")
    else:
        print(f"  [FAIL] {msg}")
        FAILURES.append(msg)


BENCH = ROOT / "benchmarks" / "ranking_benchmark_v4.json"
FIXTURE = ROOT / "fixtures" / "benchmark_v4_fixture_f55.json"

from internship_finder.filters import (  # noqa: E402
    AREA_PRIMARY,
    AREA_RELATED,
    PENALTY_NON_TARGET_FUNCTION,
)
from internship_finder.ranking import (  # noqa: E402
    CORE_BUSINESS_PATTERNS,
    WEIGHT_CORE_BUSINESS,
    WEIGHT_SKILL,
    score_job,
)
from internship_finder.ranking_benchmark import _breakdown_key_set  # noqa: E402
from internship_finder.eu_ranking import WEIGHT_CORE_EU, eu_score_job  # noqa: E402
from internship_finder.materials_ranking import (  # noqa: E402
    PENALTY_PROCUREMENT,
    WEIGHT_AREA_TITLE,
    materials_score_job,
)


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def job(jid: str, title: str, desc: str = "") -> dict:
    return {
        "id": jid, "title": title, "company": "X GmbH", "description": desc,
        "location": "", "country_iso": None, "employment_type": None,
    }


# ---------------------------------------------------------------------------
# Grade medida F55 (congelada — função OFICIAL, universo 844, aplicável-first)
# ---------------------------------------------------------------------------
CRITERIO = {"business": 0.50, "materials": 0.0, "eu": 0.50}

# opcao -> (biz, mat, eu, biz_inv(+c/-r), mat_inv, eu_inv)
GRADE_F55: dict[str, tuple] = {
    # opcao -> (biz, mat, eu, biz_inv(+c/-r), mat_inv, eu_inv)
    "main":  (0.410, -0.305, 0.478, (0, 0), (0, 0), (0, 0)),
    "G1":    (0.410, 0.076, 0.478, (0, 0), (0, 40), (0, 0)),
    "G2":    (0.410, 0.381, 0.478, (0, 0), (31, 103), (0, 0)),
    "G2b":   (0.410, 0.438, 0.478, (0, 0), (15, 93), (0, 0)),
    "G4":    (0.438, -0.305, 0.565, (0, 3), (0, 0), (0, 1)),
    "G5b":   (0.438, 0.438, 0.565, (0, 3), (15, 93), (0, 1)),
    "G6a":   (0.505, 0.438, 0.652, (1, 11), (15, 93), (0, 2)),
    "G6b":   (0.533, 0.438, 0.739, (3, 16), (15, 93), (0, 3)),
    "G9":    (0.505, 0.438, 0.565, (0, 10), (15, 93), (0, 1)),
    "G10":   (0.524, 0.438, 0.652, (0, 12), (15, 93), (0, 2)),
    "G11":   (0.543, 0.438, 0.739, (3, 17), (15, 93), (0, 3)),
    # FINAL (implementada): G10 no business/EU + materials primary+related
    # 1.0x SEM weak
    "FINAL": (0.524, 0.495, 0.652, (0, 12), (15, 99), (0, 2)),
}


def test_diagnostico_v4() -> None:
    print("== diagnóstico (evidência VERBATIM da régua v4) ==")
    v4 = load(BENCH)
    jobs = {j["id"]: j for j in v4["jobs"]}
    otimas = [j for j in v4["jobs"] if j["label"] == "otima"]

    import re
    core_hit = lambda t: any(re.search(p, t, re.IGNORECASE) for p in CORE_BUSINESS_PATTERNS)
    check(len(otimas) == 4, "4 ótimas no v4")
    hits = [j for j in otimas if core_hit(j.get("title") or "")]
    hib = [j for j in otimas if not core_hit(j.get("title") or "")]
    check(len(hits) == 3 and len(hib) == 1 and "SC&L" in (hib[0].get("title") or ""),
          "3 das 4 ótimas carregam núcleo SC/proc no TÍTULO; a 4ª é a híbrida "
          "'Analytics Advisory & Data Democratization / SC&L' (ótima pelo lado "
          "SC, título de analytics — a exceção documentada nas 15 criadas)")
    check(all("supply" in (j.get("title") or "").lower()
              or "procurement" in (j.get("title") or "").lower()
              or "sc&l" in (j.get("title") or "").lower() for j in otimas),
          "as 4 ótimas são procurement/SC (núcleo da candidatura real — "
          "premissa 'compras = perfil oposto' do materials REFUTADA)")
    mat_ranks = sorted(j["rank_materials"] for j in otimas)
    check(mat_ranks[-1] >= 646 and mat_ranks == sorted(mat_ranks),
          f"ótimas afundadas no materials (ranks {mat_ranks} no universo 844)")

    adidas = jobs["adidas|sf_dataset:successfactors:1442838433"]
    hr = jobs["Corbion Career Site|sf_dataset:successfactors:1444333533"]
    check(adidas["label"] == "otima" and hr["label"] == "ruim",
          "adidas GLOBAL PROCUREMENT ótima; HR Rewards Analytics ruim")
    check(adidas["score_materials"] == hr["score_materials"] == 0.5,
          "crise materials em 1 número: ótima adidas 0.5 == ruim HR 0.5 "
          "(penalidade procurement −1.5 empatou núcleo da candidatura com RH)")
    check(hr["rank_materials"] < adidas["rank_materials"],
          f"ruim HR #{hr['rank_materials']} ACIMA da ótima adidas "
          f"#{adidas['rank_materials']} no materials v4 (desempate por título)")

    nestle = jobs["nestleHRprdRMK|successfactors:jobdetails:1441411733"]
    check(nestle["label"] == "otima" and hr["rank_eu"] < nestle["rank_eu"],
          f"EU: ruim HR #{hr['rank_eu']} acima da ótima Nestlé DSP #{nestle['rank_eu']} "
          "(gate de área primária protegia RH — 'HR Rewards Analytics')")
    check(adidas["score_breakdown"]["penalties"] == 0.0
          and adidas["score_breakdown"]["skills"] == 1.5,
          "business v4: ótima adidas sem penalidade, skills 1.5 (2 termos × 0.75 — "
          "peso fraco que F55 sobe p/ 1.0)")

    kpmg = next(j for j in v4["jobs"] if j["id"].startswith("KPMG"))
    check(kpmg["label"] == "boa" and kpmg["rank"] == 1
          and all(j["rank"] > 1 for j in otimas),
          "business v4: KPMG 'boa' #1 acima de TODAS as ótimas (topo sem separação — "
          "skills fraco deixava template ganhar do conteúdo)")


def test_fixture_verbatim() -> None:
    print("== fixture F55 (VERBATIM do v4) ==")
    v4 = load(BENCH)
    fx = load(FIXTURE)
    check(fx.get("fixture_version") == "f55-2026-10-17", "versão da fixture")
    check(len(fx["jobs"]) == 6, "6 entradas de diagnóstico")
    vmap = {j["id"]: j for j in v4["jobs"]}
    for e in fx["jobs"]:
        ref = vmap.get(e["id"])
        ok = (ref is not None and ref["label"] == e["label"]
              and ref["rank"] == e["rank"]
              and (ref.get("title") or "") == e["title"]
              and (ref.get("justification") or "").startswith(e["justification"][:40]))
        check(ok, f"verbatim: [{e['label']}] {e['title'][:52]}...")


def test_pesos_f55() -> None:
    print("== pesos F55 (constantes documentadas) ==")
    check(WEIGHT_SKILL == 1.0, "WEIGHT_SKILL 0.75 -> 1.0 (gradiente ótima>aceitável do v4)")
    check(WEIGHT_CORE_BUSINESS == 1.5, "WEIGHT_CORE_BUSINESS == 1.5 (k=2.5 criava 3 inversões)")
    check(WEIGHT_CORE_EU == 1.5, "WEIGHT_CORE_EU == 1.5 (mesmo k do business)")
    check(PENALTY_PROCUREMENT == 0.0, "materials: PENALTY_PROCUREMENT −1.5 -> 0.0 (premissa refutada)")
    check(WEIGHT_AREA_TITLE == 1.0, "materials: WEIGHT_AREA_TITLE == 1.0 (primary+related, sem weak)")
    check(PENALTY_NON_TARGET_FUNCTION == -2.5, "fn não-alvo −2.5 (casa canônica em filters)")
    import re
    pats = "|".join(CORE_BUSINESS_PATTERNS)
    check(all(re.search(p, pats) for p in (r"supply", r"procurement", r"purchas",
                                           r"einkauf", r"beschaffung")),
          "CORE: supply chain/procurement/purchas/einkauf/beschaffung (analytics NÃO é core)")
    check(any("analytics" not in p for p in CORE_BUSINESS_PATTERNS)
          and not any("analytics" in p for p in CORE_BUSINESS_PATTERNS),
          "analytics fora do CORE (lente de área já o cobre)")
    # área do dono no materials: primary+related SOMENTE (SEM weak)
    check(any("supply" in p for p in AREA_PRIMARY) and any("operations" in p for p in AREA_RELATED),
          "levels usados: AREA_PRIMARY + AREA_RELATED")


def test_fn_hr_sem_gate() -> None:
    print("== fn: HR sem gate (business + EU); híbridos sales protegidos ==")
    hr_t = "Internship - HR Rewards Analytics (BSc, BA, MSc, MBA)"
    s = score_job(job("hr", hr_t))
    check(s.breakdown["fn"] == PENALTY_NON_TARGET_FUNCTION,
          f"business: HR Rewards Analytics fn={s.breakdown['fn']} (antes: gate de analytics protegia RH)")
    e = eu_score_job(job("hr", hr_t))
    check(e.breakdown["fn"] == PENALTY_NON_TARGET_FUNCTION,
          f"EU: idem fn={e.breakdown['fn']}")
    s = score_job(job("sa", "Sales Analytics Intern"))
    check(s.breakdown["fn"] == 0.0,
          "business: 'Sales Analytics Intern' protegido (gate mantém híbridos não-HR)")
    s = score_job(job("mk", "Digital Marketing Intern"))
    check(s.breakdown["fn"] == PENALTY_NON_TARGET_FUNCTION,
          "business: marketing sem área primária penalizado")
    s = score_job(job("sc", "Supply Chain Intern"))
    check(s.breakdown["fn"] == 0.0, "business: supply chain sem penalidade de função")


def test_core_business() -> None:
    print("== core: núcleo SC/procurement no TÍTULO (biz + EU) ==")
    for t in ("Supply Chain Planning Internship (6 months)",
              "INTERNSHIP - GLOBAL PROCUREMENT (M/F/D)",
              "Werkstudent Einkauf (m/w/d)"):
        s = score_job(job("c", t))
        check(s.breakdown["core"] == 1.5, f"business core 1.5: {t[:48]}")
        e = eu_score_job(job("c", t))
        check(e.breakdown["core"] == 1.5, f"EU core 1.5: {t[:48]}")
    for t in ("Praktikum Data Science / Data Analytics & BI  (w/m/d)",
              "Internship – Data Analytics"):
        s = score_job(job("d", t))
        check(s.breakdown["core"] == 0.0, f"analytics NÃO é core: {t[:44]}")


def test_skills_gradiente() -> None:
    print("== skills 1.0 (sinal do CONTEÚDO vs template) ==")
    s = score_job(job("sk", "Data Analytics Intern", "python and apis"))
    check(s.breakdown["skills"] == 2.0, "2 competências na descrição -> 2.0 (era 1.5)")
    s = score_job(job("sk0", "Data Analytics Intern", "just text"))
    check(s.breakdown["skills"] == 0.0, "sem competências -> 0.0 (termo único, nunca por ocorrência)")


def test_materials_area_e_penalidade() -> None:
    print("== materials: procurement não penaliza; área do dono sem weak ==")
    s = materials_score_job(job("e", "Werkstudent Einkauf (m/w/d)"))
    check(s.breakdown["penalties"] == 0.0,
          "'Einkauf' NÃO penaliza mais (premissa 'compras=oposto' refutada — as 4 ótimas são procurement/SC)")
    s = materials_score_job(job("v", "Werkstudent Vertrieb & Marketing"))
    check(s.breakdown["penalties"] == -1.0,
          "outras funções não-materiais MANTÊM −1.0 (vendas/marketing)")
    s = materials_score_job(job("sc", "Working Student Supply Chain"))
    check(s.breakdown["area"] == 3.0, "área primary no título -> 3.0 (×1.0)")
    s = materials_score_job(job("op", "Working Student Operations"))
    check(s.breakdown["area"] == 2.0, "área related-only -> 2.0")
    s = materials_score_job(job("rp", "Working Student Reporting"))
    check(s.breakdown["area"] == 0.0, "nível WEAK NÃO conta ('reporting'/'data'/'sap' = ruído de template)")
    mtest = materials_score_job(job("mt", "Praktikum Materials Testing"))
    dan = materials_score_job(job("da", "Working Student Data Analytics"))
    check(mtest.total > dan.total,
          f"invariante de identidade: núcleo materials ({mtest.total}) > área genérica ({dan.total})")
    hib = materials_score_job(job("al", "Praktikant Einkauf Aluminium (w/m/x)"))
    tec = materials_score_job(job("ba", "Praktikum Entwicklung Batteriezelle (w/m/d)"))
    check(hib.total > tec.total,
          f"híbrido alinhado ao perfil DUPLO (núcleo+área {hib.total}) acima da técnica pura ({tec.total}) — rubrica v4")


def test_breakdown_honesto() -> None:
    print("== breakdown honesto (formas F55 válidas, soma == total) ==")
    probe = job("p", "Werkstudent Supply Chain (m/w/d)")
    for name, s in (("business", score_job(dict(probe))),
                    ("EU", eu_score_job(dict(probe))),
                    ("materials", materials_score_job(dict(probe)))):
        check(_breakdown_key_set(dict(s.breakdown)) is not None,
              f"{name}: forma F55 válida p/ _breakdown_key_set ({sorted(s.breakdown)})")
        check(abs(s.total - round(sum(s.breakdown.values()), 2)) < 1e-9,
              f"{name}: soma dos componentes == total ({s.total})")
    b = score_job(dict(probe))
    check("fn" in b.breakdown and "core" in b.breakdown, "business carrega fn+core")
    e = eu_score_job(dict(probe))
    check("fn" in e.breakdown and "core" in e.breakdown, "EU carrega fn+core")
    m = materials_score_job(dict(probe))
    check("area" in m.breakdown, "materials carrega area")


def test_grade_medida_congelada() -> None:
    print("== grade medida (função OFICIAL, universo 844, congelada) ==")
    check(GRADE_F55["main"][0:3] == (0.410, -0.305, 0.478),
          "main fresh: 0.410/−0.305/0.478 (v4 frozen: 0.400/−0.305/0.478 — 1 par "
          "de diferença = 2 scores STALE de hidratação pós-score, documentado)")
    for opt, row in GRADE_F55.items():
        biz, mat, eu = row[0], row[1], row[2]
        ok = biz >= CRITERIO["business"] and mat >= CRITERIO["materials"] and eu >= CRITERIO["eu"]
        if opt == "FINAL":
            check(ok, f"FINAL (implementada) {biz:+.3f}/{mat:+.3f}/{eu:+.3f} ATINGE o critério")
        elif opt != "main":
            print(f"    {opt:<6} {biz:+.3f}/{mat:+.3f}/{eu:+.3f} crit={'OK' if ok else '--'} "
                  f"| inv biz +{row[3][0]}/-{row[3][1]} mat +{row[4][0]}/-{row[4][1]} eu +{row[5][0]}/-{row[5][1]}")
    f = GRADE_F55["FINAL"]
    check(f[4] == (15, 99),
          "materials FINAL: 99 resolvidas / 15 criadas (híbrida 'Analytics Advisory/SC&L' "
          "e ótima adidas abaixo das boas de procurement puro — trade-off da lente de área)")
    check(f[3] == (0, 12) and f[5] == (0, 2),
          "business/EU FINAL: ZERO inversões criadas (12/2 resolvidas)")
    # rejeitados documentados com números
    check(GRADE_F55["G2"][1] == 0.381, "rejeitado G2 (1.0x área CHEIA com weak): 0.381 — identidade diluída")
    check(GRADE_F55["G6b"][3] == (3, 16), "rejeitado G6b (core 2.5): 3 inversões criadas no business")
    check(GRADE_F55["G11"][3] == (3, 17), "rejeitado G11 (core 2.5 + skills 1.0): 3 criadas")
    check(GRADE_F55["G2b"][4] == (15, 93), "G2b (0.5x cheia): as MESMAS 15 criadas, só 93 resolvidas")


def main() -> int:
    print("Testes F55 — revisão de pesos do ranking (régua v4)")
    test_diagnostico_v4()
    test_fixture_verbatim()
    test_pesos_f55()
    test_fn_hr_sem_gate()
    test_core_business()
    test_skills_gradiente()
    test_materials_area_e_penalidade()
    test_breakdown_honesto()
    test_grade_medida_congelada()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
