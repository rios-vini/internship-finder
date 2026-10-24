"""F76.1 — DISCOVERY_RULES local: regras EXECUTAVEIS por ATS do registry.

Contexto (decisao do dono 20/10, opcao B "mecanismo minimo local"): as
DISCOVERY_RULES do upstream (kalil0321/ats-scrapers @6b44a1b = v0.3.0,
``docs/DISCOVERY_RULES.md``, 318 linhas) sao um DOC — endpoints e criterios
em PROSA para humanos abrindo PRs no upstream, zero codigo executavel; so
4 das 10 provider notes cobrem ATS do nosso registry. Este modulo destila o
subconjunto que o IF usa em REGRAS VERSIONADAS, uma por ATS DO REGISTRY (14
medidos em 20/10, 127 empresas), e executa a validacao com a API INSTALADA
como maquina: ``resolve_careers_url``/``get_scraper_for_url`` (mapeamento
deterministico OFFLINE de URL -> (ats, slug)) + o scraper do pacote (a
unica rede, e so no uso MANUAL — suite e CI sao 100% offline).

Cada regra e originada em MEDICAO, nao em opiniao:
- ``csv_columns``: header do ``ats-companies/<ats>.csv`` upstream (@6b44a1b).
- ``slug_semantics``: o que e a identidade estavel do tenant e como ela vira
  input do scraper (token de path, subdominio, URL completa, company/site).
- ``canonical_endpoint``: endpoint de validacao consumido pelo scraper
  INSTALADO (a regra e verificada contra o codigo instalado — ver
  ``scripts/test_f76_1.py`` Grupo B).
- ``jobs_signal``: onde vagas VIVAS aparecem numa resposta de sucesso.
- ``invalid``: classes de rejeicao aplicaveis (taxonomia canônica
  ``Invalid``, destilada do doc upstream §Invalid Cases + provider notes).
- ``sample_url``: URL real do shape do ATS (exercita o resolver offline).
- ``resolvable``: ``resolve_careers_url`` reconhece o shape? False =>
  dominio custom: a validacao exige slug-URL via ``validate_slug``.
- ``url_as_slug``: o input do scraper e a URL completa do board (espelha o
  ``URL_SLUG_ATS`` do coletor — consistencia travada no teste).

Drift tem DOIS eixos (o mecanismo e LEVE por definicao):
1. Pacote instalado <-> regras: pego OFFLINE pelo ``test_f76_1`` (Grupo B
   confere endpoint/sinal no fonte instalado; bump de ats-scrapers que mude
   endpoint => suite vermelha, sem rede, sem procedimento).
2. Doc upstream <-> regras: procedimento MANUAL leve (nunca CI — rede):
   ver ``docs/f76_1_discovery_rules.md`` §drift-check.

F105 (23/10): alem das regras por ATS, tenants medidos com MIGRACAO de
formato de URL DE VAGA ganham a camada ``TENANT_JOB_URL_FORMATS`` (guard
do formato vivo x legado morto — caso Vetter: ``/jobs/<ID>`` da 404,
``/job/<slug>/<ID>/`` ativo, IDs inalterados). Mesma natureza: regra
derivada de medicao, consumo manual/drift-check, zero pipeline.

Nao e estagio do pipeline: discovery de tenant e procedimento humano
assistido (candidatas ao registry); nada aqui roda no cron.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ats_scrapers import (
    CompanyNotFoundError,
    MalformedJSONError,
    ScraperError,
    get_scraper_for_url,
    resolve_careers_url,
)

from internship_finder.registry import SEED


class Invalid:
    """Taxonomia canonica de rejeicao.

    Mapeia 1:1 o §Invalid Cases do doc upstream (10 classes) + 2 classes
    das provider notes (archived_board/recruitee, api_disabled/eightfold) +
    4 classes do PROPRIO mecanismo de validacao (resolucao de URL, universo
    do registry, status nao-200, falha de rede/parse).
    """

    # — doc upstream §Invalid Cases —
    PROVIDER_HOME = "provider_home"  # pagina de marketing do ATS
    GLOBAL_MARKETPLACE = "global_marketplace"  # busca global multi-empresa
    LOGIN_SHELL = "login_shell"  # pagina de login generica do ATS
    BRANDED_SHELL = "branded_shell_no_jobs"  # 200 sem dado de vaga vivo
    STALE_404_LIVE_API = "stale_404_live_api"  # board 404 mas API viva (edge Gem)
    HTTP_NOT_FOUND = "http_not_found"  # 404/410 da board candidata
    REDIRECTED = "redirected_to_provider_home"  # board -> home/busca do ATS
    EXPIRED_JOB_PAGE = "expired_job_page"  # vaga expirada, board invalida
    DEMO_TENANT = "demo_sandbox_tenant"  # demo/sandbox/stage/QA/test
    OPAQUE_SLUG = "opaque_slug_no_name"  # slug tecnico sem nome confiavel
    DUPLICATE_IDENTITY = "duplicate_identity"  # mesmo tenant, variante locale/tracking
    # — provider notes (ATS especificas) —
    ARCHIVED_BOARD = "archived_board"  # recruitee: board arquivado
    API_DISABLED = "api_disabled_tenant"  # eightfold: PCSX off / so SmartApply
    # — mecanismo (validacao com a API instalada) —
    UNRESOLVABLE_URL = "unresolvable_url"  # dominio custom: resolver -> None
    UNKNOWN_ATS = "unknown_ats"  # ATS fora do universo do registry
    HTTP_ERROR = "http_error"  # status nao-200 nao-404 (ex.: 403 de WAF)
    UNREACHABLE = "unreachable"  # rede/timeout/parse durante a validacao


# Baseline do doc upstream: vale para TODOS os ATS do registry.
_BASELINE_INVALID: tuple[str, ...] = (
    Invalid.PROVIDER_HOME,
    Invalid.GLOBAL_MARKETPLACE,
    Invalid.LOGIN_SHELL,
    Invalid.BRANDED_SHELL,
    Invalid.STALE_404_LIVE_API,
    Invalid.HTTP_NOT_FOUND,
    Invalid.REDIRECTED,
    Invalid.EXPIRED_JOB_PAGE,
    Invalid.DEMO_TENANT,
    Invalid.OPAQUE_SLUG,
    Invalid.DUPLICATE_IDENTITY,
)

# Criterio de sucesso universal (Baseline Rule #3 e #4 do doc upstream:
# "validation request returns HTTP 200" + "response contains live job-list
# data"). Extras especificos das provider notes (SF: ReqId/JobTitle/
# Job-Description nao-vazios; cornerstone: nome legivel) sao criterios de
# REVISAO MANUAL — ficam no docstring da regra e no docs/f76_1, nao aqui.
_SUCCESS: tuple[str, ...] = ("http_200", "jobs_live")


@dataclass(frozen=True)
class DiscoveryRule:
    """Regra executavel de discovery para um ATS do registry."""

    ats: str
    csv_columns: tuple[str, ...]  # input shape: header do CSV upstream
    slug_semantics: str
    canonical_endpoint: str
    jobs_signal: str
    success: tuple[str, ...]
    invalid: tuple[str, ...]
    sample_url: str
    resolvable: bool  # resolve_careers_url(sample_url) -> (ats, slug)?
    url_as_slug: bool  # input do scraper e a URL completa (URL_SLUG_ATS)


@dataclass(frozen=True)
class Verdict:
    """Desfecho da validacao de uma candidata (com evidencia)."""

    valid: bool
    ats: str | None
    reason: str  # classe de invalido OU descricao do sucesso
    evidence: dict = field(default_factory=dict)


RULES: dict[str, DiscoveryRule] = {
    "successfactors": DiscoveryRule(
        ats="successfactors",
        csv_columns=("name", "slug", "url"),
        slug_semantics=(
            "Recruiting Marketing: o slug da linha e curto (ex. 'jobs'), mas o "
            "INPUT do scraper e a URL COMPLETA do host RM por empresa "
            "(jobs2web/careers.*) — URL_SLUG_ATS do coletor; legacy = "
            "career{N}.successfactors.com + query company estavel"
        ),
        canonical_endpoint=(
            "GET {host}/sitemal.xml (RSS) — legacy: GET /career?"
            "company={id}&career_ns=job_listing_summary&resultType=XML"
        ),
        jobs_signal="rss:<item> (RMK); xml:<Job-Listing>/<Job> (legacy)",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID + (Invalid.UNRESOLVABLE_URL,),
        sample_url="https://ace1950.jobs2web.com",
        resolvable=False,  # host jobs2web/careers.* nao tem shape no resolver
        url_as_slug=True,
    ),
    "workday": DiscoveryRule(
        ats="workday",
        csv_columns=("name", "slug", "url"),
        slug_semantics=(
            "URL COMPLETA do board (company.wdN.myworkdayjobs.com/site) — o "
            "slug do CSV e 'company/site' mas a instancia wdN e load-bearing; "
            "resolve_careers_url devolve a URL inteira como slug"
        ),
        canonical_endpoint=(
            "POST {board}/wday/cxs/{company}/{site}/jobs (JSON com total)"
        ),
        jobs_signal="json:total (POST wday/cxs)",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID,
        sample_url="https://23andme.wd5.myworkdayjobs.com/23",
        resolvable=True,
        url_as_slug=True,
    ),
    "greenhouse": DiscoveryRule(
        ats="greenhouse",
        csv_columns=("name", "slug", "url"),
        slug_semantics="token de path em boards.greenhouse.io/job-boards.greenhouse.io (etc.)",
        canonical_endpoint="GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        jobs_signal="json:jobs",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID,
        sample_url="https://job-boards.greenhouse.io/10beauty",
        resolvable=True,
        url_as_slug=False,
    ),
    "smartrecruiters": DiscoveryRule(
        ats="smartrecruiters",
        csv_columns=("name", "slug", "url"),
        slug_semantics="token de path em careers.smartrecruiters.com (por empresa)",
        canonical_endpoint="GET https://api.smartrecruiters.com/v1/companies/{slug}/postings",
        jobs_signal="json:content (+total)",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID,
        sample_url="https://careers.smartrecruiters.com/10pearls",
        resolvable=True,
        url_as_slug=False,
    ),
    "cornerstone": DiscoveryRule(
        ats="cornerstone",
        csv_columns=("name", "slug", "url"),
        slug_semantics=(
            "subdominio {tenant}.csod.com + site_id (default 1); URL e por "
            "empresa (query c={slug}); nome legivel vem do CSV (provider "
            "note: so slugs tecnicos expostos)"
        ),
        canonical_endpoint=(
            "GET https://{slug}.csod.com/ux/ats/careersite/{site_id}/home?c={slug} "
            "+ gateway de reqs (json:requisitions/totalCount)"
        ),
        jobs_signal="json:data.requisitions (+totalCount)",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID + (Invalid.UNRESOLVABLE_URL,),
        sample_url="https://aswatsoneurope.csod.com/ux/ats/careersite/1/home?c=aswatsoneurope",
        resolvable=False,  # *.csod.com nao tem shape no resolver
        url_as_slug=False,
    ),
    "phenom": DiscoveryRule(
        ats="phenom",
        csv_columns=("url", "name", "company_code", "locale", "country"),
        slug_semantics=(
            "URL COMPLETA do site de careers (dominio CUSTOM por tenant, ex. "
            "jobs.bell.ca) + locale/country por tenant (CSV upstream tem as 5 "
            "colunas); registry IF: phenom:nan e tenant COMPARTILHADO (F81) — "
            "a URL do portal e por empresa"
        ),
        canonical_endpoint=(
            "GET {base}/{country}/{lang}/search-results (CSRF) + "
            "POST {base}/widgets (ddoKey=refineSearch)"
        ),
        jobs_signal="json:totalHits (POST /widgets)",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID + (Invalid.UNRESOLVABLE_URL,),
        sample_url="https://jobs.bell.ca",
        resolvable=False,  # dominio custom: resolver -> None (por desenho)
        url_as_slug=True,
    ),
    "recruitee": DiscoveryRule(
        ats="recruitee",
        csv_columns=("name", "slug", "url"),
        slug_semantics="subdominio {slug}.recruitee.com",
        canonical_endpoint="GET https://{slug}.recruitee.com/api/offers",
        jobs_signal="json:offers",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID + (Invalid.ARCHIVED_BOARD,),
        sample_url="https://12build.recruitee.com",
        resolvable=True,
        url_as_slug=False,
    ),
    "eightfold": DiscoveryRule(
        ats="eightfold",
        csv_columns=("name", "slug", "url", "domain"),
        slug_semantics=(
            "subdominio {slug}.eightfold.ai (PCSX); coluna domain extra do "
            "CSV — obrigatoria quando o tenant exige domain configurado"
        ),
        canonical_endpoint=(
            "POST {base}/api/pcsx/search (domain, query/location vazios, "
            "start=0, sort_by=timestamp)"
        ),
        jobs_signal="json:data.positions",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID + (Invalid.API_DISABLED,),
        sample_url="https://albemarle.eightfold.ai/careers",
        resolvable=True,
        url_as_slug=False,
    ),
    "softgarden": DiscoveryRule(
        ats="softgarden",
        csv_columns=("name", "slug", "url"),
        slug_semantics="subdominio {tenant}.career.softgarden.de",
        canonical_endpoint="GET https://{tenant}.career.softgarden.de/jobs.feed.json",
        jobs_signal="json:dataFeedElement (+numberOfItems)",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID,
        sample_url="https://abeking.career.softgarden.de/",
        resolvable=True,
        url_as_slug=False,
    ),
    "teamtailor": DiscoveryRule(
        ats="teamtailor",
        csv_columns=("name", "slug", "url"),
        slug_semantics="subdominio {slug}.teamtailor.com",
        canonical_endpoint="GET https://{slug}.teamtailor.com/jobs.rss",
        jobs_signal="rss:<item>",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID,
        sample_url="https://123pousse.teamtailor.com",
        resolvable=True,
        url_as_slug=False,
    ),
    "ashby": DiscoveryRule(
        ats="ashby",
        csv_columns=("name", "slug", "url"),
        slug_semantics="token de path em jobs.ashbyhq.com",
        canonical_endpoint=(
            "GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
        ),
        jobs_signal="json:jobs",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID,
        sample_url="https://jobs.ashbyhq.com/openai",
        resolvable=True,
        url_as_slug=False,
    ),
    "moka": DiscoveryRule(
        ats="moka",
        csv_columns=("name", "slug", "url"),
        slug_semantics=(
            "composto empresa/site_id numerico (ex. adidas/140456); hosts "
            "app.mokahr.com/hire-r1.mokahr.com; campus ganha sufixo /campus"
        ),
        canonical_endpoint="POST {host}/api/outer/ats-apply/website/jobs/v2",
        jobs_signal="json:jobs (+jobStats.total)",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID,
        sample_url="https://app.mokahr.com/social-recruitment/trip/70415",
        resolvable=True,
        url_as_slug=False,
    ),
    "bamboohr": DiscoveryRule(
        ats="bamboohr",
        csv_columns=("name", "slug", "url"),
        slug_semantics="subdominio {slug}.bamboohr.com (URL /careers por empresa)",
        canonical_endpoint="GET https://{slug}.bamboohr.com/jobs/embed2.php (JSON puro desde 08/10 — ver F59)",
        jobs_signal="json:result.jobOpening",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID,
        sample_url="https://10web.bamboohr.com/careers",
        resolvable=True,
        url_as_slug=False,
    ),
    "personio": DiscoveryRule(
        ats="personio",
        csv_columns=("name", "slug", "url"),
        slug_semantics="subdominio {slug}.jobs.personio.com (ou .de)",
        canonical_endpoint="GET https://{slug}.jobs.personio.com/search.json (legacy /api/careers/jobs/list/)",
        jobs_signal="json:jobs (search.json; ats_id via id/jobId/uuid)",
        success=_SUCCESS,
        invalid=_BASELINE_INVALID,
        sample_url="https://10xfounders.jobs.personio.com",
        resolvable=True,
        url_as_slug=False,
    ),
}


def registry_ats() -> frozenset[str]:
    """ATS do universe do registry, medido do SEED (fonte: registry.py).

    Entries ``dynamic`` tem ats=None (F71) e ficam fora do universo de
    regras — discovery valida o que o scraper sabe consumir.
    """
    return frozenset(e.ats for e in SEED if e.ats)


def rule_for(ats: str) -> DiscoveryRule | None:
    """Regra de discovery do ATS (ou None se fora do universo do registry)."""
    return RULES.get((ats or "").strip().casefold())


def coverage() -> dict[str, list[str]]:
    """Drift regras x registry: ATS sem regra e regras sem ATS no registry."""
    reg = set(registry_ats())
    have = set(RULES)
    return {
        "missing_rules": sorted(reg - have),
        "rules_without_registry_ats": sorted(have - reg),
    }


def rule_for_url(url: str) -> DiscoveryRule | None:
    """Regra do ATS reconhecido na URL — None se forma desconhecida.

    Usa o resolver OFFLINE do pacote instalado (mapeamento deterministico
    de URL -> (ats, slug); sem rede). Dominios custom (phenom/cornerstone/
    successfactors RM) retornam None por desenho — o caminho manual e
    ``validate_slug(ats, slug)``.
    """
    resolved = resolve_careers_url(url)
    if resolved is None:
        return None
    return rule_for(resolved.ats.value)


# ---------------------------------------------------------------------------
# Classificador puro — executa os criterios da regra sobre um desfecho.
# ---------------------------------------------------------------------------


def _evidence(rule: DiscoveryRule, *, url: str, slug: str, status: int,
              job_count: int, error: str) -> dict:
    return {
        "url": url,
        "ats": rule.ats,
        "slug": slug,
        "endpoint": rule.canonical_endpoint,
        "status": status,
        "job_count": job_count,
        "error": error,
        "tenant_key": tenant_key(rule.ats, slug) if slug else "",
    }


def classify(ats: str, *, status: int, job_count: int = 0, error: str = "",
             url: str = "", slug: str = "") -> Verdict:
    """Executa a regra do ATS sobre um desfecho de validacao.

    ``status`` 0 significa "sem HTTP confiavel" (rede/timeout). A ordem dos
    criterios espelha o doc upstream: 404 com API viva e o edge documentado
    (Gem); 200 sem vaga viva e o branded shell; 200 com corpo que nao parseia
    (ex.: HTML de WAF onde se espera JSON) e ALSO branded shell — o 200-falso
    da licao F76.
    """
    rule = rule_for(ats)
    if rule is None:
        return Verdict(False, ats, Invalid.UNKNOWN_ATS, {
            "url": url, "ats": ats, "slug": slug, "endpoint": "",
            "status": status, "job_count": job_count, "error": error,
            "tenant_key": "",
        })
    ev = _evidence(rule, url=url, slug=slug, status=status,
                   job_count=job_count, error=error)
    if status == 0 and error:
        return Verdict(False, rule.ats, Invalid.UNREACHABLE, ev)
    if status in (404, 410):
        if job_count > 0:
            return Verdict(False, rule.ats, Invalid.STALE_404_LIVE_API, ev)
        return Verdict(False, rule.ats, Invalid.HTTP_NOT_FOUND, ev)
    if status != 200:
        return Verdict(False, rule.ats, Invalid.HTTP_ERROR, ev)
    if error:  # 200 com corpo invalido = shell sem dado de vaga
        return Verdict(False, rule.ats, Invalid.BRANDED_SHELL, ev)
    if job_count <= 0:
        return Verdict(False, rule.ats, Invalid.BRANDED_SHELL, ev)
    return Verdict(True, rule.ats,
                   f"http_200 + {job_count} vagas vivas ({rule.jobs_signal})",
                   ev)


_DEMO_TOKENS = frozenset(
    {"demo", "sandbox", "stage", "staging", "qa", "test", "uat"}
)


def classify_slug(ats: str, slug: str) -> Verdict | None:
    """Screening de slug de tenant (doc upstream: demo/sandbox/stage/QA/test).

    None = slug limpo. Verdict invalido carrega a classe ``demo_sandbox_tenant``
    (exemplo documentado do doc: orgs Taleo ``RDASH_DEMO*``).
    """
    rule = rule_for(ats)
    if rule is None:
        return Verdict(False, ats, Invalid.UNKNOWN_ATS, {"ats": ats, "slug": slug})
    s = (slug or "").casefold()
    tokens = {t for t in re.split(r"[^a-z0-9]+", s) if t}
    if tokens & _DEMO_TOKENS or s.startswith("rdash_demo"):
        return Verdict(False, rule.ats, Invalid.DEMO_TENANT,
                       {"ats": rule.ats, "slug": slug})
    return None


def tenant_key(ats: str, slug_or_url: str) -> str:
    """Identidade ESTAVEL do tenant para dedupe (workflow upstream #4).

    Normaliza: casefold, sem scheme/www, sem barra final, sem params de
    tracking (utm_*). Params funcionais (pid/page/id/site...) sao
    PRESERVADOS — conservadorismo da licao F5 (identidade de URL e
    contrato). O prefixo ats separa universos (slugs podem colidir entre
    ATS).
    """
    s = (slug_or_url or "").strip().casefold()
    if "://" in s:
        parts = urlsplit(s)
        host = (parts.netloc or "").removeprefix("www.")
        path = parts.path.rstrip("/")
        keep = [(k, v) for k, v in parse_qsl(parts.query)
                if not k.casefold().startswith("utm_")]
        s = urlunsplit(("", host, path, urlencode(keep), ""))
    else:
        s = s.rstrip("/")
    return f"{(ats or '').casefold()}:{s}"


# ---------------------------------------------------------------------------
# F105 — Formato de URL DE VAGA por tenant (medido; guard de migracao)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TenantJobUrlFormat:
    """Formato de URL DE VAGA medido p/ um tenant do registry (F105).

    O ``RULES`` acima descreve a descoberta de TENANT (board de careers);
    tenants medidos podem MIGRAR o formato da URL de vaga — a regra existe
    como GUARD: URL no formato ``legacy`` esta MORTA (404 medido) e NUNCA
    e seguida/reconstruida/divulgada como link; URL no formato ``current``
    e a viva. Tenant sem medicao (ou URL de outro shape) => ``None`` — a
    ausencia de evidencia nunca vira veredito (mesmo padrao do
    ``provider_id_plausible`` da F96).
    """

    tenant: str  # nome do tenant no registry (ex. "Vetter")
    ats: str  # ATS do tenant (``rule_for(ats)`` e a regra-mae)
    current: "re.Pattern[str]"  # formato VIVO (o feed emite hoje)
    legacy: tuple["re.Pattern[str]", ...]  # formatos MORTOS (404 medido)
    evidence: str  # medicao (data + metodo) — nunca opiniao


TENANT_JOB_URL_FORMATS: dict[str, TenantJobUrlFormat] = {
    "vetter": TenantJobUrlFormat(
        tenant="Vetter",
        ats="successfactors",
        current=re.compile(
            r"https://careers\.vetter-pharma\.com/job/[^/?#]+/\d+/"),
        legacy=(
            re.compile(r"https://careers\.vetter-pharma\.com/jobs/\d+/?"),
        ),
        evidence=(
            "registro 23/10/2026: portal migrou de formato — "
            "careers.vetter-pharma.com/jobs/<ID> da 404; novo "
            "/job/<slug>/<ID>/ ATIVO (7 vagas verificadas, IDs "
            "inalterados); apply = botao \"Jetzt bewerben\" na pagina da "
            "vaga -> Bewerberkonto no SuccessFactors "
            "(career5.successfactors.eu, company=Vetter); sem geoblock"
        ),
    ),
    # F108 (23/10/2026) — padrão CSOD: /home/requisition/<ID>?c=<tenant>...
    # é o formato VIVO; /job/<ID> redireciona para ADFS (login wall) e
    # NUNCA deve ser linkado diretamente. Portal luxair.lu/en/careers = 404.
    "luxair": TenantJobUrlFormat(
        tenant="Luxair",
        ats="cornerstone",
        current=re.compile(
            r"https://[^/]+\.csod\.com/ux/ats/careersite/\d+/home\?c=luxair&[^#]*"),
        legacy=(
            re.compile(r"https://[^/]+\.csod\.com/ux/ats/careersite/\d+/job/\d+/?"),
        ),
        evidence=(
            "registro 23/10/2026: Luxair csod — /job/<ID> (ex. req5377/5376) "
            "redireciona para ADFS (login wall); vivo = "
            "/home/requisition/<ID>?c=luxair&lang=... (req5377 ALIVE medido); "
            "portal luxair.lu/en/careers = 404 -> sempre link csod direto; "
            "padrão csod geral: link por requisition, NUNCA por /job/ (ADFS)"
        ),
    ),
    "henkel": TenantJobUrlFormat(
        tenant="Henkel",
        ats="cornerstone",
        current=re.compile(
            r"https://[^/]+\.csod\.com/ux/ats/careersite/\d+/home\?c=henkel&[^#]*"),
        legacy=(
            re.compile(r"https://[^/]+\.csod\.com/ux/ats/careersite/\d+/job/\d+/?"),
        ),
        evidence=(
            "registro 23/10/2026: Henkel csod ×4 (F96/SAML case F94) — "
            "/job/<ID> redireciona para ADFS/SAML (login wall); vivo = "
            "/home/requisition/<ID>?c=henkel&lang=...; padrão csod geral "
            "documentado: portais csod linkam por requisition, nunca por /job/"
        ),
    ),
}


def job_url_format_status(url: str) -> str | None:
    """Status do formato da URL DE VAGA p/ tenants com regra (F105).

    ``"current"`` = formato vivo (o que o feed deve emitir);
    ``"legacy_dead"`` = formato morto (404 medido — NUNCA seguir);
    ``None`` = sem regra p/ a URL (tenant sem medicao ou outro shape) —
    silencio honesto, nunca veredito inventado.
    """
    u = str(url or "").strip()
    if not u:
        return None
    for fmt in TENANT_JOB_URL_FORMATS.values():
        if fmt.current.fullmatch(u):
            return "current"
        for dead in fmt.legacy:
            if dead.fullmatch(u):
                return "legacy_dead"
    return None


# ---------------------------------------------------------------------------
# Maquina de validacao — API instalada como motor (rede SO no caminho
# default; testes injetam scraper_factory/outcome_of e ficam offline).
# ---------------------------------------------------------------------------


def _outcome_of(scraper) -> tuple[int, int, str]:
    """(status, job_count, error) de um fetch REAL — REDE, uso manual.

    Mapeamento das excecoes do pacote instalado para o desfecho que o
    classificador entende: CompanyNotFoundError -> 404; MalformedJSONError
    (200-falso, licao F76) -> 200 sem jobs + erro; demais ScraperError ->
    sem HTTP confiavel (0).
    """
    try:
        jobs = scraper.fetch()
    except CompanyNotFoundError:
        return (404, 0, "")
    except MalformedJSONError as exc:
        return (200, 0, f"MalformedJSONError: {exc}")
    except ScraperError as exc:
        return (0, 0, f"ScraperError: {exc}")
    except Exception as exc:  # rede/timeout/parse inesperado
        return (0, 0, f"{type(exc).__name__}: {exc}")
    return (200, len(jobs), "")


def _verdict(rule: DiscoveryRule, scraper, url: str, slug: str, outcome_of) -> Verdict:
    outcome = outcome_of(scraper)
    status, job_count, error = outcome
    verdict = classify(rule.ats, status=status, job_count=job_count,
                       error=error, url=url, slug=slug)
    name = ""
    try:
        name = str(getattr(scraper, "company_name", "") or "")
    except Exception:
        name = ""
    verdict.evidence["company"] = name
    verdict.evidence["final_url"] = url
    return verdict


def validate_candidate(url: str, *, timeout: float = 30.0,
                       scraper_factory=None, outcome_of=None) -> Verdict:
    """Valida uma candidata ao registry a partir da URL de careers — REDE.

    Uso MANUAL (procedimento de discovery/drift-check; nunca CI):
    resolve a URL com a API instalada, aplica a regra do ATS e classifica o
    desfecho do scraper. Para testes offline: ``scraper_factory`` (url ->
    scraper fake) e ``outcome_of`` (scraper -> (status, job_count, error)).
    """
    resolved = resolve_careers_url(url)
    if resolved is None:
        return Verdict(False, None, Invalid.UNRESOLVABLE_URL, {
            "url": url, "ats": None, "slug": "",
            "hint": (
                "dominio custom (phenom/cornerstone/successfactors RM): use "
                "validate_slug(ats, slug) com a URL completa do board, ou "
                "get_scraper(ats, slug) — ver docs/f76_1_discovery_rules.md"
            ),
        })
    rule = rule_for(resolved.ats.value)
    if rule is None:
        return Verdict(False, resolved.ats.value, Invalid.UNKNOWN_ATS, {
            "url": url, "ats": resolved.ats.value, "slug": resolved.slug,
            "endpoint": "",
            "hint": "ATS reconhecido fora do universo do registry (14 ATS)",
        })
    factory = scraper_factory or get_scraper_for_url
    scraper = factory(url)
    return _verdict(rule, scraper, url, resolved.slug,
                    outcome_of or _outcome_of)


def validate_slug(ats: str, slug: str, *, scraper_factory=None,
                  outcome_of=None) -> Verdict:
    """Valida candidata pelo (ats, slug) — caminho dos ATS de dominio custom.

    Uso MANUAL: para successfactors/phenom o slug e a URL completa do
    board (url_as_slug=True); para cornerstone e o token do tenant (+site_id
    default 1); para os demais aceita o token/subdominio tambem. Injecao
    ``scraper_factory`` () -> scraper e ``outcome_of`` p/ testes offline.
    """
    rule = rule_for(ats)
    if rule is None:
        return Verdict(False, ats, Invalid.UNKNOWN_ATS,
                       {"ats": ats, "slug": slug, "endpoint": "",
                        "hint": "ATS fora do universo do registry (14 ATS)"})
    screening = classify_slug(rule.ats, slug)
    if screening is not None:
        return screening

    def _default_factory(_ats=rule.ats, _slug=slug):
        from ats_scrapers.scrapers import get_scraper

        return get_scraper(_ats, _slug)

    factory = scraper_factory or _default_factory
    scraper = factory()
    return _verdict(rule, scraper, url=slug if rule.url_as_slug else "",
                    slug=slug, outcome_of=outcome_of or _outcome_of)
