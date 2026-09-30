#!/usr/bin/env python3
"""Fase J — Deterministic Enrichment Quality Fixes (testes offline).

Correções determinísticas de QUALIDADE dos detectores pós-eligibilidade
(job_salary / work_authorization), sem tocar eligibility/score/ranking/
Top 30/dedup/hydration/official-page/cron (invariantes §0):

J1. "/h" reconhecido como marcador horário (VW 18,33 €/h, philips 15 €/h,
     VDI 16€/h) — 2ª alternativa do _HOURLY_AFTER_RE com prefixo
     obrigatório; "h" solto não casa.
J2. FP "N Monate befristet" → "N €/month" morto por 2 defeitos
     corrigidos: (a) \b nas duas pontas do grupo period (não casa o
     prefixo "Monat" de "Monate"); (b) label FORWARD só conta NA MESMA
     SENTENÇA (terminador [.!?;](\s|$) corta a janela forward 60).
     Backward 40 inalterado — assimetria deliberada (FP evidenciado é
     forward; backward cross-sentence sem evidência de problema).
J3. WA condicionais "if indicated" (Bosch ×5) e "falls erforderlich"
     (continental ×2) suprimem existing_required via o mecanismo
     sentence-scope da Fase F (_wa_existing_evidence) — só vocabulário
     novo, mecanismo intocado; "relocation" continua ≠ imigração.
J4. Salário ANUAL: _YEARLY_LABEL_RE (Bruttojahresgehalt / annual salary)
     + _YEARLY_AFTER_RE (/year, per year, pro Jahr, jährlich) +
     _is_yearly_clause (espelho do _is_hourly_clause, mesmo guard de
     fragmento) + gate ampliado (marcador horário/anual + moeda é
     evidência por si) + resolução hourly > yearly > sufixo > month.
     Labels compostos: \w*gehalt (Bruttojahresgehalt, Monatsgehalt),
     \w*stundenlohn (Bruttostundenlohn); "Gehaltsvorstellung" NÃO é
     label (o "s" pós "gehalt" quebra o \b final); "Gehälter" não casa
     (ä) — documentado.

Grupos (spec §6):

A. "/h" horário — EN/DE decimais, inteiros, com/sem label
B. "12 Monate" adversarial — durações nunca são salário; Monatsgehälter
   com contexto monetário real captura o valor REAL (1500), não 12
C. "6 Monate"/"2 Jahre" anti-regressão do \b — e mensais reais vivos
D. year — labels anuais e sufixos /year, pro Jahr
E. hourly composto — Bruttostundenlohn 18,33 (label a 53 chars),
   Stundenlohn 21, covestro 21 Euro (não-regressão Fase F)
F. WA condicionais — os 7 casos da spec + regressão Fase F (relocation ≠
   imigração; intento do caso 7: existing vence contexto de relocation
   em sentença separada)
G. não-regressão geral — roche €2268 (label forward MESMA sentença),
   STIHL 2.117, Tchibo 2.570, MAHLE 1500€, covestro 21/h, CURRENTA
   estruturado (raw recruitee), determinismo
H. adversarial \w*gehalt — Gehaltsvorstellung não é label; Monatsgehalt
   é; Gehälter documentado (não casa, sem quebrar)

Padrão da suíte standalone: check()/exit 1; 100% offline.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder import opportunity_intel as oi  # noqa: E402
from internship_finder import app_intel as ai           # noqa: E402

_FAILS: list[str] = []


def check(desc: str, cond: bool) -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {desc}")
    if not cond:
        _FAILS.append(desc)


def _sal(title: str = "", description: str = "") -> dict | None:
    return oi.job_salary({"title": title, "description": description})


def _sal_raw(raw: dict, description: str = "") -> dict | None:
    return oi.job_salary({"title": "", "description": description, "raw": raw})


def wa(text: str) -> str:
    return ai.work_authorization(text)["state"]


def main() -> int:
    # ------------------------------------------------------------------ A
    print("== A: /h horário ==")
    out = _sal(description="Vergütung: 18.33 €/h")
    check("A1 '18.33 €/h' (decimal EN) -> 18.33 hour",
          bool(out) and out["min"] == 18.33 and out["period"] == "hour")
    out = _sal(description="Vergütung: 18,33 €/h")
    check("A2 '18,33 €/h' (decimal DE) -> 18.33 hour",
          bool(out) and out["min"] == 18.33 and out["period"] == "hour")
    out = _sal(description="15 €/h oder 17 €/h")
    check("A3 '15 €/h oder 17 €/h' -> 15 hour (philips)",
          bool(out) and out["min"] == 15 and out["max"] == 15 and out["period"] == "hour")
    check("A3b decimais preservados exatamente (17.5)",
          (_sal(description="17.5 €/h") or {}).get("min") == 17.5)
    out = _sal(description="Gehalt: 16€/h")
    check("A4 '16€/h' colado (VDI) -> 16 hour",
          bool(out) and out["min"] == 16 and out["period"] == "hour")
    out = _sal(description="Gehalt: 17 €/h")
    check("A5 com label 'Gehalt' + /h -> 17 hour",
          bool(out) and out["min"] == 17 and out["period"] == "hour")
    out = _sal(description="Vergütung 21 €/h")
    check("A6 SEM label: marker /h com moeda basta -> 21 hour",
          bool(out) and out["min"] == 21 and out["period"] == "hour")
    check("A7 'h' SOLTO não é marcador ('Bereits 3 h Erfahrung. Gehalt: 2000 €' "
          "-> month, não hour)",
          (_sal(description="Bereits 3 h Erfahrung. Gehalt: 2000 €") or {})
          .get("period") == "month")
    check("A8 'X Euro/Stunde' com 'Euro' por extenso: post group captura "
          "'Eur' e deixa 'o/Stunde' -> month (comportamento PRÉ-EXISTENTE "
          "main=branch, 0 ocorrências no dataset 409; alternância €|eur|euro "
          "é ORDERED e casa 'eur' primeiro — ver docs/fase_j §limitações)",
          (_sal(description="Vergütung: 12 Euro/Stunde") or {})
          .get("period") == "month")
    check("A9 não-regressão '€/Stunde' -> hour",
          (_sal(description="Gehalt: 12 €/Stunde") or {}).get("period") == "hour")
    check("A10 não-regressão 'per hour' -> hour",
          (_sal(description="Salary: €21 per hour") or {}).get("period") == "hour")

    # ------------------------------------------------------------------ B
    print("== B: 12 Monate adversarial ==")
    check("B1 '12 Monate befristet' -> None (FP morto)",
          _sal(description="Die Stelle ist auf 12 Monate befristet.") is None)
    check("B2 'für 12 Monate' -> None",
          _sal(description="befristet für 12 Monate.") is None)
    check("B3 '12 Monate Praktikum' -> None",
          _sal(description="Es ist ein 12 Monate Praktikum.") is None)
    check("B4 Fraunhofer real: 'auf 12 Monate befristet. Die Vergütung "
          "richtet sich…' -> None (label é da frase SEGUINTE)",
          _sal(description="Die Stelle ist zunächst i. d. R. auf 12 Monate "
                            "befristet. Die Vergütung richtet sich nach der "
                            "Gesamtbetriebsvereinbarung.") is None)
    check("B5 '12 Monatsgehälter' SEM contexto monetário -> None",
          _sal(description="12 Monatsgehälter pro Jahr, Urlaub und Weihnachtsgeld "
                            "inklusive.") is None)
    out = _sal(description="Gehalt: 12 Monatsgehälter à 1.500 €")
    check("B6 com contexto monetário real -> valor REAL 1500 (não 12)",
          bool(out) and out["min"] == 1500 and out["period"] == "month")
    check("B7 '12 Monatsgehälter à 1.500 €' puro (sem label) -> None "
          "(moeda sozinha não passa o gate)",
          _sal(description="12 Monatsgehälter à 1.500 €") is None)

    # ------------------------------------------------------------------ C
    print("== C: durações (anti-regressão do \\b) ==")
    check("C1 'Dauer: 6 Monate' sozinho -> None",
          _sal(description="Dauer: 6 Monate") is None)
    check("C2 'Duration 6 months' -> None",
          _sal(description="Duration: 6 months") is None)
    check("C3 'befristet auf 2 Jahre' -> None",
          _sal(description="Die Stelle ist befristet auf 2 Jahre.") is None)
    out = _sal(description="Gehalt: 2.117 €/Monat")
    check("C4 'Gehalt: 2.117 €/Monat' -> 2117 month (a barra não casa o "
          "period group — igual antes)",
          bool(out) and out["min"] == 2117 and out["period"] == "month")
    out = _sal(description="Salary: EUR 2,000 per month")
    check("C5 'Salary: EUR 2,000 per month' -> 2000 month",
          bool(out) and out["min"] == 2000 and out["period"] == "month")
    out = _sal(description="Vergütung 1500 € monatlich")
    check("C6 'Vergütung 1500 € monatlich' -> 1500 month (default)",
          bool(out) and out["min"] == 1500 and out["period"] == "month")

    # ------------------------------------------------------------------ D
    print("== D: year ==")
    out = _sal(description="Gross annual salary (full-time): 40.000 - 46.000 €")
    check("D1 BASF EN: 'Gross annual salary … 40.000 - 46.000 €' -> "
          "40000-46000 year (era month)",
          bool(out) and out["min"] == 40000 and out["max"] == 46000
          and out["period"] == "year")
    out = _sal(description="Bruttojahresgehalt (Vollzeit): 35.000 - 39.000 €")
    check("D2 BASF DE: 'Bruttojahresgehalt … 35.000 - 39.000 €' -> "
          "35000-39000 year (era None)",
          bool(out) and out["min"] == 35000 and out["max"] == 39000
          and out["period"] == "year")
    out = _sal(description="Salary: €50,000/year")
    check("D3 '€50,000/year' -> 50000 year (limitação G fechada)",
          bool(out) and out["min"] == 50000 and out["period"] == "year")
    out = _sal(description="Jahresgehalt: 60.000 €")
    check("D4 'Jahresgehalt: 60.000 €' -> 60000 year",
          bool(out) and out["min"] == 60000 and out["period"] == "year")
    out = _sal(description="Vergütung: 50.000 € pro Jahr")
    check("D5 '50.000 € pro Jahr' (sufixo) -> 50000 year",
          bool(out) and out["min"] == 50000 and out["period"] == "year")
    out = _sal(description="Gehalt: pro Jahr 50.000 €")
    check("D6 'pro Jahr' ANTES do valor: mantém month default (limitação "
          "documentada — marcador só casa como SUFIXO)",
          bool(out) and out["min"] == 50000 and out["period"] == "month")
    out = _sal(description="Annual compensation: 45,000 €")
    check("D7 'Annual compensation' (família EN completa) -> 45000 year",
          bool(out) and out["min"] == 45000 and out["period"] == "year")

    # ------------------------------------------------------------------ E
    print("== E: hourly composto ==")
    out = _sal(description="Der Bruttostundenlohn für Werkstudierende beträgt "
                           "aktuell 18,33 €.")
    check("E1 VW real: 'Bruttostundenlohn … 18,33 €' (label a 53 chars) -> "
          "18.33 hour (era None)",
          bool(out) and out["min"] == 18.33 and out["period"] == "hour")
    out = _sal(description="Stundenlohn: 21 €")
    check("E2 'Stundenlohn: 21 €' -> 21 hour",
          bool(out) and out["min"] == 21 and out["period"] == "hour")
    out = _sal(description="Neben unseren vielfältigen Benefits erwartet Dich "
                           "ein Stundenlohn von 21 Euro plus Weihnachts- und "
                           "Urlaubsgeld.")
    check("E3 covestro (não-regressão Fase F): 'Stundenlohn von 21 Euro' -> "
          "21 hour",
          bool(out) and out["min"] == 21 and out["period"] == "hour")
    check("E4 'Bruttostundenvergütung' composto -> hour",
          (_sal(description="Die Bruttostundenvergütung beträgt 13 €.") or {})
          .get("period") == "hour")

    # ------------------------------------------------------------------ F
    print("== F: WA condicionais (os 7 da spec) ==")
    check("F1 'must already have a valid work permit' -> existing_required",
          wa("must already have a valid work permit") == "existing_required")
    check("F2 Bosch real: '…and if indicated a valid work and residence "
          "permit.' NÃO é existing_required (→ unclear)",
          wa("Please attach your CV, transcript of records, enrollment "
             "certificate, examination regulations and if indicated a valid "
             "work and residence permit.") != "existing_required"
          and wa("Please attach your CV, transcript of records, enrollment "
                 "certificate, examination regulations and if indicated a "
                 "valid work and residence permit.") == "unclear")
    check("F3 continental real: 'Falls erforderlich, zusätzlich: Gültiger "
          "Aufenthaltstitel' NÃO é existing_required (→ unclear)",
          wa("Falls erforderlich, zusätzlich: Gültiger Aufenthaltstitel "
             "Arbeitsgenehmigung inkl. Zusatzblatt") != "existing_required"
          and wa("Falls erforderlich, zusätzlich: Gültiger Aufenthaltstitel "
                 "Arbeitsgenehmigung inkl. Zusatzblatt") == "unclear")
    check("F4 condicional genérica -> unclear",
          wa("Visa questions can be discussed during the interview") == "unclear")
    check("F5 'We support you with the visa process' -> support",
          wa("We support you with the visa process") == "support")
    check("F6 relocation ≠ imigração: 'Relocation assistance provided' NÃO "
          "é support",
          wa("Relocation assistance provided") != "support")
    check("F7 intento do caso 7: existing vence contexto de relocation em "
          "SENTENÇA SEPARADA",
          wa("We provide relocation assistance. Applicants must already "
             "have a valid work permit.") == "existing_required")
    # Nota F7: o LITERAL "valid work permit required, relocation assistance "
    # provided" (mesma sentença, vírgula) casa _WA_SUPPORT pela janela
    # bidirecional 25 chars ANTES de chegar ao caminho existing —
    # comportamento PRÉ-EXISTENTE da main (não introduzido pela Fase J),
    # registrado como backlog (docs/fase_j_enrichment_quality.md).
    check("F8 não-regressão Fase F: 'sowie ggf. eine gültige Arbeits- und "
          "Aufenthaltserlaubnis' NÃO é existing_required",
          wa("Please attach your Prüfungsordnung sowie ggf. eine gültige "
             "Arbeits- und Aufenthaltserlaubnis bei.") != "existing_required")
    check("F9 não-regressão: 'if applicable' segue suprimindo",
          wa("Please attach your CV and, if applicable, a valid work permit.")
          != "existing_required")
    check("F10 não-regressão: condicional em SENTENÇA ANTERIOR não suprime "
          "existing real",
          wa("ggf. werden Reisen benötigt. Eine gültige Arbeitserlaubnis "
             "ist erforderlich.") == "existing_required")
    check("F11 não é regra simplista: condicional SEM tema WA -> "
          "not_mentioned",
          wa("if indicated, more details will follow.") == "not_mentioned")
    check("F12 falls+erforderlich em sentença anterior não suprime: "
          "'Falls erforderlich, reisen. Gültige Arbeitserlaubnis "
          "erforderlich.' -> existing_required",
          wa("Falls erforderlich, wird gereist. Gültige Arbeitserlaubnis "
             "erforderlich.") == "existing_required")

    # ------------------------------------------------------------------ G
    print("== G: não-regressão geral ==")
    out = _sal(description="Flexible Zeiteinteilung €2268 Vergütung im Monat "
                           "für ein Vollzeit Praktikum")
    check("G1 roche €2268 (label forward NA MESMA sentença) -> 2268 month",
          bool(out) and out["min"] == 2268 and out["period"] == "month")
    out = _sal(description="Weitere Details zur Stelle Gehalt: 2.117 €/Monat "
                           "Beginn: ab November 2026")
    check("G2 STIHL 2.117 €/Monat -> 2117 month",
          bool(out) and out["min"] == 2117 and out["period"] == "month")
    out = _sal(description="Du erhältst ein attraktives Gehalt (2.570 Euro "
                           "brutto pro Monat) und einen Fahrtkostenzuschuss")
    check("G3 Tchibo 2.570 Euro pro Monat -> 2570 month",
          bool(out) and out["min"] == 2570 and out["period"] == "month")
    out = _sal(description="Vergütung: 1500€ I Abteilung: TBX")
    check("G4 MAHLE 1500€ -> 1500 month",
          bool(out) and out["min"] == 1500 and out["period"] == "month")
    out = _sal(description="Vergütung: 17,80 €/Stunde und Gehalt danach "
                           "2.117 €/Monat.")
    check("G5 VW 17,80 €/Stunde (Fase G) -> 17.8 hour",
          bool(out) and out["min"] == 17.8 and out["period"] == "hour")
    out = _sal_raw(raw={"salary_min": 1400, "salary_max": 1500,
                        "salary_currency": "EUR", "salary_period": None},
                   description="")
    check("G6 CURRENTA estruturado (raw recruitee) inalterado: 1400-1500, "
          "period=None",
          bool(out) and out["min"] == 1400 and out["max"] == 1500
          and out["period"] is None)
    j = {"title": "", "description": "Gehalt: 2.117 €/Monat und "
                                     "Vergütung 18,33 €/h."}
    check("G7 determinismo (100x)",
          all(oi.job_salary(j) == oi.job_salary(j) for _ in range(100)))
    check("G8 determinismo WA (100x)",
          len({wa("Falls erforderlich, zusätzlich: Gültiger Aufenthaltstitel")
               for _ in range(100)}) == 1)
    out = _sal_raw(raw={"salary_min": 0, "salary_max": 0},
                   description="Gehalt: 2.500 €/Monat")
    check("G9 raw com placeholder 0 NÃO vence o caminho textual (softgarden "
          "— regra pré-existente)",
          bool(out) and out["min"] == 2500 and out["period"] == "month")

    # ------------------------------------------------------------------ H
    print("== H: adversarial \\w*gehalt ==")
    check("H1 'Gehaltsvorstellung: 2.500 €' NÃO é salário (sufixo 's' quebra "
          "\\b final)",
          _sal(description="Gehaltsvorstellung: 2.500 €") is None)
    out = _sal(description="Monatsgehalt: 2.500 €")
    check("H2 'Monatsgehalt: 2.500 €' -> 2500 month (composto casa)",
          bool(out) and out["min"] == 2500 and out["period"] == "month")
    check("H3 'Gehälter' não casa (ä; documentado) e não quebra nada: "
          "'Gehälter werden überwiesen. Dauer: 6 Monate' -> None",
          _sal(description="Gehälter werden überwiesen. Dauer: 6 Monate") is None)
    check("H4 'Gehaltsangabe: 40.000 €' NÃO é label (sufixo)",
          _sal(description="Gehaltsangabe: 40.000 €") is None)

    fails = len(_FAILS)
    print(f"\n{'=' * 20} test_fasej {'OK' if not fails else 'FAIL'} {'=' * 20}")
    print(f"fails: {fails}")
    if fails:
        for f in _FAILS:
            print(f"  FAIL: {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
