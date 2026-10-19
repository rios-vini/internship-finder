#!/usr/bin/env python3
''''true; V="$(dirname "$0")/../.venv/bin/python"; [ -x "$V" ] || V=python3; exec "$V" -- "$0" "$@" # '''
"""Suite F61_visa — Visa §16e: exigência textual de permit já válido a não-UE.

Poliglota de 1 linha (bash: ``exec`` re-invoca sob python3; python: string
no-op) — ``bash scripts/test_f61_visa.py`` e ``python scripts/test_f61_visa.py``
rodam a mesma suíte; o CI usa ``python scripts/$t.py`` (contrato ci.yml).

F61 (19/10): MAHLE Lead-Buying (score 4.5) passou no pipeline apesar de
"Für Nicht-EU-Bürger: gültiger Aufenthaltstitel erforderlich" na
description — o dono (§16e PRIMEIRA ENTRADA, muda jan/2027) não tem
título de residência antes de emigrar e eliminou a vaga manualmente
(REGISTRO-AVALIACOES-VAGAS 10/2026).

MEDIÇÃO PRÉ-IMPLEMENTAÇÃO (archive 20261018T090001Z; estágio de
aplicabilidade = 3.121; A/B completo no relatório
~/.hermes/handoff/f61-visa-s16e/):

- ``app_intel.work_authorization`` JÁ devolve ``existing_required`` para
  a description MAHLE — a falha era da CADEIA: ``visa_blocked`` era
  intel-only e a MAHLE é ``unclear`` na curadoria F9. O detector novo
  (``requires_existing_permit_for_non_eu``) fecha o buraco pelo padrão
  ESPECÍFICO endereçado-a-não-UE + qualificador de exigência — NÃO pelo
  estado genérico (patterns _WA_EXISTING incluem alternativas sem
  qualificador; ``EU-Bürger`` bare casa o pattern [3]).
- A/B cascata (main 99ca2ce vs branch, mesmo input congelado): 16 saem
  / 0 entram (8 postings MAHLE × 2 fontes); visa_blocked 66→84
  (+16 novas +2 re-atribuídas de master_required 43→41, first-match);
  german_required 1189 inalterado. the-exploration-company (patrocínio
  real, no eligible HOJE) SOBREVIVE na cadeia.
- Universo 18/10: 165 vagas mencionam permit SEM o qualificador não-UE
  → ZERO casam o padrão (VW "Ggf. ... für Nicht-EU-Bürgerinnen" ordem
  INVERTIDA, STIHL "wenn vorliegend", Fraunhofer "ggf." ficam).

NOME: esta suíte chama-se ``test_f61_visa`` porque ``test_f61`` já é a
suíte da fase F6.1 (compactação do Top 5 no Telegram, PR #100) — colisão
de numeração verificada ao vivo; nenhum arquivo existente é tocado.

ZERO REDE: todos os fixtures são strings VERBATIM do archive
20261018T090001Z (descriptions/janelas copiadas sem invenção); nenhuma
leitura de data/, nenhum socket.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from internship_finder.filters import (  # noqa: E402
    APPLICABILITY_EXCLUSION_REASONS,
    applicability_exclusion_reason,
    requires_existing_permit_for_non_eu,
    select_eligible,
)

ROOT = Path(__file__).resolve().parent.parent
CHECKS: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# Fixtures VERBATIM — archive 20261018T090001Z (jobs.json), sem invenção.
# ---------------------------------------------------------------------------

# MAHLE Lead-Buying DE — a vaga da card, description COMPLETA
# (id: MAHLE International GmbH|sf_dataset:successfactors:1373497333,
#  também successfactors:mahleinter:1373497333 — twin do registry;
#  score 4.5 no pipeline, eliminada manualmente pelo dono)
F_MAHLE_DE_TITLE = "Praktikum Lead-Buying Mechatronics (m/w/d)"
F_MAHLE_DE = (
    "Zeitraum ab sofort für einen Zeitraum von 6 Monaten Tätigkeiten "
    "Mitwirken bei der Transformation der Kaufteil-Strategien im Hinblick "
    "auf Mechatronik an der Seite unserer strategischen Einkäufer im engen "
    "Austausch mit der Produktentwicklung und externen Partnern "
    "Unterstützung bei der Vor- und Nachbereitung von Rahmenvertrags- und "
    "Preisverhandlungen, externen Meetings sowie Abteilungs- und "
    "Projektteamsitzungen zur Sicherung der Unternehmensinteressen "
    "bezüglich Mensch, Umwelt, Technik und Kosten Bearbeitung spannender "
    "Projekte im internationalen Kontext (Planung von Lieferantentage im "
    "Haus MAHLE, Markt- und Portfolioanalysen von Unternehmenspartnern und "
    "potenziellen Lieferanten, Benchmark-Analysen, etc.) Erstellung von "
    "einkaufsspezifischen Analysen und Kennzahlen-Reports mithilfe der "
    "Einkaufstools, SAP und MS Excel Organisation von Team-Events "
    "Voraussetzungen Immatrikulation im Studiengang Betriebswirtschaftslehre, "
    "Maschinenbau oder einem ähnlichen Studiengang Analytisches "
    "Denkvermögen und selbstständige Arbeitsweise Gute MS-Office "
    "Kenntnisse, insbesondere Excel und PowerPoint Gute Englischkenntnisse "
    "Engagement und Teamfähigkeit Bewerbungsunterlagen Vollständiger "
    "Lebenslauf Motivationsschreiben Immatrikulationsbescheinigung "
    "Zeugnisse, v. a. aktueller Notenspiegel Bei Pflichtpraktika: "
    "Praktikumsrichtlinien der Universität bzw. Hochschule aus der die "
    "Mindestdauer hervorgeht Für Nicht-EU-Bürger: gültiger "
    "Aufenthaltstitel erforderlich Benefits Attraktive Vergütung "
    "35-Stunden-Woche mit flexiblen Arbeitszeiten Bezahlte Urlaubstage "
    "Vergünstigtes Mittagessen im Betriebsrestaurant Kostenfreie "
    "Parkmöglichkeiten Urbanes Umfeld mit guter Verkehrsanbindung "
    "Individuelle Betreuung im Fachbereich Begleitende Aktivitäten und "
    "Studierendennetzwerk Haben Sie Fragen? +49 711 501-47574"
)

# MAHLE Lead-Buying EN — twin inglês (mesma família de postings; o padrão
# EN mediu 16 registros no estágio 18/10)
# (id: MAHLE International GmbH|successfactors:mahleinter:1374077433)
F_MAHLE_EN_TITLE = "Internship (m/f/d) Lead-Buying Mechatronics"
F_MAHLE_EN = (
    "Time period Immediately for a period of 6 months Tasks Support the "
    "lead buyer with the purchasing material group strategies about "
    "mechatronic components, in close cooperation with product development "
    "and external partners Support in the preparation and follow-up of "
    "framework contract and price negotiations, external meetings as well "
    "as department and project team meetings Processing exciting projects "
    "in an international context (planning of supplier days at MAHLE, "
    "market and portfolio analyses of existing suppliers and potential "
    "suppliers, benchmark analyses, etc.) Creation of purchase-specific "
    "analyses and key performance indicator reports using the purchasing "
    "tools, SAP and MS Excel Organization of team events Requirements "
    "Enrolment in the degree program Business Administration, Mechanical "
    "Engineer or Similar Analytical thinking skills and independent way of "
    "working Good MS-Office skills, especially Excel and PowerPoint Good "
    "English skills Commitment and teamwork Application documents Complete "
    "resume Letter of motivation Certificate of enrollment Transcripts, "
    "especially current grade reports For mandatory internship: University "
    "or college guidelines specifying the minimum duration For non-EU "
    "citizens: Valid residence permit required Benefits Attractive "
    "remuneration 35-hour week with flexible working hours Paid vacation "
    "days Discounted lunch in the company restaurant Free parking Urban "
    "environment with good transport connections Individual support in the "
    "department Accompanying activities and student network #TeamMAHLE ist "
    "vielfältig und das sehen wir als großen Vorteil! Wir freuen uns auf "
    "Bewerbungen mit unterschiedlichen Erfahrungen, Hintergründen und "
    "Identitäten. Do you have any questions? SABINE.PASSEK@MAHLE.COM "
    "+49 711 501-47574"
)

# CONTRA-CASO 1 — the-exploration-company (patrocínio REAL; no eligible
# 739 do dia 18/10; janela verbatim)
# (id: the-exploration-company|sf_dataset:ashby:c0bd5a1e-0150-417f-9e83-afa9494d2357)
F_EXPLORATION_TITLE = (
    "Internship - Radiation Testing of Electronic Components and Test Automation"
)
F_EXPLORATION = (
    "r, national origin, gender, sexual orientation, age, marital status or "
    "disability status. Relocation assistance is provided for those willing "
    "to relocate including visa sponsorship where applicable.*       *All "
    "offers are contingent upon the successful complet"
)

# CONTRA-CASO 2 — internations People Experience Intern (estágio,
# patrocínio verbatim; NÃO está no estágio por filtro de área, mas o
# texto é do universo)
# (id: internations|sf_dataset:smartrecruiters:744000145780559)
F_INTERNATIONS_TITLE = "People Experience Intern"
F_INTERNATIONS = (
    "ons: a growing, dynamic company with an international team work in a "
    "fully remote setting support with your visa application a "
    "climate-neutral company a friendly atmosphere and the space to "
    "pursue your ideas 30 paid vacation days + special paid leave the optio"
)

# Contra-casos extras do universo (patrocínio explícito, janelas verbatim)
F_TEAMPICNIC = (
    "hat's why we offer lots of support for our many expat colleagues, "
    "including:&nbsp;</p> <p>Relocation package: If you join Picnic from "
    "abroad, we'll cover your trip to Amsterdam, sponsor your Visa, and "
    "offer you a month of accommodation while you settle in (as "
)
F_MMS = (
    "in Barceloneta , right in the center of Barcelona. Free coffee and "
    "free fruit once a week If you need a VISA , don't worry, we'll assist "
    "you with the visa process and accompany you throughout the entire "
    "process! There is a training budget so you can continue d"
)
# MAHLE Tailândia — a PRÓPRIA MAHLE oferece sponsorship em outra vaga:
# o padrão não pode bloquear patrocínio nem da mesma empresa.
# (id: MAHLE International GmbH|successfactors:mahleinter:1421077433)
F_MAHLE_TH = (
    "lobal stakeholders. Japanese candidates currently based in Thailand "
    "are welcome to apply. Visa and work permit sponsorship will be "
    "provided by the company. Willingness to work on-site at MAHLE Thermal "
    "and Fluid Systems (Thailand) Co., Ltd. - Rojjana, Ayutthaya"
)

# NEAR-MISSES medidos (devem continuar NÃO bloqueados)
# VW (id: Volkswagen AG|successfactors:VWAGLPPROD10:1443186533) —
# condicional "Ggf." + ordem INVERTIDA (documento ANTES de nicht-eu)
F_VW_TITLE = "Praktikum Räder-/Reifenentwicklung (w/m/d)"
F_VW = (
    "ller Notenspiegel Bei einem Pflichtpraktikum zusätzlich eine "
    "Bescheinigung der Hochschule Ggf. Arbeits- und Aufenthaltserlaubnis "
    "inkl. Zusatzblatt für Nicht-EU-Bürgerinnen / -Bürger Keywords "
    "Informationsmodellierung, Anforderungsmanagement, Prozessoptimierung,"
)
# STIHL (id: STIHL|successfactors:jobs:1427335433) — condicional
# "wenn vorliegend" (evidência Fase F)
F_STIHL = (
    "nterlagen bei: Lebenslauf, aktueller Notenspiegel und "
    "Immatrikulationsbescheinigung sowie wenn vorliegend Arbeitszeugnisse "
    "und deine gültige Arbeits- und Aufenthaltserlaubnis"
)
# Fraunhofer (id: Fraunhofer-Gesellschaft|successfactors:fraunhofer:1396444533)
F_FRAUNHOFER = (
    "t Ihren vollständigen Bewerbungsunterlagen (Anschreiben, Lebenslauf, "
    "Immatrikulationsbescheinigung, ggf. Arbeitserlaubnis)! Fragen zu "
    "dieser Position beantwortet Ihnen gerne: Frau Katriya Seitz Recruiting"
)
# celonis (id: celonis|greenhouse:celonis:7887061003) — no_sponsorship
# NÃO é visa_blocked (o dono traz o próprio visto §16e)
F_CELONIS = (
    '</div> </div> </div> </div> </div> </div> </div> </div> </div> </div> '
    '</div> <p>Visa sponsorship is not offered for this role.</p><div '
    'class="content-conclusion'
)


def _job(title: str, description: str | None) -> dict:
    return {
        "id": f"fixture|f61:{abs(hash(title)) % 10**8}",
        "company": "Fixture Co",
        "title": title,
        "description": description,
        "country_iso": "de",
        "location": "Stuttgart, DE",
    }


# ---------------------------------------------------------------------------
# A. Detector puro — casos positivos
# ---------------------------------------------------------------------------
section("A: detector — exigência endereçada a não-UE (positivos)")

check(
    "A1 MAHLE DE verbatim COMPLETA (a vaga da card) casa o detector",
    requires_existing_permit_for_non_eu(F_MAHLE_DE_TITLE, F_MAHLE_DE) is True,
)
check(
    "A2 MAHLE EN verbatim (twin inglês, 'Valid residence permit required') "
    "casa o detector",
    requires_existing_permit_for_non_eu(F_MAHLE_EN_TITLE, F_MAHLE_EN) is True,
)
# variantes estruturais (0 ocorrências no universo 18/10 — forma canônica,
# rotuladas como tais; mesmas janelas/qualificadores dos verbatim)
check(
    "A3 variante DE Aufenthaltserlaubnis (canônica, 0 no universo) casa",
    requires_existing_permit_for_non_eu(
        "Praktikum", "Für Nicht-EU-Bürger: gültige Aufenthaltserlaubnis erforderlich"
    ) is True,
)
check(
    "A4 variante EN work permit (canônica, 0 no universo) casa",
    requires_existing_permit_for_non_eu(
        "Internship", "For non-EU citizens: valid work permit required"
    ) is True,
)
check(
    "A5 phrasing no TÍTULO também casa (detector lê title+description)",
    requires_existing_permit_for_non_eu(
        "Praktikum für Nicht-EU-Bürger: gültiger Aufenthaltstitel erforderlich", None
    ) is True,
)
check(
    "A6 entradas vazias/None não crasham e não casam",
    requires_existing_permit_for_non_eu(None, None) is False
    and requires_existing_permit_for_non_eu("", "") is False,
)

# ---------------------------------------------------------------------------
# B. Cadeia — applicability_exclusion_reason devolve visa_blocked
# ---------------------------------------------------------------------------
section("B: cadeia — visa_blocked textual com e SEM intel_map")

check(
    "B1 MAHLE DE → visa_blocked COM intel_map",
    applicability_exclusion_reason(_job(F_MAHLE_DE_TITLE, F_MAHLE_DE), intel_map={})
    == "visa_blocked",
)
check(
    "B2 MAHLE DE → visa_blocked SEM intel_map (caminho da re-avaliação "
    "pós-hidratação F20/F25, chamada sem mapa)",
    applicability_exclusion_reason(_job(F_MAHLE_DE_TITLE, F_MAHLE_DE))
    == "visa_blocked",
)
check(
    "B3 MAHLE EN → visa_blocked sem intel_map",
    applicability_exclusion_reason(_job(F_MAHLE_EN_TITLE, F_MAHLE_EN))
    == "visa_blocked",
)

# ---------------------------------------------------------------------------
# C. CONTRA-CASOS (anti-falso-positivo — não negociável)
# ---------------------------------------------------------------------------
section("C: contra-casos — patrocínio OFERECIDO nunca vira bloqueio")

check(
    "C1 the-exploration-company (patrocínio real, no eligible 18/10) "
    "continua aplicável na cadeia",
    applicability_exclusion_reason(_job(F_EXPLORATION_TITLE, F_EXPLORATION))
    is None,
)
check(
    "C2 internations 'support with your visa application' continua aplicável",
    applicability_exclusion_reason(_job(F_INTERNATIONS_TITLE, F_INTERNATIONS))
    is None,
)
check(
    "C3 teampicnic 'sponsor your Visa' não casa o detector",
    requires_existing_permit_for_non_eu("Software Engineer", F_TEAMPICNIC) is False,
)
check(
    "C4 MediaMarktSaturn 'we'll assist you with the visa process' não casa",
    requires_existing_permit_for_non_eu("AI Platform Engineer", F_MMS) is False,
)
check(
    "C5 MAHLE Tailândia 'Visa and work permit sponsorship will be provided "
    "by the company' não casa (nem patrocínio da PRÓPRIA MAHLE bloqueia)",
    requires_existing_permit_for_non_eu(
        "Head of Quality Management - Japanese Speaking (MTTH)", F_MAHLE_TH
    ) is False,
)

# ---------------------------------------------------------------------------
# D. Near-misses medidos (perm sem qualificador não-UE / ordem invertida /
#    condicionais) — ficam
# ---------------------------------------------------------------------------
section("D: near-misses — condicionais e ordem invertida ficam")

check(
    "D1 VW 'Ggf. Arbeits- und Aufenthaltserlaubnis ... für "
    "Nicht-EU-Bürgerinnen' (condicional, ordem INVERTIDA) não bloqueia",
    requires_existing_permit_for_non_eu(F_VW_TITLE, F_VW) is False,
)
check(
    "D2 STIHL 'wenn vorliegend ... gültige Arbeits- und Aufenthaltserlaubnis' "
    "não bloqueia",
    requires_existing_permit_for_non_eu("Abschlussarbeit Innovative Antriebssysteme", F_STIHL)
    is False,
)
check(
    "D3 Fraunhofer 'ggf. Arbeitserlaubnis' não bloqueia",
    requires_existing_permit_for_non_eu("Masterarbeit: Aufpralldynamik", F_FRAUNHOFER)
    is False,
)
check(
    "D4 celonis 'Visa sponsorship is not offered' (no_sponsorship) NÃO é "
    "visa_blocked — o dono traz o próprio visto §16e; aviso ≠ bloqueio",
    requires_existing_permit_for_non_eu("Field CTO", F_CELONIS) is False
    and applicability_exclusion_reason(_job("Field CTO", F_CELONIS)) is None,
)

# ---------------------------------------------------------------------------
# E. Negações (guard) — negação no span casado invalida a exigência
# ---------------------------------------------------------------------------
section("E: negações — guard suprime; controle positivo confirma")

check(
    "E1 'kein gültiger Aufenthaltstitel erforderlich' NÃO bloqueia",
    requires_existing_permit_for_non_eu(
        "Praktikum", "Für Nicht-EU-Bürger: kein gültiger Aufenthaltstitel erforderlich"
    ) is False,
)
check(
    "E2 'residence permit not required' NÃO bloqueia",
    requires_existing_permit_for_non_eu(
        "Internship", "For non-EU citizens: Valid residence permit not required"
    ) is False,
)
check(
    "E3 'no valid residence permit required' NÃO bloqueia",
    requires_existing_permit_for_non_eu(
        "Internship", "For non-EU citizens: no valid residence permit required"
    ) is False,
)
check(
    "E4 controle positivo: as MESMAS sentenças de E1–E3 SEM a negação "
    "bloqueiam (o guard é quem suprime, não regex quebrado)",
    requires_existing_permit_for_non_eu(
        "Praktikum", "Für Nicht-EU-Bürger: gültiger Aufenthaltstitel erforderlich"
    )
    is True
    and requires_existing_permit_for_non_eu(
        "Internship", "For non-EU citizens: Valid residence permit required"
    )
    is True,
)

# ---------------------------------------------------------------------------
# F. Registro e contadores — mecanismo F37 reutilizado, nada novo p/ criar
# ---------------------------------------------------------------------------
section("F: contadores — mecanismo F37 existente, visa_blocked alcançável")

check(
    "F1 visa_blocked já é motivo do APPLICABILITY_EXCLUSION_REASONS "
    "(nenhum motivo novo; o contador existente passa a contar o caminho "
    "textual)",
    "visa_blocked" in APPLICABILITY_EXCLUSION_REASONS,
)

from refresh_daily import (  # noqa: E402
    HYDRATION_INAPPLICABLE_FLAG,
    _applicability_metrics_record,
    _reassess_hydrated_applicability,
)

mahle_job = _job(F_MAHLE_DE_TITLE, F_MAHLE_DE)
mahle_job["description_source"] = "hydration"
check(
    "F2 re-avaliação pós-hidratação (F20/F25, sem intel_map) devolve "
    "visa_blocked para a MAHLE hidratada",
    _reassess_hydrated_applicability(mahle_job) == "visa_blocked",
)

flagged = dict(mahle_job)
flagged[HYDRATION_INAPPLICABLE_FLAG] = "visa_blocked"
rec = _applicability_metrics_record([flagged, _job("Outra vaga", "Einkauf")])
check(
    "F3 registro type:applicability conta flagged_visa_blocked == 1 e a "
    "matemática fecha (eligible 2, flagged 1, applicable 1)",
    rec.get("flagged_visa_blocked") == 1
    and rec.get("eligible") == 2
    and rec.get("flagged") == 1
    and rec.get("applicable") == 1,
    f"rec={ {k: rec[k] for k in ('eligible', 'flagged', 'applicable', 'flagged_visa_blocked')} }",
)

check(
    "F4 reversibilidade: select_eligible(applicability=False) mantém a MAHLE "
    "(comportamento pré-F18 intacto)",
    any(
        j["title"] == F_MAHLE_DE_TITLE
        for j in select_eligible(
            [mahle_job], country="de", applicability=False
        )[0]
    ),
)

# ---------------------------------------------------------------------------
# G. ci.yml — união RELATIVA (presença; contagens nunca hardcoded)
# ---------------------------------------------------------------------------
section("G: ci.yml — união relativa")

ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
m = re.search(r"tests=\(([^)]*)\)", ci, re.S)
arr = m.group(1).split() if m else []
check(
    "G1 test_f61_visa presente no array do CI (união por presença)",
    "test_f61_visa" in arr,
    f"{len(arr)} suítes",
)
check(
    "G2 array vivo e relativo (>= 99 suítes; contagem nunca exata)",
    len(arr) >= 99,
    f"{len(arr)}",
)

# ---------------------------------------------------------------------------
# H. Colisão de nome — test_f61.py é da F6.1 (compactação Telegram); esta
#    suíte é test_f61_visa. Nenhum arquivo existente foi tocado.
# ---------------------------------------------------------------------------
section("H: colisão de numeração F61 × F6.1 (documentada)")

f61_old = ROOT / "scripts" / "test_f61.py"
check(
    "H1 scripts/test_f61.py (suíte F6.1, PR #100) existe INTACTO — a "
    "suíte nova é test_f61_visa.py; colisão de numeração resolvida por "
    "nome distinto, nenhum arquivo existente sobrescrito",
    f61_old.exists()
    and "top5" in f61_old.read_text(encoding="utf-8").lower()
    and (ROOT / "scripts" / "test_f61_visa.py").exists(),
)


def main() -> int:
    fails = [c for c in CHECKS if not c[1]]
    print(f"\nF61_visa: {len(CHECKS) - len(fails)} OK, {len(fails)} FAIL")
    for name, _, detail in fails:
        print(f"  FAIL: {name} {detail}")
    print("TUDO OK" if not fails else "HÁ FALHAS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
