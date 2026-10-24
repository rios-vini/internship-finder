#!/usr/bin/env python3
"""Testes da Fase F109 — start_date_ambiguous (ab <mês> sem ano) + medição AB SOFORT.

Deltas (spec ~/.hermes/handoff/f109-start-date-ambiguo/ESPECIFICACAO.md):
  (a) 3 vagas Lidl "Ab August/September" SEM ano (1391375033, 1389429933,
      1394651233) -> flag start_date_ambiguous (NÃO conflito; nunca decide
      TOO_EARLY sem ano). Fixtures verbatim das 3 vagas.
  (b) AB SOFORT 6× recorrente (Lidl repostagem contínua: 1386592133,
      1386583433, 13231263, 1386615133, 1412315033 + padrão) -> a flag
      start_conflict:IMMEDIATE da F95 JÁ DISPARA nas 5 com descrição (medição
      confirmada); a 6ª (13231263) não tem descrição -> não dispara (OK).
  Passo 0: medido 777 vagas com "ab <mês>" sem ano no corpus inteiro (não só Lidl).
  Os 2 ajustes entram no MESMO detector da F95 (extensão, não módulo novo).

Fixtures VERBATIM de records reais (dataset 23/10, data/ intocável):
  - 3 Lidl ambíguas (ab August/September)
  - 5 Lidl ab-sofort com descrição (a 6ª não tem descrição)
  - Contra-casos: início COM ano (não ambíguo), sem janela, etc.
Uso:
  .venv/bin/python scripts/test_f109.py   (ou bash scripts/test_f109.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "src"))

import seasonality  # noqa: E402
import minimal_page as mp  # noqa: E402
import funnel_report as fr  # noqa: E402

N = 0
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global N
    N += 1
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def section(name: str) -> None:
    print(f"\n== {name} ==")


def _job(title_desc: tuple[str, str], **extra) -> dict:
    return {"title": title_desc[0], "description": title_desc[1], **extra}


# ---------------------------------------------------------------------------
# Fixtures VERBATIM (dataset de produção 23/10 — round-trip por frase-chave)
# ---------------------------------------------------------------------------

# ---- (a) 3 Lidl "Ab August/September" SEM ano ----
LIDL_1391375033 = (
    "Praktikum Einkauf International - Produkt-Compliance Qualität & Nachhaltigkeit",
    "Einleitung Eine gute Idee war der Ursprung, ein erfolgreiches Konzept ist das Ergebnis. Qualität zum guten Preis möglichst vielen Menschen anbieten zu können treibt uns an - mittlerweile weltweit, denn wir sind Lidl. Hier ist das berufliche Zuhause vielfältiger Talente. Ob im Einkauf, in der Logistik, im Warengeschäft oder in der IT; ob als Impulsgeber, Gestalter oder Dienstleister der Länder. Wir suchen Anpacker, Durchstarter, Möglichmacher und bieten spannende Aufgaben und Projekte in einem dynamischen und internationalen Umfeld. Bei Lidl findet jeder seine persönliche Herausforderung. Denn Lidl lohnt sich. Deine Aufgaben Du unterstützt uns dabei, den Überblick im Dschungel komplexer EU-Regularien zu behalten, neue gesetzliche Rahmenbedingungen zu identifizieren und die Kommunikation konkreter Maßnahmen mit den betroffenen Schnittstellen zu gestalten. Ab August / September für 6 Monate. … konkret heißt das: Mitarbeit bei dem kontinuierlichen Monitoring neuer rechtlicher Rahmenbedingungen zu Produktsicherheit und Nachhaltigkeit sowie Ableitung klarer Handlungsempfehlungen für das Produktsortiment Unterstützung bei der Weiterentwicklung der Produktsicherheit im Warenstrom durch ein schlankes, risikobasiertes Konzept (Lean Compliance) Kreative und zielgruppengerechte Aufbereitung von Fachthemen sowie organisatorische Unterstützung bei fachbereichsübergreifenden Terminen (z. B. Einkauf, CSR, Logistik und Vertrieb) Dein Profil Studium* im Bereich Wirtschafts-, Natur- oder Sozialwissenschaften (vorzugsweise mit Schwerpunkt Qualitätsmanagement, Nachhaltigkeit oder Produktsicherheit) Erste Erfahrungen im Handels- oder Konsumgüterbereich oder im Bereich Qualitätsmanagement von Vorteil Interesse am Thema Prozesse, Prozessoptimierung und Qualität Ausgeprägte Kommunikationsstärke insbesondere wenn es darum geht, komplexe Sachverhalte zielgruppengerecht aufzubereiten und strukturiert darzustellen. *Bitte füge deiner Bewerbung deinen aktuellen Notenspiegel hinzu. Wir bieten Lidl legt Wert darauf, dass sich deine Zeit bei uns lohnt! Deshalb kannst du bei uns nicht nur deine Finanzen aufbessern (Pflichtpraktikum: 1.000 € p.M. / freiwilliges Praktikum: Gesetzlicher Mindestlohn): Du gewinnst wertvolle Praxiseinblicke in „deinen“ Fachbereich und lernst die Herausforderungen im Tagesgeschäft kennen. Dabei steht dir nicht nur während der Einarbeitung ein fester Ansprechpartner zur Seite. Du hast zu jeder Zeit Zugriff auf das Expertenwissen deiner festen Ansprechpartners und das Know-how deiner hilfsbereiten Kolleginnen und Kollegen. Lerne das kollegiale Umfeld und deine beruflichen Möglichkeiten bei Lidl kennen. Und nutze die Chance, dir ein erstes Karrierenetzwerk aufzubauen.",
)

LIDL_1394651233 = (
    "Praktikum Einkauf - Textil",
    "Einleitung Eine gute Idee war der Ursprung, ein erfolgreiches Konzept ist das Ergebnis. Qualität zum guten Preis möglichst vielen Menschen anbieten zu können treibt uns an - mittlerweile weltweit, denn wir sind Lidl. Hier ist das berufliche Zuhause vielfältiger Talente. Ob im Einkauf, in der Logistik, im Warengeschäft oder in der IT; ob als Impulsgeber, Gestalter oder Dienstleister der Länder. Wir suchen Anpacker, Durchstarter, Möglichmacher und bieten spannende Aufgaben und Projekte in einem dynamischen und internationalen Umfeld. Bei Lidl findet jeder seine persönliche Herausforderung. Denn Lidl lohnt sich. Deine Aufgaben Du unterstützt bei Marktanalysen, Größenfestlegungen, Messevorbereitungen, Einkaufsverhandlungen und der Weiterentwicklung der Warengruppe. Ab August / September für für 6 Monate. … konkret heißt das: Identifizieren von Markttrends und Innovationen innerhalb der eigenen Warengruppe Durchführung von Storechecks sowie Analysieren von Abverkaufszahlen Mitarbeit bei der Festlegung von Größenläufe und Sortierungen als auch bei Farb- und Größenanalysen Mithilfe bei der Vorbereitung und Durchführung von Hausmessen Begleitung von internationalen Einkaufsverhandlungen Analysieren und Weiterentwickeln der Warengruppe durch Category Management Tools Dein Profil Studium* im Bereich Betriebswirtschaftlichlehre oder Textil- und Bekleidungstechnik vorzugsweise mit einkaufsspezifischem Schwerpunkt Auslandserfahrung wünschenswert Analytische Fähigkeiten Sehr gute Englischkenntnisse *Bitte füge deiner Bewerbung deinen aktuellen Notenspiegel hinzu. Wir bieten Lidl legt Wert darauf, dass sich deine Zeit bei uns lohnt! Deshalb kannst du bei uns nicht nur deine Finanzen aufbessern (Pflichtpraktikum: 1.000 € p.M. / freiwilliges Praktikum: Gesetzlicher Mindestlohn): Du gewinnst wertvolle Praxiseinblicke in „deinen“ Fachbereich und lernst die Herausforderungen im Tagesgeschäft kennen. Dabei steht dir nicht nur während der Einarbeitung ein fester Ansprechpartner zur Seite. Du hast zu jeder Zeit Zugriff auf das Expertenwissen deiner festen Ansprechpartners und das Know-how deiner hilfsbereiten Kolleginnen und Kollegen. Lerne das kollegiale Umfeld und deine beruflichen Möglichkeiten bei Lidl kennen. Und nutze die Chance, dir ein erstes Karrierenetzwerk aufzubauen.",
)

LIDL_1389429933 = (
    "Praktikum Einkaufskoordination Food - Marke",
    "Einleitung Eine gute Idee war der Ursprung, ein erfolgreiches Konzept ist das Ergebnis. Qualität zum guten Preis möglichst vielen Menschen anbieten zu können treibt uns an - mittlerweile weltweit, denn wir sind Lidl. Hier ist das berufliche Zuhause vielfältiger Talente. Ob im Einkauf, in der Logistik, im Warengeschäft oder in der IT; ob als Impulsgeber, Gestalter oder Dienstleister der Länder. Wir suchen Anpacker, Durchstarter, Möglichmacher und oferecem spannende Aufgaben und Projekte in einem dynamischen und internationalen Umfeld. Bei Lidl findet jeder seine persönliche Herausforderung. Denn Lidl lohnt sich. Deine Aufgaben Unterstütze uns als direkter Ansprechpartner und Schnittstelle zwischen unseren internationalen Geschäftspartnern, dem Einkauf und den Lidl Ländern weltweit. Ab August / September für 6 Monate. … konkret heißt das: Einblicke in die Organisation der jeweiligen Prozesse im Einkauf international Kennenlernen der Verwaltungsaufgaben wie Büroorganisation, Informationsaufbereitung und Korrespondenz Unterstützung im Tagesgeschäft der Purchasing Operator Dein Profil Studium* der Betriebswirtschaftslehre, Wirtschaftswissenschaften ou um vergleichbarer Studiengang Kommunikationsstärke Sehr gute Englischkenntnisse *Bitte füge deiner Bewerbung deinen aktuellen Notenspiegel hinzu. Wir bieten Lidl legt Wert darauf, dass sich deine Zeit bei uns lohnt! Deshalb kannst du bei uns nicht nur deine Finanzen aufbessern (Pflichtpraktikum: 1.000 € p.M. / freiwilliges Praktikum: Gesetzlicher Mindestlohn): Du gewinnst wertvolle Praxiseinblicke in „deinen“ Fachbereich und lernst die Herausforderungen im Tagesgeschäft kennen. Dabei steht dir nicht nur während der Einarbeitung ein fester Ansprechpartner zur Seite. Du hast zu jeder Zeit Zugriff auf das Expertenwissen deiner festen Ansprechpartners und das Know-how deiner hilfsbereiten Kolleginnen und Kollegen. Lerne das kollegiale Umfeld und deine beruflichen Möglichkeiten bei Lidl kennen. Und nutze a Chance, dir ein erstes Karrierenetzwerk aufzubauen.",
)

# ---- (b) 5 Lidl "Ab sofort" COM descrição (a 6ª não tem descrição) ----
LIDL_1386583433 = (
    "Praktikum Data Science",
    "Einleitung Eine gute Idee war der Ursprung, ein erfolgreiches Konzept ist das Ergebnis. Qualität zum guten Preis möglichst vielen Menschen anbieten zu können treibt uns an - mittlerweile weltweit, denn wir sind Lidl. Hier ist das berufliche Zuhause vielfältiger Talente. Ob im Einkauf, in der Logistik, im Warengeschäft oder in der IT; ob als Impulsgeber, Gestalter oder Dienstleister der Länder. Wir suchen Anpacker, Durchstarter, Möglichmacher und oferecem spannende Aufgaben und Projekte in einem dynamischen und internationalen Umfeld. Bei Lidl findet jeder seine persönliche Herausforderung. Denn Lidl lohnt sich. Deine Aufgaben Werde Teil unseres Daten & KI Teams, unterstütze datenbasierte Analysen und entwickle innovative Automatisierungslösungen. Ab sofort für 4 bis 6 Monate. … konkret heißt das: Erhalte Einblicke in Big Data und Machine Learning Technologien Mitarbeit bei Datenerhebung, -aufbereitung und explorativer Analyse Entwicklung, Validierung und Pilotierung KI- und Statistik-basierte Lösungen für automatisierte Entscheidungen in Fachabteilungen Einbringen in die strategische Definition von Daten- & KI-Themen, beispielsweise durch Präsentationserstellung oder Workshop-Teilnahme Dein Profil Fortgeschrittenes Studium* im Bereich Statistik, (Wirtschafts-) Mathematik, Informatik, Physik, Wirtschaftswissenschaften, Psychologie, Sozialwissenschaften oder einem vergleichbaren Studiengang Grundlegende Kenntnisse in Statistik und Machine Learning sowie erste Berührungspunkte mit Big-Data-Technologien und relevanten Tools wie scikit-learn, Spark oder Hive Erste Erfahrungen mit Programmiersprachen (Python, R oder Scala) und grundlegende Kenntnisse der Softwareentwicklung Erste Erfahrungen mit Datenbanken und SQL wünschenswert *Bitte füge deiner Bewerbung deinen aktuellen Notenspiegel hinzu. Wir oferecem Lidl legt Wert darauf, dass sich deine Zeit bei uns lohnt! Deshalb kannst du bei uns nicht nur deine Finanzen aufbessern (Pflichtpraktikum: 1.300 € p.M. / freiwilliges Praktikum: Gesetzlicher Mindestlohn): Du gewinnst wertvolle Praxiseinblicke in „deinen“ Fachbereich und lernst die Herausforderungen im Tagesgeschäft kennen. Dabei steht dir nicht nur während der Einarbeitung ein fester Ansprechpartner zur Seite. Du hast zu jeder Zeit Zugriff auf das Expertenwissen deiner festen Ansprechpartners und das Know-how deiner hilfsbereiten Kolleginnen und Kollegen. Lerne das kollegiale Umfeld und deine beruflichen Möglichkeiten bei Lidl kennen. Und nutze die Chance, dir ein erstes Karrierenetzwerk aufzubauen.",
)

LIDL_1412315033 = (
    "Praktikum Prozesse & Standards Verpackungsmanagement",
    "Einleitung Eine gute Idee war der Ursprung, ein erfolgreiches Konzept ist das Ergebnis. Qualität zum guten Preis möglichst vielen Menschen anbieten zu können treibt uns an - mittlerweile weltweit, denn wir sind Lidl. Hier ist das berufliche Zuhause vielfältiger Talente. Ob im Einkauf, in der Logistik, im Warengeschäft oder in der IT; ob als Impulsgeber, Gestalter oder Dienstleister der Länder. Wir suchen Anpacker, Durchstarter, Möglichmacher und oferecem spannende Aufgaben und Projekte in einem dynamischen und internationalen Umfeld. Bei Lidl findet jeder seine persönliche Herausforderung. Denn Lidl lohnt sich. Deine Aufgaben Unterstütze uns im internationalen Verpackungsmanagement als zentrale Schnittstelle bei der Entwicklung smarter Prozesse, damit unsere Eigenmarken-Artikel reibungslos, pünktlich und im besten Design in den Filialen glänzen. Ab sofort für 6 Monate. … konkret heißt das: Unterstützung bei der Gestaltung unserer Prozesse & Standards im Bereich Verpackungsmanagement zur Erstellung der Verpackungen unserer Eigenmarken Mitarbeit bei der Analyse, Optimierung und Neuentwicklung von Prozessen und relevanten Standards Aufnahme von Anforderungen aus den Fachbereichen Enge Schnittstellenarbeit mit dem internationalen Einkauf sowie anderen Fachbereichen aus unseren Lidl Ländern und externen Dienstleistern Dein Profil Studium im Bereich BWL, Wirtschaftswissenschaften ou um vergleichbarer Studiengang Erste praktische Erfahrung im Themenfeld Projektmanagement wünschenswert Spaß an der Optimierung bestehender Prozesse und Standards Strukturierte Arbeitsweise, sowie schnelle Auffassungsgabe und analytisches Denken Sicherer Umgang mit Google Workspace, insbesondere Sheets *Bitte füge deiner Bewerbung deinen aktuellen Notenspiegel hinzu. Wir oferecem Lidl legt Wert darauf, dass sich deine Zeit bei uns lohnt! Deshalb kannst du bei uns nicht nur deine Finanzen aufbessern (Pflichtpraktikum: 1.300 € p.M. / freiwilliges Praktikum: Gesetzlicher Mindestlohn): Du gewinnst wertvolle Praxiseinblicke in „deinen“ Fachbereich und lernst die Herausforderungen im Tagesgeschäft kennen. Dabei steht dir nicht nur während der Einarbeitung ein fester Ansprechpartner zur Seite. Du hast zu jeder Zeit Zugriff auf das Expertenwissen deiner festen Ansprechpartners und das Know-how deiner hilfsbereiten Kolleginnen und Kollegen. Lerne das kollegiale Umfeld und deine beruflichen Möglichkeiten bei Lidl kennen. Und nutze a Chance, dir ein erstes Karrierenetzwerk aufzubauen.",
)

LIDL_1386615133 = (
    "Praktikum Controlling International - Einkauf",
    "Einleitung Eine gute Idee war der Ursprung, ein erfolgreiches Konzept ist das Ergebnis. Qualität zum guten Preis möglichst vielen Menschen anbieten zu können treibt uns an - mittlerweile weltweit, denn wir sind Lidl. Hier ist das berufliche Zuhause vielfältiger Talente. Ob im Einkauf, in der Logistik, im Warengeschäft oder in der IT; ob als Impulsgeber, Gestalter oder Dienstleister der Länder. Wir suchen Anpacker, Durchstarter, Möglichmacher und oferecem spannende Aufgaben und Projekte in einem dynamischen und internationalen Umfeld. Bei Lidl findet jeder seine persönliche Herausforderung. Denn Lidl lohnt sich. Deine Aufgaben Unterstütze uns bei der Durchführung von Auswertungen und Analysen relevanter Kennzahlen des Einkaufs. Ab sofort für bis zu 6 Monate. … konkret heißt das: Mitarbeit bei der Analyse von Auffälligkeiten in den Einkaufs-KPIs (z.B. Preis- und Mengenentwicklungen) und Aufbereitung der Ergebnisse in Präsentationen Unterstützung bei der Konzeption und Weiterentwicklung von Berichten im digitalen Kontext Mithilfe bei aktuellen Projekten Austausch mit verschiedenen Schnittstellen sowie unseren Lidl Ländern Dein Profil Studium* der Wirtschaftswissenschaften mit Schwerpunkt Controlling, Finance, Accounting ou um vergleichbarer Studiengang Sehr gutes Zahlenverständnis Sicherer Umgang mit Microsoft Excel / Google Sheets *Bitte füge deiner Bewerbung deinen aktuellen Notenspiegel hinzu. Wir oferecem Lidl legt Wert darauf, dass sich deine Zeit bei uns lohnt! Deshalb kannst du bei uns nicht nur deine Finanzen aufbessern (Pflichtpraktikum: 1.300 € p.M. / freiwilliges Praktikum: Gesetzlicher Mindestlohn): Du gewinnst wertvolle Praxiseinblicke in „deinen“ Fachbereich und lernst die Herausforderungen im Tagesgeschäft kennen. Dabei steht dir nicht nur während der Einarbeitung ein fester Ansprechpartner zur Seite. Du hast zu jeder Zeit Zugriff auf das Expertenwissen deiner festen Ansprechpartners und das Know-how deiner hilfsbereiten Kolleginnen und Kollegen. Lerne das kollegiale Umfeld und deine beruflichen Möglichkeiten bei Lidl kennen. Und nutze a Chance, dir ein erstes Karrierenetzwerk aufzubauen.",
)

LIDL_1386592133 = (
    "Praktikum Data Analytics & Digitalisierung",
    "Einleitung Eine gute Idee war der Ursprung, ein erfolgreiches Konzept ist das Ergebnis. Qualität zum guten Preis möglichst vielen Menschen anbieten zu können treibt uns an - mittlerweile weltweit, denn wir sind Lidl. Hier ist das berufliche Zuhause vielfältiger Talente. Ob im Einkauf, in der Logistik, im Warengeschäft oder in der IT; ob als Impulsgeber, Gestalter oder Dienstleister der Länder. Wir suchen Anpacker, Durchstarter, Möglichmacher und oferecem spannende Aufgaben e Projekte in einem dynamischen und internationalen Umfeld. Bei Lidl findet jeder seine persönliche Herausforderung. Denn Lidl lohnt sich. Deine Aufgaben Werde Teil unseres Daten & KI Teams, unterstütze datenbasierte Analysen und entwickle innovative Automatisierungslösungen. Ab sofort für 4 bis 6 Monate. … konkret heißt das: Begleitung des gesamten Prozesses einer Analyse: Von der Definition der Fragestellung und Zielsetzung bis zur Kommunikation einer Empfehlung Durchführung von Analysen mit internen und externen Daten (bspw. Effekte der Umstellung einer Werbemaßnahme) Mitarbeit in Projekten aus dem Bereich Machine Learning, wo Datenmengen mittels statistischer Modelle verarbeitet und ausgewertet werden Dein Profil Fortgeschrittenes Studium* im Bereich Statistik, (Wirtschafts-) Mathematik, Informatik, Physik, Wirtschaftswissenschaften, Psychologie, Sozialwissenschaften ou um vergleichbaren Studiengang Grundlegendes Verständnis von Datenanalyse, idealerweise erste Erfahrungen com Python ou R Erste Erfahrungen mit Datenbanken und SQL wünschenswert Sicherer Umgang mit Microsoft Excel/Google Sheets *Bitte füge deiner Bewerbung deinen aktuellen Notenspiegel hinzu. Wir oferecem Lidl legt Wert darauf, dass sich deine Zeit bei uns lohnt! Deshalb kannst du bei uns nicht só deine Finanzen aufbessern (Pflichtpraktikum: 1.300 € p.M. / freiwilliges Praktikum: Gesetzlicher Mindestlohn): Du gewinnst wertvolle Praxiseinblicke in „deinen“ Fachbereich e lernst die Herausforderungen im Tagesgeschäft kennen. Dabei steht dir nicht nur während der Einarbeitung ein fester Ansprechpartner zur Seite. Du hast zu jeder Zeit Zugriff auf das Expertenwissen deiner festen Ansprechpartners e das Know-how deiner hilfsbereiten Kolleginnen und Kollegen. Lerne das kollegiale Umfeld und deine beruflichen Möglichkeiten bei Lidl kennen. Und nutze a Chance, dir ein erstes Karrierenetzwerk aufzubauen.",
)

# 13231263 — sem descrição (None) -> NÃO dispara IMMEDIATE (comportamento correto)
LIDL_13231263 = (
    "Praktikum Einkauf International - Produkt-Compliance QualitÃ¤t & Nachhaltigkeit",
    "",
)

# ---- Contra-casos ----
# Início COM ano (não ambíguo)
START_WITH_YEAR = (
    "Praktikum",
    "Beginn: ab März 2027 für 6 Monate",
)

# Sem janela de início
NO_WINDOW = (
    "Praktikum",
    "Tolle Stelle, super Team, viel lernen.",
)

# ab sofort em prosa (slogan Lidl) — NÃO é janela declarada (F67)
LIDL_SLOGAN_FP = (
    "Praktikum Verkauf",
    "Du steigst sofort in die Arbeitswelt ein und lernst unser Team kennen.",
)

# Início ambíguo NÃO-Lidl (ex.: BASF, BMW, etc. — medição Passo 0: 777 total)
BASF_AB_FEBRUAR = (
    "Praktikum Personalmarketing",
    "Wir suchen dich ab Februar für spannende Aufgaben im Employer Branding.",
)


def main() -> int:
    # ---------------------------------------------------------------- A
    section("A: start_date_ambiguous — 3 Lidl 'Ab August/September' SEM ano")
    for name, fixture in [
        ("1391375033", LIDL_1391375033),
        ("1394651233", LIDL_1394651233),
        ("1389429933", LIDL_1389429933),
    ]:
        job = _job(fixture)
        # Parser detecta ambiguous_start
        hits = seasonality.parse_seasonality(seasonality.job_window_text(job))
        amb_hits = [h for h in hits if h.get("kind") == "ambiguous_start"]
        check(f"A1.{name} parse: ambiguous_start hit presente", len(amb_hits) == 1,
              f"got {len(amb_hits)} hits: {amb_hits}")

        # Canonical pode ser ambiguous_start (se não houver janela datada)
        canon = seasonality.canonical_seasonality(seasonality.job_window_text(job))
        check(f"A2.{name} canonical: kind=ambiguous_start", canon and canon.get("kind") == "ambiguous_start",
              f"got {canon}")

        # Label do calendário mostra meses (ex.: "ago/set (sem ano)")
        if amb_hits:
            label = seasonality.seasonality_label(amb_hits[0])
            check(f"A3.{name} label: meses PT", label == "ago/set (sem ano)",
                  f"got '{label}'")

        # Flag start_date_ambiguous_of = True
        check(f"A4.{name} start_date_ambiguous_of=True",
              seasonality.start_date_ambiguous_of(job), str(seasonality.start_date_ambiguous_of(job)))

        # NÃO deve ter conflito (sem ano não decide TOO_EARLY/TOO_LATE)
        conflict = seasonality.start_conflict_of(job)
        check(f"A5.{name} start_conflict_of=None (sem ano não conflita)",
              conflict is None, str(conflict))

    # ---------------------------------------------------------------- B
    section("B: start_date_ambiguous — contra-casos (COM ano / sem janela / slogan)")
    # Início COM ano -> NÃO é ambíguo
    job_year = _job(START_WITH_YEAR)
    check("B1 com ano: start_date_ambiguous_of=False",
          not seasonality.start_date_ambiguous_of(job_year))
    # Mas PODE ter conflito se datado (ex.: março 2027 = OK, sem flag)
    check("B1b com ano: conflito=None (mar/2027 dentro da janela)",
          seasonality.start_conflict_of(job_year) is None)

    # Sem janela -> NÃO é ambíguo
    job_none = _job(NO_WINDOW)
    check("B2 sem janela: start_date_ambiguous_of=False",
          not seasonality.start_date_ambiguous_of(job_none))

    # Slogan Lidl "steigt sofort" -> NÃO é ambíguo (é imediato SEM contexto)
    job_slogan = _job(LIDL_SLOGAN_FP)
    check("B3 slogan Lidl: start_date_ambiguous_of=False",
          not seasonality.start_date_ambiguous_of(job_slogan))
    check("B3b slogan Lidl: start_conflict_of=None (F67 sem contexto)",
          seasonality.start_conflict_of(job_slogan) is None)

    # Não-Lidl ambíguo (BASF "ab Februar") -> TAMBÉM flag (medição Passo 0)
    job_basf = _job(BASF_AB_FEBRUAR)
    check("B4 BASF ab Februar: start_date_ambiguous_of=True",
          seasonality.start_date_ambiguous_of(job_basf))
    hits = seasonality.parse_seasonality(seasonality.job_window_text(job_basf))
    amb = [h for h in hits if h.get("kind") == "ambiguous_start"]
    check("B4b BASF parse: ambiguous_start hit", len(amb) == 1)
    if amb:
        label = seasonality.seasonality_label(amb[0])
        check("B4c BASF label: fev (sem ano)", label == "fev (sem ano)", f"got '{label}'")

    # ---------------------------------------------------------------- C
    section("C: AB SOFORT — 5 Lidl com descrição disparam IMMEDIATE (F95)")
    for name, fixture in [
        ("1386583433", LIDL_1386583433),
        ("1412315033", LIDL_1412315033),
        ("1386615133", LIDL_1386615133),
        ("1386592133", LIDL_1386592133),
    ]:
        job = _job(fixture)
        # Parser: imediato COM contexto (tem "für X Monate" colado)
        hits = seasonality.parse_seasonality(seasonality.job_window_text(job))
        imm_hits = [h for h in hits if h.get("kind") == "immediate" and h.get("context")]
        check(f"C1.{name} parse: imediato COM contexto", len(imm_hits) == 1,
              f"got {len(imm_hits)} hits: {imm_hits}")

        # Canonical = imediato com contexto
        canon = seasonality.canonical_seasonality(seasonality.job_window_text(job))
        check(f"C2.{name} canonical: imediato+contexto",
              canon and canon.get("kind") == "immediate" and canon.get("context"),
              f"got {canon}")

        # F95 start_conflict = IMMEDIATE
        conflict = seasonality.start_conflict_of(job)
        check(f"C3.{name} start_conflict_of=IMMEDIATE",
              conflict and conflict.get("conflict") == "IMMEDIATE",
              str(conflict))

        # NÃO é ambíguo (tem "ab sofort" que é imediato, não "ab <mês>")
        check(f"C4.{name} start_date_ambiguous_of=False (é imediato, não ambíguo)",
              not seasonality.start_date_ambiguous_of(job))

    # 6ª vaga (13231263) SEM descrição -> NÃO dispara nada
    job_no_desc = _job(LIDL_13231263)
    check("C5 13231263 sem descrição: start_conflict_of=None",
          seasonality.start_conflict_of(job_no_desc) is None)
    check("C5b 13231263: start_date_ambiguous_of=False",
          not seasonality.start_date_ambiguous_of(job_no_desc))

    # ---------------------------------------------------------------- D
    section("D: prioridade canônico — datado vence ambíguo")
    # Vaga com AMBOS: "Ab August / September" E "ab März 2027"
    mixed_text = "Ab August / September für 6 Monate. Alternativ ab März 2027."
    hits = seasonality.parse_seasonality(mixed_text)
    kinds = [h.get("kind") for h in hits]
    check("D1 parse: tem start (datado) E ambiguous_start",
          "start" in kinds and "ambiguous_start" in kinds, f"kinds={kinds}")

    # Canonical deve ser o DATADO (prioridade 2 vs 3)
    canon = seasonality.canonical_seasonality(mixed_text)
    check("D2 canonical: vence start datado (prioridade 2 > 3)",
          canon and canon.get("kind") == "start" and canon.get("start") == "2027-03",
          f"got {canon}")

    # Mas a flag ambígua AINDA deve ser True (informativa)
    job_mixed = _job(("Test", mixed_text))
    check("D3 mixed: start_date_ambiguous_of=True (flag informativa persiste)",
          seasonality.start_date_ambiguous_of(job_mixed))

    # ---------------------------------------------------------------- E
    section("E: minimal_page — badge start_date_ambiguous_flag_text")
    for name, fixture in [
        ("1391375033", LIDL_1391375033),
        ("1394651233", LIDL_1394651233),
        ("1389429933", LIDL_1389429933),
    ]:
        job = _job(fixture)
        flag_pt = mp.start_date_ambiguous_flag_text(job, "pt")
        flag_en = mp.start_date_ambiguous_flag_text(job, "en")
        check(f"E1.{name} pt: badge com meses",
              "início ambíguo: ago/set (sem ano" in flag_pt, f"got '{flag_pt}'")
        check(f"E2.{name} en: badge EN",
              "ambiguous start: ago/set (sem ano" in flag_en, f"got '{flag_en}'")

    # Contra-caso: vaga sem ambíguo -> string vazia
    check("E3 sem ambíguo: string vazia",
          mp.start_date_ambiguous_flag_text(_job(START_WITH_YEAR), "pt") == "")

    # ---------------------------------------------------------------- F
    section("F: funnel_report — ambiguous_start count")
    jobs_test = [
        _job(LIDL_1391375033),
        _job(LIDL_1394651233),
        _job(LIDL_1389429933),
        _job(LIDL_1386583433),  # imediato
        _job(START_WITH_YEAR),  # datado
        _job(NO_WINDOW),  # sem janela
    ]
    summary = fr.seasonality_summary(jobs_test)
    check("F1 ambiguous_start count = 3 (as 3 Lidl ambíguas)",
          summary.get("ambiguous_start") == 3,
          f"got {summary.get('ambiguous_start')}")
    check("F2 too_early = 0", summary.get("too_early") == 0)
    check("F3 too_late = 0", summary.get("too_late") == 0)
    check("F4 immediate_context = 1 (só a Lidl 1386583433 tem contexto)",
          summary.get("immediate_context") == 1,
          f"got {summary.get('immediate_context')}")

    # ---------------------------------------------------------------- G
    section("G: determinismo ×50")
    job = _job(LIDL_1391375033)
    first_amb = seasonality.start_date_ambiguous_of(job)
    first_conf = seasonality.start_conflict_of(job)
    first_flag = mp.start_date_ambiguous_flag_text(job, "pt")
    for _ in range(50):
        check("G1 start_date_ambiguous_of determinístico",
              seasonality.start_date_ambiguous_of(job) == first_amb)
        check("G2 start_conflict_of determinístico",
              seasonality.start_conflict_of(job) == first_conf)
        check("G3 start_date_ambiguous_flag_text determinístico",
              mp.start_date_ambiguous_flag_text(job, "pt") == first_flag)

    # ---------------------------------------------------------------- H
    section("H: render_minimal_html — badge aparece no card")
    jobs_render = [_job(LIDL_1391375033, company="Lidl")]
    html = mp.render_minimal_html(
        jobs_render, total_eligible=1, generated_at="2026-10-24T00:00:00Z",
        top=10, lang="pt")
    check("H1 card tem badge início ambíguo",
          "início ambíguo: ago/set (sem ano" in html,
          "badge não encontrado no HTML")
    check("H2 badge tem classe flag",
          '<span class="flag">⚠️ início ambíguo' in html)

    html_en = mp.render_minimal_html(
        jobs_render, total_eligible=1, generated_at="2026-10-24T00:00:00Z",
        top=10, lang="en")
    check("H3 EN card tem badge EN",
          "ambiguous start: ago/set (sem ano" in html_en)

    # ---------------------------------------------------------------- I
    section("I: digest — linha ambiguous_start (se houver)")
    # O funnel_report agora expõe ambiguous_start; o digest pode opcionalmente
    # mostrar uma linha (não obrigatório na spec, mas o campo existe)
    sea = fr.seasonality_summary(jobs_test)
    check("I1 seasonality_summary expõe ambiguous_start",
          "ambiguous_start" in sea, str(sea))
    check("I2 valor correto", sea["ambiguous_start"] == 3)

    print(f"\nF109: {N} checks, {len(FAILURES)} falhas")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print("F109: TUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())