"""Fontes de pesquisa institucionais e APIs keyless (F21) — adapters diretos.

Tier 1 do mapa de portais de pesquisa da Alemanha (reconhecimento ao vivo
07-08/10, revalidado nesta fase): fontes que NAO sao tenants ATS do
manifest companies.csv — portanto entram por ADAPTER DIRETO (padrao
dataset_source/direct_fetch: fetch -> ``Job`` -> mesmo funil
filtros->dedup->ranking), nunca pelo registry (regra F16: registry e so
para empresas do manifest).

Fontes (todas com probe ao vivo 09/10, 200 OK; tempos no relatorio):

1. ``mpg_rss``      — Max Planck Society, RSS https://www.mpg.de/feeds/jobs.rss
                      (30 itens; campos title/link/description/pubDate; id
                      estavel = URL do item, definida no prompt da fase).
2. ``tu_berlin``    — TU Berlin, HTML estavel www.jobs.tu-berlin.de/
                      stellenausschreibungen (~20 vagas/pagina; detail
                      ``/stellenausschreibungen/<id>`` com JSON-LD
                      JobPosting — description, addressCountry, validThrough).
                      id = <id> do detail.
3. ``leibniz``      — Leibniz Association, TYPO3 leibniz-gemeinschaft.de/en/
                      careers/jobs (~102 detail-links ``detail/job/show/Job/
                      <slug>``; instituto+cidade no item da listagem).
                      id = slug.
4. ``arbeitnow``    — API keyless https://www.arbeitnow.com/api/job-board-api
                      (board EU; 325 items; sem country_iso — prefilter F3
                      por marcador DE na location).
5. ``remoteok``     — API keyless https://remoteok.com/api (100 items;
                      item 0 do array = aviso legal, ignorado).
7. ``freehire``     — API keyless https://freehire.me/api/v1/jobs (feeds ATS
                      normalizados; paginacao por ``offset`` — ``page`` e
                      ``ignored_params`` no meta, fato medido 09/10).

F30 — fontes keyless nicho (probes ao vivo 13/10; robots verificados por
fonte, evidencia em docs/f30_niche_sources.md):

8.  ``amazon_jobs``  — Amazon jobs board, search.json publico sem auth
                      (https://www.amazon.jobs/en/search.json?...
                      &normalized_country_code[]=DEU&result_limit=100).
                      704 vagas DE (13/10); schema rico com description
                      inline e company_name real por entidade legal
                      (probe: "Amazon Logistik Winsen GmbH"); prefilter
                      client-side (o filtro server-side ``category=
                      internship``/``is_intern`` e IGNORADO pela API —
                      probe 13/10). Country: ``country_code`` e alpha-3
                      ("DEU") — o adapter converte para alpha-2 "de"
                      (dado da fonte; prefilter/funil so conhecem alpha-2,
                      fato medido: is_country_row("DEU", ...)=False).
9.  ``jobmensa``     — Jobmensa (jobvalley), sitemap publico ANNUNCIADO
                      no proprio robots.txt (jobsearch_jobs.xml.gz; 1781
                      URLs de vagas, probe 13/10). Sem lastmod por URL —
                      prefilter pelo slug do ultimo segmento (marcador de
                      estagio no texto do slug) e materializacao do titulo
                      SEM detail fetch (padrao Leibniz: board de
                      Werkstudentenjobs; a maioria absoluta e werkstudent
                      puro, morto pela aplicabilidade F18 — ver A/B).
10. ``absolventa``  — ABSOLVENTA.de, canal ``materialwirtschaft`` com
                      filtro server-side ``positions[]=praktikum&positions
                      []=werkstudent`` (91 vagas, probe 13/10 — nicho
                      exato Supply Chain/Einkauf do projeto). Cards HTML
                      estaveis (teaser_job_offer_<id>, <h2> titulo,
                      empresa no alt do logo, CEP+cidade no <span>);
                      paginacao ``page=N`` (20 cards/pagina).
11. ``praktikum_info`` — Praktikum.info: MESMA plataforma/DB da
                      ABSOLVENTA (probe 13/10: IDs de card identicos
                      18/20, mesmos assets uno-production.imgix.net,
                      badge 2.473 ⊂ 2.554). DESLIGADA por default via
                      env (dupla contagem sem ganho — a dedup existente
                      NAO colapsa cross-host: chave (a) e escopada por
                      source, chave (b) por URL de host diferente; so a
                      chave (c) company+title+location funde, e nem toda
                      vaga tem location). Adapter existe para ligar sob
                      demanda; evidencia no relatorio.

Regras da fase (spec §0/§2):

- IDEMPOTENTE e FAIL-SOFT: fonte fora do ar -> log + ``[]`` + registro com
  status failed; NUNCA derruba o refresh (mesma regra dos estagios
  dataset/direct_fetch). O summary geral carrega ``status: failed`` so se
  TODAS falharem, ``partial`` se alguma falhar — o run segue com o que
  houver e o exit code NAO muda.
- 1 fetch/dia por fonte (o refresh roda 1x/dia), sequencial, timeout curto
  por request (``RESEARCH_HTTP_TIMEOUT`` = 30s, spec §0.7), cap de details
  por fonte (TU Berlin: 1 detail por vaga, max ``TU_BERLIN_MAX_DETAILS``).
- UA honesto (padrao F20): ``internship-finder-liveness/1.1``.
- APIs keyless: filtro DE + estagio ANTES de materializar (MESMA regra da
  F3: ``row_is_intern_candidate`` no TITULO + ``is_country_row`` — reuso
  integral, zero vocabulario novo). Portais institucionais materializam a
  listagem inteira (volume trivial: 30+20+102; o funil oficial de tipo/area
  decide o eligible — regra do dono intocada).
- Dedup: nenhuma normalizacao nova — o dedup 3-tier + tier 4 existente
  colapsa cross-fonte pelas chaves URL (b)/company+title+location (c)
  automaticamente (mesma vaga no BA e no Arbeitnow tem a MESMA URL).
- Desligar sem deploy: env var ``INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF``
  (CSV de nomes de fonte, ex.: ``"arbeitnow,remoteok"``) e lida AQUI, no
  momento da coleta — desligar uma fonte nao exige editar codigo.
"""

from __future__ import annotations

import hashlib
import html
import logging
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from internship_finder.countries import infer_country_iso
from internship_finder.dataset_source import is_country_row, row_is_intern_candidate
from internship_finder.filters import is_student_role
from internship_finder.models.job import Job

log = logging.getLogger(__name__)

# UA honesto (padrao F20).
_USER_AGENT = "internship-finder-liveness/1.1 (daily public-source fetch; contact: repo owner)"

# Timeout por REQUEST (listagem e cada detail). Spec §0.7: 30s.
RESEARCH_HTTP_TIMEOUT = 30.0

# Teto TOTAL do estagio (10 fontes F21+F30), checado ENTRE fontes. A soma
# medida dos fetchs vivos (09/10 F21) e ~45s; F30 soma ~15s medidos 13/10
# (amazon 5x2s, jobmensa 1x1s, absolventa 5x2s). O teto e folga para dias
# lentos (criterio de pronto: soma < 5 min).
RESEARCH_BUDGET_SECONDS = 300.0

# --- Endpoints (probe ao vivo 09/10: todos 200) ------------------------------
MPG_RSS_URL = "https://www.mpg.de/feeds/jobs.rss"
TU_BERLIN_LIST_URL = "https://www.jobs.tu-berlin.de/stellenausschreibungen"
TU_BERLIN_DETAIL_URL = "https://www.jobs.tu-berlin.de/stellenausschreibungen/{job_id}"
LEIBNIZ_LIST_URL = "https://www.leibniz-gemeinschaft.de/en/careers/jobs"
ARBEITNOW_API_URL = "https://www.arbeitnow.com/api/job-board-api"
REMOTEOK_API_URL = "https://remoteok.com/api"
FREEHIRE_API_URL = "https://freehire.me/api/v1/jobs"

