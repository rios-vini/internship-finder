#!/usr/bin/env python3
"""test_f62 — Badge/warning 'ab sofort ↔ jan/2027' (display-only).

F62 (registro de desfechos 10/2026): Lidl SAP BI 'Ab sofort für 6 Monate'
(ficou PENDENTE — conflito com jan/2027) e MAHLE 'ab sofort' (eliminada
em conjunto com o bloqueio de visto §16e). O parser da F45 JÁ extrai o
sinal (kind=immediate; 'ab sofort: 37' no calendário 📆 do run 17/10) —
a F62 adiciona o SINAL DE CONFLITO com a meta do dono (início jan/2027),
sem tocar em score/ranking/filtro (regra never-worsens).

Divergências spec × código vivo (o código é a verdade — lição F11/F9):
- a spec fala em 'kind=start'; no seasonality.py da F45 o início imediato
  é kind='immediate' (start = 'ab <mês-ano>'). O badge consome kind=immediate.
- attr do toggle: o padrão enrollment (F46) perde o ⚠️ no swap EN→pt; o
  badge F62 carrega o emoji no data-i18n-pt — o toggle reproduz o badge
  pt nativo byte a byte (melhoria consciente, travada em C2).

Medição real (run 17/10 — relatório da fase, MEDIÇÃO ANTES do desenho):
37 canônicos 'ab sofort' = 26 janelas declaradas de verdade ('Ab sofort
für 6 Monate', 'Beginn: ab sofort', 'START IMMEDIATELY…') + 11
falsos-positivos em prosa (7× Lidl 'steigt sofort in die Arbeitswelt
ein', 2× rodapé anti-fraude Medtronic 'contact us immediately', 1× boas
'you can join us immediately', 1× OLAM 'immediately after production').
Amazon: 0/37 — as 48 vagas do template dizem 'jederzeit von Januar bis
Juli 2027 anfangen' e canonizam jan–jul/2027 (range > imediato). O badge
permanece determinístico (fonte única F45); apertar o parser é decisão
da F45, NÃO desta fase.

Fixtures VERBATIM (sem invenção): Lidl SAP BI / Liebherr / Amazon do
archive 20261018T090001Z (run 17/10 — os '37' do digest F45); MAHLE
copiado de test_f61_visa.py (mesma proveniência de archive).

100% OFFLINE (nenhum socket; data/ intocável — fixtures em memória).
Exit 0/1 (padrão da casa: rc + zero '[FAIL]').
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
for _p in (str(SCRIPTS), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import funnel_report as fr  # noqa: E402
import minimal_page as mp  # noqa: E402
import ranking_digest as rg  # noqa: E402
import seasonality  # noqa: E402

STAMP = "2026-10-19T09:20:00Z"
_AB_BASELINE_SHA = "047ac98"  # main pré-F62 (SHA congelado — lição PR #145)

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def _job(jid: str, title: str, company: str, desc: str,
         loc: str = "Berlin, DE", score: float = 10.0,
         url: str = "https://example.com/j") -> dict:
    return {"id": jid, "title": title, "company": company,
            "location": loc, "description": desc, "url": url,
            "score": score, "posted_at": "2026-10-18", "raw": {}}


# Lidl Stiftung (tenant lidlstiftup2) — A VAGA DA CARD: ficou
# PENDENTE no registro de desfechos por conflitar com jan/2027
# ("Ab sofort für 6 Monate"). Id real:
# lidlstiftup2|sf_dataset:successfactors:1436050633, Neckarsulm.
F_LIDL_TITLE = (
    'Praktikum Controlling International - SAP BI Reporting'
)
F_LIDL_DESC = (
    'Einleitung Eine gute Idee war der Ursprung, ein erfolgreiches Konzept ist das Ergebnis. '
    'Qualität zum guten Preis möglichst vielen Menschen anbieten zu können treibt uns an - mi'
    'ttlerweile weltweit, denn wir sind Lidl. Hier ist das berufliche Zuhause vielfältiger Ta'
    'lente. Ob im Einkauf, in der Logistik, im Warengeschäft oder in der IT; ob als Impulsgeb'
    'er, Gestalter oder Dienstleister der Länder. Wir suchen Anpacker, Durchstarter, Möglichm'
    'acher und bieten spannende Aufgaben und Projekte in einem dynamischen und internationale'
    'n Umfeld. Bei Lidl findet jeder seine persönliche Herausforderung. Denn Lidl lohnt sich.'
    ' Deine Aufgaben Unterstütze uns bei der Digitalisierung und Weiterentwicklung des Report'
    'ings mit SAP und der SAP Analytics Cloud. Ab sofort für 6 Monate. … konkret heißt das: M'
    'itarbeit im Anforderungsprozess rund um die Aufnahme und den Rollout fachlicher Anforder'
    'ungen an unsere BI-Systeme Systemseitige Sicherstellung der Reporting-Qualität Austausch'
    ' mit Schnittstellen in den operativen und technischen Fachbereichen (IT) sowie in den La'
    'ndesgesellschaften Unterstützung bei der Vorbereitung und Durchführung von Schulungen zu'
    ' unseren SAP Berichten und Produkten Dein Profil Studium* im Bereich Wirtschaftswissensc'
    'haften oder ein vergleichbarer Studiengang Idealerweise Interesse an IT Themen sowie ers'
    'te praktische Erfahrungen mit SAP/SAC Sehr guter Umgang mit Google Sheets *Bitte füge de'
    'iner Bewerbung deinen aktuellen Notenspiegel hinzu. Wir bieten Lidl legt Wert darauf, da'
    'ss sich deine Zeit bei uns lohnt! Deshalb kannst du bei uns nicht nur deine Finanzen auf'
    'bessern (Pflichtpraktikum: 1.300 € p.M. / freiwilliges Praktikum: Gesetzlicher Mindestlo'
    'hn): Du gewinnst wertvolle Praxiseinblicke in „deinen“ Fachbereich und lernst die Heraus'
    'forderungen im Tagesgeschäft kennen. Dabei steht dir nicht nur während der Einarbeitung '
    'ein fester Ansprechpartner zur Seite. Du hast zu jeder Zeit Zugriff auf das Expertenwiss'
    'en deines festen Ansprechpartners und das Know-how deiner hilfsbereiten Kolleginnen und '
    'Kollegen. Lerne das kollegiale Umfeld und deine beruflichen Möglichkeiten bei Lidl kenne'
    'n. Und nutze die Chance, dir ein erstes Karrierenetzwerk aufzubauen.'
)

# MAHLE Lead-Buying DE — verbatim do test_f61_visa.py (mesma
# proveniência: archive 20261018T090001Z jobs.json); a vaga
# "ab sofort" eliminada em conjunto com o bloqueio de visto §16e.
F_MAHLE_TITLE = (
    'Praktikum Lead-Buying Mechatronics (m/w/d)'
)
F_MAHLE_DESC = (
    'Zeitraum ab sofort für einen Zeitraum von 6 Monaten Tätigkeiten Mitwirken bei der Transf'
    'ormation der Kaufteil-Strategien im Hinblick auf Mechatronik an der Seite unserer strate'
    'gischen Einkäufer im engen Austausch mit der Produktentwicklung und externen Partnern Un'
    'terstützung bei der Vor- und Nachbereitung von Rahmenvertrags- und Preisverhandlungen, e'
    'xternen Meetings sowie Abteilungs- und Projektteamsitzungen zur Sicherung der Unternehme'
    'nsinteressen bezüglich Mensch, Umwelt, Technik und Kosten Bearbeitung spannender Projekt'
    'e im internationalen Kontext (Planung von Lieferantentage im Haus MAHLE, Markt- und Port'
    'folioanalysen von Unternehmenspartnern und potenziellen Lieferanten, Benchmark-Analysen,'
    ' etc.) Erstellung von einkaufsspezifischen Analysen und Kennzahlen-Reports mithilfe der '
    'Einkaufstools, SAP und MS Excel Organisation von Team-Events Voraussetzungen Immatrikula'
    'tion im Studiengang Betriebswirtschaftslehre, Maschinenbau oder einem ähnlichen Studieng'
    'ang Analytisches Denkvermögen und selbstständige Arbeitsweise Gute MS-Office Kenntnisse,'
    ' insbesondere Excel und PowerPoint Gute Englischkenntnisse Engagement und Teamfähigkeit '
    'Bewerbungsunterlagen Vollständiger Lebenslauf Motivationsschreiben Immatrikulationsbesch'
    'einigung Zeugnisse, v. a. aktueller Notenspiegel Bei Pflichtpraktika: Praktikumsrichtlin'
    'ien der Universität bzw. Hochschule aus der die Mindestdauer hervorgeht Für Nicht-EU-Bür'
    'ger: gültiger Aufenthaltstitel erforderlich Benefits Attraktive Vergütung 35-Stunden-Woc'
    'he mit flexiblen Arbeitszeiten Bezahlte Urlaubstage Vergünstigtes Mittagessen im Betrieb'
    'srestaurant Kostenfreie Parkmöglichkeiten Urbanes Umfeld mit guter Verkehrsanbindung Ind'
    'ividuelle Betreuung im Fachbereich Begleitende Aktivitäten und Studierendennetzwerk Habe'
    'n Sie Fragen? +49 711 501-47574'
)

# Liebherr-International S.A. — CONTRA-CASO prioridade: o texto
# TEM "ab sofort", mas "oder für das Sommersemester 2027" vence
# no canônico (semestre > imediato, F45) -> badge AUSENTE,
# janela futura positiva. Id: ...|successfactors:LiMySLive:1433348733.
F_LIEBHERR_TITLE = (
    'Praktikant/Werkstudent im Bereich Projektmanagement Logistik (m/w/d)'
)
F_LIEBHERR_DESC = (
    'Zur Unterstützung unserer Abteilung Logistik suchen wir ab sofort oder für das Sommersem'
    'ester 2027 dich für ein Praktikum oder eine Werkstudentenstelle. Faszinierendes schaffen'
    ': deine Aufgaben Erstellen von Prozessanweisungen/-dokumentationen im Bereich Logistik. '
    'Unterstützung unserer Projektleiter bei der Planung, Organisation und Umsetzung von Logi'
    'stikprojekten Analyse bestehender Prozesse sowie Erarbeitung von Optimierungsvorschlägen'
    ' zur Steigerung von Effizienz und Transparenz Aufbereitung von Projektinformationen, Ken'
    'nzahlen und Präsentationen für interne Abstimmungen und Workshops Eigenständige Übernahm'
    'e kleinerer Projekte und Entwicklung neuer Ideen zur Unterstützung unseres Teams und uns'
    'erer Prozesse Erstellung von Schulungs- und Kommunikationsunterlagen für neue oder geänd'
    'erte Prozesse Stärken einbringen: deine Qualifikationen Studium an einer Hochschule oder'
    ' Universität in der Fachrichtung BWL, Wirtschaftsingenieurswesen, Projektmanagement oder'
    ' vergleichbaren Studiengängen Begeisterung für die Umsetzung von Projekten &amp; Optimie'
    'rung von Prozessen Dynamische und motivierte Einstellung &amp; Lust auf Neues Strukturie'
    'rte, zielorientierte und selbständige Arbeitsweise Ausgeprägte Team- &amp; Kommunikation'
    'sfähigkeit Entschlossenheit, etwas zu bewegen Sehr gute Deutschkentnisse Unser Angebot A'
    'nspruchsvolle Aufgaben in einer international erfolgreichen Firmengruppe Spannendes Arbe'
    'itsumfeld und moderne Ausstattung Mitarbeit an faszinierenden Produkten und Projekten Gu'
    'te Einarbeitung und persönliche Betreuung Bereitstellung einer Praktikantenwohnung durch'
    ' Liebherr möglich Teil eines großen Studierendennetzwerks durch regelmäßige übergreifend'
    'e Studierendenevents Faire, angemessene Vergütung Angenehmes Arbeitsklima, ein hilfsbere'
    'ites Team sowie kollegiales Miteinander Bitte lasse uns mit deiner Bewerbung eine gültig'
    'e Immatrikulationsbescheinigung, einen Nachweis deiner aktuellen Studienleistungen sowie'
    ' die aktuelle Prüfungs- und Studienordnung zukommen, in der die Praktikumsdauer (Präsenz'
    'tage) geregelt ist. Haben wir Ihr Interesse geweckt? Dann freuen wir uns über Ihre Onlin'
    'e-Bewerbung. Bei Fragen kontaktieren Sie bitte Julia Häußler. One Passion. Many Opportun'
    'ities. Das Unternehmen \u200b Die Liebherr-Werk Ehingen GmbH zählt zu den weltweit führenden '
    'Herstellern von Fahrzeugkranen. Das Produktprogramm umfasst Teleskop- und Gittermastkran'
    'e auf Mobil- und Raupenfahrwerken mit Traglasten von 35 bis 3.000 Tonnen.\u200b Standort Lieb'
    'herr-Werk Ehingen GmbH Dr.-Hans-Liebherr-Str. 1 89584 Ehingen/Donau Deutschland (DE) Kon'
    'takt Julia Häußler julia.haeussler@liebherr.com'
)

# Amazon Logistik (A33) — CONTRA-CASO template: janela futura
# explícita ("jederzeit von Januar bis Juli 2027 anfangen"),
# ZERO "sofort" no texto; as 48 vagas Amazon canonizam
# jan–jul/2027 e NÃO ganham badge (medição F62: 0/48).
# Id: Amazon Logistik GmbH - A33|amazon_jobs:10491482.
F_AMAZON_TITLE = (
    'Praktikum im Bereich Logistik - Bad Hersfeld - Start 2027'
)
F_AMAZON_DESC = (
    'Du bewirbst dich auf unseren Talent Pool für Logistikpraktika mit Start ab Januar 2027. '
    'Durch eine frühzeitige Bewerbung profitierst du von:\n\n* Frühzeitiger Berücksichtigung fü'
    'r verfügbare Positionen\n* Bevorzugtem Zugang zu gewünschten Standorten und Startdaten\n* '
    'Größerer Flexibilität bei der Terminplanung im Interviewprozess\n\nUnser vorläufiger Zeitp'
    'lan: Interviews beginnen im September, das Role Matching startet voraussichtlich im Okto'
    'ber. Dieser Zeitplan kann sich je nach geschäftlichem Bedarf ändern.\n\nBitte beachte: Wir'
    ' haben verschiedene Möglichkeiten in ganz Deutschland und benötigen Flexibilität bezügli'
    'ch der Standorte. Wenn du dich für die Stelle bewirbst, gib bitte alle deine bevorzugten'
    ' Standorte in Deutschland an.\nAlle unsere Praktika finden vollständig vor Ort statt.\nAma'
    'zon Operations ist das Rückgrat der Amazon-Kundenerfahrung. Mit über 50 Logistikzentren,'
    ' hunderten von Zustellstationen und zehntausenden von Versandmitarbeiter:innen arbeitet '
    'das Team zusammen, um Artikel effizient an Kund:innen zu liefern. In den Logistikzentren'
    ' werden jährlich Millionen von Artikeln kommissioniert und verpackt, während die Zustell'
    'teams daran arbeiten, Bestellungen pünktlich an die Kund:innen zu bringen. Sicherheit ha'
    't oberste Priorität, und die Betriebskultur ist geprägt von Teamwork, Vielfalt und einer'
    ' gemeinsamen Arbeitsethik, die das Geschäft reibungslos am Laufen hält. Das Team ist sto'
    'lz darauf, den Qualitätsservice zu liefern, für den Amazon weltweit bekannt ist.\n\nHinwei'
    's: Du musst zum Starttermin die Arbeitsberechtigung für das Beschäftigungsland haben.\n\n\n'
    'Key job responsibilities\nAls Amazon Operations-Praktikant:in hast du die Möglichkeit, de'
    'ine analytischen Fähigkeiten in wirkungsvollen Projekten anzuwenden, die die Funktionali'
    'tät und den Service von Logistikzentren, Sortierzentren und Zustellstationen verbessern.'
    ' Wichtige Aspekte der Rolle umfassen:\n• Abschluss von Projekten mit hoher Priorität nach'
    ' höchstem Standard und Nachweis deiner Fähigkeit, Ergebnisse zu liefern\n• Datenanalyse z'
    'ur Identifizierung operativer Herausforderungen und Verbesserungsmöglichkeiten\n• Vorschl'
    'agen und Testen von Lösungen in Zusammenarbeit mit dem Team zur Umsetzung der effektivst'
    'en Ansätze\n• Entwicklung von Kommunikations- und Teamfähigkeiten durch die Zusammenarbei'
    't mit Führungskräften, Stakeholdern und Versandmitarbeiter:innen.\n• Bewegung im Gebäude,'
    ' um mit verschiedenen Teams zu interagieren. Das umfasst aktives Wissenssammeln durch Te'
    'ilnahme an Aktivitäten wie Vorbesprechungen, Ablaufmeetings und Diskussionen mit dem Füh'
    'rungsteam und Versandmitarbeiter:innen.\n• Die Fähigkeit, sich im Arbeitsbereich zu orien'
    'tieren und zwischen verschiedenen Bereichen zu wechseln, ist für diese Position unerläss'
    'lich.\n• Flexibilität bei verschiedenen Arbeitszeiten und Schichtmustern nach Bedarf zeig'
    'en.\n• Möglicher Umzug an den vorgesehenen Arbeitsort.\n\n\nA day in the life\nUnsere Praktik'
    'a sind Bildungsmöglichkeiten, die es dir als unserer zukünftigen Führungskraft ermöglich'
    'en, zu entdecken, wie wir unsere Teams von Versandmitarbeiter:innen führen und entwickel'
    'n. Du tauchst in die schnelllebige, komplexe Welt unserer Logistikzentren, Sortierzentre'
    'n und Zustellstationen ein und erlebst, wie unsere Führungskräfte ihre Teams einsetzen, '
    'um Kundenerwartungen zu erfüllen.\nDieses Praktikum versetzt dich ins Herz unserer Abläuf'
    'e und ermöglicht es dir, den Weg einer Kundenbestellung zu verfolgen. Du erhältst einen '
    'realistischen Einblick in die Vollzeitchancen, die dich in unserem Unternehmen erwarten.'
    '\nDu lernst, wie unsere Führungskräfte eine sichere, produktive Umgebung schaffen und das'
    ' volle Potenzial ihrer Teams durch effektive Einbindung und Leistungsmanagement-Strategi'
    'en nutzen. Das ist deine Chance, Fähigkeiten zu entwickeln, die dich zu einer lohnenden '
    'Karriere bei Amazon führen werden.\n\n\nAbout the team\nPraktikant:innen-Community:\n• Als Am'
    'azon-Praktikant:in bist du Teil einer lebendigen, unterstützenden Community, die dein Wa'
    'chstum und deine Entwicklung fördert. Du arbeitest mit Praktikant:innen aus der ganzen W'
    'elt zusammen, knüpfst Kontakte und nimmst an sozialen Veranstaltungen teil, um deinen Ho'
    'rizont zu erweitern. Du kannst auch spezialisierten Gruppen beitreten, die sich auf Bere'
    'iche wie Nachhaltigkeit konzentrieren, um deine vielfältigen Interessen zu erkunden.\nUnt'
    'erstützung:\n• Das Praktikumsprogramm bietet ein robustes Unterstützungssystem, einschlie'
    'ßlich wöchentlicher Praktikant:innen-Sprechstunden, spezieller IT- und HR-Unterstützung '
    'sowie einem Programmteam, das sich deinem Erfolg verschrieben hat. Das stellt sicher, da'
    'ss du die Anleitung und Hilfe hast, die du zum Gedeihen brauchst.\nLernsessions:\n• Exklus'
    'ive Lernsessions werden deine Fähigkeiten weiter verbessern und dir Zugang zu Amazons mo'
    'dernsten Lernplattformen und der Expertise von Branchenführern gewähren. Diese strukturi'
    'erten Entwicklungsmöglichkeiten bereiten dich auf den nächsten Schritt in deiner Karrier'
    'e vor.\nMöglichkeiten:\n• Nach erfolgreichem Abschluss des Praktikums kannst du für eine A'
    'bsolvent:innen-Stelle oder ein zweites Praktikum in Betracht gezogen werden, was es dir '
    'ermöglicht, deine Reise mit Amazon fortzusetzen. Zusätzlich erhältst du ein wettbewerbsf'
    'ähiges Monatsgehalt, Umzugsunterstützung und Zugang zu einer Reihe von Mitarbeitervortei'
    'len.\nPraktikums-Starttermine über das Jahr:\n• Wir stellen Praktikant:innen ein, die jede'
    'rzeit von Januar bis Juli 2027 anfangen können. Jeden Monat führen wir 1-2 Onboarding-Ta'
    'ge für neue Mitarbeiter:innen durch.\nInternal job description'
)


# ---------------------------------------------------------------------------
# Fixtures de teste (jobs mínimos; textos VERBATIM dos literais acima)
# ---------------------------------------------------------------------------

WARN = "\u26a0\ufe0f"  # ⚠️ explícito por codepoints — imune a mojibake
LIDL = _job("lidlstiftup2|sf_dataset:successfactors:1436050633",
            F_LIDL_TITLE, "lidlstiftup2", F_LIDL_DESC,
            loc="Neckarsulm, DE", score=10.0)
MAHLE = _job("MAHLE International GmbH|sf_dataset:successfactors:1373497333",
             F_MAHLE_TITLE, "MAHLE International GmbH", F_MAHLE_DESC,
             loc="Stuttgart, DE", score=9.5)
LIEBHERR = _job("Liebherr-International S.A.|successfactors:LiMySLive:1433348733",
                F_LIEBHERR_TITLE, "Liebherr-International S.A.",
                F_LIEBHERR_DESC, loc="Ehingen, DE", score=9.0)
AMAZON = _job("Amazon Logistik GmbH - A33|amazon_jobs:10491482",
              F_AMAZON_TITLE, "Amazon Logistik GmbH - A33", F_AMAZON_DESC,
              loc="Bad Hersfeld, Hesse, DEU", score=8.5)
PLAIN = _job("beispiel|sf:1", "Praktikum Data Engineering", "Beispiel GmbH",
             "Wir suchen Studierende fuer ein Praktikum im Bereich Data.",
             score=8.0)
MINI = [LIDL, MAHLE, LIEBHERR, AMAZON, PLAIN]

PT_SPAN = f'<span class="flag">{WARN} {mp.AB_SOFORT_FLAG_TEXT}</span>'
EN_SPAN = (f'<span class="flag" data-i18n-pt="{WARN} '
           f'{mp.AB_SOFORT_FLAG_TEXT}">{WARN} '
           f'{mp.I18N["ab_sofort_flag"]["en"]}</span>')


def _render(jobs, *, full=False, lang="pt"):
    return mp.render_size_aware(
        jobs, total_eligible=len(jobs), generated_at=STAMP,
        top=(mp.PAGE_TOP_FULL if full else mp.PAGE_TOP),
        full_list=full, vitrine=True, lang=lang)


def _card_of(html, title):
    """O <li> cujo link de título contém ``title`` (identidade por título)."""
    lis = re.findall(r"<li class=\"c\".*?</li>", html, re.S)
    return next((li for li in lis if title in li), "")


# ---------------------------------------------------------------------------
# A. Flag pura — fixtures VERBATIM + contra-casos
# ---------------------------------------------------------------------------
def test_flag_pura():
    section("A: ab_sofort_flag — fonte única F45, fixtures verbatim")
    check("A1 Lidl SAP BI (a vaga da card): canônico imediato + flag pt",
          seasonality.canonical_seasonality(
              seasonality.job_window_text(LIDL)).get("kind") == "immediate"
          and mp.ab_sofort_flag(LIDL) == mp.AB_SOFORT_FLAG_TEXT)
    check("A2 MAHLE (eliminada c/ bloqueio §16e): canônico imediato + flag",
          seasonality.canonical_seasonality(
              seasonality.job_window_text(MAHLE)).get("kind") == "immediate"
          and mp.ab_sofort_flag(MAHLE) == mp.AB_SOFORT_FLAG_TEXT)
    check("A3 contra-caso Liebherr: 'ab sofort' no texto, SoSe 2027 vence",
          seasonality.canonical_seasonality(
              seasonality.job_window_text(LIEBHERR)).get("kind") == "semester"
          and seasonality.seasonality_label(
              seasonality.canonical_seasonality(
                  seasonality.job_window_text(LIEBHERR))
          ).startswith("SoSe 2027")
          and mp.ab_sofort_flag(LIEBHERR) == "")
    check("A4 contra-caso Amazon: template jan–jul/2027, zero 'sofort'",
          seasonality.seasonality_label(seasonality.canonical_seasonality(
              seasonality.job_window_text(AMAZON))) == "jan–jul/2027"
          and "sofort" not in F_AMAZON_DESC.casefold()
          and mp.ab_sofort_flag(AMAZON) == "")
    check("A5 sem janela: sem canônico, sem flag",
          seasonality.canonical_seasonality(
              seasonality.job_window_text(PLAIN)) is None
          and mp.ab_sofort_flag(PLAIN) == "")
    en_txt = mp.I18N["ab_sofort_flag"]["en"]
    check("A6 i18n (F46): paridade pt/en; pt é a constante VERBATIM",
          set(mp.I18N["ab_sofort_flag"]) == set(mp.I18N_LANGS)
          and mp.I18N["ab_sofort_flag"]["pt"] == mp.AB_SOFORT_FLAG_TEXT
          and en_txt == "immediate start — conflicts with Jan/2027"
          and mp.ab_sofort_flag(LIDL, "en") == en_txt)
    ok_rob = True
    for broken in ({}, {"title": None, "description": None},
                   {"title": "x", "description": None},
                   {"description": "ab sofort"}):
        try:
            if mp.ab_sofort_flag(broken) not in ("", mp.AB_SOFORT_FLAG_TEXT):
                ok_rob = False
        except Exception:  # noqa: BLE001 — nunca pode lançar
            ok_rob = False
    check("A7 best-effort: job vazio/None NUNCA lança (view não quebra)",
          ok_rob and mp.ab_sofort_flag({}) == "")
    check("A8 fonte única: composição título — descrição é do seasonality",
          seasonality.job_window_text({"title": "T", "description": "D"})
          == "T — D")
    imm_label = seasonality.seasonality_label(
        seasonality.canonical_seasonality("ab sofort"))
    check("A9 pino de rótulo: rg.IMMEDIATE_LABEL == rótulo do parser F45",
          rg.IMMEDIATE_LABEL == imm_label == "ab sofort",
          f"rg={rg.IMMEDIATE_LABEL!r} parser={imm_label!r}")
    summary = fr.seasonality_summary(MINI)
    cal_imm = next((c["count"] for c in summary["calendar"]
                    if c["label"] == "ab sofort"), 0)
    n_flags = sum(1 for j in MINI if mp.ab_sofort_flag(j))
    check("A10 consistência: badge e calendário 📆 contam o MESMO conjunto",
          cal_imm == n_flags == 2,
          f"calendário={cal_imm} badges={n_flags}")


# ---------------------------------------------------------------------------
# B. Card pt — badge exato, contra-casos limpos, retrocompat
# ---------------------------------------------------------------------------
def test_card_pt():
    section("B: render pt — badge nas ab sofort, NADA nas demais")
    html = _render(MINI)
    check("B1 badge pt exato, 2× (Lidl + MAHLE)", html.count(PT_SPAN) == 2,
          f"{html.count(PT_SPAN)}×")
    no_attr = re.findall(
        r'<span class="flag" [^>]*>' + re.escape(WARN)
        + r' início imediato', html)
    check("B2 render pt é PURO: badge sem attrs do toggle (contrato F46)",
          no_attr == [] and 'data-i18n-pt="' + WARN not in html)
    check("B3 contra-casos: cards Liebherr/Amazon SEM badge e SEM flag",
          "flag" not in _card_of(html, F_LIEBHERR_TITLE)
          and "flag" not in _card_of(html, F_AMAZON_TITLE)
          and "início imediato" not in _card_of(html, F_LIEBHERR_TITLE))
    check("B4 retrocompat: _card sem o param novo = sem badge (default '')",
          "flag" not in mp._card(1, PLAIN, visa=False, salary="",
                                 snippet="", apply_href=None,
                                 job_href="https://x", de_level="none",
                                 age="")
          and PT_SPAN in mp._card(1, LIDL, visa=False, salary="",
                                  snippet="", apply_href=None,
                                  job_href="https://x", de_level="none",
                                  age="", start_conflict_flag=mp.AB_SOFORT_FLAG_TEXT))
    check("B5 estrutura intocada: 5 <li>, badge DENTRO do card (não novo nó)",
          len(re.findall(r'<li class="c"', html)) == len(MINI)
          and PT_SPAN in _card_of(html, F_LIDL_TITLE)
          and PT_SPAN in _card_of(html, F_MAHLE_TITLE))


# ---------------------------------------------------------------------------
# C. Card EN — texto EN + attr pt COM o emoji (toggle byte-fiel)
# ---------------------------------------------------------------------------
def test_card_en():
    section("C: render EN — tradução + attr do toggle com ⚠️")
    html = _render(MINI, lang="en")
    check("C1 badge EN exato, 2× (texto EN + attr pt do dia)",
          html.count(EN_SPAN) == 2, f"{html.count(EN_SPAN)}×")
    attrs = re.findall(
        r'<span class="flag" data-i18n-pt="([^"]*)">'
        + re.escape(WARN) + r' immediate start', html)
    check("C2 attr carrega o ⚠️ JUNTO (toggle EN→pt reproduz o pt nativo)",
          attrs == [f"{WARN} {mp.AB_SOFORT_FLAG_TEXT}"] * 2,
          detail=str(attrs[:1]))
    check("C3 contra-casos EN: Liebherr/Amazon sem badge",
          "immediate start" not in _card_of(html, F_LIEBHERR_TITLE)
          and "immediate start" not in _card_of(html, F_AMAZON_TITLE)
          and html.count(WARN + " immediate start") == 2)


# ---------------------------------------------------------------------------
# D. Digest — linha ⚠ na seção 📅 (display-only; ausente sem imediatas)
# ---------------------------------------------------------------------------
def test_digest_line():
    section("D: linha ⚠ no digest — fonte calendário, nunca-worsens")
    report = {
        "funnel": {"run_id": "2026-10-17T09:00:02Z",
                   "applicability": {"total": 2134,
                                     "reasons": {"german_required": 1189}}},
        "trend": {"eligible_last": 871, "eligible_then": 779,
                  "window": 7, "delta": 92},
        "seasonality": {"scanned": 5, "with_window": 3,
                        # F67: campo obrigatório do sinal ⚠ (imediatos
                        # COM contexto; antes deste campo a contagem
                        # vinha do lookup por rótulo no calendar).
                        "immediate_context": 2,
                        "calendar": [{"label": "ab sofort", "count": 2},
                                     {"label": "SoSe 2027 (abr–set/2027)",
                                      "count": 1}]},
        "application": None,
    }
    lines = rg.funnel_seasonality_lines(report)
    warn = ("  ⚠ início imediato (ab sofort): 2 vagas "
            "— conflita com jan/2027")
    check("D1 linha ⚠ exata, DEPOIS da 📆 (posição travada)",
          warn in lines
          and lines.index(warn) == lines.index(
              "  📆 ab sofort: 2 · SoSe 2027 (abr–set/2027): 1") + 1)
    single = json.loads(json.dumps(report))
    single["seasonality"] = {"scanned": 2, "with_window": 2,
                             "immediate_context": 1,  # F67 (campo do ⚠)
                             "calendar": [{"label": "ab sofort", "count": 1},
                                          {"label": "mar/2027", "count": 1}]}
    check("D2 singular: 1 vaga — 'conflita' (texto honesto)",
          ("  ⚠ início imediato (ab sofort): 1 vaga "
           "— conflita com jan/2027")
          in rg.funnel_seasonality_lines(single))
    no_imm = json.loads(json.dumps(report))
    no_imm["seasonality"] = {"scanned": 5, "with_window": 1,
                             "calendar": [{"label": "SoSe 2027 (abr–set/2027)",
                                           "count": 1}]}
    no_lines = rg.funnel_seasonality_lines(no_imm)
    check("D3 never-worsens: sem imediatas -> linha AUSENTE, seção 4 linhas",
          "⚠" not in "\n".join(no_lines) and len(no_lines) == 4)
    check("D4 None/zerado: seção ausente ou sem ⚠ (degradação F45 intacta)",
          rg.funnel_seasonality_lines(None) == []
          and "⚠" not in "\n".join(rg.funnel_seasonality_lines({
              "funnel": None, "trend": None, "application": None,
              "seasonality": {"scanned": 0, "with_window": 0,
                              "calendar": []}})))
    summary = fr.seasonality_summary(MINI)
    integ = rg.funnel_seasonality_lines(
        {"funnel": None, "trend": None, "application": None,
         "seasonality": summary})
    check("D5 integração: ⚠ derivada do RESUMO REAL (mesma fonte do 📆)",
          ("  ⚠ início imediato (ab sofort): 2 vagas "
           "— conflita com jan/2027") in integ
          and integ[-2].startswith("  📆 ")
          and integ[-1].startswith("  ⚠ "),
          detail=" | ".join(integ))
    digest = ["⚡ Top 5 do dia (candidatura direta)", "  1. vaga", ""]
    digest += integ + ["", "🔗 Ranking completo: https://x"]
    check("D6 extrator do compact: ⚠ viaja DENTRO da seção 📅 (corpo)",
          rg.funnel_section_lines(digest) == integ
          and rg.funnel_section_lines(digest)[-1].startswith("  ⚠ "))


# ---------------------------------------------------------------------------
# E. A/B byte a byte vs SHA congelado (lição PR #145; CI shallow: [SKIP])
# ---------------------------------------------------------------------------


def _strip_f62(html: str) -> str:
    """Remove SOMENTE os spans do badge F62 (delta cirúrgico, padrão
    _strip_f60 da F60): qualquer OUTRA divergência continua visível."""
    return re.sub(r' <span class="flag"[^>]*>' + re.escape(WARN)
                  + r' (?:início imediato[^<]*|immediate start[^<]*)</span>',
                  "", html)


def _main_module(fname: str):
    blob = subprocess.run(
        ["git", "show", f"{_AB_BASELINE_SHA}:scripts/{fname}"],
        capture_output=True, text=True, cwd=str(ROOT), check=True).stdout
    return blob


def _render_main(jobs, *, full):
    """Renderiza a MESMA fixture no minimal_page.py pré-F62 (subprocesso
    isolado, offline). None se indisponível (checkout shallow)."""
    try:
        blob = _main_module("minimal_page.py")
    except Exception:  # noqa: BLE001 — CI shallow degrada, nunca falso-verde
        return None
    with tempfile.TemporaryDirectory(prefix="f62_ab_") as td:
        tdp = Path(td)
        (tdp / "scripts").mkdir(parents=True)
        (tdp / "scripts" / "minimal_page.py").write_text(
            blob, encoding="utf-8")
        jp = tdp / "jobs.json"
        jp.write_text(json.dumps(jobs), encoding="utf-8")
        top = "mp.PAGE_TOP_FULL" if full else "mp.PAGE_TOP"
        code = (
            "import sys, json\n"
            f"sys.path.insert(0, r'{tdp / 'scripts'}')\n"
            f"sys.path.insert(0, r'{ROOT / 'src'}')\n"
            "import minimal_page as mp\n"
            f"jobs = json.load(open(r'{jp}'))\n"
            f"html = mp.render_size_aware(jobs, total_eligible=len(jobs),"
            f" generated_at='{STAMP}', top={top}, full_list={full},"
            f" vitrine=True, lang='pt')\n"
            f"open(r'{tdp / 'out.html'}', 'w', encoding='utf-8').write(html)\n"
            "print('ok')\n")
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("      [A/B antes] subprocesso falhou:",
                  r.stderr.strip().splitlines()[-1] if r.stderr else "?")
            return None
        return (tdp / "out.html").read_text(encoding="utf-8")


def test_ab_byte():
    section(f"E: A/B byte a byte — render pt == main pré-F62 "
            f"(SHA congelado {_AB_BASELINE_SHA}) módulo badges F62")
    for full, regime in ((False, "top-N"), (True, "full-list")):
        head = _render_main(MINI, full=full)
        if head is None:
            print(f"  [SKIP] git show indisponível (checkout shallow) — "
                  f"regime {regime} degradado com aviso, sem falso-verde")
            continue
        cur = _render(MINI, full=full)
        n = len(re.findall(r' <span class="flag"[^>]*>' + re.escape(WARN)
                           + r' (?:início imediato|immediate start)', cur))
        cur_net = _strip_f62(cur)
        check(f"E{1 if not full else 2} {regime}: {n} badges; "
              f"branch menos badges == main BYTE A BYTE",
              cur_net == head and n == 2,
              f"{len(cur_net.encode('utf-8'))}B vs "
              f"{len(head.encode('utf-8'))}B")
    # digest: seção 📅 — diff EXATAMENTE a linha ⚠; sem imediatas, ZERO diff
    try:
        reports = {
            "with_imm": {"funnel": None, "trend": None, "application": None,
                         "seasonality": fr.seasonality_summary(MINI)},
            "no_imm": {"funnel": None, "trend": None, "application": None,
                       "seasonality": fr.seasonality_summary(
                           [LIEBHERR, AMAZON, PLAIN])},
        }
        with tempfile.TemporaryDirectory(prefix="f62_abd_") as td:
            tdp = Path(td)
            (tdp / "scripts").mkdir(parents=True)
            for f in ("ranking_digest.py", "seasonality.py",
                      "funnel_report.py"):
                (tdp / "scripts" / f).write_text(
                    _main_module(f), encoding="utf-8")
            rp = tdp / "reports.json"
            rp.write_text(json.dumps(reports), encoding="utf-8")
            code = (
                "import sys, json\n"
                f"sys.path.insert(0, r'{tdp / 'scripts'}')\n"
                f"sys.path.insert(0, r'{ROOT / 'src'}')\n"
                "import ranking_digest as rg\n"
                f"r = json.load(open(r'{rp}'))\n"
                "print(json.dumps({k: rg.funnel_seasonality_lines(v)"
                " for k, v in r.items()}, ensure_ascii=False))\n")
            r = subprocess.run([sys.executable, "-c", code],
                               capture_output=True, text=True)
            main_map = (json.loads(r.stdout)
                        if r.returncode == 0 else None)
    except Exception:  # noqa: BLE001 — shallow: degrada
        main_map = None
    if main_map is None:
        print("  [SKIP] A/B do digest indisponível (checkout shallow)")
    else:
        cur_map = {k: rg.funnel_seasonality_lines(v) for k, v in reports.items()}
        diff = ([l for l in cur_map["with_imm"]
                 if l not in main_map["with_imm"]]
                + [l for l in main_map["with_imm"]
                   if l not in cur_map["with_imm"]])
        check("E3 digest c/ imediatas: diff simétrico vs main = SÓ a ⚠",
              len(diff) == 1 and diff[0].startswith("  ⚠ início imediato")
              and diff[0].endswith("conflita com jan/2027"),
              detail=str(diff))
        check("E4 digest SEM imediatas: seção == main byte a byte",
              cur_map["no_imm"] == main_map["no_imm"],
              detail=str(cur_map["no_imm"]))


# ---------------------------------------------------------------------------
# F. Wiring + never-worsens (display-only; pipeline intocado)
# ---------------------------------------------------------------------------
def test_wiring():
    section("F: wiring + never-worsens — score/ranking NUNCA tocados")
    src_mp = (SCRIPTS / "minimal_page.py").read_text(encoding="utf-8")
    check("F1 call-site único do _card wired: start_conflict_flag=ab_sofort_flag",
          "start_conflict_flag=ab_sofort_flag(job, lang)" in src_mp)
    tree = ast.parse(src_mp)
    top_imports = [n for n in tree.body
                   if isinstance(n, ast.Import)
                   and any(a.name == "seasonality" for a in n.names)]
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "ab_sofort_flag")
    writes = [n for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "open"]
    check("F2 pureza: seasonality é import LAZY; ab_sofort_flag sem open()",
          top_imports == [] and writes == [])
    hits = []
    for f in (ROOT / "src" / "internship_finder").rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        if "ab_sofort" in t or "start_conflict" in t:
            hits.append(str(f))
    check("F3 display-only: src/ (pipeline) ZERO menções ao badge F62",
          hits == [], detail=str(hits))
    html = _render(MINI)
    check("F4 ordem/score intocados: mesmos 5 cards na ordem de score",
          [m for m in re.findall(r'<a class="t"[^>]*>([^<]*)</a>', html)]
          == [j["title"] for j in MINI])
    leg = mp._legend_html("pt") + mp._legend_html("en")
    check("F5 legenda intocada: o badge explica a si MESMO (zero chrome novo)",
          "conflita com jan/2027" not in leg
          and "immediate start — conflicts" not in leg)


# ---------------------------------------------------------------------------
# G. ci.yml — união RELATIVA (padrão F61)
# ---------------------------------------------------------------------------
def test_ci_union():
    section("G: ci.yml — união relativa")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8")
    m = re.search(r"tests=\(([^)]*)\)", ci, re.S)
    arr = m.group(1).split() if m else []
    check("G1 test_f62 presente no array do CI (união por presença)",
          "test_f62" in arr, f"{len(arr)} suítes")
    check("G2 array vivo e relativo (>= 101; contagem nunca exata)",
          len(arr) >= 101, f"{len(arr)}")
    missing = [t for t in arr
               if not (SCRIPTS / f"{t}.py").exists()]
    check("G3 todo token do array tem arquivo (sanity da união)",
          missing == [], detail=str(missing))


def main() -> int:
    test_flag_pura()
    test_card_pt()
    test_card_en()
    test_digest_line()
    test_ab_byte()
    test_wiring()
    test_ci_union()
    fails = [c for c in CHECKS if not c[1]]
    print(f"\n{'=' * 60}")
    print(f"F62: {len(CHECKS)} checks, {len(fails)} falhas")
    for name, _, detail in fails:
        print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

