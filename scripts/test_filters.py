"""Testes dos filtros de tipo/estudante e pais (scripts/test_filters.py).

Doze casos definidos pelo dono na pos-auditoria (Fase 1), mais niveis de
integracao: consistencia dos marcadores/exclusoes, adapter (flag
``Job.internship``) e resolver (empresa/ATS inexistente). Uso:

    .venv/bin/python scripts/test_filters.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.filters import (  # noqa: E402
    PROGRAM_EXCLUSION_PATTERNS,
    STUDENT_TYPE_PATTERNS,
    infer_country_iso,
    is_student_role,
    matches_country,
    parse_country_spec,
)
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.resolver.company_resolver import CompanyResolver  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def test_type_rules() -> None:
    print("== regras de tipo (12 casos do dono) ==")
    # 1. Internship -> aceitar
    check("1. Internship aceito", is_student_role("Internship (m/f/d) - Supply Chain"))
    # 2. Praktikum -> aceitar
    check("2. Praktikum aceito", is_student_role("Praktikum im Einkauf"))
    # 3. Werkstudent -> aceitar
    check("3. Werkstudent aceito", is_student_role("Werkstudent (w/m/d) Data Analytics"))
    # 4. Working Student + Part-time -> aceitar
    check(
        "4. Working Student + PART_TIME aceito",
        is_student_role("Working Student (f/m/d) - BI", None, "PART_TIME"),
    )
    # 5. Part-time sem indicador estudantil -> rejeitar
    check(
        "5. PART_TIME sozinho rejeitado",
        not is_student_role("Sales Assistant (m/f/d)", None, "PART_TIME"),
    )
    # 6. Senior + Praktikum -> aceitar (marcador forte vence senioridade)
    check(
        "6. Senior + Praktikum aceito",
        is_student_role("Praktikum - Assistenz des Senior Vice Presidents"),
    )
    # 7. Graduate Trainee -> rejeitar (mesmo com employment_type "trainee")
    check(
        "7. Graduate Trainee rejeitado",
        not is_student_role("Graduate Trainee - Procurement", None, "trainee"),
    )
    # 8. Management Trainee -> rejeitar
    check(
        "8. Management Trainee rejeitado",
        not is_student_role("Management Trainee - Operations", None, "trainee"),
    )
    # 9. JMP / Junior Managers Program -> rejeitar (exclusao vence employment_type)
    check(
        "9a. Junior Managers Program rejeitado",
        not is_student_role(
            "Junior Managers Program (Trainee) - Purchasing", None, "trainee"
        ),
    )
    check(
        "9b. JMP abreviado rejeitado",
        not is_student_role("JMP - Leadership Journey", None, "trainee"),
    )
    # Trainee generico deixou de ser marcador: sem outro marcador, nao passa.
    check(
        "9c. 'Trainee' generico nao e marcador",
        not is_student_role("Trainee - Finance", None, "FULL_TIME"),
    )
    # "Internship Trainee" / contexto estudantil continua aceito (coberto por
    # intern/internship — sem regra extra).
    check(
        "9d. 'Internship Trainee' aceito (contexto estudantil)",
        is_student_role("Internship Trainee (f/m/d) - Supply Chain"),
    )


def test_location_level() -> None:
    print("== vaga sem localizacao (dois niveis) ==")
    spec_de = parse_country_spec("de")
    # is_student_role NAO depende de localizacao: aceita se tipo/area.
    check(
        "10a. is_student_role independe de localizacao (aceita)",
        is_student_role("Werkstudent - Data Analytics"),
    )
    check("10b. infer_country_iso sem localizacao -> None", infer_country_iso() is None)
    # matches_country com spec "de" REJEITA vaga sem localizacao.
    check(
        "10c. matches_country 'de' rejeita sem localizacao",
        not matches_country(None, None, None, spec_de),
    )
    check(
        "10d. matches_country 'de' aceita com country_iso=de",
        matches_country("de", None, None, spec_de),
    )
    check(
        "10e. matches_country 'all' aceita sem localizacao",
        matches_country(None, None, None, parse_country_spec("all")),
    )


def test_no_description() -> None:
    print("== vaga sem descricao ==")
    check(
        "11a. sem descricao nao quebra (titulo com marcador aceita)",
        is_student_role("Praktikum Logistik", None),
    )
    check(
        "11b. sem descricao, titulo sem marcador rejeita",
        not is_student_role("Junior Buyer (m/f/d)", None),
    )
    check(
        "11c. sem descricao, classificacao so pelo titulo",
        is_student_role("Working Student (f/m/d) - Procurement", None),
    )


def test_ats_independence() -> None:
    print("== independencia de ATS ==")
    # is_student_role nao recebe origem/ATS: mesma vaga de estagio e aceita.
    check(
        "12a. is_student_role independe do ATS (INTERN aceito)",
        is_student_role("Intern - Supply Chain", None, "INTERN"),
    )
    resolver = CompanyResolver()
    check(
        "12b. resolver empresa inexistente -> lista vazia",
        resolver.resolve("empresa-inexistente-xyz-123") == [],
    )


def test_consistency() -> None:
    print("== consistencia: marcadores x exclusoes ==")
    joined = " ".join(STUDENT_TYPE_PATTERNS).lower()
    check("trainee fora dos marcadores fortes", "trainee" not in joined)
    check("junior managers fora dos marcadores fortes", "junior managers" not in joined)
    check("jmp fora dos marcadores fortes", "jmp" not in joined)
    check(
        "exclusoes com os 4 programas do dono",
        len(PROGRAM_EXCLUSION_PATTERNS) == 4,
    )
    # Adaptador (flag Job.internship) usa a mesma regra.
    company = Company(ats="smartrecruiters", slug="BoschGroup", name="Bosch Group")
    adapter = AtsJobAdapter()
    jmp_job = adapter.to_job(
        {"title": "Junior Managers Program (Trainee) - Purchasing",
         "employment_type": "trainee"},
        company,
    )
    check("adapter: JMP -> internship False", jmp_job.internship is False)
    praktikum = adapter.to_job(
        {"title": "Praktikum Logistik - Data & Analytics"}, company
    )
    check("adapter: Praktikum -> internship True", praktikum.internship is True)


def main() -> int:
    test_type_rules()
    test_location_level()
    test_no_description()
    test_ats_independence()
    test_consistency()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
