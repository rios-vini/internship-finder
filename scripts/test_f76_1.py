"""F76.1 — DISCOVERY_RULES local: regras EXECUTAVEIS por ATS (test_f76_1).

Trava o mecanismo minimo local da fase — decisao do dono 20/10 (opcao B):
regras versionadas por ATS DO REGISTRY (14 medidos) + a API instalada
(resolve_careers_url/get_scraper_for_url) como maquina de validacao.

GRUPO A — cobertura regras x registry (DERIVADO do SEED, offline):
  A1. set(RULES) == registry_ats() — 14 == 14; coverage() vazio nos dois
      eixos (nenhum ATS do registry sem regra; nenhuma regra fora do
      universo).
  A2. rule_for e involutivo (chave == rule.ats) e todo ATS e conhecido da
      MAQUINA instalada (list_ats do pacote).
  A3. resolvable=True (11 ATS): resolve_careers_url(sample_url) -> (ats da
      regra, slug nao-vazio) e rule_for_url(sample_url) e a regra — o
      resolver OFFLINE do pacote concorda com a regra.
  A4. resolvable=False (3: successfactors/cornerstone/phenom): resolver
      retorna None (dominio custom) e url_as_slug=True — validacao manual
      exige slug-URL (validate_slug).
  A5. url_as_slug == (ats in URL_SLUG_ATS do coletor) para os 14 — a regra
      espelha o pipeline REAL de coleta (successfactors/workday/phenom).

GRUPO B — 1 regra EXECUTAVEL por ATS, contra o pacote INSTALADO (14x):
  B1. csv_columns == header medido do ats-companies/<ats>.csv @6b44a1b
      (12x name,slug,url; eightfold +domain; phenom 5 colunas url-first);
      success == ('http_200', 'jobs_live') universal.
  B2. tokens do canonical_endpoint presentes no FONTE do scraper instalado
      (a regra descreve o endpoint que a maquina consome de verdade).
  B3. token do jobs_signal presente no fonte instalado (sinal de vagas
      vivas existe no parser do pacote).
  B4. invalid: baseline do doc upstream (11 classes) completo; subclasses
      especificas (eightfold api_disabled; recruitee archived_board);
      invariante resolvable <-> UNRESOLVABLE_URL para os 14.

GRUPO C — classificador puro (executa os criterios da regra):
  C1. 200 + 42 jobs -> valid; reason cita o jobs_signal do ATS; evidence
      carrega endpoint/status/job_count/tenant_key.
  C2. 200 + 0 jobs -> branded_shell_no_jobs (shell sem dado de vaga).
  C3. 404/410 -> http_not_found.
  C4. 404 + 12 jobs -> stale_404_live_api (edge Gem do doc upstream).
  C5. 403 -> http_error (nao-200 nao-404; WAF — eco do E1 da F76).
  C6. 200 + erro de parse -> branded_shell_no_jobs (o 200-falso).
  C7. status 0 + erro de rede -> unreachable.
  C8. ATS instalado mas FORA do registry (lever) -> unknown_ats.
  C9. classify_slug: demo/sandbox/stage/qa/test -> demo_sandbox_tenant
      (incl. prefixo RDASH_DEMO do doc); slug limpo -> None; ATS fora do
      universo -> unknown_ats.
  C10. tenant_key: scheme/www/barra-final/utm_* colapsam para a MESMA
      chave; slug distinto -> chave distinta; prefixo ats separa
      universos; params funcionais (site) preservados (licao F5).

GRUPO D — maquina de validacao OFFLINE (injecao scraper/outcome):
  D1. URL resolvivel + scraper fake (200, 37 jobs) -> valid; evidence
      completa (url/ats/slug/endpoint/status/job_count/tenant_key/company).
  D2. CompanyNotFoundError -> http_not_found (mapeamento documentado).
  D3. MalformedJSONError -> branded_shell_no_jobs (200-falso F76).
  D4. ScraperError de rede -> unreachable.
  D5. dominio custom (phenom jobs.bell.ca) -> unresolvable_url com hint
      apontando validate_slug.
  D6. URL de ATS fora do universo (lever) -> unknown_ats.
  D7. determinismo: veredito identico em 2 chamadas.
  D8. validate_slug com (ats, slug-URL) + scraper fake -> valid (o caminho
      manual dos 3 ATS resolvable=False funciona).
  D9. validate_slug com slug demo -> demo_sandbox_tenant ANTES de
      construir o scraper (factory nunca chamada).
  D10. validate_slug de ATS fora do universo -> unknown_ats.

GRUPO E — contratos:
  E1. modulo SEM rede propria: fonte nao importa urllib.request/requests/
      httpx e nao chama urlopen (a rede vive so no scraper do pacote, no
      caminho manual _outcome_of).
  E2. membership: test_f76_1 na suite descoberta (auto-discovery F78).
  E3. README: contador 'N CI test suites' == len(suite descoberta)
      (contrato F73 — bumped 121 -> 122 neste PR).

100% offline: resolver do pacote e mapeamento deterministico de URL;
scrapers sao FAKES com fetch/outcome injetados; zero rede, zero espera.
"""

