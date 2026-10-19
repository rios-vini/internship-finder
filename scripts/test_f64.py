''''true; V="$(dirname "$0")/../.venv/bin/python"; [ -x "$V" ] || V=python3; exec "$V" -- "$0" "$@" # '''
"""Suite F64 — Benchmark desfechos x score: 37 rotulos reais (registro 10/2026).

Poliglota de 1 linha (bash: ``exec`` re-invoca sob python3; python: string
no-op) — mesmo contrato do test_f59. 100% OFFLINE: nenhum socket, nenhum
data/ de producao (a mediacao REAL rodou sobre copias congeladas e vive no
relatorio da fase + ``f64_results.json`` do handoff; o CI valida o dataset,
a logica do harness e os fixtures).

Contrato da fase:

1. DATASET ``benchmarks/outcomes_2026-10.jsonl`` — 37 linhas, schema por
   linha ``{job_id, source, score, rank, verdict, reason_class, date,
   notes}`` + extensoes F64 ``dup_of`` (linha e re-listagem/twin da vaga
   canônica) e ``linkable`` (id existe no archive do dia). Contagens
   RECONCILIADAS com o registro (ver comentario G1): a decomposicao citada
   na card ("5+12+13+1+6+1") soma 38 e conta o lote DE no estado INICIAL
   (preparada) E na re-listagem (ja-no-funil); a contagem honesta por LINHA
   e 9/7/1/13/6/1 = 37.
2. PROVENANCE ``benchmarks/REGISTRO-AVALIACOES-VAGAS-2026-10.md`` — copia
   verbatim do registro do dono (anexo preservado pelo orquestrador).
3. HARNESS ``scripts/f64_outcomes.py`` — logica pura validada em fixtures
   sinteticas: filtro de pares, tau same-day/pooled (FUNCAO OFICIAL
   ``pairwise_concordance`` — assert de identidade), bandas pre-declaradas,
   top-k, tabela fato x veredito, e o caminho end-to-end ``measure()``
   (inclui os imports de materials/eu_ranking).
4. DEDUP F48 (bonus da card): os 3 PARES REAIS rotulados pelo dono como
   mesma vaga em outra fonte entram como fixtures VERBATIM (campos
   estruturais ipsis literis do archive 18/10). CANARY ATUALIZADO PELA F66
   (19/10, comemoracao prevista aqui): o par Lidl re-post AGORA FUNDE via
   alias de identidade tenant-label (lidlstiftup2 -> Lidl Stiftung & Co.
   KG); Wuerth (cidade vazia + filial) e Bosch Strategic (bag DE/EN do
   titulo) seguem NAO fundindo — bloqueios restantes documentados. Nunca
   "conserte" o teste as cegas: toda mudanca de expectativa e consciente
   (ver relatorio F64 §dedup e o test_f66, que e o dono do mecanismo).
5. ``.github/workflows/ci.yml`` contem test_f64 no array ``tests=``
   (uniao RELATIVA: >= 101 suites — assert relativo, regra da casa).
"""

import json
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from internship_finder import ranking_benchmark  # noqa: E402
from internship_finder.cross_source_dedup import (  # noqa: E402
    KEY_CROSS_SOURCE,
    _de_en_title_key,
    canonical_company,
    city_key,
    company_identity,
    deduplicate_cross_source,
    load_company_aliases,
)

import f64_outcomes as h  # noqa: E402

CHECKS: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


# ---------------------------------------------------------------------------
# G1 — dataset outcomes_2026-10.jsonl (schema + contagens reconciliadas)
# ---------------------------------------------------------------------------
JL = ROOT / "benchmarks" / "outcomes_2026-10.jsonl"
rows = [json.loads(l) for l in JL.read_text(encoding="utf-8").splitlines() if l.strip()]

check("G1 dataset existe com 37 linhas", len(rows) == 37, f"n={len(rows)}")
REQ = ("job_id", "source", "score", "rank", "verdict", "reason_class", "date", "notes")
REQ_STR = ("job_id", "source", "verdict", "reason_class", "date", "notes")
check("G1 schema: 8 campos obrigatorios presentes; 6 textuais nao-vazios "
      "(score/rank podem ser None nas linhas fora do ranking)",
      all(all(k in r for k in REQ) and all(str(r.get(k) or "").strip() for k in REQ_STR) for r in rows))
