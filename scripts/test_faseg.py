#!/usr/bin/env python3
"""Fase G — Salary Decimal Parsing Fix (testes offline, 100% determinísticos).

Corrige o parsing de separadores decimais em valores monetários textuais
(sem reescrita do parser, sem LLM): o ``_MONEY_CLAUSE`` captura decimais
alemães/internacionais inteiros ("17,50", "18,06", "1.400,50", "17.50") em
vez de truncar ("€17,50" -> 17) ou produzir salários-lixo via fragmento
("17,50 Euro" -> 50 €/mês). Milhares ("1,400", "2.117", "50,000") NUNCA são
confundidos com decimais; formatos existentes (mensal/anual/hourly, ranges,
gate moeda+rotulo) permanecem idênticos; eligibility/ranking/score não são
tocados (o ranking não consome salary).

Grupos (spec da fase):

A. Decimal alemão puro: 17,50 / 18,06 / 16,75 / 21,00 (hourly)
B. Alemão completo (milhar + decimal): 1.400,50
C. Decimal internacional: 17.50
D. Milhares: 1,400 / 50,000 (e 50,000.00)
E. Formatos existentes: mensal, anual, hourly inteiro, ranges, recruitee
F. Inválidos/ambíguos: sem gate, datas, receitas, fragmentos — nada novo
G. _to_number unitário + determinismo

Padrão da suíte standalone do projeto: ``check(desc, cond)`` com exit 1 se
qualquer falha; roda 100% offline (dataset real é opcional e read-only).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder import opportunity_intel as oi  # noqa: E402

_FAILS: list[str] = []


def check(desc: str, cond: bool) -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {desc}")
    if not cond:
        _FAILS.append(desc)


def _sal(title: str = "", description: str = "") -> dict | None:
    return oi.job_salary({"title": title, "description": description})


def _sal_raw(raw: dict, description: str = "") -> dict | None:
    return oi.job_salary({"title": "", "description": description, "raw": raw})


def main() -> int:
    # ------------------------------------------------------------------ A
    print("== A: decimal alemão puro ==")
    out = _sal(description="Gehalt: €17,50")
    check("A1 '€17,50' -> 17.50 (antes: 17.0)",
          bool(out) and out["min"] == 17.5 and out["max"] == 17.5)
    check("A1b text preserva o trecho exato da fonte",
          bool(out) and out["text"] == "€17,50")
    out = _sal(description="Gehalt: €18,06")
    check("A2 '€18,06' -> 18.06 (antes: 18.0)", bool(out) and out["min"] == 18.06)
    out = _sal(description="Gehalt: €16,75")
    check("A3 '€16,75' -> 16.75 (antes: 16.0)", bool(out) and out["min"] == 16.75)
    out = _sal(description="Gehalt: 17,50 Euro")
    check("A4 '17,50 Euro' -> 17.50 (antes: 50.0 — fragmento-lixo)",
          bool(out) and out["min"] == 17.5 and out["max"] == 17.5)
    out = _sal(description="Gehalt: 17,50 €")
    check("A5 '17,50 €' -> 17.50 (antes: 50.0 — fragmento-lixo)",
          bool(out) and out["min"] == 17.5)
    out = _sal(description="Gehalt: 17,80 €/Monat")
    check("A6 '17,80 €/Monat' -> 17.80 month", bool(out)
          and out["min"] == 17.8 and out["period"] == "month")
    out = _sal(description="Stundenlohn von 21,00 Euro")
    check("A7 'Stundenlohn von 21,00 Euro' -> 21.00 hour (antes: None)",
          bool(out) and out["min"] == 21.0 and out["period"] == "hour")
    out = _sal(description="Stundenlohn von 17,80 €")
    check("A8 'Stundenlohn von 17,80 €' -> 17.80 hour (antes: 80.0 month)",
          bool(out) and out["min"] == 17.8 and out["period"] == "hour")
    out = _sal(description="Vergütung: 17,80 €/Stunde")
    check("A9 '17,80 €/Stunde' -> 17.80 hour (antes: 80.0 month — real VW)",
          bool(out) and out["min"] == 17.8 and out["period"] == "hour")
    out = _sal(description="Compensation: €16,75 per hour")
    check("A10 '€16,75 per hour' -> 16.75 hour (real teampicnic, era €16)",
          bool(out) and out["min"] == 16.75 and out["period"] == "hour")
    out = _sal(description="hourly rate: €18,06/hour")
    check("A11 '€18,06/hour' -> 18.06 hour (real Fraunhofer, era €18)",
          bool(out) and out["min"] == 18.06 and out["period"] == "hour")

    # ------------------------------------------------------------------ B
    print("== B: alemão completo (milhar + decimal) ==")
    out = _sal(description="Gehalt: €1.400,50")
    check("B1 '€1.400,50' -> 1400.50 (antes: 1400.0)",
          bool(out) and out["min"] == 1400.5)
    out = _sal(description="Gehalt: 2.410,00 €/Monat")
    check("B2 '2.410,00 €/Monat' -> 2410.00 month (antes: None — real teampicnic)",
          bool(out) and out["min"] == 2410.0 and out["period"] == "month")
    out = _sal(description="Gehalt: 17.500,50 €")
    check("B3 '17.500,50 €' -> 17500.50 (antes: 50.0 — fragmento-lixo)",
          bool(out) and out["min"] == 17500.5)
    out = _sal(description="Gehalt: 1.000,00 €/Monat für ein Pflichtpraktikum")
    check("B4 '1.000,00 €/Monat' (2ª cláusula do anúncio teampicnic) -> 1000.00",
          bool(out) and out["min"] == 1000.0 and out["period"] == "month")

    # ------------------------------------------------------------------ C
    print("== C: decimal internacional ==")
    out = _sal(description="Gehalt: €17.50")
    check("C1 '€17.50' -> 17.50 month (antes: 17.0)",
          bool(out) and out["min"] == 17.5 and out["period"] == "month")
    out = _sal(description="Vergütung: 17.50 €/Stunde")
    check("C2 '17.50 €/Stunde' -> 17.50 hour",
          bool(out) and out["min"] == 17.5 and out["period"] == "hour")
    out = _sal(description="hourly wage of €17.50")
    check("C3 'hourly wage of €17.50' -> 17.50 hour (real VW, era 17.0)",
          bool(out) and out["min"] == 17.5 and out["period"] == "hour")

    # ------------------------------------------------------------------ D
    print("== D: milhares nunca são decimais ==")
    out = _sal(description="Gehalt: €1,400")
    check("D1 '€1,400' -> 1400 month (igual antes)", bool(out)
          and out["min"] == 1400.0 and out["period"] == "month")
    out = _sal(description="Gehalt: €1,400/month")
    check("D2 '€1,400/month' -> 1400 (igual antes)", bool(out) and out["min"] == 1400.0)
    out = _sal(description="Gehalt: €50,000/year")
    check("D3 '€50,000/year' -> 50000 (igual antes; period=month pré-existente "
          "documentado como limitação — period group não captura '/year')",
          bool(out) and out["min"] == 50000.0)
    out = _sal(description="Gehalt: €50,000.00/year")
    check("D4 '€50,000.00/year' -> 50000.00 (antes: 50000 — decimal .00 agora "
          "capturado, mesmo valor real)", bool(out) and out["min"] == 50000.0)
    out = _sal(description="Gehalt: 2.117 €/Monat")
    check("D5 '2.117 €/Monat' -> 2117 (igual antes)", bool(out)
          and out["min"] == 2117.0 and out["period"] == "month")
    out = _sal(description="Gehalt: 2117 €/Monat")
    check("D6 '2117 €/Monat' (sem milhar) -> 2117 (regressão 1ª-alternativa "
          "evitada: nunca 211)", bool(out) and out["min"] == 2117.0)

    # ------------------------------------------------------------------ E
    print("== E: formatos existentes intactos ==")
    out = _sal(description="Salary: EUR 2,000 per month")
    check("E1 'EUR 2,000 per month' -> 2000 month (igual antes)", bool(out)
          and out["min"] == 2000.0 and out["period"] == "month")
    out = _sal(description="Vergütung: 1.500 € - 1.800 € im Monat")
    check("E2 range '1.500 € - 1.800 €' -> 1500–1800 month (igual antes)",
          bool(out) and (out["min"], out["max"]) == (1500.0, 1800.0))
    out = _sal(description="Vergütung: €1.500–€1.800 im Monat")
    check("E3 range compacto '€1.500–€1.800' -> 1500–1800 (igual antes)",
          bool(out) and (out["min"], out["max"]) == (1500.0, 1800.0))
    out = _sal(description="Gehalt: €3,000 – €3,500 / month")
    check("E4 range EN '€3,000 – €3,500' -> 3000–3500 (igual antes)",
          bool(out) and (out["min"], out["max"]) == (3000.0, 3500.0))
    out = _sal(description="Gehalt: 17 Euro")
    check("E5 '17 Euro' -> 17.0 (igual antes)", bool(out) and out["min"] == 17.0)
    out = _sal(title="Werkstudent:in Supply Chain",
               description="Neben unseren vielfältigen Benefits erwartet Dich ein "
                           "Stundenlohn von 21 Euro plus Weihnachts- und Urlaubsgeld.")
    check("E6 'Stundenlohn von 21 Euro' -> 21.0 hour (Fase F intacta)",
          bool(out) and out["min"] == 21.0 and out["period"] == "hour")
    out = _sal(description="Vergütung: 18 €/Stunde")
    check("E7 '18 €/Stunde' -> 18.0 hour (Fase F intacta)",
          bool(out) and out["min"] == 18.0 and out["period"] == "hour")
    out = _sal(description="Compensation: €21 per hour")
    check("E8 '€21 per hour' -> 21.0 hour (Fase F intacta)",
          bool(out) and out["min"] == 21.0 and out["period"] == "hour")
    out = _sal_raw(raw={"salary_min": 1400.0, "salary_max": 1500.0,
                       "salary_currency": "EUR", "salary_period": None})
    check("E9 recruitee estruturado preserva min/max/currency (item 6 auditoria)",
          bool(out) and (out["min"], out["max"]) == (1400.0, 1500.0)
          and out["currency"] == "EUR" and out["period"] is None)
    out = _sal_raw(raw={"salary_min": 16480.0, "salary_max": 21203.0,
                        "salary_currency": "EUR", "salary_period": "MONTH"})
    check("E10 recruitee salary_period=MONTH -> month (nunca inferido)",
          bool(out) and out["period"] == "month")
    out = _sal_raw(raw={"salary_min": 0, "salary_max": -5,
                        "salary_currency": "EUR"},
                   description="Gehalt: 2.117 €/Monat")
    check("E11 raw inválido (<=0) cai no caminho textual -> 2117",
          bool(out) and out["min"] == 2117.0 and out["period"] == "month")

    # ------------------------------------------------------------------ F
    print("== F: inválidos/ambíguos continuam rejeitados ==")
    check("F1 '€17,50' sem rotulo/periodo -> None (gate intacto)",
          _sal(description="€17,50") is None)
    check("F2 'Gehalt: 17,50' sem moeda/periodo -> None (gate intacto)",
          _sal(description="Gehalt: 17,50") is None)
    check("F3 'Wir bieten 40 Stunden/Woche und 25 Urlaubstage' -> None",
          _sal(description="Wir bieten 40 Stunden/Woche und 25 Urlaubstage") is None)
    check("F4 'kein Geld hier' -> None", _sal(description="kein Geld hier") is None)
    check("F5 'Salary: not disclosed' -> None",
          _sal(description="Salary: not disclosed") is None)
    check("F6 'Der Kunde zahlt 21 Euro für die Stunde' -> None (gate da Fase F)",
          _sal(description="Der Kunde zahlt 21 Euro für die Stunde") is None)
    out = _sal(description="Bewerbung bis 15.09.2026, Gehalt 2.000 €")
    check("F7 data na janela não vira salário; o valor real segue 2000",
          bool(out) and out["min"] == 2000.0)
    check("F8 'Wir sind 7,9 Mrd. Euro schwer' -> None (receita, não salário)",
          _sal(description="Wir sind 7,9 Mrd. Euro schwer") is None)
    out = _sal(description="Unser Umsatz lag zuletzt bei 7,9 Mrd. Euro. "
                           "Bei uns erwartet Dich ein Stundenlohn von 17,80 €.")
    check("F9 7,9 Mrd. não é salário; o hourly real 17,80 é (contexto Knorr)",
          bool(out) and out["min"] == 17.8 and out["period"] == "hour")
    check("F10 '3,5 days of paid leave' não vira hourly (label ausente)",
          _sal(description="Transport reimbursement 3.5 days of paid leave") is None)
    out = _sal(description="Gehalt: 2.000,00 €/Monat")
    check("F11 '2.000,00 €/Monat' -> 2000.00 month (decimal final de milhar)",
          bool(out) and out["min"] == 2000.0 and out["period"] == "month")
    out = _sal(description="Gehalt: 1.099,99 €/Monat")
    check("F12 '1.099,99 €/Monat' -> 1099.99 month",
          bool(out) and abs(out["min"] - 1099.99) < 1e-9)

    # ------------------------------------------------------------------ G
    print("== G: _to_number unitário + determinismo ==")
    tn = oi._to_number
    check("G1 '2.117' -> 2117", tn("2.117") == 2117.0)
    check("G2 '2,000' -> 2000", tn("2,000") == 2000.0)
    check("G3 '1,400' -> 1400", tn("1,400") == 1400.0)
    check("G4 '50,000' -> 50000", tn("50,000") == 50000.0)
    check("G5 '17,50' -> 17.5", tn("17,50") == 17.5)
    check("G6 '17.50' -> 17.5 (antes: 1750.0)", tn("17.50") == 17.5)
    check("G7 '1,5' -> 1.5", tn("1,5") == 1.5)
    check("G8 '1.400,50' -> 1400.5", tn("1.400,50") == 1400.5)
    check("G9 '1,400.50' -> 1400.5 (convenção EN)", tn("1,400.50") == 1400.5)
    check("G10 '50,000.00' -> 50000.0 (antes: 50.0)", tn("50,000.00") == 50000.0)
    check("G11 '2.410,00' -> 2410.0", tn("2.410,00") == 2410.0)
    check("G12 '2117' -> 2117 (sem milhar)", tn("2117") == 2117.0)
    check("G13 '17' -> 17", tn("17") == 17.0)
    check("G14 '0'/'00' -> None (guard >0 preservado)",
          tn("0") is None and tn("00") is None)
    check("G15 '1.10.2026' -> None (data: conservador, antes: 1102026.0)",
          tn("1.10.2026") is None)
    check("G16 '15.09' (1 separador) -> 15.09 — decimal LEGÍTIMO pela regra 3; "
          "datas COMPLETAS têm 2 separadores (G15) e nunca passam o gate "
          "moeda+rotulo", tn("15.09") == 15.09)
    check("G16b '15.09.2026' (data completa) -> None", tn("15.09.2026") is None)
    j = {"title": "", "description": "Vergütung: 17,80 €/Stunde und Gehalt "
                                     "danach 2.117 €/Monat."}
    check("G17 determinismo (100x)",
          all(oi.job_salary(j) == oi.job_salary(j) for _ in range(100)))
    check("G18 decimal de 3+ dígitos continua MILHAR ('3,500' -> 3500, "
          "conservador)", tn("3,500") == 3500.0)

    fails = len(_FAILS)
    print(f"\n{'=' * 20} test_faseg {'OK' if not fails else 'FAIL'} {'=' * 20}")
    print(f"fails: {fails}")
    if fails:
        for f in _FAILS:
            print(f"  FAIL: {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
