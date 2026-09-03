"""Testes do modulo de ranking (scripts/test_ranking.py).

Roda quatro blocos: (1) score_job sintetico (componentes e regras de negocio),
(2) determinismo/desempate/robustez, (3) ranking sobre uma FIXTURE FIXA
(sintetica, sem data/) verificando as regras de ranking no nivel do rank, e
(4) execucao real sobre data/eligible_jobs.json com invariantes de formato
(mesma quantidade, score/breakdown, ordenacao desc, impressao da distribuicao
e TOP 10 apenas como observabilidade — as regras de negocio agora vivem na
fixture, desacopladas de qualquer snapshot de dados). Uso:

    .venv/bin/python scripts/test_ranking.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.filters import area_score  # noqa: E402
from internship_finder.ranking import (  # noqa: E402
    WEIGHT_AREA_TITLE,
    rank_jobs,
    score_job,
)

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def base_job(**overrides) -> dict:
    job = {
        "id": "test:1",
        "source": "test",
        "title": "Intern - Supply Chain",
        "company": "TestCo",
        "location": "Stuttgart, de",
        "country": "de",
        "remote": None,
        "url": "https://example.com/1",
        "description": None,
        "internship": True,
        "employment_type": "INTERN",
        "country_iso": "de",
        "external_id": "1",
        "collected_at": "2026-08-10T00:00:00Z",
    }
    job.update(overrides)
    return job


# ---------------------------------------------------------------------------
# Fixture fixa (P2 #16) — desacopla as checagens de regra de ranking de
# qualquer snapshot de dados real.
#
# 18 vagas 100% sinteticas (ids ``fixture:N``, construidas com base_job,
# SEM ler ``data/``), inspiradas em casos reais mas com titulos/descricoes
# proprios. Cobrem as regras que o bloco real validava por presenca de vaga:
#   - A-grade de area-alvo (SC/Logistik, BI/Data, Automacao), com descricao
#     rica (area + skills + idioma) -> pontuam no topo;
#   - presales SCM (area real de Supply Chain vinda do TITULO, sem penalidade
#     de contexto) -> TOP 5 com area >= 6.0 e penalties == 0.0;
#   - "Communications/Media ... SAP Analytics Cloud" (produto mascarado) ->
#     area 0, segunda metade;
#   - Marketing sem area real -> fora do top 25% e na segunda metade;
#   - Senior/Head/Director -> penalidade forte;
#   - JMP/Management Trainee -> penalidade de manager, sem bonus de tipo;
#   - vagas neutras (tipo ok, sem area) -> faixa intermediaria/baixa.
# ---------------------------------------------------------------------------
FIXTURE: list[dict] = [
    # A-grade: Supply Chain / Logistik / Procurement
    base_job(
        id="fixture:1",
        company="CoA",
        title="Praktikum Supply Chain & Logistik (w/m/d)",
        description=(
            "Optimize inventory management and supplier relationships. "
            "Process automation with Python and APIs. English required, "
            "German is a plus."
        ),
    ),
    base_job(
        id="fixture:2",
        company="CoA",
        title="Werkstudent Einkauf & Procurement (w/m/d)",
        description=(
            "Support strategic procurement and purchasing operations. "
            "Supplier management and reporting. English required."
        ),
    ),
    base_job(
        id="fixture:3",
        company="CoK",
        title="Werkstudent Procurement & Digital Operations",
        description="Digital operations and sourcing. English required.",
    ),
    # A-grade: BI / Data & Analytics
    base_job(
        id="fixture:4",
        company="CoB",
        title="Praktikum im Bereich Data & Analytics",
        description=(
            "Process automation with Python and APIs. Reporting and "
            "continuous improvement. English required."
        ),
    ),
    base_job(
        id="fixture:5",
        company="CoC",
        title="Working Student BI & Data Analytics",
        description=(
            "Build data analytics and reporting dashboards. Python and cloud. "
            "English required."
        ),
    ),
    base_job(
        id="fixture:6",
        company="CoJ",
        title="Working Student Business Intelligence",
        description=(
            "Build business intelligence dashboards and data reporting. "
            "English required."
        ),
    ),
    # A-grade: Automation
    base_job(
        id="fixture:7",
        company="CoB",
        title="Working Student Process Automation & RPA",
        description="Robotic process automation and system integration. English required.",
    ),
    # B-list do dono: presales SCM — area real de Supply Chain no TITULO,
    # sem penalidade de contexto (regra Fase 2 preservada).
    base_job(
        id="fixture:8",
        company="CoD",
        title=(
            "Werkstudent (w/m/d) - Solution Advisory / Presales - "
            "Fokus auf Supply Chain Management"
        ),
        description=(
            "Support supply chain presales and solution demos with customers. "
            "Inventory management, supplier relationships, process automation "
            "and system integration with APIs and reporting. English required, "
            "German a plus. Python for continuous improvement."
        ),
    ),
    # Communications/Media em "SAP Analytics Cloud": produto mascarado ->
    # area 0, vaga BAIXA (regra Fase 2).
    base_job(
        id="fixture:9",
        company="CoE",
        location="Berlin, de",
        title=(
            "Working Student (f/m/d) - Communications / Media Production "
            "in SAP Analytics Cloud"
        ),
        description="Support the marketing team with content creation.",
    ),
    # Marketing sem area real -> BAIXO (fora do top 25%).
    base_job(
        id="fixture:10",
        company="CoE",
        title="Working Student - Marketing",
        description="Support the marketing team with content creation.",
    ),
    # Senior/Head/Director: penalidade forte.
    base_job(
        id="fixture:11",
        company="CoF",
        title="Senior Data Analyst (m/f/d)",
        description="Internship position supporting BI reporting.",
    ),
    base_job(id="fixture:12", company="CoF", title="Head of Supply Chain Operations"),
    base_job(id="fixture:13", company="CoG", title="Director Procurement"),
    # JMP / Management Trainee: penalidade de manager, sem bonus de tipo.
    base_job(
        id="fixture:14",
        company="CoG",
        title="Junior Managers Program (Trainee) - Purchasing",
    ),
    base_job(id="fixture:15", company="CoH", title="Management Trainee - Supply Chain"),
    # Neutras (tipo ok, sem area): faixa intermediaria/baixa.
    base_job(id="fixture:16", company="CoI", title="Praktikum Logistik"),
    base_job(
        id="fixture:17",
        company="CoL",
        title="Working Student Supplier Quality Management",
        description=(
            "Supplier management and continuous improvement in quality. "
            "English required."
        ),
    ),
    base_job(id="fixture:18", company="CoI", title="Werkstudent allgemeine Verwaltung"),
]
FIXTURE_N = len(FIXTURE)


def test_fixture_ranking() -> None:
    """ranqueia a FIXTURE fixa e valida as REGRAS de ranking (deterministico,
    sem dados reais), no nivel do RANK: mesmo conjunto de invariantes do
    bloco real, mas sobre a fixture — nenhum find() em dados reais."""
    print(f"== ranking na fixture fixa (N={FIXTURE_N}) ==")
    # Topo proporcional (1/3 de 18): A-grade de cada area + presales cabem.
    top_n = 6
    first_half = (FIXTURE_N // 2) + 1  # segunda metade comeca a partir dai

    ranked = rank_jobs(FIXTURE)
    top = ranked[:top_n]

    # Invariantes de formato (valem para qualquer dataset, inclusive a fixture).
    check("fixture: mesma quantidade", len(ranked) == FIXTURE_N)
    check("fixture: todos com score", all("score" in j for j in ranked))
    check(
        "fixture: todos com score_breakdown",
        all("score_breakdown" in j for j in ranked),
    )
    scores = [j["score"] for j in ranked]
    scores_sorted = sorted(scores, reverse=True)
    check("fixture: ordenado desc", scores == scores_sorted)
    check(
        "fixture: score_breakdown soma ao score",
        all(
            abs(sum(j["score_breakdown"].values()) - j["score"]) < 0.01
            for j in ranked
        ),
    )
    print(
        f"  fixture: min {min(scores):.2f} | "
        f"mediana {scores_sorted[FIXTURE_N // 2]:.2f} | max {max(scores):.2f}"
    )

    # Regras (no nivel do RANK).
    check(
        "fixture: topo e de area-alvo",
        all(j["score_breakdown"]["area"] > 0 for j in top),
    )
    senior_pat = re.compile(
        r"\bsenior\b|\bdirector\b|\bhead of\b|\bprincipal\b", re.IGNORECASE
    )
    check(
        "fixture: nenhum senior/head/director no topo",
        not any(senior_pat.search(j["title"]) for j in top),
    )

    # A-grade de cada area-alvo no TOP N (SC/Logistik, Data & Analytics,
    # BI, Automation).
    top_titles = [j["title"] for j in ranked[: top_n]]
    top_agrade = [
        "Praktikum Supply Chain & Logistik (w/m/d)",  # Supply Chain
        "Praktikum im Bereich Data & Analytics",      # Data & Analytics
        "Working Student BI & Data Analytics",        # BI/Data
        "Working Student Process Automation & RPA",   # Automation
    ]
    check(
        "fixture: A-grade (SC/BI/Data/Automacao) no TOP N",
        all(any(sub in t for t in top_titles) for sub in top_agrade),
    )

    # Presales SCM: TOP N com area real (>=6.0) vinda do TITULO e sem
    # penalidade de contexto (penalties == 0.0).
    presales = next(
        j for j in ranked if "presales" in j["title"].lower()
    )
    check(
        "fixture: presales SCM no TOP N",
        ranked.index(presales) + 1 <= top_n,
    )
    check(
        "fixture: presales SCM area >= 6.0 (titulo)",
        presales["score_breakdown"]["area"] >= 6.0,
    )
    check(
        "fixture: presales SCM sem penalidade (penalties == 0.0)",
        presales["score_breakdown"]["penalties"] == 0.0,
    )

    # 'SAP Analytics Cloud' (produto mascarado): area == 0 e na segunda metade.
    comms = next(
        j for j in ranked if "communications / media production" in j["title"].lower()
    )
    check(
        "fixture: Communications/Media 'SAP Analytics Cloud' area == 0.0",
        comms["score_breakdown"]["area"] == 0.0,
    )
    check(
        "fixture: Communications/Media 'SAP Analytics Cloud' na segunda metade",
        ranked.index(comms) + 1 >= first_half,
    )

    # Marketing sem area real: fora do top 25% e na segunda metade.
    mkt = next(j for j in ranked if j["title"] == "Working Student - Marketing")
    check(
        "fixture: marketing sem area fora do top 25%",
        ranked.index(mkt) + 1 > FIXTURE_N // 4,
    )
    check(
        "fixture: marketing sem area na segunda metade",
        ranked.index(mkt) + 1 >= first_half,
    )

    # Senior/Head/Director penalizados: nao podem estar acima de qualquer
    # A-grade (regra que o bloco real checava por presenca/top).
    check(
        "fixture: nenhum senior/head/director acima de A-grade",
        all(ranked.index(j) + 1 > top_n for j in ranked if senior_pat.search(j["title"])),
    )

    # JMP/Trainee: abaixo do topo, penalidade de manager (penalties <= -1.0).
    trainee_titles = [
        "Junior Managers Program (Trainee) - Purchasing",
        "Management Trainee - Supply Chain",
    ]
    trainee_pos = [ranked.index(j) for j in ranked if j["title"] in trainee_titles]
    check("fixture: JMP/Trainee fora do TOP N", all(p + 1 > top_n for p in trainee_pos))
    check(
        "fixture: JMP/Trainee com penalidade de manager",
        all(ranked[p]["score_breakdown"]["penalties"] <= -1.0 for p in trainee_pos),
    )


def test_synthetic() -> None:
    print("== score_job sintetico ==")

    # 1. Supply Chain Praktikum com descricao rica: area + skills + idioma.
    sc = score_job(
        base_job(
            title="Praktikum Supply Chain Management",
            description=(
                "Optimize inventory management and supplier relationships. "
                "Process automation with Python and APIs. English required, "
                "German is a plus."
            ),
            employment_type="FULL_TIME",  # Werkstudent/Praktikum FULL_TIME: nao zera
        )
    )
    check("Praktikum SC: area > 0", sc.breakdown["area"] > 0)
    check("Praktikum SC: skills > 0", sc.breakdown["skills"] > 0)
    check("Praktikum SC: ingles detectado", sc.breakdown["language"] >= 2.0)
    check("Praktikum SC: tipo no titulo", sc.breakdown["type"] == 1.0)
    check("Praktikum SC: DE explicito", sc.breakdown["location"] >= 1.0)
    check("Praktikum SC: FULL_TIME suave (nao zera)", sc.total > 5.0)
    check(
        "breakdown soma ao total",
        abs(sum(sc.breakdown.values()) - sc.total) < 0.01,
    )

    # 2. Working Student de Marketing: sem termo de area no titulo/descricao
    #    -> area 0, sem skills -> BAIXO. (Cuidado: titulo com "SAP" ganharia
    #    +1.0 de area por AREA_WEAK — comportamento herdado de filters.py.)
    mkt = score_job(
        base_job(
            id="test:2",
            title="Working Student (f/m/d) - Marketing - MEE",
            description="Support the marketing team with content creation.",
        )
    )
    sc_bonus = sc.breakdown
    mkt_area = mkt.breakdown
    check("Marketing: area 0", mkt_area["area"] == 0.0)
    check("Marketing: skills 0", mkt_area["skills"] == 0.0)
    check("Marketing: MENOR que Praktikum SC", mkt.total < sc.total)

    # 3. JMP Purchasing: "Junior Managers Program" NAO e mais marcador forte
    #    (Fase 1 pos-auditoria: programas de trainee sao excluidos do
    #    eligible; no ranking, nao ganham bonus de tipo e NAO protegem de
    #    penalidade de manager).
    jmp = score_job(
        base_job(
            id="test:3",
            title="Junior Managers Program (Trainee) - Start your Leadership "
            "Journey in Purchasing",
            description=None,
        )
    )
    check("JMP: penalidade de manager aplica", jmp.breakdown["penalties"] <= -1.0)
    check("JMP: area alta (purchasing primary)", jmp.breakdown["area"] >= 3.0)
    check("JMP: sem bonus de tipo (nao e marcador)", jmp.breakdown["type"] == 0.0)

    # 4. Senior sem marcador de tipo no titulo: penalidade forte.
    senior = score_job(
        base_job(
            id="test:4",
            title="Senior Data Analyst (m/f/d)",
            description="Internship position supporting BI reporting.",
        )
    )
    check("Senior: penalidade forte", senior.breakdown["penalties"] <= -3.0)

    # 5. Manager suave: "Manager" sozinho penaliza menos que senior.
    manager = score_job(
        base_job(
            id="test:5",
            title="Procurement Operations Manager",
            description="Internship position in procurement.",
        )
    )
    check(
        "Manager: penalidade suave (nao forte)",
        -3.0 < manager.breakdown["penalties"] <= -1.0,
    )

    # 6. Area: reusa filters.area_score (so a parte do TITULO, com peso).
    title = "Praktikum im Bereich Logistik und Supply Chain Design"
    desc = "Working in the warehouse operations team."
    job = base_job(title=title, description=desc)
    s = score_job(job)
    check(
        "area reusa filters.area_score (titulo * peso)",
        s.breakdown["area"] == WEIGHT_AREA_TITLE * area_score(title, None),
    )

    # 7. Fase 2 (pos-auditoria): termo de area dentro do NOME DO PRODUTO nao
    #    pontua como area do titulo — "SAP Analytics Cloud" e produto, nao
    #    funcao (a vaga real era Communications/Media e dominava o ranking).
    prod = score_job(
        base_job(
            id="test:7",
            title="Working Student (f/m/d) - Communications / Media Production "
            "in SAP Analytics Cloud",
            description="Support the marketing team with content creation.",
            location="Berlin, de",
        )
    )
    check(
        "Fase2: 'SAP Analytics Cloud' mascarado no titulo -> area 0",
        prod.breakdown["area"] == 0.0,
    )
    check(
        "Fase2: tipo/locale continuam (nao zerou a vaga)",
        prod.breakdown["type"] == 1.0 and prod.breakdown["location"] >= 1.5,
    )
    check(
        "Fase2: 'SAP Analytics Cloud' BAIXO (sem area)",
        prod.total < 6.75,
    )

    # O TERMO de area fora de produto continua pontuando normalmente
    # (o mask e de frase de produto, nao do termo).
    real_area = score_job(
        base_job(
            id="test:7b",
            title="Working Student (f/m/d) - Analytics: AI Enablement",
            description=None,
        )
    )
    check(
        "Fase2: 'Analytics' sozinho continua pontuando area",
        real_area.breakdown["area"] == 6.0,
    )

    # B-list do dono: presales SCM NAO recebe penalidade de contexto — a
    # area real de Supply Chain no titulo segue valendo (sem Option B).
    presales = score_job(
        base_job(
            id="test:7c",
            title="Werkstudent (w/m/d) - Solution Advisory / Presales - Fokus "
            "auf Supply Chain Management",
            description=None,
        )
    )
    check(
        "Fase2: presales SCM preservado (area de Supply Chain no titulo)",
        presales.breakdown["area"] == 6.0,
    )
    check("Fase2: presales SCM sem penalidade de contexto",
          presales.breakdown["penalties"] == 0.0)


def test_determinism() -> None:
    print("== determinismo e robustez ==")
    j1 = base_job()
    j2 = base_job()
    check("determinismo: mesmo dict -> mesmo score", score_job(j1) == score_job(j2))
    check(
        "determinismo: dict vs Job -> mesmo score",
        score_job(j1) == score_job(_job_model(j1)),
    )

    # sem descricao: nao quebra, so titulo pontua (skills/idioma zerados)
    no_desc = score_job(base_job(title="Praktikum Logistik", description=None))
    check("sem descricao: nao quebra", no_desc.total >= 0)
    check("sem descricao: skills 0", no_desc.breakdown["skills"] == 0.0)

    # rank_jobs: ordena desc e desempata deterministicamente
    a = base_job(id="a", title="Praktikum A", company="Co")
    b = base_job(id="b", title="Praktikum B", company="Co")
    ranked = rank_jobs([b, a])
    check("rank: mesmo score, desempate por titulo", ranked[0]["title"] == "Praktikum A")
    check("rank: adiciona score_breakdown", "score_breakdown" in ranked[0])
    check(
        "rank: entrada nao mutada",
        "score" not in a and "score" not in b,
    )


def _job_model(d: dict):
    """Converte dict em modelo Job (mesmo schema do CLI)."""
    from internship_finder.models.job import Job

    return Job(**{k: v for k, v in d.items() if k in Job.model_fields})


def test_real_data() -> None:
    print("== execucao real (data/eligible_jobs.json) ==")
    root = Path(__file__).resolve().parent.parent
    path = root / "data" / "eligible_jobs.json"
    # Ambiente sem coleta (ex.: CI runner sem data/): skip do bloco real (e dos
    # sanity checks de ranking/snapshot) com exit 0. O bloco so roda onde o
    # arquivo existe localmente. Os 5 sanity pre-existentes (P2 #16) seguem
    # intactos no codigo, mas nao rodam sem dados.
    if not path.exists():
        print("  SKIP: data/eligible_jobs.json ausente (sem coleta local) - bloco real e sanity ignorados")
        return
    jobs = json.loads(path.read_text(encoding="utf-8"))
    ranked = rank_jobs(jobs)
    scores = [j["score"] for j in ranked]
    scores_sorted = sorted(scores, reverse=True)
    check("real: mesma quantidade", len(ranked) == len(jobs))
    check("real: todos com score", all("score" in j for j in ranked))
    check("real: todos com breakdown", all("score_breakdown" in j for j in ranked))
    check("real: ordenado desc", scores == scores_sorted)

    n = len(scores)
    med = scores_sorted[n // 2] if n % 2 else (scores_sorted[n // 2 - 1] + scores_sorted[n // 2]) / 2
    print(f"  scores: min {min(scores):.2f} | mediana {med:.2f} | max {max(scores):.2f}")

    print("  TOP 10:")
    for i, j in enumerate(ranked[:10], 1):
        b = j["score_breakdown"]
        print(
            f"    {i:>2}. {j['score']:5.2f} | {j['title'][:64]} | "
            f"{j['company']} | area {b['area']:+.1f} skills {b['skills']:+.1f} "
            f"lang {b['language']:+.1f} tipo {b['type']:+.1f} loc {b['location']:+.1f} "
            f"pen {b['penalties']:+.1f}"
        )

    # P2 #16 (desacoplar do snapshot): este bloco so valida INVARIANTES DE
    # FORMATO que valem para QUALQUER dataset (mesma quantidade, todos com
    # score/breakdown, ordenado desc) e imprime a distribuicao + TOP 10 como
    # observabilidade. As checagens de REGRA (topo de area-alvo, nenhum
    # senior no topo, presales SCM, Communications 'SAP Analytics Cloud'
    # mascarado, marketing sem area fora do top, JMP/Trainee penalizado)
    # foram movidas para a FIXTURE fixa (``test_fixture_ranking``), desacopladas
    # de qualquer vaga especifica existir no dataset real (drift de dados).


def main() -> int:
    test_synthetic()
    test_determinism()
    test_fixture_ranking()
    test_real_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