# Caps conservadores (1 fetch/dia por fonte; detalhes sequenciais):
# TU Berlin: 1 detail por vaga da listagem (o JSON-LD traz description +
# jobLocation). A listagem tem ~20 itens/pagina (103 vagas no total, probe
# 09/10) — 20 details/dia e o limite honesto para 1 run.
TU_BERLIN_MAX_DETAILS = 20
# freehire: 100 items por request (limit=100, max aceito pela API — probe
# 09/10: limit=200 volta meta.limit=100). 1 pagina/dia.
FREEHIRE_LIMIT = 100

# Nomes canonicos das fontes (identidade no ``Job.source`` e no summary).
SOURCE_MPG = "mpg_rss"
SOURCE_TU_BERLIN = "tu_berlin"
SOURCE_LEIBNIZ = "leibniz"
SOURCE_ARBEITNOW = "arbeitnow"
SOURCE_REMOTEOK = "remoteok"
SOURCE_FREEHIRE = "freehire"

# Empresas institucionais canonicas (fato do portal, nao deducao por slug):
# os jobs pertencem a SOCIEDADE/universidade; institutos individuais (MPG
# tem ~80) nao sao identificaveis no feed sem detail fetch.
MPG_COMPANY = "Max Planck Society"
TUM_BERLIN_COMPANY = "Technische Universität Berlin"
LEIBNIZ_COMPANY = "Leibniz Association"

# Env var para desligar fontes SEM deploy (spec §2.3: flag de configuracao
# por fonte, default ON). CSV de nomes canonicos; item desconhecido e
# ignorado com log (nunca crash).
RESEARCH_SOURCES_OFF_ENV = "INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF"

# F30 — fontes DESLIGADAS por default (honestidade da spec §6: fonte sem
# yield consistente de estagios DE, ou duplicata estrutural de outra
# fonte, entra OFF por default):
#
# - ``praktikum_info``: MESMA plataforma/DB da ABSOLVENTA (probe 13/10:
#   IDs de card identicos 18/20 entre as duas listagens; mesmos assets
#   uno-production.imgix.net; badge 2.473 ⊂ 2.554 da ABSOLVENTA). Ligar as
#   duas = dupla contagem (a dedup existente nao colapsa cross-host: chave
#   (a) escopada por source, chave (b) por URL de host distinto).
# - ``jobmensa``: A/B real 13/10 (docs/f30_niche_sources.md): 1785 URLs de
#   vaga -> 187 passam no prefilter de estagio -> 0 eligible — 100% dos
#   sobreviventes de area (22) sao Werkstudent PURO por titulo, morto pela
#   aplicabilidade F18 (board da agencia jobvalley: emprega o estudante e
#   coloca em clientes; nao ha Praktikum direto). Zero-yield estrutural,
#   nao acidental — OFF com evidencia.
#
# Mecanismo: este set e o DEFAULT de configuracao (nivel de codigo, 1
# linha); a env CSV ``RESEARCH_SOURCES_OFF_ENV`` continua sendo o kill
# switch manual por cima de TUDO (qualquer fonte, on ou off por default).
# Ligar uma fonte default-OFF = remover o nome do set (deploy trivial).
F30_DEFAULT_OFF_SOURCES: frozenset[str] = frozenset({
    "praktikum_info",
    "jobmensa",
})

# F30 — endpoints (robots verificados 13/10: nenhum path-alvo bloqueado,
# sem Crawl-delay; evidencia em docs/f30_niche_sources.md):
AMAZON_SEARCH_URL = "https://www.amazon.jobs/en/search.json"
JOBMENSA_SITEMAP_URL = "https://www.jobmensa.de/sitemaps/jobsearch_jobs.xml.gz"
ABSOLVENTA_JOBS_URL = "https://www.absolventa.de/jobs/channel/materialwirtschaft"
PRAKTIKUM_INFO_URL = "https://www.praktikum.info/stellenangebote"

# F30 — caps conservadores (<=5 paginas/fonte, spec §2):
# Amazon: result_limit=100/pagina; 704 vagas DE (13/10) -> 5 paginas
# cobrem 500 (recent-first por sort=recent — as mais novas primeiro).
AMAZON_PAGES = 5
AMAZON_PAGE_SIZE = 100
# Jobmensa: sitemap inteiro em 1 request (53KB gz); sem detail fetch.
# ABSOLVENTA: 20 cards/pagina; canal materialwirtschaft tem 91 vagas com
# positions[]=praktikum+werkstudent (13/10) -> 5 paginas cobrem 100 > 91.
ABSOLVENTA_PAGES = 5

# Nomes canonicos das fontes F30 (identidade no ``Job.source`` e summary).
SOURCE_AMAZON_JOBS = "amazon_jobs"
SOURCE_JOBMENSA = "jobmensa"
SOURCE_ABSOLVENTA = "absolventa"
SOURCE_PRAKTIKUM_INFO = "praktikum_info"

# Jobmensa e operada pela jobvalley (Studitemps) — ``hiringOrganization``
# do JSON-LD de AMBOS os details do probe 13/10 (/jobs/ex/ e /jobs/in/):
# "jobvalley" (modelo de agencia de studentenjobs: jobvalley emprega e
# coloca). Sem detail fetch nao ha empresa-cliente por vaga — a vaga e
# materializada pelo operador do board (evidencia no relatorio F30).
JOBMENSA_COMPANY = "jobvalley"


# ---------------------------------------------------------------------------
# Transporte (urllib stdlib — mesma dependencia zero do dataset_source)
# ---------------------------------------------------------------------------


def _http_get(
    url: str,
    *,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
) -> str | None:
    """GET texto; ``None`` em qualquer falha (fail-soft, 1 tentativa).

    1 tentativa por request (sem retry agressivo — rate limit conservador
    para portais publicos; a fonte tenta de novo no run do dia seguinte).
    O opener injetavel serve aos testes (fixtures offline, zero HTTP).
    """
    if opener is not None:
        try:
            return str(opener(urllib.request.Request(url)))
        except Exception as exc:  # noqa: BLE001
            log.warning("research_sources: GET %s falhou: %s", url.split("?")[0], exc)
            return None
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - fail-soft
        log.warning("research_sources: GET %s falhou: %s", url.split("?")[0], exc)
        return None


def _sha16(text: str) -> str:
    """Hash sha1 16-hex (mesma regra do ``AtsJobAdapter._make_id``/F3)."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _parse_dt(value: Any) -> datetime | None:
    """Parse tolerante: ISO 8601 (``Z`` -> ``+00:00``) OU RFC 822 (RSS
    ``pubDate``, ex.: ``Thu, 08 Oct 2026 13:46:00 +0200``). Nunca crash."""
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(s)
    except Exception:  # noqa: BLE001
        return None


def _clean(value: Any) -> str | None:
    """String normalizada (strip); vazio/None -> ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _html_to_text(value: str | None, limit: int = 25000) -> str | None:
    """HTML cru -> texto plano (mesma heuristica do direct_fetch/EURES)."""
    if not value:
        return None
    text = html.unescape(value)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text.strip()[:limit] or None


# ---------------------------------------------------------------------------
# 1. Max Planck Society — RSS (parse XML trivial)
# ---------------------------------------------------------------------------


