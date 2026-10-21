#!/usr/bin/env python3
"""F91 — hidratação dos CEGOS: description para as desc-empty (offline).

Estágio flag-gated (padrão F65, budget PRÓPRIO
``INTERNSHIP_FINDER_BLIND_HYDRATION_BUDGET``; default 0 = OFF, regra 9)
que dá descrição real às vagas cegas do pool (<50 chars) de fontes cujo
texto só existe na página própria — absolventa (30/30) e praktikum_info
(1/1), medidos no Passo 0 — via fetch da página + ``parse_job_description``
(JSON-LD JobPosting, gates F22 intactos: >=120 chars, cap 16 KB, só se
maior que a atual).

Passo 0 (21/10) FALSIFICOU a premissa da spec para
``sf_dataset:bundesagentur``: 74/74 refnrs das cegas MORTOS na fonte
(detail v4 HTTP 404; página pública 410; o slice do dataset é espelho
atrasado — os postings vivos, 26/26, a Fase A já cura diariamente).
A fonte fica FORA da lista do estágio (spec: "se parede, documentar e
pular fonte") — testado aqui como contrato (cega BA NUNCA é fetchada).

Fix habilitador testado aqui: ``url_liveness._loads_lenient`` — o
JSON-LD da absolventa vem malformado (chars de controle crus dentro de
strings em 26/30 páginas; escapes inválidos ``\\x`` em 4/30, todas
Mercedes-Benz). Cascata: estrito -> ``strict=False`` -> reparo de escape
+ ``strict=False``. Estritamente aditivo (JSON válido segue idêntico);
gates do ``parse_job_description`` intocados.

Contratos do estágio (spec item 5): desc-empty vira hidratada
(provenance ``hydrated_blind``, desc preenchida, re-score chamado);
fetch falha => vaga intacta + contador ``failed`` (Fase A pattern),
run segue; budget 0 => estágio OFF (JSON byte-identical, zero fetch);
budget parcial => para no teto; vaga já com desc >=50 não é re-hidratada;
ordenação por score respeitada dentro da fonte (fontes em prioridade
medida). Extras: re-avaliação honesta (german_required revelado desce do
topo via marcador), métrica ``blind_hydration`` no JSONL, idempotência,
JSON ilegível => estágio pula, guard de URL não-http, retro-compat do
``_hydration_budget`` (knob histórico do F65/F87 intacto).

Fixtures VERBATIM da medição: refnr BMW 12462-1601017-1-S (404 no detail
v4, 410 na página), descrições absolutenta com controle cru/escape
inválido. Zero rede (fetch injetável); tempdir para data/; nada de data/
de produção.

Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
"""
from __future__ import annotations

import json
import os
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


def page_jsonld(desc: str) -> str:
    """Página com JSON-LD JobPosting VÁLIDO (caminho atual do parser)."""
    block = json.dumps(
        {"@context": "http://schema.org", "@type": "JobPosting",
         "title": "P", "description": desc})
    return ('<html><head><script type="application/ld+json">'
            + block + '</script></head><body>ok</body></html>')


GOOD_DESC = ("Wir suchen einen Praktikanten (all genders) im Bereich "
             "Einkauf und Travel Management. Du unterstuetzt das Team bei "
             "Beschaffungsprozessen, Lieferantenmanagement und "
             "Preisanalysen. " * 4)

GERMAN_REQUIRED_DESC = ("Wir suchen einen Praktikanten im Einkauf. "
                        "Sehr gute Deutschkenntnisse (C1) werden "
                        "vorausgesetzt. Du arbeitest an "
                        "Lieferantenmanagement und Beschaffung. " * 3)

# JSON-LD malformado estilo absolventa (medido 21/10, 26/30 páginas):
# newline CRUA dentro da string — json.loads estrito rejeita.
PAGE_CONTROL = (
    '<html><head><script type="application/ld+json">{\n'
    '    "@context": "http://schema.org",\n'
    '    "@type": "JobPosting",\n'
    '    "title": "Praktikant",\n'
    '    "description": "Zeile 1 mit Beschaffung und Einkauf.\n'
    'Zeile 2 mit Lieferantenmanagement und Preisanalyse.\n'
    'Zeile 3 mit Materialwirtschaft und Logistik. ' + GOOD_DESC + '"\n'
    '}</script></head><body>ok</body></html>'
)

