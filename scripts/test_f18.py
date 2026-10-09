"""Testes da Fase F18 — aplicabilidade: classificador correto + hard exclude.

100% offline (sem rede, sem ``data/`` de produção — fixtures em memória;
os trechos de texto são REAIS, extraídos do eligible_jobs.json de 08/10).

T1 — Classificador german_level (correção dos falsos negativos medidos):
     os 5 FNs (MTU x2, Vodafone, TRUMPF, Deloitte x2) viram ``required``;
     regressões obrigatórias: Airbus "German desirable" continua
     ``preferred``; STIHL (verb_rev) continua ``required``; soft grudado
     ("English required, German is a plus") continua ``preferred``.
     Regra F18 (i): par de idiomas sem soft grudado => required (Deloitte/
     Vodafone); par com soft grudado => preferred (Airbus).
     Regra F18 (ii): intensidade grudada (janela tight, sem cruzar
     vírgula) vence soft solto na janela larga (MTU: "von Vorteil"
     vizinho não rebaixa "Sehr gute Deutsch- und Englischkenntnisse").
     Guardas de FP: soft grudado DEPOIS do token ("German being a big
     plus") continua preferred; parêntese bloqueia ("fluent in German
     (English is a plus)" é required — o plus é do inglês).

T2 — requires_master: título de tese/estudo de mestrado => True; exigência
     de grau na descrição (caso real SAP iXp 1444205833) => True; lista
     completa de FPs ("master data", "masterclass", "postmaster"...) =>
     False; "Bachelor's or Master's" => False; "Abschlussarbeit" isolado
     => False; case-insensitive EN+DE.

T3 — Exclusões (applicability_exclusion_reason + select_eligible):
     de-required sai; visa-blocked sai (match exato do estado); unclear
     FICA; não-mentionada FICA; tese sai; ws-puro sai; híbrido FICA;
     master sai. Ordem first-match (uma vaga, um motivo).

T4 — Integração: fixture misto => eligible só com aplicáveis; contagens
     por motivo corretas; --no-applicability (applicability=False)
     recupera o comportamento pré-F18 (reversibilidade).

T5 — Regressão de pipeline: dataset sintético SEM não-aplicáveis =>
     saída byte a byte idêntica com/sem o estágio (F18 é no-op quando
     nada exclui); counts ganham as chaves de contagem zeradas.

T6 — ZERO falsos positivos (casos reais do top-100 de 07/10): TE
     Connectivity "Master Data Management" NÃO excluído; Corning/Stryker/
     Infineon/Liebherr "Bachelor's or Master's" NÃO excluídos; híbrido
     "Werkstudent ... Praktikum" NÃO excluído; Airbus "German desirable"
     NÃO excluído; empresa visa ``unclear`` NÃO excluída.

Uso:
    .venv/bin/python scripts/test_f18.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

from internship_finder import app_intel  # noqa: E402
from internship_finder import filters as flt  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' — ' + extra) if extra else ''}")
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"== {title} ==")


# ---------------------------------------------------------------------------
# T1 — Classificador german_level (correção dos FNs)
# ---------------------------------------------------------------------------

# Trechos REAIS extraídos do eligible_jobs.json de 08/10 (vagas citadas
# na medição do orquestrador 07/10).
FN_FIXTURES = [
    # (nome, texto real, nível esperado)
    (
        "MTU 12951-d055a806 — 'von Vorteil' vizinho NÃO rebaixa",
        "✓ Sicherer Umgang mit Microsoft 365; erste Kenntnisse der Microsoft "
        "Power Platform sind von Vorteil✓ Sehr gute Deutsch- und "
        "Englischkenntnisse ✓ Ausgeprägte Team- und Kommunikationsfähigkeit",
        "required",
    ),
    (
        "MTU 12951-36fb8cd6 — 'ein Plus' vizinho NÃO rebaixa",
        "✓ Kenntnisse in VBA, Power BI, Python oder vergleichbaren "
        "Analysetools sind ein Plus✓ Gute Deutsch- und Englischkenntnisse✓ "
        "Strukturierte, selbstständige und lösungsorientierte Arbeitsweise",
        "required",
    ),
    (
        "Vodafone 597871501 — 'Du sprichst Deutsch und Englisch fließend'",
        "Du sprichst Deutsch und Englisch fließend. Du lebst mit uns den "
        "Vodafone-Spirit, bist engagiert, offen und hast Lust auf neue "
        "Herausforderungen.",
        "required",
    ),
    (
        "TRUMPF R00043415 — 'sehr guten Deutsch- und guten Englischkenntnissen'",
        "Mit hoher Motivation und Lernbereitschaft sowie sehr guten Deutsch- "
        "und guten Englischkenntnissen in Wort und Schrift runden Sie Ihr "
        "Profil ab.",
        "required",
    ),
    (
        "Deloitte 1419898933 — 'vermitteln – auf Deutsch und Englisch'",
        "Kommunikationsstärke : Du kannst Inhalte klar aufbereiten und "
        "vermitteln – auf Deutsch und Englisch. Deine Chance: Echte "
        "Verantwortung für eigene Aufgabenpakete innerhalb unserer Projekte.",
        "required",
    ),
    (
        "Deloitte 15794-471478 — mesma frase, fonte Bundesagentur",
        "Kommunikationsstärke: Du kannst Inhalte klar aufbereiten und "
        "vermitteln – auf Deutsch und Englisch. Deine Chance: Echte "
        "Verantwortung für eigene Aufgabenpakete innerhalb unserer Projekte.",
        "required",
    ),
]

REGRESSION_FIXTURES = [
    (
        "Airbus 'Business fluent in English, German desirable' — continua preferred",
        "Confident handling of MS Office or Google Suite. First practical "
        "experience desirable. Business fluent in English, German desirable, "
        "all other additional languages are welcome.",
        "preferred",
    ),
    (
        "STIHL 'Fließend in Deutsch & Englisch' — continua required (verb_rev)",
        "Teamplayer mit Freude an der interdisziplinären Zusammenarbeit, "
        "idealerweise mit Vorerfahrungen im agilen Umfeld Fließend in Deutsch "
        "& Englisch Weitere Details zur Stelle Gehalt: 2.117 €/Monat",
        "required",
    ),
    (
        "Flink3 'Fluent English with German being a big plus' — soft DEPOIS vence",
        "Fluent English with German being a big plus for dealing with the "
        "authorities.",
        "preferred",
    ),
    (
        "soft grudado 'English required, German is a plus' — continua preferred",
        "English required, German is a plus",
        "preferred",
    ),
    (
        "'Sprichst fließend Englisch; Deutschkenntnisse sind ein Plus' — preferred",
        "Sprichst fließend Englisch; Deutschkenntnisse sind ein Plus",
        "preferred",
    ),
    (
        "'You are fluent in German (English is a plus)' — parêntese bloqueia o plus",
        "You are fluent in German (English is a plus). We value diversity.",
        "required",
    ),
    (
        "negação 'Keine Deutschkenntnisse erforderlich' — continua plus",
        "Keine Deutschkenntnisse erforderlich",
        "plus",
    ),
    (
        "'Deutschkenntnisse sind erforderlich, Englischkenntnisse von Vorteil'",
        "Deutschkenntnisse sind erforderlich, Englischkenntnisse von Vorteil",
        "required",
    ),
    (
        "sem menção -> None",
        "Working Student - SAP Analytics Cloud (f/m/d)",
        "none",
    ),
]


def test_t1_classifier() -> None:
    section("T1 — classificador german_level: 5 FNs + regressões")
    for name, text, expected in FN_FIXTURES:
        gl = app_intel.german_level(text)
        got = gl.level if gl else "none"
        check(f"FN {name}", got == expected,
              f"got {got} ({gl.reason if gl else '-'})")
    for name, text, expected in REGRESSION_FIXTURES:
        gl = app_intel.german_level(text)
        got = gl.level if gl else "none"
        check(f"REG {name}", got == expected,
              f"got {got} ({gl.reason if gl else '-'})")
    # Regra (i) explícita: par COM soft grudado na janela tight -> preferred
    gl = app_intel.german_level("Languages: German and English desirable")
    check("REG par COM soft grudado -> preferred", gl.level == "preferred")
    # Regra (i): par SEM soft -> required (mudança deliberada F18)
    gl = app_intel.german_level("Languages: German and English")
    check("par SEM soft -> required (regra F18)", gl.level == "required")
    # Determinismo (contrato da função)
    base = "Praktikum Data Analytics. Sehr gute Deutsch- und Englischkenntnisse."
    check("determinismo: 100 repetições iguais",
          len({app_intel.german_level(base).level for _ in range(100)}) == 1)


# ---------------------------------------------------------------------------
# T2 — requires_master
# ---------------------------------------------------------------------------

MASTER_TRUE = [
    ("Masterarbeit im Bereich Data Science (m/w/d)", None),
    ("Master's Thesis in Supply Chain Analytics", None),
    ("Master Thesis Procurement Analytics", None),
    ("Masterstudium Finance & Analytics", None),
    ("Masterstudent (m/w/d) im Einkauf", None),
    # Caso real SAP iXp 1444205833: exigência NA DESCRIÇÃO, não no título
    ("SAP iXp Intern (f/m/d) - Adoption & Consumption Operations",
     "Currently enrolled in a Master's program in business, economics, "
     "information systems or a related field."),
    ("Intern Data Analytics", "You have a Master's degree in Engineering."),
    ("Praktikum Einkauf", "Requirements: M.Sc. or equivalent"),
    ("Praktikum Logistik", "Du hast einen Masterabschluss"),
    ("Werkstudent Data", "you are a Master student"),
    ("Intern SCM", "studying towards a Master in Data Science"),
    ("Praktikum", "completed master's degree required"),
    ("praktikum", "MASTERABSCHLUSS vorhanden"),  # case-insensitive DE
    ("intern", "currently enrolled in a master's program"),  # case EN
    ("Werkstudent", "Masterstudent (m/w/d) gesucht"),
]

MASTER_FALSE = [
    # FPs obrigatórios (prompt §2.iii)
    ("Working Student - KPI Dashboards & Data Analytics (m/f/d)",
     "Help structure and improve data models, master data and reporting "
     "processes."),  # TE Connectivity real (#88 do top-100 de 08/10)
    ("Intern", "The master plan for the quarter includes master data governance"),
    ("Intern", "Join our masterclass on analytics"),
    ("Intern", "The master key system needs maintenance"),
    ("Intern", "master bedroom in the company housing"),
    ("Intern", "You will be the Master of Ceremonies for events"),
    ("Intern", "contact the postmaster about the mail"),
    ("Intern", "the webmaster maintains the site"),
    ("Intern", "the gamesmaster runs the quiz"),
    ("Intern", "the quartermaster issues supplies"),
    ("Intern", "masterful handling of the topic"),
    ("Intern", "an absolute masterpiece"),
    ("Intern", "follow the master schedule"),
    # "Bachelor's or Master's" NÃO é exigência de mestrado
    ("IT Working Student (Documentation, Data Analytics & Project Management) (m/f/d)",
     "Currently enrolled in a Bachelor's or Master's degree program in: "
     "Computer Science Information Technology Business Informatics"),  # Corning real
    ("Praktikum Data Analytics & Lean Process Improvement (m/w/d)",
     "You are currently pursuing a Bachelor's or Master's degree in "
     "Engineering, Industrial Engineering, Business Informatics"),  # Stryker real
    ("Werkstudent - Logistik / Supply Chain (w/m/div)",
     "Bachelor or Master degree in progress"),  # Infineon-style
    ("Praktikant / Werkstudent Datenanalyse & BI (m/w/d)",
     "(Bachelor/Master)"),  # Liebherr-style
    ("Intern SCM", "Bachelor; Master"),
    # "Abschlussarbeit" isolado -> False (ambíguo, pode ser bachelor)
    ("Praktikum Data", "Du schreibst deine Abschlussarbeit bei uns"),
]


def test_t2_requires_master() -> None:
    section("T2 — requires_master: exigência de mestrado (título E descrição)")
    for title, desc in MASTER_TRUE:
        check(f"True <- {title[:48]!r}",
              flt.requires_master(title, desc))
    for title, desc in MASTER_FALSE:
        check(f"False <- {title[:48]!r}",
              not flt.requires_master(title, desc))


# ---------------------------------------------------------------------------
# T3 — Exclusões por motivo (applicability_exclusion_reason / select_eligible)
# ---------------------------------------------------------------------------

def _job(**kw) -> dict:
    base = {
        "id": "T|src:1", "source": "src:1", "title": "Praktikum Data Analytics",
        "company": "TestCo", "location": "Berlin, DE", "country_iso": "de",
        "url": "https://j/1", "description": "Support the team with analyses.",
    }
    base.update(kw)
    return base


INTEL_MAP = {
    # normalizado pela MESMA regra de load_company_intel (casefold/sem espaços)
    "blockedco": {"company": "BlockedCo", "visa_policy": "candidate_must_have_authorization"},
    "unclearco": {"company": "UnclearCo", "visa_policy": "unclear"},
    "supportco": {"company": "SupportCo", "visa_policy": "explicit_support"},
    "novisaco": {"company": "NoVisaCo", "visa_policy": "explicit_no_support"},
}


def test_t3_exclusions() -> None:
    section("T3 — exclusões por motivo (first-match)")

    de_req = _job(description="Sehr gute Deutschkenntnisse erforderlich")
    check("de-required sai (german_required)",
          flt.applicability_exclusion_reason(de_req) == "german_required")

    visa_blocked = _job(company="BlockedCo")
    check("visa-blocked sai (candidate_must_have_authorization)",
          flt.applicability_exclusion_reason(visa_blocked, intel_map=INTEL_MAP)
          == "visa_blocked")
    check("visa unclear FICA (unclear é a aposta do projeto)",
          flt.applicability_exclusion_reason(_job(company="UnclearCo"),
                                             intel_map=INTEL_MAP) is None)
    check("visa explicit_support FICA",
          flt.applicability_exclusion_reason(_job(company="SupportCo"),
                                             intel_map=INTEL_MAP) is None)
    check("empresa não-mentionada FICA",
          flt.applicability_exclusion_reason(_job(company="NoNameCo"),
                                             intel_map=INTEL_MAP) is None)
    check("sem intel_map o critério de visto NÃO aplica (função pura)",
          flt.applicability_exclusion_reason(visa_blocked) is None)
    check("explicit_no_support FICA (critério é SÓ must_have_authorization)",
          flt.applicability_exclusion_reason(_job(company="NoVisaCo"),
                                             intel_map=INTEL_MAP) is None)

    thesis = _job(title="Abschlussarbeit im Bereich Data Analytics")
    check("tese (Abschlussarbeit) sai",
          flt.applicability_exclusion_reason(thesis) == "thesis_title")
    thesis_en = _job(title="Thesis Internship Audit")
    check("tese EN (Thesis Internship) sai",
          flt.applicability_exclusion_reason(thesis_en) == "thesis_title")

    ws_puro = _job(title="Werkstudent Data Engineering & Business Intelligence (m/m)")
    check("Werkstudent PURO sai",
          flt.applicability_exclusion_reason(ws_puro) == "werkstudent_puro")
    ws_en = _job(title="Working Student Analytics")
    check("Working Student PURO sai",
          flt.applicability_exclusion_reason(ws_en) == "werkstudent_puro")
    hibrido = _job(title="Werkstudent / Praktikum Data Analytics (m/w/d)")
    check("híbrido 'Werkstudent ... Praktikum' FICA",
          flt.applicability_exclusion_reason(hibrido) is None)
    hibrido2 = _job(title="Praktikant / Werkstudent Data Analytics")
    check("híbrido 'Praktikant / Werkstudent' FICA",
          flt.applicability_exclusion_reason(hibrido2) is None)
    hibrido3 = _job(title="Working Student - Internship SCM")
    check("híbrido EN 'Working Student - Internship' FICA",
          flt.applicability_exclusion_reason(hibrido3) is None)

    master_t = _job(title="Master's Thesis in Supply Chain")
    check("master por título sai (thesis_title — precedência first-match)",
          flt.applicability_exclusion_reason(master_t) == "thesis_title")
    master_d = _job(description="Currently enrolled in a Master's program")
    check("master por descrição sai (master_required)",
          flt.applicability_exclusion_reason(master_d) == "master_required")

    # first-match: vaga com alemão exigido E título de tese conta SÓ german_required
    both = _job(title="Abschlussarbeit im Bereich Data",
                description="Sehr gute Deutschkenntnisse erforderlich")
    check("first-match: alemão+tese conta SÓ german_required",
          flt.applicability_exclusion_reason(both) == "german_required")

    # is_werkstudent_puro_title / is_thesis_title contratos diretos
    check("is_thesis_title case-insensitive",
          flt.is_thesis_title("ABSCHLUSSARBEIT EINKAUF"))
    check("is_werkstudent_puro_title case-insensitive",
          flt.is_werkstudent_puro_title("WERKSTUDENT DATA"))


# ---------------------------------------------------------------------------
# T4 — Integração: cascata completa com estágio de aplicabilidade
# ---------------------------------------------------------------------------

def test_t4_integration() -> None:
    section("T4 — integração: cascata completa (select_eligible)")

    jobs = [
        _job(id="ok-1", title="Praktikum Data Analytics",
             description="English required. Support the team."),
        _job(id="ok-2", company="UnclearCo",
             description="sap reporting python"),  # visa unclear FICA
        _job(id="out-de", title="Praktikum Data Analytics",
             description="Sehr gute Deutsch- und Englischkenntnisse erforderlich"),
        _job(id="out-visa", company="BlockedCo",
             description="support the team"),
        _job(id="out-thesis", title="Abschlussarbeit Data Analytics",
             description="support"),
        _job(id="out-ws", title="Werkstudent Data Analytics",
             description="support"),
        _job(id="out-master", title="Praktikum Data Analytics",
             description="Currently enrolled in a Master's program"),
    ]
    sel, counts = flt.select_eligible(jobs, country="de", intel_map=INTEL_MAP)
    ids = [j["id"] for j in sel]
    check("eligible só com aplicáveis",
          set(ids) == {"ok-1", "ok-2"}, str(ids))
    check("contagem por motivo: german_required 1",
          counts["aplicabilidade_excluidas_german_required"] == 1)
    check("contagem por motivo: visa_blocked 1",
          counts["aplicabilidade_excluidas_visa_blocked"] == 1)
    check("contagem por motivo: thesis_title 1",
          counts["aplicabilidade_excluidas_thesis_title"] == 1)
    check("contagem por motivo: werkstudent_puro 1",
          counts["aplicabilidade_excluidas_werkstudent_puro"] == 1)
    check("contagem por motivo: master_required 1",
          counts["aplicabilidade_excluidas_master_required"] == 1)
    check("counts['aplicabilidade'] == len(sel) == 2",
          counts["aplicabilidade"] == len(sel) == 2)

    # Reversibilidade: applicability=False recupera o comportamento pré-F18
    sel_off, counts_off = flt.select_eligible(
        jobs, country="de", applicability=False, intel_map=INTEL_MAP
    )
    check("--no-applicability: NADA é excluído (reversível)",
          len(sel_off) == 7
          and "aplicabilidade" in counts_off
          and all(v == 0 for k, v in counts_off.items()
                  if k.startswith("aplicabilidade_excluidas_"))
          and counts_off["aplicabilidade"] == 7)

    # A lamada SEM intel_map (pura) mantém os outros motivos
    sel_nomap, _ = flt.select_eligible(jobs, country="de")
    check("sem intel_map: só o critério de visto não aplica",
          set(j["id"] for j in sel_nomap) == {"ok-1", "ok-2", "out-visa"})


# ---------------------------------------------------------------------------
# T5 — Regressão: dataset sem não-aplicáveis => saída idêntica (no-op)
# ---------------------------------------------------------------------------

def test_t5_regression_noop() -> None:
    section("T5 — regressão: sem não-aplicáveis, F18 é no-op byte a byte")

    clean = [
        _job(id=f"ok-{i}", title=f"Praktikum Data Analytics {i}",
             description="English required. Support the team.")
        for i in range(5)
    ]
    sel_on, counts_on = flt.select_eligible(clean, country="de")
    sel_off, counts_off = flt.select_eligible(clean, country="de",
                                             applicability=False)
    check("mesmo conjunto com/sem o estágio",
          json.dumps(sel_on, sort_keys=True) == json.dumps(sel_off, sort_keys=True))
    check("contagens clássicas idênticas (total/tipo/area/pais)",
          all(counts_on[k] == counts_off[k]
              for k in ("total", "tipo", "area", "pais")))
    check("counts F18 zerados quando nada exclui",
          all(counts_on[f"aplicabilidade_excluidas_{r}"] == 0
              for r in flt.APPLICABILITY_EXCLUSION_REASONS)
          and counts_on["aplicabilidade"] == 5)

    # Pipeline completo via cli.run_filter_pipeline: dataset limpo produz
    # arquivo byte a byte idêntico com o estágio ligado (default) — o
    # estágio não introduz nada além da remoção.
    import tempfile

    from internship_finder.cli import run_filter_pipeline

    with tempfile.TemporaryDirectory(prefix="t_f18_") as td:
        out_a = Path(td) / "a.json"
        out_b = Path(td) / "b.json"
        rc_a = run_filter_pipeline(
            [json.loads(json.dumps(j)) for j in clean],
            student=True, area=False, country="all", output=out_a,
            dedup=False, rank=True, hydrate=False, official_page=False,
        )
        rc_b = run_filter_pipeline(
            [json.loads(json.dumps(j)) for j in clean],
            student=True, area=False, country="all", output=out_b,
            dedup=False, rank=True, hydrate=False, official_page=False,
            applicability=False,
        )
        check("pipeline: exit codes iguais e >0 vagas (dataset limpo)",
              rc_a == rc_b == 0)
        check("pipeline: eligible byte a byte idêntico (F18 no-op)",
              out_a.read_bytes() == out_b.read_bytes())


# ---------------------------------------------------------------------------
# T6 — ZERO falsos positivos (casos reais do top-100 de 07/10)
# ---------------------------------------------------------------------------

def test_t6_zero_fp() -> None:
    section("T6 — ZERO falsos positivos (casos reais do top-100)")

    # NOTA de escopo (F18): cada vaga abaixo é verificada no EIXO que o
    # enunciado nomeia (regex de mestrado / classificador de alemão /
    # híbrido / visa). Vagas com título "Working Student"/"Werkstudent"
    # PURO continuam saindo pelo motivo (d) — 36 medidas no top-100 de
    # 07/10 — isso é a REGRA da fase, não falso positivo. O que NÃO pode
    # acontecer é a vaga sair pelo eixo ERRADO (master-data virando
    # mestrado, "German desirable" virando required etc.).

    # TE Connectivity "Master Data Management" (#90 do enunciado; #88 no
    # snapshot): menção a master DATA, não a grau — regex de mestrado
    # NÃO pode pegar.
    te = _job(
        title="Working Student - KPI Dashboards & Data Analytics (m/f/d)",
        description=(
            "Help structure and improve data models, master data and "
            "reporting processes. Gather requirements and coordinate open "
            "topics with stakeholders across different business functions."
        ),
    )
    check("TE Connectivity 'master data': requires_master False",
          not flt.requires_master(te["title"], te["description"]))

    # Corning: "Bachelor's or Master's" não é exigência de mestrado.
    corning_desc = (
        "Required Qualifications Currently enrolled in a Bachelor's or "
        "Master's degree program in: Computer Science Information "
        "Technology Business Informatics Data Science Engineering"
    )
    check("Corning 'Bachelor's or Master's': requires_master False",
          not flt.requires_master(
              "IT Working Student (Documentation, Data Analytics & Project "
              "Management) (m/f/d)", corning_desc))

    stryker_desc = ("You are currently pursuing a Bachelor's or Master's "
                    "degree in Engineering, Industrial Engineering")
    check("Stryker 'Bachelor's or Master's': requires_master False",
          not flt.requires_master(
              "Internship Data Analytics & Process Improvement – 6 Months",
              stryker_desc))

    liebherr_desc = ("Du bist Studierende:r der Fachrichtung (Bachelor/Master) "
                     "Wirtschaftsinformatik, Data Science oder ähnliches")
    check("Liebherr '(Bachelor/Master)': requires_master False",
          not flt.requires_master(
              "Praktikant / Werkstudent Datenanalyse & BI im Customer Service",
              liebherr_desc))

    infineon_desc = ("Studium der Wirtschaftsinformatik, Data Science oder "
                     "vergleichbar (Bachelor oder Master)")
    check("Infineon 'Bachelor or Master': requires_master False",
          not flt.requires_master(
              "Werkstudent - Reporting und Data Analytics (w/m/div)",
              infineon_desc))

    # EIXO COMPLETO: as vagas de título Praktikum/Internship com esses
    # textos NÃO são excluídas por NENHUM motivo (prova integrada de que
    # o eixo mestrado não vaza).
    corning_like = _job(title="Praktikum Data Analytics & Project Management",
                        description=corning_desc)
    check("vaga Praktikum com 'Bachelor's or Master's' NÃO excluída",
          flt.applicability_exclusion_reason(corning_like) is None)
    te_like = _job(title="Praktikum KPI Dashboards & Data Analytics",
                  description=te["description"])
    check("vaga Praktikum com 'master data' NÃO excluída",
          flt.applicability_exclusion_reason(te_like) is None)

    # Híbrido Werkstudent...Praktikum (73 medidos no dataset): FICA
    hib = _job(title="Werkstudent / Praktikum Operations Center (m/w/d)",
               description="Support the operations center team.")
    check("híbrido Werkstudent/Praktikum NÃO excluído",
          flt.applicability_exclusion_reason(hib) is None)

    # Airbus "German desirable": preferred, não required -> o EIXO de
    # alemão não exclui (classificador não pode ter promoted a required).
    airbus_text = ("Business fluent in English, German desirable, all "
                   "other additional languages are welcome.")
    gl = app_intel.german_level(airbus_text)
    check("Airbus 'German desirable': german_level preferred (não required)",
          gl is not None and gl.level == "preferred")
    airbus_like = _job(title="Working student (d/f/m) in Strategic Procurement "
                         "Praktikum", description=airbus_text)
    check("vaga com 'German desirable' NÃO excluída pelo eixo alemão",
          flt.applicability_exclusion_reason(airbus_like) is None)

    # Empresa visa unclear FICA (mesmo sem alemão/mestrado)
    unclear = _job(company="UnclearCo", description="sap reporting python")
    check("empresa visa 'unclear' NÃO excluída",
          flt.applicability_exclusion_reason(unclear, intel_map=INTEL_MAP)
          is None)


def main() -> int:
    test_t1_classifier()
    test_t2_requires_master()
    test_t3_exclusions()
    test_t4_integration()
    test_t5_regression_noop()
    test_t6_zero_fp()
    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} de {CHECKS} checks falharam:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"TUDO OK ({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
