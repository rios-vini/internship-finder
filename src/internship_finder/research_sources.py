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
6. ``freehire``     — API keyless https://freehire.me/api/v1/jobs (feeds ATS
                      normalizados; paginacao por ``offset`` — ``page`` e
                      ``ignored_params`` no meta, fato medido 09/10).

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

# Teto TOTAL do estagio (6 fontes), checado ENTRE fontes. A soma medida dos
# fetchs vivos (09/10) e ~45s; o teto e folga para dias lentos (criterio de
# pronto: soma < 5 min).
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
# Estagio F21: sequencia das 6 fontes com budget + kill switch por env var
# ---------------------------------------------------------------------------

# Ordem fixa (deterministica): portais institucionais primeiro (relevancia
# de pesquisa — objetivo da fase), APIs keyless depois.
RESEARCH_SOURCE_ORDER: tuple[tuple[str, Callable[..., tuple[list[Job], dict[str, Any]]]], ...] = (
    (SOURCE_MPG, fetch_mpg_rss),
    (SOURCE_TU_BERLIN, fetch_tu_berlin),
    (SOURCE_LEIBNIZ, fetch_leibniz),
    (SOURCE_ARBEITNOW, fetch_arbeitnow),
    (SOURCE_REMOTEOK, fetch_remoteok),
    (SOURCE_FREEHIRE, fetch_freehire),
)


def disabled_research_sources(
    env: dict[str, str] | None = None,
) -> set[str]:
    """Nomes de fontes desligadas via env var (kill switch sem deploy).

    ``INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF``: CSV de nomes canonicos
    (``mpg_rss,tu_berlin,leibniz,arbeitnow,remoteok,freehire``), case
    insensitive, whitespace tolerante. Item desconhecido gera log de aviso
    (visivel) e e ignorado — nunca crasha o run. Sem a var (ou vazia):
    conjunto vazio = todas as fontes ligadas (default ON, spec §2.3).
    """
    if env is None:
        env = dict(os.environ)
    raw = str(env.get(RESEARCH_SOURCES_OFF_ENV, "") or "")
    known = {name for name, _ in RESEARCH_SOURCE_ORDER}
    disabled: set[str] = set()
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
    """Estagio F21: 6 fontes de pesquisa sequenciais; ``(jobs, summary)``.

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