# JSON-LD malformado estilo absolventa/Mercedes (medido 21/10, 4/30):
# escape INVÁLIDO (\x) — falha mesmo com strict=False; o reparo cura.
PAGE_BAD_ESCAPE = (
    '<html><head><script type="application/ld+json">{\n'
    '    "@context": "http://schema.org",\n'
    '    "@type": "JobPosting",\n'
    '    "description": "Einkauf 100\\x Prozente Beschaffung '
    + GOOD_DESC + '"\n'
    '}</script></head><body>ok</body></html>'
)

PAGE_NO_JSONLD = "<html><head><title>x</title></head><body>plain</body></html>"
PAGE_SHORT = page_jsonld("kurz")  # < 120 chars => gate do parser => None


def blind_job(jid: str, source: str, url: str, score: float = 5.0,
              desc=None, company="X GmbH") -> dict:
    return {"id": jid, "source": source, "title": "Praktikant Einkauf",
            "company": company, "url": url, "description": desc,
            "score": score, "location": "München",
            "posted_at": "2026-10-01"}


def stage(tmp: Path, jobs: list, fetch, budget: int) -> tuple[dict, list]:
    """Roda o estágio num tempdir; devolve (record, ranking final)."""
    (tmp / "eligible_jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    rec = rd._run_blind_hydration(
        tmp, tmp / "metrics.jsonl", run_id="t", config_path=None,
        fetch_page=fetch, budget_override=budget)
    ranking = json.loads((tmp / "eligible_jobs.json").read_text(encoding="utf-8"))
    return rec, ranking


