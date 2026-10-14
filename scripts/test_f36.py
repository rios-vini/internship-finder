"""Testes da Fase F36 — perfil EU non-DE: terceiro perfil de ranking (100% offline).

F36 (veredito do dono 13/10): ranking SEPARADO para o estrato não-DE,
mesmo padrão da Fase 4 (Materials). Este teste é offline, sem rede, sem
``data/`` — fixtures SINTÉTICAS (nenhum texto real de vaga):

- **T1 invariante byte-idêntica (a condição (a) do veredito)**: sobre um
  fixture sintético com N vagas variadas, os scores BREAKDOWN dos perfis
  business (``score``/``score_breakdown``) e materials
  (``materials_score``/``materials_breakdown``) são IDÊNTICOS antes e
  depois de computar o perfil EU — ``rank_eu_jobs`` adiciona campos NOVOS
  e nunca toca os existentes (ordem do dict incluída).
- **T2 componentes do perfil EU**: location vale +1.0 para TODOS os
  países-alvo (NL/BE/LU/FI e também DE — sem bônus Berlin); interest
  +0.5 pela watchlist (match exato e substring; ausente = 0, nunca erro);
  fn −2.5 para marketing/HR/sales-BD no título SEM termo primário de área;
  híbridos "HR Analytics"/"Sales Analytics" PROTEGIDOS pelo gate (fn=0);
  area/skills/language/type/penalties idênticos ao business.
- **T3 ranking próprio e desempate determinístico**: ``rank_eu_jobs``
  ordena por eu_score desc com o desempate oficial (título casefold →
  empresa → id); determinismo (duas execuções → listas iguais); a entrada
  NÃO é mutada; campos eu_* presentes e business/materials intactos.
- **T4 isolamento dos perfis existentes (padrão Fase 4)**: sobre o MESMO
  fixture, ``rank_jobs`` e ``rank_materials_jobs`` produzem scores
  idênticos com e sem a existência do módulo EU — eu_ranking não é
  importado por ranking.py/materials_ranking.py (verificação estática).
- **T5 seções de display**: digest ``eu_lines`` (header próprio, top 5,
  score eu — não o business) e minimal_page com seção 🇪🇺 (score_key
  eu_score, include_eu/--no-eu).

Uso:  .venv/bin/python scripts/test_f36.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.eu_ranking import (  # noqa: E402
    PENALTY_NON_TARGET_FUNCTION,
    WEIGHT_TARGET_COUNTRY,
    WEIGHT_WATCHLIST_INTEREST,
    eu_score_job,
    rank_eu_jobs,
    watchlist_interest,
)
from internship_finder.materials_ranking import (  # noqa: E402
    rank_materials_jobs,
)
from internship_finder.ranking import rank_jobs  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures sintéticas (nenhum dado real; nomes inventados)
# ---------------------------------------------------------------------------

FX_JOBS = [
    {
        "id": "fx|nl:1", "title": "Supply Chain Intern",
        "company": "ZuidLogistiek BV", "location": "Rotterdam, NL",
        "country_iso": "nl", "employment_type": "FULL_TIME",
        "description": "Support the procurement team with reporting in "
                       "English. Python and APIs. Inventory management.",
    },
    {
        "id": "fx|be:2", "title": "Digital Marketing Intern",
        "company": "Bruxelles Buzz", "location": "Brussels, BE",
        "country_iso": "be", "employment_type": "PART_TIME",
        "description": "Create content for our brand. English required.",
    },
    {
        "id": "fx|hr:3", "title": "HR Analytics Intern",
        "company": "LuxPeople SA", "location": "Luxembourg, LU",
        "country_iso": "lu", "employment_type": "FULL_TIME",
        "description": "Data analytics for people teams. English. Python.",
    },
    {
        "id": "fx|de:4", "title": "Praktikum Einkauf",
        "company": "NordWerk GmbH", "location": "Hamburg, DE",
        "country_iso": "de", "employment_type": "FULL_TIME",
        "description": "Beschaffung und supplier management.",
    },
    {
        "id": "fx|sales:5", "title": "Sales Development Intern",
        "company": "FjordStart", "location": "Helsinki, FI",
        "country_iso": "fi", "employment_type": "FULL_TIME",
        "description": "Grow the pipeline. English. CRM reporting.",
    },
    {
        "id": "fx|remote:6", "title": "Procurement Analyst Intern (Remote)",
        "company": "RemoteCo", "location": "Remote", "country_iso": None,
        "employment_type": "FULL_TIME",
        "description": "Procurement analytics, English, python, cloud.",
    },
    {
        "id": "fx|wd:6", "title": "Business Development Intern",
        "company": "WatchCo", "location": "Amsterdam, NL",
        "country_iso": "nl", "employment_type": "FULL_TIME",
        "description": "Sales and growth.",
    },
]


def _baseline_scores(jobs):
    """Scores business + materials de um snapshot (fields + ordem)."""
    ranked_biz = rank_jobs([dict(j) for j in jobs])
    ranked_mat = rank_materials_jobs([dict(j) for j in jobs])
    return (
        {j["id"]: (j["score"], json.dumps(j["score_breakdown"])) for j in ranked_biz},
        {j["id"]: (j["materials_score"], json.dumps(j["materials_breakdown"]))
         for j in ranked_mat},
    )


def main() -> int:
    section("T1: invariante byte-idêntica — perfis business/materials intocados")
    biz_before, mat_before = _baseline_scores(FX_JOBS)
    ranked_eu = rank_eu_jobs([dict(j) for j in FX_JOBS])
    biz_after, mat_after = _baseline_scores(FX_JOBS)
    check("scores business byte-idênticos antes/depois do perfil EU",
          biz_before == biz_after,
          f"{len(biz_before)} vagas comparadas")
    check("scores materials byte-idênticos antes/depois do perfil EU",
          mat_before == mat_after,
          f"{len(mat_before)} vagas comparadas")
    check("rank_eu_jobs adiciona eu_score/eu_breakdown (campos novos)",
          all("eu_score" in j and "eu_breakdown" in j for j in ranked_eu))
    check("entrada não é mutada pelo rank_eu_jobs",
          all("eu_score" not in j for j in FX_JOBS))

    section("T2: componentes do perfil EU (fixtures sintéticas)")
    # location: todos os países-alvo valem o mesmo; sem Berlin bonus
    sc_nl = eu_score_job(dict(FX_JOBS[0]))
    sc_de = eu_score_job(dict(FX_JOBS[3]))
    check(f"location NL = +{WEIGHT_TARGET_COUNTRY} (país-alvo)",
          sc_nl.breakdown["location"] == WEIGHT_TARGET_COUNTRY,
          f"location={sc_nl.breakdown['location']}")
    check(f"location DE = +{WEIGHT_TARGET_COUNTRY} (sem bônus Berlin no perfil EU)",
          sc_de.breakdown["location"] == WEIGHT_TARGET_COUNTRY,
          f"location={sc_de.breakdown['location']}")
    check("location remoto/sem iso = 0",
          eu_score_job(dict(FX_JOBS[5])).breakdown["location"] == 0.0)
    # interest: watchlist (fixture escreve um arquivo temporário)
    with tempfile.TemporaryDirectory() as td:
        wl_path = Path(td) / "company_watchlist.json"
        wl_path.write_text(json.dumps({"companies": ["ZuidLogistiek BV", "WatchCo"]}),
                           encoding="utf-8")
        import internship_finder.eu_ranking as eur
        eur._watchlist_cache = None
        eur._WATCHLIST_PATH = wl_path
        check("interest +0.5 para empresa da watchlist (match exato)",
              watchlist_interest("ZuidLogistiek BV") == WEIGHT_WATCHLIST_INTEREST)
        check("interest +0.5 por substring (nome legal contém o nome)",
              watchlist_interest("ZuidLogistiek BV Rotterdam") == WEIGHT_WATCHLIST_INTEREST)
        check("interest 0 para empresa fora da watchlist",
              watchlist_interest("Bruxelles Buzz") == 0.0)
        check("interest 0 para company vazia/None (nunca erro)",
              watchlist_interest("") == 0.0 and watchlist_interest(None) == 0.0)
        # fn penalty: título de função não-alvo SEM termo primário de área
        sc_mkt = eu_score_job(dict(FX_JOBS[1]))
        check("fn −2.5 para 'Digital Marketing Intern' (sem área primária)",
              sc_mkt.breakdown["fn"] == PENALTY_NON_TARGET_FUNCTION,
              f"fn={sc_mkt.breakdown['fn']}")
        # gate: híbrido com área primária é protegido
        sc_hyb = eu_score_job(dict(FX_JOBS[2]))
        check("gate: 'HR Analytics Intern' protegido (analytics é primária)",
              sc_hyb.breakdown["fn"] == 0.0, f"fn={sc_hyb.breakdown['fn']}")
        # sales-BD sem área primária é penalizado
        sc_sales = eu_score_job(dict(FX_JOBS[4]))
        check("fn −2.5 para 'Sales Development Intern' (sem área primária)",
              sc_sales.breakdown["fn"] == PENALTY_NON_TARGET_FUNCTION,
              f"fn={sc_sales.breakdown['fn']}")
        # watchlist interest aplicado no score completo (WatchCo na fixture)
        eur._watchlist_cache = None
        eur._WATCHLIST_PATH = wl_path
        sc_wd = eu_score_job(dict(FX_JOBS[6]))
        check("score completo usa a watchlist (interest do fixture)",
              sc_wd.breakdown["interest"] == WEIGHT_WATCHLIST_INTEREST,
              f"interest={sc_wd.breakdown['interest']}")
    # watchlist ausente/corrompida → 0 para todos, nunca erro
    import internship_finder.eu_ranking as eur
    eur._watchlist_cache = None
    eur._WATCHLIST_PATH = Path("/nonexistent/definitely/missing.json")
    check("watchlist ausente → interest 0 sem erro",
          watchlist_interest("ZuidLogistiek BV") == 0.0)
    eur._watchlist_cache = None
    bad = Path(tempfile.mkdtemp()) / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    eur._WATCHLIST_PATH = bad
    check("watchlist corrompida → interest 0 sem erro",
          watchlist_interest("ZuidLogistiek BV") == 0.0)
    eur._watchlist_cache = None
    # restaura o path real do repo para os demais testes
    eur._WATCHLIST_PATH = (
        Path(__file__).resolve().parent.parent / "config" / "company_watchlist.json"
    )

    section("T3: ranking próprio + desempate determinístico")
    r1 = rank_eu_jobs([dict(j) for j in FX_JOBS])
    r2 = rank_eu_jobs([dict(j) for j in FX_JOBS])
    check("determinismo: duas execuções → mesma ordem",
          [j["id"] for j in r1] == [j["id"] for j in r2])
    scores_desc = [j["eu_score"] for j in r1]
    check("ordenação por eu_score desc",
          scores_desc == sorted(scores_desc, reverse=True))
    # empate: dois títulos idênticos, empresas distintas → título casefold, depois empresa
    tie_jobs = [
        {"id": "fx|t:1", "title": "Supply Chain Intern", "company": "Bbee",
         "location": "Utrecht, NL", "country_iso": "nl", "description": ""},
        {"id": "fx|t:2", "title": "supply chain intern", "company": "Aaa Ltd",
         "location": "Utrecht, NL", "country_iso": "nl", "description": ""},
    ]
    rt = rank_eu_jobs(tie_jobs)
    check("desempate: título casefold → empresa casefold",
          [j["id"] for j in rt] == ["fx|t:2", "fx|t:1"],
          f"ordem: {[j['id'] for j in rt]}")
    # supply chain NL deve liderar o ranking do fixture (área primária + EN + país-alvo)
    check("top do fixture = Supply Chain Intern NL (sinal correto no topo)",
          r1[0]["id"] == "fx|nl:1", f"top: {r1[0]['id']}")
    # F36 display: o corte de exibição é o ESTRATO (iso != de)
    from internship_finder.eu_ranking import is_eu_stratum_job, rank_eu_stratum
    stratum_ids = [j["id"] for j in rank_eu_stratum([dict(j) for j in FX_JOBS])]
    check("rank_eu_stratum filtra o estrato (sem vagas DE)",
          set(stratum_ids) == {"fx|nl:1", "fx|be:2", "fx|hr:3", "fx|sales:5",
                               "fx|wd:6"},
          f"stratum: {stratum_ids}")
    check("is_eu_stratum_job: remoto sem iso não é do estrato",
          not is_eu_stratum_job(dict(FX_JOBS[5])))
    check("is_eu_stratum_job: vaga DE não é do estrato",
          not is_eu_stratum_job(dict(FX_JOBS[3])))

    section("T4: isolamento estático dos perfis existentes")
    src_root = Path(__file__).resolve().parent.parent / "src" / "internship_finder"
    ranking_src = (src_root / "ranking.py").read_text(encoding="utf-8")
    materials_src = (src_root / "materials_ranking.py").read_text(encoding="utf-8")
    check("ranking.py não importa eu_ranking",
          "eu_ranking" not in ranking_src)
    check("materials_ranking.py não importa eu_ranking",
          "eu_ranking" not in materials_src)
    # pesos dos perfis existentes intocados (regressão proibida — veredito)
    check("WEIGHT_REGISTRY_INTEREST do business segue +1.0",
          "WEIGHT_REGISTRY_INTEREST = 1.0" in ranking_src)
    check("WEIGHT_MATERIALS_TITLE do materials segue 2.5",
          "WEIGHT_MATERIALS_TITLE = 2.5" in materials_src)

    section("T5: seções de display (digest + minimal_page)")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ranking_digest as rd  # noqa: E402

    eu_sec = rd.eu_lines([dict(j) for j in FX_JOBS], [])
    check("digest: seção EU tem header próprio",
          any("EU non-DE" in l for l in eu_sec), f"header: {eu_sec[0][:60]}")
    check("digest: top 5 com score eu (não o business)",
          any("(eu " in l for l in eu_sec))
    check("digest: seção EU só traz vagas do estrato (top = Supply Chain NL)",
          eu_sec[2].strip().startswith("1.")
          and "Supply Chain Intern" in eu_sec[2])
    check("digest: lista vazia → sem seção (nunca erro)",
          rd.eu_lines([], []) == [])
    # minimal_page: seção 🇪🇺 com score_key eu_score
    import minimal_page as mp  # noqa: E402

    check(f"minimal_page: EU_SECTION_TOP = 10 (padrão materials)",
          mp.EU_SECTION_TOP == 10)
    from internship_finder.eu_ranking import rank_eu_stratum as _res
    html = mp.render_minimal_html(
        [dict(j) for j in FX_JOBS], total_eligible=len(FX_JOBS),
        generated_at="2026-10-14T00:00:00Z",
        eu=_res([dict(j) for j in FX_JOBS])[:mp.EU_SECTION_TOP],
    )
    check("minimal_page: seção 🇪🇺 presente quando eu=ranking",
          "Fora da Alemanha" in html)
    check("minimal_page: data-s da seção EU usa eu_score (não o business)",
          f'data-s="{r1[0]["eu_score"]:.1f}"' in html)
    html_no_eu = mp.render_minimal_html(
        [dict(j) for j in FX_JOBS], total_eligible=len(FX_JOBS),
        generated_at="2026-10-14T00:00:00Z", eu=None,
    )
    check("minimal_page: sem eu → sem seção EU",
          "Fora da Alemanha" not in html_no_eu)
    # CLI --no-eu desliga a seção (subprocess offline com fixture em tmp)
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        inp = tdp / "eligible_jobs.json"
        inp.write_text(json.dumps([dict(j) for j in FX_JOBS]), encoding="utf-8")
        out = tdp / "page.html"
        env = {**dict(__import__("os").environ),
               "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src")}
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "minimal_page.py"),
             "--input", str(inp), "--output", str(out), "--top", "10",
             "--archive", "", "--no-eu"],
            capture_output=True, text=True, env=env, timeout=120,
        )
        ok_run = proc.returncode == 0 and out.exists()
        check("CLI: minimal_page --no-eu roda offline (fixture)", ok_run,
              (proc.stderr or "").strip()[:200])
        if ok_run:
            check("CLI: --no-eu → página sem seção EU",
                  "Fora da Alemanha" not in out.read_text(encoding="utf-8"))
        proc2 = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "minimal_page.py"),
             "--input", str(inp), "--output", str(out), "--top", "10",
             "--archive", ""],
            capture_output=True, text=True, env=env, timeout=120,
        )
        ok_run2 = proc2.returncode == 0 and out.exists()
        check("CLI: default ligado → página com seção EU", ok_run2 and
              "Fora da Alemanha" in out.read_text(encoding="utf-8"))

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"F36: {len(FAILURES)} FALHA(S) de {CHECKS} checks")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print(f"F36: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