from __future__ import annotations

import importlib
import inspect
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ats_scrapers import (  # noqa: E402
    CompanyNotFoundError,
    MalformedJSONError,
    ScraperError,
    list_ats,
    resolve_careers_url,
)
from internship_finder import discovery_rules as dr  # noqa: E402
from internship_finder.collectors.ats_scraper import URL_SLUG_ATS  # noqa: E402
from internship_finder.discovery_rules import (  # noqa: E402
    Invalid,
    RULES,
    classify,
    classify_slug,
    coverage,
    registry_ats,
    rule_for,
    rule_for_url,
    tenant_key,
    validate_candidate,
    validate_slug,
)

FAILURES: list[str] = []

# Headers medidos do ats-companies/*.csv upstream @6b44a1b (v0.3.0).
CSV_HEADERS: dict[str, tuple[str, ...]] = {
    "successfactors": ("name", "slug", "url"),
    "workday": ("name", "slug", "url"),
    "greenhouse": ("name", "slug", "url"),
    "smartrecruiters": ("name", "slug", "url"),
    "cornerstone": ("name", "slug", "url"),
    "phenom": ("url", "name", "company_code", "locale", "country"),
    "recruitee": ("name", "slug", "url"),
    "eightfold": ("name", "slug", "url", "domain"),
    "softgarden": ("name", "slug", "url"),
    "teamtailor": ("name", "slug", "url"),
    "ashby": ("name", "slug", "url"),
    "moka": ("name", "slug", "url"),
    "bamboohr": ("name", "slug", "url"),
    "personio": ("name", "slug", "url"),
    "avature": ("name", "slug", "url"),
    "oracle": ("name", "slug", "url"),  # sem CSV upstream (descoberta manual F126)
}

# Tokens do canonical_endpoint que PRECISAM existir no fonte do scraper
# INSTALADO (medição 20/10 contra ats_scrapers 0.3.0 do venv).
ENDPOINT_TOKENS: dict[str, tuple[str, ...]] = {
    "successfactors": ("sitemal.xml", "Job-Listing"),
    "workday": ("/wday/cxs/",),
    "greenhouse": ("boards-api.greenhouse.io", "/v1/boards/"),
    "smartrecruiters": ("api.smartrecruiters.com", "/postings"),
    "cornerstone": ("csod.com", "careersite"),
    "phenom": ("/widgets",),
    "recruitee": ("/api/offers",),
    "eightfold": ("/api/pcsx/",),
    "softgarden": ("jobs.feed.json",),
    "teamtailor": ("jobs.rss",),
    "ashby": ("posting-api/job-board",),
    "moka": ("/api/outer/ats-apply/website/jobs/v2",),
    "bamboohr": ("jobs/embed2.php",),
    "personio": ("search.json",),
    "avature": ("SearchJobs", "jobRecordsPerPage"),
    "oracle": ("recruitingCEJobRequisitions",),
}

