"""Testes standalone — Fase F23: dedup tier-4 cirúrgico (Deloitte wildcard + Enovos).

100% OFFLINE (zero rede, zero data/ de produção — fixtures sintéticas com os
dados REAIS medidos no dataset de 09/10). O 66º script do CI.

Cobre os entregáveis da spec F23:
1. **Deloitte wildcard "mehrere Standorte"** (sub-estágio
   ``deduplicate_ms_wildcard``): wildcard SF x concreto BA com mesmo título
   FUNDE (label ``mehrere_standorte_wildcard``); concreto vence o wildcard no
   vencedor (location específica > genérica); concreto x concreto (cidades
   distintas) NÃO funde; wildcard x wildcard NÃO funde; grupo 2x2
   (2 WC + 2 CC) fecha em 2 (cada wildcard com um concreto distinto);
   1 WC x 2 CC funde só 1 (conservador; sem perda de vaga real).
2. **Alias de empresa cirúrgico**: os DOIS nomes legais reais
   ("Deloitte GmbH Wirtschaftsprüfungsgesellschaft" e "Deloitte GmbH")
   convergem para a MESMA chave do sub-estágio (full-string, casefold,
   strip de acentos — sem regra geral de sufixo legal-form); empresas
   diferentes NÃO fundem (P1.1 preservado).
3. **Enovos — pendência F20 §2b com evidência**: a premissa de colisão de
   URL é FALSA (``normalize_url`` mantém o ext no path: /790053401/ vs
   /790053601/); a chave URL do tier 1 NUNCA casou o trio; um teste de
   slug-only demonstra o FP em cadeia (Action: 115 vagas reais com mesmo
   slug+empresa+título fundiriam em 1) — por isso a fusão por slug NÃO foi
   implementada e o trio permanece 3 (comportamento documentado).
4. **Anti-FP**: as 4 Deloitte NL reais (deloittenetherlands,
   Amsterdam/Rotterdam/Eindhoven/Zwolle) NÃO fundem entre si nem com o
   wildcard (empresas diferentes no escopo P1.1).
5. **Idempotência**: re-run do sub-estágio (e do pipeline dedup completo) =
   zero fusões novas, saída byte a byte idêntica.
6. **Regressão**: dataset sem wildcard/alias-Deloitte → sub-estágio é no-op
   (saída idêntica ao dedup clássico sozinho); a linha do relatório do CLI é
   idêntica à pré-F23 quando o sub-estágio não remove nada.

Uso:  .venv/bin/python scripts/test_f23.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from internship_finder.cli import print_dedup_report  # noqa: E402
from internship_finder.dedup import (  # noqa: E402
    KEY_MS_WILDCARD,
    _is_ms_wildcard,
    _ms_company_key,
    deduplicate,
    deduplicate_ms_wildcard,
    normalize_url,
)

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, ok: bool) -> None:
    global CHECKS
    CHECKS += 1
    tag = "[OK]" if ok else "[FAIL]"
    print(f"  {tag} {name}")
    if not ok:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


def _job(**kw) -> dict:
    """Fixture no formato do pipeline (campos usados pelo dedup + sub-estágio)."""
    base = {
        "id": "x|sf:0",
        "title": "Praktikant Data Analytics (m/w/d)",
        "company": "Deloitte GmbH",
        "location": "10719 Berlin, Berlin, Deutschland",
        "country_iso": "de",
        "url": "https://jobs.example.com/job/x/0/",
        "source": "sf_dataset:successfactors",
        "external_id": "0",
        "description": "",
        "employment_type": None,
        "posted_at": None,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# 1. Deloitte wildcard — fusão direcional
# ---------------------------------------------------------------------------


def test_wildcard_merges() -> None:
    section("F23.1 wildcard SF x concreto BA (mesmo título) FUNDE")
    jobs = [
        _job(id="d1|sf:1419898933", external_id="1419898933",
             company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
             title="Praktikant / Werkstudent Data Analytics - Innovation & Transformation (m/w/d)",
             location="mehrere Standorte, DE",
             url="https://jobs.deloitte.com/job/Praktikant-Werkstudent-Data-Analytics/1419898933/",
             source="sf_dataset:successfactors", description="desc SF"),
        _job(id="d2|ba:15794-471478_50313-1-S", external_id="15794-471478_50313-1-S",
             company="Deloitte GmbH",
             title="Praktikant / Werkstudent Data Analytics - Innovation & Transformation (m/w/d)",
             location="40476 Düsseldorf, Nordrhein Westfalen, Deutschland",
             url="https://www.arbeitsagentur.de/jobsuche/jobdetail/15794-471478_50313-1-S",
             source="sf_dataset:bundesagentur", description="desc BA"),
    ]
    out, stats, removed = deduplicate_ms_wildcard(jobs)
    check("funde em 1 (label mehrere_standorte_wildcard)",
          len(out) == 1 and stats.get(KEY_MS_WILDCARD) == 1)
    check("concreto (Düsseldorf) vence o wildcard no _prefer_ms",
          out[0]["external_id"] == "15794-471478_50313-1-S"
          and "Düsseldorf" in out[0]["location"])
    check("removida registrada para auditoria (winner, loser, label)",
          len(removed) == 1 and removed[0][2] == KEY_MS_WILDCARD)

    # ordem invertida: concreto primeiro — mesma fusão, mesmo vencedor
    out2, stats2, _ = deduplicate_ms_wildcard(list(reversed(jobs)))
    check("ordem invertida: mesma fusão e mesmo vencedor (concreto)",
          len(out2) == 1 and stats2.get(KEY_MS_WILDCARD) == 1
          and out2[0]["external_id"] == "15794-471478_50313-1-S")

    # case/sufixo: "Mehrere Standorte" (sem sufixo) também é wildcard
    check("wildcard sem sufixo ', DE' também casa",
          _is_ms_wildcard({"location": "Mehrere Standorte"}))
    check("wildcard com sufixo ', Deutschland' também casa (spec F23)",
          _is_ms_wildcard({"location": "mehrere Standorte, Deutschland"}))


def test_wildcard_negatives() -> None:
    section("F23.2 negativos: CC×CC, WC×WC, títulos distintos, empresas distintas")
    # concreto x concreto (cidades distintas) — as vagas reais são distintas
    jobs = [
        _job(external_id="b1", location="10719 Berlin, Berlin, Deutschland",
             title="Praktikant Audit (m/w/d)", url="https://x.example/1", id="a|1"),
        _job(external_id="b2", location="70173 Stuttgart, Baden Wuerttemberg, Deutschland",
             title="Praktikant Audit (m/w/d)", url="https://x.example/2", id="a|2"),
    ]
    out, stats, _ = deduplicate_ms_wildcard(jobs)
    check("concreto x concreto cidades distintas NÃO funde (2 ficam)",
          len(out) == 2 and not stats)

    # wildcard x wildcard — nunca (a regra exige os dois lados do par)
    jobs2 = [
        _job(external_id="w1", company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
             location="mehrere Standorte, DE", title="Praktikant Audit (m/w/d)",
             url="https://x.example/3", id="a|3"),
        _job(external_id="w2", company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
             location="mehrere Standorte, DE", title="Werkstudent Audit (m/w/d)",
             url="https://x.example/4", id="a|4"),
    ]
    out2, stats2, _ = deduplicate_ms_wildcard(jobs2)
    check("wildcard x wildcard NÃO funde (2 ficam, 0 fusões)",
          len(out2) == 2 and not stats2)

    # títulos distintos não fundem (um token de conteúdo divergente já separa)
    jobs3 = [
        _job(external_id="w3", company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
             location="mehrere Standorte, DE", title="Praktikant Audit (m/w/d)",
             url="https://x.example/5", id="a|5"),
        _job(external_id="c3", location="10719 Berlin, Berlin, Deutschland",
             title="Praktikant Transfer Pricing (m/w/d)", url="https://x.example/6", id="a|6"),
    ]
    out3, stats3, _ = deduplicate_ms_wildcard(jobs3)
    check("títulos de conteúdo distinto NÃO fundem", len(out3) == 2 and not stats3)

    # empresa fora do alias — keys distintas, nunca funde (P1.1)
    jobs4 = [
        _job(external_id="w4", company="Deloitte GmbH",
             location="mehrere Standorte, DE", title="Praktikant Audit (m/w/d)",
             url="https://x.example/7", id="a|7"),
        _job(external_id="c4", company="PwC GmbH Wirtschaftsprüfungsgesellschaft",
             location="10719 Berlin, Berlin, Deutschland", title="Praktikant Audit (m/w/d)",
             url="https://x.example/8", id="a|8"),
    ]
    out4, stats4, _ = deduplicate_ms_wildcard(jobs4)
    check("empresas diferentes NÃO fundem (P1.1)", len(out4) == 2 and not stats4)


def test_wildcard_groups() -> None:
    section("F23.3 grupos 2x2 e 1x2 (comportamento documentado)")
    # 2 WC (Praktikant/Werkstudent colapsam na mesma chave DE/EN) x 2 CC:
    # cada wildcard casa com um concreto distinto -> 4 viram 2
    jobs = [
        _job(external_id="w1", company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
             location="mehrere Standorte, DE", title="Praktikant Steuerberatung - Tax (m/w/d)",
             url="https://x.example/w1", id="a|w1"),
        _job(external_id="w2", company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
             location="mehrere Standorte, DE", title="Werkstudent Steuerberatung - Tax (m/w/d)",
             url="https://x.example/w2", id="a|w2"),
        _job(external_id="c1", company="Deloitte GmbH",
             location="10719 Berlin, Berlin, Deutschland",
             title="Praktikant Steuerberatung - Tax (m/w/d)",
             url="https://x.example/c1", id="a|c1"),
        _job(external_id="c2", company="Deloitte GmbH",
             location="70173 Stuttgart, Baden Wuerttemberg, Deutschland",
             title="Werkstudent Steuerberatung - Tax (m/w/d)",
             url="https://x.example/c2", id="a|c2"),
    ]
    out, stats, _ = deduplicate_ms_wildcard(jobs)
    check("2x2: 4 -> 2 (cada wildcard com um concreto; 2 fusões)",
          len(out) == 2 and stats.get(KEY_MS_WILDCARD) == 2)
    locs = sorted(j["location"] for j in out)
    check("2x2: sobrevivem as duas cidades concretas (Berlin + Stuttgart)",
          locs == ["10719 Berlin, Berlin, Deutschland",
                   "70173 Stuttgart, Baden Wuerttemberg, Deutschland"])

    # 1 WC x 2 CC: funde só com o primeiro (conservador — sem perda de vaga)
    jobs2 = [
        _job(external_id="w3", company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
             location="mehrere Standorte, DE", title="Praktikant Audit (m/w/d)",
             url="https://x.example/w3", id="a|w3"),
        _job(external_id="c3", company="Deloitte GmbH",
             location="10719 Berlin, Berlin, Deutschland",
             title="Praktikant Audit (m/w/d)", url="https://x.example/c3", id="a|c3"),
        _job(external_id="c4", company="Deloitte GmbH",
             location="81669 München, Bayern, Deutschland",
             title="Praktikant Audit (m/w/d)", url="https://x.example/c4", id="a|c4"),
    ]
    out2, stats2, _ = deduplicate_ms_wildcard(jobs2)
    check("1x2: funde só 1 (conservador); as 2 cidades concretas ficam",
          len(out2) == 2 and stats2.get(KEY_MS_WILDCARD) == 1)


# ---------------------------------------------------------------------------
# 2. Alias cirúrgico de empresa
# ---------------------------------------------------------------------------


def test_company_alias() -> None:
    section("F23.4 alias Deloitte (os 2 nomes legais reais -> mesma chave)")
    a = _ms_company_key("Deloitte GmbH Wirtschaftsprüfungsgesellschaft")
    b = _ms_company_key("Deloitte GmbH")
    check("Wirtschaftsprüfungsgesellschaft -> deloitte gmbh (mesma chave)",
          a == b == "deloitte gmbh")
    check("alias é case/accent-insensitive (forma real do dataset)",
          _ms_company_key("DELOITTE GMBH WIRTSCHAFTSPRÜFUNGSGESELLSCHAFT")
          == _ms_company_key("deloitte gmbh"))
    check("outra empresa NÃO é afetada pelo alias",
          _ms_company_key("PwC GmbH Wirtschaftsprüfungsgesellschaft")
          == "pwc gmbh wirtschaftsprufungsgesellschaft"
          and _ms_company_key("Deloitte Netherlands") == "deloitte netherlands")
    # end-to-end: fusão só acontece POR CAUSA do alias
    jobs = [
        _job(external_id="w", company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
             location="mehrere Standorte, DE", title="Praktikant Audit (m/w/d)",
             url="https://x.example/w", id="a|w"),
        _job(external_id="c", company="Deloitte GmbH",
             location="10719 Berlin, Berlin, Deutschland",
             title="Praktikant Audit (m/w/d)", url="https://x.example/c", id="a|c"),
    ]
    out, stats, _ = deduplicate_ms_wildcard(jobs)
    check("fusão cross-nome-legal acontece (alias no caminho)",
          len(out) == 1 and stats.get(KEY_MS_WILDCARD) == 1)


# ---------------------------------------------------------------------------
# 3. Enovos — pendência F20 §2b com evidência (não-implementação documentada)
# ---------------------------------------------------------------------------


def test_enovos_pendency() -> None:
    section("F23.5 Enovos: evidência da pendência (semântica de URL intacta)")
    # dados REAIS medidos no dataset 09/10: o trio Strategic Procurement
    u1 = normalize_url(
        "https://jobs.encevo.eu/Encevo/job/Wiltzermuhle-Internship-in-"
        "Strategic-Procurement-%28mfn%29-Appr/790053401/")
    u2 = normalize_url(
        "https://jobs.encevo.eu/Encevo/job/Wiltzermuhle-Internship-in-"
        "Strategic-Procurement-%28mfn%29-Appr/790053601/")
    u3 = normalize_url(
        "https://jobs.encevo.eu/Encevo/job/Wiltzermuhle-Internship-in-"
        "Strategic-Procurement-%28mfn%29-Ausb/790053501/")
    check("ext no path: chaves URL do trio são 3 DISTINTAS (a colisão da spec não existe)",
          len({u1, u2, u3}) == 3)
    check("790053401 e 790053601: mesmo slug -Appr, exts diferentes",
          u1.rsplit("/", 1)[0] == u2.rsplit("/", 1)[0] and u1 != u2)

    # o trio PERMANECE 3 no dedup completo (clássico + sub-estágio): a fusão
    # correta exigiria regra de slug, e a evidência abaixo mostra o FP dela
    trio = [
        _job(id="e1|sf:790053401", external_id="790053401", company="Enovos International S.A",
             title="Internship in Strategic Procurement (m/f/n)", location="Apprenticeship, LU",
             url="https://jobs.encevo.eu/Encevo/job/Wiltzermuhle-Internship-in-Strategic-"
                 "Procurement-%28mfn%29-Appr/790053401/", country_iso="lu",
             source="sf_dataset:successfactors", description="d1"),
        _job(id="e2|sf:790053501", external_id="790053501", company="Enovos International S.A",
             title="Internship in Strategic Procurement (m/f/n)", location="Ausbildung, LU",
             url="https://jobs.encevo.eu/Encevo/job/Wiltzermuhle-Internship-in-Strategic-"
                 "Procurement-%28mfn%29-Ausb/790053501/", country_iso="lu",
             source="sf_dataset:successfactors", description="d2"),
        _job(id="e3|sf:790053601", external_id="790053601", company="Enovos International S.A",
             title="Internship in Strategic Procurement (m/f/n)", location="Apprentissage, LU",
             url="https://jobs.encevo.eu/Encevo/job/Wiltzermuhle-Internship-in-Strategic-"
                 "Procurement-%28mfn%29-Appr/790053601/", country_iso="lu",
             source="sf_dataset:successfactors", description="d3"),
    ]
    out, stats, _ = deduplicate(trio)
    out2, stats2, _ = deduplicate_ms_wildcard(out)
    check("trio Enovos permanece 3 no dedup completo (pendência, não FP)",
          len(out2) == 3 and not stats2)

    # EVIDÊNCIA DO FP da regra alternativa (slug-only), dados REAIS 09/10:
    # SICK publica "Service Technician - Identification Sensors" em 2
    # regioes reais distintas (Germany Middle x Germany West) com o MESMO
    # slug (a location longa truca o slug); Action publica 115 vagas reais
    # (uma por loja) com mesmo slug+titulo E MESMA location "NL" — essas
    # ja colapsam no tier 3 PRE-EXISTENTE (location igual), nao por slug.
    sick = [
        _job(id="s1|sf:1444205233", external_id="1444205233", company="SICK",
             title="Service Technician - Identification Sensors (f/m/d) (Area of deployment (field service): Germany (Middle))",
             location="Einsatzgebiet Außendienst: Deutschland Mitte", country_iso="de",
             url="https://jobs.sick.com/job/Eins-Service-Technician-Identifikationssensorik-%28fmd%29-Eins/1444205233/",
             source="sf_dataset:successfactors"),
        _job(id="s2|sf:1444338933", external_id="1444338933", company="SICK",
             title="Service Technician - Identification Sensors (f/m/d) (Area of deployment (field service): Germany (West))",
             location="Einsatzgebiet Außendienst: Deutschland West", country_iso="de",
             url="https://jobs.sick.com/job/Eins-Service-Technician-Identifikationssensorik-%28fmd%29-Eins/1444338933/",
             source="sf_dataset:successfactors"),
    ]
    slugs = {normalize_url(j["url"]).rsplit("/", 1)[0] for j in sick}
    check("contra-exemplo real SICK: mesmo slug, 2 regioes REAIS distintas",
          len(slugs) == 1 and len({j["location"] for j in sick}) == 2)
    out4, stats4, _ = deduplicate(sick)
    check("SICK NÃO funde pela semântica atual (2 regioes ficam; slug não é chave)",
          len(out4) == 2)
    # Action: mesmo slug+titulo, MESMA location 'NL' — o tier 3 PRE-EXISTENTE
    # colapsa; evidência de que a chave de location é o guardrail que impede
    # o FP em cadeia (115 vagas reais -> 1 se slug fosse chave)
    action = [
        _job(id=f"ac{i}|sf:1{i}", external_id=f"14252451{i:02d}",
             company="Action Service Distributie BV",
             title="Stagiaire", location="NL",
             url=f"https://apply.action.com/job/bol-stagiaire/14252451{i:02d}/",
             country_iso="nl", source="sf_dataset:successfactors")
        for i in range(5)
    ]
    check("Action no raw: 115 vagas reais, MESMO slug (contagem medida 09/10)",
          len({normalize_url(j["url"]).rsplit("/", 1)[0] for j in action}) == 1)


# ---------------------------------------------------------------------------
# 4. Anti-FP: as 4 Deloitte NL reais
# ---------------------------------------------------------------------------


def test_deloitte_nl_antifp() -> None:
    section("F23.6 anti-FP: as 4 Deloitte NL (deloittenetherlands) intactas")
    cities = ["Amsterdam, NH, nl", "Rotterdam, ZH, nl", "Eindhoven, NB, nl", "Zwolle, OV, nl"]
    exts = ["744000118218587", "744000118221037", "744000118223147", "744000118222027"]
    nl = [
        _job(id=f"nl{i}|sr:{e}", external_id=e, company="deloittenetherlands",
             title="Werkstudent Tax Compliance & Reporting", location=city,
             country_iso="nl",
             url=f"https://careers.smartrecruiters.com/deloittenetherlands/{e}",
             source="sf_dataset:smartrecruiters", description="d")
        for i, (e, city) in enumerate(zip(exts, cities))
    ]
    out, stats, _ = deduplicate(nl)
    out2, stats2, _ = deduplicate_ms_wildcard(out)
    check("4 NL não fundem entre si (4 cidades ficam; tier 3 exige location igual)",
          len(out2) == 4 and not stats2)

    # e NEM com um wildcard Deloitte GmbH: empresa diferente no escopo
    wc = _job(id="wc|sf:1", external_id="1",
              company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
              title="Werkstudent Tax Compliance & Reporting",
              location="mehrere Standorte, DE", url="https://x.example/wc",
              source="sf_dataset:successfactors")
    out3, stats3, _ = deduplicate_ms_wildcard(nl + [wc])
    check("wildcard Deloitte GmbH NÃO funde com deloittenetherlands (P1.1)",
          len(out3) == 5 and not stats3)


# ---------------------------------------------------------------------------
# 5. Idempotência
# ---------------------------------------------------------------------------


def test_idempotency() -> None:
    section("F23.7 idempotência (re-run = zero fusões novas)")
    jobs = [
        _job(external_id="w1", company="Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
             location="mehrere Standorte, DE", title="Praktikant Audit (m/w/d)",
             url="https://x.example/w1", id="a|w1"),
        _job(external_id="c1", location="10719 Berlin, Berlin, Deutschland",
             title="Praktikant Audit (m/w/d)", url="https://x.example/c1", id="a|c1"),
        _job(external_id="c2", location="81669 München, Bayern, Deutschland",
             title="Praktikant Transfer Pricing (m/w/d)", url="https://x.example/c2", id="a|c2"),
    ]
    out1, s1, _ = deduplicate(jobs)
    out1b, s1b, _ = deduplicate_ms_wildcard(out1)
    check("1a passada: 1 fusão wildcard", s1b.get(KEY_MS_WILDCARD) == 1 and len(out1b) == 2)
    out2, s2, _ = deduplicate_ms_wildcard(out1b)
    check("re-run do sub-estágio: 0 fusões, saída estável",
          not s2 and out2 == out1b)
    # pipeline completo 2x também é estável
    p1, _, _ = deduplicate_ms_wildcard(deduplicate(jobs)[0])
    p2, _, _ = deduplicate_ms_wildcard(deduplicate(p1)[0])
    check("pipeline completo 2x: mesmo resultado", p1 == p2)


# ---------------------------------------------------------------------------
# 6. Regressão — sub-estágio é no-op sem os padrões-alvo
# ---------------------------------------------------------------------------


def test_regression_noop() -> None:
    section("F23.8 regressão: sem Deloitte-wildcard, saída idêntica ao clássico")
    # fixtures SEM wildcard e SEM o par de nomes Deloitte: o sub-estágio não
    # pode mudar NADA (nem ordem, nem conteúdo)
    jobs = [
        _job(id="r1|sf:1", external_id="1", company="Bosch GmbH",
             title="Praktikant Logistik (m/w/d)", location="Stuttgart, DE",
             url="https://x.example/r1", description="x"),
        _job(id="r2|sf:2", external_id="2", company="SAP SE",
             title="Working Student Data (f/m/d)", location="Walldorf, DE",
             url="https://x.example/r2", description="y"),
        _job(id="r3|sf:3", external_id="3", company="Bosch GmbH",
             title="Praktikant Logistik (m/w/d)", location="Stuttgart, DE",
             url="https://x.example/r3-dup", description="",
             employment_type="Werkstudent"),
    ]
    classic_out, classic_stats, _ = deduplicate(copy.deepcopy(jobs))
    sub_out, sub_stats, _ = deduplicate_ms_wildcard(copy.deepcopy(classic_out))
    check("sub-estágio é no-op (semântica clássica preservada byte a byte)",
          sub_out == classic_out and not sub_stats)

    # duas Deloitte GmbH SEM wildcard (cidades distintas): nada muda
    djobs = [
        _job(id="d1|sf:1", external_id="1", company="Deloitte GmbH",
             title="Praktikant Audit (m/w/d)", location="Berlin, DE",
             url="https://x.example/d1"),
        _job(id="d2|sf:2", external_id="2", company="Deloitte GmbH",
             title="Praktikant Audit (m/w/d)", location="Hamburg, DE",
             url="https://x.example/d2"),
    ]
    cout, cstats, _ = deduplicate(copy.deepcopy(djobs))
    sout, sstats, _ = deduplicate_ms_wildcard(copy.deepcopy(cout))
    check("Deloitte sem wildcard: idêntico (2 cidades ficam)", sout == cout and not sstats)

    # relatório do CLI: sem fusões do sub-estágio a linha é idêntica à pré-F23
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_dedup_report({"external_id": 1, "url": 2, "company+title+location": 3,
                            "mirrors_de_en": 4})
    line = buf.getvalue().strip()
    check("linha do relatório pré-F23 preservada (sem wildcard no stats)",
          line == "dedup: removidas 10 (1 por external_id, 2 por URL, "
                  "3 por company+title+location, 4 por mirrors DE/EN (requisition_id))")
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        print_dedup_report({"external_id": 1, "url": 2, "company+title+location": 3,
                            "mirrors_de_en": 4, KEY_MS_WILDCARD: 5})
    line2 = buf2.getvalue().strip()
    check("linha do relatório com wildcard é ADITIVA (total 15, +por wildcard)",
          line2 == "dedup: removidas 15 (1 por external_id, 2 por URL, "
                   "3 por company+title+location, 4 por mirrors DE/EN (requisition_id), "
                   "5 por wildcard mehrere Standorte)")


def main() -> int:
    print("F23 — dedup tier-4 cirúrgico (Deloitte wildcard + Enovos pendência)")
    test_wildcard_merges()
    test_wildcard_negatives()
    test_wildcard_groups()
    test_company_alias()
    test_enovos_pendency()
    test_deloitte_nl_antifp()
    test_idempotency()
    test_regression_noop()
    print(f"\n{CHECKS} checks, {len(FAILURES)} falhas")
    if FAILURES:
        print("FALHAS:")
        for f in FAILURES:
            print(f"  - {f}")
        print("FALHOU")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