def _mpg_item_to_job(item: ET.Element) -> Job | None:
    """Item RSS MPG -> Job (None se sem title/link)."""
    title = _clean(item.findtext("title"))
    link = _clean(item.findtext("link"))
    if not title or not link:
        return None
    description = _html_to_text(item.findtext("description"))
    # id estavel da fonte = URL do item (spec da fase); guid do feed carrega
    # sufixo de cache (?<ts>) — o <link> limpo e a chave estavel.
    job = Job(
        id=f"{MPG_COMPANY}|{SOURCE_MPG}:{_sha16(link)}",
        source=SOURCE_MPG,
        title=title,
        company=MPG_COMPANY,
        location=None,
        country="de",
        url=link,
        description=description,
        internship=is_student_role(title, description, None),
        posted_at=_parse_dt(item.findtext("pubDate")),
        collected_at=datetime.now(UTC),
        external_id=link,
        country_iso="de",
        raw=None,
    )
    return job


def parse_mpg_rss(xml_text: str) -> list[Job]:
    """XML RSS do MPG -> ``list[Job]`` (itens validos).

    Parse ``xml.etree`` (stdlib) — o feed e RSS 2.0 valido (probe 09/10:
    30 itens). Malformado -> ``[]`` com log (fail-soft).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("research_sources: mpg_rss XML malformado (%s)", exc)
        return []
    jobs: list[Job] = []
    for item in root.iter("item"):
        try:
            job = _mpg_item_to_job(item)
        except Exception as exc:  # noqa: BLE001 - item ruim nao derruba o resto
            log.warning("research_sources: mpg_rss item invalido (%s)", exc)
            continue
        if job is not None:
            jobs.append(job)
    return jobs


def fetch_mpg_rss(
    *,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    url: str = MPG_RSS_URL,
) -> tuple[list[Job], dict[str, Any]]:
    """RSS do MPG -> ``(jobs, stats)``. Fail-soft: falha = ``[]`` + status."""
    stats: dict[str, Any] = {
        "source": SOURCE_MPG, "status": "ok", "rows_seen": 0,
        "jobs": 0, "details_ok": 0, "details_failed": 0, "error": None,
    }
    text = _http_get(url, timeout=timeout, opener=opener)
    if text is None:
        stats["status"] = "failed"
        stats["error"] = "fetch falhou"
        return [], stats
    jobs = parse_mpg_rss(text)
    stats["rows_seen"] = len(jobs)
    stats["jobs"] = len(jobs)
    if not jobs:
        stats["status"] = "failed"
        stats["error"] = "nenhum item parseado"
    return jobs, stats


# ---------------------------------------------------------------------------
# 2. TU Berlin — listagem HTML + detail com JSON-LD JobPosting
# ---------------------------------------------------------------------------

# Detail: JSON-LD JobPosting embutido (probe 09/10): title, description
# (HTML), datePosted, validThrough, employmentType[], jobLocation[].address
# (addressLocality/Region/Country), identifier.value (codigo da vaga).
_TU_ITEM_RE = re.compile(
    r'<a\s+href="(/stellenausschreibungen/(\d+))"\s*>(.*?)</a>', re.DOTALL
)
_TU_JSONLD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL
)


def parse_tu_berlin_listing(html_text: str) -> list[dict[str, str]]:
    """Listagem HTML -> ``[{job_id, url, title}]`` (ordem do documento).

    Estrutura estavel (probe 09/10): ``<li>`` com ``<h2>`` e anchor
    ``/stellenausschreibungen/<id>``; 20 itens/pagina.
    """
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _TU_ITEM_RE.finditer(html_text):
        path, job_id, raw_title = m.group(1), m.group(2), m.group(3)
        if job_id in seen:
            continue
        title = _html_to_text(raw_title)
        if not title:
            continue
        seen.add(job_id)
        items.append({
            "job_id": job_id,
            "url": f"https://www.jobs.tu-berlin.de{path}",
            "title": title,
        })
    return items


def parse_tu_berlin_detail(
    html_text: str, fallback_title: str | None = None,
) -> dict[str, Any] | None:
    """Detail HTML -> campos do JSON-LD JobPosting (ou None se ausente)."""
    import json

    m = _TU_JSONLD_RE.search(html_text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("@type") != "JobPosting":
        return None

    address = None
    locality = region = country = None
    locations = data.get("jobLocation")
    if isinstance(locations, list) and locations:
        addr = (locations[0] or {}).get("address") or {}
        if isinstance(addr, dict):
            locality = _clean(addr.get("addressLocality"))
            region = _clean(addr.get("addressRegion"))
            country = _clean(addr.get("addressCountry"))
            parts = [p for p in (locality, region, country) if p]
            address = ", ".join(parts) or None

    employment_type = None
    et = data.get("employmentType")
    if isinstance(et, list) and et:
        employment_type = str(et[0]).strip() or None
    elif isinstance(et, str) and et.strip():
        employment_type = et.strip()

    identifier = None
    ident = data.get("identifier")
    if isinstance(ident, dict):
        identifier = _clean(ident.get("value"))

    return {
        "title": _clean(data.get("title")) or fallback_title,
        "description": _html_to_text(data.get("description")),
        "location": address,
        "country_name": country,
        "employment_type": employment_type,
        "date_posted": _parse_dt(data.get("datePosted")),
        "valid_through": _parse_dt(data.get("validThrough")),
        "identifier": identifier,
    }


def fetch_tu_berlin(
    *,
    max_details: int = TU_BERLIN_MAX_DETAILS,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    list_url: str = TU_BERLIN_LIST_URL,
    detail_url_template: str = TU_BERLIN_DETAIL_URL,
) -> tuple[list[Job], dict[str, Any]]:
    """TU Berlin -> ``(jobs, stats)``: listagem + 1 detail por vaga (cap).

    Detail por vaga traz a description (o corpo carrega o marcador de
    estudante — ``studentische Hilfskraft`` — que o ``is_student_role``
    consome; probe 09/10: is_student_role(title, corpo)=True para vagas
    ``Studentische Beschaeftigung``) e o jobLocation (Berlin/Deutschland).
    Detail falho -> vaga da listagem SEM description (nao derruba).
    """
    stats: dict[str, Any] = {
        "source": SOURCE_TU_BERLIN, "status": "ok", "rows_seen": 0,
        "jobs": 0, "details_ok": 0, "details_failed": 0, "error": None,
    }
    html_text = _http_get(list_url, timeout=timeout, opener=opener)
    if html_text is None:
        stats["status"] = "failed"
        stats["error"] = "listagem falhou"
        return [], stats
    listing = parse_tu_berlin_listing(html_text)
    stats["rows_seen"] = len(listing)
    if not listing:
        stats["status"] = "failed"
        stats["error"] = "nenhuma vaga na listagem"
        return [], stats

    jobs: list[Job] = []
    for entry in listing[:max_details]:
        detail_text = _http_get(
            detail_url_template.format(job_id=entry["job_id"]),
            timeout=timeout, opener=opener,
        )
        detail: dict[str, Any] | None = None
        if detail_text is not None:
            detail = parse_tu_berlin_detail(detail_text, fallback_title=entry["title"])
        if detail is not None:
            stats["details_ok"] += 1
        else:
            stats["details_failed"] += 1

        title = (detail or {}).get("title") or entry["title"]
        description = (detail or {}).get("description")
        location = (detail or {}).get("location")
        employment_type = (detail or {}).get("employment_type")
        posted_at = (detail or {}).get("date_posted")
        deadline = (detail or {}).get("valid_through")
        # ISO: jobLocation.address.addressCountry ("Deutschland") — dado da
        # fonte; fallback da instituicao (TU Berlin = DE) quando detail falha.
        iso = infer_country_iso(location=location, country_iso="de")
        job = Job(
            id=f"{TUM_BERLIN_COMPANY}|{SOURCE_TU_BERLIN}:{entry['job_id']}",
            source=SOURCE_TU_BERLIN,
            title=title,
            company=TUM_BERLIN_COMPANY,
            location=location or "Berlin",
            country=iso,
            url=entry["url"],
            description=description,
            internship=is_student_role(title, description, employment_type),
            posted_at=posted_at,
            collected_at=datetime.now(UTC),
            external_id=entry["job_id"],
            employment_type=employment_type,
            application_deadline=deadline,
            country_iso=iso,
            raw=None,
        )
        jobs.append(job)

    stats["jobs"] = len(jobs)
    return jobs, stats


# ---------------------------------------------------------------------------
# 3. Leibniz Association — TYPO3 (listagem com instituto+cidade)
# ---------------------------------------------------------------------------

# Item da listagem (probe 09/10): <h4> com anchor detail/job/show/Job/<slug>
# e <p class="mono-i1"> com "Instituto, Cidade" (ex.: "Senckenberg ... (SGN),
# Frankfurt am Main").
_LEIBNIZ_ITEM_RE = re.compile(
    r'<a\s+class="link"\s+href="([^"]*detail/job/show/Job/([^"]+))"\s*>(.*?)</a>'
    r'.{0,400}?<p\s+class="mono-i1">\s*(.*?)\s*</p>',
    re.DOTALL,
)


def parse_leibniz_listing(html_text: str) -> list[dict[str, str]]:
    """Listagem Leibniz -> ``[{slug, url, title, company, location}]``.

    Instituto+cidade vem juntos no ``<p class="mono-i1">``; split na ULTIMA
    virgula (cidades com virgula no nome nao existem no padrao observado;
    sem virgula -> tudo e company, location=None).
    """
    base = "https://www.leibniz-gemeinschaft.de"
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _LEIBNIZ_ITEM_RE.finditer(html_text):
        path, slug, raw_title, raw_org = m.group(1), m.group(2), m.group(3), m.group(4)
        if slug in seen:
            continue
        title = _html_to_text(raw_title)
        if not title:
            continue
        seen.add(slug)
        org = _html_to_text(raw_org) or ""
        company, location = org, None
        if "," in org:
            head, _, tail = org.rpartition(",")
            company, location = head.strip() or org, tail.strip() or None
        url = path if path.startswith("http") else f"{base}{path}"
        items.append({
            "slug": slug, "url": url, "title": title,
            "company": company or LEIBNIZ_COMPANY, "location": location or "",
        })
    return items


def fetch_leibniz(
    *,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    list_url: str = LEIBNIZ_LIST_URL,
) -> tuple[list[Job], dict[str, Any]]:
    """Leibniz -> ``(jobs, stats)``: 1 fetch da listagem (sem detail).

    102 links (probe 09/10) materializados sem detail fetch (detail = 9s
    cada, 102 = 15 min — fora do orcamento diario). Description ausente: o
    filtro de tipo consome o TITULO (``Student Assistant``/``Internship``
    casam o vocabulario canonico); institutos DE.
    """
    stats: dict[str, Any] = {
        "source": SOURCE_LEIBNIZ, "status": "ok", "rows_seen": 0,
        "jobs": 0, "details_ok": 0, "details_failed": 0, "error": None,
    }
    html_text = _http_get(list_url, timeout=timeout, opener=opener)
    if html_text is None:
        stats["status"] = "failed"
        stats["error"] = "listagem falhou"
        return [], stats
    items = parse_leibniz_listing(html_text)
    stats["rows_seen"] = len(items)
    if not items:
        stats["status"] = "failed"
        stats["error"] = "nenhuma vaga na listagem"
        return [], stats

    jobs: list[Job] = []
    for item in items:
        company = item["company"] or LEIBNIZ_COMPANY
        # Portal institucional ALEMAO (Associação Leibniz): institutos
        # membros DE (enderecos observados na listagem: Frankfurt am Main,
        # Hamburg...). Location da listagem e so a cidade — o ISO vem da
        # fonte (constante do portal), documentado no relatorio.
        iso = "de"
        job = Job(
            id=f"{company}|{SOURCE_LEIBNIZ}:{_sha16(item['slug'])}",
            source=SOURCE_LEIBNIZ,
            title=item["title"],
            company=company,
            location=item["location"] or None,
            country=iso,
            url=item["url"],
            description=None,
            internship=is_student_role(item["title"], None, None),
            collected_at=datetime.now(UTC),
            external_id=item["slug"],
            country_iso=iso,
            raw=None,
        )
        jobs.append(job)
    stats["jobs"] = len(jobs)
    return jobs, stats


# ---------------------------------------------------------------------------
# 4. Arbeitnow — API keyless (board EU; prefilter DE + estagio)
# ---------------------------------------------------------------------------


def parse_arbeitnow(payload: dict[str, Any]) -> tuple[list[Job], int, int]:
    """Payload Arbeitnow -> ``(jobs, rows, invalid)``.

    Schema (probe 09/10): ``{"data": [...], "meta": {...}}``; item:
    slug/title/company_name/location/description/job_types[]/remote/tags[].
    PREFILTER F3 no TITULO antes de materializar (spec: mesma regra da F3 —
    marcador de estagio). Pais: o board Arbeitnow e ALEMAO por definicao
    (Berlin-based; locations sao cidades sem marcador de pais — probe
    09/10: "Muenchen", "Berlin, Berlin", "Duesseldorf und Remote"), entao o
    ISO vem da FONTE (constante do board, documentada) e o funil re-confere
    via ``matches_country`` como faz com qualquer job.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return [], 0, 0
    jobs: list[Job] = []
    rows = invalid = 0
    for it in data:
        if not isinstance(it, dict):
            continue
        rows += 1
        title = _clean(it.get("title")) or ""
        location = _clean(it.get("location"))
        remote = bool(it.get("remote"))
        if not row_is_intern_candidate(title):
            continue
        company = _clean(it.get("company_name"))
        url = _clean(it.get("url")) or (
            f"https://www.arbeitnow.com/jobs/{_clean(it.get('slug'))}"
            if _clean(it.get("slug")) else None
        )
        if not company or not url:
            invalid += 1
            continue
        employment_type = None
        jt = it.get("job_types")
        if isinstance(jt, list) and jt:
            employment_type = str(jt[0]).strip() or None
        description = _html_to_text(it.get("description"))
        # ISO: board Arbeitnow e alemao por definicao (Berlin-based, vagas
        # DE; probe 09/10: locations sao cidades sem marcador de pais —
        # "Muenchen", "Berlin, Berlin", "Duesseldorf und Remote"). O pais
        # vem da FONTE (constante do board), nao da inferencia de texto; o
        # funil re-confere via matches_country como faz com qualquer job.
        iso = "de"
        job = Job(
            id=f"{company}|{SOURCE_ARBEITNOW}:{_sha16(url)}",
            source=SOURCE_ARBEITNOW,
            title=title,
            company=company,
            location=location,
            country=iso,
            url=url,
            description=description,
            internship=is_student_role(title, description, employment_type),
            posted_at=_parse_dt(it.get("created_at")),
            collected_at=datetime.now(UTC),
            external_id=_clean(it.get("slug")),
            employment_type=employment_type,
            country_iso=iso,
            remote=remote,
            raw=None,
        )
        jobs.append(job)
    return jobs, rows, invalid


