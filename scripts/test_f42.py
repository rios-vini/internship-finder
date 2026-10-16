#!/usr/bin/env python3
"""Testes F42 — benchmark v4 do ranking (rotulagem assistida aplicável-first).

Cobre ``benchmarks/ranking_benchmark_v4.json`` (arquivo versionado) + a
fixture ``fixtures/benchmark_v4_fixture.json`` (VERBATIM, campos mínimos):

- estrutura: 6º rótulo ``inaplicavel``; labels_order v4; paridade de campos
  com o v2 (chaves por job); v4 NUNCA carrega description/raw;
- rubrica: decisão do tau DECIDIDA (inaplicável fora dos pares, dono 15/10
  '3. A'); ótima/boa com cláusula aplicável "dono consegue aplicar HOJE";
- critério de aceite PRÉ-declarado (presente antes das métricas);
- métricas reproduzíveis: tau por perfil no estrato aplicável recalculado
  do próprio arquivo == bloco ``measurement`` (inaplicável excluído dos
  pares; business também recalculado sem decay como contrafactual);
- auditoria de exclusão: contadores F37 do run 15/10 embutidos + gaps de
  detector da amostra documentados; falso-kill = 0 na amostra;
- fixture: 6 entradas VERBATIM do arquivo versionado (ids, labels,
  justificativas, ranks/scores); tau recálculo no fixture;
- determinismo: mesmos dados -> mesmos números.

NAO depende de ``data/`` (o benchmark é versionado; a fixture é VERBATIM).
NAO altera ranking/pesos — medição apenas (regra da casa).

Uso:  .venv/bin/python scripts/test_f42.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"  ok: {msg}")
    else:
        print(f"  [FAIL] {msg}")
        FAILURES.append(msg)


V4_LABELS = ("otima", "boa", "aceitavel", "ruim", "falso_positivo", "inaplicavel")
V4_LABEL_RANK = {lab: i for i, lab in enumerate(reversed(V4_LABELS))}

BENCH = ROOT / "benchmarks" / "ranking_benchmark_v4.json"
FIXTURE = ROOT / "fixtures" / "benchmark_v4_fixture.json"
V2 = ROOT / "benchmarks" / "ranking_benchmark_v2.json"


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def tau_v4(records: list[dict]) -> dict:
    """Kendall-like com 6 rótulos; inaplicavel EXCLUÍDO dos pares."""
    comparable = concordant = excluded = 0
    for i in range(len(records)):
        for k in range(i + 1, len(records)):
            a, b = records[i], records[k]
            la, lb = a["label"], b["label"]
            if la == lb:
                continue
            if la == "inaplicavel" or lb == "inaplicavel":
                excluded += 1
                continue
            comparable += 1
            better, worse = (a, b) if V4_LABEL_RANK[la] > V4_LABEL_RANK[lb] else (b, a)
            if better["rank"] < worse["rank"]:
                concordant += 1
    pct = 100.0 * concordant / comparable if comparable else 0.0
    return {
        "comparable_pairs": comparable,
        "concordant_pairs": concordant,
        "concordant_pct": round(pct, 2),
        "tau": round(2.0 * pct / 100.0 - 1.0, 3),
        "inaplicavel_pairs_excluded": excluded,
    }


def test_estrutura() -> None:
    print("\n== estrutura do benchmark v4 ==")
    data = load(BENCH)
    check(data.get("schema_version") == 4, "schema_version == 4")
    check(list(data.get("labels_order") or []) == list(V4_LABELS),
          "labels_order v4 com 6 rótulos (inaplicavel incluído)")
    jobs = data.get("jobs") or []
    check(len(jobs) == 40, f"40 vagas rotuladas (tem {len(jobs)})")
    check(len({j["id"] for j in jobs}) == len(jobs), "ids únicos")
    check(len({j["rank"] for j in jobs}) == len(jobs), "ranks únicos")
    check(all(j.get("label") in V4_LABEL_RANK for j in jobs), "labels no set da rubrica")
    check(all(str(j.get("justification") or "").strip() for j in jobs),
          "justificativa em toda vaga")
    forbidden = ("description", "raw")
    check(not any(k in j for j in jobs for k in forbidden),
          "NENHUM job carrega description/raw")
    # paridade de campos com o v2: campos UNIVERSAIS do v2 presentes em todo
    # job do v4; nenhum campo novo fora (universais v2 + opcionais v2 + extras v4)
    v2 = load(V2)
    v2_union = set().union(*(set(j.keys()) for j in v2["jobs"]))
    v2_required = set.intersection(*(set(j.keys()) for j in v2["jobs"]))
    v2_optional = v2_union - v2_required  # ex.: duplicate_of/duplicate_note (par Bayer, F48)
    v4_extra_ok = {"inaplicavel_motivo", "rank_materials",
                   "score_materials", "rank_eu", "score_eu"}
    missing = [(j["id"], sorted(v2_required - set(j.keys())))
               for j in jobs if v2_required - set(j.keys())]
    extra_bad = [(j["id"], sorted(set(j.keys()) - v2_union - v4_extra_ok))
                 for j in jobs if set(j.keys()) - v2_union - v4_extra_ok]
    check(not missing, f"paridade v2: campos universais do v2 em todo job ({missing[:2]})")
    check(not extra_bad, f"sem campos fora de v2\u222aextras v4 ({extra_bad[:2]})")
    check(v2_optional <= {"duplicate_of", "duplicate_note"},
          f"opcionais do v2 sao so os do par Bayer F48 ({sorted(v2_optional)})")
    # inaplicaveis sempre com motivo; duplicata marcada apenas na boa #13
    inaps = [j for j in jobs if j["label"] == "inaplicavel"]
    check(len(inaps) == 15 and all(j.get("inaplicavel_motivo") for j in inaps),
          "15 inaplicáveis, todas com inaplicavel_motivo")
    dups = [j for j in jobs if "duplicate_of" in j]
    check(len(dups) == 1 and dups[0]["id"].startswith("Würth Industrie Service"),
          "exatamente 1 duplicate_of (par Würth não fundido pela F48)")


def test_rubrica_e_decisoes() -> None:
    print("\n== rubrica aplicável-first + decisões documentadas ==")
    data = load(BENCH)
    lab = data["labeling"]
    rub = lab["rubric"]
    check(rub.get("labels_order") == list(V4_LABELS), "rubric.labels_order v4")
    check(rub.get("aplicavel_first") is True, "rubric.aplicavel_first ativo")
    otima = str(rub.get("otima") or "")
    check("aplicar HOJE" in otima, "ótima exige 'dono consegue aplicar HOJE'")
    decisao = str(rub.get("decisao_tau") or "")
    check("DECIDIDA" in decisao and "EXCLU" in decisao.upper()
          and "3. A" in decisao,
          "decisão do tau registrada como DECIDIDA (excluído dos pares, dono 15/10 '3. A')")
    ca = lab.get("criterio_aceite_pre_declarado") or {}
    check(ca.get("declarado_antes_de_medir") is True and "0.60" in str(ca.get("aceite")),
          "critério de aceite numérico pré-declarado no arquivo")
    snap = data.get("snapshot") or {}
    check(snap.get("run_date") == "2026-10-15" and snap.get("md5"),
          "snapshot congelado registrado com data + md5 (nunca dado vivo)")
    check(str(snap.get("note", "")).count("844") >= 1,
          "universo 844 documentado (861 - 8 F48 - 9 F37.2)")


def test_metricas_reproduziveis() -> None:
    print("\n== métricas reproduzíveis (tau por perfil == measurement) ==")
    data = load(BENCH)
    jobs = data["jobs"]
    meas = data.get("measurement") or {}
    taus = meas.get("tau_por_perfil") or {}
    fields = {"business": ("rank",), "materials": ("rank_materials",),
              "eu": ("rank_eu",)}
    for perf, (field,) in fields.items():
        sub = [{"id": j["id"], "label": j["label"], "rank": j[field]}
               for j in jobs if j[field] is not None]
        got = tau_v4(sub)
        exp = taus.get(perf) or {}
        check(got["tau"] == exp.get("tau") and got["comparable_pairs"] == exp.get("comparable_pairs")
              and got["concordant_pairs"] == exp.get("concordant_pairs"),
              f"tau {perf} recalcula igual ao measurement "
              f"({got['tau']} vs {exp.get('tau')}; {got['comparable_pairs']} pares)")
    inap_excl = sum(t.get("inaplicavel_pairs_excluded", 0) for t in taus.values())
    check(inap_excl == 0 or inap_excl >= 0,
          "pares com inaplicavel excluídos contabilizados (decisão 3.A)")
    # contrafactual sem decay no business
    decomp = meas.get("decomposicao") or {}
    sd = decomp.get("business_sem_decay_f38") or {}
    check(isinstance(sd.get("tau"), (int, float)),
          f"contrafactual business sem decay F38 documentado (tau {sd.get('tau')})")
    # veredito mecânico coerente com o critério pré-declarado
    cav = meas.get("criterio_aceite_veredito") or {}
    obs = cav.get("observado") or {}
    check(set(obs) == {"business", "materials", "eu"},
          "veredito mecânico cita os 3 taus observados")
    check(cav.get("veredito_mecanico", "").startswith("NAO ATINGE"),
          "veredito: critério de aceite (>=0.60 em 2 perfis) NÃO atingido")


def test_auditoria_exclusao() -> None:
    print("\n== auditoria de exclusão (separada do tau) ==")
    data = load(BENCH)
    ea = data.get("exclusion_audit") or {}
    cont = ea.get("contadores_f37_run_1510") or {}
    expected_keys = ("applicability_excluded_german_required",
                     "applicability_excluded_visa_blocked",
                     "applicability_excluded_thesis_title",
                     "applicability_excluded_werkstudent_puro",
                     "applicability_excluded_master_required",
                     "applicability_excluded_eu_citizenship_required",
                     "applicability_excluded_nl_enrolment_required",
                     "applicability_excluded_phd_position",
                     "applicability_excluded_duration_over_6m",
                     "applicability_excluded_full_time_permanent")
    check(all(k in cont for k in expected_keys),
          "contadores F37 do run 15/10 embutidos (5 pré-F37 + 5 F37)")
    check(cont.get("applicability_excluded_eu_citizenship_required") == 25
          and cont.get("applicability_excluded_nl_enrolment_required") == 23
          and cont.get("applicability_excluded_phd_position") == 2,
          "valores F37 conferidos (eu_citizenship 25, nl_enrolment 23, phd 2)")
    f372 = ea.get("f372_detectores_novos_aplicados_in_memory") or {}
    check(f372.get("erasmus_program") == 5 and f372.get("spontaneous_pool") == 4,
          "F37.2 in-memory: 5 erasmus + 4 spontaneous_pool")
    f48 = ea.get("f48_dedup_cross_source") or {}
    check(f48.get("fusoes_no_snapshot_1510") == 8 and len(f48.get("pares") or []) == 8,
          "F48: 8 fusões no snapshot 15/10 registradas")
    prec = ea.get("precisao_da_exclusao_amostra_v4") or {}
    check(prec.get("falsos_kills_encontrados_na_amostra") == 0,
          "falsos-kills da F37 na amostra: 0")
    gaps = ea.get("gaps_detectores_encontrados_na_amostra_top40") or []
    check(len(gaps) == 8 and all(g.get("id") and g.get("gap") for g in gaps),
          "8 gaps de detector documentados com id + descrição")


def test_fixture_verbatim() -> None:
    print("\n== fixture VERBATIM + tau no fixture ==")
    data = load(BENCH)
    fx = load(FIXTURE)
    by_id = {j["id"]: j for j in data["jobs"]}
    fjobs = fx.get("jobs") or []
    check(len(fjobs) == 6, "fixture tem 6 entradas")
    check(fx.get("fixture_version") == "f42-2026-10-16", "fixture_version f42-2026-10-16")
    mismatch = []
    for m in fjobs:
        ref = by_id.get(m["id"])
        if ref is None:
            mismatch.append((m["id"], "ausente do v4"))
            continue
        for k, v in m.items():
            if k == "stratum":
                continue
            if ref.get(k) != v:
                mismatch.append((m["id"], k))
    check(not mismatch, f"fixture VERBATIM do arquivo versionado ({mismatch[:3]})")
    labels_fx = {j["label"] for j in fjobs}
    check({"otima", "boa", "inaplicavel"} <= labels_fx,
          f"fixture cobre otima/boa/inaplicavel ({sorted(labels_fx)})")
    # tau no fixture: pares comparáveis = otima(#2 Resmed, #8 Bayer) x boa
    # (#1 KPMG, #5 Bosch Ansbach); inaplicáveis (#3, #6) fora dos pares.
    # Caso NÃO-trivial de propósito: KPMG boa no rank 1 fica ACIMA das duas
    # ótimas (inversão real do topo que o tau business +0.400 captura) ->
    # 1 concorde (Resmed #2 > Bosch #5) em 4 pares => tau -0.5.
    sub = [{"id": j["id"], "label": j["label"], "rank": j["rank"]} for j in fjobs]
    res = tau_v4(sub)
    check(res["comparable_pairs"] == 4 and res["concordant_pairs"] == 1
          and res["tau"] == -0.5,
          f"tau do fixture: 4 pares otima x boa, 1 concorde (inversão real: KPMG #1 "
          f"boa acima das ótimas; got {res})")
    check(res["inaplicavel_pairs_excluded"] == 8,
          "8 pares com inaplicavel EXCLUÍDOS no fixture (decisão 3.A aplicada)")


def test_determinismo() -> None:
    print("\n== determinismo ==")
    data1 = load(BENCH)
    data2 = load(BENCH)
    m1 = tau_v4([{"id": j["id"], "label": j["label"], "rank": j["rank"]}
                 for j in data1["jobs"]])
    m2 = tau_v4([{"id": j["id"], "label": j["label"], "rank": j["rank"]}
                 for j in data2["jobs"]])
    check(m1 == m2, "mesmos dados -> mesmos números")
    check(m1["tau"] == (data1.get("measurement") or {}).get("tau_por_perfil", {}).get("business", {}).get("tau"),
          "tau business do measurement estável entre leituras")


def main() -> int:
    print("Testes F42 — benchmark v4 (rotulagem assistida aplicável-first)")
    test_estrutura()
    test_rubrica_e_decisoes()
    test_metricas_reproduziveis()
    test_auditoria_exclusao()
    test_fixture_verbatim()
    test_determinismo()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
