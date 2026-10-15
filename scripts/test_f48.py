#!/usr/bin/env python3
"""F48 — dedup CROSS-FONTE por campos estruturados (espelhos EN/DE) — 100% offline.

Cobre o contrato da fase:

A. unidades de normalizacao: cidade (CEP fora + CITY_ALIASES), identidade de
   empresa (formas legais/qualificadores fora), salario (separadores ambiguos);
B. PAR BAYER VERBATIM do print 13/10 (titulos EN/DE, empresa e local em
   FORMATOS diferentes por fonte) -> funde, canonical = registro do dataset,
   nao-canonico recebe `duplicate_of`;
C. PAR BAYER VERBATIM do print 14/10 (os dois lados em DE, local
   "Nordrhein-Westfalen" hifenizado x "Nordrhein Westfalen") -> funde;
D. contra-casos LEGITIMOS verbatim que DEVEM sobreviver: Google x3 (mesmo
   titulo, 3 paises/cidades), indiecampers x4 (mesmo titulo, 4 cidades) e o
   par MTU (duas razoes sociais do grupo, cidades distintas);
E. empresas distintas com titulo identico na MESMA cidade -> NAO casa;
F. guardrails: country divergente e salary divergente reprovam; salary igual
   em formatos diferentes aprova; employment_type divergente NAO reprova
   (vocabulario incompativel entre fontes — decisao documentada da fase);
G. par da MESMA fonte nao e alvo deste estagio; o par DE/EN ja fundido pelo
   tier 4 (F5) continua fundido pelo mecanismo ANTIGO (regressao);
H. canonical intacto (nenhum campo alterado), `duplicate_of` so na duplicata,
   estatisticas/removidas coerentes, determinismo e idempotencia;
I. integracao com o pipeline (`run_filter_pipeline`): a duplicata sai da
   saida e o registro `type: dedup_cross_source` entra na metrica diaria;
J. `.github/workflows/ci.yml` contem test_f48 no array `tests=`.

Convencoes do repo: [OK]/[FAIL], termina "TUDO OK" (exit 0). Sem rede, sem
LLM, sem data/ de producao — o A/B no universo real esta no relatorio da fase.

Fixtures: campos ESTRUTURAIS ipsis literis dos archives congelados
(`data/archive/20261014T090001Z` = print 13/10, `.../20261015T090002Z` =
print 14/10, `.../20261013T090001Z` = print 12/10). `description` foi omitida
(o estagio nao a usa; o par Bayer tem o mesmo texto EN/DE e o salario
identico esta nela — ver SALARIO_* abaixo). Fixtures sinteticas estao
rotuladas como tal.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.cli import print_dedup_report, run_filter_pipeline  # noqa: E402
from internship_finder.cross_source_dedup import (  # noqa: E402
    KEY_CROSS_SOURCE,
    city_key,
    company_identity,
    cross_source_provenance,
    deduplicate_cross_source,
    salary_value,
)
from internship_finder.dedup import (  # noqa: E402
    KEY_COMPANY_TITLE_LOCATION_DE_EN,
    deduplicate,
)

_FAILS = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global _FAILS
    tag = "[OK]" if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f" ({extra})" if extra and not cond else ""))
    if not cond:
        _FAILS += 1


def section(title: str) -> None:
    print(f"\n== {title}")


# ---------------------------------------------------------------------------
# Evidencia verbatim do salario identico do par Bayer (vive na description;
# o campo estruturado `salary` esta vazio nos 4 prints medidos).
# ---------------------------------------------------------------------------

SALARIO_DE = "erwartet Dich eine attraktive Vergütung von 2.280 € brutto pro Monat"
SALARIO_EN = "you can expect an attractive salary of € 2.280 gross per month"

# --------------------------------------------------------------------------
# FIXTURES VERBATIM — par Bayer (print 13/10, archive 20261014T090001Z)
# --------------------------------------------------------------------------

BAYER_13_BA = {
    "id": "Bayer AG Pharmaceuticals|sf_dataset:bundesagentur:12708-1623235-1-S",
    "source": "sf_dataset:bundesagentur",
    "external_id": "12708-1623235-1-S",
    "company": "Bayer AG Pharmaceuticals",
    "title": "Praktikant*in Analytics Advisory & Data Democratization / SC&L Analytics (alle Geschlechter)",
    "location": "51373 Leverkusen, Nordrhein Westfalen, Deutschland",
    "country": "de",
    "employment_type": "FULL_TIME",
    "posted_at": "2026-08-25T00:00:00",
    "salary": None,
    "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/12708-1623235-1-S",
}

BAYER_13_SF = {
    "id": "Bayer|successfactors:jobs:1429117033",
    "source": "successfactors:jobs",
    "external_id": "1429117033",
    "company": "Bayer",
    "title": "Internship Analytics Advisory & Data Democratization / SC&L Analytics (all genders)",
    "location": "Leverkusen, North Rhine Westfalia, DE",
    "country": "de",
    "employment_type": None,
    "posted_at": None,
    "salary": None,
    "url": (
        "https://jobs.bayer.com/job/Leverkusen-Internship-Analytics-Advisory-"
        "&-Data-Democratization-SC&L-Analytics-%28all-genders%29-Nort/1429117033/"
    ),
}

# --------------------------------------------------------------------------
# FIXTURES VERBATIM — par Bayer (print 14/10, archive 20261015T090002Z),
# os DOIS lados em DE (a fonte SF publicou o anuncio alemao nesse dia).
# --------------------------------------------------------------------------

BAYER_14_SF = {
    "id": "Bayer|successfactors:jobs:1429117133",
    "source": "successfactors:jobs",
    "external_id": "1429117133",
    "company": "Bayer",
    "title": "Praktikant*in Analytics Advisory & Data Democratization / SC&L Analytics (alle Geschlechter)",
    "location": "Leverkusen, Nordrhein-Westfalen, DE",
    "country": "de",
    "employment_type": None,
    "posted_at": None,
    "salary": None,
    "url": (
        "https://jobs.bayer.com/job/Leverkusen-Praktikantin-Analytics-Advisory-"
        "&-Data-Democratization-SC&L-Analytics-%28alle-Geschlechter%29-Nord/1429117133/"
    ),
}

# --------------------------------------------------------------------------
# FIXTURES VERBATIM — contra-casos legitimos (print 12/10, 20261013T090001Z)
# --------------------------------------------------------------------------

GOOGLE_X3 = [
    {
        "id": "Google|sf_dataset:google:129378231382876870",
        "source": "sf_dataset:google",
        "external_id": "129378231382876870",
        "company": "Google",
        "title": "Data Center Technician Intern, 2027",
        "location": "Saint-Ghislain, Belgium",
        "country": "be",
        "url": (
            "https://www.google.com/about/careers/applications/jobs/results/"
            "129378231382876870-data-center-technician-intern-2027"
        ),
    },
    {
        "id": "Google|sf_dataset:google:139493738358416070",
        "source": "sf_dataset:google",
        "external_id": "139493738358416070",
        "company": "Google",
        "title": "Data Center Technician Intern, 2027",
        "location": "Eemshaven, Netherlands",
        "country": "nl",
        "url": (
            "https://www.google.com/about/careers/applications/jobs/results/"
            "139493738358416070-data-center-technician-intern-2027"
        ),
    },
    {
        "id": "Google|sf_dataset:google:85160271760237254",
        "source": "sf_dataset:google",
        "external_id": "85160271760237254",
        "company": "Google",
        "title": "Data Center Technician Intern, 2027",
        "location": "Hamina, Finland",
        "country": "fi",
        "url": (
            "https://www.google.com/about/careers/applications/jobs/results/"
            "85160271760237254-data-center-technician-intern-2027"
        ),
    },
]

INDIECAMPERS_X4 = [
    {
        "id": "indiecampers|sf_dataset:greenhouse:8800656002",
        "source": "sf_dataset:greenhouse",
        "external_id": "8800656002",
        "company": "indiecampers",
        "title": "Tourism & Operations Internship",
        "location": "Düsseldorf, Nordrhein-Westfalen, Germany",
        "country": "de",
        "posted_at": "2026-09-15T06:31:34-04:00",
        "url": "https://indiecampers.com/discover/en-us/careers/8800656002?gh_jid=8800656002",
    },
    {
        "id": "indiecampers|sf_dataset:greenhouse:8764854002",
        "source": "sf_dataset:greenhouse",
        "external_id": "8764854002",
        "company": "indiecampers",
        "title": "Tourism & Operations Internship",
        "location": "Brussels Hoofstedelijk Gewest#Région de Bruxelles-Capitale, Belgium",
        "country": "be",
        "posted_at": "2026-09-14T11:16:07-04:00",
        "url": "https://indiecampers.com/discover/en-us/careers/8764854002?gh_jid=8764854002",
    },
    {
        "id": "indiecampers|sf_dataset:greenhouse:8765548002",
        "source": "sf_dataset:greenhouse",
        "external_id": "8765548002",
        "company": "indiecampers",
        "title": "Tourism & Operations Internship",
        "location": "Helsinki, Uusimaa, Finland",
        "country": "fi",
        "posted_at": "2026-09-14T11:24:27-04:00",
        "url": "https://indiecampers.com/discover/en-us/careers/8765548002?gh_jid=8765548002",
    },
    {
        "id": "indiecampers|sf_dataset:greenhouse:8768901002",
        "source": "sf_dataset:greenhouse",
        "external_id": "8768901002",
        "company": "indiecampers",
        "title": "Tourism & Operations Internship",
        "location": "Amsterdam, Noord-Holland, Netherlands",
        "country": "nl",
        "posted_at": "2026-09-14T11:40:38-04:00",
        "url": "https://indiecampers.com/discover/en-us/careers/8768901002?gh_jid=8768901002",
    },
]

MTU_X2 = [
    {
        "id": "MTU Aero Engines AG|sf_dataset:bundesagentur:12951-9b62dc68-acd6-48ee--S",
        "source": "sf_dataset:bundesagentur",
        "external_id": "12951-9b62dc68-acd6-48ee--S",
        "company": "MTU Aero Engines AG",
        "title": "Praktikum Einkauf (all genders)",
        "location": "80995 München, Bayern, Deutschland",
        "country": "de",
        "employment_type": "FULL_TIME",
        "posted_at": "2026-06-11T00:00:00",
        "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/12951-9b62dc68-acd6-48ee--S",
    },
    {
        "id": "MTU Maintenance Hannover GmbH|sf_dataset:bundesagentur:12951-4da97482-4abd-40db--S",
        "source": "sf_dataset:bundesagentur",
        "external_id": "12951-4da97482-4abd-40db--S",
        "company": "MTU Maintenance Hannover GmbH",
        "title": "Praktikum Einkauf (all genders)",
        "location": "30855 Langenhagen, Han, Niedersachsen, Deutschland",
        "country": "de",
        "employment_type": "FULL_TIME",
        "posted_at": "2026-06-11T00:00:00",
        "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/12951-4da97482-4abd-40db--S",
    },
]


def _job(**overrides) -> dict:
    """Titulo/empresa/local do par Bayer (para provas sinteticas de guardrail)."""
    job = dict(BAYER_13_BA)
    job.update(overrides)
    return job


# ---------------------------------------------------------------------------
# A. Normalizacoes
# ---------------------------------------------------------------------------


def test_normalizacoes() -> None:
    section("F48.A normalizacao: cidade (CEP/alias), empresa (identidade), salario")
    check("CEP inicial fora: '51373 Leverkusen, ...' -> leverkusen",
          city_key("51373 Leverkusen, Nordrhein Westfalen, Deutschland") == "leverkusen")
    check("local EN do espelho -> mesma cidade",
          city_key("Leverkusen, North Rhine Westfalia, DE") == "leverkusen")
    check("alias CITY_ALIASES EN->DE (Munich/München)",
          city_key("Munich, Bayern, Germany") == city_key("80809 München, Bayern, Deutschland") == "munchen")
    check("alias Cologne -> koln",
          city_key("Cologne, Germany") == city_key("50674 Köln") == "koln")
    check("local vazio -> chave vazia", city_key(None) == "" and city_key("") == "")

    check("forma legal fora: 'Bayer AG Pharmaceuticals' -> {bayer}",
          company_identity("Bayer AG Pharmaceuticals") == frozenset({"bayer"}))
    check("mesma identidade de 'Bayer'",
          company_identity("Bayer") == company_identity("Bayer AG Pharmaceuticals"))
    check("hostname artefato (phenom) -> identidade do nome",
          company_identity("www.careers.philips.com") == frozenset({"philips"}))
    check("qualificador de razao social observado (procurement) fora",
          company_identity("Vodafone Procurement Company S.a.r.l.") == frozenset({"vodafone"}))
    check("empresas DIFERENTES do grupo NAO convergem (MTU)",
          company_identity("MTU Aero Engines AG") != company_identity("MTU Maintenance Hannover GmbH"))
    check("empresas DIFERENTES NAO convergem (Healthineers)",
          company_identity("Siemens AG") != company_identity("Siemens Healthineers AG"))
    check("empresa vazia -> identidade vazia (nunca casa)",
          company_identity("") == frozenset() and company_identity(None) == frozenset())

    check("salario '2.280 €' -> (2280.0, eur)", salary_value({"salary": "2.280 €"}) == (2280.0, "eur"))
    check("salario '€ 2,280.00' -> MESMO valor (convencao US)",
          salary_value({"salary": "€ 2,280.00"}) == (2280.0, "eur"))
    check("salario '2.280 EUR brutto' -> mesmo valor",
          salary_value({"salary": "2.280 EUR brutto"}) == (2280.0, "eur"))
    check("salario '1.800 €' -> valor distinto",
          salary_value({"salary": "1.800 €"}) != salary_value({"salary": "2.280 €"}))
    check("salario ausente/nao parseavel -> None",
          salary_value({"salary": None}) is None and salary_value({"salary": ""}) is None
          and salary_value({"salary": "a combinar"}) is None)
    # a evidencia de salario identico do par Bayer vive na description
    check("salario identico do par Bayer (trecho verbatim DE)",
          "2.280" in SALARIO_DE and "2.280" in SALARIO_EN)


# ---------------------------------------------------------------------------
# B/C. Par Bayer verbatim (13/10 EN/DE e 14/10 DE/DE)
# ---------------------------------------------------------------------------


def test_bayer_verbatim() -> None:
    section("F48.B par Bayer VERBATIM 13/10 (EN/DE, empresa/local em formatos distintos)")
    before = copy.deepcopy([BAYER_13_BA, BAYER_13_SF])
    out, stats, removed = deduplicate_cross_source([BAYER_13_BA, BAYER_13_SF])
    check("funde o par (1 vaga sobrevive)", len(out) == 1 and len(removed) == 1,
          f"out={len(out)} removed={len(removed)}")
    check("estatistica registra a chave cross-fonte",
          stats == {KEY_CROSS_SOURCE: 1}, str(stats))
    check("canonical = registro do DATASET (fonte primaria F3)",
          out[0]["id"] == BAYER_13_BA["id"], out[0]["id"])
    duplicate = removed[0][1]
    check("nao-canonico e o espelho EN (successfactors)",
          duplicate["id"] == BAYER_13_SF["id"], duplicate["id"])
    check("nao-canonico recebe duplicate_of = id do canonico",
          duplicate.get("duplicate_of") == BAYER_13_BA["id"])
    check("canonical NAO foi alterado (sem merge de campos)",
          out[0] == before[0])
    check("rotulo do registro removido == chave cross-fonte",
          removed[0][2] == KEY_CROSS_SOURCE)
    # o estagio sozinho NAO ve o par: os tiers classicos tambem nao (o buraco)
    out_cls, stats_cls, _ = deduplicate(copy.deepcopy([BAYER_13_BA, BAYER_13_SF]))
    check("tiers classicos (1-5) NAO fundem o par (o buraco medido)",
          len(out_cls) == 2 and not stats_cls, str(stats_cls))

    section("F48.C par Bayer VERBATIM 14/10 (DE/DE, 'Nordrhein-Westfalen' x 'Nordrhein Westfalen')")
    out14, stats14, removed14 = deduplicate_cross_source(
        [dict(BAYER_14_SF), dict(BAYER_13_BA)]
    )
    check("funde o par do print 14/10", len(out14) == 1 and stats14 == {KEY_CROSS_SOURCE: 1},
          f"out={len(out14)} stats={stats14}")
    check("canonical segue o dataset; duplicata = SF DE",
          out14[0]["id"] == BAYER_13_BA["id"]
          and removed14[0][1]["id"] == BAYER_14_SF["id"])
    check("provenance do par 14/10 aponta o canonico",
          removed14[0][1].get("duplicate_of") == BAYER_13_BA["id"])


# ---------------------------------------------------------------------------
# D. Contra-casos legitimos (DEVEM sobreviver)
# ---------------------------------------------------------------------------


def test_contra_casos() -> None:
    section("F48.D contra-casos legitimos: cidade/pais diferente = vaga diferente")
    out, stats, _ = deduplicate_cross_source(copy.deepcopy(GOOGLE_X3))
    check("Google x3 (3 cidades/paises, mesmo titulo) -> 3 sobrevivem",
          len(out) == 3 and not stats, f"out={len(out)} stats={stats}")
    check("Google: nenhuma fusao por pais diferente",
          len({j["id"] for j in out}) == 3)

    out_i, stats_i, _ = deduplicate_cross_source(copy.deepcopy(INDIECAMPERS_X4))
    check("indiecampers x4 (4 cidades, mesmo titulo) -> 4 sobrevivem",
          len(out_i) == 4 and not stats_i, f"out={len(out_i)} stats={stats_i}")

    out_m, stats_m, _ = deduplicate_cross_source(copy.deepcopy(MTU_X2))
    check("MTU x2 (razoes sociais distintas + cidades distintas) -> 2 sobrevivem",
          len(out_m) == 2 and not stats_m, f"out={len(out_m)} stats={stats_m}")

    # Juntos no MESMO universo: nada legitimo e tocado pelo estagio
    universo = copy.deepcopy(GOOGLE_X3 + INDIECAMPERS_X4 + MTU_X2
                             + [BAYER_13_BA, BAYER_13_SF])
    out_u, stats_u, _ = deduplicate_cross_source(universo)
    check("universo misto: so o par Bayer sai (11 -> 10)",
          len(out_u) == 10 and stats_u == {KEY_CROSS_SOURCE: 1}, f"out={len(out_u)}")


# ---------------------------------------------------------------------------
# E/F. Empresas distintas e guardrails
# ---------------------------------------------------------------------------


def test_empresa_distinta_e_guardrails() -> None:
    section("F48.E empresas distintas com titulo identico na MESMA cidade")
    a = _job(id="Siemens AG|sf_dataset:bundesagentur:1", company="Siemens AG",
             location="51373 Leverkusen, Nordrhein Westfalen, Deutschland")
    b = _job(id="Siemens Healthineers AG|successfactors:jobs:2",
             company="Siemens Healthineers AG",
             location="Leverkusen, North Rhine Westfalia, DE",
             source="successfactors:jobs")
    out, stats, _ = deduplicate_cross_source([a, b])
    check("Healthineers != Siemens -> NAO funde (2 sobrevivem)",
          len(out) == 2 and not stats, str(stats))

    section("F48.F guardrails (fixtures sinteticas rotuladas; par Bayer como base)")
    # country divergente
    c = _job(id="X|sf_dataset:bundesagentur:3", country="de")
    d = _job(id="Y|successfactors:jobs:4", source="successfactors:jobs", country="nl")
    out_cd, stats_cd, _ = deduplicate_cross_source([c, d])
    check("country divergente -> par rejeitado", len(out_cd) == 2 and not stats_cd)
    # salary divergente (ambos presentes)
    e = _job(id="X|sf_dataset:bundesagentur:5", salary="2.280 €")
    f = _job(id="Y|successfactors:jobs:6", source="successfactors:jobs", salary="1.800 €")
    out_sal, stats_sal, _ = deduplicate_cross_source([e, f])
    check("salary divergente (ambos presentes) -> par rejeitado",
          len(out_sal) == 2 and not stats_sal)
    # salary igual em formatos diferentes -> funde; salary ausente -> nao reprova
    g = _job(id="X|sf_dataset:bundesagentur:7", salary="2.280 €")
    h = _job(id="Y|successfactors:jobs:8", source="successfactors:jobs", salary="€ 2,280.00")
    out_sal2, stats_sal2, _ = deduplicate_cross_source([g, h])
    check("salary igual em convencoes diferentes -> FUNDE",
          len(out_sal2) == 1 and stats_sal2 == {KEY_CROSS_SOURCE: 1})
    i_ = _job(id="X|sf_dataset:bundesagentur:9", salary="2.280 €")
    j_ = _job(id="Y|successfactors:jobs:10", source="successfactors:jobs", salary=None)
    out_sal3, stats_sal3, _ = deduplicate_cross_source([i_, j_])
    check("salary ausente de um lado NAO reprova (ausencia != dado falso)",
          len(out_sal3) == 1 and stats_sal3 == {KEY_CROSS_SOURCE: 1})
    # employment_type divergente NAO reprova (decisao documentada da fase)
    k = _job(id="X|sf_dataset:bundesagentur:11", employment_type="FULL_TIME")
    m = _job(id="Y|successfactors:jobs:12", source="successfactors:jobs",
             employment_type="INTERNSHIP")
    out_et, stats_et, _ = deduplicate_cross_source([k, m])
    check("employment_type divergente NAO reprova (vocabulario entre fontes)",
          len(out_et) == 1 and stats_et == {KEY_CROSS_SOURCE: 1})


# ---------------------------------------------------------------------------
# G. Mesma fonte x regressao do tier DE/EN (F5)
# ---------------------------------------------------------------------------


def test_mesma_fonte_e_regressao_f5() -> None:
    section("F48.G mesma fonte nao e alvo; par DE/EN do tier 4 (F5) segue fundido")
    a = _job(id="Bayer|sf_dataset:bundesagentur:1")
    b = _job(id="Bayer|sf_dataset:bundesagentur:2")  # MESMO source
    out, stats, _ = deduplicate_cross_source([a, b])
    check("par da MESMA fonte passa reto (2 sobrevivem)",
          len(out) == 2 and not stats, str(stats))

    # regressao F5: mesmo titulo DE/EN + mesma cidade -> tier 4 funde (mecanismo
    # ANTIGO, intacto); o novo estagio nao interfere.
    de = _job(id="a|sf:1", source="s1", title="Praktikum Logistik (m/w/d)",
              location="München, BY, de", external_id="", url="https://example.org/de")
    en = _job(id="b|sf:2", source="s2", title="Logistics Internship",
              location="Munich, Bavaria, DE", external_id="", url="https://example.org/en")
    out_f5, stats_f5, _ = deduplicate([de, en])
    check("tier 4 (F5) continua fundindo DE/EN cross-fonte (1 sobrevive)",
          len(out_f5) == 1 and stats_f5.get(KEY_COMPANY_TITLE_LOCATION_DE_EN) == 1,
          str(stats_f5))
    out_noop, stats_noop, _ = deduplicate_cross_source(out_f5)
    check("novo estagio e no-op sobre o que o tier 4 ja fundiu",
          len(out_noop) == 1 and not stats_noop)


# ---------------------------------------------------------------------------
# H. Determinismo, idempotencia e provenance
# ---------------------------------------------------------------------------


def test_determinismo_e_provenance() -> None:
    section("F48.H determinismo, idempotencia e registro de provenance")
    jobs = copy.deepcopy([BAYER_13_BA, BAYER_13_SF, *GOOGLE_X3])
    out1, stats1, rem1 = deduplicate_cross_source(jobs)
    out2, stats2, rem2 = deduplicate_cross_source(copy.deepcopy(jobs))
    check("deterministico: 2 execucoes -> mesma saida",
          [j["id"] for j in out1] == [j["id"] for j in out2] and stats1 == stats2)
    out3, stats3, _ = deduplicate_cross_source(out1)
    check("idempotente: re-rodar na saida -> no-op",
          [j["id"] for j in out3] == [j["id"] for j in out1] and not stats3)

    rows = cross_source_provenance(rem1)
    check("provenance: 1 registro por fusao", len(rows) == 1)
    row = rows[0]
    check("provenance com id + duplicate_of + fontes dos dois lados",
          row["id"] == BAYER_13_SF["id"]
          and row["duplicate_of"] == BAYER_13_BA["id"]
          and row["source_duplicate"] == "successfactors:jobs"
          and row["source_canonical"] == "sf_dataset:bundesagentur")
    check("provenance e JSON-serializavel",
          isinstance(json.dumps(rows, ensure_ascii=False), str))
    check("a duplicata nao esta na saida",
          BAYER_13_SF["id"] not in {j["id"] for j in out1})

    section("F48.H linha do relatorio de dedup (aditiva)")
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_dedup_report({KEY_CROSS_SOURCE: 2})
    line = buf.getvalue().strip()
    check("linha do report cita 'espelho cross-fonte'", "espelho cross-fonte" in line, line)
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        print_dedup_report({"url": 1})
    check("linha sem cross-fonte fica identica a de antes da F48",
          "cross-fonte" not in buf2.getvalue())


# ---------------------------------------------------------------------------
# I. Integracao com o pipeline (metrica diaria + saida)
# ---------------------------------------------------------------------------


def test_pipeline_integracao() -> None:
    section("F48.I pipeline: duplicata sai da saida + metrica dedup_cross_source")
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "eligible_jobs.json"
        metrics_path = Path(td) / "metrics.jsonl"
        rc = run_filter_pipeline(
            copy.deepcopy([BAYER_13_BA, BAYER_13_SF, *GOOGLE_X3]),
            student=False,
            area=False,
            country="all",
            output=out_path,
            dedup=True,
            rank=True,
            hydrate=False,
            mirror_dedup=True,
            applicability=False,
            metrics=metrics_path,
            run_id="f48-test",
        )
        check("pipeline rc=0", rc == 0, f"rc={rc}")
        rows = json.loads(out_path.read_text(encoding="utf-8"))
        ids = {r["id"] for r in rows}
        check("saida do pipeline sem a duplicata",
              BAYER_13_SF["id"] not in ids and BAYER_13_BA["id"] in ids,
              f"n={len(ids)}")
        check("Google x3 preservado na saida",
              sum(1 for i in ids if i.startswith("Google|")) == 3)
        records = [json.loads(l) for l in metrics_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        run_rec = next(r for r in records if r["type"] == "run")
        cross_rec = [r for r in records if r["type"] == "dedup_cross_source"]
        check("registro type=dedup_cross_source na metrica", len(cross_rec) == 1)
        if cross_rec:
            pairs = cross_rec[0]["pairs"]
            check("metrica com removed=1 e a duplicata + duplicate_of",
                  cross_rec[0]["removed"] == 1 and len(pairs) == 1
                  and pairs[0]["id"] == BAYER_13_SF["id"]
                  and pairs[0]["duplicate_of"] == BAYER_13_BA["id"])
        check("dedup_removed do run conta a fusao cross-fonte",
              run_rec.get("dedup_removed", 0) >= 1, str(run_rec.get("dedup_removed")))
        # --no-dedup (dedup=False) desliga o estagio inteiro (reversibilidade)
        out_path2 = Path(td) / "eligible_nodedup.json"
        run_filter_pipeline(
            copy.deepcopy([BAYER_13_BA, BAYER_13_SF]),
            student=False, area=False, country="all", output=out_path2,
            dedup=False, rank=False, hydrate=False, mirror_dedup=True,
            applicability=False, run_id="f48-test-nodedup",
        )
        rows2 = json.loads(out_path2.read_text(encoding="utf-8"))
        check("dedup=False desliga o estagio (par intacto: 2 vagas)",
              len(rows2) == 2, f"n={len(rows2)}")


# ---------------------------------------------------------------------------
# J. ci.yml
# ---------------------------------------------------------------------------


def test_ci_membership() -> None:
    section("F48.J ci.yml: test_f48 no array tests=")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    import re
    match = re.search(r"tests=\((.*?)\)", ci, re.S)
    specs = [t for t in match.group(1).split() if t] if match else []
    check("test_f48 no array tests= do ci.yml", "test_f48" in specs, str(len(specs)))
    check("array tests= sem duplicatas", len(specs) == len(set(specs)))


def main() -> int:
    test_normalizacoes()
    test_bayer_verbatim()
    test_contra_casos()
    test_empresa_distinta_e_guardrails()
    test_mesma_fonte_e_regressao_f5()
    test_determinismo_e_provenance()
    test_pipeline_integracao()
    test_ci_membership()
    print()
    if _FAILS:
        print(f"FALHAS: {_FAILS}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
