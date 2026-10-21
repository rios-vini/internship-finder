#!/usr/bin/env python3
"""F92 — gêmeos residuais: aliases canônicos + guards de location (offline).

4 classes que o F66 não cura (spec F92, medições âncora 21/10 ~02:20 UTC,
re-medidas no Passo 0 contra o eligible de 21/10 09:43 UTC — 710 vagas):

- Classe 1 (labels-lixo upstream): "SUSONITY" 2 vagas = portal da Merck
  (URLs jobs.vibrantm.com/merck/...); "Fa Exdu Saasfaprod1" 1 = Daimler
  Buses (título literal "... Einkauf Daimler Buses am Standort Mannheim");
  "gacmotoreuropebv-1747132357" 2 = tenant teamtailor da GAC Motor.
- Classe 2 (descasamento dataset×dataset): peeces (join_com) × Peeces GmbH
  (absolventa); axessintelligence × axess Intelligence GmbH; rfi-trading ×
  RFI Food Ingredients (twin fora do pool no dia da medição — alias fica
  para o retorno); ELIA (eures) × Elia System Operator SA (successfactors).
- Classe 3 (razão legal de subsidiária): NÃO tratada por design (spec item
  3 — só relatório; collapse muda contagens de cap). Contrato testado: o
  mapa F92 NUNCA contém label Lidl.
- Classe 4 (guards de location): prefixo postal (105 vagas medidas:
  "70469 Stuttgart, ..." etc.) e vazia/None (33 medidas: 32 absolventa +
  1 jobmensa — raw=None/{} no dataset, o fallback do raw vive para fontes
  que o carregam, ex.: join_com raw['location']).

Desenho (decidido no Passo 0): mapa versionado
``config/company_aliases.json`` aplicado por UM estágio de normalização no
``cli.main`` ENTRE ``select_eligible`` e ``deduplicate`` — o CAMPO company
muda (dedup + display veem o canônico); ``id``/``url``/``raw`` NÃO mudam
(identidade técnica de dataset_seen/JSONL preservada; reversível). O
sentinela "—" NUNCA é chave de dedup (``normalize_location`` devolve "") —
o guardrail "sem localização não funde" fica intacto. Loader fail-closed
(padrão F66/F13): arquivo ruim = estágio no-op.

Efeito medido honesto (Passo 0, A/B no eligible do dia): o guard postal
ENABLE fusões reais (1 Mercedes-Benz medida: "74167 Neckarsulm" ×
"Neckarsulm"); os pares da classe 2 NÃO fundem hoje porque o lado
absolventa tem location ausente E raw vazio (guardrail conservador por
design — zero falsos merges > completude); o alerta F75 SOBE 10→13
(radar passa a ENXERGAR 3 grupos antes escondidos pela divergência de
labels) — documentado no relatório, abaixo do limiar de alerta (>20).

Fixtures VERBATIM da medição do dia (títulos/labels/locations reais).
Zero rede; tempdir; nada de data/ de produção.

Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from internship_finder import cli  # noqa: E402
from internship_finder import company_aliases as ca  # noqa: E402
from internship_finder.dedup import (  # noqa: E402
    KEY_COMPANY_TITLE_LOCATION,
    deduplicate,
    normalize_location,
)

RESULTS: list[tuple[bool, str]] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((bool(cond), label))
    suffix = f" ({detail})" if (detail and not cond) else ""
    print(("  [OK] " if cond else "  [FAIL] ") + label + suffix)


def _job(
    company: str,
    title: str,
    location: str | None,
    *,
    source: str = "t",
    jid: str | int = 1,
    raw: dict | None = None,
    url: str | None = None,
) -> dict:
    """Vaga dict mínima (mesmos campos que o pipeline opera em cli.main)."""
    return {
        "id": f"{company}|{source}:{jid}",
        "source": source,
        "title": title,
        "company": company,
        "location": location,
        "url": url or f"https://example.test/{jid}",
        "collected_at": "2026-10-21T09:00:00+00:00",
        "raw": raw,
    }


# Fixtures VERBATIM da medição 21/10 09:43 UTC (eligible real).
F_SUSONITY_TITLE = "Intern Commercial Controlling Process Solutions (all genders)"
F_SUSONITY_LOC = "Darmstadt, Hessen, DE, 64293"
F_SUSONITY_URL = (
    "https://jobs.vibrantm.com/merck/job/"
    "Darmstadt-Intern-Commercial-Controlling-Process-Solutions"
)
F_PEECES_TITLE = "SUPPLY CHAIN MANAGEMENT (M/W/D) | Praktikum | Start Up"
F_JOIN_URL = "https://join.com/companies/peeces/jobs/16371371-supply-chain"
F_ABS_URL = "https://www.absolventa.de/stellenangebote/13414286-b-supply-chain"
F_MERC_TITLE = "Praktikant*in Einkauf Motorsteuerung (Pflichtpraktikum)"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="f92_suite_"))

    print("== F92 A: mapa canônico — loader fail-closed + validação (spec item 5) ==")
    real_path = ROOT / "config" / "company_aliases.json"
    check("A1 arquivo versionado existe (config/company_aliases.json)",
          real_path.is_file())
    check("A2 default do módulo aponta o arquivo do repo",
          ca.DEFAULT_COMPANY_ALIASES_PATH.name == "company_aliases.json"
          and ca.DEFAULT_COMPANY_ALIASES_PATH.parent.name == "config"
          and ca.DEFAULT_COMPANY_ALIASES_PATH.is_file())
    aliases = ca.load_company_aliases()
    check("A3 mapa real carrega (7 aliases medidos)",
          len(aliases) >= 7, f"n={len(aliases)}")
    check("A4 bem-formado: pares str->str não-vazios",
          all(isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip()
              for k, v in aliases.items()))
    keys_cf = [k.strip().casefold() for k in aliases]
    check("A5 sem colisões (chaves únicas no casefold)",
          len(set(keys_cf)) == len(keys_cf))
    check("A6 sem ciclos (nenhum valor é também chave)",
          all(v.strip().casefold() not in set(aliases) for v in aliases.values()))
    check("A7 sem auto-alias (chave == valor casefold)",
          all(k != v.strip().casefold() for k, v in aliases.items()))
    check("A8 loader: arquivo ausente -> {} (fail-closed, nunca crasha)",
          ca.load_company_aliases(tmp / "nao_existe.json") == {})
    (tmp / "corrompido.json").write_text("{oops", encoding="utf-8")
    check("A9 loader: JSON corrompido -> {}",
          ca.load_company_aliases(tmp / "corrompido.json") == {})
    (tmp / "estrutura.json").write_text(json.dumps({"aliases": ["x"]}),
                                        encoding="utf-8")
    check("A10 loader: estrutura inválida (aliases=list) -> {}",
          ca.load_company_aliases(tmp / "estrutura.json") == {})
    (tmp / "vazio.json").write_text(json.dumps({"aliases": {" ": "Co"}}),
                                    encoding="utf-8")
    check("A11 loader: chave só-espaços -> {}",
          ca.load_company_aliases(tmp / "vazio.json") == {})
    (tmp / "colisao.json").write_text(
        json.dumps({"aliases": {"Alpha": "A Corp", "ALPHA": "B Corp"}}),
        encoding="utf-8")
    check("A12 loader: colisão casefold c/ valores distintos rejeita INTEIRO",
          ca.load_company_aliases(tmp / "colisao.json") == {})
    (tmp / "ciclo.json").write_text(
        json.dumps({"aliases": {"dirty": "Clean Co", "clean co": "Other"}}),
        encoding="utf-8")
    check("A13 loader: ciclo/chain (valor é outra chave) rejeita INTEIRO",
          ca.load_company_aliases(tmp / "ciclo.json") == {})
    (tmp / "autoalias.json").write_text(
        json.dumps({"aliases": {"Same": "SAME"}}), encoding="utf-8")
    check("A14 loader: auto-alias é no-op (mapa vazio, sem crash)",
          ca.load_company_aliases(tmp / "autoalias.json") == {})

    print("\n== F92 B: aliases aplicados — canônico no dado, vaga intacta sem alias ==")
    susonity = _job("SUSONITY", F_SUSONITY_TITLE, F_SUSONITY_LOC,
                    source="sf_dataset:successfactors", jid="421751",
                    raw={"location": "Darmstadt, Hessen, DE, 64293"})
    antes = json.loads(json.dumps(susonity))
    n = ca.apply_company_aliases([susonity], aliases)
    check("B1 label suja -> campo company vira o canônico (Merck KGaA)",
          susonity["company"] == "Merck KGaA" and n == 1)
    check("B2 id/url/raw/title/location intactos (identidade técnica preservada)",
          susonity["id"] == antes["id"] and susonity["url"] == antes["url"]
          and susonity["raw"] == antes["raw"]
          and susonity["title"] == antes["title"]
          and susonity["location"] == antes["location"])
    limpa = _job("Peeces GmbH", F_PEECES_TITLE, "Aachen, Germany",
                 source="absolventa", jid="13414286")
    antes2 = json.loads(json.dumps(limpa))
    n2 = ca.apply_company_aliases([limpa], aliases)
    check("B3 alias ausente -> vaga intacta byte a byte",
          n2 == 0 and json.dumps(limpa, sort_keys=True)
          == json.dumps(antes2, sort_keys=True))
    minuscula = _job("susonity", F_SUSONITY_TITLE, F_SUSONITY_LOC)
    n3 = ca.apply_company_aliases([minuscula], aliases)
    check("B4 match é casefold inteiro ('susonity' casa 'SUSONITY')",
          minuscula["company"] == "Merck KGaA" and n3 == 1)
    check("B5 mapa vazio -> 0 aplicados, sem crash",
          ca.apply_company_aliases([_job("X", "t", None)], {}) == 0)
    semeco = _job("", "t", None)
    nula = _job("X", "t", None)
    nula["company"] = None
    check("B6 company vazia/None -> skip sem crash",
          ca.apply_company_aliases([semeco, nula], aliases) == 0)
    substringe = _job("peeces gmbh & co", "t", None)
    n4 = ca.apply_company_aliases([substringe], aliases)
    check("B7 nunca substring (label irmã não-curatada fica intacta)",
          n4 == 0 and substringe["company"] == "peeces gmbh & co")

    print("\n== F92 C: dedup pega o par por nome canônico (guardrail intacto) ==")
    par_sem_alias = [
        _job("peeces", F_PEECES_TITLE, "Aachen, Germany",
             source="sf_dataset:join_com", jid="16371371", url=F_JOIN_URL),
        _job("Peeces GmbH", F_PEECES_TITLE, "Aachen, Germany",
             source="absolventa", jid="13414286", url=F_ABS_URL),
    ]
    out, stats, _ = deduplicate(json.loads(json.dumps(par_sem_alias)))
    check("C1 SEM alias: labels distintos = empresas distintas (2 ficam)",
          len(out) == 2)
    par_com_alias = json.loads(json.dumps(par_sem_alias))
    ca.apply_company_aliases(par_com_alias, aliases)
    out2, stats2, removed2 = deduplicate(par_com_alias)
    check("C2 COM alias: dedup pega o par (1 fica)",
          len(out2) == 1, f"stats={stats2}")
    check("C3 sobrevivente exibe o nome canônico (display: 'Peeces GmbH')",
          out2[0]["company"] == "Peeces GmbH")
    check("C4 fusão registrada no tier company+title+location",
          stats2.get(KEY_COMPANY_TITLE_LOCATION) == 1 and len(removed2) == 1)
    # O par REAL do pool (twin absolventa tem location ausente e raw vazio):
    par_real = [
        _job("peeces", F_PEECES_TITLE, "Aachen, Germany",
             source="sf_dataset:join_com", jid="16371371"),
        _job("Peeces GmbH", F_PEECES_TITLE, None,
             source="absolventa", jid="13414286", raw=None),
    ]
    ca.apply_company_aliases(par_real, aliases)
    ca.apply_location_guards(par_real)
    out3, stats3, _ = deduplicate(par_real)
    check("C5 guardrail: location ausente de um lado NÃO funde (2 ficam) — "
          "contrato conservador documentado",
          len(out3) == 2)
    check("C6 sentinela '—' NUNCA é chave de dedup (normalize_location='')",
          normalize_location(ca.MISSING_LOCATION) == "")
    duas_cegas = [
        _job("Peeces GmbH", F_PEECES_TITLE, None, jid=1),
        _job("Peeces GmbH", F_PEECES_TITLE, None, jid=2),
    ]
    ca.apply_location_guards(duas_cegas)
    out4, _, _ = deduplicate(duas_cegas)
    check("C7 duas vagas sem localização (ambas '—') não fundem",
          len(out4) == 2)
    mista = [
        _job("Peeces GmbH", F_PEECES_TITLE, None, jid=1),
        _job("Peeces GmbH", F_PEECES_TITLE, "Aachen, Germany", jid=2),
    ]
    ca.apply_location_guards(mista)
    out5, _, _ = deduplicate(mista)
    check("C8 '—' × cidade real não funde (só localização REAL casa)",
          len(out5) == 2)
    postal_pair = [
        _job("Mercedes-Benz AG", F_MERC_TITLE, "74167 Neckarsulm",
             source="absolventa", jid="13435315"),
        _job("Mercedes-Benz AG", F_MERC_TITLE, "Neckarsulm",
             source="absolventa", jid="13435316"),
    ]
    out6, _, _ = deduplicate(json.loads(json.dumps(postal_pair)))
    check("C9 SEM guard: prefixo postal separa a mesma cidade (2 ficam)",
          len(out6) == 2)
    postal_guarded = json.loads(json.dumps(postal_pair))
    gstats = ca.apply_location_guards(postal_guarded)
    out7, stats7, _ = deduplicate(postal_guarded)
    check("C10 COM guard: '74167 Neckarsulm'=='Neckarsulm' -> funde (fusão "
          "real medida no eligible 21/10)",
          len(out7) == 1 and stats7.get(KEY_COMPANY_TITLE_LOCATION) == 1
          and gstats["location_postal_stripped"] == 1)

    print("\n== F92 D: guards de location (spec item 4 — fixtures medidas) ==")
    check("D1 postal strip real BA: '70469 Stuttgart, Baden_Wuerttemberg, "
          "Deutschland' -> cidade fica",
          ca.location_guard(
              "70469 Stuttgart, Baden_Wuerttemberg, Deutschland", None)
          == "Stuttgart, Baden_Wuerttemberg, Deutschland")
    check("D2 postal strip real BA 2: '84130 Dingolfing, Bayern, Deutschland'",
          ca.location_guard("84130 Dingolfing, Bayern, Deutschland", None)
          == "Dingolfing, Bayern, Deutschland")
    check("D3 postal strip absolventa: '74167 Neckarsulm' -> 'Neckarsulm'",
          ca.location_guard("74167 Neckarsulm", None) == "Neckarsulm")
    check("D4 None + raw['location'] útil (join_com) -> preenchida do raw",
          ca.location_guard(None, {"location": "Aachen, Germany"})
          == "Aachen, Germany")
    check("D5 raw com postal também é limpado",
          ca.location_guard(None, {"location": "50667 Köln"})
          == "Köln")
    check("D6 None + raw={} (jobmensa) -> sentinela '—'",
          ca.location_guard(None, {}) == ca.MISSING_LOCATION)
    check("D7 raw=None (absolventa) -> sentinela '—'",
          ca.location_guard(None, None) == ca.MISSING_LOCATION)
    check("D8 location vazia (só espaços) também é guarda (spec: 'vazia/None')",
          ca.location_guard("   ", {"ort": "Aachen"}) == "Aachen")
    jlimpa = _job("X", "t", "Mannheim, Baden-Wuerttemberg, Germany")
    antes3 = jlimpa["location"]
    ca.apply_location_guards([jlimpa])
    check("D9 location já limpa -> inalterada (nunca reescreve por igual)",
          jlimpa["location"] == antes3)
    lote = [
        _job("A", "t", "70469 Stuttgart, BW", jid=1),
        _job("B", "t", None, jid=2, raw={"location": "Aachen, Germany"}),
        _job("C", "t", None, jid=3, raw={}),
    ]
    stats_d = ca.apply_location_guards(lote)
    check("D10 stats: postal/raw/sentinela contam separadamente",
          stats_d == {"location_postal_stripped": 1,
                      "location_filled_from_raw": 1,
                      "location_missing_sentinel": 1}
          and lote[0]["location"] == "Stuttgart, BW"
          and lote[1]["location"] == "Aachen, Germany"
          and lote[2]["location"] == "—")
    stats_d2 = ca.apply_location_guards(lote)
    check("D11 idempotente: 2ª passada não muda nada (stats zerados)",
          stats_d2 == {"location_postal_stripped": 0,
                       "location_filled_from_raw": 0,
                       "location_missing_sentinel": 0}
          and lote[0]["location"] == "Stuttgart, BW")

    print("\n== F92 E: curadoria do mapa real (medições da fase) ==")
    chaves_esperadas = {
        "SUSONITY", "Fa Exdu Saasfaprod1", "gacmotoreuropebv-1747132357",
        "peeces", "axessintelligence", "rfi-trading", "ELIA",
    }
    e1_diff = {k.casefold() for k in chaves_esperadas} ^ set(aliases.keys())
    check("E1 as 7 labels medidas estão no mapa (classes 1 e 2)",
          not e1_diff, f"diff={e1_diff}")
    valores_esperados = {
        "Merck KGaA", "Daimler Buses GmbH", "GAC Motor", "Peeces GmbH",
        "axess Intelligence GmbH", "RFI Food Ingredients",
        "Elia System Operator SA",
    }
    check("E2 os 7 canônicos medidos estão no mapa",
          valores_esperados == set(aliases.values()))
    check("E3 classe 3 FORA por design (spec item 3): nenhum label Lidl "
          "no mapa (collapse de subsidiária = só relatório)",
          all("lidl" not in k.casefold() and "lidl" not in v.casefold()
              for k, v in aliases.items()))
    f66 = json.loads((ROOT / "config" / "dedup_company_aliases.json")
                     .read_text(encoding="utf-8"))["aliases"]
    check("E4 chaves F92 ∩ chaves F66 = ∅ (curadorias separadas)",
          not (set(aliases) & set(f66)))
    f54 = json.loads((ROOT / "config" / "display_aliases.json")
                     .read_text(encoding="utf-8"))["aliases"]
    check("E5 canônicos F92 não são re-aliasados pelo F54 no render "
          "(valores ∩ chaves F54 = ∅)",
          not (set(aliases.values()) & set(f54)))
    import ranking_digest as rdigest  # noqa: E402

    watch_path = ROOT / "config" / "company_watchlist.json"
    watch_raw = json.loads(watch_path.read_text(encoding="utf-8"))
    watch = watch_raw.get("companies", watch_raw) if isinstance(
        watch_raw, dict) else watch_raw
    watch_norm = {rdigest._norm_company(c) for c in watch}
    envolvidos = set(aliases) | set(aliases.values())
    check("E6 nenhuma label envolvida é string curada da watchlist "
          "(canonização não quebra o radar F13)",
          not (watch_norm & {rdigest._norm_company(x) for x in envolvidos}))

    print("\n== F92 F: integração end-to-end pelo cli.main (modo filtro) ==")
    fixture = [
        {
            "id": "SUSONITY|sf_dataset:successfactors:421751",
            "source": "sf_dataset:successfactors",
            "title": "Praktikum im Bereich Einkauf (m/w/d)",
            "company": "SUSONITY",
            "location": "64293 Darmstadt, Hessen, Germany",
            "url": F_SUSONITY_URL,
            "country": "de",
            "country_iso": "de",
            "internship": True,
            "collected_at": "2026-10-21T09:00:00+00:00",
            "raw": {"location": "Darmstadt, Hessen, DE, 64293"},
        },
        {
            "id": "peeces|sf_dataset:join_com:16371371",
            "source": "sf_dataset:join_com",
            "title": "Praktikum im Bereich Einkauf (m/w/d)",
            "company": "peeces",
            "location": None,
            "url": F_JOIN_URL,
            "country": "de",
            "country_iso": "de",
            "internship": True,
            "collected_at": "2026-10-21T09:00:00+00:00",
            "raw": {"location": "Aachen, Germany"},
        },
        {
            "id": "SemLoc|jobmensa:9",
            "source": "jobmensa",
            "title": "Praktikum im Bereich Einkauf",
            "company": "ACME Logistik GmbH",
            "location": None,
            "url": "https://www.jobmensa.de/x",
            "country": "de",
            "country_iso": "de",
            "internship": True,
            "collected_at": "2026-10-21T09:00:00+00:00",
            "raw": {},
        },
    ]
    fin = tmp / "jobs_in.json"
    fout = tmp / "eligible_out.json"
    fmetrics = tmp / "metrics.jsonl"
    fin.write_text(json.dumps(fixture), encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["--input", str(fin), "--output", str(fout),
                       "--metrics", str(fmetrics)])
    check("F1 cli.main modo filtro: rc=0 (sem rede, estágio F92 no meio)",
          rc == 0, f"rc={rc}")
    eligible = json.loads(fout.read_text(encoding="utf-8"))
    by_id = {j["id"]: j for j in eligible}
    check("F2 SUSONITY sai do pipeline como 'Merck KGaA' (display canônico) "
          "com o id técnico intacto",
          by_id.get("SUSONITY|sf_dataset:successfactors:421751", {})
          .get("company") == "Merck KGaA")
    check("F3 prefixo postal limpo no eligible ('64293 Darmstadt…' -> "
          "'Darmstadt…')",
          by_id.get("SUSONITY|sf_dataset:successfactors:421751", {})
          .get("location") == "Darmstadt, Hessen, Germany")
    check("F4 location None + raw útil -> preenchida do raw (join_com)",
          by_id.get("peeces|sf_dataset:join_com:16371371", {})
          .get("location") == "Aachen, Germany"
          and by_id.get("peeces|sf_dataset:join_com:16371371", {})
          .get("company") == "Peeces GmbH")
    check("F5 location None sem raw -> sentinela '—' no eligible",
          by_id.get("SemLoc|jobmensa:9", {}).get("location") == "—")
    check("F6 estágio reporta no stdout do CLI (observável no log do cron)",
          "Normalização de ingestão (F92)" in buf.getvalue()
          and "empresas canônicas : 2" in buf.getvalue())

    print()
    fails = [label for ok, label in RESULTS if not ok]
    print(f"F92: {len(RESULTS)} checks, {len(fails)} falhas")
    if fails:
        for f in fails:
            print(f"  FAIL: {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
