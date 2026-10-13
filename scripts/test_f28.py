"""Testes da Fase F28 — skill-gap: dicionário, extração, relatório, CLI (100% offline).

Ferramenta determinística que responde "quais skills os anúncios de estágio
exigem, com que frequência, e quais faltam no meu perfil?". Este teste é
offline, sem rede, sem ``data/`` — fixtures SINTÉTICAS (nenhum texto real de
vaga ou de perfil; o PERFIL-CANDIDATO.md real nunca é lido aqui):

- **T1 extração**: "SAP Ariba" conta como a skill ``sap``; sinônimos DE/EN
  mapeiam para o mesmo grupo (Bedarfsermittlung == demand planning);
  Tabellenkalkulation == Excel; texto vazio/filler não gera falso positivo;
  determinismo da extração.
- **T2 gap_report**: share_eligible correto (Excel em 2 de 4 → 0.5);
  freq_title conta matches de título; skill presente no perfil NÃO é gap
  (sap, excel), skill ausente É gap (powerbi); um resultado por grupo;
  determinismo do agregado.
- **T3 parser de profile**: extrai headings/bullets de um markdown
  sintético; arquivo inexistente → string vazia (tolerante, sem raise).
- **T4 CLI**: com --profile → 3 seções (mercado/gaps/matches); SEM --profile
  → apenas a seção mercado (sem GAPS, sem MATCHES, sem coluna "in
  profile"); texto do perfil NUNCA vaza para o relatório; determinismo
  (duas execuções, saída idêntica).

Uso:  .venv/bin/python scripts/test_f28.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.skill_gap import (  # noqa: E402
    extract_skills,
    gap_report,
    profile_text,
)

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures sintéticas (nenhum dado real)
# ---------------------------------------------------------------------------
JOBS = [
    {
        "title": "Praktikum Einkauf (m/w/d)",
        "description": (
            "Du unterstuetzt den Einkauf, pflegst Stammdaten in SAP Ariba, "
            "erstellst Auswertungen in Excel und Power BI und nimmst an "
            "Verhandlungen mit Lieferanten teil."
        ),
    },
    {
        "title": "Supply Chain Intern",
        "description": (
            "Bedarfsermittlung und Disposition, Bestandsmanagement sowie "
            "Warehousing. English and German required."
        ),
    },
    {
        "title": "Werkstudent Logistik",
        "description": "Lagerlogistik, Kanban und Excel.",
    },
    {
        "title": "Procurement Intern (sourcing)",
        "description": (
            "Strategischer Einkauf, Category Management, Ausschreibungen "
            "und Vertragsmanagement."
        ),
    },
]

PROFILE_MD = """# Candidate (synthetic fixture)

## Skills
- SAP
- Excel
- Portugiesisch (native), Deutsch (A2), Englisch (fluent)
- Projektmanagement

## Experience
**Acme Corp**: Qualitaetssicherung und Reporting
"""


def _profile_signal_from(md: str) -> str:
    """Aplica a mesma extração do CLI sem depender de arquivo real."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "profile.md"
        p.write_text(md, encoding="utf-8")
        return profile_text(str(p))


def t1_extraction() -> None:
    section("T1. extração de skills (extract_skills)")

    skills = extract_skills("Erfahrung mit SAP Ariba und Coupa")
    check("T1a. JD 'SAP Ariba' conta como skill sap", "sap" in skills, f"got {skills}")

    de = extract_skills("Bedarfsermittlung und Disposition")
    en = extract_skills("demand planning for purchasing and inventory")
    check("T1b. DE Bedarfsermittlung -> demand_planning", "demand_planning" in de, f"got {de}")
    check("T1c. EN demand planning -> demand_planning", "demand_planning" in en, f"got {en}")

    check("T1d. Tabellenkalkulation -> excel",
          "excel" in extract_skills("Sicherer Umgang mit Tabellenkalkulation"), "")

    check("T1e. texto vazio -> []", extract_skills("") == [], "")
    filler = extract_skills("Wir sind ein dynamisches Team.")
    check("T1f. filler sem skills -> []", filler == [], f"got {filler}")

    twice = extract_skills("Kanban und just-in-time Optimierung")
    check("T1g. extração determinística",
          twice == extract_skills("Kanban und just-in-time Optimierung"), "")


