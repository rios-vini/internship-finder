"""Suite F47 — religação das fontes F30 default-OFF: jobmensa + praktikum_info.

Estado ANTES (F30, 13/10): ``F30_DEFAULT_OFF_SOURCES`` = {jobmensa,
praktikum_info} — desligadas por evidência A/B (jobmensa zero-yield
estrutural: 187 kept -> 0 eligible, 100% Werkstudent puro; praktikum_info
mesma DB da ABSOLVENTA, dupla contagem). Estado DEPOIS (F47, 17/10):
decisão do dono (universo pós-exclusões F37/F48 pede fontes) — o set fica
VAZIO e as duas voltam a coletar no cron diário SEM mudar crontab/env.

Trava as REGRAS, não contagens (lição F7/F9 — teste de config valida
regras paramétricas):

- DEFAULT ON: sem env, NENHUMA fonte vem desligada (o set vazio é o
  default; `disabled_research_sources(env={})` == set vazio) e o estágio
  executa TODAS as 11 fontes registradas (E1/E2).
- MECANISMO default-off PERMANECE: uma fonte adicionada ao set volta a
  ser skipped_disabled (E3) — outras fontes podem entrar off no futuro.
- KILL SWITCH por cima de TUDO: env CSV desliga qualquer fonte,
  inclusive as religadas (E4/E5; summary.disabled reflete, C4).
- ROBOTS GATES PRESERVADOS: nenhum gate/robots check mudou na F47 —
  fixtures verbatim da F30 (test_f30.py continua sendo a fonte da
  verdade dos adapters; aqui só o gate de defaults/estágio) (F1/F2).
- DEGRADAÇÃO GRACIOSA: fonte religada que falha -> registro failed no
  summary, run segue (partial), exit code nunca muda (D1/D2/C4).
- A/B OFFLINE (funil completo, zero HTTP): com as fixtures verbatim da
  F30, o pool das 2 fontes religadas adiciona eligible (absolventa+
  praktikum_info colapsam o par uno pela chave (c); jobmensa contribui
  0 eligible — evidência 13/10 continua valendo) (F1/F2/F3/F4).
- ZERO REDE: nenhum socket nesta suíte (fetchers/opener fake; padrão
  test_f21/test_f30).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import internship_finder.research_sources as rs  # noqa: E402
import test_f30 as f30  # noqa: E402  (fixtures VERBATIM da F30)
from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.filters import select_eligible  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


def _mk_jobs(n, source):
    out = []
    for i in range(n):
        out.append(rs.Job(
            id=f"x|{source}:{i}", source=source, title=f"Praktikum X {i}",
            company="X", location="Berlin", country="de",
            url=f"https://example.com/{source}/{i}",
            collected_at=rs.datetime.now(rs.UTC),
        ))
    return out


# ---------------------------------------------------------------------------
# A. Default ON — o set vazio é a configuração
# ---------------------------------------------------------------------------


def test_defaults_on() -> None:
    print("== A. Default ON (F47) ==")
    check("A1. F30_DEFAULT_OFF_SOURCES vazio (fontes religadas)",
          rs.F30_DEFAULT_OFF_SOURCES == frozenset(),
          f"set={rs.F30_DEFAULT_OFF_SOURCES}")
    check("A2. jobmensa/praktikum_info registradas em RESEARCH_SOURCE_ORDER",
          {"jobmensa", "praktikum_info"} <= {n for n, _ in rs.RESEARCH_SOURCE_ORDER})
    check("A3. 18 fontes registradas (F21 6 + F30 4 + bme + fraunhofer F128 + F131 5 + englishjobs F140)",
          len(rs.RESEARCH_SOURCE_ORDER) == 18,
          f"n={len(rs.RESEARCH_SOURCE_ORDER)}")
    check("A4. sem env: NENHUMA fonte desligada (default ON total)",
          rs.disabled_research_sources(env={}) == set())
    # arquitetura: kill switch por cima de tudo permanece
    check("A5. env CSV continua o kill switch manual (RESEARCH_SOURCES_OFF_ENV)",
          rs.RESEARCH_SOURCES_OFF_ENV == "INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF")


# ---------------------------------------------------------------------------
# B. Mecanismo default-off PERMANECE (regra paramétrica)
# ---------------------------------------------------------------------------


def test_default_off_mechanism() -> None:
    print("== B. Mecanismo default-off (set + env) ==")
    # disabled_research_sources NAO tem injecao de set (le o modulo) — a
    # prova do mecanismo é via env CSV (mesma uniao do set) + o assert A1
    # (set vazio). Se uma fonte entrar no set no futuro, a regra E a mesma:
    # nome no set OU no env -> skipped_disabled.
    check("B1. mecanismo: env CSV desliga qualquer fonte pelo NOME",
          rs.disabled_research_sources(env={rs.RESEARCH_SOURCES_OFF_ENV: "mpg_rss"})
          == {"mpg_rss"})
    check("B2. mecanismo: CSV com as duas religadas as desliga (kill switch)",
          rs.disabled_research_sources(
              env={rs.RESEARCH_SOURCES_OFF_ENV: "jobmensa, praktikum_info"})
          == {"jobmensa", "praktikum_info"})
    check("B3. mecanismo: case/whitespace tolerantes (padrao F21)",
          rs.disabled_research_sources(
              env={rs.RESEARCH_SOURCES_OFF_ENV: "  JOBMENSA ,bme"})
          == {"jobmensa", "bme"})
    check("B4. nome desconhecido: aviso + ignorado (nunca crasha)",
          rs.disabled_research_sources(env={rs.RESEARCH_SOURCES_OFF_ENV: "nao_existe"})
          == set())


# ---------------------------------------------------------------------------
# C. Estágio: 11 fontes executam; kill switch; fail-soft; registro
# ---------------------------------------------------------------------------


def test_stage() -> None:
    print("== C. Estagio: defaults/kill switch/fail-soft ==")
    # E1 — default ON: TODAS as 17 executam (fetchers fake COMPLETOS — com o
    # set vazio, fonte sem fake cairia no fetcher REAL = rede; a suite e
    # zero-HTTP por construcao, licao da sonda F47).
    fetchers = {n: (lambda **kw: (_mk_jobs(1, "x"), {"source": "x", "status": "ok", "jobs": 1}))
                for n, _ in rs.RESEARCH_SOURCE_ORDER}
    jobs, summary = rs.collect_research_sources(fetchers=fetchers, env={})
    ok_n = sum(1 for s in summary["sources"].values() if s["status"] == "ok")
    check("C1. default ON: 18 fontes ok, 0 skipped_disabled, 18 jobs",
          ok_n == 18 and len(jobs) == 18
          and all(s["status"] == "ok" for s in summary["sources"].values()),
          f"ok={ok_n} jobs={len(jobs)} status={summary['status']}")
    check("C2. default ON: disabled=[] no summary",
          summary["disabled"] == [], f"disabled={summary['disabled']}")

    # E2 — kill switch das DUAS religadas: skipped_disabled + resto ok.
    jobs2, summary2 = rs.collect_research_sources(
        fetchers=fetchers,
        env={rs.RESEARCH_SOURCES_OFF_ENV: "jobmensa,praktikum_info"})
    s2 = summary2["sources"]
    check("C3. kill switch: as 2 religadas pulam; as 16 restantes ok",
          s2["jobmensa"]["status"] == "skipped_disabled"
          and s2["praktikum_info"]["status"] == "skipped_disabled"
          and sum(1 for s in s2.values() if s["status"] == "ok") == 16
          and len(jobs2) == 16,
          f"jobs={len(jobs2)} status={summary2['status']}")

    # C4 — registro JSONL reflete o kill switch (contrato do cron).
    from internship_finder.cli import _research_sources_record
    rec = _research_sources_record("run-f47", summary2)
    check("C4. registro research_sources: type/disabled/sources no JSONL",
          rec["type"] == "research_sources"
          and rec["disabled"] == ["jobmensa", "praktikum_info"]
          and rec["sources"]["jobmensa"]["status"] == "skipped_disabled",
          f"disabled={rec['disabled']}")

    # C5 — fonte religada que FALHA: registro failed, run segue (partial).
    fetchers_fail = dict(fetchers)
    fetchers_fail["jobmensa"] = (
        lambda **kw: (_ for _ in ()).throw(ConnectionError("jobmensa down")))
    jobs3, summary3 = rs.collect_research_sources(fetchers=fetchers_fail, env={})
    s3 = summary3["sources"]
    # F140: 18 fontes total; 1 falha (jobmensa) = 17 jobs
    check("C5. jobmensa falha -> failed no summary; run segue (partial); "
          "exit inalterado por construcao (estagio fail-soft)",
          s3["jobmensa"]["status"] == "failed"
          and summary3["status"] == "partial"
          and len(jobs3) == 17,
          f"jobs={len(jobs3)} status={summary3['status']}")


# ---------------------------------------------------------------------------
# D. Adapters das religadas: parse/fetch por fixture (gates intocados)
# ---------------------------------------------------------------------------


def test_adapters() -> None:
    print("== D. Adapters religados (fixtures F30 verbatim) ==")
    # robots gates: NENHUMA constante/URL mudou na F47 (probe vivo 13/10).
    check("D1. endpoints F30 inalterados (robots gates 4/4 da F30 valem)",
          rs.JOBMENSA_SITEMAP_URL == "https://www.jobmensa.de/sitemaps/jobsearch_jobs.xml.gz"
          and rs.PRAKTIKUM_INFO_URL == "https://www.praktikum.info/stellenangebote"
          and rs.ABSOLVENTA_JOBS_URL == "https://www.absolventa.de/jobs/channel/materialwirtschaft"
          and rs.AMAZON_SEARCH_URL == "https://www.amazon.jobs/en/search.json")
    # jobmensa: sitemap gz verbatim -> parse + fetch ok (fixture F30).
    jm, urls, kept = rs.parse_jobmensa_sitemap(f30.JOBMENSA_SITEMAP_XML)
    check("D2. jobmensa parse (fixture F30): 4 urls, 2 kept, ids jobvalley",
          urls == 4 and kept == 2
          and all(j.id.startswith("jobvalley|jobmensa:") for j in jm),
          f"urls={urls} kept={kept}")

    def gz_opener(req):
        return f30.JOBMENSA_SITEMAP_GZ

    jm_f, stats_jm = rs.fetch_jobmensa(opener=gz_opener)
    check("D3. jobmensa fetch ok (gzip verbatim, 1 request/run)",
          stats_jm["status"] == "ok" and len(jm_f) == 2
          and stats_jm["rows_seen"] == 4,
          f"stats={stats_jm}")
    # praktikum_info: mesmo HTML uno -> materializa com host certo.
    pk = rs._parse_uno_listing(f30.UNO_LISTING_HTML, rs.SOURCE_PRAKTIKUM_INFO)
    check("D4. praktikum_info parse (fixture F30): 2 kept, host certo",
          len(pk) == 2
          and all(j.url.startswith("https://www.praktikum.info/") for j in pk)
          and all(j.source == "praktikum_info" for j in pk),
          f"n={len(pk)}")

    def dead(req):
        raise ConnectionError("offline")

    _, stats_pk = rs.fetch_praktikum_info(opener=dead)
    check("D5. praktikum_info opener morto -> [] + failed (fail-soft)",
          stats_pk["status"] == "failed")


# ---------------------------------------------------------------------------
# F. A/B offline — fixtures verbatim da F30, funil completo, zero HTTP
# ---------------------------------------------------------------------------


def test_ab_funnel() -> None:
    print("== F. A/B offline (funil completo com fixtures F30) ==")
    ab = rs._parse_uno_listing(f30.UNO_LISTING_HTML, rs.SOURCE_ABSOLVENTA)
    pk = rs._parse_uno_listing(f30.UNO_LISTING_HTML, rs.SOURCE_PRAKTIKUM_INFO)
    check("F1. OFF (hoje): so absolventa -> 2 cards no pool",
          len(ab) == 2, f"ab={len(ab)}")
    merged, stats, removed = deduplicate(
        [j.to_dict() for j in ab] + [j.to_dict() for j in pk])
    check("F2. ON (F47): pool 2->4; dedup colapsa o par uno pela chave (c) "
          "(2 removidas, mesmo external_id/logica documentada)",
          len(merged) == 2 and stats.get("company+title+location", 0) == 2,
          f"merged={len(merged)} stats={dict(stats)}")
    sel_off, _ = select_eligible([j.to_dict() for j in ab], student=True,
                                 area=True, country="de", applicability=True)
    sel_on, _ = select_eligible(merged, student=True, area=True,
                                country="de", applicability=True)
    check("F3. eligible NAO diminiu com a fonte religada (colapso correto)",
          # F141: o card B ("Fachkraft fuer Lagerlogistik") passou a ser
          # reconhecido como area de logistica (composto, substring) — os
          # DOIS cards absolutventa sao elegiveis agora (antes: 1)
          len(sel_on) >= len(sel_off) == 2,
          f"off={len(sel_off)} on={len(sel_on)}")
    # caso adverso: sem location o par uno passa RETO (dupla exibicao
    # residual documentada no set/comment F47) — comportamento conhecido.
    def no_loc(job):
        d = dict(job.to_dict())
        d["location"] = None
        return d
    merged_nl, stats_nl, _ = deduplicate(
        [no_loc(j) for j in ab] + [no_loc(j) for j in pk])
    check("F4. sem location o par uno nao colapsa (risco documentado, "
          "dupla exibicao residual)",
          len(merged_nl) == 4 and stats_nl == {},
          f"merged={len(merged_nl)}")
    jm, _, _ = rs.parse_jobmensa_sitemap(f30.JOBMENSA_SITEMAP_XML)
    sel_jm, counts_jm = select_eligible([j.to_dict() for j in jm],
                                        student=True, area=True,
                                        country="de", applicability=True)
    check("F5. jobmensa: 0 eligible (evidencia 13/10 continua valendo; "
          "custo 1 request/dia)",
          len(sel_jm) == 0, f"counts={dict(counts_jm)}")


def main() -> int:
    test_defaults_on()
    test_default_off_mechanism()
    test_stage()
    test_adapters()
    test_ab_funnel()
    fails = [c for c in CHECKS if not c[1]]
    print()
    print(f"F47: {len(CHECKS) - len(fails)} OK, {len(fails)} FAIL")
    if fails:
        for name, _, detail in fails:
            print(f"  FAIL: {name} {detail}")
        print("FALHAS")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
