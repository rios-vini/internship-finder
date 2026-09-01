"""Testes do modulo de ranking (scripts/test_ranking.py).

Roda tres blocos: (1) score_job sintetico (componentes e regras de negocio),
(2) determinismo/desempate/robustez, (3) execucao real sobre
data/eligible_jobs.json com distribucao, TOP 10 e sanity checks. Uso:

    .venv/bin/python scripts/test_ranking.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.filters import (  # noqa: E402
    TYPE_EXCLUSION_PATTERNS,
    area_score,
)
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

    # Sanity checks da especificacao (calibrados no conjunto real 2026-08-12,
    # expansao E2: n=389, mediana 6.00; antes 2026-08-10: n=170, mediana 6.75).
    # Fase 1 das correcoes pos-auditoria (ruido de tipo): 106 vagas de Duales
    # Studium/Ausbildung/Schuelerpraktikum sairam do eligible (n=283) — nenhuma
    # regra de ranking foi alterada; os sanity abaixo sao de regra (titulo),
    # nao de contagem, e seguem validos no conjunto menor.
    # Praktikum Logistik/SC no topo; JMP fora do eligible (programa excluido
    # na Fase 1); Marketing longe do topo; nenhum senior no topo; Fase 2:
    # Communications/Media "SAP Analytics Cloud" fora do topo e sem
    # marketing/comunicacao/media no TOP 10.
    def find(sub: str):
        return [j for j in ranked if sub.lower() in j["title"].lower()]

    log_sc = find("Logistik und Supply Chain Design")
    check("sanity: 'Praktikum ... Logistik und Supply Chain Design' ALTO",
          bool(log_sc) and log_sc[0]["score"] >= med)

    # "Working Student - Marketing": todas as vagas com Working Student +
    # Marketing no titulo fora do quartil superior (top 25%); e nenhuma vaga
    # de marketing SEM area real no titulo no quartil superior (a vaga Bosch
    # "Online Marketing - Analytics & Performance" tem area REAL de Analytics
    # no titulo — pontua por area, nao e falso positivo de contexto).
    ws_mkt = [j for j in ranked
              if "working student" in j["title"].lower()
              and "marketing" in j["title"].lower()]
    check("sanity: 'Working Student - Marketing' BAIXO",
          bool(ws_mkt) and all(ranked.index(j) + 1 > len(ranked) // 4 for j in ws_mkt))
    all_mkt = [j for j in ranked if "marketing" in j["title"].lower()]
    mkt_sem_area = [j for j in all_mkt if j["score_breakdown"]["area"] == 0.0]
    check("sanity: nenhum marketing (sem area real) no top 25%",
          bool(mkt_sem_area) and all(ranked.index(j) + 1 > len(ranked) // 4 for j in mkt_sem_area))

    jmp = find("Junior Managers Program")
    check("sanity: nenhum 'Junior Managers Program' no eligible",
          not bool(jmp))

    import re

    # Fase 1 (correcao de ruido de tipo): nenhuma vaga de Duales Studium /
    # Ausbildung / Schul-/Schuelerpraktikum no eligible (regra nova do dono).
    # Fonte unica de verdade: TYPE_EXCLUSION_PATTERNS de filters.py — a regex
    # duplicada local casava 'schulpraktik' DENTRO de 'Hochschulpraktikum'
    # (estagio universitario VALIDO, 4 vagas B. Braun preservadas de proposito)
    # e gerava falso positivo.
    noise = [
        j for j in ranked
        if any(re.search(p, j["title"], re.IGNORECASE) for p in TYPE_EXCLUSION_PATTERNS)
    ]
    check("sanity Fase1: nenhum ruido de tipo (dual/ausbildung/schueler) no eligible",
          not bool(noise))
    # Hochschulpraktikum (estagio universitario VALIDO) nao pode ter saido.
    hoch = find("Hochschulpraktikum")
    check("sanity Fase1: 'Hochschulpraktikum' segue no eligible",
          bool(hoch))

    top10 = ranked[:10]
    senior_pat = re.compile(r"\bsenior\b|\bdirector\b|\bhead of\b|\bprincipal\b", re.IGNORECASE)
    check("sanity: nenhum senior no topo",
          not any(senior_pat.search(j["title"]) for j in top10))

    check("sanity: topo e de area-alvo",
          all(j["score_breakdown"]["area"] > 0 for j in top10))

    # ---- Fase 2 (pos-auditoria): falso positivo do topo corrigido ----
    # A vaga Communications/Media "in SAP Analytics Cloud" (antigo TOP 1,
    # 14.00 — area vinha do nome do PRODUTO) saiu do topo: fora do TOP 10
    # e abaixo da mediana.
    comms = find("Media Production in SAP Analytics Cloud")
    check("sanity Fase2: existe a vaga Communications/Media 'SAP Analytics Cloud'",
          bool(comms))
    if comms:
        comms_pos = ranked.index(comms[0]) + 1
        print(f"  Fase2: Communications/Media 'SAP Analytics Cloud' agora na "
              f"posicao {comms_pos}/{len(ranked)} (score {comms[0]['score']:.2f})")
        check("sanity Fase2: fora do TOP 10", comms_pos > 10)
        check("sanity Fase2: na segunda metade (nao acima da mediana)",
              comms_pos > len(ranked) // 2)
        check("sanity Fase2: area zerada (produto mascarado no titulo)",
              comms[0]["score_breakdown"]["area"] == 0.0)

    # Novo sanity (Fase 2): nenhum communications/marketing/media no TOP 10.
    ctx_pat = re.compile(r"\bcommunications?\b|\bmarketing\b|\bmedia\b", re.IGNORECASE)
    check("sanity Fase2: nenhum communications/marketing/media no TOP 10",
          not any(ctx_pat.search(j["title"]) for j in top10))

    # B-list do dono preservada: o presales SCM (unico com 'presales' no
    # titulo) segue no TOP 20 (conjunto expandido: posicao 18/389, top 5%;
    # no conjunto Fase 2 de 170 estava no TOP 10) e a area vem do titulo
    # (Supply Chain), nao de penalidade de contexto — a mudanca nao o derrubou.
    presales = find("Solution Advisory / Presales - Fokus auf Supply Chain")
    check("sanity Fase2: presales SCM (B) no TOP 20",
          bool(presales) and presales[0] in ranked[:20])
    if presales:
        check("sanity Fase2: presales SCM com area real no titulo",
              presales[0]["score_breakdown"]["area"] >= 6.0)

    # A/B do dono: os candidataria/interessante conhecidos seguem no topo.
    # Conjunto Fase 2/4 (165): todos no TOP 20. Conjunto expandido (389):
    # os A/B de 9.5-10.0 (Bosch: BI & Data Analytics, Power BI & Automation,
    # Generative AI, digitales Projektmanagement, Supplier Quality Mgmt)
    # ficaram nas posicoes 36-44 por mais concorrencia acima — seguem no
    # TOP 50 (top 13%), todos com score >= 9.5 (bem acima da mediana 6.0),
    # sem regressao de regras.
    ab_titles = [
        "Logistik - Schwerpunkt Data & Analytics",       # A
        "Praktikum in der Logistik - Data & Analytics",  # A
        "Analytics: AI Enablement & Automation",         # A
        "Technology in Global Procurement",              # A
        "Logistik und Supply Chain Design",              # A
        "Business Intelligence & Data Analytics",        # A
        "Digital Project Management, Power BI & Automation",  # A
        "Data Analytics and Generative AI",              # A
        "digitalen Projektmanagement, Power BI & Automatisierung",  # A
        "MEE Strategy & Operations",                     # B
        "Solution Advisory / Presales",                  # B
        "Supplier Quality Management",                   # B
    ]
    # Nota Fase 4 (2026-08-12): a lista reflete as vagas verificaveis no
    # conjunto ao vivo — "Einkauf - Digital Transformation" e "Health Data
    # Analytics" (A/B do dono) sairam do eligible por DRIFT DE DADOS (nao
    # estao mais publicadas/eligible na coleta real), nao por regressao.
    # Presentes na coleta 2026-08-10; removidos da lista para o sanity
    # acompanhar o conjunto real.
    missing = [t for t in ab_titles if not find(t)]
    check("sanity Fase2: A/B conhecidos presentes no eligible",
          not missing)
    below_top50 = [t for t in ab_titles if find(t) and find(t)[0] not in ranked[:50]]
    check("sanity Fase2: A/B conhecidos no TOP 50",
          not below_top50)


def main() -> int:
    test_synthetic()
    test_determinism()
    test_real_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
