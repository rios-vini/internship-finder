#!/usr/bin/env python3
"""F101 — blind_hydration p/ absolventa: verificação do caso real + regressão.

Origem: verificação 21/10 achou 3 vagas Mercedes-Benz/Daimler Buses
Einkauf (absolventa 13383618/13383432/13423232) com description VAZIA
no dataset — alto fit aparente (Einkauf/Pflicht-Praktikum), não-avaliáveis.

Passo 0 F101 (22/10, medições ao vivo, read-only — producao intocada):
- Pool vivo 708: 100 cegas <50 chars (absolventa 18, praktikum_info 1;
  sf_dataset:bundesagentur 80 FORA da lista — decisão F91 mantida:
  74/74 refnrs mortos na fonte).
- Sondas 4/4 HTTP 200 (169–266 KB), SEM login-wall/JS pesado — **GO**.
- JSON-LD JobPosting presente nas 3; classes de malformação REAIS:
  Mercedes-Benz = escape inválido ``\\x`` (só o tier 3 — reparo — cura;
  mesma classe medida na F91: 4/30, todos Mercedes), Daimler Buses =
  controle cru (tier 2 ``strict=False`` cura).
- Extração real via ``parse_job_description``: 3968/4418/4544 chars.

PREMISSA DA SPEC FALSIFICADA (o achado central da fase): "F91 cobre só
absolutenta/praktikum_info; absolventa fora do escopo" nasce do TYPO
"absolutenta" no commit/relatório da F91 — o código mergeado (#191)
atende exatamente ``("absolventa", "praktikum_info")`` e as 3 vagas
JÁ SÃO candidatas do estágio (13383432 medida entre as 18 vivas do
pool). As vagas seguem cegas em produção porque a flag
``INTERNSHIP_FINDER_BLIND_HYDRATION_BUDGET`` está OFF no ``.env``
(default regra 9) — botão do dono, não gap de código. "Estender o
estágio" é no-op; o delta REAL da fase: esta prova de regressão +
typo "absolutenta" corrigido nos comentários (raiz do mal-entendido).

O que esta suíte congela (contratos, espelhando test_f91):
- B: fonte ``absolventa`` NO estágio (a premissa que a F101 duvidou) +
  bundesagentur FORA (NÃO reabrir) + provenance ``hydrated_blind`` +
  limiar cego 50 distinto da janela F65 (500).
- A: fixtures REAIS capturadas no Passo 0 (bloco JSON-LD VERBATIM em
  ``scripts/fixtures_f101/``; capturas integrais no handoff da fase) —
  as duas classes de malformação reais + gates F22 intactos.
- C: as 3 vagas reais SÃO candidatas, na ordem do ranking.
- D: cenário REAL end-to-end: 3/3 hidratadas; re-score F56 9.5→9.0
  (language 0.0→-0.5 — o texto revela o alemão); re-assess honesto:
  ``german_required`` 3/3 (citação real "Sichere Deutsch- und
  Englischkenntnisse in Wort und Schrift" — F85 ``sicher`` → required)
  — descem do topo exibido; F37.3 remove do eligible no MESMO run;
  F87 cura ``desc_vazia``; métrica + persist JSON/CSV; idempotência.
- E: robustez espelhada (fetch morto preserva vaga byte a byte,
  exceção engolida, budget 0 = OFF byte-identical, budget parcial =
  melhores primeiro, eligible ilegível pula, guard não-http).

Offline: fetch 100% injetável (zero rede); tempdir para data/; nada
de data/ de produção. Scores exatos são estáveis no tempo:
posted_at=None ⇒ sem decay F38. Standalone: imprime [OK]/[FAIL];
rc=0 só se tudo passar.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import refresh_daily as rd  # noqa: E402
import url_liveness as ul  # noqa: E402

RESULTS: list[tuple[bool, str]] = []


def check(label: str, cond: bool) -> None:
    RESULTS.append((bool(cond), label))
    print(("  [OK] " if cond else "  [FAIL] ") + label)


# --- fixtures REAIS (bloco JSON-LD verbatim das páginas capturadas 22/10)
FIXTURES = Path(__file__).resolve().parent / "fixtures_f101"
FIX = {
    "13383618": FIXTURES / "mercedes_einkauf_motorsteuerung.html",
    "13383432": FIXTURES / "mercedes_einkaufsprozesse.html",
    "13423232": FIXTURES / "daimler_buses_einkauf.html",
}
ID_MOTOR = "Mercedes-Benz AG|absolventa:13383618"
ID_PROZESSE = "Mercedes-Benz AG|absolventa:13383432"
ID_DAIMLER = "Daimler Buses GmbH|absolventa:13423232"
# Comprimentos extraídos MEDEIDOS no Passo 0 (calibração com o parser vivo).
DESC_LEN = {ID_MOTOR: 3968, ID_PROZESSE: 4418, ID_DAIMLER: 4544}


def fixture_fetch(url: str):
    """Fetch injetável: serve a fixture real da vaga pela chave da URL."""
    for key, path in FIX.items():
        if key in str(url or ""):
            return path.read_text(encoding="utf-8")
    return None


# Cenário VERBATIM: as 3 vagas reais do dataset 21/10 (description vazia,
# score 9.5, breakdown language 0.0) — compactado byte a byte do archive.
JOBS_JSON = '''
[{"id":"Mercedes-Benz AG|absolventa:13383618","source":"absolventa","title":"Praktikant*in Einkauf Motorsteuerung (Pflicht-Praktikum)","company":"Mercedes-Benz AG","location":null,"country":"de","remote":null,"url":"https://www.absolventa.de/stellenangebote/13383618-b-praktikant-in-einkauf-motorsteuerung-pflicht-praktikum","internship":true,"posted_at":null,"collected_at":"2026-10-20T09:39:55.183669Z","application_deadline":null,"external_id":"13383618","employment_type":null,"country_iso":"de","raw":null,"description_source":null,"score":9.5,"score_breakdown":{"area":6.0,"skills":0.0,"language":0.0,"type":1.0,"location":1.0,"penalties":0.0,"registry":0.0,"fn":0.0,"core":1.5},"visa_friendly":false,"description":""},{"id":"Mercedes-Benz AG|absolventa:13383432","source":"absolventa","title":"Praktikant*in Einkaufsprozesse/-systeme, Prozess Governance & Kommunikation","company":"Mercedes-Benz AG","location":null,"country":"de","remote":null,"url":"https://www.absolventa.de/stellenangebote/13383432-b-praktikant-in-einkaufsprozesse-systeme-prozess-governance-kommunikation","internship":true,"posted_at":null,"collected_at":"2026-10-20T09:39:55.185920Z","application_deadline":null,"external_id":"13383432","employment_type":null,"country_iso":"de","raw":null,"description_source":null,"score":9.5,"score_breakdown":{"area":6.0,"skills":0.0,"language":0.0,"type":1.0,"location":1.0,"penalties":0.0,"registry":0.0,"fn":0.0,"core":1.5},"visa_friendly":false,"description":""},{"id":"Daimler Buses GmbH|absolventa:13423232","source":"absolventa","title":"Praktikum (w/m/d) im Bereich Einkauf Daimler Buses am Standort Mannheim","company":"Daimler Buses GmbH","location":null,"country":"de","remote":null,"url":"https://www.absolventa.de/stellenangebote/13423232-b-praktikum-w-m-d-im-bereich-einkauf-daimler-buses-am-standort-mannheim","internship":true,"posted_at":null,"collected_at":"2026-10-20T09:39:53.523276Z","application_deadline":null,"external_id":"13423232","employment_type":null,"country_iso":"de","raw":null,"description_source":null,"score":9.5,"score_breakdown":{"area":6.0,"skills":0.0,"language":0.0,"type":1.0,"location":1.0,"penalties":0.0,"registry":0.0,"fn":0.0,"core":1.5},"visa_friendly":false,"description":""}]
'''


def real_jobs() -> list:
    return json.loads(JOBS_JSON)


def stage(tmp: Path, jobs: list, fetch, budget: int) -> tuple[dict, list]:
    """Roda o estágio num tempdir; devolve (record, ranking final)."""
    (tmp / "eligible_jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    rec = rd._run_blind_hydration(
        tmp, tmp / "metrics.jsonl", run_id="t", config_path=None,
        fetch_page=fetch, budget_override=budget)
    ranking = json.loads(
        (tmp / "eligible_jobs.json").read_text(encoding="utf-8"))
    return rec, ranking


def page_jsonld(desc: str) -> str:
    """Página com JSON-LD JobPosting VÁLIDO (sintética, p/ gates F22)."""
    block = json.dumps(
        {"@context": "http://schema.org", "@type": "JobPosting",
         "title": "P", "description": desc})
    return ('<html><head><script type="application/ld+json">'
            + block + '</script></head><body>ok</body></html>')


PAGE_NO_JSONLD = "<html><head><title>x</title></head><body>plain</body></html>"


def _jsonld_jobposting_block(path: Path) -> str:
    """Bloco <script ld+json> JobPosting VERBATIM da fixture real."""
    html = path.read_text(encoding="utf-8")
    blocks = re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.S)
    jp = [b for b in blocks if '"JobPosting"' in b]
    if len(jp) != 1:
        raise AssertionError(f"fixture {path.name}: {len(jp)} blocos JobPosting")
    return jp[0]


def _loads_mode(block: str, mode: str) -> bool:
    """Tenta o parse nos 3 níveis do cascade leniente da F91."""
    try:
        if mode == "strict":
            json.loads(block)
        elif mode == "tier2":
            json.loads(block, strict=False)
        else:  # tier3: reparo de escape + strict=False
            json.loads(
                re.sub(r'\\(?![\\"/bfnrtu])', r'\\\\', block),
                strict=False)
        return True
    except Exception:
        return False


def main() -> int:
    print("== F101 A: fixtures REAIS — parse leniente nos 3 níveis ==")
    for key, jid, marker in (("13383618", ID_MOTOR, "A1"),
                             ("13383432", ID_PROZESSE, "A2"),
                             ("13423232", ID_DAIMLER, "A3")):
        desc = ul.parse_job_description(FIX[key].read_text(encoding="utf-8"))
        label = (f"{marker} página real {key}: extrai desc "
                 f"{DESC_LEN[jid]} chars (medido no Passo 0)")
        check(label, desc is not None and len(desc) == DESC_LEN[jid]
              and "Einkauf" in desc and "Deutsch" in desc)
    blocks = {k: _jsonld_jobposting_block(p) for k, p in FIX.items()}
    check("A4 malformação REAL: estrito falha nas 3 (JSON-LD do board)",
          all(not _loads_mode(b, "strict") for b in blocks.values()))
    check("A5 Mercedes: escape inválido \\x — tier 2 NÃO cura, tier 3 cura",
          not _loads_mode(blocks["13383618"], "tier2")
          and not _loads_mode(blocks["13383432"], "tier2")
          and _loads_mode(blocks["13383618"], "tier3")
          and _loads_mode(blocks["13383432"], "tier3"))
    check("A6 Daimler Buses: controle cru — tier 2 (strict=False) cura",
          _loads_mode(blocks["13423232"], "tier2"))
    check("A7 gates F22 intactos: desc <120 chars => None",
          ul.parse_job_description(page_jsonld("kurz")) is None)
    check("A8 gates F22 intactos: sem JSON-LD => None",
          ul.parse_job_description(PAGE_NO_JSONLD) is None)

    print("\n== F101 B: contrato das fontes (premissa da spec, congelada) ==")
    check("B1 absolventa ESTÁ no estágio F91 (typo 'absolutenta' no "
          "relatório F91 enganou a spec; F101 congela a cobertura real)",
          "absolventa" in rd.BLIND_HYDRATION_SOURCES)
    check("B2 praktikum_info no estágio (mesma DB ABSOLVENTA)",
          "praktikum_info" in rd.BLIND_HYDRATION_SOURCES)
    check("B3 bundesagentur FORA (decisão F91: 74/74 refnrs mortos — "
          "NÃO reabrir)", not any("bundesagentur" in s
                                 for s in rd.BLIND_HYDRATION_SOURCES))
    check("B4 provenance hydrated_blind distinta das 3 existentes",
          rd.HYDRATION_SOURCE_BLIND == "hydrated_blind"
          and rd.HYDRATION_SOURCE_BLIND not in (
              "hydration", "hydrated_topn", "hydrated_extended"))
    check("B5 limiar cego 50 (distinto da janela F65 = 500)",
          rd.BLIND_DESCRIPTION_LIMIT == 50)
    check("B6 prioridade medida F91: absolventa primeiro (30 > 1)",
          tuple(rd.BLIND_HYDRATION_SOURCES)[0] == "absolventa")

    print("\n== F101 C: as 3 vagas da task SÃO candidatas do estágio ==")
    jobs = real_jobs()
    by = rd._blind_hydration_candidates(jobs)
    check("C1 3 candidatas sob absolventa (nenhuma em outra fonte)",
          len(by.get("absolventa", [])) == 3
          and {j["id"] for j in by["absolventa"]}
          == {ID_MOTOR, ID_PROZESSE, ID_DAIMLER}
          and by.get("praktikum_info") == [])
    check("C2 ordem do ranking preservada dentro da fonte",
          [j["id"] for j in by["absolventa"]]
          == [ID_MOTOR, ID_PROZESSE, ID_DAIMLER])
    hydrated_desc = "Einkauf und Beschaffung " * 6  # >= 50: sai do corte
    jobs_vis = [{**j, "description": hydrated_desc} for j in real_jobs()]
    by_vis = rd._blind_hydration_candidates(jobs_vis)
    check("C3 hidratadas (desc >=50) NÃO são re-candidatas (idempotência "
          "do corte por comprimento)",
          by_vis.get("absolventa") == [])
    job_ba = dict(real_jobs()[0])
    job_ba["id"] = "BMW|sf_dataset:bundesagentur:1"
    job_ba["source"] = "sf_dataset:bundesagentur"
    by_ba = rd._blind_hydration_candidates([job_ba])
    check("C4 cega BA nunca é candidata (fora da lista, decisão F91)",
          "sf_dataset:bundesagentur" not in by_ba
          and not any(by_ba.values()))

    print("\n== F101 D: estágio end-to-end no cenário REAL (fixtures reais) ==")
    jobs = real_jobs()
    # F87 na vida real: cegas chegam ao estágio anotadas desc_vazia —
    # a cura pela hidratação é a recomputação (_annotate_assessability).
    for j in jobs:
        j["not_assessable"] = "desc_vazia"
    orig_rescore = rd.rescore_hydrated_jobs
    spy = {"n": 0, "ids": None}

    def rescore_spy(r, ids, **kw):
        spy["n"] += 1
        spy["ids"] = set(ids)
        return orig_rescore(r, ids, **kw)

    rd.rescore_hydrated_jobs = rescore_spy
    try:
        tmp = Path(tempfile.mkdtemp(prefix="f101_real_"))
        rec, out = stage(tmp, jobs, fixture_fetch, 10)
    finally:
        rd.rescore_hydrated_jobs = orig_rescore
    out_by_id = {j["id"]: j for j in out}
    a_stat = rec["by_source"]["absolventa"]
    check("D1 3/3 hidratadas via páginas reais (fetched 3, failed 0)",
          a_stat["candidates"] == 3 and a_stat["fetched"] == 3
          and a_stat["hydrated"] == 3 and a_stat["failed"] == 0
          and rec["hydrated"] == 3 and rec["failed"] == 0)
    check("D2 provenance hydrated_blind + timestamp",
          all(out_by_id[i].get("description_source") == "hydrated_blind"
              and str(out_by_id[i].get("description_hydrated_at")
                      or "").startswith("20")
              for i in (ID_MOTOR, ID_PROZESSE, ID_DAIMLER)))
    check("D3 desc preenchida com o texto REAL medido "
          "(3968/4418/4544 chars)",
          all(len(out_by_id[i].get("description") or "")
              == DESC_LEN[i] for i in (ID_MOTOR, ID_PROZESSE, ID_DAIMLER)))
    check("D4 re-score F56 chamado 1x com exatamente as 3 hidratadas",
          spy["n"] == 1 and spy["ids"]
          == {ID_MOTOR, ID_PROZESSE, ID_DAIMLER})
    check("D5 score 9.5 → 9.0 (language 0.0 → -0.5: o texto revela "
          "alemão; estável: posted_at=None ⇒ sem decay F38)",
          all(out_by_id[i]["score"] == 9.0 for i in
              (ID_MOTOR, ID_PROZESSE, ID_DAIMLER))
          and all(out_by_id[i]["score_breakdown"]["language"] == -0.5
                  for i in (ID_MOTOR, ID_PROZESSE, ID_DAIMLER)))
    check("D6 re-assess honesto: german_required 3/3 (descem do topo; "
          "F37.3 remove do eligible no MESMO run)",
          all(out_by_id[i].get(rd.HYDRATION_INAPPLICABLE_FLAG)
              == "german_required" for i in
              (ID_MOTOR, ID_PROZESSE, ID_DAIMLER))
          and rec["newly_inapplicable"] == 3
          and rec["by_reason"] == {"german_required": 3})
    check("D7 persistiu JSON (3 vagas) + CSV (score é coluna do contrato)",
          len(out) == 3
          and (tmp / "eligible_jobs.csv").exists()
          and "score" in (tmp / "eligible_jobs.csv").read_text(
              encoding="utf-8"))
    line = json.loads((tmp / "metrics.jsonl").read_text(
        encoding="utf-8").splitlines()[0])
    check("D8 métrica blind_hydration com by_source + hydrated_ids",
          line["type"] == "blind_hydration"
          and line["by_source"]["absolventa"]["hydrated"] == 3
          and set(line["hydrated_ids"])
          == {ID_MOTOR, ID_PROZESSE, ID_DAIMLER})
    rec2, _ = stage(Path(tempfile.mkdtemp(prefix="f101_idem_")),
                    out, fixture_fetch, 10)
    check("D9 idempotência: ranking hidratado gera 0 candidatas",
          rec2["candidates"] == 0 and rec2["fetched"] == 0
          and rec2["hydrated"] == 0)
    ann = rd._annotate_assessability(out)
    check("D10 flag F87 desc_vazia curado pela recomputação pós-hidratação",
          ann["cleared"] == 3
          and all(not out_by_id[i].get("not_assessable") for i in
                  (ID_MOTOR, ID_PROZESSE, ID_DAIMLER)))

    print("\n== F101 E: robustez espelhada da test_f91 (cenário real) ==")
    def fetch_dead(url: str):
        return None  # HTTP 410/404/timeout — tudo vira None
    tmp = Path(tempfile.mkdtemp(prefix="f101_dead_"))
    jobs = real_jobs()
    payload = json.dumps(jobs)
    rec, out = stage(tmp, jobs, fetch_dead, 10)
    check("E1 fetch morto: 3 failed, vagas intactas byte a byte, run seguiu",
          rec["failed"] == 3 and rec["hydrated"] == 0
          and (tmp / "eligible_jobs.json").read_text(encoding="utf-8")
          == payload)
    check("E2 vagas seguem cegas SEM marcador de inaplicabilidade "
          "(nada foi revelado)",
          all(not j.get(rd.HYDRATION_INAPPLICABLE_FLAG) for j in out)
          and all(j.get("description") == "" for j in out))

    def fetch_boom(url: str):
        raise RuntimeError("wall")
    tmp = Path(tempfile.mkdtemp(prefix="f101_boom_"))
    rec, out = stage(tmp, real_jobs(), fetch_boom, 10)
    check("E3 exceção do fetcher engolida por vaga (nunca derruba o run)",
          rec["failed"] == 3 and rec["hydrated"] == 0
          and all(j.get("description") == "" for j in out))

    calls: list[str] = []

    def fetch_count(url: str):
        calls.append(url)
        return None
    tmp = Path(tempfile.mkdtemp(prefix="f101_off_"))
    payload = json.dumps(real_jobs())
    rec, out = stage(tmp, real_jobs(), fetch_count, 0)
    check("E4 budget 0 => OFF (regra 9): zero fetch, JSON byte-identical",
          rec == {"budget": 0, "status": "off"} and calls == []
          and (tmp / "eligible_jobs.json").read_text(encoding="utf-8")
          == payload)

    tmp = Path(tempfile.mkdtemp(prefix="f101_partial_"))
    rec, out = stage(tmp, real_jobs(), fixture_fetch, 2)
    out_ids = {j["id"] for j in out if j.get("description_source")}
    check("E5 budget parcial (2 de 3): para no teto, MELHORES primeiro "
          "(ordem do ranking), 1 skipped",
          rec["by_source"]["absolventa"]["fetched"] == 2
          and rec["by_source"]["absolventa"]["hydrated"] == 2
          and rec["by_source"]["absolventa"]["skipped"] == 1
          and out_ids == {ID_MOTOR, ID_PROZESSE})

    tmp = Path(tempfile.mkdtemp(prefix="f101_garbage_"))
    (tmp / "eligible_jobs.json").write_text("{não json", encoding="utf-8")
    rec = rd._run_blind_hydration(
        tmp, tmp / "metrics.jsonl", run_id="t", config_path=None,
        fetch_page=fixture_fetch, budget_override=10)
    check("E6 eligible ilegível => estágio pula (status, sem crash)",
          rec.get("status") == "unreadable_eligible")
    check("E7 guard de URL não-http no fetch default (offline)",
          rd._default_blind_fetch_page("ftp://example.invalid/x") is None
          and rd._default_blind_fetch_page("not-a-url") is None)

    print()
    fails = [label for ok, label in RESULTS if not ok]
    print(f"F101: {len(RESULTS)} checks, {len(fails)} falhas")
    if fails:
        for f in fails:
            print(f"  FAIL: {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



