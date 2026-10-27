"""Testes do F137 — Stale automático: posted_at > 12 meses = ineligível (stale_posting).

Fixtures com posted_at de 24m/18m/13m (corta) e 11m/ausente (não corta).
Probe: título AXA com posted 2024-10-24 → ineligível com motivo `stale_posting`.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.filters import (
    APPLICABILITY_EXCLUSION_REASONS,
    STALE_POSTING_THRESHOLD_MONTHS,
    applicability_exclusion_reason,
    is_stale_posting,
    select_eligible,
)

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def test_threshold_constant() -> None:
    print("== F137: threshold constante ==")
    check("STALE_POSTING_THRESHOLD_MONTHS == 12", STALE_POSTING_THRESHOLD_MONTHS == 12)
    check("stale_posting em APPLICABILITY_EXCLUSION_REASONS", "stale_posting" in APPLICABILITY_EXCLUSION_REASONS)


def test_is_stale_posting_detector() -> None:
    print("== F137: detector is_stale_posting ==")
    today = date.today()

    # 24 meses (AXA case) -> deve ser True (stale)
    old_24m = (today - timedelta(days=24 * 30)).isoformat()
    job_24m = {"posted_at": old_24m}
    check("24 meses (AXA) -> stale=True", is_stale_posting(job_24m) is True)

    # 18 meses (Consultport case) -> deve ser True (stale)
    old_18m = (today - timedelta(days=18 * 30)).isoformat()
    job_18m = {"posted_at": old_18m}
    check("18 meses (Consultport) -> stale=True", is_stale_posting(job_18m) is True)

    # 13 meses -> deve ser True (stale, > 12)
    old_13m = (today - timedelta(days=13 * 30)).isoformat()
    job_13m = {"posted_at": old_13m}
    check("13 meses -> stale=True", is_stale_posting(job_13m) is True)

    # 12 meses exatos (365 dias) -> deve ser False (<= threshold)
    old_12m = (today - timedelta(days=365)).isoformat()
    job_12m = {"posted_at": old_12m}
    check("12 meses exatos (365d) -> stale=False", is_stale_posting(job_12m) is False)

    # 11 meses -> deve ser False (não stale)
    old_11m = (today - timedelta(days=11 * 30)).isoformat()
    job_11m = {"posted_at": old_11m}
    check("11 meses -> stale=False", is_stale_posting(job_11m) is False)

    # posted_at ausente -> deve ser False (neutro, nunca mata)
    job_none = {}
    check("posted_at ausente -> stale=False (neutro)", is_stale_posting(job_none) is False)

    # posted_at vazia -> deve ser False (neutro)
    job_empty = {"posted_at": ""}
    check("posted_at vazia -> stale=False (neutro)", is_stale_posting(job_empty) is False)

    # posted_at inválida -> deve ser False (neutro)
    job_invalid = {"posted_at": "invalid-date"}
    check("posted_at inválida -> stale=False (neutro)", is_stale_posting(job_invalid) is False)

    # posted_at no futuro (clock skew) -> deve ser False
    future = (today + timedelta(days=30)).isoformat()
    job_future = {"posted_at": future}
    check("posted_at futuro -> stale=False", is_stale_posting(job_future) is False)

    # posted_at com timezone -> deve funcionar
    job_tz = {"posted_at": (today - timedelta(days=15 * 30)).isoformat() + "+00:00"}
    check("posted_at com timezone (15m) -> stale=True", is_stale_posting(job_tz) is True)


def test_applicability_exclusion_reason() -> None:
    print("== F137: applicability_exclusion_reason ==")
    today = date.today()

    # AXA case: posted 24/10/2024 (~24 meses atrás do 'hoje' simulado)
    # Usamos uma data fixa para teste determinístico
    axa_date = "2024-10-24"
    job_axa = {
        "title": "Praktikum Datenanalyse",
        "company": "AXA",
        "description": "Estágio em análise de dados",
        "posted_at": axa_date,
    }
    reason = applicability_exclusion_reason(job_axa)
    check(f"AXA (posted {axa_date}) -> stale_posting", reason == "stale_posting")

    # Consultport case: ~18 meses
    cp_date = (today - timedelta(days=18 * 30)).strftime("%Y-%m-%d")
    job_cp = {
        "title": "Praktikum Consulting",
        "company": "Consultport",
        "description": "Consulting internship",
        "posted_at": cp_date,
    }
    reason = applicability_exclusion_reason(job_cp)
    check(f"Consultport (posted {cp_date}) -> stale_posting", reason == "stale_posting")

    # 13 meses -> stale_posting
    old_13m = (today - timedelta(days=13 * 30)).strftime("%Y-%m-%d")
    job_13m = {
        "title": "Praktikum Supply Chain",
        "company": "TestCo",
        "description": "Supply chain internship",
        "posted_at": old_13m,
    }
    reason = applicability_exclusion_reason(job_13m)
    check(f"13 meses (posted {old_13m}) -> stale_posting", reason == "stale_posting")

    # 11 meses -> NÃO stale_posting (pode passar se não houver outro motivo)
    old_11m = (today - timedelta(days=11 * 30)).strftime("%Y-%m-%d")
    job_11m = {
        "title": "Praktikum Procurement",
        "company": "TestCo",
        "description": "Procurement internship",
        "posted_at": old_11m,
    }
    reason = applicability_exclusion_reason(job_11m)
    check(f"11 meses (posted {old_11m}) -> NÃO stale_posting", reason != "stale_posting")

    # posted_at ausente -> NÃO stale_posting (neutro)
    job_no_date = {
        "title": "Praktikum Logistics",
        "company": "TestCo",
        "description": "Logistics internship",
        # sem posted_at
    }
    reason = applicability_exclusion_reason(job_no_date)
    check("posted_at ausente -> NÃO stale_posting (neutro)", reason != "stale_posting")

    # posted_at inválida -> NÃO stale_posting (neutro)
    job_bad_date = {
        "title": "Praktikum IT",
        "company": "TestCo",
        "description": "IT internship",
        "posted_at": "not-a-date",
    }
    reason = applicability_exclusion_reason(job_bad_date)
    check("posted_at inválida -> NÃO stale_posting (neutro)", reason != "stale_posting")


def test_select_eligible_integration() -> None:
    print("== F137: integração select_eligible ==")
    today = date.today()

    jobs = [
        {
            "id": "axa|source:1",
            "title": "Praktikum Data Analysis",
            "company": "AXA",
            "location": "Berlin, DE",
            "country_iso": "de",
            "url": "https://example.com/axa",
            "description": "Data analysis internship in procurement",
            "posted_at": "2024-10-24",  # ~24 meses
            "employment_type": "INTERN",
        },
        {
            "id": "cp|source:2",
            "title": "Praktikum Supply Chain Analytics",
            "company": "Consultport",
            "location": "Munich, DE",
            "country_iso": "de",
            "url": "https://example.com/cp",
            "description": "Supply chain analytics internship",
            "posted_at": (today - timedelta(days=18 * 30)).strftime("%Y-%m-%d"),  # ~18 meses
            "employment_type": "INTERN",
        },
        {
            "id": "fresh|source:3",
            "title": "Praktikum Supply Chain",
            "company": "FreshCo",
            "location": "Berlin, DE",
            "country_iso": "de",
            "url": "https://example.com/fresh",
            "description": "Supply chain internship",
            "posted_at": (today - timedelta(days=30)).strftime("%Y-%m-%d"),  # 1 mês
            "employment_type": "INTERN",
        },
        {
            "id": "no_date|source:4",
            "title": "Praktikum Logistics",
            "company": "NoDateCo",
            "location": "Berlin, DE",
            "country_iso": "de",
            "url": "https://example.com/nodate",
            "description": "Logistics internship",
            # sem posted_at
            "employment_type": "INTERN",
        },
    ]

    selected, counts = select_eligible(
        jobs,
        student=True,
        area=True,
        country="de",
        applicability=True,
        intel_map=None,
    )

    # Verifica contagens
    check(f"Total: {counts['total']}", counts["total"] == 4)
    check(f"stale_posting excluídas: {counts.get('aplicabilidade_excluidas_stale_posting', 0)}",
          counts.get("aplicabilidade_excluidas_stale_posting", 0) == 2)
    check(f"Eligible final: {counts['aplicabilidade']}", counts["aplicabilidade"] == 2)

    # Verifica quais ficaram
    selected_ids = {j["id"] for j in selected}
    check("AXA (24m) excluída", "axa|source:1" not in selected_ids)
    check("Consultport (18m) excluída", "cp|source:2" not in selected_ids)
    check("FreshCo (1m) mantida", "fresh|source:3" in selected_ids)
    check("NoDateCo (sem data) mantida", "no_date|source:4" in selected_ids)


def test_first_match_order() -> None:
    """Verifica que stale_posting é último na ordem first-match (após recent_graduate)."""
    print("== F137: ordem first-match ==")
    # O motivo stale_posting deve ser o ÚLTIMO a ser checado
    # (adicionamos no final de APPLICABILITY_EXCLUSION_REASONS)
    reasons = list(APPLICABILITY_EXCLUSION_REASONS)
    check("stale_posting é último na tupla", reasons[-1] == "stale_posting")
    check("recent_graduate vem antes de stale_posting", reasons[-2] == "recent_graduate")


def main() -> int:
    test_threshold_constant()
    test_is_stale_posting_detector()
    test_applicability_exclusion_reason()
    test_select_eligible_integration()
    test_first_match_order()

    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())