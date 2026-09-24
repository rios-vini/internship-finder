"""Testes standalone — Itens 5–9 da auditoria pós-Fases 1–8 (qualidade de dados).

Cobre, de forma DETERMINISTICA e offline (sem rede, sem data/):

1. **Item 5 — Normalização HTML** (``app_intel.normalize_text``): os
   detectores textuais (``german_level``/``work_authorization``/
   ``english_evidence``) recebem texto com entidades ``&``/``&nbsp;``
   decodificadas, tags removidas e whitespace colapsado. Casos reais
   STIHL ("Fließend in Deutsch & Englisch") e teampicnic
   ("<strong>Fließende Deutsch</strong>- und Englischkenntnisse") saem
   de ``plus`` para ``required``. O texto ORIGINAL do Job nunca é
   alterado (a normalização é local ao detector).
2. **Item 6 — Salary mapping recruitee**: ``raw.salary_min``/``salary_max``/
   ``salary_currency``/``salary_period`` alimentam o modelo canônico de
   salary (``job_salary``) SEM campo paralelo; periodicidade ausente
   -> ``None`` (nunca inferida); caminho textual intacto; mecanismos
   sem conflito (estruturado vence quando ambos existem).
3. **Item 8 — Deadline textual estrito**: ``Bewerbungsfrist:
   DD.MM.YYYY`` (e ``Bewerbungsschluss``) -> ``deadline_kind ==
   "employer_textual"``; sem data/negação/ambíguo -> nada; datas
   passadas/futuras preservadas; ``g:expiration_date`` do
   SuccessFactors continua ``platform_sf`` (NUNCA employer);
   campo estruturado não-SF continua ``employer``.
4. **Item 9 — Aliases de cidade**: ``Munich`` -> chave canônica
   ``munchen``; ``München``/``Munchen`` idem; cidade canônica direta;
   desconhecida -> None no enriquecimento; o valor original da vaga
   (location/city exibidos) NUNCA muda.

Padrao dos demais scripts: ``[OK]``/``[FAIL]`` e termina com ``TUDO OK``
(exit 0) ou ``FALHAS:`` (exit != 0).

Uso:  .venv/bin/python scripts/test_audit2_quality.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder import app_intel, opportunity_intel as oi  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _job(**overrides) -> dict:
    base = {
        "id": "t:1", "source": "test:source", "title": "Vaga", "company": "TestCo",
        "location": "Berlin, DE", "country_iso": "de", "url": "https://example.org/j",
        "description": "", "collected_at": "2026-09-23T06:00:00Z",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Item 5 — normalização HTML antes dos detectores
# ---------------------------------------------------------------------------


def test_normalize_text() -> None:
    print("== item 5: normalize_text (unescape + strip tags + whitespace) ==")
    check("entidade & decodificada",
          app_intel.normalize_text("Deutsch & Englisch") == "Deutsch & Englisch")
    check("&nbsp; vira espaço e colapsa",
          app_intel.normalize_text("a&nbsp;&nbsp;b") == "a b")
    check("tag <strong> removida",
          "<strong>" not in app_intel.normalize_text(
              "<strong>Fließende Deutsch</strong>- und")
          and "Fließende Deutsch" in app_intel.normalize_text(
              "<strong>Fließende Deutsch</strong>- und"))
    check("whitespace colapsado",
          app_intel.normalize_text("  a   b  \n c ") == "a b c")
    check("texto sem HTML identico",
          app_intel.normalize_text("Gehalt: 2.117 €/Monat") == "Gehalt: 2.117 €/Monat")
    check("None -> ''", app_intel.normalize_text(None) == "")
    check("ZWSP removido",
          "\u200b" not in app_intel.normalize_text("Sehr\u200b gut"))


def test_german_html_cases() -> None:
    print("== item 5: casos STIHL/teampicnic (FN -> required) ==")
    cases = [
        ("Fließend in Deutsch & Englisch", "required"),   # STIHL real
        ("<strong>Fließende Deutsch</strong>- und Englischkenntnisse",
         "required"),                                          # teampicnic real
        ("Fließend in Deutsch & Englisch", "required"),      # idem decodificado
        ("Fließende Deutsch- und Englischkenntnisse", "required"),
    ]
    for text, expected in cases:
        got = app_intel.german_level(text)
        check(f"{expected} <- {text[:52]!r}",
              got is not None and got.level == expected)
    # anti-regressão: soft na janela continua preferred
    _soft_case = app_intel.german_level("English required, German is a plus")
    check("'English required, German is a plus' continua preferred",
          _soft_case is not None and _soft_case.level == "preferred")
    _soft_case2 = app_intel.german_level(
        "Sprichst fließend Englisch; Deutschkenntnisse sind ein Plus")
    check("'Sprichst fließend Englisch; Deutsch ist ein Plus' continua preferred",
          _soft_case2 is not None and _soft_case2.level == "preferred")
    # WA com entidades
    check("WA com &nbsp; (existing_required)",
          app_intel.work_authorization("You need a valid work&nbsp;permit")["state"]
          == "existing_required")
    # Job original NÃO é mutado
    original = "<strong>Fließende Deutsch</strong>- und Englischkenntnisse"
    job = _job(description=original)
    snapshot = copy.deepcopy(job)
    app_intel.german_level(f"{job['title']} {job['description']}")
    app_intel.work_authorization(job["description"])
    app_intel.english_evidence(job["description"])
    check("Job.description original preservado (sem mutação)",
          job == snapshot and job["description"] == original)


# ---------------------------------------------------------------------------
# Item 6 — salary mapping recruitee
# ---------------------------------------------------------------------------


def test_salary_structured() -> None:
    print("== item 6: raw.salary_min/max (recruitee) -> modelo canonico ==")
    job = _job(raw={"salary_min": 1400.0, "salary_max": 1500.0,
                    "salary_currency": "EUR", "salary_period": None})
    got = oi.job_salary(job)
    check("min/max preservados", got == {"min": 1400.0, "max": 1500.0,
                                        "period": None, "text": "EUR 1400–1500",
                                        "currency": "EUR"})
    check("periodicidade ausente -> None (nunca inferida)",
          got is not None and got["period"] is None)
    # payload com periodicidade
    job2 = _job(raw={"salary_min": 16480.0, "salary_max": 21203.0,
                     "salary_currency": "EUR", "salary_period": "MONTH"})
    got2 = oi.job_salary(job2)
    check("salary_period MONTH -> month (preservado)",
          got2 is not None and got2["period"] == "month"
          and got2["min"] == 16480.0 and got2["max"] == 21203.0)
    # moeda ausente no raw
    job3 = _job(raw={"salary_min": 10.0, "salary_max": 20.0})
    got3 = oi.job_salary(job3)
    check("moeda ausente -> currency None, min/max mantidos",
          got3 is not None and got3["currency"] is None
          and (got3["min"], got3["max"]) == (10.0, 20.0))
    # só min
    job4 = _job(raw={"salary_min": 500.0})
    got4 = oi.job_salary(job4)
    check("só min -> max = min", got4 is not None
          and got4["min"] == 500.0 and got4["max"] == 500.0)
    # valores inválidos/negativos/zero ignorados -> caminho textual
    job5 = _job(description="Gehalt: 2.117 €/Monat",
                raw={"salary_min": 0, "salary_max": -5, "salary_currency": "EUR"})
    got5 = oi.job_salary(job5)
    check("min/max inválidos (<=0) caem no caminho textual",
          got5 is not None and got5["min"] == 2117.0
          and got5["period"] == "month")
    # ausência dos campos: caminho textual original
    job6 = _job(description="Vergütung: 1.500 € - 1.800 € im Monat")
    got6 = oi.job_salary(job6)
    check("sem raw: salario textual continua funcionando",
          got6 is not None and (got6["min"], got6["max"], got6["period"])
          == (1500.0, 1800.0, "month"))
    check("sem raw e sem texto -> None", oi.job_salary(_job()) is None)
    # conflito: estruturado vence
    job7 = _job(description="Gehalt: 999 €/Monat",
                raw={"salary_min": 1400.0, "salary_max": 1500.0,
                     "salary_currency": "EUR", "salary_period": "MONTH"})
    got7 = oi.job_salary(job7)
    check("conflito: campo estruturado vence o texto",
          got7 is not None and (got7["min"], got7["max"]) == (1400.0, 1500.0))
    # determinismo
    check("determinismo (estruturado)", oi.job_salary(job) == oi.job_salary(job))


# ---------------------------------------------------------------------------
# Item 8 — deadline textual estrito
# ---------------------------------------------------------------------------


def test_textual_deadline() -> None:
    print("== item 8: Bewerbungsfrist estrito (employer_textual) ==")
    cases = [
        ("Bewerbungsfrist: 15.10.2026", "2026-10-15"),
        ("bewerbungsfrist:15.10.2026", "2026-10-15"),        # sem espaço
        ("BEWERBUNGSFRIST 15.10.2026", "2026-10-15"),        # caps, sem ':'
        ("Bewerbungsfrist - 15.10.2026", "2026-10-15"),      # hífen
        ("Bewerbungsschluss: 01.03.2027", "2027-03-01"),    # variante
        ("Bewerbungsfrist:", None),                          # sem data
        ("Es gibt keine Bewerbungsfrist.", None),            # negação
        ("keine Bewerbungsfrist. Sie bleibt ausgeschrieben", None),
        ("Bewerbungsfrist: 32.13.2026", None),               # inválida
        ("Bewerbungsfrist: 00.10.2026", None),               # inválida
        ("Bewerbungsfrist: 15.10.26", None),                 # ano 2 dígitos
        ("Wir freuen uns auf deine Bewerbung bis 15.10.2026", None),  # ambíguo
        ("", None), (None, None),
    ]
    for text, expected in cases:
        d = app_intel.textual_deadline(text)
        got = d.isoformat() if d else None
        check(f"{expected} <- {str(text)[:44]!r}", got == expected)

    # passado/futuro preservados (extração não altera o significado)
    _past = app_intel.textual_deadline("Bewerbungsfrist: 01.01.2020")
    check("data passada preservada",
          _past is not None and _past.isoformat() == "2020-01-01")
    _future = app_intel.textual_deadline("Bewerbungsfrist: 31.12.2030")
    check("data futura preservada",
          _future is not None and _future.isoformat() == "2030-12-31")

    # deadline_kind com as 4 classes
    sf = {"source": "successfactors:jobs",
          "application_deadline": "2026-10-09T00:00:00Z",
          "title": "X", "description": ""}
    check("SF estruturado -> platform_sf (NUNCA employer)",
          app_intel.deadline_kind(sf) == "platform_sf")
    sf2 = dict(sf, description="Bewerbungsfrist: 15.10.2026")
    _sf2_date = app_intel.deadline_date(sf2)
    check("SF + prazo no texto -> employer_textual (data do TEXTO)",
          app_intel.deadline_kind(sf2) == "employer_textual"
          and _sf2_date is not None and _sf2_date.isoformat() == "2026-10-15")
    gh = {"source": "greenhouse:co",
          "application_deadline": "2026-09-20T00:00:00Z",
          "title": "X", "description": ""}
    check("não-SF estruturado -> employer",
          app_intel.deadline_kind(gh) == "employer")
    gh2 = {"source": "greenhouse:co", "application_deadline": None,
           "title": "X", "description": "Bewerbungsfrist: 15.10.2026"}
    check("não-SF textual -> employer_textual",
          app_intel.deadline_kind(gh2) == "employer_textual")
    gh3 = {"source": "greenhouse:co", "application_deadline": None,
           "title": "X", "description": "sem prazo"}
    check("sem nada -> none", app_intel.deadline_kind(gh3) == "none")
    # estruturado não-SF VENCE textual (fonte estruturada é mais forte)
    gh4 = {"source": "greenhouse:co",
           "application_deadline": "2026-09-20T00:00:00Z",
           "title": "X", "description": "Bewerbungsfrist: 15.10.2026"}
    _gh4_date = app_intel.deadline_date(gh4)
    check("estruturado não-SF vence textual",
          app_intel.deadline_kind(gh4) == "employer"
          and _gh4_date is not None and _gh4_date.isoformat() == "2026-09-20")
    # possible_problems/quality_flags cobrem textual
    from datetime import date
    ref = date(2026, 9, 23)
    probs = app_intel.possible_problems(gh2, ref)
    check("possible_problems: textual gera problema deadline",
          any(p["key"] == "deadline" for p in probs))
    flags = app_intel.quality_flags(gh2, ref)
    check("quality_flags: textual gera flag deadline_textual",
          any(f["key"] == "deadline_textual" for f in flags))
    # determinismo
    check("determinismo textual", app_intel.textual_deadline(
        "Bewerbungsfrist: 15.10.2026") == app_intel.textual_deadline(
        "Bewerbungsfrist: 15.10.2026"))


# ---------------------------------------------------------------------------
# Item 9 — aliases de cidade
# ---------------------------------------------------------------------------


def test_city_aliases() -> None:
    print("== item 9: aliases de cidade (Munich -> munchen) ==")
    loc_map = oi.load_location_intel(ROOT / "company_intel" / "location_intel.json")
    check("catálogo carregado", len(loc_map) >= 13)
    # resolve_city_key
    check("Munich -> munchen", oi.resolve_city_key("Munich") == "munchen")
    check("München -> munchen (canônica)", oi.resolve_city_key("München") == "munchen")
    check("Munchen -> munchen (canônica)", oi.resolve_city_key("Munchen") == "munchen")
    check("Cologne -> koln", oi.resolve_city_key("Cologne") == "koln")
    check("Nuremberg -> nurnberg", oi.resolve_city_key("Nuremberg") == "nurnberg")
    check("Berlin canônica direta", oi.resolve_city_key("Berlin") == "berlin")
    check("desconhecida -> chave própria (não alias)",
          oi.resolve_city_key("Wolfsburg") == "wolfsburg")
    check("vazia -> None", oi.resolve_city_key("") is None
          and oi.resolve_city_key(None) is None)
    # enriquecimento funciona para os 3 aliases
    for city in ("Munich", "München", "Munchen"):
        col = oi.cost_of_living(city, loc_map)
        check(f"cost_of_living({city!r}) -> dado de munchen",
              col is not None and "estimate_monthly" in col)
    for city in ("Cologne", "Nuremberg"):
        col = oi.cost_of_living(city, loc_map)
        check(f"cost_of_living({city!r}) enriquece", col is not None)
    # desconhecida segue None (sem fuzzy)
    check("desconhecida -> None (sem aproximação)",
          oi.cost_of_living("Wolfsburg", loc_map) is None)
    # MUDANÇA NO TEXTO
    j = _job(location="Munich, Germany")
    snap = copy.deepcopy(j)
    loc = oi.city_and_region(j)
    col = oi.cost_of_living(loc.get("city"), loc_map)
    check("valor original da vaga NÃO muda (location exibida)",
          j == snap and loc["city"] == "Munich")
    check("enriquecimento aplicado com location preservada", col is not None)


def main() -> int:
    test_normalize_text()
    test_german_html_cases()
    test_salary_structured()
    test_textual_deadline()
    test_city_aliases()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
