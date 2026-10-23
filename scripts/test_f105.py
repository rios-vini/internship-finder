#!/usr/bin/env python3
"""Testes da Fase F105 — Vetter /job/x/ + Arvato portal oficial +
external_agreement_gate J&J BE (offline, fixtures VERBATIM do registro
23/10 e do eligible de produção).

O DELTA (registro 23/10 tarde, medidas ao vivo):

1. **Vetter migrou o formato de URL de vaga** — o legado
   ``careers.vetter-pharma.com/jobs/<ID>`` dá 404; o formato vivo é
   ``/job/<slug>/<ID>/`` (IDs inalterados, 7+ vagas ATIVAS). A regra nova
   vive em ``discovery_rules.TENANT_JOB_URL_FORMATS`` (camada por tenant
   do F76.1) com GUARD: URL no formato legado é reconhecida como
   ``legacy_dead`` — NUNCA seguida/reconstruída (não existe reescrita no
   código; o guard só classifica).

2. **Arvato Systems: o geoblock era SÓ do agregador absolventa.de** — o
   portal oficial Bertelsmann (jobsearch.createyourowncareer.com) abre do
   Brasil, e a candidatura roda no SmartRecruiters corporativo. Regra de
   resolução de link no ``manual_check`` (doutrina F96: o link direto
   aponta para o alvo aplicável ao dono): quando a vaga na fila está num
   agregador geobloqueante e o gêmeo no portal oficial existe no MESMO
   ranking (mesmo título normalizado + mesmo país + overlap de descrição
   Jaccard ≥ 0.5 — o único par misto medido do funil tem 0.744), o link
   direto da fila vira o do portal oficial, marcado como tal.

3. **J&J Beerse (BE): gate EXTERNO de acordo** — a vaga só começa se a
   universidade assinar o standardized Belgium internship agreement
   ("External agreements cannot be accepted"). A vaga SEGUE elegível (o
   gate é externo e resolvível pela UFSCar) e entra na fila manual-check
   com o NOVO motivo ``external_agreement_gate`` (taxonomia F96; flag
   persistida no padrão id_collision, NUNCA exclui). Família medida no
   corpus inteiro: J&J ×2 (padrão 1) + Danone ×5 ("3-party internship
   agreement signed by your university", padrão 2). A família de
   MATRÍCULA local (Continental "Studium an einer deutschen Hochschule",
   Avery "Currently enrolled at a Dutch university" — exclusão F99 /
   card F106) e menções genéricas de acordo (Deutsche Börse boilerplate)
   NÃO acendem.

SUITE OFFLINE por contrato (o registro JÁ mediu 23/10 — nada é
re-sondado): zero rede, fixtures verbatim congeladas, tempdir para
data/. Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo
passar.
"""
from __future__ import annotations

import inspect
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import manual_check as mc  # noqa: E402
import ranking_digest  # noqa: E402
import refresh_daily as rd  # noqa: E402
from internship_finder import discovery_rules as dr  # noqa: E402

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
# Fixtures VERBATIM (registro 23/10 + eligible de produção, congeladas)
# ---------------------------------------------------------------------------

# Vetter: as URLs de vaga MEDIDAS no eligible de produção (formato vivo
# /job/<slug>/<ID>/, IDs inalterados) — todas ``current``.
VETTER_CURRENT_URLS = ['https://careers.vetter-pharma.com/job/Ravensburg-Praktikum-Einkauf-Prozesse-&-Systeme-%28mwd%29-Bade-88212/1437176433/', 'https://careers.vetter-pharma.com/job/Ravensburg-Praktikum-Lagerlogistik-&-Systeme-%28mwd%29-Bade-88212/1435349233/', 'https://careers.vetter-pharma.com/job/Ravensburg-Praktikum-Operativer-Pharma-Einkauf-%28mwd%29-Bade-88212/1437174833/', 'https://careers.vetter-pharma.com/job/Ravensburg-Praktikum-Produktionstechnik-%28mwd%29-Bade-88212/1435232033/', 'https://careers.vetter-pharma.com/job/Ravensburg-Praktikum-Prozessmanagement-Business-Process-Management-%28BPM%29-%28mwd%29-Bade-88212/1435565633/', 'https://careers.vetter-pharma.com/job/Ravensburg-Praktikum-Qualit%C3%A4tssicherung-Quality-Operations-%28mwd%29-Bade-88212/1435341033/', 'https://careers.vetter-pharma.com/job/Ravensburg-Praktikum-Sales-&-Operations-Planning-%28mwd%29-Bade-88212/1435347133/', 'https://careers.vetter-pharma.com/job/Ravensburg-Praktikum-Strategischer-Pharma-Einkauf-%28mwd%29-Bade-88212/1437176033/', 'https://careers.vetter-pharma.com/job/Ravensburg-Praktikum-Technischer-Einkauf-%28mwd%29-Bade-88212/1437457833/']