def t2_gap_report() -> None:
    section("T2. agregação (gap_report)")

    profile = _profile_signal_from(PROFILE_MD)
    stats = gap_report(JOBS, profile_text=profile)
    by = {s.skill: s for s in stats}

    check("T2a. share_eligible excel == 0.5 (2 de 4)",
          abs(by["excel"].share_eligible - 0.5) < 1e-9, f"got {by['excel'].share_eligible}")
    check("T2b. freq_any excel == 2", by["excel"].freq_any == 2, f"got {by['excel'].freq_any}")

    check("T2c. freq_title procurement == 2 (Einkauf + Procurement)",
          by["procurement"].freq_title == 2, f"got {by['procurement'].freq_title}")

    check("T2d. sap presente no perfil -> não é gap",
          by["sap"].present_in_profile is True, "")
    check("T2e. excel presente no perfil -> não é gap",
          by["excel"].present_in_profile is True, "")
    check("T2f. powerbi ausente do perfil -> gap",
          by["powerbi"].present_in_profile is False, "")

    names = [s.skill for s in stats]
    check("T2g. um resultado por grupo de skill", len(names) == len(set(names)), "")

    again = gap_report(JOBS, profile_text=profile)
    check("T2h. gap_report determinístico",
          [s.as_dict() for s in stats] == [s.as_dict() for s in again], "")


def t3_profile_parser() -> None:
    section("T3. parser de profile (markdown tolerante)")

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "profile.md"
        p.write_text(PROFILE_MD, encoding="utf-8")
        text = profile_text(str(p))
        check("T3a. extrai headings e bullets", "SAP" in text and "## Skills" in text,
              f"got {text[:80]!r}")
        check("T3b. arquivo inexistente -> '' (sem raise)",
              profile_text(str(Path(tmp) / "nope.md")) == "", "")


def t4_cli() -> None:
    section("T4. CLI (scripts/skill_gap_report.py)")

    cli = Path(__file__).resolve().parent / "skill_gap_report.py"
    with tempfile.TemporaryDirectory() as tmp:
        jobs_path = Path(tmp) / "jobs.json"
        jobs_path.write_text(json.dumps(JOBS), encoding="utf-8")
        prof_path = Path(tmp) / "profile.md"
        prof_path.write_text(PROFILE_MD, encoding="utf-8")

        out_with = subprocess.run(
            [sys.executable, str(cli), "--input", str(jobs_path),
             "--profile", str(prof_path), "--top", "40"],
            capture_output=True, text=True, check=True,
        ).stdout
        check("T4a. com --profile: seção mercado presente",
              "Top skills in the market" in out_with, "")
        check("T4b. com --profile: seção GAPS presente", "GAPS" in out_with, "")
        check("T4c. com --profile: seção MATCHES presente", "MATCHES" in out_with, "")

        out_no = subprocess.run(
            [sys.executable, str(cli), "--input", str(jobs_path), "--top", "40"],
            capture_output=True, text=True, check=True,
        ).stdout
        check("T4d. sem --profile: apenas mercado", "Top skills in the market" in out_no, "")
        check("T4e. sem --profile: sem seção GAPS", "GAPS" not in out_no, "")
        check("T4f. sem --profile: sem seção MATCHES", "MATCHES" not in out_no, "")
        check("T4g. sem --profile: sem coluna 'in profile'", "in profile" not in out_no, "")

        check("T4h. texto do perfil não vaza para o relatório",
              "Acme Corp" not in out_with and "Acme Corp" not in out_no, "")

        out_again = subprocess.run(
            [sys.executable, str(cli), "--input", str(jobs_path),
             "--profile", str(prof_path), "--top", "40"],
            capture_output=True, text=True, check=True,
        ).stdout
        check("T4i. CLI determinístico (saída idêntica)", out_with == out_again, "")


def main() -> int:
    t1_extraction()
    t2_gap_report()
    t3_profile_parser()
    t4_cli()

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print(f"OK — test_f28: {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
