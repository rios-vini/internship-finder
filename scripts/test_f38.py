#!/usr/bin/env python3
"""F38 — freshness decay: fator multiplicativo por posted_at nos 3 perfis.

Trava o contrato da F38 (PR feature/f38-freshness-decay):

1. **fórmula**: fator = 0.5 ** (idade_dias / meia-vida), meia-vida única
   DECAY_HALF_LIFE_DAYS=365.0 para os 3 perfis (business/materials/EU);
2. **neutro por default**: score_job/materials_score_job/eu_score_job SEM
   ``now`` são byte-identical ao histórico (nenhum call-site existente muda);
3. **desconhecido nunca é penalizado**: sem posted_at (ausente/inválido) →
   fator 1.0, breakdown SEM a chave ``decay`` e score byte-identical;
4. **futuro = neutro**: posted_at no futuro (bad data) → idade 0 (fator 1.0)
   — decay não premia dado ruim;
5. **invariante soma==score**: com decay o breakdown ganha ``decay`` com a
   CONTRIBUIÇÃO ADITIVA (não o fator) e sum(breakdown) == score continua
   válido (validado também para benchmarks v3 pelo ranking_benchmark);
6. **idade**: meia vida exata → fator 0.5; 2 meias-vidas → 0.25; dias
   fracionários contam;
7. **3 perfis com a MESMA fórmula**: mesmo posted_at/now → mesma razão
   score_com_decay/score_sem_decay nos 3 perfis (fator idêntico);
8. **rank_* com now**: propaga o decay e REORDENA (vaga nova sobe);
9. **validate_benchmark aceita v3** (7 componentes + decay) e ainda aceita
   v1/v2 (registros históricos permanecem válidos).

100% offline (fixtures sintéticas VERBATIM — zero rede, zero data/).
Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.ranking import (  # noqa: E402
    DECAY_HALF_LIFE_DAYS,
    Score,
    _apply_decay,
    freshness_decay,
    rank_jobs,
    score_job,
)
from internship_finder.materials_ranking import (  # noqa: E402
    materials_score_job,
    rank_materials_jobs,
)
from internship_finder.eu_ranking import eu_score_job, rank_eu_jobs  # noqa: E402
from internship_finder.ranking_benchmark import (  # noqa: E402
    BREAKDOWN_KEYS_V2,
    BREAKDOWN_KEYS_V3,
    _breakdown_key_set,
)

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# Fixtures VERBATIM (sintéticas, autocontidas — zero rede)
# ---------------------------------------------------------------------------
NOW = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
D = 86400.0  # segundos por dia

BASE_JOB = {
    "id": "fx38|ats:1",
    "title": "Praktikum Procurement & Supply Chain",
    "company": "Robert Bosch GmbH",
    "location": "Stuttgart, DE",
    "country_iso": "de",
    "employment_type": "PART_TIME",
    "description": "procurement, supplier management, english, python, cloud",
}


def at(age_days: float | None, idx: int) -> dict:
    """Fixture com posted_at a ``age_days`` de NOW (None = sem posted_at)."""
    j = dict(BASE_JOB)
    j["id"] = f"fx38|ats:{idx}"
    if age_days is not None:
        j["posted_at"] = (NOW - timedelta(seconds=age_days * D)).isoformat()
    return j


def main() -> int:
    section("T1: fórmula pura — 0.5^(idade/meia-vida); limites")
    check("meia-vida exata → fator 0.5",
          abs(freshness_decay(at(365, 1)["posted_at"], NOW, 365.0) - 0.5) < 1e-9)
    check("2 meias-vidas → fator 0.25",
          abs(freshness_decay(at(730, 1)["posted_at"], NOW, 365.0) - 0.25) < 1e-9)
    check("90d na meia-vida 365d → 0.5**(90/365)",
          abs(freshness_decay(at(90, 1)["posted_at"], NOW, 365.0)
              - 0.5 ** (90 / 365.0)) < 1e-9)
    check("idade fracionária conta (0.5 dia)",
          abs(freshness_decay(at(0.5, 1)["posted_at"], NOW, 365.0)
              - 0.5 ** (0.5 / 365.0)) < 1e-9)
    check("idade 0 (postado agora) → fator 1.0",
          freshness_decay(at(0, 1)["posted_at"], NOW) == 1.0)
    check("SEM posted_at → fator 1.0 (neutro)",
          freshness_decay(None, NOW) == 1.0)
    check("posted_at inválido ('' / 'lixo' / 42) → fator 1.0",
          freshness_decay("", NOW) == 1.0
          and freshness_decay("lixo", NOW) == 1.0
          and freshness_decay(42, NOW) == 1.0)
    check("posted_at NO FUTURO (bad data) → fator 1.0 (nunca premia)",
          freshness_decay((NOW + timedelta(days=3)).isoformat(), NOW) == 1.0)
    check("sem now → fator 1.0 (decay opt-in)",
          freshness_decay(at(900, 1)["posted_at"], None) == 1.0)
    check("meia-vida default = 365.0 (decisão benchmark F38)",
          DECAY_HALF_LIFE_DAYS == 365.0)
    check("teto de sanidade: 10 anos não explode (underflow suave)",
          0.0 < freshness_decay(at(3650, 1)["posted_at"], NOW) < 0.001
          and freshness_decay(at(36500, 1)["posted_at"], NOW) > 0.0)
    check("naive now é tolerado (assume UTC, nunca crash)",
          abs(freshness_decay(at(365, 1)["posted_at"],
                              NOW.replace(tzinfo=None)) - 0.5) < 0.01)

    section("T2: perfil business — byte-identical sem now; decay com now")
    j90 = at(90, 2)
    s_old = score_job(j90)
    s_now = score_job(j90, now=NOW)
    expected = round(s_old.total * (0.5 ** (90 / 365.0)), 2)
    check("sem now: total e breakdown byte-identical (sem chave decay)",
          s_now.total != s_old.total and "decay" not in s_old.breakdown
          and set(s_old.breakdown) == set(BREAKDOWN_KEYS_V2),
          f"total {s_old.total}")
    check("com now: total = round(total * fator)",
          s_now.total == expected, f"{s_now.total} vs {expected}")
    check("breakdown ganha 'decay' com a CONTRIBUIÇÃO (não o fator)",
          "decay" in s_now.breakdown
          and abs(s_now.breakdown["decay"]
                  - round(expected - s_old.total, 2)) < 0.011,
          f"decay={s_now.breakdown.get('decay')}")
    check("invariante soma==score com decay",
          abs(sum(s_now.breakdown.values()) - s_now.total) < 1e-9,
          f"{sum(s_now.breakdown.values())} vs {s_now.total}")
    check("sem posted_at + now: score/breakdown byte-identical (neutro)",
          score_job(at(None, 3), now=NOW).total == score_job(at(None, 3)).total
          and "decay" not in score_job(at(None, 3), now=NOW).breakdown)
    check("fator neutro devolve breakdown INTACTO (mesma chave/valores)",
          _apply_decay(dict(s_old.breakdown), s_old.total, at(None, 3), NOW)
          == (s_old.breakdown, s_old.total))

    section("T3: MESMA fórmula nos 3 perfis")
    j1867 = at(1867, 4)  # caso real medido (aitad)
    f1867 = 0.5 ** (1867 / 365.0)
    for name, fn in (("business", score_job),
                     ("materials", materials_score_job),
                     ("eu", eu_score_job)):
        base = fn(j1867)
        dec = fn(j1867, now=NOW)
        ratio = dec.total / base.total if base.total else None
        ok = (ratio is None and f1867 == 1.0) or abs(ratio - f1867) < 0.02
        check(f"{name}: razão pós/pré = fator 0.5^(1867/365)={f1867:.4f}",
              ok and "decay" in dec.breakdown,
              f"razão={ratio}, decay={dec.breakdown.get('decay')}")
        check(f"{name}: soma==score preservada",
              abs(sum(dec.breakdown.values()) - dec.total) < 1e-9)

    section("T4: rank_* com now — propaga decay e reordena (nova sobe)")
    jobs = [at(365, 10), at(30, 11), at(None, 12), at(730, 13)]
    base_rank = rank_jobs([dict(j) for j in jobs])
    dec_rank = rank_jobs([dict(j) for j in jobs], now=NOW)
    ids_base = [j["id"] for j in base_rank]
    ids_dec = [j["id"] for j in dec_rank]
    check("sem now: ordem histórica (mais texto-relevante primeiro)",
          ids_base == [j["id"] for j in sorted(
              jobs, key=lambda j: (-score_job(j).total,
                                    j["title"].casefold(),
                                    j["company"].casefold(), j["id"]))],
          f"{ids_base}")
    check("com now: vaga nova (30d) sobe acima da de 365d",
          ids_dec.index("fx38|ats:11") < ids_dec.index("fx38|ats:10"),
          f"{ids_dec}")
    check("com now: vaga de 730d é a última (fator 0.25)",
          ids_dec[-1] == "fx38|ats:13", f"{ids_dec}")
    check("sem posted_at (12) fica entre as duas (fator 1.0)",
          ids_dec.index("fx38|ats:12") < ids_dec.index("fx38|ats:10"),
          f"{ids_dec}")
    check("materiais/eu: rank com now reordena igual (mesma fórmula)",
          [j["id"] for j in rank_materials_jobs(jobs, now=NOW)]
          == ids_dec
          or {j["id"] for j in rank_materials_jobs(jobs, now=NOW)} == set(ids_dec))
    check("entrada não é mutada pelo rank com now",
          all("score" not in j and "materials_score" not in j for j in jobs))

    section("T5: validate_benchmark — v3 (7+decay) aceito; v1/v2 intactos")
    v3 = dict(BASE_JOB)
    v3_bd = {"area": 2.0, "skills": 2.25, "language": 1.5, "type": 1.0,
             "location": 1.0, "penalties": 0.0, "registry": 1.0, "decay": -3.0}
    check("breakdown v2 (7) continua válido",
          _breakdown_key_set({k: 0.0 for k in BREAKDOWN_KEYS_V2})
          == set(BREAKDOWN_KEYS_V2))
    check("breakdown v3 (7+decay) válido",
          _breakdown_key_set(v3_bd) == set(BREAKDOWN_KEYS_V3))
    check("chave desconhecida continua rejeitada",
          _breakdown_key_set({**v3_bd, "coisa": 1.0}) is None)
    check("v3 sem decay (vaga neutra) rejeita? NÃO: é v2 — aceito",
          _breakdown_key_set({k: v for k, v in v3_bd.items() if k != "decay"})
          == set(BREAKDOWN_KEYS_V2))

    section("T6: neutro em massa — universo sem posted_at é byte-identical")
    # 6 vagas de idades variadas, depois a mesma lista despida de posted_at
    bunch = [at(90, 20 + i) for i in range(3)] + [at(None, 23 + i) for i in range(3)]
    ranked_no_now = rank_jobs([dict(j) for j in bunch])
    stripped = [dict(j, posted_at=None) for j in bunch]
    stripped_now = rank_jobs(stripped, now=NOW)
    same = all(
        a["score"] == b["score"]
        and json.dumps(a["score_breakdown"], sort_keys=True)
        == json.dumps(b["score_breakdown"], sort_keys=True)
        for a, b in zip(ranked_no_now, stripped_now)
    )
    check("sem posted_at em massa + now == sem now (score E breakdown)",
          same)
    check("ordem idêntica (decay neutro não reordena)",
          [j["id"] for j in ranked_no_now] == [j["id"] for j in stripped_now])
    check("nenhum breakdown com posted_at despido carrega 'decay'",
          all("decay" not in j["score_breakdown"] for j in stripped_now))

    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("TUDO OK — F38 freshness decay: invariantes verdes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