# Vetter: o formato LEGADO do registro (23/10: "URLs antigas
# careers.vetter-pharma.com/jobs/<ID> dão 404") — exemplo com ID real da
# fila, shape ``/jobs/<ID>``.
VETTER_LEGACY_URL = "https://careers.vetter-pharma.com/jobs/1437176033"

# Arvato Systems: o MESMO job em DUAS fontes (par misto único do funil,
# medido 23/10). Agregador (geobloqueado, label-lixo "Apply now!",
# descrição hidratada pela F101) × portal oficial Bertelsmann (label do
# tenant "Levio"). Títulos idênticos, país de, overlap Jaccard 0.744.
ARVATO_AGG = {'id': 'Apply now!|absolventa:13435437', 'company': 'Apply now!', 'title': 'Praktikant Digital Supply Chain Management (m/w/d)', 'location': '—', 'country_iso': 'de', 'url': 'https://www.absolventa.de/stellenangebote/13435437-b-praktikant-digital-supply-chain-management-m-w-d', 'source': 'absolventa', 'description': 'Einleitung Unternehmensbeschreibung Arvato Systems unterstützt mit rund 3.500 Mitarbeitenden als international agierender IT-Spezialist namhafte Unternehmen bei der Digitalen Transformation. Ausgeprägtes Branchen-Know-how, hohes technisches Verständnis und ein klarer Fokus auf Kundenbedürfnisse zeichnen uns aus. Im Team entwickeln wir innovative IT-Lösungen, bringen unsere Kunden in die Cloud, integrieren digitale Prozesse und übernehmen den Betrieb sowie die Betreuung von IT-Systemen. Als Teil von Bertelsmann stehen wir auf dem soliden Fundament eines deutschen Weltkonzerns. Zugleich setzen wir auf unser starkes strategisches Partner-Netzwerk mit internationalen Top-Playern wie AWS, Google, Microsoft oder SAP. Wir machen die digitale Welt einfacher, effizienter und sicherer und unsere Kunden erfolgreicher. Stellenbeschreibung Wir suchen Menschen wie dich – und wollen gemeinsam mit dir wachsen. Als Teil unserer modernen und hybriden Arbeitskultur entscheidest du selbst, an welchem unserer Standorte du arbeiten möchtest: Gütersloh, Hamburg oder Köln . Genieße zusätzlich die Flexibilität mobil z. B. im Home-Office tätig zu sein. Bei diesem Praktikum wird eine Mindestdauer von drei Monaten vorausgesetzt. Du übernimmst die Analyse von Trends im Kontext Logistik 4.0, Plattformökonomie, Digitalisierung, Generative AI und Künstliche Intelligence Du unterstützt bei der Entwicklung und Aufbau neuer Geschäftsmodelle im Bereich Digital Supply Chain und konzipierst . neue Features für unsere Cloud-Logistiksoftware platbricks, wie z. B. Warehouse Robotics Du wirkst an der Gestaltung von Business Plänen sowie Erstellung von Potenzialanalysen und Präsentationsunterlagen mit Du identifizierst Usecases und erstellst Userstories für den Einsatz von Generativer KI im Bereich Supply Chain Management Du optimierst unser innovatives Business Analytics "Chat with your Data" und "Plan with your Data" Du begleitest die Konzeption und Durchführung von Studien und Begleitung von Pilotprojekten und führst Markt- und Wettbewerbsrecherchen durch Qualifikationen Du bist mitten in deinem Studium der Logistik, Supply Chain Management, (Wirtschafts-)Informatik, Wirtschaftsingenieurwesen oder BWL mit Schwerpunkt Supply Chain Management (SCM), Digital Management, Innovationsmanagement o. ä. Studiengänge Du besitzt sehr gute theoretische Kenntnisse im Bereich Supply Chain Management und digitale Technologien Du verfügst über sehr gute Kenntnisse des Microsoft Office Pakets (Powerpoint, Visio, Word Dich zeichnen eine hohe Einsatzbereitschaft, Flexibilität, ausgeprägte Kundenorientierung und Teamfähigkeit aus Auch wenn du nicht alle unsere Wünsche erfüllst, zögere nicht, dich bei uns zu bewerben, denn WEITERENTWICKLUNG unserer Mitarbeitenden wird bei uns großgeschrieben und eröffnet dir in unserem Unternehmen vielfältige Möglichkeiten. Zusätzliche Informationen Aufgaben'}
ARVATO_OFF = {'id': 'Levio|sf_dataset:successfactors:1411616233', 'company': 'Levio', 'title': 'Praktikant Digital Supply Chain Management (m/w/d)', 'location': 'Gütersloh, Reinhard-Mohn-Strasse 18, Germany', 'country_iso': 'de', 'url': 'https://jobsearch.createyourowncareer.com/Arvato_Systems/job/G%C3%BCtersloh-Praktikant-Digital-Supply-Chain-Management-%28mwd%29/1411616233/', 'source': 'sf_dataset:successfactors', 'description': 'Unternehmensbeschreibung Arvato Systems unterstützt mit rund 3.500 Mitarbeitenden als international agierender IT-Spezialist namhafte Unternehmen bei der Digitalen Transformation. Ausgeprägtes Branchen-Know-how, hohes technisches Verständnis und ein klarer Fokus auf Kundenbedürfnisse zeichnen uns aus. Im Team entwickeln wir innovative IT-Lösungen, bringen unsere Kunden in die Cloud, integrieren digitale Prozesse und übernehmen den Betrieb sowie die Betreuung von IT-Systemen. Als Teil von Bertelsmann stehen wir auf dem soliden Fundament eines deutschen Weltkonzerns. Zugleich setzen wir auf unser starkes strategisches Partner-Netzwerk mit internationalen Top-Playern wie AWS, Google, Microsoft oder SAP. Wir machen die digitale Welt einfacher, effizienter und sicherer und unsere Kunden erfolgreicher. Stellenbeschreibung Wir suchen Menschen wie dich – und wollen gemeinsam mit dir wachsen. Als Teil unserer modernen und hybriden Arbeitskultur entscheidest du selbst, an welchem unserer Standorte du arbeiten möchtest:\xa0 Gütersloh, Hamburg oder Köln . Genieße zusätzlich die Flexibilität mobil z. B. im Home-Office tätig zu sein. \xa0 Bei diesem Praktikum wird eine\xa0 Mindestdauer von drei Monaten \xa0vorausgesetzt.\xa0 \xa0 Du übernimmst die Analyse von Trends im Kontext Logistik 4.0, Plattformökonomie, Digitalisierung, Generative AI und Künstliche Intelligence\xa0 Du unterstützt bei der Entwicklung und Aufbau neuer Geschäftsmodelle im Bereich Digital Supply Chain und konzipierst u.a. neue Features für unsere Cloud-Logistiksoftware platbricks, wie z. B. Warehouse Robotics Du wirkst an der Gestaltung von Business Plänen sowie Erstellung von Potenzialanalysen und Präsentationsunterlagen mit Du identifizierst Usecases und erstellst Userstories für den Einsatz von Generativer KI im Bereich Supply Chain Management Du optimierst unser innovatives Business Analytics "Chat with your Data" und "Plan with your Data" Du begleitest die Konzeption und Durchführung von Studien und Begleitung von Pilotprojekten und führst Markt- und Wettbewerbsrecherchen durch Qualifikationen Du bist mitten in deinem Studium der Logistik, Supply Chain Management, (Wirtschafts-)Informatik, Wirtschaftsingenieurwesen oder BWL mit Schwerpunkt Supply Chain Management (SCM), Digital Management, Innovationsmanagement o. ä. Studiengänge Du besitzt sehr gute theoretische Kenntnisse im Bereich Supply Chain Management und digitale Technologien Du verfügst über sehr gute Kenntnisse des Microsoft Office Pakets (Powerpoint, Visio, Word etc.) Dich zeichnen eine hohe Einsatzbereitschaft, Flexibilität, ausgeprägte Kundenorientierung und Teamfähigkeit aus \xa0 Auch wenn du nicht alle unsere Wünsche erfüllst, zögere nicht, dich bei uns zu bewerben, denn WEITERENTWICKLUNG unserer Mitarbeitenden wird bei uns großgeschrieben und eröffnet dir in unserem Unternehmen vielfältige Möglichkeiten. Zusätzliche Informationen Interessiert? Dann bewirb dich über unser Online-Bewerbungsformular mit deinem Lebenslauf und deiner Gehaltsvorstellung. Wir wollen ein fairer und inklusiver Arbeitgeber sein. Wir schätzen die unterschiedlichen Perspektiven, die eine vielfältige Belegschaft einbringt. Daher suchen wir aktiv nach Menschen, die unser Unternehmen durch ihre Identität, ihren Hintergrund und ihre persönlichen Erfahrungen bereichern, mit oder ohne Behinderung. \xa0 \xa0 \xa0 Informationspflichten im Zusammenhang mit der Erhebung deiner personenbezogenen Daten: Verantwortlicher für den Datenschutz bei deiner Bewerbung ist die\xa0in der Stellenausschreibung angegebene Firma. Die Firma verarbeitet deine Daten zwecks Begründung eines Beschäftigungsverhältnisses auf Grundlage des Art. 6 (1) b DSGVO / § 26 (1) 1 BDSG. Die Speicherdauer deiner Daten richtet sich an den Fristen des jeweiligen Landes aus beginnend mit Abschluss des Einstellungsprozesses.\xa0Diese findest du hier . Den Datenschutzbeauftragten der Firma kannst du unter der o.g. Postanschrift erreichen. Weitere Informationen zum Datenschutz und zu deinen Rechten erhältst\xa0du hier . \xa0 Recruiting-Plattform powered by SmartRecruiters .'}