check("G1 extensoes F64 presentes (dup_of/linkable)",
      all(("dup_of" in r and "linkable" in r) for r in rows))
vc = Counter(r["verdict"] for r in rows)
check("G1 contagem verdicts reconciliada (9 enviada/7 preparada/1 pendente/13 eliminada/6 ja_no_funil/1 dup)",
      vc == Counter({"eliminada": 13, "enviada": 9, "preparada": 7, "ja_no_funil": 6, "pendente": 1, "dup": 1}),
      str(dict(vc)))
rc = Counter(r["reason_class"] for r in rows)
check("G1 contagem reason_class padronizada",
      rc == Counter({"good_fit": 22, "language_block": 6, "off_axis": 3, "visa_block": 1,
                     "start_date_conflict": 1, "duration": 1, "job_type": 1, "dup": 1, "undocumented": 1}),
      str(dict(rc)))
pairs_day = [(r["date"], r["job_id"]) for r in rows]
check("G1 (date, job_id) unico em 37 linhas", len(pairs_day) == len(set(pairs_day)))
relisted = [k for k, c in Counter(r["job_id"] for r in rows).items() if c > 1]
check("G1 5 job_ids re-listados por id exato (Wuerth/TRUMPF/B.Braun/Bosch Ansbach/KPMG); "
      "o 6o (Lidl SAP BI) re-lista com ID MIGRADO entre dias e liga via dup_of",
      len(relisted) == 5, f"{len(relisted)}: {relisted}")
check("G1 Lidl SAP BI: id migrou 13/10 (successfactors:lidlstiftuP2) -> 18/10 (sf_dataset:successfactors); "
      "re-listagem aponta dup_of para o id primario",
      any("lidlstiftuP2:1436050633" in r["job_id"] and r["date"] == "2026-10-13" for r in rows)
      and any("sf_dataset:successfactors:1436050633" in r["job_id"] and r["date"] == "2026-10-18"
              and r.get("dup_of") and "lidlstiftuP2" in r["dup_of"] for r in rows))
check("G1 8 linhas carregam dup_of (6 re-listagens + twin Wuerth + re-post Lidl)",
      sum(1 for r in rows if r.get("dup_of")) == 8,
      f"n={sum(1 for r in rows if r.get('dup_of'))}")
ids = {r["job_id"] for r in rows}
check("G1 dup_of aponta para job_id existente no dataset",
      all(r["dup_of"] in ids for r in rows if r.get("dup_of")))
check("G1 31 ligaveis (id no archive do dia) e 6 fora do ranking (LinkedIn)",
      sum(1 for r in rows if r.get("linkable")) == 31)
check("G1 ligavel exige score numerico + rank int>=1; nao-ligavel sem score/rank",
      all((isinstance(r["score"], (int, float)) and isinstance(r["rank"], int) and r["rank"] >= 1)
          for r in rows if r.get("linkable")) and
      all(r["score"] is None and r["rank"] is None for r in rows if not r.get("linkable")))
pr = h.pair_rows(rows)
check("G1 pares elegiveis = 22 (13 pos + 9 neg; exclui pendente/dup/re-listagens/nao-ligaveis)",
      len(pr) == 22 and Counter(h._label_of(r) for r in pr) == Counter({"boa": 13, "ruim": 9}),
      f"n={len(pr)}")
check("G1 datas dentro da janela do registro (13-18/10/2026)",
      {r["date"] for r in rows} == {"2026-10-13", "2026-10-14", "2026-10-17", "2026-10-18"})

# ---------------------------------------------------------------------------
# G2 — provenance: registro .md verbatim
# ---------------------------------------------------------------------------
MD = ROOT / "benchmarks" / "REGISTRO-AVALIACOES-VAGAS-2026-10.md"
md = MD.read_text(encoding="utf-8")
check("G2 registro .md commitado no repo", MD.exists())
check("G2 registro: titulo cabecalho", md.splitlines()[0].startswith("# REGISTRO DE AVALIAÇÕES DE VAGAS — Outubro 2026"))
check("G2 registro: insight central do dono (score != validade)",
      "score ≠ validade" in md and "KPMG 14.0 eliminada" in md and "Lidl Preis 7.0 aprovada" in md)
