#!/usr/bin/env python3
"""Testes F56 — score pós-hidratação: recomputar quando F20/F25 enriquece a
descrição (achado de proveniência da F55 §4), 100% OFFLINE.

Causa raiz (diagnóstico com caminhos/linhas, medido no snapshot 15/10):

- ``scripts/refresh_daily.py`` estágio F20 (liveness do top exibido) hidrata
  a ``description`` DEPOIS do ``rank_jobs`` da coleta (cli.py:506 — o score
  é computado com a descrição PRÉ-hidratação) e grava o JSON sem recompute;
  o estágio F25 re-avalia aplicabilidade do backlog hidratado sem tocar em
  score. Resultado: ``score``/``score_breakdown`` congelados no estado
  pré-hidratação. Medido: ``Würth Industrie Service|absolventa:13251590`` e
  ``MOLEQLAR GmbH|absolventa:13258677`` com language 0.0 gravado vs +1.5
  recomputado ("englisch" só existe na descrição DEPOIS do score).

- FIXTURE VERBATIM: ``fixtures/f56_hydrated_frozen_fixture.json`` = top-25
  do arquivo ``data/archive/20261015T090002Z/eligible_jobs.json`` (run 15/10,
  907 registros) sem o campo ``raw`` (não entra no score — verificado:
  score byte-idêntico com e sem ``raw``). Os 2 registros do achado estão
  nas posições 21/22 do arquivo com score 12.0 e language 0.0 congelados.

- FIX MÍNIMO ESCOLHIDO (a): recomputar o score APENAS das hidratadas
  pós-hidratação, no mesmo run, e re-ordenar com o MESMO desempate do
  ``rank_jobs`` (``internship_finder.ranking.rescore_hydrated_jobs``,
  chamada em refresh_daily.py ANTES de persistir JSON + CSV). Alternativa
  (b) re-ordenar no publish com score on-the-fly REJEITADA: espalharia a
  recomputação por N consumidores (site, digest) e divergiria a ordem
  publicada do JSON gravado (documentação no docstring da função).

- NÚMEROS MEDIDOS E CONGELADOS (fórmula F55 atual, NOW_REF =
  2026-10-15T09:38:19Z — a referência da F55 §4): Würth 12.0 -> 15.0
  (language +1.5) aterrando #2 no slice; MOLEQLAR 12.0 -> 15.0 (language
  +1.5) aterrando #3; 21 deslocados no slice top-25. No A/B de produção do
  run 17/10 (fórmula da época e0d75c2 — 0/732 não-hidratados divergem do
  fingerprint da fórmula): Würth #10->#4, MOLEQLAR #11->#5, Lidl #63->#23,
  57 deslocados no top-100, EU/materials 0 diffs (recomputam on-the-fly).
  OBS.: os scores gravados de NÃO-hidratados NÃO são comparados ao
  ``score_job`` atual — a fórmula evoluiu (F55); o contrato do helper é não
  TOCAR neles, não reproduzi-los.
- F60 (19/10): o detector de alemão aprendeu o ``gut`` BARE, o verbo 2ª
  pessoa ``sprichst`` e ``deutschsprachig`` por advérbio/janela reversa —
  a FRASE VERBATIM da MOLEQLAR ("Du sprichst sehr gut Deutsch, da unser
  Arbeitsalltag hauptsächlich deutschsprachig ist.") passa de menção nua
  para REQUIRED. Exatamente a falha que motivou a F60: re-medidos com o
  detector F60 (mesma fixture, mesmo NOW_REF): Würth INALTERADO (15.0,
  language +1.5, #2 — sem evidência de alemão no texto); MOLEQLAR 13.0
  (language -0.5 = +1.5 inglês -2.0 alemão required) aterrando #12 no
  slice (sai do pódio #3); deslocados top-25 SEGUEM 21 (a cascata de
  vizinhos troca de forma, mesmo tamanho). Expecteds congelados com a
  fórmula F60 — o freeze move com a fórmula (lição F56 aplicada à F60).

Uso:  .venv/bin/python scripts/test_f56.py
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.ranking import rank_jobs, rescore_hydrated_jobs, score_job  # noqa: E402

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok: {msg}")
    else:
        print(f"  [FAIL] {msg}")
        FAILURES.append(msg)


FIXTURE = ROOT / "fixtures" / "f56_hydrated_frozen_fixture.json"
NOW_REF = datetime(2026, 10, 15, 9, 38, 19, tzinfo=timezone.utc)
WURTH = "Würth Industrie Service GmbH & Co. KG|absolventa:13251590"
MOLEQLAR = "MOLEQLAR GmbH|absolventa:13258677"
F56_PAIR = {WURTH, MOLEQLAR}
# Ordem esperada do topo do slice após o re-score.
# F60: re-medida com o detector F60 — a MOLEQLAR (agora 13.0, alemão
# required pela frase verbatim da fase) SAI do topo-8; KPMG 927796101
# (a vaga da classe B, texto intro-only) entra em #8. Congelada.
EXPECTED_TOP8 = [
    "BoschGroup|smartrecruiters:BoschGroup:744000141914929",
    WURTH,
    "BoschGroup|smartrecruiters:BoschGroup:744000136455353",
    "Bayer|successfactors:jobs:1429117133",
    "BoschGroup|sf_dataset:smartrecruiters:744000147439805",
    "Bayer AG Pharmaceuticals|sf_dataset:bundesagentur:12708-1623235-1-S",
    "teampicnic|greenhouse:teampicnic:6337034",
    "KPMG International Cooperative|sf_dataset:successfactors:927796101",
]

print("=== F56 — score pós-hidratação (recompute quando F20/F25 enriquece a descrição) ===")

# ---------------------------------------------------------------- bloco A
print("[A] fixture VERBATIM — estado congelado do achado F55 §4")
ranking = json.loads(FIXTURE.read_text(encoding="utf-8"))
check(len(ranking) == 25, f"fixture = top-25 do arquivo 15/10 (len={len(ranking)})")
wurth = next(j for j in ranking if j["id"] == WURTH)
moleq = next(j for j in ranking if j["id"] == MOLEQLAR)
check(ranking.index(wurth) == 20 and ranking.index(moleq) == 21,
      "Würth #21 e MOLEQLAR #22 na ordem gravada do arquivo 15/10")
for nome, rec in (("Würth", wurth), ("MOLEQLAR", moleq)):
    check(rec.get("description_source") == "hydrated_topn",
          f"{nome}: description_source == hydrated_topn (hidratada pós-score)")
    check(rec.get("score") == 12.0, f"{nome}: score gravado congelado 12.0")
    check((rec.get("score_breakdown") or {}).get("language") == 0.0,
          f"{nome}: language gravado congelado 0.0")
    check("englisch" in (rec.get("description") or "").lower(),
          f"{nome}: 'englisch' JÁ existe na descrição gravada (post-hidratação)")
    check(len(rec.get("description") or "") >= 500,
          f"{nome}: descrição hidratada é longa (>= limite F20 de 500 chars)")
check({j["id"] for j in ranking if j.get("description_source") == "hydrated_topn"}
      == {WURTH, MOLEQLAR, "Hilti Group|absolventa:13379865"},
      "hydrated_topn no slice = o par do achado + Hilti (MESMO run 15/10, "
      "também congelada — fora do escopo do par medido)")

# ---------------------------------------------------------------- bloco B
print("[B] mecanismo — re-score fresco da dupla (fórmula atual, NOW_REF 15/10)")
# F60: Würth INALTERADO (+1.5/15.0 — sem evidência de alemão no texto);
# MOLEQLAR vira required pela frase verbatim da F60 ("Du sprichst sehr
# gut Deutsch...") — language -0.5 (inglês +1.5, alemão required -2.0),
# total 13.0. Re-medido com o detector F60; congelado.
for nome, rec, exp_lang, exp_total in (
        ("Würth", wurth, 1.5, 15.0),
        ("MOLEQLAR", moleq, -0.5, 13.0)):
    fresh = score_job(rec, now=NOW_REF)
    check(fresh.breakdown.get("language") == exp_lang,
          f"{nome}: language recomputado 0.0 -> {exp_lang:+} (F60)")
    check(fresh.total == exp_total,
          f"{nome}: score recomputado 12.0 -> {exp_total} (medido F60)")

# ---------------------------------------------------------------- bloco C
print("[C] rescore_hydrated_jobs — end-to-end no ranking do fixture")
branch = copy.deepcopy(ranking)
n = rescore_hydrated_jobs(branch, F56_PAIR, now=NOW_REF)
check(n == 2, f"re-score retornou 2 (hidratadas efetivas do par) — {n}")
check(isinstance(n, int) and branch[0]["id"] == EXPECTED_TOP8[0],
      "helper muta a lista IN PLACE (retorno = contagem, sem trocar a lista)")
br_w = next(j for j in branch if j["id"] == WURTH)
br_m = next(j for j in branch if j["id"] == MOLEQLAR)
# F60: Würth #2 (igual); MOLEQLAR desce do pódio #3 para #12 — o
# alemão required (frase verbatim da F60) tira exatamente os -2.0 que a
# colocavam empatada com o topo. Medido com o detector F60; congelado.
check(branch.index(br_w) == 1 and branch.index(br_m) == 11,
      "Würth aterra #2 e MOLEQLAR #12 (medido F60; antes #21/#22)")
check(br_w["score"] == 15.0 and br_w["score_breakdown"]["language"] == 1.5,
      "Würth: score 15.0 + language 1.5 gravados no dict")
check(br_m["score"] == 13.0 and br_m["score_breakdown"]["language"] == -0.5,
      "MOLEQLAR: score 13.0 + language -0.5 gravados no dict (F60)")
check([j["id"] for j in branch[:8]] == EXPECTED_TOP8,
      "ordem do topo pós-fix == ordem medida (congelada)")
displaced = sum(1 for i in range(len(branch)) if branch[i]["id"] != ranking[i]["id"])
check(displaced == 21, f"deslocados no slice top-25 == 21 (cascata de vizinhos) — {displaced}")
by_id = {j["id"]: j for j in ranking}
untouched = all(
    j["score"] == by_id[j["id"]]["score"]
    and j["score_breakdown"] == by_id[j["id"]]["score_breakdown"]
    for j in branch if j["id"] not in F56_PAIR
)
check(untouched, "contra-caso: NÃO-hidratados com score/score_breakdown byte-identical (por id)")

# ---------------------------------------------------------------- bloco D
print("[D] no-op byte-identical (contra-caso do card)")
noop = copy.deepcopy(ranking)
before = json.dumps(noop, ensure_ascii=False)
rescore_hydrated_jobs(noop, set(), now=NOW_REF)
check(json.dumps(noop, ensure_ascii=False) == before,
      "ids vazios -> byte-identical (nenhum dict mutado, nenhuma reordenação)")
ghost = rescore_hydrated_jobs(noop, {"id-inexistente:1", "id-inexistente:2"}, now=NOW_REF)
check(ghost == 0 and json.dumps(noop, ensure_ascii=False) == before,
      "ids ausentes do ranking -> no-op (retorno 0, byte-identical)")

# ------------------------------------------------- bloco E
print("[E] determinismo/idempotência — runs consecutivos não oscilam")
branch2 = copy.deepcopy(ranking)
rescore_hydrated_jobs(branch2, F56_PAIR, now=NOW_REF)
check(json.dumps(branch, ensure_ascii=False) == json.dumps(branch2, ensure_ascii=False),
      "mesmos dados + mesmo now -> saída byte-identical (2 cópias independentes)")
rescore_hydrated_jobs(branch2, F56_PAIR, now=NOW_REF)
check(json.dumps(branch, ensure_ascii=False) == json.dumps(branch2, ensure_ascii=False),
      "re-score repetido (2º recompute) -> idempotente, mesmo valor")
check(all(len(next(j for j in branch2 if j["id"] == i)["description"] or "") >= 500
          for i in F56_PAIR),
      "run seguinte: descrição hidratada é longa -> deixa de ser candidata F20 "
      "(sem nova hidratação, sem oscilação de score)")

# ---------------------------------------------------------------- bloco F
print("[F] integração do estágio F20 (refresh_daily) + suíte no ci.yml")
src = (ROOT / "scripts" / "refresh_daily.py").read_text(encoding="utf-8")
check("from internship_finder.ranking import rescore_hydrated_jobs" in src,
      "refresh_daily importa rescore_hydrated_jobs (wiring)")
check("rescore_hydrated_jobs(" in src and "F56" in src,
      "estágio F20 chama o re-score pós-hidratação (F56)")
pos_rescore = src.find("rescore_hydrated_jobs(")
pos_persist = src.find("_write_json_atomic(", pos_rescore)
check(0 < pos_rescore < pos_persist,
      "re-score roda ANTES de persistir o JSON (publish/digest leem o arquivo já correto)")
check(src.find("with_suffix(\".csv\")", pos_rescore) > pos_rescore
      and src.find("_dump_csv", pos_rescore) > pos_rescore,
      "persistência do CSV junto (score é coluna de CSV_COLUMNS)")
check("now=datetime.now(UTC))" in src[pos_rescore:pos_rescore + 200],
      "re-score usa now aware como a coleta (F38)")

import ci_discover_tests  # F78: suíte do CI = descoberta (array literal morreu)
names = ci_discover_tests.discover_tests()
check("test_f56" in names, "test_f56 presente na suíte descoberta do CI (F78)")
check(len(names) >= 94, f"suíte descoberta tem >= 94 suítes (93 ao vivo de 41c800d "
      f"+ test_f56; descobertas seguintes só crescem — assert RELATIVO, "
      f"lição do rebase F46: contagem exata quebra a cada união) — {len(names)}")
check(all(n in names for n in ("test_f55", "test_f49", "test_f20", "test_hydration")),
      "nenhuma suíte pré-existente removida (união 93->94)")

# ---------------------------------------------------------------- bloco G
print("[G] sanidade — desempate idêntico ao rank_jobs e pureza")
all_ids = {j["id"] for j in ranking}
re_all = copy.deepcopy(ranking)
rescore_hydrated_jobs(re_all, all_ids, now=None)
official_rank = rank_jobs(copy.deepcopy(ranking))
check([j["id"] for j in re_all] == [j["id"] for j in official_rank],
      "helper com TODOS os ids == rank_jobs (mesmo score_job + MESMO desempate)")

print()
if FAILURES:
    print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
    sys.exit(1)
print("TUDO OK")