# J&J Beerse (BE) — R-106104 (IDAR Intern Academy) e R-102271 (Analytical
# Chemistry): parágrafo verbatim com o gate ("standardized Johnson &
# Johnson Belgium internship agreement. External agreements cannot be
# accepted.").
JJ_106104_PARA = 'You can start the internship at any time in 2027, provided the internship is completed by 31 December 2027. Please note: You must remain enrolled as a student throughout the internship. Graduates who are no longer enrolled are unfortunately not eligible for this internship. The internship can only start if your school agrees to sign the standardized Johnson & Johnson Belgium internship agreement. External agreements cannot be accepted. Launch your career in analytical chemistry and help shape the future of healthcare. We look forward to receiving your application! Required Skills: Preferred Skills: The anticipated pay range and benefits for this position is: As this position is posted in a c'
JJ_102271_PARA = 'cal data software is a plus. Practical details: Location: Beerse (BE) Duration: 3 to 9 months Timeframe: TBD Others: The position requires presence on site . Please note: You must remain enrolled as a student throughout the internship. Graduates who are no longer enrolled are unfortunately not eligible for this internship. The internship can only start if your school agrees to sign the standardized Johnson & Johnson Belgium internship agreement. External agreements cannot be accepted. Launch your career in analytical chemistry and help shape the future of healthcare. We loo'