# Token do jobs_signal (onde vagas vivas aparecem) no fonte INSTALADO.
SIGNAL_TOKENS: dict[str, str] = {
    "successfactors": "Posted-Date",
    "workday": "total",
    "greenhouse": "jobs",
    "smartrecruiters": "content",
    "cornerstone": "requisitions",
    "phenom": "totalHits",
    "recruitee": "offers",
    "eightfold": "positions",
    "softgarden": "dataFeedElement",
    "teamtailor": "item",
    "ashby": "jobs",
    "moka": "jobStats",
    "bamboohr": "jobOpening",
    "personio": "jobId",
    "avature": "JobDetail",
    "oracle": "requisitionList",
}

# Classes especificas por ATS (fora do baseline) — provider notes do doc.
EXTRA_INVALID: dict[str, tuple[str, ...]] = {
    "recruitee": (Invalid.ARCHIVED_BOARD,),
    "eightfold": (Invalid.API_DISABLED,),
    "phenom": (Invalid.UNRESOLVABLE_URL,),
    "successfactors": (Invalid.UNRESOLVABLE_URL,),
    "cornerstone": (Invalid.UNRESOLVABLE_URL,),
    "avature": (Invalid.UNRESOLVABLE_URL,),
    "oracle": (Invalid.UNRESOLVABLE_URL,),
}

BASELINE = (
    Invalid.PROVIDER_HOME, Invalid.GLOBAL_MARKETPLACE, Invalid.LOGIN_SHELL,
    Invalid.BRANDED_SHELL, Invalid.STALE_404_LIVE_API,
    Invalid.HTTP_NOT_FOUND, Invalid.REDIRECTED, Invalid.EXPIRED_JOB_PAGE,
    Invalid.DEMO_TENANT, Invalid.OPAQUE_SLUG, Invalid.DUPLICATE_IDENTITY,
)

ALL_CLASSES = {
    getattr(Invalid, n) for n in dir(Invalid) if n.isupper()
}


def check(desc: str, ok: bool, msg: str = "") -> None:
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {desc}" + (f" -> {msg}" if msg and not ok else ""))
    if not ok:
        FAILURES.append(desc)


def _scraper_source(ats: str) -> str:
    mod = importlib.import_module(f"ats_scrapers.scrapers.{ats}")
    return inspect.getsource(mod)


class FakeScraper:
    """Scraper fake: fetch() devolve jobs ou levanta a excecao injetada."""

    def __init__(self, jobs=None, exc=None, company_name="Acme GmbH"):
        self._jobs = jobs if jobs is not None else []
        self._exc = exc
        self.company_name = company_name

    def fetch(self):
        if self._exc is not None:
            raise self._exc
        return self._jobs


