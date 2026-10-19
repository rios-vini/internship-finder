"""Testes da fase F63 — Salário: heurística anual×mensal (display-only).

Bug real (registro do dono 10/2026): LexisNexis R119275 (Workday,
"Intern Data Engineering", Karlsruhe) exibiu "€17.200–€28.700/mês" na
página pública — o range ANUAL foi parseado como mensal. Verbatim do
anúncio (fim da description Workday): "Primary Location Base Pay
Range: Germany - Karlsruhe €17,200 - €28,700." — sem "/year", "p.a.",
"Jährlich" ou QUALQUER unidade (medido: nenhuma dessas marcas existe
no record integral; nem "month"/"Monat"). A magnitude (€17.200/mês =
€206k/ano) é anual por plausibilidade; mensal de estágio no dataset:
€300–4.000.

Causas (as DUAS camadas, varredura do universo data/jobs.json de
19/10/2026 — 108.450 records, 6.458 com job_salary):

1. Default Fase 7: cláusula sem período resolvida como "month" AFIRMA
   unidade que o anúncio não declara (LexisNexis, Citi — os implausíveis
   do eligible do dia);
2. "per year" COLADO ignorado: o period group captura " per year", mas
   a resolução comparava o texto BRUTO contra ("jahr","year") e o
   prefixo "per" fazia falhar → default "month" (312 records do
   universo; top ofensores Nestlé RMK "260,000.00 per year").

Regra F63 (spec; display-only — NUNCA score, NUNCA estimativa):

(a) contexto anual EXPLÍCITO + bound > €6.000 → dividir por 12 com
    provenance "anual convertido p/ mensal";
(b) sem contexto anual + bound > €6.000 → period=None + provenance
    "unidade não confirmada" (o valor citado permanece; a unidade
    nunca é afirmada — decidido contra "não exibir" porque
    job_salary=None dispararia a estimativa F29 no lugar do valor
    citado: pior troca).

Intocados por construção: plausíveis (≤ €6.000), horários e anuais
pequenos (novemcore €900–1.200/year, anomalia de FONTE documentada —
exibida como "/ano").

Fixtures VERBATIM de records reais (eligible/jobs.json de 19/10/2026):
LexisNexis R119275 (description integral, 3.941 chars), Citi Placement
Analyst, Nestlé Senior Director "per year", BASF €850/month, covestro
€2.270, Lidl €1.300, averydennison €550, novemcore raw YEAR (strings).
Nota: os contra-casos "adidas/Würth €850–2.500" citados na spec NÃO
existem mais no dataset (0 records com salary no universo de 108.450 —
churn); os contra-casos equivalentes REAIS de hoje cobrem €550–2.270
(documentado no relatório).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

from internship_finder import opportunity_intel as oi       # noqa: E402
from internship_finder import salary_benchmark as sb       # noqa: E402
import minimal_page as mp                                   # noqa: E402

_FAILS: list[str] = []


def check(desc: str, cond: bool) -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {desc}")
    if not cond:
        _FAILS.append(desc)


# --- Fixture A: LexisNexis R119275 VERBATIM (eligible 19/10/2026) ----------
# Record real: 'LexisNexis® Risk Solutions|sf_dataset:workday:R119275',
# "Intern Data Engineering", Karlsruhe. Description INTEGRAL e raw
# estruturado com os campos salary_* como strings VAZIAS (o Workday do
# dataset publica sem valores estruturados — o parse é todo textual).
LEXISNEXIS_TITLE = "Intern Data Engineering"
LEXISNEXIS_RAW = {"salary_min": "", "salary_max": "",
                  "salary_period": "", "salary_currency": ""}
LEXISNEXIS_DESCRIPTION = "About ICIS ICIS is a global leader in commodity intelligence, providing trusted data, analytics and expert insights across the global chemical and energy markets. We help organisations navigate complex and rapidly changing markets, enabling smarter, faster and more confident business decisions. Trusted by more than 6,000 organisations in over 100 countries, ICIS combines independent pricing data, market intelligence and deep industry expertise to help customers manage risk, identify opportunities and optimise their strategies. With a global team and a strong culture of curiosity, collaboration and innovation, ICIS is part of LexisNexis Risk Solutions, within RELX, a global provider of information-based analytics and decision tools About the Role As part of the Analytical Data Engineering team, you will contribute to the development of a modern data platform with a focus on: Data engineering and automation Data quality and validation Standardization and simplification of data workflows You will work closely with experienced data engineers and analysts to build and improve data pipelines, manage large datasets, and support the delivery of trusted, business-ready data products across the organization. Responsibilities: Develop and maintain data pipelines and automation solutions using our Analytical Data Engineering Platform and its reusable framework components Support data quality, validation, and testing initiatives to ensure trusted and business-ready data products Research, prototype, and evaluate AI-driven solutions that automate data engineering tasks and improve developer productivity Requirements: Programming experience is required in Python and SQL Knowledge of data engineering, data processing, data validation, and data quality concepts is an advantage Strong analytical and problem-solving skills with a proactive and collaborative mindset Strong communication and writing skills in English is a requirement Enjoys working in a team, takes initiatives Bachelor's or Master's degree in Data Science, Computer Science, Data Engineering, Software Engineering, or a related field We Offer: Mentorship and hands-on learning alongside experienced data engineers Opportunities to work with Python, SQL, cloud technologies, and AI-driven solutions Interactions with commodity teams (e.g. Power, Gas, LNG, Chemicals e.g.) Flexible working hours and a competitive internship salary A dynamic, international work environment where your ideas can make an impact Ownership of meaningful projects from day one Sounds like the right opportunity for you? We’d love to hear from you! Join ICIS and become part of an international team where your ideas, expertise and perspective can make a real difference. Apply today and take the next step in your career with us. Primary Location Base Pay Range: Germany - Karlsruhe €17,200 - €28,700. We know your well-being and happiness are key to a long and successful career. We are delighted to offer country specific benefits. Click here to access benefits specific to your location. We are committed to providing a fair and accessible hiring process. If you have a disability or other need that requires accommodation or adjustment, please let us know by completing our Applicant Request Support Form or please contact 1-855-833-5120. Criminals may pose as recruiters asking for money or personal information. We never request money or banking details from job applicants. Learn more about spotting and avoiding scams here . Please read our Candidate Privacy Policy . We are an equal opportunity employer: qualified applicants are considered for and treated during employment without regard to race, color, creed, religion, sex, national origin, citizenship status, disability status, protected veteran status, age, marital status, sexual orientation, gender identity, genetic information, or any other characteristic protected by law. USA Job Seekers: EEO Know Your Rights ."

CITI_VERBATIM = ("------------ Primary Location Full Time Salary Range: "
                 "€48,000.00 - €72,000.00 Salary shown is for full-time "
                 "positions and will be prorated for part-time hires based "
                 "on number of hours worked. The hourly rate corresponding "
                 "to the annual range is: $0.00 - $0.00 ----------")
NESTLE_VERBATIM = ("Salary: $240,000.00 to $260,000.00 per year Bonus "
                   "Eligibility: Yes The pay range provided is a good "
                   "faith estimate for the position at the t")


def _lexisnexis_job() -> dict:
    return {"title": LEXISNEXIS_TITLE, "description": LEXISNEXIS_DESCRIPTION,
            "raw": LEXISNEXIS_RAW}


def main() -> int:
    # ---------------------------------------------------------------- A
    print("== A: LexisNexis R119275 (o bug reportado) ==")
    sal = oi.job_salary(_lexisnexis_job())
    check("A1 verbatim R119275: cláusula €17,200 - €28,700 detectada, "
          "min/max INTOCADOS (o valor citado é evidência)",
          bool(sal) and sal["min"] == 17200.0 and sal["max"] == 28700.0
          and sal["text"] == "€17,200 - €28,700")
    check("A2 F63 ramo (b): period=None — 'month' NUNCA mais é afirmado "
          "para range implausível sem contexto anual (era o bug)",
          bool(sal) and sal["period"] is None)
    check("A3 provenance 'unidade não confirmada' presente",
          bool(sal) and sal.get("provenance") == "unidade não confirmada")
    check("A4 nenhuma marca anual no verbatim integral (MEDIDO): "
          "'/year', 'per year', 'p.a.', 'jährlich', 'annual', 'yearly', "
          "'pro jahr' ausentes — a suspeita é só magnitude",
          not any(m in LEXISNEXIS_DESCRIPTION.lower()
                  for m in ("/year", "per year", "p.a.", "jährlich",
                            "jaehrlich", "annual", "yearly", "pro jahr")))
    fmt = mp._fmt_salary(sal)
    check("A5 display público: '€17.200–€28.700 (unidade não confirmada)' "
          "— o sintoma reportado morre",
          fmt == "€17.200–€28.700 (unidade não confirmada)")
    check("A6 nenhum '/mês' no display do record",
          "/mês" not in fmt)

    # ---------------------------------------------------------------- B
    print("== B: Citi Placement Analyst (verbatim — 'Full Time Salary "
          "Range') ==")
    sal = oi.job_salary({"title": "Placement Analyst",
                         "description": CITI_VERBATIM})
    check("B1 Citi €48,000.00–€72,000.00: ramo (b) — period=None + flag "
          "(o 'annual range' real está ~90 chars além, fora da janela "
          "e após fim de sentença: contexto não-colado não é contexto)",
          bool(sal) and sal["min"] == 48000.0 and sal["max"] == 72000.0
          and sal["period"] is None
          and sal.get("provenance") == "unidade não confirmada")

    # ---------------------------------------------------------------- C
    print("== C: anual explícito converte (ramo a) ==")
    sal = oi.job_salary({"title": "", "description":
                         "Gross annual salary (full-time): 40.000 - 46.000 €"})
    check("C1 BASF EN anual 40–46k -> 3333.33–3833.33/month + provenance",
          bool(sal) and abs(sal["min"] - 40000 / 12) < 1e-9
          and abs(sal["max"] - 46000 / 12) < 1e-9
          and sal["period"] == "month"
          and sal.get("provenance") == "anual convertido p/ mensal")
    sal = oi.job_salary({"title": "", "description": NESTLE_VERBATIM})
    check("C2 Nestlé 'per year' colado (fix rsplit na resolução) -> "
          "21666.67/month + provenance (era month — 312 records no "
          "universo)",
          bool(sal) and abs(sal["min"] - 260000 / 12) < 1e-9
          and sal["period"] == "month"
          and sal.get("provenance") == "anual convertido p/ mensal")
    sal = oi.job_salary({"title": "", "description":
                         "Jährliche Vergütung: 50.000 €"})
    check("C3 'Jährliche Vergütung' (extensão F63 do label anual; 165 "
          "records no universo) -> 4166.67/month provenance",
          bool(sal) and abs(sal["min"] - 50000 / 12) < 1e-9
          and sal["period"] == "month"
          and sal.get("provenance") == "anual convertido p/ mensal")
    sal = oi.job_salary({"title": "", "description": "", "raw": {
        "salary_min": 40000.0, "salary_max": 46000.0,
        "salary_period": "YEAR", "salary_currency": "EUR"}})
    check("C4 estruturado YEAR 40–46k -> converte p/ mensal com "
          "provenance (o mesmo ramo (a) no caminho estruturado)",
          bool(sal) and abs(sal["min"] - 40000 / 12) < 1e-9
          and abs(sal["max"] - 46000 / 12) < 1e-9
          and sal["period"] == "month"
          and sal.get("provenance") == "anual convertido p/ mensal")

    # ---------------------------------------------------------------- D
    print("== D: contra-casos intocados (plausíveis ≤6k) ==")
    sal = oi.job_salary({"title": "", "description":
                         "We compensate your internship with 850 € per month."})
    check("D1 BASF 850 €/month verbatim (o contra-caso €850 da spec) -> "
          "850 month SEM provenance",
          bool(sal) and sal["min"] == 850.0 and sal["period"] == "month"
          and "provenance" not in sal)
    sal = oi.job_salary({"title": "", "description":
                         "attraktive Vergütung von 2.270 € brutto/Monat"})
    check("D2 covestro 2.270 € verbatim -> month SEM provenance",
          bool(sal) and sal["min"] == 2270.0 and sal["period"] == "month"
          and "provenance" not in sal)
    sal = oi.job_salary({"title": "", "description":
                         "Faires Praktikantengehalt 1.300 €/Monat "
                         "(beim Pflichtpraktikum)"})
    check("D3 Lidl 1.300 € verbatim -> month SEM provenance",
          bool(sal) and sal["min"] == 1300.0 and sal["period"] == "month"
          and "provenance" not in sal)
    sal = oi.job_salary({"title": "", "description":
                         "Competitive Compensation: A monthly allowance of "
                         "€550 (based on full-time hours)"})
    check("D4 averydennison €550 verbatim (label 'Compensation' incluído "
          "— é o que valida a cláusula no record real) -> 550 month SEM "
          "provenance",
          bool(sal) and sal["min"] == 550.0 and sal["period"] == "month"
          and "provenance" not in sal)
    sal = oi.job_salary({"title": "", "description": "", "raw": {
        "salary_min": 500.0, "salary_max": 800.0,
        "salary_period": None, "salary_currency": "EUR"}})
    check("D5 recruitee estruturado 500–800 (period ausente) -> None SEM "
          "provenance (plausível não dispara nada)",
          bool(sal) and (sal["min"], sal["max"]) == (500.0, 800.0)
          and sal["period"] is None and "provenance" not in sal)
    sal = oi.job_salary({"title": "", "description": "", "raw": {
        "salary_min": "900.0", "salary_max": "1200.0",
        "salary_period": "YEAR", "salary_currency": "EUR"}})
    check("D6 novemcore raw VERBATIM (strings '900.0'/'1200.0', YEAR): "
          "anual ≤6k INTOCADO — 900–1200/year, sem conversão/provenance "
          "(anomalia de FONTE documentada no relatório F63)",
          bool(sal) and (sal["min"], sal["max"]) == (900.0, 1200.0)
          and sal["period"] == "year" and "provenance" not in sal)
    sal = oi.job_salary({"title": "", "description": "Vergütung: 18,33 €/h"})
    check("D7 hourly 18,33 € intocado (a heurística é anual×mensal)",
          bool(sal) and sal["min"] == 18.33 and sal["period"] == "hour"
          and "provenance" not in sal)
    sal = oi.job_salary({"title": "", "description": "Jahresgehalt: 6.000 €"})
    check("D8a boundary: 6.000/year (≤6k) -> year INTOCADO",
          bool(sal) and sal["min"] == 6000.0 and sal["period"] == "year"
          and "provenance" not in sal)
    sal = oi.job_salary({"title": "", "description": "Jahresgehalt: 6.001 €"})
    check("D8b boundary: 6.001/year (>6k) -> 500.08/month provenance",
          bool(sal) and abs(sal["min"] - 6001 / 12) < 1e-9
          and sal["period"] == "month"
          and sal.get("provenance") == "anual convertido p/ mensal")
    sal = oi.job_salary({"title": "", "description": "Gehalt: €6,000/month"})
    check("D8c boundary: 6.000/month (≤6k) -> month INTOCADO",
          bool(sal) and sal["min"] == 6000.0 and sal["period"] == "month"
          and "provenance" not in sal)

    # ---------------------------------------------------------------- E
    print("== E: displays e gates ==")
    sal = oi.job_salary({"title": "", "description":
                         "Gross annual salary (full-time): 40.000 - 46.000 €"})
    check("E1 _fmt_salary anual convertido: "
          "'€3.333–€3.833/mês (anual convertido p/ mensal)'",
          mp._fmt_salary(sal)
          == "€3.333–€3.833/mês (anual convertido p/ mensal)")
    check("E2 _fmt_salary plausível: '€850/mês' (regressão zero)",
          mp._fmt_salary({"min": 850.0, "max": 850.0, "period": "month"})
          == "€850/mês")
    check("E3 _fmt_salary anual pequeno: '€900–€1.200/ano' (novemcore)",
          mp._fmt_salary({"min": 900.0, "max": 1200.0, "period": "year"})
          == "€900–€1.200/ano")
    check("E4 _fmt_salary None/{} -> '' (contrato preservado)",
          mp._fmt_salary(None) == "" and mp._fmt_salary({}) == "")
    job = _lexisnexis_job()
    check("E5 gate F29 A5: job_salary com flag continua PRESENTE -> "
          "market_salary_estimate None (a flag NÃO abre espaço para "
          "estimativa no lugar do valor citado)",
          sb.market_salary_estimate(job, None) is None)
    check("E6 badge F29 4b: salário citado (com flag) -> SEM badge "
          "'remuneração não citada'",
          mp.salary_unspecified_flag(job) == "")

    # ---------------------------------------------------------------- F
    print("== F: determinismo e invariantes ==")
    j = _lexisnexis_job()
    first = oi.job_salary(j)
    check("F1 determinismo ×100 (LexisNexis ramo b)",
          all(oi.job_salary(j) == first for _ in range(100)))
    j2 = {"title": "", "description":
          "Gross annual salary: 40.000 - 46.000 €"}
    first2 = oi.job_salary(j2)
    check("F2 determinismo ×100 (anual convertido ramo a)",
          all(oi.job_salary(j2) == first2 for _ in range(100)))
    check("F3 re-aplicação da heurística não degenera: 3333.33 é "
          "plausível -> 2ª passada intocada",
          oi._apply_salary_plausibility(dict(first2)) == first2)
    sal_b = dict(first)
    twice = oi._apply_salary_plausibility(
        oi._apply_salary_plausibility(sal_b))
    check("F4 ramo (b) estável sob re-aplicação (period=None + flag "
          "permanecem)",
          twice.get("period") is None
          and twice.get("provenance") == "unidade não confirmada")
    check("F5 heurística NUNCA inventa período: resultado com flag não "
          "afirma 'month' nem 'year'",
          first["period"] is None
          and first2["period"] == "month"
          and first2.get("provenance") == "anual convertido p/ mensal")

    print()
    n = len(_FAILS)
    print("F63: %s" % ("TUDO OK" if not n else "%d FALHA(S)" % n))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