# Danone (icims) — família 2 medida (×5 no corpus): acordo 3-partes
# assinado pela universidade.
DANONE_PARA = '/Masters student during the whole internship period; You are a resident of the Netherlands and hold a valid BSN number (if you are a non-EU citizen, you need to have a valid Dutch residency permit); In the case of non-EU citizens, it is mandatory to provide a 3-party internship agreement signed by your university; Ideally available to start in December/January for a minimum of '

# Contra-casos (família de MATRÍCULA local — F99/F106, NÃO o gate de
# acordo externo):
CONTINENTAL_PARA = 'dernisierung der bestehenden Word-Guideline - Strukturierung und Visualisierung von Inhalten - Weiterentwicklung zum praktischen Arbeits-Tool Qualifikationen - Studium der Chemie, Chemieingenieurwissenschaften, Materialwissenschaften, Data Science, Ingenieurwissenschaften oder vergleichbar an einer deutschen Hochschule - Interesse an Datenanalyse, Materialentwicklung oder Automobiltechnologie - Gute Microsoft Excel-Kenntnisse - Erste Erfahrungen mit Power '  # "Studium ... an einer deutschen Hochschule"
AVERY_PARA = "ired: Currently enrolled in a Bachelor's or Master's degree program in Procurement, Logistics, Supply Chain Management, Business Administration, or a related field of study for the entire duration of the internship. Currently enrolled at a Dutch university. Excellent communication and interpersonal skills in English (written and verbal). "  # "Currently enrolled at a Dutch university"

# Contra-caso (menção genérica de acordo, boilerplate — sem gate):
DBOERSE_PARA = "asks and ad-hoc assessments, as required. Your profile: You are enrolled in a Bachelor's or Master's Degree programme with a recognized institution focusing on Financial Markets, Data and Technologies and can provide an internship agreement, OR have graduated with a Bachelor's degree or similar for no more than 6 months Comfortable with creating graphics, presentations and managing communication channels. Sound judge"  # "can provide an internship agreement, OR ..."


def jj_job(ref: str, para: str) -> dict:
    return {
        "id": f"Jj|sf_dataset:workday:{ref}",
        "company": "Jj",
        "title": f"Internship - J&J Beerse ({ref})",
        "location": "Beerse, Antwerp, Belgium",
        "country_iso": "be",
        "url": (f"https://jj.wd5.myworkdayjobs.com/jj/job/"
                f"Beerse-Antwerp-Belgium/Internship_{ref}"),
        "description": para,
    }


