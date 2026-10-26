#!/usr/bin/env python3
"""F100 — registry gap das 4 EN-friendly + curadoria EN-source (offline).

O QUE A F100 MEDIU (Passo 0, contra jobs.db read-only e o JSONL de métricas
— relatório ~/.hermes/handoff/f100-registry-gap/): o grep "0 registros" das
4 empresas no eligible (N=704 em 21/10) NÃO é gap de curadoria para 3 delas —
Infineon (eightfold:infineon), Zalando (workday:zalando/zalandositewd) e
Celonis (greenhouse:celonis) JÁ têm tenants no SEED coletando todo dia
(1.294/182/216 vagas medidas 22/10, status ok). O gap é de FUNIL: as vagas
DE de nicho morrem nos estágios de aplicabilidade honestos — Infineon 3/3
Werkstudent (werkstudent_puro, F86: exige matrícula em universidade alemã),
Celonis 3/3 german_required (alemão exigido na descrição hidratada),
Healthineers 11/11 Werkstudent, Zalando 3 student-type → 0 no ÁREA (títulos
"Intern Category Management" fora do vocab de nicho — score de área 0.0;
achado de vocab p/ decisão do dono, NÃO corrigido nesta fase). Siemens AG é
a única ausência REAL (curadoria), mas o board vivo é o portal custom
jobs.siemens.com ("Siemens Careers Marketplace", server-rendered) — ATS fora
dos 14 suportados; as linhas do inventário upstream estão mortas
(teamtailor 404; avature = portal interno de login) — sem entry (uma entry
sem scraper seria o "empty silencioso" perpétuo da patologia F58).

O QUE A F100 FEZ: onda F100 de 2 entradas no SEED — Issgovernance (ISS,
workday issgovernance/isscareers, 75 vagas validadas ao vivo) e JACOBS DOUWE
EGBERTS (smartrecruiters JACOBSDOUWEEGBERTS, 175 vagas) — candidatas da
varredura EN-source (>=3 vagas EN, score médio >=5, ausentes do registry)
do eligible N=708: 4 brutas, 2 cobertas (Amazon: conector próprio
amazon_jobs; "Kraftheinz": tenant Kraft Heinz da F88 — residual de alias
F88 §9), 2 validadas com o scraper REAL (discovery_rules.validate_slug,
rede read-only) e adicionadas. Bump F73 completo 145→147 (README 4×,
architecture, README-operacional 5×, docstrings dataset_source/ranking,
test_f71/test_registry/test_f72 paramétricos).

A/B DE DEDUP (medido no clone com a cadeia real: collect_company →
select_eligible(country=de,lu,nl,fi,be) → deduplicate →
deduplicate_cross_source): ISS 5→4 (par colidiu no tier
company+title+location — a URL da fatia do dataset difere da do tenant) e
JDE 7→5 (par no estágio URL — mesma URL space do SmartRecruiters);
ZERO duplicação pós-filtro. O grupo D trava esse mecanismo por fixture.

Este teste é 100% OFFLINE: nenhum teste de rede; as fixtures usam títulos
REAIS medidos dos boards (jobs.db read-only) e as exclusões são verificadas
por execução, não assunção.

Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
Uso:  .venv/bin/python scripts/test_f100.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.filters import (  # noqa: E402
    is_student_role,
    matches_area,
    select_eligible,
)
from internship_finder.registry import SEED, RegistryEntry  # noqa: E402

CHECKS = 0
FAILURES: list[str] = []

COUNTRY = "de,lu,nl,fi,be"


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name if not detail else f"{name} — {detail}")


def section(name: str) -> None:
    print(f"\n--- {name} ---")


def _covered(name_query: str) -> list[str]:
    """Entradas do SEED que casam com a query pela regra F88 §2 (casefold
    eq OU substring em qualquer direção)."""
    q = name_query.casefold()
    return [e.name for e in SEED if e.name.casefold() == q
            or e.name.casefold() in q or q in e.name.casefold()]


def _job(title: str, company: str, country_iso: str,
         description: str | None = None) -> dict:
    return {
        "title": title,
        "company": company,
        "country_iso": country_iso,
        "country": country_iso,
        "location": "Berlin, Germany" if country_iso == "de" else "Brussels",
        "description": description,
        "employment_type": None,
        "url": f"https://example.test/f100/{abs(hash(title))}",
        "source": "fixture:f100",
        "id": f"fixture|f100:{abs(hash(title))}",
    }


# ---------------------------------------------------------------------------
# [A] Passo 0 — classificação das 4 empresas como invariantes executáveis
# ---------------------------------------------------------------------------

def group_a() -> None:
    section("[A] Passo 0 — 3 tenants existentes + Siemens AG ausente")

    check("a1. Infineon JÁ no SEED (eightfold:infineon — coleta 1.294/dia)",
          any(e.name == "Infineon" and e.tenant == "eightfold:infineon"
              and e.ats == "eightfold" for e in SEED))
    check("a2. Zalando JÁ no SEED (workday:zalando/zalandositewd — 182/dia)",
          any(e.name == "Zalando" and e.tenant == "workday:zalando/zalandositewd"
              and e.ats == "workday" for e in SEED))
    check("a3. Celonis JÁ no SEED (greenhouse:celonis — 216/dia)",
          any(e.name == "Celonis" and e.tenant == "greenhouse:celonis"
              and e.ats == "greenhouse" for e in SEED))
    siemens_family = _covered("Siemens")
    check("a4. família Siemens no SEED: Healthineers (phenom, F58) + "
          "Energy (avature, F125 — empresa distinta pós-split 2020)",
          siemens_family == ["Siemens Healthineers", "Siemens Energy"],
          f"presentes: {siemens_family}")
    check("a5. 'Siemens AG' NÃO casa com nenhuma entry (curadoria gap "
          "documentada — portal custom jobs.siemens.com, ATS fora dos 14)",
          _covered("Siemens AG") == [])


# ---------------------------------------------------------------------------
# [B] Funil — fixtures com títulos REAIS medidos (onde as vagas morrem)
# ---------------------------------------------------------------------------

def group_b() -> None:
    section("[B] funil: exclusões medidas por execução (cascata real)")

    # B1 — Infineon real: vaga DE de nicho Werkstudent -> werkstudent_puro.
    ws = _job("Working Student - ASIC Product Marketing and Business "
              "Intelligence (f/m/div)", "Infineon", "de")
    sel, counts = select_eligible([ws], country=COUNTRY)
    check("b1. Infineon Werkstudent DE de nicho morre em "
          "werkstudent_puro (3/3 medidos)",
          counts.get("aplicabilidade_excluidas_werkstudent_puro") == 1
          and sel == [], f"counts={ {k: v for k, v in counts.items() if v} }")

    # B2 — Celonis real: alemão exigido na descrição -> german_required.
    # Frases VERBATIM do posting real hidratado (jobs.db): "business fluent
    # in German and English" + vocab de nicho que faz a vaga passar na área
    # ANTES de morrer na aplicabilidade (3/3 medidos).
    ge = _job("AI & Management Consulting Intern (Value Engineering - "
              "DACH Market)", "celonis", "de",
              description="Support the Value Engineering team in process "
                          "mining projects. Student of Business Analytics / "
                          "Technology & Management. Experience in consulting "
                          "and highly interested in Data Analytics. "
                          "Effective communicator and business fluent in "
                          "German and English.")
    sel, counts = select_eligible([ge], country=COUNTRY)
    check("b2. Celonis intern DE de nicho morre em german_required "
          "(3/3 medidos)",
          counts.get("aplicabilidade_excluidas_german_required") == 1
          and sel == [])

    # B3 — Zalando real: "Category Management" fora do vocab de área.
    cm = _job("Intern Category Management - Accessories & Specialties "
              "(all genders)", "zalando", "de")
    check("b3. Zalando 'Intern Category Management' É student-type mas "
          "score de área 0.0 (vocab não cobre 'category' — decisão do dono, "
          "não corrigido na F100)",
          is_student_role(cm["title"], None, None)
          and not matches_area(cm["title"], None))

    # B4 — controle positivo ISS real: título só (tenant coleta sem
    # description) atravessa a cascata INTEIRA.
    iss = _job("Internship - Corporate Governance Data Procurement (m/w/d)",
               "Issgovernance", "de")
    sel, counts = select_eligible([iss], country=COUNTRY)
    check("b4. ISS 'Data Procurement' (título só, EN, de) atravessa a "
          "cascata (A/B: aplicabilidade manteve 1/1)",
          len(sel) == 1 and counts.get("aplicabilidade") == 1)

    # B5 — controle positivo JDE real: Supply Chain no título, Brussels (be).
    jde = _job("Internship / Stage Planning Operations (Supply Chain)",
               "JACOBSDOUWEEGBERTS", "be")
    sel, counts = select_eligible([jde], country=COUNTRY)
    check("b5. JDE 'Planning Operations (Supply Chain)' (be) atravessa a "
          "cascata (A/B: aplicabilidade manteve 4/4)",
          len(sel) == 1 and counts.get("aplicabilidade") == 1)

    # B6 — contra-prova: a cascata não está quebrada para as 4 —
    # intern DE de nicho na própria Infineon passaria se existisse no board.
    pos = _job("Internship - Procurement (m/w/d)", "Infineon", "de")
    sel, _ = select_eligible([pos], country=COUNTRY)
    check("b6. contra-prova: 'Internship - Procurement' na Infineon "
          "ATRAVESSARIA a cascata (o 0 registros é do perfil do board, "
          "não do filtro)",
          len(sel) == 1)


# ---------------------------------------------------------------------------
# [C] Registry — schema/dedup da onda F100 (spec: validação offline)
# ---------------------------------------------------------------------------

F100_WAVE = {
    "Issgovernance": ("workday", "workday:issgovernance/isscareers"),
    "JACOBS DOUWE EGBERTS": ("smartrecruiters",
                             "smartrecruiters:JACOBSDOUWEEGBERTS"),
}


def group_c() -> None:
    section("[C] onda F100 no SEED — schema, dedup, enabled")

    for name, (ats, tenant) in F100_WAVE.items():
        entries = [e for e in SEED if e.name == name]
        check(f"c1. '{name}' presente exatamente 1× no SEED",
              len(entries) == 1, f"{len(entries)} entries")
        if entries:
            e = entries[0]
            check(f"c2. '{name}': ats={ats}, tenant={tenant} (inventário "
                  f"upstream, validado ao vivo)",
                  e.ats == ats and e.tenant == tenant)
            check(f"c3. '{name}': tenant com prefixo do próprio ats "
                  "(regra de forma F71) e enabled",
                  bool(e.tenant) and e.tenant.startswith(f"{e.ats}:")
                  and e.enabled)

    names = [e.name for e in SEED]
    check("c4. nenhum nome duplicado no SEED (147 nomes únicos)",
          len(names) == len(set(names)))
    triples = [(e.name, e.ats, e.tenant) for e in SEED]
    check("c5. nenhuma (name, ats, tenant) duplicada",
          len(triples) == len(set(triples)))
    check("c6. onda F100 não duplica cobertura: Issgovernance/JDE não "
          "casam com nenhuma OUTRA entry (regra F88 §2 bidirecional)",
          all(len(_covered(n)) == 1 for n in F100_WAVE))


# ---------------------------------------------------------------------------
# [D] A/B de dedup — o mecanismo medido (tenant × dataset) por fixture
# ---------------------------------------------------------------------------

def group_d() -> None:
    section("[D] A/B dedup: pares tenant×dataset colidem — zero duplicação")

    # D1 — JDE (medido): mesma URL space do SmartRecruiters -> estágio URL.
    url = "https://jobs.smartrecruiters.com/JACOBSDOUWEEGBERTS/744000150326658"
    tenant = _job("Internship / Stage Planning Operations (Supply Chain)",
                  "JACOBSDOUWEEGBERTS", "be")
    tenant["url"] = url
    dataset = dict(tenant, id="ds|1", source="sf_dataset:smartrecruiters")
    out, stats, _ = deduplicate([tenant, dataset])
    check("d1. mesmo-URL (tenant vs fatia dataset, mesmo ATS): dedup "
          "funde no estágio URL (medido 1/1)",
          len(out) == 1 and stats.get("company+url", 0) + stats.get("url", 0) == 1,
          f"stats={dict(stats)}")

    # D2 — ISS (medido): URLs DIFERENTES entre fatia e tenant -> colisão no
    # tier company+title+location (o 3-pass pega além do estágio URL).
    t2 = _job("Internship - Corporate Governance Data Procurement (m/w/d)",
              "Issgovernance", "de")
    t2["url"] = "https://issgovernance.wd1.myworkdayjobs.com/isscareers/job/TENANT-1"
    d2 = dict(t2, id="ds|2", source="sf_dataset:workday",
              url="https://issgovernance.wd1.myworkdayjobs.com/isscareers/job/SLICE-1")
    out, stats, _ = deduplicate([t2, d2])
    check("d2. URL distinta + mesma (company, title, location): dedup "
          "funde no tier company+title+location (medido 1/1)",
          len(out) == 1
          and stats.get("company+title+location", 0) == 1,
          f"stats={dict(stats)}")

    # D3 — contra-caso: vagas DISTINTAS nunca fundem.
    a = _job("Internship - Corporate Governance Data Procurement (m/w/d)",
             "Issgovernance", "de")
    b = _job("Internship - Corporate Governance Research (m/w/d)",
             "Issgovernance", "de")
    out, stats, _ = deduplicate([a, b])
    check("d3. contra-caso: títulos distintos permanecem 2 vagas",
          len(out) == 2 and not stats)


def main() -> int:
    print("F100 — registry gap das 4 EN-friendly + curadoria EN-source (offline)")
    group_a()
    group_b()
    group_c()
    group_d()
    print("\n" + "=" * 60)
    if FAILURES:
        print(f"FAIL — test_f100: {CHECKS} checks, {len(FAILURES)} falhas")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"OK — test_f100: {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
