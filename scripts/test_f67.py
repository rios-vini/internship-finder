#!/usr/bin/env python3
"""test_f67 — Contexto de início para o imediato (aperta o parser F45
contra os 11 FPs de prosa; 26 reais intocados).

F67 (19/10, spec da card): o badge "⚠ início imediato — conflita com
jan/2027" da F62 acendia nos 37 canônicos "ab sofort", mas a medição
F62 §2 (a olho, run 17/10) splitou 26 janelas REAIS ("Ab sofort für 6
Monate", "Beginn: ab sofort", "STARTING IMMEDIATELY … FOR 6 MONTHS") de
11 FALSOS-POSITIVOS EM PROSA (7× slogan Lidl "steigt sofort in die
Arbeitswelt ein", 2× rodapé anti-fraude Medtronic "contact us
immediately", 1× processo boas "join us immediately", 1× lab OLAM
"measuring … immediately after production"). A diferença observável:
reais vêm com MARCADOR DE CONTEXTO DE INÍCIO colado ao termo; prosa,
não.

DECISÃO DE DESIGN (recomendação da card, documentada aqui e no
seasonality.py): o hit imediato ganha "context" (bool); sem marcador
na janela ±60 chars o hit CONTINUA no calendário 📆 com o rótulo
"ab sofort" (contagem textual preservada: 37 segue 37) mas deixa de
ser IMEDIATO — só o SINAL aperta (badge da F62 e linha ⚠ do digest
consomem context=True via campo "immediate_context" do summary, fonte
única seasonality.immediate_context_count). Calibração medida nos 37:
real mais distante tem marcador a 45 chars; os 11 FPs não têm NENHUM
a ±250 (folga ~200). Canônico ganha desempate: imediato COM contexto
vence imediato em prosa no mesmo texto (delta 0 nos runs 17–19/10 —
nenhuma vaga com 2 hits).

Série medida (cópias read-only /tmp/f67-data; data/ intocável):
  run 17/10: 37 = 26R+11FP -> 26 c/ contexto, 11 sem (26/26 + 0/11)
  run 18/10: 37 = 26R+11FP -> idem (delta 17→18: Schaeffler e MAHLE
             saem; Lidl Stiftung (praktikum_info) e MAHLE nova entram)
  run 19/10: 34 = 23R+11FP -> 23 c/ contexto, 11 sem (churn todo no
             lado real: MAHLE + Vodafone ×2 saem; FPs estáveis 11/11/11)

Fixtures VERBATIM: os 37 do run 17/10 (archive 20261018T090001Z),
trechos ±120 chars, expecteds VALIDADOS contra o parser real pelo
gerador (anti-invenção; regra da casa).

100% OFFLINE (nenhum socket; data/ intocável). Exit 0/1 (padrão: rc +
zero '[FAIL]').
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

CHECKS: list[tuple[str, bool, str]] = []
# Basline congelado do A/B display: main pré-F67 (F65) — lição PR #145
# (nunca main móvel). CI shallow: [SKIP] sem falso-verde.
_AB_BASELINE_SHA = "f604fe3"
WARN = "⚠️"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def _job(jid: str, desc: str, score: float = 10.0) -> dict:
    """Job de fixture: título NEUTRO (zero marcadores/hits) + o trecho
    verbatim na descrição — o texto varrido pelo consumidor real
    (``job_window_text``) é 'título — descrição'."""
    return {"id": jid, "title": "Praktikum (m/w/d)",
            "company": jid.split("|")[0], "location": "Berlin, DE",
            "description": desc, "url": "https://example.com/j",
            "score": score, "posted_at": "2026-10-19", "raw": {}}



# Fixtures VERBATIM — os 37 canônicos imediatos do run 17/10
# (archive 20261018T090001Z; tábua F62 §2): 26 janelas
# declaradas (REAL, contexto de início presente) + 11 FPs em
# prosa (slogan Lidl, rodapé Medtronic, processo boas, lab
# OLAM). Trechos de ±120 chars ao redor do termo; whitespace
# normalizado. Expecteds VALIDADOS contra o parser real pelo
# gerador (medir_f67/calibrar/selfcheck em /tmp/f67-data).

# REAL — lidlstiftup2
_REAL_01 = 'gaben Unterstütze uns bei der Digitalisierung und Weiterentwicklung des Reportings mit SAP und der SAP Analytics Cloud. Ab sofort für 6 Monate. … konkret heißt das: Mitarbeit im Anforderungsprozess rund um die Aufnahme und den Rollout fachlicher Anf'

# REAL — lidlstiftup2
_REAL_02 = 'de Teil unseres Daten & KI Teams, unterstütze datenbasierte Analysen und entwickle innovative Automatisierungslösungen. Ab sofort für 4 bis 6 Monate. … konkret heißt das: Begleitung des gesamten Prozesses einer Analyse: Von der Definition der Frages'

# REAL — Schaeffler Technologies AG & Co. KG
_REAL_03 = 'zung für ein Praktikum bei Schaeffler ist der Nachweis der Immatrikulation zum Zeitpunkt des Praktikums. Die Stelle ist ab sofort für den Zeitraum von 6 Monaten zu besetzen. Ihre Aufgaben Mitarbeit in spannenden internationalen Projekten im Bereich'

# REAL — lidlstiftup2
_REAL_04 = 'de Teil unseres Daten & KI Teams, unterstütze datenbasierte Analysen und entwickle innovative Automatisierungslösungen. Ab sofort für 4 bis 6 Monate. … konkret heißt das: Erhalte Einblicke in Big Data und Machine Learning Technologien Mitarbeit bei'

# FP — lidlstiftup2
_FP_01 = 'Praktikum Warengeschäft - Supply Chain & Disposition (m/w/d) — Einleitung Wer mit uns ins Berufsleben startet, steigt sofort in die Arbeitswelt ein ─ und mit uns schnell die Jobleiter hoch. Wir wollen, dass du als Teil des Teams nicht nur Neues'

# REAL — lidlstiftup2
_REAL_05 = '. Deine Aufgaben Unterstütze uns bei der Durchführung von Auswertungen und Analysen relevanter Kennzahlen des Einkaufs. Ab sofort für bis zu 6 Monate. … konkret heißt das: Mitarbeit bei der Analyse von Auffälligkeiten in den Einkaufs-KPIs (z.B. Prei'

# REAL — careers.dhl.com
_REAL_06 = 'Internship in Global Belonging (m/f/d) – Communication Design & Analytics — JOIN OUR TEAM IN BONN – START IMMEDIATELY OR BY ARRANGEMENT FOR 3–6 MONTHS. Internship in Global Belonging (m/f/d) – Communication Design & Analytics. Ready to m'

# REAL — careers.dhl.com
_REAL_07 = 'Praktikant (m/w/d) Business Intelligence - Zeitwirtschaft — GESUCHT IN BONN, AB SOFORT UND FÜR 6 MONATE. Praktikant (m/w/d) Business Intelligence - Zeitwirtschaft. SIE WISSEN VIEL UND WOLLEN ETWAS BEWEGEN?'

# REAL — Vodafone Procurement Company S.a.r.l.
_REAL_08 = 'n wir Dich z. B. mit flexiblen Arbeitszeiten und Gesundheitsangeboten bei einer ausgeglichenen Work-Life-Balance. Wann? Ab sofort für Dein fünf - bis sechsmonatiges Praktikum. Bereit für das Neue, das Unerwartete, das Eindrucksvolle? Dann bewirb Dic'

# REAL — Vodafone Procurement Company S.a.r.l.
_REAL_09 = 'rstützen wir Dich bei einer ausgeglichenen Work-Life-Balance. Dazu bekommst Du bei uns eine attraktive Vergütung. Wann? Ab sofort für Dein drei - bis sechsmonatiges Praktikum. Bereit für das Neue, das Unerwartete, das Eindrucksvolle? Dann bewirb Dic'

# REAL — FRoSTA AG Career
_REAL_10 = 'Praktikant Prozessoptimierung (w/m/d) — Für unseren Standort Bobenheim-Roxheim suchen wir ab sofort für sechs Monate einen motivierte:n und qualifizierte:n Student:in (w/m/d) für ein PRAKTIKUM IM BEREICH PROZESSOPTIMIER'

# FP — lidlstiftup2
_FP_02 = 'Praktikum im Logistikzentrum — Einleitung Wer mit uns ins Berufsleben startet, steigt sofort in die Arbeitswelt ein ─ und mit uns schnell die Jobleiter hoch. Wir wollen, dass du als Teil des Teams nicht nur Neues'

# FP — lidlstiftup2
_FP_03 = 'Praktikum im Logistikzentrum — Einleitung Wer mit uns ins Berufsleben startet, steigt sofort in die Arbeitswelt ein ─ und mit uns schnell die Jobleiter hoch. Wir wollen, dass du als Teil des Teams nicht nur Neues'

# FP — Medtronic
_FP_04 = 'regarding the authenticity of a communication alleged to have been made by or on behalf of Medtronic, please contact us immediately at <AskHR@medtronic.com> . Benefits & Compensation Medtronic offers a competitive Salary and flexible Benefits Package'

# FP — Medtronic (Redeploymentmedtroniccareers)
_FP_05 = 'regarding the authenticity of a communication alleged to have been made by or on behalf of Medtronic, please contact us immediately at <AskHR@medtronic.com> . Benefits & Compensation Medtronic offers a competitive Salary and flexible Benefits Package'

# REAL — Wolke Back & Snack GmbH
_REAL_11 = 'etzt Teil unserer Wolke-Familie und mach unsere Region jeden Tag ein bisschen glücklicher. **Wann und wo?** Wir suchen ab sofort für unsere Zentrale in Dinklage Unterstützung durch einen Werkstudenten oder Praktikanten , der unseren Einkauf und Inn'

# REAL — Würth Group
_REAL_12 = 'Praktikant (m/w/d) im Bereich Logistik - Leihgut- & Palettenmanagement — Beginn: ab sofort Was Dich erwartet Einblicke : Du erhältst tiefe Einblicke in die Leihgutabwicklung des Palettenmanagements und begleite'

# REAL — careers.dhl.com
_REAL_13 = 'formation Security und Data Protection (m/w/d) — DHL Express – Ein Unternehmen, das Menschen verbindet! Wir suchen dich ab sofort als Praktikant Information Security & Data Protection (m/w/d) in unserer Unternehmenszentrale in Bonn idealerweise f...'

# REAL — MAHLE International GmbH
_REAL_14 = 'Internship (m/f/d) Lead-Buying Mechatronics — Time period Immediately for a period of 6 months Tasks Support the lead buyer with the purchasing material group strategies about mechatronic c'

# REAL — careers.dhl.com
_REAL_15 = 'Intern (m/f/d) in the Human Resources Group Functions Data & Systems department — JOIN OUR TEAM IN BONN—STARTING IMMEDIATELY OR AS AGREED, FOR 6 MONTHS. Intern (m/f/d) in the Human Resources Group Functions Data & Systems department. DO YOU KNO'

# REAL — ahc GmbH
_REAL_16 = 'Praktikant/Werkstudent AI-Automatisierung (w/m/d) — Werde Teil unseres Teams und verstärke uns ab sofort in Stuttgart (vor Ort/Hybrid) als Praktikant/Werkstudent AI-Automatisierung (w/m/d) . Du arbeitest direkt mit unseren C'

# REAL — lidlstiftup2
_REAL_17 = 'der Erstellung von Inhalten (Videos, Postings, Emails etc.) zur Förderung der Nutzung von digitalen Arbeitsplatz-Tools. Ab sofort für 6 Monate. ...konkret heißt das: Unterstützung bei der Planung und Umsetzung von Kommunikationskampagnen für zentral'

# REAL — lidlstiftup2
_REAL_18 = 'l lohnt sich. Deine Aufgaben Unterstütze uns bei der Konzeptionierung und Implementierung von Projekten im Controlling. Ab sofort für 6 Monate. … konkret heißt das: Mitarbeit bei der Weiterentwicklung von internationalen Standards und Prozessen sowi'

# REAL — lidlstiftup2
_REAL_19 = 'smarter Prozesse, damit unsere Eigenmarken-Artikel reibungslos, pünktlich und im besten Design in den Filialen glänzen. Ab sofort für 6 Monate. … konkret heißt das: Unterstützung bei der Gestaltung unserer Prozesse & Standards im Bereich Verpackungs'

# FP — lidlstiftup2
_FP_06 = 'Praktikum Warengeschäft — Einleitung Wer mit uns ins Berufsleben startet, steigt sofort in die Arbeitswelt ein ─ und mit uns schnell die Jobleiter hoch. Wir wollen, dass du als Teil des Teams nicht nur Neues'

# FP — lidlstiftup2
_FP_07 = 'Praktikum Warengeschäft — Einleitung Wer mit uns ins Berufsleben startet, steigt sofort in die Arbeitswelt ein ─ und mit uns schnell die Jobleiter hoch. Wir wollen, dass du als Teil des Teams nicht nur Neues'

# FP — lidlstiftup2
_FP_08 = 'Praktikum Warengeschäft — Einleitung Wer mit uns ins Berufsleben startet, steigt sofort in die Arbeitswelt ein ─ und mit uns schnell die Jobleiter hoch. Wir wollen, dass du als Teil des Teams nicht nur Neues'

# FP — lidlstiftup2
_FP_09 = 'Praktikum Warengeschäft - Sortiment (m/w/d) — Einleitung Wer mit uns ins Berufsleben startet, steigt sofort in die Arbeitswelt ein ─ und mit uns schnell die Jobleiter hoch. Wir wollen, dass du als Teil des Teams nicht nur Neues'

# REAL — REWE Group
_REAL_20 = 'Werkstudent International Tax (m/w/d) — Ort: 50668 Köln | Vertragsart: Teilzeit, befristet | Start: ab sofort | Job-ID: 976039 Was wir zusammen vorhaben: Bei uns erhältst du praxisnahe Einblicke in internationale Steuerfragen und'

# FP — boas
_FP_10 = 'nvite you to work with us for a day so we can both see if we like working together. If everything fits, you can join us immediately. We are looking forward to meeting you!'

# REAL — moot
_REAL_21 = 'Praktikum Operations Management (m/w/d) — Ab sofort für 3 bis 6 Monate in Berlin. Aufgaben Deine Aufgaben Unterstütze uns im operativen Tagesgeschäft Fotografiere unsere P'

# REAL — Würth Group
_REAL_22 = 'Praktikant (m/w/d) im Bereich Vertrieb national — Beginn: ab sofort Das erwartet Dich bei uns Einblicke: Du bekommst Einblicke in das Key Account Management und betreust dabei unsere inte'

# REAL — REWE Group
_REAL_23 = 'Praktikum HR IT Support (m/w/d) — Ort: 50933 Köln | Vertragsart: Vollzeit, befristet | Start: Ab sofort | Job-ID: 982965 Was wir zusammen vorhaben: Wir sind die Starthilfe für den Einstieg neuer Mitarbeitenden in die System'

# REAL — mllerservi
_REAL_24 = 'r Menschen zu bringen. Begleite uns auf dieser Reise und sichere Dir einen Job mit Zukunftsperspektive. Wir suchen Dich ab sofort in Aretsried für das Praktikum Trade Marketing & Category Management. Deine Rolle Du wirkst bei der Planung, Steuerung'

# REAL — mllerservi
_REAL_25 = 'r Menschen zu bringen. Begleite uns auf dieser Reise und sichere Dir einen Job mit Zukunftsperspektive. Wir suchen Dich ab sofort in Leppersdorf als Werkstudent Internal Balancing & Kostenoptimierung Produktion (m/w/d). Deine Rolle Du unterstützt de'

# FP — OLAM INTERNATIONAL LTD
_FP_11 = 'ull shelf‑life evaluation process, including: Preparing nut fillings at lab scale and measuring key baseline parameters immediately after production. Supporting application testing, working closely with the Application team to evaluate product perform'

# REAL — maora-matchade
_REAL_26 = 'onzepts schauen? Dann werde Teil unseres Teams und unterstütze uns im Storemanagement! Für unser Matcha Café suchen wir ab sofort eine motivierte Unterstützung im Rahmen eines 3-monatigen Pflichtpraktikums . Aufgaben Deine Aufgaben Unterstützung der'


# Listas da tábua F62 §2 (26 REAIS + 11 FPs em prosa)
REALS = [
    _REAL_01,
    _REAL_02,
    _REAL_03,
    _REAL_04,
    _REAL_05,
    _REAL_06,
    _REAL_07,
    _REAL_08,
    _REAL_09,
    _REAL_10,
    _REAL_11,
    _REAL_12,
    _REAL_13,
    _REAL_14,
    _REAL_15,
    _REAL_16,
    _REAL_17,
    _REAL_18,
    _REAL_19,
    _REAL_20,
    _REAL_21,
    _REAL_22,
    _REAL_23,
    _REAL_24,
    _REAL_25,
    _REAL_26,
]

FPS = [
    _FP_01,
    _FP_02,
    _FP_03,
    _FP_04,
    _FP_05,
    _FP_06,
    _FP_07,
    _FP_08,
    _FP_09,
    _FP_10,
    _FP_11,
]

# ---------------------------------------------------------------------------
# Suíte A — PRECISÃO da regra: 26/26 + 0/11 nos fixtures verbatim
# ---------------------------------------------------------------------------

def test_precisao():
    section("A: precisão — 26 reais c/ contexto, 11 FPs sem (26/26 + 0/11)")
    real_ok = [f for f in REALS if
               (h := seasonality.canonical_seasonality(f))
               and h.get("kind") == "immediate" and h.get("context")]
    check("A1 26/26 REAIS: canônico immediate COM contexto",
          len(real_ok) == 26, f"{len(real_ok)}/26")
    fp_clean = [f for f in FPS if
                (h := seasonality.canonical_seasonality(f))
                and h.get("kind") == "immediate" and not h.get("context")]
    fp_dirty = [f for f in FPS if
                (h := seasonality.canonical_seasonality(f))
                and h.get("context")]
    check("A2 0/11 FPs: canônico immediate SEM contexto (prosa)",
          len(fp_clean) == 11 and not fp_dirty,
          f"limpos={len(fp_clean)}/11, com contexto={len(fp_dirty)}")
    # mesmo veredito no TEXTO CANÔNICO DO CONSUMIDOR (título — descrição):
    # classe esperada pela IDENTIDADE do fixture (id), nunca por score
    jobs = [_job(f"real{i}|f67:{i}", f, score=20.0 - i)
            for i, f in enumerate(REALS)]
    jobs += [_job(f"fp{i}|f67:{i}", f, score=1.0 + i)
             for i, f in enumerate(FPS)]
    a3_ok = all(
        ((h := seasonality.canonical_seasonality(
            seasonality.job_window_text(j))) is not None
         and h.get("kind") == "immediate"
         and h.get("context") is j["id"].startswith("real"))
        for j in jobs)
    check("A3 job_window_text: mesma regra no texto do consumidor (37/37)",
          a3_ok)
    texts = [seasonality.job_window_text(j) for j in jobs]
    check("A4 immediate_context_count(37) == 26",
          seasonality.immediate_context_count(texts) == 26)
    cal = seasonality.seasonality_calendar(texts)
    imm_total = next((n for lab, n in cal if lab == "ab sofort"), 0)
    check("A5 calendário 📆 PRESERVA contagem textual: 'ab sofort' 37",
          imm_total == 37, f"calendário={cal}")
    n_badges = sum(1 for j in jobs if mp.ab_sofort_flag(j))
    check("A6 badge: acende nos 26 reais, ZERO nos 11 FPs",
          n_badges == 26, f"{n_badges} badges")


# ---------------------------------------------------------------------------
# Suíte B — parser puro: campo context, janela, tie-break, determinismo
# ---------------------------------------------------------------------------

def test_parser_puro():
    section("B: parser — contexto, janela ±60, tie-break, determinismo")
    can = seasonality.canonical_seasonality("ab sofort")
    check("B1 'ab sofort' PURO (sem marcador): prosa — context=False",
          bool(can) and can.get("kind") == "immediate"
          and can.get("context") is False)
    lab = seasonality.seasonality_label(can)
    check("B2 rótulo intacto (pino F62): 'ab sofort' == rg.IMMEDIATE_LABEL",
          lab == "ab sofort" == rg.IMMEDIATE_LABEL, f"{lab!r}")
    both = ("Wer mit uns ins Berufsleben startet, steigt sofort in die "
            "Arbeitswelt ein. Deine Aufgaben Ab sofort für 6 Monate.")
    can = seasonality.canonical_seasonality(both)
    check("B3 tie-break: slogan ANTES + janela real DEPOIS -> canônico "
          "é o hit COM contexto",
          bool(can) and can.get("kind") == "immediate"
          and can.get("context") is True
          and can.get("term", "").lower() == "ab sofort")
    t = "SoSe 2027 und ab sofort"
    check("B4 prioridade intocada: semestre vence imediato (F45)",
          bool(seasonality.canonical_seasonality(t))
          and seasonality.canonical_seasonality(t).get("kind") == "semester")
    hit = seasonality.parse_seasonality("Ab sofort für 6 Monate.")
    check("B5 determinismo: parse 2x idêntico (campo context incluso)",
          json.dumps(hit) == json.dumps(
              seasonality.parse_seasonality("Ab sofort für 6 Monate.")))
    # janela ±60 pinada: probes de borda com a DISTÂNCIA marcador↔termo
    # variando (pad entre espaços — o \b do marcador e o lookbehind do
    # termo exigem separação). Antes: início do marcador a exatamente W
    # do início do termo casa; W+1 não. Depois: fim do marcador a
    # exatamente W do fim do termo casa (endpos inclusivo); W+1 não.
    W = seasonality._IMMEDIATE_CONTEXT_WINDOW
    check("B6 janela documentada: ±60 (calibração: real max 45, FPs 250)",
          W == 60)
    in_before = "wann " + "z" * (W - 6) + " ab sofort"
    out_before = "wann " + "z" * (W - 5) + " ab sofort"
    h_in = seasonality.canonical_seasonality(in_before)
    h_out = seasonality.canonical_seasonality(out_before)
    check("B7 borda ANTES: marcador a exatamente W casa; W+1 não",
          bool(h_in) and h_in.get("context") is True
          and bool(h_out) and h_out.get("context") is False,
          f"W={W}")
    in_after = "ab sofort " + "z" * (W - 8) + " monate"
    out_after = "ab sofort " + "z" * (W - 7) + " monate"
    a1 = seasonality.canonical_seasonality(in_after)
    a2 = seasonality.canonical_seasonality(out_after)
    check("B8 borda DEPOIS: marcador no limite casa; além não",
          bool(a1) and a1.get("context") is True
          and bool(a2) and a2.get("context") is False)
    slogan = FPS[0]
    check("B9 'startet' (verbo do slogan Lidl) NÃO é marcador — o FP real "
          "segue limpo",
          (h := seasonality.canonical_seasonality(slogan))
          is not None and h.get("context") is False)


# ---------------------------------------------------------------------------
# Suíte C — consumidores: summary, linha ⚠, degradação honesta
# ---------------------------------------------------------------------------

def test_consumidores():
    section("C: summary + linha ⚠ (sinal apertado; 📆 preservado)")
    jobs = ([_job(f"real{i}|f67:{i}", f) for i, f in enumerate(REALS)]
            + [_job(f"fp{i}|f67:{i}", f) for i, f in enumerate(FPS)])
    s = fr.seasonality_summary(jobs)
    check("C1 summary: immediate_context=26; 📆 'ab sofort' 37 (ambos vivos)",
          s["immediate_context"] == 26
          and next(c["count"] for c in s["calendar"]
                   if c["label"] == "ab sofort") == 37)
    report = {"funnel": None, "trend": None, "application": None,
              "seasonality": s}
    lines = rg.funnel_seasonality_lines(report)
    warn = ("  ⚠ início imediato (ab sofort): 26 vagas "
            "— conflita com jan/2027")
    cal_line = next(l for l in lines if l.startswith("  📆 "))
    check("C2 linha ⚠ conta os 26 (não os 37), DEPOIS da 📆",
          warn in lines
          and lines.index(warn) > lines.index(cal_line), cal_line)
    check("C3 📆 preserva: linha contém 'ab sofort: 37'",
          "ab sofort: 37" in cal_line)
    old = {"funnel": None, "trend": None, "application": None,
           "seasonality": {"scanned": 2, "with_window": 2,
                           "calendar": [{"label": "ab sofort", "count": 2}]}}
    check("C4 report SEM o campo (formato pré-F67): ⚠ AUSENTE — "
          "degradação honesta, nunca volta a contar prosa",
          "⚠" not in "\n".join(rg.funnel_seasonality_lines(old)))
    one = json.loads(json.dumps(report))
    one["seasonality"] = fr.seasonality_summary(jobs[:1])
    check("C5 singular: '1 vaga' com contexto",
          ("  ⚠ início imediato (ab sofort): 1 vaga "
           "— conflita com jan/2027")
          in rg.funnel_seasonality_lines(one))
    only_fp = {"funnel": None, "trend": None, "application": None,
               "seasonality": fr.seasonality_summary(
                   [_job(f"fp{i}|f67:{i}", f) for i, f in enumerate(FPS)])}
    lines_fp = rg.funnel_seasonality_lines(only_fp)
    check("C6 só prosa (11 FPs): 📆 segue viva com 11, ⚠ AUSENTE",
          any(l.startswith("  📆 ") and "ab sofort: 11" in l
              for l in lines_fp)
          and "⚠" not in "\n".join(lines_fp))



# ---------------------------------------------------------------------------
# Suíte D — display-only + A/B byte a byte (baseline congelado f604fe3)
# ---------------------------------------------------------------------------

def _strip_badges(html: str) -> str:
    """Remove SOMENTE os spans do badge F62/F67 (strip cirúrgico dos
    DOIS lados do A/B — o delta de exibição esperado é o número de
    badges; qualquer OUTRO byte divergente continua FAIL)."""
    # F86 — o item da legenda ⏳/⚠️ ganhou o sinal de tipo ambíguo e as
    # cards de TÍTULO DUPLO ganham o badge ⚠️ (normaliza novo -> antigo
    # nos DOIS lados do A/B; fixture F67 sem título duplo = no-op).
    html = html.replace(
        "alemã / tipo ambíguo Werkstudent/Praktikum (F86 — decidir na "
        "vaga)", "alemã")
    html = re.sub(
        r' <span class="flag"[^>]*>⚠️ (?:tipo ambíguo|ambiguous type)'
        r'[^<]*</span>', "", html)
    return re.sub(
        r' <span class="flag"[^>]*>' + re.escape(WARN)
        + r' (?:início imediato[^<]*|immediate start[^<]*)</span>',
        "", html)


def _baseline_modules(names: list[str]):
    """Bytes dos módulos do baseline congelado (git show). None se o
    checkout for raso (CI) — o chamador degrada com [SKIP]."""
    out = {}
    for fname in names:
        r = subprocess.run(
            ["git", "show", f"{_AB_BASELINE_SHA}:scripts/{fname}"],
            capture_output=True, text=True, cwd=str(ROOT))
        if r.returncode != 0:
            return None
        out[fname] = r.stdout
    return out


def _render_mods(mods: dict, jobs: list[dict], *, full: bool) -> str | None:
    """Renderiza a MESMA fixture com minimal_page.py + seasonality.py do
    baseline (subprocesso isolado, offline)."""
    with tempfile.TemporaryDirectory(prefix="f67_ab_") as td:
        tdp = Path(td)
        (tdp / "scripts").mkdir(parents=True)
        for fname, blob in mods.items():
            (tdp / "scripts" / fname).write_text(blob, encoding="utf-8")
        jp = tdp / "jobs.json"
        jp.write_text(json.dumps(jobs), encoding="utf-8")
        top = ("mp.PAGE_TOP_FULL" if full else "mp.PAGE_TOP")
        code = (
            "import sys, json\n"
            f"sys.path.insert(0, r'{tdp / 'scripts'}')\n"
            f"sys.path.insert(0, r'{ROOT / 'src'}')\n"
            "import minimal_page as mp\n"
            f"jobs = json.load(open(r'{jp}'))\n"
            f"html = mp.render_size_aware(jobs, total_eligible=len(jobs),"
            f" generated_at='2026-10-19T09:20:00Z', top={top},"
            f" full_list={full}, vitrine=True, lang='pt')\n"
            f"open(r'{tdp / 'out.html'}', 'w', encoding='utf-8').write(html)\n"
            "print('ok')\n")
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("      [A/B baseline] subprocesso falhou:",
                  r.stderr.strip().splitlines()[-1] if r.stderr else "?")
            return None
        return (tdp / "out.html").read_text(encoding="utf-8")


def test_ab_display():
    section(f"D: A/B display-only vs main pré-F67 "
            f"(SHA congelado {_AB_BASELINE_SHA})")
    src_hits = []
    for f in (ROOT / "src" / "internship_finder").rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        if ("immediate_context" in t or "_IMMEDIATE_CONTEXT" in t
                or "ab_sofort" in t or "start_conflict" in t):
            src_hits.append(str(f))
    check("D1 display-only: src/ (pipeline) ZERO menções ao sinal F67",
          src_hits == [], detail=str(src_hits))

    jobs = ([_job(f"real{i}|f67:{i}", f, score=20.0 - i)
             for i, f in enumerate(REALS)]
            + [_job(f"fp{i}|f67:{i}", f, score=1.0 + i)
               for i, f in enumerate(FPS)])
    mods = _baseline_modules(["minimal_page.py", "seasonality.py"])
    if mods is None:
        print("  [SKIP] git show indisponível (checkout raso) — A/B de "
              "página degradado com aviso, sem falso-verde")
    else:
        for full, regime in ((False, "top-N"), (True, "full-list")):
            base = _render_mods(mods, jobs, full=full)
            cur = mp.render_size_aware(
                jobs, total_eligible=len(jobs),
                generated_at="2026-10-19T09:20:00Z",
                top=(mp.PAGE_TOP_FULL if full else mp.PAGE_TOP),
                full_list=full, vitrine=True, lang="pt")
            n_base = len(re.findall(
                r'<span class="flag"[^>]*>' + re.escape(WARN)
                + r' início imediato', base))
            n_cur = len(re.findall(
                r'<span class="flag"[^>]*>' + re.escape(WARN)
                + r' início imediato', cur))
            ok = (_strip_badges(cur) == _strip_badges(base)
                  and n_base == 37 and n_cur == 26)
            check(f"D{'2' if not full else '3'} {regime}: main 37 badges "
                  f"-> branch 26; strip dos DOIS lados == byte a byte",
                  ok, f"main={n_base} branch={n_cur}; "
                      f"{len(_strip_badges(cur).encode())}B vs "
                      f"{len(_strip_badges(base).encode())}B")

    # digest: 📆 byte a byte; diff = SÓ as linhas ⚠ (37 -> 26)
    mods = _baseline_modules(["ranking_digest.py", "seasonality.py",
                             "funnel_report.py"])
    if mods is None:
        print("  [SKIP] A/B do digest indisponível (checkout raso)")
    else:
        reports = {"with_imm": {"funnel": None, "trend": None,
                                "application": None,
                                "seasonality": fr.seasonality_summary(jobs)}}
        with tempfile.TemporaryDirectory(prefix="f67_abd_") as td:
            tdp = Path(td)
            (tdp / "scripts").mkdir(parents=True)
            for fname, blob in mods.items():
                (tdp / "scripts" / fname).write_text(blob, encoding="utf-8")
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
            base_map = (json.loads(r.stdout)
                        if r.returncode == 0 else None)
        if base_map is None:
            print("  [SKIP] A/B do digest: subprocesso baseline falhou")
        else:
            cur_map = {k: rg.funnel_seasonality_lines(v)
                       for k, v in reports.items()}
            diff = ([l for l in cur_map["with_imm"]
                     if l not in base_map["with_imm"]]
                    + [l for l in base_map["with_imm"]
                       if l not in cur_map["with_imm"]])
            warn_cur = ("  ⚠ início imediato (ab sofort): 26 vagas "
                        "— conflita com jan/2027")
            warn_base = ("  ⚠ início imediato (ab sofort): 37 vagas "
                         "— conflita com jan/2027")
            check("D4 digest: 📆 byte a byte; diff vs main = SÓ a ⚠ "
                  "(37 -> 26)",
                  diff == [warn_cur, warn_base], detail=str(diff))
            check("D5 📆 idêntica ao main (contagem textual preservada)",
                  next(l for l in cur_map["with_imm"]
                       if l.startswith("  📆 "))
                  == next(l for l in base_map["with_imm"]
                          if l.startswith("  📆 ")))


# ---------------------------------------------------------------------------
# Suíte E — pureza (AST) + decisão documentada no fonte
# ---------------------------------------------------------------------------

def test_pureza():
    section("E: pureza do parser novo + documentação viva")
    src = Path(seasonality.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for fname in ("_immediate_has_context", "immediate_context_count"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == fname)
        writes = [n for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and (
                      (isinstance(n.func, ast.Name)
                       and n.func.id == "open")
                      or (isinstance(n.func, ast.Attribute)
                          and n.func.attr in ("read_text", "write_text",
                                              "open")))]
        check(f"E1 {fname}: pura — sem open()/I/O", not writes)
    check("E2 decisão F67 documentada no docstring do parser (medição + "
          "janela)",
          "F67" in src and "±60" in src and "45" in src)
    check("E3 marcadores calibrados presentes (beginn/wann/suchen/"
          "als Praktikant)",
          "beginn" in src and "wann" in src and "suchen" in src
          and "als\\s+praktikant" in src)


# ---------------------------------------------------------------------------
# Suíte F — ci.yml: união RELATIVA (padrão F61/F62/F65)
# ---------------------------------------------------------------------------

def test_ci_union():
    section("F: CI — suíte descoberta, relativa (F78)")
    import ci_discover_tests
    arr = ci_discover_tests.discover_tests()
    check("F1 test_f67 presente na suíte descoberta do CI (por presença)",
          "test_f67" in arr, f"{len(arr)} suítes")
    check("F2 array vivo e relativo (nunca contagem exata)", len(arr) >= 103,
          f"{len(arr)}")
    missing = [t for t in arr if not (SCRIPTS / f"{t}.py").exists()]
    check("F3 todo token do array tem arquivo (sanity da união)",
          missing == [], detail=str(missing))


def main() -> int:
    test_precisao()
    test_parser_puro()
    test_consumidores()
    test_ab_display()
    test_pureza()
    test_ci_union()
    fails = [c for c in CHECKS if not c[1]]
    print(f"\n{'=' * 60}")
    print(f"F67: {len(CHECKS)} checks, {len(fails)} falhas")
    for name, _, detail in fails:
        print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