def fetch_arbeitnow(
    *,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    url: str = ARBEITNOW_API_URL,
) -> tuple[list[Job], dict[str, Any]]:
    """Arbeitnow -> ``(jobs, stats)``. 1 request (board inteiro)."""
    stats: dict[str, Any] = {
        "source": SOURCE_ARBEITNOW, "status": "ok", "rows_seen": 0,
        "jobs": 0, "invalid_rows": 0, "details_ok": 0, "details_failed": 0,
        "error": None,
    }
    text = _http_get(url, timeout=timeout, opener=opener)
    if text is None:
        stats["status"] = "failed"
        stats["error"] = "fetch falhou"
        return [], stats
    import json

    try:
        payload = json.loads(text)
    except ValueError:
        stats["status"] = "failed"
        stats["error"] = "JSON malformado"
        return [], stats
    jobs, rows, invalid = parse_arbeitnow(payload)
    stats.update({"rows_seen": rows, "jobs": len(jobs), "invalid_rows": invalid})
    return jobs, stats


# ---------------------------------------------------------------------------
# 5. RemoteOK — API keyless (remote jobs; prefilter DE + estagio)
# ---------------------------------------------------------------------------


def parse_remoteok(payload: list[Any]) -> tuple[list[Job], int, int]:
    """Payload RemoteOK -> ``(jobs, rows, invalid)``.

    Schema (probe 09/10): ARRAY; item 0 = aviso legal (sem ``position``) —
    ignorado. Item: position/company/slug/url/location/description/tags[].
    Board REMOTO por natureza: prefilter aceita marcador de estagio no
    TITULO + (DE OU remote) — jobs remotos sem pais entram com
    ``remote=True`` e o filtro ``--country remote`` do funil os alcancam;
    jobs DE sao alcancados pelo escopo multi-pais da producao.
    """
    jobs: list[Job] = []
    rows = invalid = 0
    for it in payload:
        if not isinstance(it, dict) or not it.get("position"):
            continue  # aviso legal / item invalido
        rows += 1
        title = _clean(it.get("position")) or ""
        location = _clean(it.get("location"))
        remote = True  # board 100% remoto (definicao da fonte)
        if not row_is_intern_candidate(title):
            continue
        iso = infer_country_iso(location=location)
        if iso not in ("de", None):
            continue  # pais explicito nao-DE fora do escopo alvo
        company = _clean(it.get("company"))
        url = _clean(it.get("url")) or (
            f"https://remoteok.com/remote-jobs/{_clean(it.get('slug'))}"
            if _clean(it.get("slug")) else None
        )
        if not company or not url:
            invalid += 1
            continue
        description = _html_to_text(it.get("description"))
        posted_at = _parse_dt(it.get("date"))
        job = Job(
            id=f"{company}|{SOURCE_REMOTEOK}:{_sha16(url)}",
            source=SOURCE_REMOTEOK,
            title=title,
            company=company,
            location=location,
            country=iso,
            url=url,
            description=description,
            internship=is_student_role(title, description, None),
            posted_at=posted_at,
            collected_at=datetime.now(UTC),
            external_id=_clean(it.get("slug")),
            country_iso=iso,
            remote=remote,
            raw=None,
        )
        jobs.append(job)
    return jobs, rows, invalid