def test_coverage() -> None:
    print("GRUPO A — cobertura regras x registry (derivado do SEED)")
    reg, have = registry_ats(), set(RULES)
    cov = coverage()
    check("A1. set(RULES) == registry_ats() (16 == 16, coverage vazio — +avature F125 +oracle F126)",
          have == reg and not cov["missing_rules"]
          and not cov["rules_without_registry_ats"] and len(reg) == 16,
          f"registry={len(reg)} rules={len(RULES)} cov={cov}")

    known = set(list_ats())
    ok_inv = all(rule_for(r.ats) is r for r in RULES.values())
    ok_known = all(r.ats in known for r in RULES.values())
    check("A2. rule_for involutivo e ATS conhecidos da maquina instalada",
          ok_inv and ok_known,
          f"inv={ok_inv} known={ok_known}")

    bad_res, bad_url = [], []
    for ats, rule in sorted(RULES.items()):
        r = resolve_careers_url(rule.sample_url)
        if rule.resolvable:
            if not (r is not None and r.ats.value == ats and r.slug):
                bad_res.append(ats)
            if rule_for_url(rule.sample_url) is not rule:
                bad_url.append(ats)
        else:
            if r is not None or rule_for_url(rule.sample_url) is not None:
                bad_res.append(ats)
    n_res = sum(1 for r in RULES.values() if r.resolvable)
    check("A3. resolvable=True (11): resolver concorda (ats+slug) e "
          "rule_for_url devolve a regra",
          n_res == 11 and not bad_res and not bad_url,
          f"n_res={n_res} bad={bad_res + bad_url}")

    non_res = sorted(a for a, r in RULES.items() if not r.resolvable)
    check("A4. resolvable=False == exatamente avature/successfactors/cornerstone/"
          "phenom/oracle (dominio custom/legado/sem CSV upstream: resolver "
          "None por desenho — validacao manual via validate_slug)",
          non_res == ["avature", "cornerstone", "oracle", "phenom", "successfactors"],
          f"non_res={non_res}")

    bad_uas = [a for a, r in RULES.items()
               if r.url_as_slug != (a in URL_SLUG_ATS)]
    check("A5. url_as_slug == (ats in URL_SLUG_ATS do coletor) — espelho "
          "do pipeline real",
          not bad_uas, f"bad={bad_uas} URL_SLUG_ATS={sorted(URL_SLUG_ATS)}")


def test_rules_executable() -> None:
    print("GRUPO B — 1 regra EXECUTAVEL por ATS, contra o pacote INSTALADO")
    for ats, rule in sorted(RULES.items()):
        check(f"B1. {ats}: csv_columns == header medido do CSV upstream "
              f"@6b44a1b + success universal",
              rule.csv_columns == CSV_HEADERS[ats]
              and rule.success == ("http_200", "jobs_live"),
              f"csv={rule.csv_columns} success={rule.success}")

    for ats, rule in sorted(RULES.items()):
        src = _scraper_source(ats)
        missing = [t for t in ENDPOINT_TOKENS[ats] if t not in src]
        check(f"B2. {ats}: tokens do canonical_endpoint no fonte instalado",
              not missing,
              f"missing={missing} endpoint={rule.canonical_endpoint}")

    for ats, rule in sorted(RULES.items()):
        src = _scraper_source(ats)
        tok = SIGNAL_TOKENS[ats]
        check(f"B3. {ats}: token do jobs_signal no fonte instalado",
              tok in src, f"token={tok!r} signal={rule.jobs_signal}")

    for ats, rule in sorted(RULES.items()):
        inv = set(rule.invalid)
        ok_tax = inv <= ALL_CLASSES
        ok_base = set(BASELINE) <= inv
        ok_extra = inv - set(BASELINE) == set(EXTRA_INVALID.get(ats, ()))
        ok_inv_res = (Invalid.UNRESOLVABLE_URL in inv) == (not rule.resolvable)
        check(f"B4. {ats}: invalid baseline completo + especificas + "
              f"invariante resolvable",
              ok_tax and ok_base and ok_extra and ok_inv_res,
              f"tax={ok_tax} base={ok_base} extra={inv - set(BASELINE)} "
              f"inv_res={ok_inv_res}")