# ---------------------------------------------------------------------------
# G1 — Vetter v2: formato vivo x legado morto (guard, nunca segue)
# ---------------------------------------------------------------------------

def test_vetter_v2() -> None:
    section("G1 — Vetter v2: /job/<slug>/<ID>/ vivo; /jobs/<ID> morto")
    check("camada por tenant existe (TENANT_JOB_URL_FORMATS['vetter'])",
          "vetter" in dr.TENANT_JOB_URL_FORMATS)
    fmt = dr.TENANT_JOB_URL_FORMATS["vetter"]
    check("regra-mãe é a do ATS do tenant (successfactors no RULES)",
          fmt.ats == "successfactors" and dr.rule_for("successfactors") is not None)
    check("evidência é medição datada (registro 23/10), não opinião",
          "23/10" in fmt.evidence and "404" in fmt.evidence)
    for u in VETTER_CURRENT_URLS:
        check(f"current (medido): …{u[-42:]}",
              dr.job_url_format_status(u) == "current")
    check("legacy do registro (/jobs/<ID>) => legacy_dead (MORTO)",
          dr.job_url_format_status(VETTER_LEGACY_URL) == "legacy_dead")
    check("legacy com barra final também é morto",
          dr.job_url_format_status(VETTER_LEGACY_URL + "/") == "legacy_dead")
    check("guard 'não seguido': NÃO existe reescrita legado->novo "
          "(resolve_direct_link deixa a URL intocada)",
          mc.resolve_direct_link(VETTER_LEGACY_URL) == VETTER_LEGACY_URL)
    check("outro shape do MESMO host => None (silêncio honesto, sem "
          "veredito inventado)",
          dr.job_url_format_status(
              "https://careers.vetter-pharma.com/job/Ravensburg/abc/")
          is None)
    check("tenant sem medição (SF jobs2web) => None",
          dr.job_url_format_status("https://ace1950.jobs2web.com") is None)
    check("vazio => None", dr.job_url_format_status("") is None)


# ---------------------------------------------------------------------------
# G2 — Arvato: preferência pelo portal oficial (quando ambos existem)
# ---------------------------------------------------------------------------

