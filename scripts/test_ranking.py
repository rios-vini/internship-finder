"""Testes do modulo de ranking (scripts/test_ranking.py).

Roda tres blocos: (1) score_job sintetico (componentes e regras de negocio),
(2) determinismo/desempate/robustez, (3) execucao real sobre
data/relevant_jobs.json com distribucao, TOP 10 e sanity checks. Uso:

    .venv/bin/python scripts/test_ranking.py
"""

from __future__ import annotations

import json
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

    # 3. JMP Purchasing: "Junior Managers Program" no titulo protege de
    #    penalidade de "manager" (marcador forte de tipo vence senioridade).
    jmp = score_job(
        base_job(
            id="test:3",
            title="Junior Managers Program (Trainee) - Start your Leadership "
            "Journey in Purchasing",
            description=None,
        )
    )
    check("JMP: sem penalidade de manager", jmp.breakdown["penalties"] >= -0.5)
    check("JMP: area alta (purchasing primary)", jmp.breakdown["area"] >= 3.0)
    check("JMP: tipo no titulo", jmp.breakdown["type"] == 1.0)
    check("JMP: score alto", jmp.total >= 4.0)

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
    print("== execucao real (data/relevant_jobs.json) ==")
    root = Path(__file__).resolve().parent.parent
    jobs = json.loads((root / "data" / "relevant_jobs.json").read_text(encoding="utf-8"))
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

    # Sanity checks da especificacao (calibrados no conjunto real 2026-08-10:
    # mediana ~6.25; Praktikum Logistik/SC no topo; JMP acima da mediana;
    # Marketing longe do topo; nenhum senior no topo).
    def find(sub: str):
        return [j for j in ranked if sub.lower() in j["title"].lower()]

    log_sc = find("Logistik und Supply Chain Design")
    check("sanity: 'Praktikum ... Logistik und Supply Chain Design' ALTO",
          bool(log_sc) and log_sc[0]["score"] >= med)

    # "Working Student - Marketing": todas as vagas com Working Student +
    # Marketing no titulo abaixo da mediana, e NENHUMA vaga de marketing no
    # quartil superior (top 25%).
    ws_mkt = [j for j in ranked
              if "working student" in j["title"].lower()
              and "marketing" in j["title"].lower()]
    check("sanity: 'Working Student - Marketing' BAIXO",
          bool(ws_mkt) and all(j["score"] <= med for j in ws_mkt))
    all_mkt = [j for j in ranked if "marketing" in j["title"].lower()]
    check("sanity: nenhum marketing no top 25%",
          bool(all_mkt) and all(ranked.index(j) + 1 > len(ranked) // 4 for j in all_mkt))

    jmp = find("Junior Managers Program")
    check("sanity: 'Junior Managers Program' alto",
          bool(jmp) and any(j["score"] >= med for j in jmp))

    import re

    top10 = ranked[:10]
    senior_pat = re.compile(r"\bsenior\b|\bdirector\b|\bhead of\b|\bprincipal\b", re.IGNORECASE)
    check("sanity: nenhum senior no topo",
          not any(senior_pat.search(j["title"]) for j in top10))

    check("sanity: topo e de area-alvo",
          all(j["score_breakdown"]["area"] > 0 for j in top10))


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