def test_classifier() -> None:
    print("GRUPO C — classificador puro")
    v = classify("recruitee", status=200, job_count=42, url="u",
                 slug="12build")
    check("C1. 200 + 42 jobs -> valid; reason cita jobs_signal; evidence "
          "com endpoint/tenant_key",
          v.valid and v.reason.startswith("http_200 + 42")
          and "offers" in v.reason and v.evidence["endpoint"]
          and v.evidence["tenant_key"] == "recruitee:12build",
          f"reason={v.reason!r} ev={v.evidence}")

    v = classify("recruitee", status=200, job_count=0)
    check("C2. 200 + 0 jobs -> branded_shell_no_jobs",
          not v.valid and v.reason == Invalid.BRANDED_SHELL, v.reason)

    v404 = classify("ashby", status=404)
    v410 = classify("ashby", status=410)
    check("C3. 404/410 -> http_not_found",
          v404.reason == Invalid.HTTP_NOT_FOUND
          and v410.reason == Invalid.HTTP_NOT_FOUND,
          f"{v404.reason}/{v410.reason}")

    v = classify("greenhouse", status=404, job_count=12)
    check("C4. 404 + 12 jobs -> stale_404_live_api (edge Gem)",
          v.reason == Invalid.STALE_404_LIVE_API, v.reason)

    v = classify("workday", status=403)
    check("C5. 403 -> http_error (WAF — eco do E1 da F76)",
          not v.valid and v.reason == Invalid.HTTP_ERROR, v.reason)

    v = classify("workday", status=200, job_count=0,
                 error="MalformedJSONError: html")
    check("C6. 200 + erro de parse -> branded_shell_no_jobs (200-falso)",
          v.reason == Invalid.BRANDED_SHELL, v.reason)

    v = classify("ashby", status=0, error="URLError: timeout")
    check("C7. status 0 + rede -> unreachable",
          v.reason == Invalid.UNREACHABLE, v.reason)

    v = classify("lever", status=200, job_count=5)
    check("C8. ATS fora do universo (lever) -> unknown_ats",
          not v.valid and v.reason == Invalid.UNKNOWN_ATS, v.reason)

    d1 = classify_slug("ashby", "acme-test")
    d2 = classify_slug("greenhouse", "rdash_demo42")
    d3 = classify_slug("bamboohr", "sandbox-co")
    d4 = classify_slug("moka", "adidas/140456")
    d5 = classify_slug("lever", "whatever")
    check("C9. classify_slug: demo/sandbox/rdash -> demo_sandbox_tenant; "
          "limpo -> None; fora do universo -> unknown_ats",
          d1 is not None and d1.reason == Invalid.DEMO_TENANT
          and d2 is not None and d2.reason == Invalid.DEMO_TENANT
          and d3 is not None and d3.reason == Invalid.DEMO_TENANT
          and d4 is None and d5 is not None
          and d5.reason == Invalid.UNKNOWN_ATS,
          f"{[getattr(x, 'reason', None) for x in (d1, d2, d3, d4, d5)]}")

    k1 = tenant_key("workday", "https://23andme.wd5.myworkdayjobs.com/23/")
    k2 = tenant_key("workday", "https://www.23andme.wd5.myworkdayjobs.com/23?utm_source=ga")
    k3 = tenant_key("workday", "https://23andme.wd5.myworkdayjobs.com/other")
    k4 = tenant_key("recruitee", "12build.recruitee.com/")
    k5 = tenant_key("greenhouse", "12build")  # mesmo slug, ATS distinto
    check("C10. tenant_key: variantes colapsam; distinto separa; ats "
          "separa; param funcional preservado",
          k1 == k2 and k1 != k3 and k4 == "recruitee:12build.recruitee.com"
          and k5 == "greenhouse:12build" and k5 != k4
          and tenant_key("workday", "https://x.wd5.myworkdayjobs.com/23?site=abc").endswith("site=abc"),
          f"k1={k1!r} k3={k3!r} k4={k4!r} k5={k5!r}")