def test_arvato_portal() -> None:
    section("G2 — agregador geobloqueante × portal oficial (par Arvato)")
    check("constante de calibração: Jaccard mínimo 0.5",
          mc._PORTAL_TWIN_MIN_JACCARD == 0.5)
    check("hosts medidos (registro 23/10): absolventa.de bloqueado; "
          "createyourowncareer.com oficial",
          mc.GEOBLOCKED_AGGREGATOR_HOSTS == ("absolventa.de",)
          and mc.OFFICIAL_PORTAL_HOSTS == ("createyourowncareer.com",))
    check("metadata de tenant: Bertelsmann = portal oficial + apply "
          "SmartRecruiters",
          mc.TENANT_PORTAL_METADATA["bertelsmann"]["official_portal"]
          == "jobsearch.createyourowncareer.com"
          and "smartrecruiters.com/Bertelsmann-Jobs"
          in mc.TENANT_PORTAL_METADATA["bertelsmann"]["apply"])

    # o par real: gêmeo resolvido com overlap forte (0.744 medido)
    twin = mc.official_portal_twin_url(ARVATO_AGG, [ARVATO_AGG, ARVATO_OFF])
    check("gêmeo agregador->oficial resolvido (par Arvato verbatim)",
          twin == ARVATO_OFF["url"], twin[:90])
    jac = mc._desc_jaccard(ARVATO_AGG["description"],
                           ARVATO_OFF["description"])
    check("overlap do par real >= 0.6 (0.744 medido na calibração)",
          jac is not None and jac >= 0.6, f"jaccard={jac:.3f}")

    # linha da fila: link vira o portal, marcado como tal
    off_queued = dict(ARVATO_OFF, not_assessable="desc_curta")
    rows = mc.build_manual_check_rows([
        dict(ARVATO_AGG, not_assessable="desc_vazia"), off_queued])
    by_id = {r["id"]: r for r in rows}
    row = by_id[ARVATO_AGG["id"]]
    check("fila: link direto da linha do agregador = URL do portal oficial",
          row["url"] == ARVATO_OFF["url"], row["url"][:90])
    check("fila: linha marcada portal_oficial=True (+resolved)",
          row["portal_oficial"] is True and row["resolved"] is True)
    check("fila: linha do OFICIAL mantém a própria URL (sem swap reverso)",
          by_id[off_queued["id"]]["url"] == ARVATO_OFF["url"]
          and by_id[off_queued["id"]]["portal_oficial"] is False)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "MANUAL-CHECK.md"
        mc.write_manual_check_md(path, rows, "2026-10-23T09:00:00+00:00")
        text = path.read_text(encoding="utf-8")
    line = [l for l in text.splitlines() if "13435437" in l][0]
    check("MANUAL-CHECK.md: sufixo 'portal oficial — agregador "
          "geobloqueado' na linha",
          "_(link direto: portal oficial — agregador geobloqueado)_" in line,
          line[:160])

    # fail-closed: sem prova de mesma vaga => sem swap
    check("sem gêmeo no ranking => '' (URL do registro permanece)",
          mc.official_portal_twin_url(ARVATO_AGG, [ARVATO_AGG]) == "")
    agg_sem_desc = dict(ARVATO_AGG, description="")
    check("descrição vazia no agregador => '' (fail-closed)",
          mc.official_portal_twin_url(agg_sem_desc,
                                      [agg_sem_desc, ARVATO_OFF]) == "")
    off_sem_desc = dict(ARVATO_OFF, description="")
    check("descrição vazia no oficial => '' (fail-closed)",
          mc.official_portal_twin_url(ARVATO_AGG,
                                      [ARVATO_AGG, off_sem_desc]) == "")
    outro_pais = dict(ARVATO_OFF, country_iso="nl")
    check("país divergente => '' (não é o mesmo job)",
          mc.official_portal_twin_url(ARVATO_AGG,
                                      [ARVATO_AGG, outro_pais]) == "")
    outro_titulo = dict(ARVATO_OFF, title="Werkstudent Einkauf (m/w/x)")
    check("título divergente => '' (não é o mesmo job)",
          mc.official_portal_twin_url(ARVATO_AGG,
                                      [ARVATO_AGG, outro_titulo]) == "")
    desc_disjunta = dict(
        ARVATO_OFF,
        description="Bäckerei Konditorei Handwerk Toast Brot Brötchen " * 30)
    check("título igual mas descrição DISJUNTA (overlap < 0.5) => '' "
          "(prova de mesma vaga exige overlap)",
          mc.official_portal_twin_url(ARVATO_AGG,
                                      [ARVATO_AGG, desc_disjunta]) == "")
    official_queued = dict(ARVATO_OFF, not_assessable="desc_vazia")
    check("vaga já no portal oficial => sem swap (regra só saí do "
          "agregador)",
          mc.official_portal_twin_url(official_queued,
                                      [official_queued, ARVATO_AGG]) == "")
    otros = [dict(ARVATO_AGG, not_assessable="desc_vazia"),
             {"id": "X|workday:x:1", "company": "X", "title": "t",
              "url": "https://acme.example.com/1",
              "description": "procurement supply chain logistics " * 40,
              "country_iso": "de", "not_assessable": "desc_curta"}]
    rows2 = mc.build_manual_check_rows(otros)
    check("URL não-agregador na fila => sem preferência (comportamento "
          "F96 intocado)",
          rows2[1]["url"] == "https://acme.example.com/1"
          and rows2[1]["portal_oficial"] is False)


# ---------------------------------------------------------------------------
# G3 — external_agreement_gate: detector + motivo + prioridade
# ---------------------------------------------------------------------------

