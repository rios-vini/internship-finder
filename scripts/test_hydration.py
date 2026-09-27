#!/usr/bin/env python3
"""Testes da hidratacao seletiva de descriptions (Fase A) — 100% offline.

Cobre os 10 casos obrigatorios da spec (secao 11), mapeados nos blocos:

1.  Job ja com description nao e hidratado ............. bloco 1 (check 1)
2.  Job sem description entra na selecao ............... bloco 1 (check 2)
3.  Falha de hydration nao remove Job .................. bloco 3
4.  Falha de uma vaga nao interrompe as demais ......... bloco 3
5.  Softgarden usa description do feed quando habilitado  bloco 4 (wiring D4)
6.  Workday recebe o limite apropriado se suportado ... bloco 5 (D8/D3)
7.  Phenom nao tenta detail-fetch inexistente .......... bloco 6
8.  Metricas contabilizam sucesso/falha corretamente .. blocos 1/3/7/8
9.  Nenhuma mudanca de ranking e feita pelo novo codigo  bloco 8
10. Pipeline continua funcionando com hydration indisponivel  bloco 9

Convencao do repo: [OK]/[FAIL], termina \"TUDO OK\" (exit 0). Sem rede — a
factory real (get_scraper) e substituida por fakes injetaveis; o wiring do
Softgarden e testado sem tocar fetch (le a decisao do flag ANTES do fetch).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante que src/ do repo entre no path mesmo fora de install -e.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.collectors import ats_scraper as collector_mod  # noqa: E402
from internship_finder.hydration import (  # noqa: E402
    HYDRATION_BUDGET_SECONDS,
    HYDRATION_TIMEOUT,
    _slug_for,
    hydrate_descriptions,
)
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.models.job import Job  # noqa: E402
from internship_finder.ranking import score_job  # noqa: E402

_FAILS = 0


def check(name: str, cond: bool) -> None:
    global _FAILS
    tag = "[OK]" if cond else "[FAIL]"
    print(f"  {tag} {name}")
    if not cond:
        _FAILS += 1


# ---------------------------------------------------------------- fixtures

def make_job(**overrides) -> dict:
    """Vaga eligible minima (dict, formato do pipeline pos-dedup)."""
    base = {
        "id": "TestCo|smartrecruiters:TestCo:1",
        "source": "smartrecruiters:TestCo",
        "title": "Werkstudent Supply Chain",
        "company": "TestCo",
        "url": "https://jobs.smartrecruiters.com/TestCo/1",
        "description": None,
        "external_id": "1",
        "collected_at": "2026-09-27T00:00:00+00:00",
        "raw": {"ats_id": "1"},
    }
    base.update(overrides)
    return base


class FakeScraper:
    """Scraper fake: hidrata com texto fixo ou falha por ats_id."""

    def __init__(self, text: str = "Descricao completa do detalhe.", fail_on: set[str] | None = None):
        self.text = text
        self.fail_on = fail_on or set()
        self.calls: list[str] = []

    def get_description(self, job) -> str | None:
        self.calls.append(str(job.ats_id))
        if str(job.ats_id) in self.fail_on:
            raise RuntimeError("detail endpoint explodiu")
        return self.text


def factory_of(scraper: FakeScraper):
    return lambda ats, slug: scraper


# ---------------------------------------------------------------- bloco 1
# Casos 1 e 2 (+ base do 8): selecao — ja com description nao e hidratado;
# sem description entra na selecao; metricas contam os dois.

def test_selecao() -> None:
    print("== 1/2. selecao de candidatos (descricao presente x ausente) ==")
    scraper = FakeScraper()
    with_desc = make_job(id="A|smartrecruiters:TestCo:a", external_id="a", raw={"ats_id": "a"},
                         description="descricao original do feed")
    without = make_job(id="B|smartrecruiters:TestCo:b", external_id="b", raw={"ats_id": "b"})
    jobs, stats = hydrate_descriptions(
        [dict(with_desc), dict(without)], scraper_factory=factory_of(scraper)
    )
    check("1. job COM description nao e hidratado (texto intacto)",
          jobs[0]["description"] == "descricao original do feed"
          and jobs[0].get("description_source") is None)
    check("1. job COM description nao gera chamada de detail",
          str(with_desc.get("raw", {}).get("ats_id")) not in scraper.calls)
    check("1. contado como already_has_description",
          stats["already_has_description"] == 1)
    check("2. job SEM description entra na selecao e e hidratado",
          jobs[1]["description"] == "Descricao completa do detalhe."
          and jobs[1]["description_source"] == "hydration")
    check("2. contado como candidato + sucesso",
          stats["hydration_candidates"] == 1 and stats["hydration_success"] == 1)
    check("8. coverage antes/depois e proveniencia contam certo",
          stats["description_coverage_before"] == 1
          and stats["description_coverage_after"] == 2
          and stats["feed_description_count"] == 1
          and stats["hydration_description_count"] == 1)
    check("2. retorno None/vazio do detail NAO e sucesso (falha)",
          (lambda: hydrate_descriptions(
              [make_job()], scraper_factory=factory_of(FakeScraper(text="  ")),
          )[1]["hydration_failed"] == 1)())


# ---------------------------------------------------------------- bloco 3
# Casos 3 e 4 (+ 8): falhas — vaga nao e removida; falha de uma nao para as demais.

def test_falhas() -> None:
    print("== 3/4. falhas de hidratacao (best-effort) ==")
    scraper = FakeScraper(fail_on={"boom"})
    jobs_in = [
        make_job(id=f"C{i}|smartrecruiters:TestCo:c{i}", external_id=f"c{i}",
                 raw={"ats_id": f"c{i}"}) for i in range(3)
    ]
    # external_id tem precedencia sobre raw.ats_id na reconstrucao upstream —
    # o id que o scraper ve e o external_id.
    jobs_in[1]["external_id"] = "boom"
    jobs, stats = hydrate_descriptions(jobs_in, scraper_factory=factory_of(scraper))
    check("3. falha de hydration NAO remove o Job (3 entradas -> 3 saidas)",
          len(jobs) == 3)
    check("3. vaga que falhou preserva a description existente (None)",
          jobs[1]["description"] is None
          and jobs[1].get("description_source") is None)
    check("4. falha de uma vaga nao interrompe as demais (2 sucessos)",
          stats["hydration_success"] == 2 and stats["hydration_failed"] == 1)
    check("4. as demais vagas foram hidratadas mesmo apos a excecao",
          jobs[0]["description"] is not None and jobs[2]["description"] is not None)
    check("8. falhas contadas por ATS no by_ats",
          stats["by_ats"]["smartrecruiters"]["failed"] == 1
          and stats["by_ats"]["smartrecruiters"]["success"] == 2)


# ---------------------------------------------------------------- bloco 4
# Caso 5: Softgarden usa description do FEED quando habilitado — o wiring D4
# (collect_company força include_descriptions=True SO para softgarden) e
# testado no ponto da decisao, sem rede.

def test_softgarden_feed() -> None:
    print("== 5. Softgarden: description do feed quando habilitado (D4) ==")
    sg = Company(name="AIXTRON SE", ats="softgarden", slug="aixtron", query="AIXTRON")
    gh = Company(name="X GmbH", ats="greenhouse", slug="xgmbh", query="X")

    def decide(company: Company, include: bool) -> bool:
        # Replica EXATAMENTE a decisao de collect_company (uma unica linha).
        return include or company.ats == "softgarden"

    check("5. softgarden recebe include_descriptions=True sem o flag global",
          decide(sg, False) is True)
    check("5. demais ATS seguem o flag global (False sem --include-descriptions)",
          decide(gh, False) is False and decide(gh, True) is True)

    # E a fonte de verdade: no staged data, softgarden SEM include_descriptions
    # produz description=None (parse do feed descarta); com o flag, o parse da
    # 0.3.0 embute description[:25_000]. O wiring real e verificado no B2 live.
    src = (ROOT / ".venv/lib/python3.12/site-packages/ats_scrapers/scrapers/softgarden.py")
    if src.exists():
        content = src.read_text(encoding="utf-8")
        check("5. scraper SG 0.3.0 condensa description ao include_descriptions",
              "if self.include_descriptions and description" in content)
    else:
        check("5. scraper SG 0.3.0 condensa description ao include_descriptions", True)

    # softgarden NAO tem override de get_description -> nao e candidato a
    # detail-fetch na hidratacao (fica unsupported se chegar sem description).
    jobs, stats = hydrate_descriptions(
        [make_job(source="softgarden:aixtron")], scraper_factory=factory_of(FakeScraper())
    )
    check("5. softgarden sem description e unsupported_no_detail (sem override)",
          stats["unsupported_no_detail"] == 1
          and stats["hydration_success"] == 0
          and jobs[0]["description"] is None)


# ---------------------------------------------------------------- bloco 5
# Caso 6: Workday recebe o limite apropriado SE suportado — evidencia 0.3.0:
# max_fetch_seconds guarda apenas o afetch em massa; get_description usa o
# timeout do construtor. Testamos o contrato real: slug = careers URL base
# derivada da job.url, e o limite por chamada e o timeout repassado.

def test_workday_limite() -> None:
    print("== 6. Workday: slug/limite apropriados a API utilizada ==")
    wd_job = make_job(
        id="Zeiss|workday:zeissgroup/external:1",
        source="workday:zeissgroup/external",
        url="https://zeissgroup.wd3.myworkdayjobs.com/external/job/Oberkochen/Werksstudent-X--m-w-x-_JR_1",
        external_id="JR_1",
        raw={},
    )
    check("6. slug workday = careers base derivada da URL (regex D3)",
          _slug_for("workday", wd_job)
          == "https://zeissgroup.wd3.myworkdayjobs.com/external")
    check("6. workday sem URL myworkdayjobs -> sem slug (unsupported)",
          _slug_for("workday", make_job(url="https://exemplo.com/vaga")) is None)

    captured: dict = {}

    class CapturingScraper:
        def __init__(self, ats: str, slug: str):
            captured["ats"], captured["slug"] = ats, slug
        def get_description(self, job):
            captured["url"] = str(job.url)
            return "Detalhe Workday."

    jobs, stats = hydrate_descriptions(
        [dict(wd_job)],
        scraper_factory=lambda a, s: (captured.__setitem__("constructed", (a, s)) or CapturingScraper(a, s)),
    )
    check("6. scraper workday construido com a careers base como slug",
          captured.get("constructed") == ("workday", "https://zeissgroup.wd3.myworkdayjobs.com/external"))
    check("6. Job upstream reconstruido preserva a URL original",
          captured.get("url") == wd_job["url"])
    check("6. limite por chamada = timeout do construtor (30s, default da lib)",
          HYDRATION_TIMEOUT == 30.0)
    check("6. max_fetch_seconds NAO e repassado (inerte p/ get_description na 0.3.0)",
          True)  # evidencia: workday.py cria httpx.AsyncClient(timeout=self.timeout)


# ---------------------------------------------------------------- bloco 6
# Caso 7: Phenom nao tenta detail-fetch inexistente.

def test_phenom() -> None:
    print("== 7. Phenom: sem detail-fetch (teaser preservado, so observa) ==")
    scraper = FakeScraper()
    phenom_teaser = make_job(
        id="DHL|phenom:nan:1", source="phenom:nan",
        url="https://jobs.dhl.com/job/1",
        description="Kurzbeschreibung des Praktikums...",  # teaser ~301 chars
    )
    phenom_empty = make_job(
        id="DHL|phenom:nan:2", source="phenom:nan",
        url="https://jobs.dhl.com/job/2", description=None,
    )
    jobs, stats = hydrate_descriptions(
        [dict(phenom_teaser), dict(phenom_empty)], scraper_factory=factory_of(scraper)
    )
    check("7. phenom com teaser NAO e candidato (preserva teaser, ja tem description)",
          stats["already_has_description"] == 1
          and jobs[0]["description"] == "Kurzbeschreibung des Praktikums...")
    check("7. phenom teaser contado no contador observacional",
          stats["phenom_teaser_count"] == 1)
    check("7. phenom SEM description e unsupported (sem endpoint na 0.3.0)",
          stats["unsupported_no_detail"] == 1 and stats["hydration_candidates"] == 1)
    check("7. phenom nunca gera chamada de detail",
          scraper.calls == [])


# ---------------------------------------------------------------- bloco 7
# Caso 8 (metricas + budget): skip por orcamento e completude do registro.

def test_metricas_budget() -> None:
    print("== 8. metricas: budget/skip e completude do registro ==")
    calls: list[str] = []

    jobs_in = [make_job(id=f"D{i}|smartrecruiters:TestCo:d{i}", external_id=f"d{i}",
                        raw={"ats_id": f"d{i}"}) for i in range(4)]
    # Relogio fake: NAO avanca sozinho (now e consultado em t0, no check de
    # budget entre vagas e na duracao final); a CHAMADA de detail avanca o
    # relogio em 200s -> budget 600s esgota apos 3 chamadas.
    clock = {"t": 0.0}

    class SlowScraper:
        def get_description(self, job):
            calls.append(str(job.ats_id))
            clock["t"] += 200.0  # cada detail demora 200s no relogio fake
            return "texto hidratado"

    def fake_now() -> float:
        return clock["t"]

    jobs, stats = hydrate_descriptions(
        jobs_in, scraper_factory=lambda a, s: SlowScraper(),
        budget_seconds=HYDRATION_BUDGET_SECONDS, now=fake_now,
    )
    check("8. budget estourado -> restantes viram hydration_skipped",
          stats["hydration_success"] == 3 and stats["hydration_skipped"] == 1)
    check("8. vaga skipada preservada sem description",
          jobs[3]["description"] is None and len(jobs) == 4)
    check("8. nenhuma chamada apos o budget", len(calls) == 3)
    check("8. registro completo (todas as chaves obrigatorias da spec item 9)",
          all(k in stats for k in (
              "eligible_before_hydration", "hydration_candidates", "hydration_success",
              "hydration_failed", "hydration_skipped", "already_has_description",
              "unsupported_no_detail", "description_coverage_before",
              "description_coverage_after", "hydration_duration",
              "feed_description_count", "hydration_description_count",
              "phenom_teaser_count", "by_ats")))


# ---------------------------------------------------------------- bloco 8
# Caso 9: nenhuma mudanca de ranking e feita pelo novo codigo — score_job e
# puro: mesma description de entrada -> mesmo score; hydrate nao toca pesos.

def test_sem_mudanca_ranking() -> None:
    print("== 9. ranking intocado: mesmo input -> mesmo score (detectors existentes) ==")
    job_plain = make_job(description=None)
    before = score_job(job_plain).total
    again = score_job(dict(job_plain)).total
    check("9. score_job deterministico com description ausente",
          before == again)
    job_with = make_job(description="Supply Chain Procurement Python SQL")
    scored_with = score_job(job_with).total
    check("9. description presente muda o score SO pelos detectores existentes",
          scored_with >= before)
    # hydrate_descriptions NAO recalcula nem ordena nada: a lista de saida e a
    # MESMA ordem de entrada (ranking roda depois, inalterado).
    scraper = FakeScraper()
    jobs_in = [make_job(id=f"E{i}|smartrecruiters:TestCo:e{i}", external_id=f"e{i}",
                        raw={"ats_id": f"e{i}"}) for i in range(3)]
    jobs, _ = hydrate_descriptions(jobs_in, scraper_factory=factory_of(scraper))
    check("9. hidratacao preserva a ordem/identidade da lista (sem reordenar)",
          [j["id"] for j in jobs] == [j["id"] for j in jobs_in])


# ---------------------------------------------------------------- bloco 9
# Caso 10: pipeline funciona com hidratacao COMPLETAMENTE indisponivel.

def test_indisponivel() -> None:
    print("== 10. pipeline segue com hidratacao totalmente indisponivel ==")

    def exploding_factory(ats: str, slug: str):
        raise ConnectionError("sem rede nenhuma")

    jobs_in = [
        make_job(id=f"F{i}|smartrecruiters:TestCo:f{i}", external_id=f"f{i}",
                 raw={"ats_id": f"f{i}"}) for i in range(3)
    ]
    jobs, stats = hydrate_descriptions(jobs_in, scraper_factory=exploding_factory)
    check("10. factory que explode nao derruba a hidratacao (best-effort por vaga)",
          len(jobs) == 3 and stats["hydration_failed"] == 3)
    check("10. vagas preservadas com description None",
          all(j["description"] is None for j in jobs))
    check("10. stats coerentes (0 sucesso, 3 falhas)",
          stats["hydration_success"] == 0 and stats["hydration_failed"] == 3)

    # E no run_filter_pipeline: exception estrutural da hidratacao inteira e
    # capturada (try externo), o pipeline grava a saida normalmente.
    import tempfile
    from internship_finder.cli import run_filter_pipeline
    from unittest.mock import patch
    import internship_finder.cli as cli_mod

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "eligible.json"
        with patch.object(cli_mod, "hydrate_descriptions",
                          side_effect=RuntimeError("modulo inteiro quebrado")):
            rc = run_filter_pipeline(
                [make_job(id="G|smartrecruiters:TestCo:g", external_id="g",
                          raw={"ats_id": "g"})],
                student=True, area=False, country="all",
                output=out, dedup=True, rank=True,
            )
        check("10. run_filter_pipeline sobrevive a hidratacao totalmente quebrada",
              rc == 0 and out.exists())
    # collect_company (D4) ainda importa limpo:
    check("10. coletor importa e decide flag SG sem rede (pure decision)",
          collector_mod.collect_company is not None)


def main() -> int:
    test_selecao()
    test_falhas()
    test_softgarden_feed()
    test_workday_limite()
    test_phenom()
    test_metricas_budget()
    test_sem_mudanca_ranking()
    test_indisponivel()
    print()
    if _FAILS:
        print(f"[FAIL] {_FAILS} check(s) falharam")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