def test_machine_offline() -> None:
    print("GRUPO D — maquina de validacao OFFLINE (injecao)")
    v = validate_candidate(
        "https://12build.recruitee.com",
        scraper_factory=lambda url: FakeScraper(jobs=[object()] * 37),
    )
    ev = v.evidence
    check("D1. URL resolvivel + fake (200, 37) -> valid; evidence completa",
          v.valid and v.ats == "recruitee" and ev["slug"] == "12build"
          and ev["status"] == 200 and ev["job_count"] == 37
          and ev["endpoint"] and ev["tenant_key"] == "recruitee:12build"
          and ev["company"] == "Acme GmbH" and ev["url"] == ev["final_url"],
          f"v={v}")

    v = validate_candidate(
        "https://12build.recruitee.com",
        scraper_factory=lambda url: FakeScraper(exc=CompanyNotFoundError("nf")),
    )
    check("D2. CompanyNotFoundError -> http_not_found",
          not v.valid and v.reason == Invalid.HTTP_NOT_FOUND, v.reason)

    v = validate_candidate(
        "https://12build.recruitee.com",
        scraper_factory=lambda url: FakeScraper(exc=MalformedJSONError("html")),
    )
    check("D3. MalformedJSONError -> branded_shell_no_jobs (200-falso)",
          v.reason == Invalid.BRANDED_SHELL, v.reason)

    v = validate_candidate(
        "https://12build.recruitee.com",
        scraper_factory=lambda url: FakeScraper(exc=ScraperError("net")),
    )
    check("D4. ScraperError de rede -> unreachable",
          v.reason == Invalid.UNREACHABLE, v.reason)

    v = validate_candidate("https://jobs.bell.ca")
    check("D5. dominio custom (phenom) -> unresolvable_url + hint "
          "validate_slug",
          not v.valid and v.reason == Invalid.UNRESOLVABLE_URL
          and "validate_slug" in v.evidence.get("hint", ""),
          f"reason={v.reason} hint={v.evidence.get('hint')}")

    v = validate_candidate("https://jobs.lever.co/acme")
    check("D6. URL de ATS fora do universo (lever) -> unknown_ats",
          v.reason == Invalid.UNKNOWN_ATS, v.reason)

    def _call():
        return validate_candidate(
            "https://12build.recruitee.com",
            scraper_factory=lambda url: FakeScraper(jobs=[object()] * 3),
        )

    a, b = _call(), _call()
    check("D7. determinismo: 2 chamadas -> veredito identico",
          (a.valid, a.reason, a.evidence) == (b.valid, b.reason, b.evidence))

    v = validate_slug(
        "phenom", "https://jobs.bell.ca",
        scraper_factory=lambda: FakeScraper(jobs=[object()] * 9),
    )
    check("D8. validate_slug (ats, slug-URL) + fake -> valid (caminho "
          "manual dos 3 resolvable=False)",
          v.valid and v.ats == "phenom" and v.evidence["job_count"] == 9,
          f"v={v}")

    def _boom():
        raise AssertionError("factory nao deve ser chamada para slug demo")

    v = validate_slug("cornerstone", "acme-stage", scraper_factory=_boom)
    check("D9. validate_slug com slug demo -> demo_sandbox_tenant ANTES do "
          "scraper",
          not v.valid and v.reason == Invalid.DEMO_TENANT, v.reason)

    v = validate_slug("lever", "https://jobs.lever.co/acme")
    check("D10. validate_slug de ATS fora do universo -> unknown_ats",
          v.reason == Invalid.UNKNOWN_ATS, v.reason)


def test_contracts() -> None:
    print("GRUPO E — contratos")
    src = Path(dr.__file__).read_text(encoding="utf-8")
    bad_imports = [t for t in ("import urllib.request", "import requests",
                               "import httpx", "urlopen") if t in src]
    check("E1. modulo SEM rede propria (rede so no scraper do pacote, "
          "caminho manual)",
          not bad_imports, f"bad={bad_imports}")

    import ci_discover_tests  # noqa: E402  (F78: auto-discovery)
    names = ci_discover_tests.discover_tests()
    check("E2. membership: test_f76_1 na suite descoberta do CI",
          "test_f76_1" in names, f"{len(names)} suites")

    readme = Path(__file__).resolve().parent.parent / "README.md"
    text = readme.read_text(encoding="utf-8")
    m = re.search(r"\*\*(\d+)\*\* \| CI test suites", text)
    n_readme = int(m.group(1)) if m else -1
    check("E3. README: contador 'N CI test suites' == suite descoberta "
          "(contrato F73; bumped 121 -> 122)",
          n_readme == len(names), f"readme={n_readme} discovery={len(names)}")


def main() -> int:
    test_coverage()
    print()
    test_rules_executable()
    print()
    test_classifier()
    print()
    test_machine_offline()
    print()
    test_contracts()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