def test_external_agreement_gate() -> None:
    section("G3 — novo motivo external_agreement_gate (J&J BE + família)")
    jj1, jj2 = jj_job("R-106104", JJ_106104_PARA), jj_job("R-102271",
                                                          JJ_102271_PARA)
    stats = mc.detect_external_agreement_gates([jj1, jj2])
    check("J&J BE ×2 (parâgrafo verbatim do eligible) acende",
          stats["flagged"] == 2 and stats["checked"] == 2, str(stats))
    check("âncora no flag = trecho literal 'External agreements cannot "
          "be accepted'",
          jj1["external_agreement_gate"]
          == "External agreements cannot be accepted"
          and jj2["external_agreement_gate"]
          == "External agreements cannot be accepted",
          str(jj1["external_agreement_gate"]))
    check("gates reportam job_id/company/anchor",
          stats["gates"][0]["job_id"] == jj1["id"]
          and stats["gates"][0]["anchor"].startswith("External agreements"))

    danone = {"id": "enapply-danone|sf_dataset:icims:27067",
              "company": "enapply-danone", "title": "Indirect Procurement Intern",
              "url": "https://jobs.danone.com/icims/27067",
              "description": DANONE_PARA}
    stats_d = mc.detect_external_agreement_gates([danone])
    check("família 2 (Danone: 3-party agreement signed by your "
          "university) acende — mesma família do gate externo",
          stats_d["flagged"] == 1
          and "signed by your university"
          in danone["external_agreement_gate"],
          str(danone.get("external_agreement_gate")))

    continental = {"id": "Continental AG|sf_dataset:eures:REF99687I",
                   "company": "Continental AG", "title": "t",
                   "url": "https://europa.eu/eures/x", "description":
                   CONTINENTAL_PARA}
    avery = {"id": "Avery Dennison|sf_dataset:smartrecruiters:744000156277589",
             "company": "Avery Dennison", "title": "t",
             "url": "https://jobs.smartrecruiters.com/x",
             "description": AVERY_PARA}
    dboerse = {"id": "Deutsche Börse AG|successfactors:career:1264508401",
               "company": "Deutsche Börse AG", "title": "t",
               "url": "https://dbo.example/1", "description": DBOERSE_PARA}
    stats_neg = mc.detect_external_agreement_gates(
        [continental, avery, dboerse])
    check("matrícula local DE (Continental 'deutschen Hochschule') NÃO "
          "acende — outra família (F99/F106)",
          stats_neg["flagged"] == 0
          and "external_agreement_gate" not in continental, str(stats_neg))
    check("matrícula NL (Avery 'Dutch university') NÃO acende (JÁ coberto "
          "pela F99 como exclusão)",
          "external_agreement_gate" not in avery)
    check("menção genérica de acordo (Deutsche Börse 'can provide an "
          "internship agreement') NÃO acende",
          "external_agreement_gate" not in dboerse)
    check("descrição vazia => fora (sem texto, sem gate)",
          mc.detect_external_agreement_gates(
              [{"id": "x|y:1", "company": "x", "url": "u",
                "description": ""}])["flagged"] == 0)

    # motivo + prioridade
    check("motivo da vaga com o flag => external_agreement_gate",
          mc.motivo_of(jj1) == "external_agreement_gate")
    check("gate perde para wall SAML (a máquina julga o wall primeiro)",
          mc.motivo_of(dict(jj1, liveness_status="unknown",
                            liveness_detail="saml wall (url)"))
          == "saml_wall")
    check("gate vence js_only (sem produtor hoje; gate é acionável)",
          mc.motivo_of(dict(jj1, not_assessable="js_only"))
          == "external_agreement_gate")
    check("dead NUNCA entra na fila (mesmo com o gate)",
          mc.motivo_of(dict(jj1, liveness_status="dead")) is None)
    check("sem gate e avaliável => fora da fila",
          mc.motivo_of({"description": "x" * 900, "id": "a|b:1"}) is None)
    check("vocabulário F96 fixo: MOTIVO_EXTERNAL_AGREEMENT_GATE = "
          "'external_agreement_gate'",
          mc.MOTIVO_EXTERNAL_AGREEMENT_GATE == "external_agreement_gate")
    check("taxonomia na prioridade (entre empty_desc e js_only)",
          mc._MOTIVO_PRIORITY.index(mc.MOTIVO_EMPTY_DESC)
          < mc._MOTIVO_PRIORITY.index(mc.MOTIVO_EXTERNAL_AGREEMENT_GATE)
          < mc._MOTIVO_PRIORITY.index(mc.MOTIVO_JS_ONLY))


# ---------------------------------------------------------------------------
# G4 — generate_manual_check: flag persistida + arquivo (integração)
# ---------------------------------------------------------------------------

def test_generate_integration() -> None:
    section("G4 — generate_manual_check: gates persistidos + fila + md")
    jj1 = jj_job("R-106104", JJ_106104_PARA)
    agg = dict(ARVATO_AGG, not_assessable="desc_vazia")
    limpo = {"id": "Acme|workday:acme:42", "company": "Acme",
             "title": "Internship Procurement", "url": "https://acme/42",
             "description": "x" * 900}
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        (data_dir / "eligible_jobs.json").write_text(
            json.dumps([jj1, ARVATO_OFF, agg, limpo], ensure_ascii=False),
            encoding="utf-8")
        stats = mc.generate_manual_check(
            data_dir, generated_at="2026-10-23T09:30:00+00:00",
            seen_db_path=data_dir / "dataset_seen.db")
        check("stats carrega 'gates' com 1 flag (J&J)",
              stats["gates"]["flagged"] == 1
              and stats["gates"]["gates"][0]["company"] == "Jj",
              str(stats["gates"]))
        check("flag PERSISTIDA no registro (padrão id_collision/F87/F94)",
              "external_agreement_gate" in json.loads(
                  (data_dir / "eligible_jobs.json").read_text(
                      encoding="utf-8"))[0])
        check("fila: 2 linhas (jj com gate + agregador com desc_vazia; a "
              "oficial está limpa)",
              stats["rows"] == 2, str(stats["rows"]))
        md = (data_dir / "MANUAL-CHECK.md").read_text(encoding="utf-8")
        check("MANUAL-CHECK.md: motivo external_agreement_gate na linha J&J",
              "motivo: external_agreement_gate" in md)
        check("MANUAL-CHECK.md: âncora literal na evidência (flag persistida "
              "é o trecho)",
              "External agreements cannot be accepted" in md)
        check("MANUAL-CHECK.md: link do agregador aponta pro portal oficial",
              "jobsearch.createyourowncareer.com" in md
              and "absolventa.de" not in md)