def fetch_remoteok(
    *,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    url: str = REMOTEOK_API_URL,
) -> tuple[list[Job], dict[str, Any]]:
    """RemoteOK -> ``(jobs, stats)``. 1 request (100 itens)."""
    stats: dict[str, Any] = {
        "source": SOURCE_REMOTEOK, "status": "ok", "rows_seen": 0,
        "jobs": 0, "invalid_rows": 0, "details_ok": 0, "details_failed": 0,
        "error": None,
    }
    text = _http_get(url, timeout=timeout, opener=opener)
    if text is None:
        stats["status"] = "failed"
        stats["error"] = "fetch falhou"
        return [], stats
    import json

    try:
        payload = json.loads(text)
    except ValueError:
        stats["status"] = "failed"
        stats["error"] = "JSON malformado"
        return [], stats
    if not isinstance(payload, list):
        stats["status"] = "failed"
        stats["error"] = "schema inesperado (nao-array)"
        return [], stats
    jobs, rows, invalid = parse_remoteok(payload)
    stats.update({"rows_seen": rows, "jobs": len(jobs), "invalid_rows": invalid})
    return jobs, stats


# ---------------------------------------------------------------------------
# 6. freehire — API keyless (feeds ATS normalizados; prefilter DE + estagio)
# ---------------------------------------------------------------------------


