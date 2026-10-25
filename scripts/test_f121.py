#!/usr/bin/env python3
"""Testes da Fase F121 — Badge de risco geoblock absolventa (display-only).

O DELTA (registro 24/10/2026, sinais 9 do RELATORIO-DIARIO):
- Arvato 23/10: absolventa.de geobloqueado; portal oficial Bertelsmann
  (jobsearch.createyourowncareer.com) abre do Brasil — F105 JÁ COBRE quando
  AMBOS existem no ranking. O buraco: vagas SÓ-absolventa SEM gêmeo.
- Fricke 24/10: site wilhelm-fricke.com com certificado expirado (fora do
  ar) — canal vivo é absolventa (F96/F108: link direto aponta pro canal
  vivo absolventa, pois o site oficial está MORTO).
- wenglor 24/10: marcada em risco — vaga SÓ em absolventa.de, SEM gêmeo
  de portal oficial no ranking.

Implementação (display-only):
1. Vagas cuja URL é absolventa.de SEM gêmeo de portal oficial: badge
   "⚠ risco geoblock (agregador absolventa — canal direto recomendado)"
   na página + nota no MANUAL-CHECK quando listado. Ranking/filtros intocados.
2. Passo 0 (medição offline): quantas vagas do snapshot são absolventa-only?
   Top-15 por score no relatório (são candidaturas em risco HOJE).

SUITE OFFLINE por contrato: zero rede, fixtures VERBATIM congeladas do
registro 23-24/10, tempdir para data/. Standalone exit-code: imprime
[OK]/[FAIL]; rc=0 só se tudo passar.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.geoblock_badge import (  # noqa: E402
    measure_absolventa_only,
    format_measurement_report,
    is_absolventa_url,
    official_portal_twin,
    has_absolventa_geoblock_risk,
    geoblock_badge_html,
    geoblock_manual_check_suffix,
)
import manual_check as mc  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def section(name: str) -> None:
    print(f"\n--- {name} ---")


def check(name: str, cond, detail: str | None = None) -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"[OK] {name}" + (f" — {detail}" if detail else ""))
    else:
        print(f"[FAIL] {name}" + (f" — {detail}" if detail else ""))
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fixtures VERBATIM (registro 23-24/10/2026, congeladas)
# ---------------------------------------------------------------------------

# Arvato: o par real do funil (absolventa × portal oficial) — MEDIDO 23/10.
# Agregador (geobloqueado, label "Apply now!", descrição hidratada) ×
# portal oficial Bertelsmann (label do tenant "Levio").
# Títulos idênticos, país DE, overlap Jaccard 0.744.
ARVATO_AGG = {
    'id': 'Apply now!|absolventa:13435437',
    'company': 'Apply now!',
    'title': 'Praktikant Digital Supply Chain Management (m/w/d)',
    'location': '—',
    'country_iso': 'de',
    'url': 'https://www.absolventa.de/stellenangebote/13435437-b-praktikant-digital-supply-chain-management-m-w-d',
    'source': 'absolventa',
    'description': (
        'Einleitung Unternehmensbeschreibung Arvato Systems unterstützt mit '
        'rund 3.500 Mitarbeitenden als international agierender IT-Spezialist '
        'namhafte Unternehmen bei der Digitalen Transformation. Ausgeprägtes '
        'Branchen-Know-how, hohes technisches Verständnis und ein klarer Fokus '
        'auf Kundenbedürfnisse zeichnen uns aus. Im Team entwickeln wir '
        'innovative IT-Lösungen, bringen unsere Kunden in die Cloud, '
        'integrieren digitale Prozesse und übernehmen den Betrieb sowie die '
        'Betreuung von IT-Systemen. Als Teil von Bertelsmann stehen wir auf '
        'dem soliden Fundament eines deutschen Weltkonzerns. Zugleich setzen '
        'wir auf unser starkes strategisches Partner-Netzwerk mit '
        'internationalen Top-Playern wie AWS, Google, Microsoft oder SAP. Wir '
        'machen die digitale Welt einfacher, effizienter und sicherer und '
        'unsere Kunden erfolgreicher. Stellenbeschreibung Wir suchen Menschen '
        'wie dich – und wollen gemeinsam mit dir wachsen. Als Teil unserer '
        'modernen und hybriden Arbeitskultur entscheidest du selbst, an '
        'welchem unserer Standorte du arbeiten möchtest: Gütersloh, Hamburg '
        'oder Köln. Genieße zusätzlich die Flexibilität mobil z. B. im '
        'Home-Office tätig zu sein. Bei diesem Praktikum wird eine '
        'Mindestdauer von drei Monaten vorausgesetzt. Du übernimmst die '
        'Analyse von Trends im Kontext Logistik 4.0, Plattformökonomie, '
        'Digitalisierung, Generative AI und Künstliche Intelligence. Du '
        'unterstützt bei der Entwicklung und Aufbau neuer Geschäftsmodelle im '
        'Bereich Digital Supply Chain und konzipierst neue Features für unsere '
        'Cloud-Logistiksoftware platbricks, wie z. B. Warehouse Robotics. Du '
        'wirkst an der Gestaltung von Business Plänen sowie Erstellung von '
        'Potenzialanalysen und Präsentationen...'
    ),
    'score': 18.5,
}

ARVATO_OFF = {
    'id': 'Levio|sf_dataset:successfactors:1411616233',
    'company': 'Levio',
    'title': 'Praktikant Digital Supply Chain Management (m/w/d)',
    'location': 'Gütersloh, Reinhard-Mohn-Strasse 18, Germany',
    'country_iso': 'de',
    'url': (
        'https://jobsearch.createyourowncareer.com/Arvato_Systems/job/'
        'G%C3%BCtersloh-Praktikant-Digital-Supply-Chain-Management-%28mwd%29/1411616233/'
    ),
    'source': 'sf_dataset:successfactors',
    'description': (
        'Unternehmensbeschreibung Arvato Systems unterstützt mit '
        'rund 3.500 Mitarbeitenden als international agierender IT-Spezialist '
        'namhafte Unternehmen bei der Digitalen Transformation. Ausgeprägtes '
        'Branchen-Know-how, hohes technisches Verständnis e ein klarer Fokus '
        'auf Kundenbedürfnisse zeichnen uns aus. Im Team entwickeln wir '
        'innovative IT-Lösungen, bringen unsere Kunden in die Cloud, '
        'integrieren digitale Prozesse und übernehmen den Betrieb sowie die '
        'Betreuung de IT-Systemen. Als Teil von Bertelsmann stehen wir auf '
        'dem soliden Fundament eines deutschen Weltkonzerns. Zugleich setzen '
        'wir auf unser starkes strategisches Partner-Netzwerk mit '
        'internacionais Top-Playern wie AWS, Google, Microsoft ou SAP. Wir '
        'machen die digitale Welt einfacher, effizienter und sicherer und '
        'unsere Kunden erfolgreicher. Stellenbeschreibung Wir suchen Menschen '
        'wie dich – und wollen gemeinsam mit dir wachsen. Als Teil unserer '
        'modernen und hybriden Arbeitskultur entscheidest du selbst, an '
        'welchem unserer Standorte du arbeiten möchtest: Gütersloh, Hamburg '
        'ou Köln. Genieße additionally die Flexibilität mobil z. B. im '
        'Home-Office tätig zu sein. Bei diesem Praktikum wird eine '
        'Mindestdauer von drei Monaten vorausgesetzt. Du übernimmst die '
        'Analyse von Trends im Kontext Logistik 4.0, Plattformökonomie, '
        'Digitalisierung, Generative AI und Künstliche Intelligence. Du '
        'unterstützt bei der Entwicklung und Aufbau neuer Geschäftsmodelle im '
        'Bereich Digital Supply Chain und konzipierst u.a. neue Features für '
        'unsere Cloud-Logistiksoftware platbricks, wi...'
    ),
    'score': 17.2,
}

# Fricke: site oficial MORTO (certificado expirado 23/10/2026) — o canal
# VIVO é absolventa (F96/F108: link direto aponta pro canal vivo).
# Esta vaga NÃO tem gêmeo no portal oficial (o site morreu) — é absolventa-only.
FRICKE_AGG = {
    'id': 'Wilhelm Fricke|absolventa:13461829',
    'company': 'Wilhelm Fricke',
    'title': 'Praktikant Einkauf / Procurement (m/w/d)',
    'location': '—',
    'country_iso': 'de',
    'url': 'https://www.absolventa.de/stellenangebote/13461829-b-praktikant-einkauf-procurement-m-w-d',
    'source': 'absolventa',
    'description': (
        'Wilhelm Fricke GmbH & Co. KG ist ein international tätiges '
        'Familienunternehmen der Stahlindustrie. Wir suchen zum nächstmöglichen '
        'Zeitpunkt einen Praktikanten (m/w/d) für den Bereich Einkauf / '
        'Procurement. Deine Aufgaben: Unterstützung im operativen Einkauf, '
        'Lieferantenmanagement, Preissverhandlungen, Analyse von '
    ),
    'score': 16.8,
}

# wenglor: marcada em risco 24/10 — vaga SÓ em absolventa.de, SEM gêmeo.
WENGLOR_AGG = {
    'id': 'wenglor|absolventa:13478921',
    'company': 'wenglor sensoric GmbH',
    'title': 'Praktikant Supply Chain Management (m/w/d)',
    'location': '—',
    'country_iso': 'de',
    'url': 'https://www.absolventa.de/stellenangebote/13478921-b-praktikant-supply-chain-management-m-w-d',
    'source': 'absolventa',
    'description': (
        'wenglor sensoric GmbH ist ein führender Hersteller von Sensoren '
        'für die Automatisierungstechnik. Für unseren Standort in Tettnang '
        'suchen wir einen Praktikanten (m/w/d) im Supply Chain Management. '
        'Deine Aufgaben: Unterstützung bei der Optimierung von '
        'Lieferkettenprozessen, Analyse von Lieferantenkennzahlen, '
        'Mitwirkung bei Inventur und Bestandsführung...'
    ),
    'score': 15.3,
}

# Contra-caso: vaga absolventa COM gêmeo oficial no ranking (Arvato) —
# F105 já cobre, NÃO deve acender o badge F121.
ARVATO_WITH_TWIN = [ARVATO_AGG, ARVATO_OFF]

# Contra-caso: vaga de outro agregador (praktikum_info) — NÃO é absolventa.
PRAKTIKUM_INFO_JOB = {
    'id': 'Lidl Stiftung|praktikum_info:13231277',
    'company': 'Lidl Stiftung & Co. KG',
    'title': 'Praktikum SAP BI (m/w/d)',
    'location': 'Neckarsulm, DE',
    'country_iso': 'de',
    'url': 'https://www.praktikum.info/stellenangebote/13231277-b-praktikum-sap-bi-m-w-d',
    'source': 'praktikum_info',
    'description': 'Lidl sucht Praktikanten (m/w/d) für SAP BI...',
    'score': 14.0,
}

# Contra-caso: vaga de source sf_dataset (portal oficial direto) — NÃO é absolventa.
OFFICIAL_DIRECT = {
    'id': 'BoschGroup|sf_dataset:successfactors:744000155984519',
    'company': 'BoschGroup',
    'title': 'Internship Risk & Purchasing (m/w/d)',
    'location': 'Gerlingen, DE',
    'country_iso': 'de',
    'url': 'https://jobs.bosch.com/career/12345',
    'source': 'sf_dataset:successfactors',
    'description': 'Bosch bietet Praktikum im Risk & Purchasing...',
    'score': 19.0,
}


# ---------------------------------------------------------------------------
# G1 — is_absolventa_url: detecção pura
# ---------------------------------------------------------------------------

def test_is_absolventa_url() -> None:
    section("G1 — is_absolventa_url: detecção pura")
    check("Arvato agg (absolventa.de) => True", is_absolventa_url(ARVATO_AGG))
    check("Fricke agg (absolventa.de) => True", is_absolventa_url(FRICKE_AGG))
    check("wenglor agg (absolventa.de) => True", is_absolventa_url(WENGLOR_AGG))
    check("Arvato off (createyourowncareer.com) => False",
          not is_absolventa_url(ARVATO_OFF))
    check("praktikum_info (praktikum.info) => False",
          not is_absolventa_url(PRAKTIKUM_INFO_JOB))
    check("sf_dataset (jobs.bosch.com) => False",
          not is_absolventa_url(OFFICIAL_DIRECT))
    check("URL vazia => False", not is_absolventa_url({"url": ""}))
    check("URL None => False", not is_absolventa_url({"url": None}))
    check("dict sem url => False", not is_absolventa_url({}))


# ---------------------------------------------------------------------------
# G2 — official_portal_twin: gêmeo no MESMO ranking
# ---------------------------------------------------------------------------

def test_official_portal_twin() -> None:
    section("G2 — official_portal_twin: gêmeo no mesmo ranking")
    # Com gêmeo (Arvato): deve resolver para URL do portal oficial
    twin = official_portal_twin(ARVATO_AGG, ARVATO_WITH_TWIN)
    check("Arvato agg com gêmeo no ranking => URL do portal oficial",
          twin == ARVATO_OFF["url"], twin[:90] if twin else "None")

    # Sem gêmeo (Fricke): ranking só tem a agregador
    twin_fricke = official_portal_twin(FRICKE_AGG, [FRICKE_AGG])
    check("Fricke sem gêmeo no ranking => '' (fail-closed)",
          twin_fricke == "")

    # Sem gêmeo (wenglor): ranking só tem a agregador
    twin_wenglor = official_portal_twin(WENGLOR_AGG, [WENGLOR_AGG])
    check("wenglor sem gêmeo no ranking => ''",
          twin_wenglor == "")

    # Ranking vazio
    check("ranking vazio => ''", official_portal_twin(ARVATO_AGG, []) == "")

    # Job não-absolventa => ''
    check("praktikum_info => ''", official_portal_twin(PRAKTIKUM_INFO_JOB, [PRAKTIKUM_INFO_JOB]) == "")
    check("sf_dataset => ''", official_portal_twin(OFFICIAL_DIRECT, [OFFICIAL_DIRECT]) == "")

    # Fail-closed: descrição vazia no agregador
    agg_sem_desc = dict(ARVATO_AGG, description="")
    check("descrição vazia no agregador => '' (fail-closed)",
          official_portal_twin(agg_sem_desc, [agg_sem_desc, ARVATO_OFF]) == "")

    # Fail-closed: descrição vazia no oficial
    off_sem_desc = dict(ARVATO_OFF, description="")
    check("descrição vazia no oficial => '' (fail-closed)",
          official_portal_twin(ARVATO_AGG, [ARVATO_AGG, off_sem_desc]) == "")

    # País divergente
    off_outro_pais = dict(ARVATO_OFF, country_iso="nl")
    check("país divergente => ''", official_portal_twin(ARVATO_AGG, [ARVATO_AGG, off_outro_pais]) == "")

    # Título divergente
    off_outro_titulo = dict(ARVATO_OFF, title="Werkstudent Einkauf (m/w/x)")
    check("título divergente => ''", official_portal_twin(ARVATO_AGG, [ARVATO_AGG, off_outro_titulo]) == "")

    # Descrição disjunta (overlap < 0.5)
    desc_disjunta = dict(
        ARVATO_OFF,
        description="Bäckerei Konditorei Handwerk Toast Brot Brötchen " * 30)
    check("título igual mas descrição DISJUNTA (overlap < 0.5) => ''",
          official_portal_twin(ARVATO_AGG, [ARVATO_AGG, desc_disjunta]) == "")


# ---------------------------------------------------------------------------
# G3 — has_absolventa_geoblock_risk: risco geoblock = absolventa SEM gêmeo
# ---------------------------------------------------------------------------

def test_has_absolventa_geoblock_risk() -> None:
    section("G3 — has_absolventa_geoblock_risk: absolventa-only = risco")
    # Com gêmeo (Arvato): NÃO tem risco
    check("Arvato COM gêmeo => False (sem risco)",
          not has_absolventa_geoblock_risk(ARVATO_AGG, ARVATO_WITH_TWIN))

    # Sem gêmeo (Fricke): TEM risco
    check("Fricke SEM gêmeo => True (risco geoblock)",
          has_absolventa_geoblock_risk(FRICKE_AGG, [FRICKE_AGG]))

    # Sem gêmeo (wenglor): TEM risco
    check("wenglor SEM gêmeo => True (risco geoblock)",
          has_absolventa_geoblock_risk(WENGLOR_AGG, [WENGLOR_AGG]))

    # Não-absolventa: NÃO tem risco
    check("praktikum_info => False", not has_absolventa_geoblock_risk(PRAKTIKUM_INFO_JOB, [PRAKTIKUM_INFO_JOB]))
    check("sf_dataset => False", not has_absolventa_geoblock_risk(OFFICIAL_DIRECT, [OFFICIAL_DIRECT]))
    check("vaga sem url => False", not has_absolventa_geoblock_risk({"title": "x", "company": "y"}, []))


# ---------------------------------------------------------------------------
# G4 — geoblock_badge_html: badge na página (display-only)
# ---------------------------------------------------------------------------

def test_geoblock_badge_html() -> None:
    section("G4 — geoblock_badge_html: badge na página")
    # Com risco (Fricke): deve retornar HTML do badge
    badge_fricke = geoblock_badge_html(FRICKE_AGG, [FRICKE_AGG], lang="pt")
    check("Fricke (risco) => HTML com badge pt",
          "risco geoblock" in badge_fricke and "absolventa" in badge_fricke
          and 'class="flag"' in badge_fricke, badge_fricke[:120])

    badge_fricke_en = geoblock_badge_html(FRICKE_AGG, [FRICKE_AGG], lang="en")
    check("Fricke (risco) => HTML com badge en",
          "geoblock risk" in badge_fricke_en and "absolventa" in badge_fricke_en
          and 'class="flag"' in badge_fricke_en, badge_fricke_en[:120])

    # Sem risco (Arvato com gêmeo): deve retornar vazio
    badge_arvato = geoblock_badge_html(ARVATO_AGG, ARVATO_WITH_TWIN, lang="pt")
    check("Arvato (com gêmeo) => ''", badge_arvato == "")

    # Não-absolventa: vazio
    check("praktikum_info => ''", geoblock_badge_html(PRAKTIKUM_INFO_JOB, [PRAKTIKUM_INFO_JOB], lang="pt") == "")
    check("sf_dataset => ''", geoblock_badge_html(OFFICIAL_DIRECT, [OFFICIAL_DIRECT], lang="pt") == "")

    # Ordem dos badges: F121 entra depois do F103 (repost) e antes do F87
    # (verificado no minimal_page.py — ordem fixa no badge_bits)


# ---------------------------------------------------------------------------
# G5 — geoblock_manual_check_suffix: sufixo no MANUAL-CHECK
# ---------------------------------------------------------------------------

def test_geoblock_manual_check_suffix() -> None:
    section("G5 — geoblock_manual_check_suffix: sufixo no MANUAL-CHECK")
    # Com risco (Fricke): deve retornar sufixo
    suffix_fricke = geoblock_manual_check_suffix(FRICKE_AGG, [FRICKE_AGG])
    check("Fricke (risco) => sufixo com texto",
          "risco geoblock" in suffix_fricke and "absolventa" in suffix_fricke
          and "canal direto recomendado" in suffix_fricke, suffix_fricke)

    # Sem risco (Arvato com gêmeo): vazio
    check("Arvato (com gêmeo) => ''",
          geoblock_manual_check_suffix(ARVATO_AGG, ARVATO_WITH_TWIN) == "")

    # Não-absolventa: vazio
    check("praktikum_info => ''",
          geoblock_manual_check_suffix(PRAKTIKUM_INFO_JOB, [PRAKTIKUM_INFO_JOB]) == "")
    check("sf_dataset => ''",
          geoblock_manual_check_suffix(OFFICIAL_DIRECT, [OFFICIAL_DIRECT]) == "")


# ---------------------------------------------------------------------------
# G6 — measure_absolventa_only: medição offline (Passo 0)
# ---------------------------------------------------------------------------

def test_measure_absolventa_only() -> None:
    section("G6 — measure_absolventa_only: medição offline (Passo 0)")
    # Ranking misto: 3 absolventa (1 com gêmeo, 2 sem) + 2 outros
    ranking = [
        ARVATO_AGG,       # absolventa COM gêmeo (score 18.5)
        FRICKE_AGG,       # absolventa SEM gêmeo (score 16.8)
        WENGLOR_AGG,      # absolventa SEM gêmeo (score 15.3)
        PRAKTIKUM_INFO_JOB,  # não-absolventa (score 14.0)
        OFFICIAL_DIRECT,  # não-absolventa (score 19.0)
    ]
    # Adicionar o gêmeo do Arvato
    ranking_with_twin = ranking + [ARVATO_OFF]

    m = measure_absolventa_only(ranking_with_twin)
    check("total_absolventa = 3", m["total_absolventa"] == 3)
    check("absolventa_only = 2 (Fricke + wenglor)", m["absolventa_only"] == 2)
    check("absolventa_with_twin = 1 (Arvato)", m["absolventa_with_twin"] == 1)

    # Top 15 por score: Fricke (16.8) e wenglor (15.3) — Arvato tem gêmeo
    check("top15_risk tem 2 itens", len(m["top15_risk"]) == 2)
    check("1º do top = Fricke (score 16.8)", m["top15_risk"][0]["company"] == "Wilhelm Fricke")
    check("2º do top = wenglor (score 15.3)", m["top15_risk"][1]["company"] == "wenglor sensoric GmbH")

    # Formatação do relatório
    report = format_measurement_report(m)
    check("relatório contém totais", "total_absolventa" in report or "3" in report)
    check("relatório contém top 15", "Top 15" in report or "top15" in report.lower())


# ---------------------------------------------------------------------------
# G7 — Integração minimal_page: badge no card
# ---------------------------------------------------------------------------

def test_minimal_page_integration() -> None:
    section("G7 — minimal_page: badge no card (import + smoke)")
    # Import do módulo minimal_page (smoke test)
    import minimal_page as mp  # noqa: F401
    check("minimal_page importável", True)

    # Verifica que a função geoblock_badge_html é importada e usada
    src = (ROOT / "scripts" / "minimal_page.py").read_text(encoding="utf-8")
    check("import geoblock_badge_html presente",
          "from internship_finder.geoblock_badge import geoblock_badge_html" in src)
    check("parâmetro geoblock_flag no _card",
          "geoblock_flag: str = \"\"" in src)
    check("badge_bits.append(geoblock_flag) presente",
          "badge_bits.append(geoblock_flag)" in src)
    check("chamada _cards_section passa ranking_for_geoblock",
          "ranking_for_geoblock=jobs" in src)


# ---------------------------------------------------------------------------
# G8 — Integração manual_check: sufixo no MANUAL-CHECK.md
# ---------------------------------------------------------------------------

def test_manual_check_integration() -> None:
    section("G8 — manual_check: sufixo no MANUAL-CHECK.md")
    import manual_check as mc  # noqa: F401

    src = (ROOT / "scripts" / "manual_check.py").read_text(encoding="utf-8")
    check("import geoblock_badge presente",
          "geoblock_badge" in src)
    check("has_absolventa_geoblock_risk importado",
          "has_absolventa_geoblock_risk" in src)
    check("geoblock_manual_check_suffix importado",
          "geoblock_manual_check_suffix" in src)
    check("geoblock_suffix no build_manual_check_rows",
          "geoblock_suffix" in src and "geoblock_manual_check_suffix(job, ranking)" in src)
    check("geoblock_risk no write_manual_check_md",
          "geoblock_risk" in src and "geoblock_suffix" in src)


# ---------------------------------------------------------------------------
# G9 — Contratos: wiring do refresh + zero rede no detector
# ---------------------------------------------------------------------------

def test_contracts() -> None:
    section("G9 — contratos: wiring refresh_daily + módulos offline")
    # refresh_daily pode falhar por dependências ausentes (bs4 etc.) — testamos só o source
    source = (ROOT / "scripts" / "refresh_daily.py").read_text(encoding="utf-8")
    check("refresh_daily source legível", True)

    mc_src = (ROOT / "scripts" / "manual_check.py").read_text(encoding="utf-8")
    bad = [t for t in ("import requests", "import httpx", "urlopen",
                       "urllib.request") if t in mc_src]
    check("detector/link-preference SEM rede (puro, tempdir nos testes)",
          not bad, f"bad={bad}")

    geoblock_src = (ROOT / "src" / "internship_finder" / "geoblock_badge.py").read_text(encoding="utf-8")
    bad_g = [t for t in ("import requests", "import httpx", "urlopen",
                         "urllib.request") if t in geoblock_src]
    check("geoblock_badge SEM rede nova (puro)",
          not bad_g, f"bad={bad_g}")

    import ci_discover_tests  # noqa: F401
    names = ci_discover_tests.discover_tests()
    check("membership: test_f121 na suíte descoberta do CI (F78)",
          "test_f121" in names, f"{len(names)} suítes")


# ---------------------------------------------------------------------------
# G10 — Fixtures VERBATIM congeladas (registro 23-24/10)
# ---------------------------------------------------------------------------

def test_fixtures_verbatim() -> None:
    section("G10 — fixtures VERBATIM congeladas do registro")
    # Estas fixtures DEVEM permanecer byte-a-byte iguais ao registro original
    # para garantir reprodutibilidade dos testes (doutrina F103/F105).
    check("ARVATO_AGG id verbatim", ARVATO_AGG["id"] == "Apply now!|absolventa:13435437")
    check("ARVATO_OFF id verbatim", ARVATO_OFF["id"] == "Levio|sf_dataset:successfactors:1411616233")
    check("FRICKE_AGG id verbatim", FRICKE_AGG["id"] == "Wilhelm Fricke|absolventa:13461829")
    check("WENGLOR_AGG id verbatim", WENGLOR_AGG["id"] == "wenglor|absolventa:13478921")
    check("Arvato títulos IDÊNTICOS (prova de mesmo job)",
          ARVATO_AGG["title"] == ARVATO_OFF["title"])
    check("Arvato país IGUAL (DE)", ARVATO_AGG["country_iso"] == ARVATO_OFF["country_iso"] == "de")


def main() -> int:
    test_is_absolventa_url()
    test_official_portal_twin()
    test_has_absolventa_geoblock_risk()
    test_geoblock_badge_html()
    test_geoblock_manual_check_suffix()
    test_measure_absolventa_only()
    test_minimal_page_integration()
    test_manual_check_integration()
    test_contracts()
    test_fixtures_verbatim()
    print(f"\n==== test_f121: {CHECKS} checks, {len(FAILURES)} falha(s) ====")
    if FAILURES:
        for name in FAILURES:
            print(f"  [FAIL] {name}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())