# ---------------------------------------------------------------------------
# G5 — doutrina F87/F96: fila PARALELA, ranking intacto
# ---------------------------------------------------------------------------

def test_queue_parallel() -> None:
    section("G5 — nenhuma vaga sai do ranking/Top-5; ranking não mutado")
    jj1 = jj_job("R-106104", JJ_106104_PARA)
    agg = dict(ARVATO_AGG, not_assessable="desc_vazia")
    ranking = [jj1, agg, ARVATO_OFF,
               {"id": "B|workday:b:43", "company": "B", "title": "Internship",
                "url": "https://b/43", "description": "y" * 900}]
    # ordem de produção: anotadores primeiro (detector muta POR DESENHO —
    # padrão id_collision), DEPOIS a fila
    stats = mc.detect_external_agreement_gates(ranking)
    before_keys = set(jj_job("R-106104", ""))
    after_keys = set(ranking[0])
    check("detector só ADICIONA o campo de flag (sem tocar score/url/ordem)",
          after_keys - before_keys == {"external_agreement_gate"}
          and stats["flagged"] == 1
          and ranking[0]["url"] == jj_job("R-106104", "")["url"])
    snapshot = json.dumps(ranking, sort_keys=True, ensure_ascii=False)
    rows = mc.build_manual_check_rows(ranking)
    after = json.dumps(ranking, sort_keys=True, ensure_ascii=False)
    check("build_manual_check_rows não muta o ranking",
          snapshot == after and len(rows) == 2, f"{len(rows)} linhas")
    top5_text = ranking_digest.format_top5(ranking)
    check("Top-5 mantém a flagada (J&J segue no ranking)",
          "Internship - J&J Beerse (R-106104)" in top5_text,
          top5_text[:120])


# ---------------------------------------------------------------------------
# G6 — contratos: wiring do refresh + zero rede no detector
# ---------------------------------------------------------------------------

def test_contracts() -> None:
    section("G6 — wiring refresh_daily + módulos offline")
    source = inspect.getsource(rd.main)
    check("generate_manual_check segue no fluxo de produção",
          "generate_manual_check" in source)
    check("hook dentro do gate do digest (publication_allowed)",
          source.find("publication_allowed") < source.find(
              "generate_manual_check"))
    check("log do refresh reporta o gate de acordo externo",
          "gate de acordo externo" in source
          and 'mc_stats["gates"]["flagged"]' in source)
    mc_src = (ROOT / "scripts" / "manual_check.py").read_text(encoding="utf-8")
    bad = [t for t in ("import requests", "import httpx", "urlopen",
                       "urllib.request") if t in mc_src]
    check("detector/link-preference SEM rede (puro, tempdir nos testes)",
          not bad, f"bad={bad}")
    dr_src = (ROOT / "src" / "internship_finder" / "discovery_rules.py"
              ).read_text(encoding="utf-8")
    check("camada F105 no discovery_rules sem rede nova (contrato E1 do "
          "test_f76_1 preservado)",
          "TENANT_JOB_URL_FORMATS" in dr_src
          and "import requests" not in dr_src and "urlopen" not in dr_src)
    import ci_discover_tests  # noqa: F401  (scripts/ no sys.path)
    names = ci_discover_tests.discover_tests()
    check("membership: test_f105 na suíte descoberta do CI (F78)",
          "test_f105" in names, f"{len(names)} suítes")


def main() -> int:
    test_vetter_v2()
    test_arvato_portal()
    test_external_agreement_gate()
    test_generate_integration()
    test_queue_parallel()
    test_contracts()
    print(f"\n==== test_f105: {CHECKS} checks, "
          f"{len(FAILURES)} falha(s) ====")
    if FAILURES:
        for name in FAILURES:
            print(f"  [FAIL] {name}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