def parse_freehire(payload: dict[str, Any]) -> tuple[list[Job], int, int]:
    """Payload freehire -> ``(jobs, rows, invalid)``.

    Schema (probe 09/10): ``{"data": [...], "meta": {limit, offset,
    total, ignored_params}}``; item: public_slug/source/external_id/url/
    title/company/company_slug/location/countries[]/regions[]/description/
    posted_at/enrichment{seniority,category,posting_language}.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return [], 0, 0
    jobs: list[Job] = []
    rows = invalid = 0
    for it in data:
        if not isinstance(it, dict):
            continue
        rows += 1
        title = _clean(it.get("title")) or ""
        if not row_is_intern_candidate(title):
            continue
        countries = it.get("countries")
        iso_raw = str(countries[0]).strip().lower() if (
            isinstance(countries, list) and countries
        ) else None
        location = _clean(it.get("location"))
        if not is_country_row(iso_raw, location, ("de",)):
            continue
        company = _clean(it.get("company"))
        url = _clean(it.get("url")) or (
            f"https://freehire.me/jobs/{_clean(it.get('public_slug'))}"
            if _clean(it.get("public_slug")) else None
        )
        if not company or not url:
            invalid += 1
            continue
        description = _html_to_text(it.get("description"))
        iso = infer_country_iso(location=location, country_iso=iso_raw)
        job = Job(
            id=f"{company}|{SOURCE_FREEHIRE}:{_sha16(url)}",
            source=SOURCE_FREEHIRE,
            title=title,
            company=company,
            location=location,
            country=iso,
            url=url,
            description=description,
            internship=is_student_role(title, description, None),
            posted_at=_parse_dt(it.get("posted_at")),
            collected_at=datetime.now(UTC),
            external_id=_clean(it.get("public_slug")) or _clean(it.get("external_id")),
            country_iso=iso,
            raw=None,
        )
        jobs.append(job)
    return jobs, rows, invalid


def fetch_freehire(
    *,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    url: str = FREEHIRE_API_URL,
    limit: int = FREEHIRE_LIMIT,
) -> tuple[list[Job], dict[str, Any]]:
    """freehire -> ``(jobs, stats)``. 1 request (``limit`` items)."""
    stats: dict[str, Any] = {
        "source": SOURCE_FREEHIRE, "status": "ok", "rows_seen": 0,
        "jobs": 0, "invalid_rows": 0, "details_ok": 0, "details_failed": 0,
        "error": None,
    }
    from urllib.parse import urlencode

    full_url = f"{url}?{urlencode({'limit': limit})}"
    text = _http_get(full_url, timeout=timeout, opener=opener)
    if text is None:
        stats["status"] = "failed"
        stats["error"] = "fetch falhou"
        return [], stats
    import json

    try:
        payload = json.loads(text)
    except ValueError:
        stats["status"] = "failed"
        stats["error"] = "JSON malformado"
        return [], stats
    jobs, rows, invalid = parse_freehire(payload)
    stats.update({"rows_seen": rows, "jobs": len(jobs), "invalid_rows": invalid})
    return jobs, stats


# ---------------------------------------------------------------------------
# 7. Amazon jobs — search.json publico (F30; prefilter DE + estagio)
# ---------------------------------------------------------------------------

# alpha-3 -> alpha-2 do pais (dado da fonte Amazon: country_code e alpha-3,
# ex. "DEU" — fato medido 13/10: is_country_row("DEU", ...)=False, o
# prefilter/funil so conhecem alpha-2). Mapa minimo das aparicoes reais
# do board (probe 13/10): DEU/LUX/NLD/BEL/GBR etc. — desconhecido = None
# (a linha NAO passa no prefilter de pais, honesto).
_AMAZON_ALPHA3_TO_ISO = {
    "deu": "de", "lux": "lu", "nld": "nl", "bel": "be", "fin": "fi",
    "gbr": "gb", "fra": "fr", "aut": "at", "che": "ch", "ita": "it",
    "esp": "es", "pol": "pl", "cze": "cz", "irl": "ie", "swe": "se",
    "usa": "us", "can": "ca", "chn": "cn", "jpn": "jp", "ind": "in",
    "bra": "br", "aus": "au",
}


def _amazon_iso(country_code: Any) -> str | None:
    """alpha-3 do board Amazon -> ISO alpha-2 (ou None se fora do mapa)."""
    raw = _clean(country_code)
    if not raw:
        return None
    return _AMAZON_ALPHA3_TO_ISO.get(raw.strip().lower())


def parse_amazon_jobs(payload: dict[str, Any]) -> tuple[list[Job], int, int]:
    """Payload search.json Amazon -> ``(jobs, rows, invalid)``.

    Schema (probe 13/10): ``{"jobs": [...], "hits": 704, ...}``; item:
    id/id_icims/title/company_name/location/normalized_location/
    country_code/city/state/description/description_short/posted_date/
    job_path/job_category/job_schedule_type. O filtro server-side de
    internship e IGNORADO pela API (probe: ``category[]=internship`` e
    ``is_intern=1`` nao mudam o resultado) — prefilter client-side:
    marcador de estagio no TITULO + pais DE (criteria F3 reusados).
    """
    data = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return [], 0, 0
    jobs: list[Job] = []
    rows = invalid = 0
    for it in data:
        if not isinstance(it, dict):
            continue
        rows += 1
        title = _clean(it.get("title")) or ""
        if not row_is_intern_candidate(title):
            continue
        iso = _amazon_iso(it.get("country_code"))
        location = _clean(it.get("normalized_location")) or _clean(it.get("location"))
        if not is_country_row(iso, location, ("de",)):
            continue
        company = _clean(it.get("company_name")) or "Amazon"
        path = _clean(it.get("job_path"))
        url = f"https://www.amazon.jobs{path}" if path else None
        external_id = _clean(it.get("id_icims")) or _clean(it.get("id"))
        if not url or not external_id:
            invalid += 1
            continue
        description = _html_to_text(it.get("description")) or _html_to_text(
            it.get("description_short")
        )
        posted_at = _parse_dt(it.get("posted_date"))
        job = Job(
            id=f"{company}|{SOURCE_AMAZON_JOBS}:{external_id}",
            source=SOURCE_AMAZON_JOBS,
            title=title,
            company=company,
            location=location,
            country=iso,
            url=url,
            description=description,
            internship=is_student_role(title, description, it.get("job_schedule_type")),
            posted_at=posted_at,
            collected_at=datetime.now(UTC),
            external_id=external_id,
            employment_type=_clean(it.get("job_schedule_type")),
            country_iso=iso,
            raw=None,
        )
        jobs.append(job)
    return jobs, rows, invalid


def fetch_amazon_jobs(
    *,
    pages: int = AMAZON_PAGES,
    page_size: int = AMAZON_PAGE_SIZE,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    url: str = AMAZON_SEARCH_URL,
) -> tuple[list[Job], dict[str, Any]]:
    """Amazon jobs board -> ``(jobs, stats)``. Ate ``pages`` paginas (offset).

    1 request por pagina (``result_limit`` items, sort=recent); para quando
    a pagina volta com 0 items (fim do board). DE ja filtrado server-side
    (``normalized_country_code[]=DEU`` — o filtro de internship NAO existe
    server-side, probe 13/10).
    """
    import json as _json
    from urllib.parse import urlencode

    stats: dict[str, Any] = {
        "source": SOURCE_AMAZON_JOBS, "status": "ok", "rows_seen": 0,
        "jobs": 0, "invalid_rows": 0, "details_ok": 0, "details_failed": 0,
        "pages": 0, "error": None,
    }
    jobs: list[Job] = []
    seen: set[str] = set()
    for page in range(max(1, pages)):
        query = urlencode({
            "offset": page * page_size,
            "result_limit": page_size,
            "sort": "recent",
            "normalized_country_code[]": "DEU",
        })
        text = _http_get(f"{url}?{query}", timeout=timeout, opener=opener)
        if text is None:
            stats["status"] = "failed"
            stats["error"] = f"fetch falhou (pagina {page + 1})"
            break
        try:
            payload = _json.loads(text)
        except ValueError:
            stats["status"] = "failed"
            stats["error"] = f"JSON malformado (pagina {page + 1})"
            break
        page_jobs, rows, invalid = parse_amazon_jobs(payload)
        stats["rows_seen"] += rows
        stats["invalid_rows"] += invalid
        stats["pages"] += 1
        fresh = [j for j in page_jobs if j.external_id not in seen]
        for j in fresh:
            seen.add(j.external_id or "")
        jobs.extend(fresh)
        if not page_jobs and not payload.get("jobs"):
            break  # fim do board: pagina vazia
    stats["jobs"] = len(jobs)
    if stats["pages"] == 0 and stats["status"] == "ok":
        stats["status"] = "failed"
        stats["error"] = "nenhuma pagina obtida"
    return jobs, stats


# ---------------------------------------------------------------------------
# 8. Jobmensa — sitemap publico (F30; prefilter por slug, sem detail)
# ---------------------------------------------------------------------------


def parse_jobmensa_sitemap(xml_text: str) -> tuple[list[Job], int, int]:
    """Sitemap XML Jobmensa -> ``(jobs, urls, kept)``.

    Sitemap ANNUNCIADO no robots.txt (jobsearch_jobs.xml.gz; 1781 URLs,
    probe 13/10). Cada ``<loc>`` de vaga carrega o titulo no slug do
    ultimo segmento — prefilter de marcador de estagio sobre o texto do
    slug ANTES de materializar (mesma regra F3; zero detail fetch: board
    de Werkstudentenjobs, o funil decide o resto — padrao Leibniz).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("research_sources: jobmensa sitemap malformado (%s)", exc)
        return [], 0, 0
    jobs: list[Job] = []
    urls = kept = 0
    for loc_el in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}url"):
        loc = _clean(loc_el.findtext(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"))
        if not loc or "/jobs/" not in loc:
            continue
        urls += 1
        slug = loc.rstrip("/").rsplit("/", 1)[-1]
        if not slug:
            continue
        title = slug.replace("-", " ")
        if not row_is_intern_candidate(title):
            continue
        kept += 1
        job = Job(
            id=f"{JOBMENSA_COMPANY}|{SOURCE_JOBMENSA}:{_sha16(loc)}",
            source=SOURCE_JOBMENSA,
            title=title,
            company=JOBMENSA_COMPANY,
            location=None,
            country="de",
            url=loc,
            description=None,
            internship=is_student_role(title, None, None),
            collected_at=datetime.now(UTC),
            external_id=slug,
            country_iso="de",
            raw=None,
        )
        jobs.append(job)
    return jobs, urls, kept


def fetch_jobmensa(
    *,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    url: str = JOBMENSA_SITEMAP_URL,
) -> tuple[list[Job], dict[str, Any]]:
    """Jobmensa -> ``(jobs, stats)``: 1 request do sitemap .gz (sem detail)."""
    import gzip as _gzip

    stats: dict[str, Any] = {
        "source": SOURCE_JOBMENSA, "status": "ok", "rows_seen": 0,
        "jobs": 0, "invalid_rows": 0, "details_ok": 0, "details_failed": 0,
        "error": None,
    }
    body = None
    if opener is not None:
        try:
            body = opener(urllib.request.Request(url))
            body = body.encode("utf-8") if isinstance(body, str) else body
        except Exception as exc:  # noqa: BLE001
            log.warning("research_sources: GET %s falhou: %s", url.split("?")[0], exc)
            body = None
    else:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except Exception as exc:  # noqa: BLE001 - fail-soft
            log.warning("research_sources: GET %s falhou: %s", url.split("?")[0], exc)
            body = None
    if body is None:
        stats["status"] = "failed"
        stats["error"] = "fetch falhou"
        return [], stats
    try:
        xml_text = _gzip.decompress(body).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - gz corrompido = fonte falhou
        stats["status"] = "failed"
        stats["error"] = f"gzip invalido: {exc}"
        return [], stats
    jobs, urls, kept = parse_jobmensa_sitemap(xml_text)
    stats.update({"rows_seen": urls, "jobs": len(jobs), "invalid_rows": urls - kept})
    if not urls:
        stats["status"] = "failed"
        stats["error"] = "sitemap sem URLs de vagas"
    return jobs, stats


# ---------------------------------------------------------------------------
# 9. ABSOLVENTA — canal materialwirtschaft + positions (F30; plataforma uno)
# ---------------------------------------------------------------------------

# Card estavel (probe 13/10): anchor teaser_job_offer_<id> com href
# /stellenangebote/<id>-<x>-<slug> onde <x> e um sufixo de TIPO de vaga —
# "p" nas paginas 1-2, "b" da pagina 3 em diante (fato medido 13/10;
# sem significado documentado, aceitamos [a-z]). <h2> carrega o titulo;
# empresa no alt do logo ("<Empresa> Logo"); CEP+cidade no <span> dentro
# do <li> de Standort.
_UNO_CARD_RE = re.compile(
    r'<a[^>]*id="teaser_job_offer_(\d+)"[^>]*href="/stellenangebote/(\d+)-([a-z])-([a-z0-9-]+)"(.*?)</a>',
    re.DOTALL,
)
_UNO_LOCATION_RE = re.compile(r"<span>(\d{5})\s*<span>([^<]+)</span></span>")


def _parse_uno_listing(html_text: str, source: str) -> list[Job]:
    """Listagem HTML da plataforma uno (ABSOLVENTA/Praktikum.info) -> Jobs.

    Board DE por definicao (vagas de empresas DE com CEP alemao; o funil
    re-confere via matches_country). Sem description no card: o filtro de
    tipo consome o TITULO (marcador no <h2>), padrao Leibniz.
    """
    jobs: list[Job] = []
    for card_id, _jid, kind, slug, block in _UNO_CARD_RE.findall(html_text):
        h2 = re.search(r"<h2[^>]*>(.*?)</h2>", block, re.DOTALL)
        title = _html_to_text(h2.group(1)) if h2 else None
        if not title:
            continue
        if not row_is_intern_candidate(title):
            continue
        # Empresa: o <span> de texto do card carrega o NOME LEGAL completo
        # (probe 13/10: "Lidl Stiftung & Co. KG" — o alt do logo so traz o
        # nome curto "Lidl"); fallback = alt do logo.
        comp = re.search(
            r'<span class="text-secondary[^"]*">(.*?)</span>', block, re.DOTALL
        )
        company = _html_to_text(comp.group(1)) if comp else None
        if not company:
            alt = re.search(r'alt="([^"]+?)\s+Logo"', block)
            company = _html_to_text(alt.group(1)) if alt else None
        loc = _UNO_LOCATION_RE.search(block)
        location = f"{loc.group(1)} {loc.group(2)}" if loc else None
        host = "www.absolventa.de" if source == SOURCE_ABSOLVENTA else "www.praktikum.info"
        url = f"https://{host}/stellenangebote/{card_id}-{kind}-{slug}"
        job = Job(
            id=f"{company or source}|{source}:{card_id}",
            source=source,
            title=title,
            company=company or source,
            location=location,
            country="de",
            url=url,
            description=None,
            internship=is_student_role(title, None, None),
            collected_at=datetime.now(UTC),
            external_id=card_id,
            country_iso="de",
            raw=None,
        )
        jobs.append(job)
    return jobs


def _fetch_uno_pages(
    *,
    base_url: str,
    source: str,
    pages: int,
    timeout: float,
    opener: Callable[[urllib.request.Request], Any] | None,
) -> tuple[list[Job], dict[str, Any]]:
    """Mecanismo comum ABSOLVENTA/Praktikum.info: paginacao page=N.

    Fato medido 13/10 (debug pos-probe): ``urlencode`` com lista PRECISA de
    ``doseq=True`` — sem ele a query serializa a string literal
    ``['praktikum', 'werkstudent']`` e o servidor ignora o filtro (board
    sem prefilter = 0 jobs). A paginacao do Praktikum.info vive em
    ``/stellenangebote?page=N`` (o path ``/praktikum/angebote`` ignora o
    param ``page`` — overlap 20/20 medido entre page=1 e page=2); o
    default de ``base_url`` ja aponta o caminho paginavel.
    """
    from urllib.parse import urlencode

    stats: dict[str, Any] = {
        "source": source, "status": "ok", "rows_seen": 0,
        "jobs": 0, "invalid_rows": 0, "details_ok": 0, "details_failed": 0,
        "pages": 0, "error": None,
    }
    jobs: list[Job] = []
    seen: set[str] = set()
    for page in range(1, max(1, pages) + 1):
        query = urlencode({
            "positions[]": ["praktikum", "werkstudent"],
            "page": page,
        }, doseq=True)
        text = _http_get(f"{base_url}?{query}", timeout=timeout, opener=opener)
        if text is None:
            stats["status"] = "failed"
            stats["error"] = f"fetch falhou (pagina {page})"
            break
        page_jobs = _parse_uno_listing(text, source)
        fresh = [j for j in page_jobs if j.external_id not in seen]
        for j in fresh:
            seen.add(j.external_id or "")
        jobs.extend(fresh)
        stats["rows_seen"] += len(page_jobs)
        stats["pages"] += 1
        if not page_jobs:
            break  # fim das vagas do canal
    stats["jobs"] = len(jobs)
    if stats["pages"] == 0 and stats["status"] == "ok":
        stats["status"] = "failed"
        stats["error"] = "nenhuma pagina obtida"
    return jobs, stats


def fetch_absolventa(
    *,
    pages: int = ABSOLVENTA_PAGES,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    url: str = ABSOLVENTA_JOBS_URL,
) -> tuple[list[Job], dict[str, Any]]:
    """ABSOLVENTA canal materialwirtschaft -> ``(jobs, stats)``.

    Canal de Einkauf/Logistik/Materialwirtschaft com filtro server-side
    positions[]=praktikum+werkstudent (91 vagas, probe 13/10) — nicho
    exato do projeto. 5 paginas cobrem o canal inteiro (20 cards/pagina).
    """
    return _fetch_uno_pages(
        base_url=url, source=SOURCE_ABSOLVENTA, pages=pages,
        timeout=timeout, opener=opener,
    )


# ---------------------------------------------------------------------------
# 10. Praktikum.info — MESMA plataforma uno (F30; default OFF, ver docstring)
# ---------------------------------------------------------------------------


def fetch_praktikum_info(
    *,
    pages: int = ABSOLVENTA_PAGES,
    timeout: float = RESEARCH_HTTP_TIMEOUT,
    opener: Callable[[urllib.request.Request], Any] | None = None,
    url: str = PRAKTIKUM_INFO_URL,
) -> tuple[list[Job], dict[str, Any]]:
    """Praktikum.info -> ``(jobs, stats)``. DESLIGADA por default (F30).

    Mesma plataforma/DB da ABSOLVENTA (probe 13/10: IDs identicos 18/20,
    mesmos assets, badge 2.473 ⊂ 2.554). O adapter existe para o caso da
    ABSOLVENTA sair do ar ou do canal divergir — ligar = remover de
    ``F30_DEFAULT_OFF_SOURCES`` (a env OFF continua valendo por cima).
    """
    return _fetch_uno_pages(
        base_url=url, source=SOURCE_PRAKTIKUM_INFO, pages=pages,
        timeout=timeout, opener=opener,
    )


# ---------------------------------------------------------------------------
# Estagio F21+F30: sequencia das 10 fontes com budget + kill switch por env
# ---------------------------------------------------------------------------

# Ordem fixa (deterministica): portais institucionais primeiro (relevancia
# de pesquisa — objetivo da fase), APIs keyless depois, fontes nicho F30
# por ultimo (recem-chegadas: falha nelas nunca afeta as veteranas dentro
# do budget diario).
RESEARCH_SOURCE_ORDER: tuple[tuple[str, Callable[..., tuple[list[Job], dict[str, Any]]]], ...] = (
    (SOURCE_MPG, fetch_mpg_rss),
    (SOURCE_TU_BERLIN, fetch_tu_berlin),
    (SOURCE_LEIBNIZ, fetch_leibniz),
    (SOURCE_ARBEITNOW, fetch_arbeitnow),
    (SOURCE_REMOTEOK, fetch_remoteok),
    (SOURCE_FREEHIRE, fetch_freehire),
    (SOURCE_AMAZON_JOBS, fetch_amazon_jobs),
    (SOURCE_JOBMENSA, fetch_jobmensa),
    (SOURCE_ABSOLVENTA, fetch_absolventa),
    (SOURCE_PRAKTIKUM_INFO, fetch_praktikum_info),
)


def disabled_research_sources(
    env: dict[str, str] | None = None,
) -> set[str]:
    """Nomes de fontes desligadas (kill switch sem deploy + default F30).

    ``INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF``: CSV de nomes canonicos
    (``mpg_rss,tu_berlin,leibniz,arbeitnow,remoteok,freehire,amazon_jobs,
    jobmensa,absolventa,praktikum_info``), case insensitive, whitespace
    tolerante. Item desconhecido gera log de aviso (visivel) e e
    ignorado — nunca crasha o run. Sem a var (ou vazia): conjunto vazio.

    F30: ``F30_DEFAULT_OFF_SOURCES`` junta-se ao resultado — fontes com
    yield/duplicidade estrutural documentada (hoje: ``praktikum_info``,
    mesma DB da ABSOLVENTA) entram OFF por default; a env CSV desliga
    QUALQUER fonte por cima (kill switch manual). Retomada de uma fonte
    default-OFF = remove-la do set (1 linha, deploy trivial).
    """
    if env is None:
        env = dict(os.environ)
    raw = str(env.get(RESEARCH_SOURCES_OFF_ENV, "") or "")
    known = {name for name, _ in RESEARCH_SOURCE_ORDER}
    disabled: set[str] = set(F30_DEFAULT_OFF_SOURCES)
    for token in re.split(r"[,;\s]+", raw):
        if not token:
            continue
        name = token.strip().lower()
        if name in known:
            disabled.add(name)
        else:
            log.warning(
                "research_sources: fonte desconhecida '%s' em %s (ignorada)",
                token, RESEARCH_SOURCES_OFF_ENV,
            )
    return disabled


def collect_research_sources(
    *,
    budget_seconds: float = RESEARCH_BUDGET_SECONDS,
    now: Callable[[], float] = time.monotonic,
    env: dict[str, str] | None = None,
    fetchers: dict[str, Callable[..., tuple[list[Job], dict[str, Any]]]] | None = None,
) -> tuple[list[Job], dict[str, Any]]:
    """Estagio F21+F30: 10 fontes de pesquisa sequenciais; ``(jobs, summary)``.

    - Cada fonte e independente e best-effort (fail-soft): falha vira
      registro com ``status: failed`` e o run segue — o exit code nunca
      muda (mesma regra dos estagios dataset F3/direct_fetch F4).
    - Budget TOTAL checado ENTRE fontes; estourado -> fontes restantes
      ``skipped_budget`` (nunca interrompe a fonte em andamento).
    - ``env``: injetavel (testes); default ``os.environ``.
    - ``fetchers``: substitui fetchers por nome (testes injetam fixtures
      offline). Default: as funcoes reais de cada fonte.
    """
    t0 = now()
    disabled = disabled_research_sources(env)
    by_name = dict(fetchers) if fetchers else {}
    summary: dict[str, Any] = {
        "source": "research_sources", "status": "ok",
        "jobs": 0, "duration": 0.0, "skipped_budget": 0,
        "disabled": sorted(disabled),
        "sources": {},
    }
    jobs: list[Job] = []
    failures = 0
    ran = 0

    for name, default_fetcher in RESEARCH_SOURCE_ORDER:
        entry: dict[str, Any] = {
            "source": name, "status": "skipped_disabled" if name in disabled else "ok",
            "jobs": 0, "rows_seen": 0, "duration": None, "error": None,
        }
        summary["sources"][name] = entry
        if name in disabled:
            log.info("research_sources: %s desligada via %s; pulada",
                     name, RESEARCH_SOURCES_OFF_ENV)
            continue
        if now() - t0 > budget_seconds:
            entry["status"] = "skipped_budget"
            summary["skipped_budget"] += 1
            log.warning(
                "research_sources: budget de %.0fs estourado; %s e as fontes "
                "restantes viram skipped_budget", budget_seconds, name)
            continue
        fetcher = by_name.get(name, default_fetcher)
        src_t0 = now()
        try:
            src_jobs, src_stats = fetcher()
            entry.update({
                "status": src_stats.get("status", "ok"),
                "jobs": src_stats.get("jobs", 0),
                "rows_seen": src_stats.get("rows_seen", 0),
                "error": src_stats.get("error"),
            })
            if "invalid_rows" in src_stats:
                entry["invalid_rows"] = src_stats["invalid_rows"]
            if "details_ok" in src_stats:
                entry["details_ok"] = src_stats["details_ok"]
                entry["details_failed"] = src_stats["details_failed"]
            jobs.extend(src_jobs)
            if src_stats.get("status") == "failed":
                failures += 1
        except Exception as exc:  # noqa: BLE001 - fonte NUNCA derruba o run
            entry["status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            failures += 1
            log.warning("research_sources: fonte %s falhou (%s); seguindo", name, exc)
        finally:
            entry["duration"] = round(now() - src_t0, 2)
            ran += 1

    summary["jobs"] = len(jobs)
    summary["duration"] = round(now() - t0, 2)
    # status geral: failed so se TODAS as executadas falharam (nenhuma
    # entregou jobs); partial se alguma falhou. Fontes desligadas nao
    # contam como falha (decisao de configuracao, nao erro).
    if ran == 0:
        summary["status"] = "skipped_disabled"
    elif failures >= ran:
        summary["status"] = "failed"
    elif failures:
        summary["status"] = "partial"
    return jobs, summary