check("G2 registro: 6 verdicts nomeados",
      all(v in md for v in ("ENVIADA", "PREPARADA", "PENDENTE", "ELIMINADA", "DUP", "JÁ NO FUNIL")))
check("G2 registro: 3 pares de dedup citados (Wuerth twin, Bosch REF298797V, Lidl re-post 13231277)",
      "absolventa" in md and "REF298797V" in md and "13231277" in md)
check("G2 registro: classes de motivo cobertas pelo dataset (idioma/visto/duracao/tipo/off-axis)",
      all(s in md for s in ("Deutschkenntnisse", "Aufenthaltstitel", "12 meses", "Student assistant", "fora do eixo")))

# ---------------------------------------------------------------------------
# G3 — harness: funcao OFICIAL + logica pura em fixtures sinteticas
# ---------------------------------------------------------------------------
check("G3 harness usa a FUNCAO OFICIAL pairwise_concordance (identidade)",
      h.pairwise_concordance is ranking_benchmark.pairwise_concordance)

# load_outcomes valida schema
def _tmp_outcomes(rows_: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    for r in rows_:
        f.write(json.dumps(r) + "\n")
    f.close()
    return Path(f.name)


def _row(**kw):
    base = {"job_id": "X|sf:1", "source": "sf", "score": None, "rank": None,
            "verdict": "enviada", "reason_class": "good_fit", "date": "2026-01-02",
            "dup_of": None, "linkable": False, "notes": "synthetic"}
    base.update(kw)
    return base


loaded = h.load_outcomes(_tmp_outcomes([_row(), _row(job_id="X|sf:2")]))
check("G3 load_outcomes carrega jsonl valido", len(loaded) == 2)
for name, bad in (
    ("verdict invalida", _row(verdict="talvez")),
    ("reason_class invalida", _row(reason_class="gostei")),
    ("campo obrigatorio ausente", {k: v for k, v in _row().items() if k != "date"}),
    ("data fora de formato", _row(date="13/10/2026")),
    ("linkable sem score/rank", _row(linkable=True)),
):
    try:
        h.load_outcomes(_tmp_outcomes([_row(), bad]))
        check(f"G3 load_outcomes rejeita: {name}", False)
    except ValueError:
        check(f"G3 load_outcomes rejeita: {name}", True)

# pair_rows filtra pendente/dup_of/nao-ligavel
filt = h.pair_rows([
    _row(job_id="A|1", linkable=True, score=1, rank=1),
    _row(job_id="B|2", linkable=True, score=2, rank=2, verdict="pendente", reason_class="start_date_conflict"),
    _row(job_id="C|3", linkable=True, score=3, rank=3, verdict="ja_no_funil", dup_of="A|1"),
    _row(job_id="D|4", verdict="eliminada", reason_class="off_axis"),
])
check("G3 pair_rows exclui pendente/dup_of/nao-ligavel", [r["job_id"] for r in filt] == ["A|1"])

# tau same-day: dia perfeito + dia invertido -> agregado 2/3
day_rows = [
    _row(job_id="P1|1", date="2026-01-01", linkable=True, score=10, rank=1),
    _row(job_id="P2|2", date="2026-01-01", linkable=True, score=9, rank=2),
    _row(job_id="N1|3", date="2026-01-01", linkable=True, score=1, rank=3, verdict="eliminada", reason_class="off_axis"),
    _row(job_id="N2|4", date="2026-01-02", linkable=True, score=10, rank=1, verdict="eliminada", reason_class="off_axis"),
    _row(job_id="P3|5", date="2026-01-02", linkable=True, score=5, rank=2),
    _row(job_id="P4|6", date="2026-01-03", linkable=True, score=7, rank=1),
]
same = h.tau_same_day(day_rows)
check("G3 tau_same_day agrega por dia (2+0 de 2+1 pares -> tau +0.333)",
      same["comparable_pairs"] == 3 and same["concordant_pairs"] == 2 and same["tau"] == 0.333,
      f"got {same['comparable_pairs']}/{same['concordant_pairs']} tau={same['tau']}")
check("G3 tau_same_day ignora dia so-positivos (0 pares)", same["per_day"]["2026-01-03"]["comparable_pairs"] == 0)

# tau_pooled: empate de score -> desempate oficial por titulo
pool = h.tau_pooled([
    _row(job_id="A|a", linkable=True, score=10, rank=1, notes="titulo A"),
    _row(job_id="B|b", linkable=True, score=10, rank=2, verdict="eliminada", reason_class="off_axis", notes="titulo B"),
    _row(job_id="C|c", linkable=True, score=5, rank=3, notes="titulo C"),
])
check("G3 tau_pooled empate resolve pela chave oficial (1/2 -> tau 0.0)",
      pool["comparable_pairs"] == 2 and pool["concordant_pairs"] == 1 and pool["tau"] == 0.0,
      f"got {pool}")

# bandas pre-declaradas: bordas
band_rows = [
    _row(job_id="E|1", linkable=True, score=5.99, rank=1, verdict="eliminada", reason_class="off_axis"),
    _row(job_id="E|2", linkable=True, score=6.0, rank=2),
    _row(job_id="E|3", linkable=True, score=8.99, rank=3),
    _row(job_id="E|4", linkable=True, score=9.0, rank=4),
    _row(job_id="E|5", linkable=True, score=12.99, rank=5),
    _row(job_id="E|6", linkable=True, score=13.0, rank=6),
]
bands = h.score_bands(band_rows)
got = {(b["band"], b["n"]) for b in bands}
check("G3 bandas: bordas fechadas em [lo, hi)",
      got == {("-inf..6", 1), ("6..9", 2), ("9..11", 1), ("11..13", 1), (">=13", 1)}, str(got))

# top-k
tk = h.topk_precision(band_rows, k=2)
check("G3 topk k=2 sobre 6 linhas", tk["n"] == 2 and tk["positivos"] == 2 and tk["pct_positivos"] == 100.0)

# sinais fato x veredito
sig_rows = [
    _row(job_id="S|1", date="2026-01-01", linkable=True, score=10, rank=1),
    _row(job_id="S|2", date="2026-01-01", linkable=True, score=5, rank=2, verdict="eliminada", reason_class="off_axis"),
]
sig_snap = {"2026-01-01": {
    "S|1": {"score_breakdown": {"area": 2.0, "type": 1.0}},
    "S|2": {"score_breakdown": {"area": 0.0, "type": 1.0}},
}}
sig = h.signals_table(sig_rows, sig_snap)
check("G3 sinais: media/2x2 por componente",
      sig["componentes"]["area"]["media_pos"] == 2.0 and sig["componentes"]["area"]["media_neg"] == 0.0
      and sig["componentes"]["area"]["separacao"] == 2.0
      and sig["componentes"]["area"]["pos_sem_sinal"] == 0 and sig["componentes"]["area"]["neg_sem_sinal"] == 1)
check("G3 sinais: componente ausente em todas as linhas fica fora da tabela",
      "decay" not in sig["componentes"] and "skills" not in sig["componentes"])
check("G3 sinais: ordenacao por |separacao|", sig["ordenado_por_abs_separacao"][0] == "area")

# ---------------------------------------------------------------------------
# G4 — bonus dedup F48: 3 pares REAIS verbatim (archive 18/10)
# ---------------------------------------------------------------------------
def _fix(id_, company, title, location, source, country="de"):
    return {"id": id_, "company": company, "title": title, "location": location,
            "country": country, "source": source, "employment_type": None}


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
BOSCH_TWIN = _fix("Robert Bosch GmbH|direct:bundesagentur:15986-REF298797V-5acbda5-S", "Robert Bosch GmbH",
                  "Pflichtpraktikum im strategischen Einkauf von logistischen Transportdienstleistungen (w/m/div.)",
                  "70469 Stuttgart, Baden_Wuerttemberg, Deutschland", "direct:bundesagentur")
LIDL_SF = _fix("lidlstiftup2|sf_dataset:successfactors:1436050633", "lidlstiftup2",
               "Praktikum Controlling International - SAP BI Reporting",
               "Neckarsulm, DE", "sf_dataset:successfactors")
LIDL_REPOST = _fix("Lidl Stiftung & Co. KG|praktikum_info:13231277", "Lidl Stiftung & Co. KG",
                   "Praktikum Controlling International - SAP BI Reporting",
                   "74167 Neckarsulm", "praktikum_info")

# F66 (19/10): o canario foi atualizado COMEMORANDO — o par Lidl re-post
# agora FUNDE via alias de identidade tenant-label (lidlstiftup2 ->
# "Lidl Stiftung & Co. KG" em config/dedup_company_aliases.json, consumido
# pelo estagio cross-fonte F48). Os outros dois pares seguem NAO fundindo
# com os bloqueios RESTANTES documentados abaixo (a fusao deles exige
# mecanismos que NAO sao o mapa de tenant-label — ver test_f66 F6-F9).
_ALIASES_F66 = load_company_aliases(ROOT / "config" / "dedup_company_aliases.json")

for label, a, b in (("Wuerth SF x absolventa", WUERTH_SF, WUERTH_TWIN),
                    ("Bosch Strategic SR x arbeitsagentur", BOSCH_SR, BOSCH_TWIN)):
    _out, _stats, removed = deduplicate_cross_source(
        [dict(a), dict(b)], aliases=_ALIASES_F66)
    check(f"G4 par real '{label}': NAO funde (bloqueio restante pos-F66)",
          not removed, str(_stats))

_out_l, _stats_l, removed_l = deduplicate_cross_source(
    [dict(LIDL_SF), dict(LIDL_REPOST)], aliases=_ALIASES_F66)
check("G4 par real 'Lidl SAP BI x re-post praktikum_info': FUNDE "
      "(F66 fecha o gap 'SO identidade de empresa' — canario atualizado comemorando)",
      len(removed_l) == 1 and _stats_l == {KEY_CROSS_SOURCE: 1}, str(_stats_l))
check("G4 Lidl re-post fundido: canonico = registro do DATASET, twin sai com duplicate_of",
      removed_l[0][0]["id"] == LIDL_SF["id"]
      and removed_l[0][1].get("duplicate_of") == LIDL_SF["id"])

check("G4 Wuerth: bloqueio restante = cidade vazia (absolventa) + filial sem alias "
      "(regra Levio/TYTAN: 'Wuerth Group' e nome real de holding); titulo casaria",
      city_key(WUERTH_SF["location"]) == "bad mergentheim" and city_key(WUERTH_TWIN["location"]) == ""
      and company_identity(WUERTH_SF["company"]) == frozenset({"wurth"})
      and company_identity(WUERTH_TWIN["company"]) == frozenset({"service", "wurth", "industrie"})
      and _de_en_title_key(WUERTH_SF["title"]) == _de_en_title_key(WUERTH_TWIN["title"]))
check("G4 Bosch: bloqueio restante = SO bag DE/EN do titulo (empresa RESOLVIDA pelo "
      "alias F66: BoschGroup -> Robert Bosch GmbH); cidade casa",
      city_key(BOSCH_SR["location"]) == city_key(BOSCH_TWIN["location"]) == "stuttgart"
      and company_identity(canonical_company(BOSCH_SR["company"], _ALIASES_F66))
      == company_identity(canonical_company(BOSCH_TWIN["company"], _ALIASES_F66))
      and _de_en_title_key(BOSCH_SR["title"]) != _de_en_title_key(BOSCH_TWIN["title"]))
check("G4 Lidl re-post: identidade BRUTA diverge (company_identity pura preservada); "
      "alias F66 resolve; cidade+titulo casam",
      city_key(LIDL_SF["location"]) == city_key(LIDL_REPOST["location"]) == "neckarsulm"
      and _de_en_title_key(LIDL_SF["title"]) == _de_en_title_key(LIDL_REPOST["title"])
      and company_identity(LIDL_SF["company"]) == frozenset({"lidlstiftup2"})
      and company_identity(LIDL_REPOST["company"]) == frozenset({"lidl", "stiftung"}))
check("G4 o re-post esta rotulado no dataset (verdict=dup, dup_of=vaga canonica)",
      any(r["verdict"] == "dup" and "13231277" in r["job_id"] and r.get("dup_of") for r in rows))

# ---------------------------------------------------------------------------
# G5 — ci.yml: membership + uniao RELATIVA
# ---------------------------------------------------------------------------
ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
m = re.search(r"tests=\((.*?)\)", ci)
check("G5 ci.yml array tests= presente", m is not None)
toks = m.group(1).split() if m else []
check("G5 ci.yml contem test_f64 no array tests=", "test_f64" in toks)
check("G5 ci.yml uniao RELATIVA (>= 101 suites)", len(toks) >= 101, f"n={len(toks)}")
check("G5 ci.yml tokens do array puros (sem parenteses/fragmentos de comentario)",
      all("(" not in t and ")" not in t and "#" not in t for t in toks))

# ---------------------------------------------------------------------------
# G6 — measure() end-to-end em fixtures sinteticas (wiring completo offline)
# ---------------------------------------------------------------------------
D1 = "2026-01-02"
snap_jobs = [
    {"id": "ACME|sf:1", "title": "Praktikum Einkauf", "company": "ACME", "location": "Berlin, DE",
     "country": "de", "description": "procurement english", "source": "sf", "score": 10.0,
     "score_breakdown": {"area": 6.0, "skills": 0.0, "language": 2.0, "type": 1.0, "location": 1.0,
                         "penalties": 0.0, "registry": 0.0}},
    {"id": "BETA|sf:2", "title": "Praktikum Marketing", "company": "BETA", "location": "Hamburg, DE",
     "country": "de", "description": "marketing", "source": "sf", "score": 5.0,
     "score_breakdown": {"area": 3.0, "skills": 0.0, "language": 0.0, "type": 1.0, "location": 1.0,
                         "penalties": 0.0, "registry": 0.0}},
    {"id": "GAMMA|sf:3", "title": "Internship Supply Chain", "company": "GAMMA", "location": "Luxembourg, LU",
     "country": "lu", "description": "supply chain english", "source": "sf", "score": 8.0,
     "score_breakdown": {"area": 5.0, "skills": 1.0, "language": 1.0, "type": 1.0, "location": 0.0,
                         "penalties": 0.0, "registry": 1.0}},
]
with tempfile.TemporaryDirectory() as td:
    tdp = Path(td)
    oc = tdp / "outcomes.jsonl"
    oc.write_text("\n".join(json.dumps(r) for r in [
        _row(job_id="ACME|sf:1", score=10.0, rank=1, linkable=True, date=D1),
        _row(job_id="GAMMA|sf:3", score=8.0, rank=2, linkable=True, date=D1),
        _row(job_id="BETA|sf:2", score=5.0, rank=3, linkable=True, date=D1,
             verdict="eliminada", reason_class="off_axis"),
    ]) + "\n", encoding="utf-8")
    snap = tdp / "snap.json"
    snap.write_text(json.dumps(snap_jobs), encoding="utf-8")
    res = h.measure(str(oc), [f"{D1}={snap}"], [f"{D1}=2026-01-02T09:00:00+00:00"])

check("G6 measure(): estrutura completa (business/materials/eu/bandas/topk/sinais)",
      all(k in res for k in ("meta", "business", "materials", "eu_uniform_18_10",
                             "bandas_score", "precisao_topk", "sinais_fato_veredito")))
check("G6 measure(): business same-day hand-computado (2/2 -> tau +1.0)",
      res["business"]["same_day"]["comparable_pairs"] == 2
      and res["business"]["same_day"]["concordant_pairs"] == 2
      and res["business"]["same_day"]["tau"] == 1.0)
check("G6 measure(): materials re-score roda (imports vivos) com 2 pares e tau em [-1,1]",
      res["materials"]["same_day"]["comparable_pairs"] == 2
      and -1.0 <= res["materials"]["same_day"]["tau"] <= 1.0)
check("G6 measure(): EU estrato n=1 (so GAMMA lu) -> 0 pares comparaveis",
      res["eu_uniform_18_10"]["n"] == 1 and res["eu_uniform_18_10"]["comparable_pairs"] == 0)
check("G6 measure(): bandas — 9..11 com 1 positivo (100%) e -inf..6 com 1 negativo (0%)",
      {(b["band"], b["n"], b["pct_positivos"]) for b in res["bandas_score"]} ==
      {("-inf..6", 1, 0.0), ("6..9", 1, 100.0), ("9..11", 1, 100.0), ("11..13", 0, None), (">=13", 0, None)})
check("G6 measure(): sinais area sep = 2.5 (pos media 5.5 x neg 3.0)",
      res["sinais_fato_veredito"]["componentes"]["area"]["separacao"] == 2.5)


def main() -> int:
    fails = [c for c in CHECKS if not c[1]]
    print(f"F64: {len(CHECKS) - len(fails)} OK, {len(fails)} FAIL")
    for name, _, detail in fails:
        print(f"  FAIL: {name} {detail}")
    print("TUDO OK" if not fails else "HÁ FALHAS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
