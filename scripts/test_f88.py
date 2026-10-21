#!/usr/bin/env python3
"""F88 — top-up de frescor: contrato da onda de 18 tenants (offline).

O QUE A F88 FEZ (contexto do contrato): as 44 empresas do watchlist F13 sem
tenant no registry (de 67) dependiam SÓ do dataset upstream (~18,5h stale,
efêmero, sem lifecycle — invariante F3 §7.8). A onda F88 promoveu 18 delas a
coleta direta same-day via tenant no SEED, descobertas com o mecanismo F76.1
(discovery_rules) + find_company (inventário upstream, match EXATO) e
validadas AO VIVO com o scraper REAL (validate_slug/validate_candidate):
vereditos com job_count/TTFB/tamanho no relatório da fase
(~/.hermes/handoff/f88-topup-tenants/). Rejeições medidas e documentadas:
REWE (sitemal.xml 114 MB, GET cru 342 s — patologia Lidl-like, critério de
rejeição da spec), Airbus workday ag/airbus (2.964 vagas, 0 elegíveis —
locations sem país parseável), falsos positivos de substring do inventário
(ADAC→Cadac, MTU→East Harlem Tutorial Program, REWE→CoreWeave) e as 2 já
presentes no SEED (Zeiss Group, bahagag/BAUHAUS — precedente F32: não
duplica).

A/B DE DEDUP (insumo do dono, medido no clone com a cadeia REAL de produção:
collect_company → select_eligible(country=de,lu,nl,fi,be) → dedup chain):
para KPMG/AGCO/aumovio o estágio URL do dedup removeu 100% dos pares
tenant×dataset (9/9, 9/9, 2/2) — união 19→10, 18→9, 12→10 — ZERO duplicação
pós-filtro. O precedente Amazon (amazon_jobs 81 + sf_dataset:amazon 7
coexistem) NÃO se repete aqui porque as URLs são idênticas entre o feed do
tenant e a fatia do dataset (mesmo ATS); no caso Amazon os espaços de URL
são distintos. O grupo E trava esse mecanismo.

Este teste é 100% OFFLINE: o scraper_factory/outcome_of do validate_slug são
mockados (injeção prevista pela F76.1), o CompanyCollector roda contra um
inventário fake (pandas) via monkeypatch do find_company upstream, e as 4
armadilhas de conector do clean-room (§2.4) são fixtures:

1. Workday ``posted`` boolean — datas reais em startDate/endDate: o
   adapter não quebra (posted_at=None, datas preservadas no raw);
2. subdomínios wd3 (Shell) — resolve_careers_url reconhece wd1/wd3/wd501 e
   devolve a URL COMPLETA como slug (instância wdN é load-bearing);
3. SmartRecruiters ignora filtro de país (vaga Wien/AT em query de=DE):
   o estágio país do select_eligible EXCLUI (mitigação downstream
   verificada por fixture, não assumida);
4. Amazon ISO3 (country_code alpha-3 "DEU"): o conector amazon_jobs
   normaliza (_amazon_iso DEU→de); o caminho GENÉRICO sem evidência de
   país na location fica country=None e o filtro EXCLUI (conservador:
   nunca admite país errado).

Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
Uso:  .venv/bin/python scripts/test_f88.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from types import SimpleNamespace  # noqa: E402

from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.collectors import company as company_mod  # noqa: E402
from internship_finder.collectors.ats_scraper import scraper_slug  # noqa: E402
from internship_finder.cross_source_dedup import deduplicate_cross_source  # noqa: E402
from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.discovery_rules import (  # noqa: E402
    Invalid,
    classify,
    registry_ats,
    tenant_key,
    validate_slug,
)
from internship_finder.eu_ranking import (  # noqa: E402
    WEIGHT_WATCHLIST_INTEREST,
    watchlist_interest,
)
from internship_finder.filters import select_eligible  # noqa: E402
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.registry import SEED  # noqa: E402
from internship_finder.research_sources import _amazon_iso  # noqa: E402

from ats_scrapers import resolve_careers_url  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

# ---------------------------------------------------------------------------
# Evidência validada AO VIVO (21/10, scraper real; job_count/TTFB no relatório
# da fase): name canônico de coleta (consulta real do --companies — match
# EXATO no inventário upstream) → (ats, slug do tenant). O slug gravado no
# SEED é a IDENTIDADE (Company.source); para os URL_SLUG_ATS (successfactors,
# workday, phenom, taleo, icims) o input efetivo do scraper é a URL de
# careers da linha do inventário, não o slug curto.
# ---------------------------------------------------------------------------
F88_VALIDATED: dict[str, tuple[str, str]] = {
    "KPMG | DE - KPMG Global": ("successfactors", "jobs"),
    "Vetter": ("successfactors", "careers"),
    "AGCO": ("successfactors", "careers"),
    "mllerservi": ("successfactors", "mllerservi"),
    "Deutsche Börse AG": ("successfactors", "career"),
    "Witglobal": ("successfactors", "wrthitinteP2"),
    "Levio": ("greenhouse", "levio"),
    "Indie Campers": ("greenhouse", "indiecampers"),
    "Vitesco": ("successfactors", "VitescoProd"),
    "Marquardt Group": (
        "cornerstone",
        "https://marquardt-group.csod.com/ux/ats/careersite/5/home?c=marquardt-group",
    ),
    "Kraft Heinz": ("eightfold", "kraftheinz"),
    "aumovio": ("smartrecruiters", "aumovio"),
    "Vodafone": ("successfactors", "vodafone"),
    "Vanderlande": ("workday", "vanderlande/careers"),
    "Stryker": ("workday", "stryker/strykercareers"),
    "Endress+Hauser": ("successfactors", "careers"),
    "Pirelli": ("successfactors", "jobs"),
    "GALERIA": ("cornerstone", "galeria"),
}

# Candidatas DESCARTADAS com causa medida — NÃO podem estar no SEED.
F88_REJECTED_NAMES = {
    # Lidl-like: sitemal.xml 114 MB, GET cru 342 s (além do teto de tenant).
    "Karriere & Jobs bei der REWE Group",
    # 2.964 vagas coletadas, 0 elegíveis (país não parseável, country=None).
    "Ag",
    # Falsos positivos de substring do inventário (match EXATO os filtra).
    "Cadac",
    "East Harlem Tutorial Program",
    "CoreWeave",
    "CoreWeave Europe",
    "Carewell",
    "House of Commons (Canada) / Chambre des communes (Canada)",
    "HanseVision GmbH - Bechtle Group",
}
F88_REJECTED_TENANTS = {
    # Airbus workday: rejeitada no A/B (0 elegíveis pós-filtro de país).
    "workday:ag/airbus",
}

# Já presentes no SEED pré-F88 (precedente F32: validou ao vivo, NÃO duplica).
F88_ALREADY_PRESENT_TENANTS = {
    "successfactors:bahagag",  # BAUHAUS — bewerben.bauhaus.info
    "workday:zeissgroup/external",  # Zeiss Group
}


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name if not detail else f"{name} — {detail}")


def section(name: str) -> None:
    print(f"\n--- {name} ---")


# ---------------------------------------------------------------------------
# [A] SEED íntegro — a onda F88 entra conforme, sem duplicatas
# ---------------------------------------------------------------------------

def group_a() -> None:
    section("[A] SEED íntegro — onda F88 (formato, duplicatas, contagem)")

    src = (ROOT / "src" / "internship_finder" / "registry.py").read_text(
        encoding="utf-8")
    m = re.search(r"\+ (\d+) da onda F88", src)
    check("A1. marcador da onda F88 documentado no registry.py", m is not None,
          f"marker = {m.group(0) if m else 'AUSENTE'}")
    wave_n = int(m.group(1)) if m else -1

    by_name = {e.name: e for e in SEED}
    present = [n for n in F88_VALIDATED if n in by_name]
    check("A2. todas as validadas ao vivo estão no SEED",
          len(present) == len(F88_VALIDATED),
          f"{len(present)}/{len(F88_VALIDATED)}")
    check("A3. marcador da onda == entradas da onda (recontagem, nunca hardcode)",
          wave_n == len(F88_VALIDATED), f"marker={wave_n} vs tabela={len(F88_VALIDATED)}")

    ok_shape = True
    bad: list[str] = []
    for name, (ats, slug) in F88_VALIDATED.items():
        e = by_name.get(name)
        if e is None:
            bad.append(f"{name}: ausente")
            ok_shape = False
            continue
        if not e.enabled:
            bad.append(f"{name}: enabled=False")
            ok_shape = False
        if e.ats != ats:
            bad.append(f"{name}: ats={e.ats!r} != {ats!r}")
            ok_shape = False
        if e.ats not in registry_ats():
            bad.append(f"{name}: ats fora do universo do registry")
            ok_shape = False
        if e.tenant != f"{ats}:{slug}":
            bad.append(f"{name}: tenant={e.tenant!r} != {ats}:{slug!r}")
            ok_shape = False
    check("A4. formato por entrada (enabled, ats do universo, ats:slug exato "
          "da validação ao vivo)", ok_shape, "; ".join(bad[:4]) if bad else
          f"{len(F88_VALIDATED)} conformes")

    names = [e.name for e in SEED]
    dups = {n for n in names if names.count(n) > 1}
    check("A5. nenhum name duplicado no SEED inteiro", not dups, f"{sorted(dups)}")
    # Para URL_SLUG_ATS (successfactors/workday/phenom/taleo/icims) o slug
    # curto é NORMA compartilhada (o host da linha do inventário disambigua:
    # "successfactors:jobs" pré-F88 já serve 16 empresas) — f71 §[3] o lista
    # como informativo. O contrato real: a onda não introduz BOARD duplicado
    # para ATS cujo slug É a identidade do tenant.
    URL_SLUG_ATS = {"successfactors", "workday", "phenom", "taleo", "icims"}
    identity = [(e.ats, e.tenant) for e in SEED
                if e.ats not in URL_SLUG_ATS and e.tenant]
    idups = {f"{a}:{t}" for a, t in identity if identity.count((a, t)) > 1}
    check("A6. nenhum board duplicado p/ ATS de slug-identidade "
          "(greenhouse/smartrecruiters/eightfold/cornerstone...); slug "
          "compartilhado de URL_SLUG_ATS é norma documentada", not idups,
          f"{sorted(idups)}")

    header = re.search(r"Seed: (\d+) empresas operacionais", src)
    check("A7. header do seed == len(SEED) (contrato F73 viva aqui também)",
          header is not None and int(header.group(1)) == len(SEED),
          f"header={header.group(1) if header else '?'} vs len(SEED)={len(SEED)}")


# ---------------------------------------------------------------------------
# [B] validate_slug com scraper_factory mockado — vereditos por classe
# ---------------------------------------------------------------------------

def _factory_call_counter():
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return SimpleNamespace(company_name="FakeCo")

    return factory, calls


def group_b() -> None:
    section("[B] validate_slug mockado — veredito por classe (taxonomia Invalid)")

    def run(ats, slug, status, job_count, error=""):
        return validate_slug(
            ats, slug,
            scraper_factory=lambda: SimpleNamespace(company_name="FakeCo"),
            outcome_of=lambda scraper: (status, job_count, error),
        )

    v = run("successfactors", "https://jobs.kpmg.de", 200, 364)
    check("B1. 200 + vagas vivas → VALID (razão cita o sinal)",
          v.valid and "http_200" in v.reason and "364" in v.reason,
          f"reason={v.reason!r}")

    v = run("smartrecruiters", "levio", 200, 0)
    check("B2. 200 sem vaga viva → branded_shell_no_jobs",
          (not v.valid) and v.reason == Invalid.BRANDED_SHELL, v.reason)

    v = run("greenhouse", "carewell", 200, 0, error="MalformedJSONError: WAF")
    check("B3. 200-falso (corpo que não parseia) → branded_shell_no_jobs",
          (not v.valid) and v.reason == Invalid.BRANDED_SHELL, v.reason)

    v = run("greenhouse", "carewell", 404, 0)
    check("B4. 404 limpo → http_not_found",
          (not v.valid) and v.reason == Invalid.HTTP_NOT_FOUND, v.reason)

    v = run("greenhouse", "exemplo", 404, 12)
    check("B5. 404 com API viva → stale_404_live_api (edge documentado Gem; "
          "classe vale p/ todo ATS do universo)",
          (not v.valid) and v.reason == Invalid.STALE_404_LIVE_API, v.reason)

    v = run("successfactors", "https://karriere.rewe-group.com", 0, 0,
            error="TimeoutError")
    check("B6. sem HTTP confiável (rede/timeout) → unreachable",
          (not v.valid) and v.reason == Invalid.UNREACHABLE, v.reason)

    v = run("eightfold", "kraftheinz", 403, 0)
    check("B7. status de bloqueio → http_error",
          (not v.valid) and v.reason == Invalid.HTTP_ERROR, v.reason)

    factory, calls = _factory_call_counter()
    v = validate_slug("workday", "kpmg-demo-board",
                       scraper_factory=factory,
                       outcome_of=lambda s: (200, 10, ""))
    check("B8. slug demo/sandbox → demo_sandbox_tenant (screening ANTES da "
          "rede — factory não chamada)",
          (not v.valid) and v.reason == Invalid.DEMO_TENANT and calls["n"] == 0,
          f"reason={v.reason!r}, factory_calls={calls['n']}")

    v = validate_slug("lever", "acme", scraper_factory=lambda: None,
                      outcome_of=lambda s: (200, 5, ""))
    check("B9. ATS fora do universo do registry → unknown_ats",
          (not v.valid) and v.reason == Invalid.UNKNOWN_ATS, v.reason)

    v = run("successfactors", "https://jobs.kpmg.de", 200, 364)
    ev = v.evidence
    check("B10. evidência carrega (tenant_key, status, job_count, endpoint)",
          ev.get("tenant_key") == tenant_key("successfactors",
                                             "https://jobs.kpmg.de")
          and ev.get("status") == 200 and ev.get("job_count") == 364
          and "sitemal.xml" in ev.get("endpoint", ""),
          f"tenant_key={ev.get('tenant_key')!r}")

    # Classificador puro (mesmas classes, sem scraper): contrato da ordem
    # dos critérios (doc upstream): 404+vivas > 404, 200-falso > 200-vazio.
    c = classify("workday", status=200, job_count=0, error="x")
    check("B11. classify puro: 200 com erro → branded_shell (200-falso "
          "também é shell)", (not c.valid) and c.reason == Invalid.BRANDED_SHELL)


# ---------------------------------------------------------------------------
# [C] As 4 armadilhas de conector do clean-room (§2.4) — fixtures
# ---------------------------------------------------------------------------

def _job_dict(title, url, location, source, company, external_id, **extra):
    d = {
        "id": f"{company}|{source}:{external_id}",
        "source": source,
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "external_id": external_id,
    }
    d.update(extra)
    return d


def group_c() -> None:
    section("[C] 4 armadilhas de conector (fixtures do clean-room §2.4)")

    # (1) Workday `posted` boolean — datas reais em startDate/endDate.
    wd = Company(name="Stryker", ats="workday", slug="stryker/strykercareers",
                 url="https://stryker.wd1.myworkdayjobs.com/strykercareers")
    trap = {
        "title": "Werkstudent Supply Chain (m/w/d)",
        "url": "https://stryker.wd1.myworkdayjobs.com/strykercareers/job/1",
        "location": "Kiel, Germany",
        "external_id": "R-1",
        # A armadilha: booleano onde o pipeline espera data.
        "posted": True,
        "startDate": "2026-09-01T00:00:00.000Z",
        "endDate": "2026-12-31T23:59:59.000Z",
    }
    try:
        job = AtsJobAdapter().to_job(trap, wd)
        ok_no_break = True
        err = ""
    except Exception as exc:  # noqa: BLE001
        job = None
        ok_no_break = False
        err = f"{type(exc).__name__}: {exc}"
    check("C1a. Workday posted=boolean NÃO quebra o adapter", ok_no_break, err)
    check("C1b. posted_at vira None (booleano não é data — nunca fabrica)",
          ok_no_break and job is not None and job.posted_at is None,
          f"posted_at={getattr(job, 'posted_at', 'n/a')!r}")
    check("C1c. datas reais preservadas no raw (startDate/endDate)",
          ok_no_break and job is not None
          and (job.raw or {}).get("startDate", "").startswith("2026-09-01"))
    twin = dict(trap, posted=None, postedAt="2026-10-01T00:00:00Z")
    job2 = AtsJobAdapter().to_job(twin, wd)
    check("C1d. twin com postedAt string real parseia normalmente",
          job2.posted_at is not None and job2.posted_at.year == 2026)

    # (2) SmartRecruiters ignora filtro de país — vaga Wien/AT numa query
    # country=de: mitigação DOWNSTREAM (estágio país), verificada por fixture.
    sr = Company(name="aumovio", ats="smartrecruiters", slug="aumovio",
                 url="https://careers.smartrecruiters.com/aumovio")
    at_job = AtsJobAdapter().to_job({
        "title": "Praktikum Supply Chain Management (m/w/d)",
        "url": "https://careers.smartrecruiters.com/aumovio/1",
        "location": "Wien, Austria",  # a armadilha: vaga AT na query de=de
        "external_id": "1",
    }, sr)
    de_job = AtsJobAdapter().to_job({
        "title": "Praktikum Supply Chain Management (m/w/d)",
        "url": "https://careers.smartrecruiters/aumovio/2",
        "location": "Hamburg, Germany",
        "external_id": "2",
    }, sr)
    check("C2a. adapter infere country 'at' para Wien (armadilha exposta)",
          at_job.country == "at", f"country={at_job.country!r}")
    sel, counts = select_eligible(
        [at_job.to_dict(), de_job.to_dict()],
        student=True, area=True, country="de,lu,nl,fi,be", applicability=True)
    sel_ids = {j.get("id") for j in sel}
    check("C2b. estágio país EXCLUI a vaga AT (mitigação downstream REAL)",
          at_job.id not in sel_ids and de_job.id in sel_ids,
          f"pais={counts.get('pais')} kept={len(sel)}")
    check("C2c. contagem do estágio país coerente (2→1)",
          counts.get("pais") == 1, f"counts={ {k: counts.get(k) for k in ('total','tipo','area','pais')} }")

    # (3) Subdomínios wd3 (Shell) — a instância wdN é load-bearing: o
    # resolver reconhece QUALQUER wdN e devolve a URL COMPLETA como slug.
    resolved_wd3 = resolve_careers_url(
        "https://shell.wd3.myworkdayjobs.com/ShellCareers")
    check("C3a. resolve_careers_url reconhece wd3 → workday",
          resolved_wd3 is not None
          and resolved_wd3.ats.value == "workday"
          and resolved_wd3.slug ==
          "https://shell.wd3.myworkdayjobs.com/ShellCareers",
          f"resolved={resolved_wd3!r}")
    resolved_vdl = resolve_careers_url(
        "https://vanderlande.wd3.myworkdayjobs.com/careers")
    ok_all = all(
        resolve_careers_url(u) is not None
        and resolve_careers_url(u).ats.value == "workday"
        and resolve_careers_url(u).slug == u
        for u in (
            "https://stryker.wd1.myworkdayjobs.com/strykercareers",
            "https://vanderlande.wd3.myworkdayjobs.com/careers",
            "https://google.wd501.myworkdayjobs.com/gocjobs",
        )
    )
    check("C3b. wd1/wd3/wd501 uniformes (URL completa como slug)", ok_all)
    check("C3c. scraper_slug usa a URL do board para URL_SLUG_ATS "
          "(coleta da onda: Stryker/Vanderlande)",
          scraper_slug(Company(name="Stryker", ats="workday",
                              slug="stryker/strykercareers",
                              url="https://stryker.wd1.myworkdayjobs.com/strykercareers"))
          == "https://stryker.wd1.myworkdayjobs.com/strykercareers")

    # (4) Amazon ISO3 — country_code alpha-3 do board ("DEU"). Defesa em
    # CAMADAS: (i) o conector amazon_jobs normaliza; (ii) a tabela de
    # cidades DE conhecidas do resolver preenche 'de' quando a cidade é
    # conhecida; (iii) sem evidência nenhuma, country=None e o filtro
    # EXCLUI (fail-safe — nunca admite país errado).
    check("C4a. conector amazon_jobs normaliza DEU→de (mitigação da fonte)",
          _amazon_iso("DEU") == "de" and _amazon_iso("USA") == "us"
          and _amazon_iso(None) is None,
          f"DEU={_amazon_iso('DEU')!r}")
    base_iso3 = {
        "title": "Praktikum Supply Chain Management (m/w/d)",
        "url": "https://example.invalid/iso3",
        "external_id": "iso3",
        "country_iso": "DEU",  # a armadilha: alpha-3 não é alpha-2
    }
    city = AtsJobAdapter().to_job(
        dict(base_iso3, location="München"),
        Company(name="Acme", ats="greenhouse", slug="acme"))
    check("C4b. camada 2: cidade DE conhecida resgata o ISO3 cru "
          "(München → de pela tabela do resolver)", city.country == "de",
          f"country={city.country!r}")
    gen = AtsJobAdapter().to_job(
        dict(base_iso3, location="Musterstadt", external_id="iso3b"),
        Company(name="Acme", ats="greenhouse", slug="acme"))
    check("C4c. camada 3: localização SEM evidência → country=None "
          "(nunca admite país errado)", gen.country is None,
          f"country={gen.country!r}")
    sel_iso, _ = select_eligible(
        [gen.to_dict()], student=True, area=True,
        country="de,lu,nl,fi,be", applicability=True)
    check("C4d. filtro de país EXCLUI a vaga ISO3 sem evidência (fail-safe)",
          len(sel_iso) == 0)


# ---------------------------------------------------------------------------
# [D] Counter-cases — sem tenant no universo → NÃO adiciona
# ---------------------------------------------------------------------------

def group_d() -> None:
    section("[D] counter-cases — descartadas não entram; regra EXATA filtra ruído")

    names = {e.name for e in SEED}
    tenants = {e.tenant for e in SEED}
    leaked = sorted(n for n in F88_REJECTED_NAMES if n in names)
    check("D1. nenhuma descartada (falsos positivos/rejeitadas) virou entrada",
          not leaked, f"{leaked}")
    leaked_t = sorted(t for t in F88_REJECTED_TENANTS if t in tenants)
    check("D2. tenants rejeitados ausentes (Airbus workday, REWE Lidl-like)",
          not leaked_t, f"{leaked_t}")

    for t in F88_ALREADY_PRESENT_TENANTS:
        n = sum(1 for e in SEED if e.tenant == t)
        check(f"D3. já-presente NÃO duplicado: {t} (precedente F32)",
              n == 1, f"entradas={n}")

    # O radar/ranking F13 casa pelo job.company (nome de feed), não pelo nome
    # do SEED: os jobs do tenant KPMG vêm com company "KPMG International
    # Cooperative" — a watchlist continua acertando pós-merge (o residual
    # "KPMG | DE - KPMG Global"×"KPMG International Cooperative" é só do
    # métrico analítico SEED×watchlist, documentado no relatório).
    wi = watchlist_interest("KPMG International Cooperative")
    check("D4. radar F13 continua casando os jobs do tenant KPMG (company)",
          wi == WEIGHT_WATCHLIST_INTEREST, f"interest={wi!r}")

    # O match EXATO do CompanyCollector é o que descarta o ruído do
    # find_company upstream (substring): "ADAC" → Cadac NÃO é ADAC.
    import pandas as pd  # ats_scrapers depende de pandas (offline aqui)

    noise = pd.DataFrame([
        # ruído substring: "adac" está DENTRO de "cadac-group" (casefold)
        {"name": "Cadac", "slug": "cadac-group", "ats": "personio",
         "url": "https://cadac-group.jobs.personio.com"},
        {"name": "Everllence", "slug": "everllence", "ats": "greenhouse",
         "url": "https://job-boards.greenhouse.io/everllence"},
    ])
    real = company_mod.ats_find_company
    company_mod.ats_find_company = lambda q, limit=10: noise
    try:
        got_noise = company_mod.CompanyCollector().find_company("ADAC SE")
        got_empty = company_mod.CompanyCollector().find_company("TikTok")
    finally:
        company_mod.ats_find_company = real
    check("D5. ruído de substring NÃO vira candidato (match EXATO/token)",
          got_noise == [] and got_empty == [],
          f"ADAC SE -> {[c.name for c in got_noise]!r}")

    ok_rows = pd.DataFrame([
        {"name": "GALERIA", "slug": "galeria", "ats": "cornerstone",
         "url": "https://galeria.csod.com/ux/ats/careersite/1/home?c=galeria"},
    ])
    company_mod.ats_find_company = lambda q, limit=10: ok_rows
    try:
        got_ok = company_mod.CompanyCollector().find_company("GALERIA")
    finally:
        company_mod.ats_find_company = real
    check("D6. positive control: match exato resolve (a regra funciona)",
          len(got_ok) == 1 and got_ok[0].ats == "cornerstone"
          and got_ok[0].slug == "galeria",
          f"GALERIA -> {[(c.ats, c.slug) for c in got_ok]!r}")


# ---------------------------------------------------------------------------
# [E] Contrato do A/B de dedup — o par tenant×dataset é REMOVIDO
# ---------------------------------------------------------------------------

def group_e() -> None:
    section("[E] A/B dedup — pares tenant×dataset colidem no estágio URL")

    def pair(url, title, loc):
        tn = _job_dict(title, url, loc, "successfactors:jobs",
                       "KPMG International Cooperative", "J1")
        ds = _job_dict(title, url, loc, "sf_dataset:successfactors",
                       "KPMG International Cooperative", "J1")
        # ids distintos (fonte no prefixo) — como no eligible real
        tn["id"] = "KPMG International Cooperative|successfactors:jobs:J1"
        ds["id"] = "KPMG International Cooperative|sf_dataset:successfactors:J1"
        return tn, ds

    tn, ds = pair("https://jobs.kpmg.de/careers/123",
                  "Praktikum Data Science (w/m/d)", "Berlin, DE")
    out, stats, removed = deduplicate([tn, ds])
    check("E1. mesma URL (mesmo ATS) → 1 sobrevivente, stats no estágio url",
          len(out) == 1 and stats.get("url") == 1, f"stats={stats}")
    check("E2. o sobrevivente é o primeiro da união (cópia tenant, fresca — "
          "espelha o A/B: união 19→10)", out[0]["id"] == tn["id"],
          f"kept={out[0]['source']!r}")
    out2, stats2, _ = deduplicate_cross_source(out)
    check("E3. cross-source não re-remove o que já colidiu (A/B: cross vazio)",
          len(out2) == 1 and not stats2, f"stats2={stats2}")

    # Precedente Amazon: espaços de URL DISTINTOS não colidem no estágio URL
    # (amazon_jobs 81 + sf_dataset:amazon 7 coexistem no eligible).
    a1, a2 = (dict(tn, source="amazon_jobs",
                   url="https://www.amazon.jobs/en/jobs/1",
                   id="Amazon|amazon_jobs:1"),
              dict(tn, source="sf_dataset:amazon",
                   url="https://example.dataset/amazon/1",
                   id="Amazon|sf_dataset:amazon:1",
                   title="Intern Supply Chain"))
    out3, stats3, _ = deduplicate([a1, a2])
    check("E4. precedente Amazon preservado: URLs distintas NÃO colidem "
          "(coexistência documentada)", len(out3) == 2 and not stats3,
          f"out={len(out3)}, stats={stats3}")


def main() -> int:
    print("F88 — contrato da onda de tenants (offline)")
    group_a()
    group_b()
    group_c()
    group_d()
    group_e()
    print("\n" + "=" * 60)
    if FAILURES:
        print(f"FAIL — test_f88: {CHECKS} checks, {len(FAILURES)} falhas")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"OK — test_f88: {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