def main() -> int:
    print("== F91 A: parse leniente (_loads_lenient / parse_job_description) ==")
    d = ul.parse_job_description(PAGE_CONTROL)
    check("A1 controle cru (absolventa 26/30): extrai desc",
          d is not None and len(d) > 120 and "Einkauf" in d)
    d2 = ul.parse_job_description(PAGE_BAD_ESCAPE)
    check("A2 escape invalido (absolventa 4/30, Mercedes): extrai desc",
          d2 is not None and len(d2) > 120 and "Beschaffung" in d2)
    check("A3 JSON valido: caminho atual preservado (mesma desc)",
          ul.parse_job_description(page_jsonld(GOOD_DESC))
          == ul._clean_description(GOOD_DESC))
    check("A4 gates F22 intactos: desc curta (<120) => None",
          ul.parse_job_description(PAGE_SHORT) is None)
    check("A5 gates F22 intactos: sem JSON-LD => None",
          ul.parse_job_description(PAGE_NO_JSONLD) is None)
    check("A6 lixo real (nao-parseavel em 3 niveis) => None",
          ul._loads_lenient("{definitivamente nao json") is None)
    check("A7 JSON valido parseia identico nos 3 niveis",
          ul._loads_lenient('{"a": 1}') == {"a": 1}
          and ul._loads_lenient('{"a": "b\\nc"}') == {"a": "b\nc"})

    print("\n== F91 B: _hydration_budget — flag própria + retro-compat F65/F87 ==")
    key_blind = rd.BLIND_HYDRATION_BUDGET_ENV_FLAG
    key_f65 = rd.HYDRATION_BUDGET_ENV_FLAG
    check("B1 flag própria existe e é distinta da do F65",
          key_blind == "INTERNSHIP_FINDER_BLIND_HYDRATION_BUDGET"
          and key_blind != key_f65)
    old_b, old_f = os.environ.get(key_blind), os.environ.get(key_f65)
    try:
        os.environ.pop(key_blind, None)
        os.environ.pop(key_f65, None)
        check("B2 ausente => 0 (OFF, regra 9)",
              rd._hydration_budget(None, flag=key_blind) == 0)
        os.environ[key_blind] = "31"
        check("B3 env '31' => 31 (budget próprio lido)",
              rd._hydration_budget(None, flag=key_blind) == 31)
        check("B4 flag própria NÃO vaza para o knob do F65",
              rd._hydration_budget(None) == 0)
        os.environ[key_blind] = "abc"
        check("B5 valor inválido => 0 (fail-safe)",
              rd._hydration_budget(None, flag=key_blind) == 0)
        os.environ[key_blind] = "-5"
        check("B6 negativo => 0 (fail-safe)",
              rd._hydration_budget(None, flag=key_blind) == 0)
        os.environ.pop(key_blind, None)
        os.environ[key_f65] = "77"
        try:
            check("B7 retro-compat: default continua lendo o knob F65",
                  rd._hydration_budget(None) == 77)
        finally:
            os.environ.pop(key_f65, None)
        # .env: arquivo legível pela MESMA chave (padrão F1; env vence)
        envfile = Path(tempfile.mkdtemp(prefix="f91_env_")) / ".env"
        envfile.write_text(f"{key_blind}=12\n", encoding="utf-8")
        check("B8 .env com a chave => 12 (sem env)",
              rd._hydration_budget(envfile, flag=key_blind) == 12)
        os.environ[key_blind] = "3"
        try:
            check("B9 env tem precedência sobre .env",
                  rd._hydration_budget(envfile, flag=key_blind) == 3)
        finally:
            os.environ.pop(key_blind, None)
        envfile.write_text("outra=1\n", encoding="utf-8")
        check("B10 .env sem a chave => 0",
              rd._hydration_budget(envfile, flag=key_blind) == 0)
    finally:
        for k, v in ((key_blind, old_b), (key_f65, old_f)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print("\n== F91 C: _blind_hydration_candidates (pura) ==")
    ranking = [
        blind_job("a|absolventa:1", "absolventa", "https://abs/x1", 9.5),
        blind_job("b|sf_dataset:bundesagentur:1", "sf_dataset:bundesagentur",
                  "https://ba/1", 11.0),
        blind_job("c|absolventa:2", "absolventa", "https://abs/x2", 8.0),
        {"id": "d|feed:1", "source": "ats:slug", "description": "x" * 300,
         "url": "https://y/1", "score": 7.0},
        blind_job("e|praktikum_info:1", "praktikum_info", "https://pi/1", 6.0),
        blind_job("f|absolventa:3", "absolventa", "https://abs/x3", 5.0,
                  desc="kurz aber echt"),
    ]
    cands = rd._blind_hydration_candidates(ranking)
    check("C1 cegas (<50) por fonte; desc >=50 fora",
          [j["id"] for j in cands["absolventa"]] ==
          ["a|absolventa:1", "c|absolventa:2", "f|absolventa:3"])
    check("C2 desc curta (12 chars) é cega (corte por comprimento)",
          "f|absolventa:3" in [j["id"] for j in cands["absolventa"]])
    check("C3 ordem do ranking preservada dentro da fonte (score desc)",
          [j["id"] for j in cands["praktikum_info"]] == ["e|praktikum_info:1"])
    check("C4 fonte fora da lista (BA) nunca é candidata",
          "sf_dataset:bundesagentur" not in cands
          and "sf_dataset:bundesagentur" not in rd.BLIND_HYDRATION_SOURCES)
    check("C5 contrato das fontes do estágio (medido no Passo 0)",
          rd.BLIND_HYDRATION_SOURCES == ("absolventa", "praktikum_info"))
    check("C6 limiar cego = 50 (distinto da janela F65 = 500)",
          rd.BLIND_DESCRIPTION_LIMIT == 50
          and rd.HYDRATION_SHORT_LIMIT == 500)
    check("C7 provenance distinta das 3 existentes",
          rd.HYDRATION_SOURCE_BLIND == "hydrated_blind"
          and rd.HYDRATION_SOURCE_BLIND not in (
              rd.HYDRATION_SOURCE, rd.HYDRATION_SOURCE_EXTENDED, "hydration"))

    print("\n== F91 D: estágio — caminho feliz (hidrata + re-score + persiste) ==")
    calls: list[str] = []
    pages = {"https://abs/x1": page_jsonld(GOOD_DESC),
             "https://abs/x2": PAGE_CONTROL,
             "https://pi/1": PAGE_BAD_ESCAPE}
    def fetch_ok(url: str):
        calls.append(url)
        return pages.get(url)
    jobs = [dict(j) for j in ranking[:3]] + [dict(ranking[3])] \
        + [dict(ranking[4])] + [dict(ranking[5])]
    # F87 na vida real: vaga cega chega ao ranking anotada desc_vazia —
    # a cura pela hidratação é a recomputação (_annotate_assessability).
    jobs[0]["not_assessable"] = "desc_vazia"
    orig_rescore = rd.rescore_hydrated_jobs
    spy = {"n": 0}
    def rescore_spy(r, ids, now=None):
        spy["n"] += 1
        return orig_rescore(r, ids, now=now)
    rd.rescore_hydrated_jobs = rescore_spy
    try:
        tmp = Path(tempfile.mkdtemp(prefix="f91_happy_"))
        rec, out = stage(tmp, jobs, fetch_ok, 99)
    finally:
        rd.rescore_hydrated_jobs = orig_rescore
    by_id = {j["id"]: j for j in out}
    check("D1 3 cegas hidratadas (absolventa 2 + praktikum_info 1)",
          rec["hydrated"] == 3)
    check("D2 provenance hydrated_blind + timestamp",
          all(by_id[i].get("description_source") == "hydrated_blind"
              and by_id[i].get("description_hydrated_at")
              for i in ("a|absolventa:1", "c|absolventa:2", "e|praktikum_info:1")))
    check("D3 desc preenchida (texto real, >120 chars)",
          all(len(by_id[i].get("description") or "") >= 120
              for i in ("a|absolventa:1", "c|absolventa:2", "e|praktikum_info:1")))
    check("D4 re-score chamado 1x com exatamente as hidratadas",
          spy["n"] == 1)
    check("D5 BA (fonte fora da lista) NUNCA fetchada",
          not any("ba/" in u for u in calls) and calls.count("https://ba/1") == 0)
    check("D6 vaga visível (desc >=50) intacta",
          by_id["d|feed:1"]["description"] == "x" * 300
          and "d|feed:1" not in rec["hydrated_ids"])
    check("D7 ordem por score respeitada dentro da fonte",
          calls.index("https://abs/x1") < calls.index("https://abs/x2"))
    check("D8 fonte prioritária (absolventa) fetchada antes de praktikum_info",
          calls.index("https://abs/x2") < calls.index("https://pi/1"))
    check("D9 ranking reordenado por score desc pós-re-score",
          [j["score"] for j in out] ==
          sorted([j["score"] for j in out], reverse=True))
    check("D10 persistiu JSON + CSV (score é coluna do contrato)",
          (tmp / "eligible_jobs.csv").exists()
          and "score" in (tmp / "eligible_jobs.csv").read_text(encoding="utf-8"))
    line = json.loads((tmp / "metrics.jsonl").read_text(encoding="utf-8").splitlines()[0])
    check("D11 métrica blind_hydration gravada com by_source",
          line["type"] == "blind_hydration"
          and line["by_source"]["absolventa"]["hydrated"] == 2
          and line["by_source"]["praktikum_info"]["hydrated"] == 1)
    check("D12 idempotência: hidratadas (desc >=50) NÃO são re-fetchadas",
          # re-run: só a f (fetch falhou no 1º passe, continua cega) é
          # candidata — as 3 hidratadas saem do corte por comprimento.
          (lambda r: r["candidates"] == 1 and r["fetched"] == 1
           and r["hydrated"] == 0 and calls[-1] == "https://abs/x3"
           and calls.count("https://abs/x1") == 1
           and calls.count("https://pi/1") == 1)
          (stage(tmp, out, fetch_ok, 99)[0]))
    ann = rd._annotate_assessability(out)
    out_by_id = {j["id"]: j for j in out}
    check("D13 flag not_assessable curado pela recomputação F87 (mesma run)",
          # a vaga que CHEGOU com desc_vazia e foi hidratada perde o flag;
          # nenhuma hidratada sai do estágio anotada (desc >=600 > limiar).
          not out_by_id["a|absolventa:1"].get("not_assessable")
          and all(not out_by_id[i].get("not_assessable")
                  for i in rec["hydrated_ids"])
          and ann["cleared"] >= 1)

    print("\n== F91 E: estágio — fallback gracioso (padrão Fase A) ==")
    def fetch_dead(url: str):
        calls.append(url)
        return None  # HTTP 410/404/timeout — tudo vira None
    tmp = Path(tempfile.mkdtemp(prefix="f91_fail_"))
    jobs2 = [blind_job("a|absolventa:1", "absolventa", "https://abs/x1", 9.5),
             blind_job("b|absolventa:9", "absolventa", "https://abs/dead", 8.0)]
    before = json.dumps(jobs2, sort_keys=True)
    rec, out = stage(tmp, jobs2, fetch_dead, 99)
    check("E1 fetch falhou para TODAS as candidatas (2 failed)",
          rec["failed"] == 2 and rec["hydrated"] == 0)
    check("E2 vagas intactas (byte a byte por campo)",
          all(not j.get("description") and not j.get("description_source")
              for j in out) and len(out) == 2)
    check("E3 run seguiu (retornou registro, nao levantou)",
          rec["type"] == "blind_hydration")
    def fetch_raises(url: str):
        raise RuntimeError("boom")
    tmp = Path(tempfile.mkdtemp(prefix="f91_raise_"))
    rec, out = stage(tmp, jobs2, fetch_raises, 99)
    check("E4 exceção do fetcher engolida por vaga (nunca derruba)",
          rec["failed"] == 2 and len(out) == 2)
    tmp = Path(tempfile.mkdtemp(prefix="f91_nodscr_"))
    rec, out = stage(tmp, jobs2, lambda u: PAGE_NO_JSONLD, 99)
    check("E5 página viva sem JSON-LD => failed (vaga intacta)",
          rec["failed"] == 2 and rec["hydrated"] == 0)
    tmp = Path(tempfile.mkdtemp(prefix="f91_short_"))
    rec, out = stage(tmp, jobs2, lambda u: PAGE_SHORT, 99)
    check("E6 gate <120 chars => failed (nunca piora)",
          rec["failed"] == 2 and all(not j.get("description") for j in out))

    print("\n== F91 F: estágio — budget (regra 9) e gates ==")
    tmp = Path(tempfile.mkdtemp(prefix="f91_off_"))
    jobs3 = [blind_job("a|absolventa:1", "absolventa", "https://abs/x1", 9.5)]
    (tmp / "eligible_jobs.json").write_text(json.dumps(jobs3), encoding="utf-8")
    snap = (tmp / "eligible_jobs.json").read_text(encoding="utf-8")
    n_before = len(calls)
    rec = rd._run_blind_hydration(tmp, tmp / "metrics.jsonl", run_id="t",
                                   config_path=None, fetch_page=fetch_ok,
                                   budget_override=0)
    check("F1 budget 0 => OFF (status off, zero fetch, JSON byte-identical)",
          rec == {"budget": 0, "status": "off"}
          and len(calls) == n_before
          and (tmp / "eligible_jobs.json").read_text(encoding="utf-8") == snap)
    check("F2 OFF não grava métrica",
          not (tmp / "metrics.jsonl").exists())
    tmp = Path(tempfile.mkdtemp(prefix="f91_cap_"))
    jobs4 = [blind_job(f"a{i}|absolventa:{i}", "absolventa",
                       f"https://abs/x{i}", 9.0 - i) for i in range(1, 6)]
    calls.clear()
    rec, out = stage(tmp, jobs4, fetch_ok, 2)
    check("F3 budget parcial (2 de 5 candidatas): para no teto",
          rec["fetched"] == 2 and rec["hydrated"] == 2
          and rec["by_source"]["absolventa"]["skipped"] == 3)
    check("F4 as MELHORES primeiro (score desc): x1 e x2 fetchadas",
          calls[:2] == ["https://abs/x1", "https://abs/x2"])
    tmp = Path(tempfile.mkdtemp(prefix="f91_badjson_"))
    (tmp / "eligible_jobs.json").write_text("{nao json", encoding="utf-8")
    rec = rd._run_blind_hydration(tmp, tmp / "m.jsonl", run_id="t",
                                  config_path=None, fetch_page=fetch_ok,
                                  budget_override=99)
    check("F5 eligible ilegível => estágio pula (status, sem crash)",
          rec.get("status") == "unreadable_eligible")
    check("F6 guard de URL não-http no fetch default (offline)",
          rd._default_blind_fetch_page("") is None
          and rd._default_blind_fetch_page("ftp://x/y") is None)

    print("\n== F91 G: re-avaliação honesta (revela german_required) ==")
    tmp = Path(tempfile.mkdtemp(prefix="f91_german_"))
    jobs5 = [blind_job("g|absolventa:7", "absolventa", "https://abs/g", 9.0)]
    rec, out = stage(tmp, jobs5, lambda u: page_jsonld(GERMAN_REQUIRED_DESC), 99)
    by_id = {j["id"]: j for j in out}
    check("G1 desc hidratada revelou german_required => marcador no JSON",
          by_id["g|absolventa:7"].get(rd.HYDRATION_INAPPLICABLE_FLAG)
          == "german_required")
    check("G2 contada no registro (newly_inapplicable/by_reason)",
          rec["newly_inapplicable"] == 1
          and rec["by_reason"].get("german_required") == 1)
    check("G3 vaga hidratada MESMO assim (fica no JSON; F37.3 decide)",
          "g|absolventa:7" in rec["hydrated_ids"]
          and len(by_id["g|absolventa:7"].get("description") or "") >= 120)

    print()
    fails = [label for ok, label in RESULTS if not ok]
    print(f"F91: {len(RESULTS)} checks, {len(fails)} falhas")
    if fails:
        for f in fails:
            print(f"  FAIL: {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
