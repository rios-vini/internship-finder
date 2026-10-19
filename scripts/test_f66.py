#!/usr/bin/env python3
"""test_f66 — Dedup: alias tenant-label -> empresa real (lidlstiftup2 -> Lidl).

F66 (19/10, spec da card): fontes de dataset carregam o ``company`` como o
LABEL DO TENANT do ATS (o feed SuccessFactors da Lidl Stiftung vem com
``company="lidlstiftup2"`` — 90 vagas no eligible 19/10; SmartRecruiters da
Robert Bosch GmbH com ``"BoschGroup"``; cornerstone com o hostname
``"ebmpapst"``). Quando a MESMA vaga aparece em outra fonte pelo nome real
("Lidl Stiftung & Co. KG"), ``company_identity`` compara ``{lidlstiftup2}``
x ``{lidl, stiftung}`` e o par nao funde — twins no funil (o registro de
desfechos do dono pegou 3 manualmente: Wuerth SF x absolventa, Bosch
Strategic SR x arbeitsagentur, Lidl SAP BI re-post; a varredura F66 achou
25 pares suspeitos no eligible ATUAL, 20 colapsaveis pos-alias).

DECISAO DE DESIGN (medida, nao digitada): o alias de DISPLAY da F54
(config/display_aliases.json) NAO cobre o dedup — ele mapeia para nomes de
MARCA curtos ("lidlstiftup2" -> "Lidl" -> identidade {lidl}) que NUNCA
igualam a identidade token do nome real {lidl, stiftung}; consumi-lo
quebraria o contrato display-only da F54 ("o alias nao pode contaminar o
pipeline"). Logo: mapa PROPRIO no dominio do dedup
(config/dedup_company_aliases.json), aplicado SO na chave de identidade
do estagio cross_source (F48) via canonical_company antes da tokenizacao
(match EXATO casefold, nunca substring; passo unico).

CURADORIA (regra Levio/TYTAN, licao F9/F10): so alias o label com UM
UNICO empregador real por tras — auditado pelos hosts/slugs das URLs da
varredura (lidlstiftup2 = 100% jobs.lidl; BoschGroup = 100% tenant
SmartRecruiters; ebmpapst = csod; HORSCH Leeb AS = abreviacao da BA).
String multi-empregador ("Levio" = tenant Bertelsmann com RTL/Arvato/BFS
nas URLs) e nome juridico real de holding ("Wuerth Group") NUNCA ganham
alias — zero falsos merges > completude.

Fixtures VERBATIM: os 3 pares do registro de desfechos (archive 18/10,
mesmos do canario test_f64 G4) + os pares novos da varredura do eligible
19/10 (Lidl x absolventa, Bosch Lagerwirtschaft, HORSCH, ebm-papst) + os
contra-casos (Workwize x godutch, Amazon Erfurt x Amazon E2 Transport,
Siemens homonimos, Levio x Bertelsmann).

100% OFFLINE (nenhum socket; data/ intocavel; snapshot so le). Exit 0/1
(padrao da casa: rc + zero '[FAIL]').
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
for _p in (str(SCRIPTS), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from internship_finder.cross_source_dedup import (  # noqa: E402
    DEFAULT_DEDUP_COMPANY_ALIASES_PATH,
    KEY_CROSS_SOURCE,
    _de_en_title_key,
    canonical_company,
    city_key,
    company_identity,
    deduplicate_cross_source,
    load_company_aliases,
)
from internship_finder.dedup import deduplicate  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(cond), detail))
    print(f"{'[OK] ' if cond else '[FAIL]'} {name}" + (f" — {detail}" if detail and not cond else ""))


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _fix(id_, company, title, location, source, country="de", **extra):
    job = {"id": id_, "company": company, "title": title, "location": location,
           "country": country, "source": source, "employment_type": None}
    job.update(extra)
    return job


ALIASES = load_company_aliases(ROOT / "config" / "dedup_company_aliases.json")

# ---------------------------------------------------------------------------
# Fixtures VERBATIM — registro de desfechos do dono (archive 18/10; canario
# test_f64 G4) — pares rotulados manualmente como a MESMA vaga.
# ---------------------------------------------------------------------------
WUERTH_SF = _fix("Würth Group|sf_dataset:successfactors:1439347933", "Würth Group",
                 "Praktikant (m/w/d) im Bereich Logistik - Import Beschaffung",
                 "Bad Mergentheim, BW, DE, 97980", "sf_dataset:successfactors")
WUERTH_TWIN = _fix("Würth Industrie Service GmbH & Co. KG|absolventa:13251590",
                   "Würth Industrie Service GmbH & Co. KG",
                   "Praktikant (m/w/d) im Bereich Logistik - Import Beschaffung",
                   None, "absolventa")
BOSCH_SR = _fix("BoschGroup|sf_dataset:smartrecruiters:744000155984519", "BoschGroup",
                "Mandatory Internship in Strategic Purchasing of Logistic Transport Services",
                "Stuttgart, BW, de", "sf_dataset:smartrecruiters")
BOSCH_TWIN = _fix("Robert Bosch GmbH|direct:bundesagentur:15986-REF298797V-5acbda5-S",
                  "Robert Bosch GmbH",
                  "Pflichtpraktikum im strategischen Einkauf von logistischen Transportdienstleistungen (w/m/div.)",
                  "70469 Stuttgart, Baden_Wuerttemberg, Deutschland", "direct:bundesagentur")
LIDL_SF = _fix("lidlstiftup2|sf_dataset:successfactors:1436050633", "lidlstiftup2",
               "Praktikum Controlling International - SAP BI Reporting",
               "Neckarsulm, DE", "sf_dataset:successfactors", description="SAP BI")
LIDL_REPOST = _fix("Lidl Stiftung & Co. KG|praktikum_info:13231277", "Lidl Stiftung & Co. KG",
                   "Praktikum Controlling International - SAP BI Reporting",
                   "74167 Neckarsulm", "praktikum_info")

# ---------------------------------------------------------------------------
# Fixtures VERBATIM — varredura F66 do eligible ATUAL (19/10, 725 vagas).
# ---------------------------------------------------------------------------
LIDL_EXPORT_SF = _fix("lidlstiftup2|sf_dataset:successfactors:1441846233", "lidlstiftup2",
                      "Praktikum Einkauf - Export International", "Neckarsulm, DE",
                      "sf_dataset:successfactors", description="x")
LIDL_EXPORT_ABS = _fix("Lidl Stiftung & Co. KG|absolventa:13308137", "Lidl Stiftung & Co. KG",
                       "Praktikum Einkauf - Export International", "74167 Neckarsulm", "absolventa")
BOSCH_LAGER_SR = _fix("BoschGroup|sf_dataset:smartrecruiters:744000153160319", "BoschGroup",
                      "Pflichtpraktikum im Einkauf mit Schwerpunkt Lagerwirtschaft",
                      "Stuttgart, BW, de", "sf_dataset:smartrecruiters", description="x")
BOSCH_LAGER_BA = _fix("Robert Bosch GmbH|sf_dataset:bundesagentur:15986-REF294291P-b976730-S",
                      "Robert Bosch GmbH",
                      "Pflichtpraktikum im Einkauf mit Schwerpunkt Lagerwirtschaft",
                      "70469 Stuttgart, Baden Wuerttemberg, Deutschland", "sf_dataset:bundesagentur")
HORSCH_ABS = _fix("HORSCH LEEB Application Systems SE & Co. KG|absolventa:12937826",
                  "HORSCH LEEB Application Systems SE & Co. KG",
                  "Praktikum (m/w/d) in der Unit Purchasing", "94405 Landau an der Isar",
                  "absolventa", description="x")
HORSCH_BA = _fix("HORSCH Leeb AS SE & Co. KG|sf_dataset:bundesagentur:10001-1003285907-S",
                 "HORSCH Leeb AS SE & Co. KG", "Praktikum (m/w/d) in der Unit Purchasing",
                 "94405 Landau an der Isar, Bayern, Deutschland", "sf_dataset:bundesagentur")
EBM_DATASET = _fix("ebm-papst|sf_dataset:cornerstone:3529", "ebm-papst",
                   "Pflichtpraktikum im Bereich Controlling (m/w/d)", "Mulfingen, DE",
                   "sf_dataset:cornerstone", description="x")
EBM_REGISTRY = _fix("ebmpapst|cornerstone:https://ebmpapst.csod.com/ux/ats/careersite/4/home?c=ebmpapst:3529",
                    "ebmpapst", "Pflichtpraktikum im Bereich Controlling (m/w/d)", "Mulfingen, DE",
                    "cornerstone:https://ebmpapst.csod.com/ux/ats/careersite/4/home?c=ebmpapst")

# Contra-casos VERBATIM da varredura (mesma cidade+titulo, empresas distintas).
WORKWIZE = _fix("Workwize|sf_dataset:welcometothejungle:d5b5ad0b-2a8e-4ad8-9fe2-d23e323d2687",
                "Workwize", "Operations intern", "Amsterdam, Netherlands",
                "sf_dataset:welcometothejungle", country="nl")
GODUTCH = _fix("godutch|sf_dataset:teamtailor:7015387", "godutch", "Operations Intern",
               "Amsterdam, Netherlands", "sf_dataset:teamtailor", country="nl")
AMAZON_ERFURT = _fix("Amazon Erfurt GmbH - O80|absolventa:13235973", "Amazon Erfurt GmbH - O80",
                     "Praktikum im Bereich Logistik - Erfurt - Start 2027", None, "absolventa")
AMAZON_E2 = _fix("Amazon Deutschland E2 Transport GmbH - I70|amazon_jobs:10541774",
                 "Amazon Deutschland E2 Transport GmbH - I70",
                 "Praktikum im Bereich Logistik - Erfurt - Start 2027",
                 "Erfurt, Thuringia, DEU", "amazon_jobs")


# ===========================================================================
# A. Config do mapa — curadoria (regras, nao contagens)
# ===========================================================================

def test_config() -> None:
    section("F66.A mapa de aliases: arquivo, curadoria e regras")
    path = ROOT / "config" / "dedup_company_aliases.json"
    check("A1 arquivo versionado existe (config/dedup_company_aliases.json)",
          path.exists(), str(path))
    check("A2 caminho PADRAO do modulo aponta para o arquivo versionado",
          str(DEFAULT_DEDUP_COMPANY_ALIASES_PATH) == "config/dedup_company_aliases.json",
          str(DEFAULT_DEDUP_COMPANY_ALIASES_PATH))
    check("A3 mapa carrega (dict nao-vazio)", bool(ALIASES), str(ALIASES))
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("aliases", {})
    check("A4 chave casefold: 'lidlstiftup2' -> 'Lidl Stiftung & Co. KG' (spec da card)",
          ALIASES.get("lidlstiftup2") == "Lidl Stiftung & Co. KG",
          str(ALIASES.get("lidlstiftup2")))
    check("A5 'boschgroup' -> 'Robert Bosch GmbH' (varredura 19/10)",
          ALIASES.get("boschgroup") == "Robert Bosch GmbH")
    check("A6 'ebmpapst' -> 'ebm-papst' (artefato de hostname)",
          ALIASES.get("ebmpapst") == "ebm-papst")
    check("A7 'horsch leeb as se & co. kg' -> nome completo (abreviacao da BA)",
          "HORSCH LEEB Application Systems SE & Co. KG" in ALIASES.values())
    # Regra Levio/TYTAN: string multi-empregador NUNCA no mapa (lesson F9/F10)
    forbidden = [k for k in ALIASES if any(
        t in k for t in ("levio", "tytan", "createyourown", "würth", "wurth"))]
    check("A8 regra Levio/TYTAN: nenhum label ambiguo/holding no mapa "
          "(levio/tytan/createyourown/wuerth ausentes)", forbidden == [], str(forbidden))
    # Mapa PLANO: valor nunca e chave de outro (sem cadeia), sem auto-alias
    keys_cf = set(ALIASES)
    vals_cf = {v.strip().casefold() for v in ALIASES.values()}
    check("A9 mapa plano: nenhum valor e chave de outra entry (passo unico por contrato)",
          not (keys_cf & vals_cf), str(keys_cf & vals_cf))
    # Identidades: todo valor tem identidade nao-vazia (alias nunca cega o par)
    bad_vals = [v for v in ALIASES.values() if not company_identity(v)]
    check("A10 todo valor tem identidade token nao-vazia", bad_vals == [], str(bad_vals))
    # Honestidade: o valor iguala a identidade do NOME REAL usado pelas outras fontes
    check("A11 identidade do valor 'Lidl Stiftung & Co. KG' == identidade do twin real",
          company_identity(ALIASES.get("lidlstiftup2", ""))
          == company_identity(LIDL_REPOST["company"]),
          f"{sorted(company_identity(ALIASES.get('lidlstiftup2', '')))} x "
          f"{sorted(company_identity(LIDL_REPOST['company']))}")
    # Chaves do mapa nao colidem no casefold (loader fail-closed ja garante;
    # aqui valida o ARQUIVO versionado em si)
    raw_keys = [k.strip().casefold() for k in entries]
    check("A12 arquivo: chaves unicas apos casefold", len(raw_keys) == len(set(raw_keys)))


# ===========================================================================
# B. Loader — degradacao graciosa (nunca crasha o estagio)
# ===========================================================================

def test_loader() -> None:
    section("F66.B loader: ausente/corrompido/invalido -> {} (fail-closed)")
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        check("B1 arquivo inexistente -> {}",
              load_company_aliases(td_path / "nope.json") == {})
        corrupt = td_path / "corrupt.json"
        corrupt.write_text("{ not json !!!", encoding="utf-8")
        check("B2 JSON corrompido -> {}", load_company_aliases(corrupt) == {})
        wrong = td_path / "wrong.json"
        wrong.write_text('["list", "nao", "dict"]', encoding="utf-8")
        check("B3 raiz nao-dict -> {}", load_company_aliases(wrong) == {})
        no_aliases = td_path / "no_aliases.json"
        no_aliases.write_text('{"_comment": "x"}', encoding="utf-8")
        check("B4 sem chave 'aliases' -> {}", load_company_aliases(no_aliases) == {})
        empty = td_path / "empty.json"
        empty.write_text('{"aliases": {}}', encoding="utf-8")
        check("B5 aliases vazio -> {}", load_company_aliases(empty) == {})
        badtype = td_path / "badtype.json"
        badtype.write_text('{"aliases": {"a": 123}}', encoding="utf-8")
        check("B6 valor nao-string -> {} (curadoria rejeitada inteira)",
              load_company_aliases(badtype) == {})
        collision = td_path / "collision.json"
        collision.write_text('{"aliases": {"Lidl": "A", "LIDL": "B"}}', encoding="utf-8")
        check("B7 colisao casefold com valores distintos -> {} (ambiguidade e rejeitada)",
              load_company_aliases(collision) == {})
        selfalias = td_path / "selfalias.json"
        selfalias.write_text('{"aliases": {"Gsk": "GSK", "x": "X Corp"}}',
                             encoding="utf-8")
        got = load_company_aliases(selfalias)
        check("B8 auto-alias e descartado (no-op), entry valida sobrevive",
              got == {"x": "X Corp"}, str(got))
        blank = td_path / "blank.json"
        blank.write_text('{"aliases": {"  ": "X"}}', encoding="utf-8")
        check("B9 chave vazia/so-espacos -> {}", load_company_aliases(blank) == {})
        good = td_path / "good.json"
        good.write_text('{"aliases": {"somelabel": "Real Co GmbH"}}', encoding="utf-8")
        got2 = load_company_aliases(good)
        check("B10 arquivo valido carrega com chave casefold",
              got2 == {"somelabel": "Real Co GmbH"}, str(got2))


# ===========================================================================
# C. canonical_company — match exato, passo unico, sem substring
# ===========================================================================

def test_canonical() -> None:
    section("F66.C canonical_company: resolucao exata e conservadora")
    check("C1 label exato resolve ('lidlstiftup2' -> nome real)",
          canonical_company("lidlstiftup2", ALIASES) == "Lidl Stiftung & Co. KG")
    check("C2 casefold: 'LIDLSTIFTUP2' (maiusculo) tambem resolve",
          canonical_company("LIDLSTIFTUP2", ALIASES) == "Lidl Stiftung & Co. KG")
    check("C3 SEM substring: 'lidlstiftup2 GmbH' fica intacta",
          canonical_company("lidlstiftup2 GmbH", ALIASES) == "lidlstiftup2 GmbH")
    check("C4 SEM substring: 'BoschGroup Career' fica intacta",
          canonical_company("BoschGroup Career", ALIASES) == "BoschGroup Career")
    check("C5 string fora do mapa volta intacta ('Robert Bosch GmbH')",
          canonical_company("Robert Bosch GmbH", ALIASES) == "Robert Bosch GmbH")
    check("C6 aliases=None -> passthrough puro", canonical_company("lidlstiftup2", None) == "lidlstiftup2")
    check("C7 aliases={} -> passthrough (escape do A/B)", canonical_company("lidlstiftup2", {}) == "lidlstiftup2")
    check("C8 company None -> None", canonical_company(None, ALIASES) is None)
    check("C9 company vazia -> vazia", canonical_company("", ALIASES) == "")
    # passo unico: valor que e chave de outro NAO re-resolve (mapa plano)
    chained = {"a": "b-label", "b-label": "C Corp"}
    check("C10 passo unico: valor nunca e re-resolvido (anti-cadeia)",
          canonical_company("a", chained) == "b-label")
    # identidade pos-canonical converge so quando a string E o label exato
    ident_lidl = company_identity(canonical_company("lidlstiftup2", ALIASES))
    check("C11 identidade pos-canonical == identidade do nome real do twin",
          ident_lidl == company_identity("Lidl Stiftung & Co. KG"),
          f"{sorted(ident_lidl)}")


# ===========================================================================
# D. company_identity pura — regressao: semantica pre-F66 intacta
# ===========================================================================

def test_identity_pura() -> None:
    section("F66.D company_identity PURA (sem alias): contrato pre-F66 intacto")
    check("D1 'lidlstiftup2' -> {lidlstiftup2} (token unico, nao splitado)",
          company_identity("lidlstiftup2") == frozenset({"lidlstiftup2"}))
    check("D2 'Lidl Stiftung & Co. KG' -> {lidl, stiftung}",
          company_identity("Lidl Stiftung & Co. KG") == frozenset({"lidl", "stiftung"}))
    check("D3 'BoschGroup' -> {boschgroup} (nao vira {bosch, group})",
          company_identity("BoschGroup") == frozenset({"boschgroup"}))
    check("D4 'Robert Bosch GmbH' -> {robert, bosch}",
          company_identity("Robert Bosch GmbH") == frozenset({"robert", "bosch"}))
    check("D5 identidades raw divergem SEM alias (o buraco medido)",
          company_identity("lidlstiftup2") != company_identity("Lidl Stiftung & Co. KG"))
    check("D6 Siemens homonimos continuam distintos (contra-caso pre-existente)",
          company_identity("Siemens AG") != company_identity("Siemens Healthineers AG"))
    check("D7 empresa vazia -> identidade vazia (nunca casa)",
          company_identity("") == frozenset() and company_identity(None) == frozenset())


# ===========================================================================
# E. Display alias F54 NAO cobre o dedup (a checagem 'PARE' da card)
# ===========================================================================

def test_display_alias_nao_cobre() -> None:
    section("F66.E display alias F54 nao cobre o dedup — mapa proprio justificado")
    disp = json.loads((ROOT / "config" / "display_aliases.json").read_text(encoding="utf-8"))
    d = disp.get("aliases", {})
    check("E1 display tem o label 'lidlstiftup2' (branding da pagina)",
          "lidlstiftup2" in d, str(sorted(d)[:3]))
    # O alvo do display e nome de MARCA curto cuja identidade NAO iguala a do
    # nome real — consumir o display NAO fecharia o par (medicao da card).
    brand = d.get("lidlstiftup2", "")
    check("E2 identidade do alvo de display ('Lidl') != identidade do nome real",
          company_identity(brand) == frozenset({"lidl"})
          and company_identity(brand) != company_identity("Lidl Stiftung & Co. KG"),
          f"brand={brand!r} -> {sorted(company_identity(brand))}")
    # Simulacao honesta: dedup consumindo o MAPA DE DISPLAY nao funde o par
    display_as_dedup = {k.casefold(): v for k, v in d.items()}
    out, stats, removed = deduplicate_cross_source(
        [dict(LIDL_SF), dict(LIDL_REPOST)], aliases=display_as_dedup)
    check("E3 dedup consumindo SO o mapa de display NAO funde o par Lidl "
          "(alvos de marca curta nao igualam a identidade real)",
          removed == [], f"removed={len(removed)}")


# ===========================================================================
# F. Os 3 pares REAIS do registro de desfechos (canario test_f64 G4, verbatim)
# ===========================================================================

def test_pares_registro() -> None:
    section("F66.F registro de desfechos do dono: 3 pares verbatim (archive 18/10)")
    # 1. Lidl SAP BI re-post — o caso que o dono apontou ("badge NOVA re-exibiu
    #    dup"): FUNDE via alias; o nao-canonico sai com duplicate_of.
    out, stats, removed = deduplicate_cross_source(
        [dict(LIDL_SF), dict(LIDL_REPOST)], aliases=ALIASES)
    check("F1 Lidl SAP BI x re-post praktikum_info: FUNDE (alias fecha o par)",
          len(removed) == 1 and stats == {KEY_CROSS_SOURCE: 1},
          f"removed={len(removed)} stats={dict(stats)}")
    check("F2 canonico = registro do DATASET (fonte primaria F3)",
          removed and removed[0][0]["id"] == LIDL_SF["id"], str(removed and removed[0][0]["id"]))
    check("F3 nao-canonico recebe duplicate_of",
          removed and removed[0][1].get("duplicate_of") == LIDL_SF["id"])
    check("F4 campo company do canonico NUNCA mutado (display segue 'lidlstiftup2'; "
          "o alias de display F54 cuida da marca na pagina)",
          out and out[0].get("company") == "lidlstiftup2")
    # baseline: SEM alias o par NAO funde (braço A do A/B, gap pre-F66)
    _, _, removed0 = deduplicate_cross_source(
        [dict(LIDL_SF), dict(LIDL_REPOST)], aliases={})
    check("F5 baseline aliases={}: o MESMO par NAO funde (gap pre-F66 medido)",
          removed0 == [])
    # 2. Wuerth twin — NAO funde: localizacao VAZIA no twin absolventa
    #    (guardrail location-aware) + subsidiaria sem alias (regra Levio/TYTAN).
    _, _, rem_w = deduplicate_cross_source(
        [dict(WUERTH_SF), dict(WUERTH_TWIN)], aliases=ALIASES)
    check("F6 Wuerth twin: NAO funde (cidade vazia no absolventa + "
          "'Wuerth Group' e nome real de holding — fora da curadoria)",
          rem_w == [], f"removed={len(rem_w)}")
    check("F7 Wuerth: titulo casaria (bag DE/EN igual) — o trava e cidade+empresa",
          _de_en_title_key(WUERTH_SF["title"]) == _de_en_title_key(WUERTH_TWIN["title"])
          and city_key(WUERTH_TWIN["location"]) == "")
    # 3. Bosch Strategic — NAO funde: bag DE/EN do TITULO divergente
    #    (empresa RESOLVIDA pelo alias, titulo trava; dup perdido < fusao errada).
    _, _, rem_b = deduplicate_cross_source(
        [dict(BOSCH_SR), dict(BOSCH_TWIN)], aliases=ALIASES)
    check("F8 Bosch Strategic: NAO funde (bag DE/EN do titulo diverge — limite documentado)",
          rem_b == [], f"removed={len(rem_b)}")
    check("F9 Bosch: alias RESOLVE a empresa (pos-canonical identidades iguais); "
          "o titulo e o bloqueio restante",
          company_identity(canonical_company(BOSCH_SR["company"], ALIASES))
          == company_identity(canonical_company(BOSCH_TWIN["company"], ALIASES))
          and _de_en_title_key(BOSCH_SR["title"]) != _de_en_title_key(BOSCH_TWIN["title"]))


# ===========================================================================
# G. Pares NOVOS da varredura do eligible atual (19/10) — verbatim
# ===========================================================================

def test_pares_varredura() -> None:
    section("F66.G varredura 19/10: pares novos verbatim (17 Lidl + Bosch + HORSCH + ebm)")
    # Lidl x absolventa (o par 13308116 da F60 revisitado pelo outro lado)
    _, _, rem = deduplicate_cross_source(
        [dict(LIDL_EXPORT_SF), dict(LIDL_EXPORT_ABS)], aliases=ALIASES)
    check("G1 Lidl Einkauf Export SF x absolventa: FUNDE",
          len(rem) == 1 and rem[0][0]["id"] == LIDL_EXPORT_SF["id"], f"removed={len(rem)}")
    # Bosch Lagerwirtschaft: mesmo TITULO DE nas duas fontes — funde
    _, _, rem = deduplicate_cross_source(
        [dict(BOSCH_LAGER_SR), dict(BOSCH_LAGER_BA)], aliases=ALIASES)
    check("G2 Bosch Lagerwirtschaft SR x BA: FUNDE (titulo identico, empresa resolvida)",
          len(rem) == 1, f"removed={len(rem)}")
    # HORSCH: abreviacao da fonte BA -> nome completo
    _, _, rem = deduplicate_cross_source(
        [dict(HORSCH_ABS), dict(HORSCH_BA)], aliases=ALIASES)
    check("G3 HORSCH absolventa x BA (abreviacao 'AS'): FUNDE",
          len(rem) == 1, f"removed={len(rem)}")
    # ebm-papst: artefato de hostname — mesmissima URL pre-F66 nao colapsava
    # no tier URL (chave (company, url) escopada pela empresa divergente)
    _, _, rem = deduplicate_cross_source(
        [dict(EBM_DATASET), dict(EBM_REGISTRY)], aliases=ALIASES)
    check("G4 ebm-papst dataset x registry ('ebmpapst'): FUNDE",
          len(rem) == 1, f"removed={len(rem)}")
    # familia Lidl multi-fonte (2x SF, absolventa, praktikum_info; mesmo
    # titulo+cidade): os twins de fontes DISTINTAS colapsam no registro de
    # dataset; os 2 registros da MESMA fonte sobrevivem entre si (exclusao
    # mesma-fonte preservada — cada SF e uma vaga propria com id proprio)
    lidl_sf2 = dict(LIDL_EXPORT_SF, id="lidlstiftup2|sf_dataset:successfactors:999")
    out, stats, rem = deduplicate_cross_source(
        [dict(LIDL_EXPORT_SF), dict(LIDL_EXPORT_ABS),
         _fix("Lidl Stiftung & Co. KG|praktikum_info:999", "Lidl Stiftung & Co. KG",
              "Praktikum Einkauf - Export International", "74167 Neckarsulm",
              "praktikum_info"), lidl_sf2],
        aliases=ALIASES)
    check("G5 familia Lidl multi-fonte: 2 fusoes (cada twin no canonico de dataset), "
          "os 2 registros SF sobrevivem entre si (mesma-fonte nunca funde)",
          stats == {KEY_CROSS_SOURCE: 2} and len(out) == 2
          and {j["id"] for j in out} == {LIDL_EXPORT_SF["id"], "lidlstiftup2|sf_dataset:successfactors:999"}
          and all(d["id"].startswith("Lidl Stiftung") and d.get("duplicate_of") == LIDL_EXPORT_SF["id"]
                  for _, d, _ in rem),
          f"stats={dict(stats)} out={[j['id'] for j in out]}")


# ===========================================================================
# H. Contra-casos: ZERO falsos merges
# ===========================================================================

def test_contra_cases() -> None:
    section("F66.H contra-casos: nenhum job unico pode ser dedupado errado")
    # mesma cidade + mesmo titulo, empresas DISTINTAS, nenhum alias
    _, _, rem = deduplicate_cross_source(
        [dict(WORKWIZE), dict(GODUTCH)], aliases=ALIASES)
    check("H1 Workwize x godutch (Amsterdam, 'Operations intern'): NAO funde",
          rem == [], f"removed={len(rem)}")
    # entidades legais distintas (o caso 'dois Siemens diferentes')
    _, _, rem = deduplicate_cross_source(
        [dict(AMAZON_ERFURT), dict(AMAZON_E2)], aliases=ALIASES)
    check("H2 Amazon Erfurt O80 x Amazon E2 Transport I70 (entidades distintas): NAO funde",
          rem == [], f"removed={len(rem)}")
    siemens_a = _fix("Siemens AG|sf_dataset:successfactors:1", "Siemens AG",
                    "Praktikum Supply Chain", "München, DE", "sf_dataset:successfactors")
    siemens_b = _fix("Siemens Healthineers AG|absolventa:1", "Siemens Healthineers AG",
                     "Praktikum Supply Chain", "München, DE", "absolventa")
    _, _, rem = deduplicate_cross_source([siemens_a, siemens_b], aliases=ALIASES)
    check("H3 Siemens AG x Siemens Healthineers AG (homonimos): NAO funde",
          rem == [], f"removed={len(rem)}")
    # Levio: label multi-empregador (tenant Bertelsmann; RTL/Arvato/BFS reais)
    # — a regra da curadoria NUNCA o alias
    levio = _fix("Levio|sf_dataset:successfactors:77", "Levio",
                 "Working Student Data", "Gütersloh, DE", "sf_dataset:successfactors")
    bert = _fix("Bertelsmann SE & Co. KGaA|absolventa:77", "Bertelsmann SE & Co. KGaA",
                "Working Student Data", "Gütersloh, DE", "absolventa")
    _, _, rem = deduplicate_cross_source([levio, bert], aliases=ALIASES)
    check("H4 Levio x Bertelsmann (multi-empregador, regra Levio/TYTAN): NAO funde",
          rem == [] and "levio" not in ALIASES, f"removed={len(rem)}")
    # guardrails continuam valendo POS-alias
    a_sal = _fix("lidlstiftup2|sf_dataset:successfactors:1", "lidlstiftup2",
                 "Praktikum Einkauf", "Neckarsulm, DE", "sf_dataset:successfactors",
                 salary="2.280 €")
    b_sal = _fix("Lidl Stiftung & Co. KG|absolventa:1", "Lidl Stiftung & Co. KG",
                 "Praktikum Einkauf", "74167 Neckarsulm", "absolventa", salary="1.800 €")
    _, _, rem = deduplicate_cross_source([dict(a_sal), dict(b_sal)], aliases=ALIASES)
    check("H5 salario divergente rejeita o par mesmo com empresa resolvida",
          rem == [], f"removed={len(rem)}")
    a_cty = _fix("lidlstiftup2|sf_dataset:successfactors:2", "lidlstiftup2",
                 "Praktikum Einkauf", "Neckarsulm, DE", "sf_dataset:successfactors", country="de")
    b_cty = _fix("Lidl Stiftung & Co. KG|absolventa:2", "Lidl Stiftung & Co. KG",
                 "Praktikum Einkauf", "74167 Neckarsulm", "absolventa", country="nl")
    _, _, rem = deduplicate_cross_source([dict(a_cty), dict(b_cty)], aliases=ALIASES)
    check("H6 country divergente rejeita o par mesmo com empresa resolvida",
          rem == [], f"removed={len(rem)}")
    # idempotencia com aliases: re-rodar e no-op
    uni = [dict(LIDL_SF), dict(LIDL_REPOST), dict(LIDL_EXPORT_SF), dict(LIDL_EXPORT_ABS)]
    out1, s1, _ = deduplicate_cross_source(uni, aliases=ALIASES)
    out2, s2, rem2 = deduplicate_cross_source(copy_dicts(out1), aliases=ALIASES)
    check("H7 idempotente: re-rodar sobre o output e no-op",
          s2 == {} and rem2 == [], f"stats2={dict(s2)}")
    # determinismo: mesma entrada -> mesma saida (2 execucoes independentes)
    o_a, s_a, r_a = deduplicate_cross_source(copy_dicts(uni), aliases=ALIASES)
    o_b, s_b, r_b = deduplicate_cross_source(copy_dicts(uni), aliases=ALIASES)
    check("H8 determinista: execucoes independentes identicas",
          [j["id"] for j in o_a] == [j["id"] for j in o_b] and s_a == s_b
          and [d.get("duplicate_of") for _, d, _ in r_a] == [d.get("duplicate_of") for _, d, _ in r_b])
    # nenhum UNICO (sem twin) sai do conjunto por causa do alias
    check("H9 nenhuma vaga sem twin e removida (todas as removidas tem canonico no output)",
          {d["id"] for _, d, _ in r_a} <= {j["id"] for j in uni} - {j["id"] for j in o_a}
          and len(o_a) + len(r_a) == len(uni),
          f"out={len(o_a)} removed={len(r_a)} in={len(uni)}")
    # tiers classicos (1-5) INTACTOS: sem alias, mesmo par nao funde neles
    out_cls, stats_cls, _ = deduplicate([dict(LIDL_SF), dict(LIDL_REPOST)])
    check("H10 tiers classicos (1-5) NAO fundem o par Lidl (dominio do alias e SO o F48)",
          len(out_cls) == 2, f"out={len(out_cls)}")


def copy_dicts(jobs):
    return [dict(j) for j in jobs]


# ===========================================================================
# I. Integracao: pipeline, auto-load e CI
# ===========================================================================

def test_integracao() -> None:
    section("F66.I integracao: call site do cli, auto-load e ci.yml")
    cli_src = (ROOT / "src" / "internship_finder" / "cli.py").read_text(encoding="utf-8")
    check("I1 cli.py chama deduplicate_cross_source(selected) SEM aliases "
          "(auto-load do padrao — producao pega o mapa pela raiz do repo)",
          re.search(r"deduplicate_cross_source\(selected\)", cli_src) is not None)
    # auto-load: cwd na RAIZ do repo acha o arquivo (producao/CI rodam daqui)
    import os
    cwd_prev = os.getcwd()
    try:
        os.chdir(ROOT)
        auto = load_company_aliases()
        _out, _s, rem = deduplicate_cross_source([dict(LIDL_SF), dict(LIDL_REPOST)])
    finally:
        os.chdir(cwd_prev)
    check("I2 auto-load do padrao (cwd=raiz): mapa carrega e o par Lidl funde",
          auto == ALIASES and len(rem) == 1, f"auto={len(auto)} removed={len(rem)}")
    # fora da raiz do repo o padrao relativo NAO existe: sem aliases, sem erro
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        cwd_prev2 = os.getcwd()
        try:
            os.chdir(td)
            outside = load_company_aliases()
        finally:
            os.chdir(cwd_prev2)
    check("I3 cwd fora da raiz: padrao nao achado -> {} (degradacao graciosa, "
          "o estagio NUNCA crasha por config ausente)", outside == {}, str(outside))
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    m = re.search(r"tests=\(([^)]*)\)", ci, re.S)
    arr = m.group(1).split() if m else []
    check("I4 test_f66 presente no array do CI (uniao por presenca)",
          "test_f66" in arr, f"{len(arr)} suites")
    check("I5 array vivo e relativo (nunca contagem exata)", len(arr) >= 106, f"{len(arr)}")
    missing = [t for t in arr if not (SCRIPTS / f"{t}.py").exists()]
    check("I6 todo token do array tem arquivo (sanity da uniao)", missing == [], str(missing))


def main() -> int:
    test_config()
    test_loader()
    test_canonical()
    test_identity_pura()
    test_display_alias_nao_cobre()
    test_pares_registro()
    test_pares_varredura()
    test_contra_cases()
    test_integracao()
    fails = [c for c in CHECKS if not c[1]]
    print(f"\n{'=' * 60}")
    print(f"F66: {len(CHECKS)} checks, {len(fails)} falhas")
    for name, _, detail in fails:
        print(f"  FAIL: {name}" + (f" — {detail}" if detail else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
