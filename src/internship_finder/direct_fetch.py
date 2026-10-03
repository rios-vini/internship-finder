"""Fetch diario DIRETO das APIs publicas BA/EURES com filtro de estagio (F4).

As duas maiores fontes de estagio da Europa entram no pipeline por DOIS
caminhos complementares (spec F4 §4.3 — nao duplica ingestao, adiciona o
que falta):

1. **sf_dataset (F3)**: rows BA/EURES ja sao ingeridas das fatias hospedadas
   (prefilter DE+estagio; F3 mediu 10.920 BA + 1.484 EURES kept). A fatia BA
   tem 0% description — a HIDRATACAO desta fase (mapa da Fase A estendido a
   bundesagentur/eures) preenche via detail endpoint.
2. **direct_fetch (F4, este modulo)**: uma amostra FRESCA diaria direto das
   APIs publicas COM o filtro de estagio nativo de cada fonte —
   ``angebotsart=34`` (PRAKTIKUM_TRAINEE) na BA e keywords EVERYWHERE no
   EURES — com cap rigido de jobs/paginas por run (rate limit conservador
   para servicos publicos: spec §3.3).

Por que o fetch direto vale as 2 fontes:

- BA: 14,3k rows PRAKTIKUM_TRAINEE ao vivo; a fatia dataset (1M rows) tem
  27.870 linhas casando ``praktikum`` mas o prefilter F3 das fatias ve o
  TITULO + pais da row — rows recentemente publicadas podem nao estar na
  fatia do dia (atualiza ~05h UTC). O fetch direto pega as mais novas
  (sortierung veroeffdatum) e ganha description via detail v4.
- EURES: 35.486 rows DE com "Praktikum" (EVERYWHERE) vs 4.649 linhas
  ``praktikum|internship`` na fatia (prefilter por titulo so); a busca por
  keyword alcanc,a rows cujo titulo NAO traz o marcador (description
  fala). E description vem DE GRAca na resposta da busca (1-2k chars,
  probe 14/10-02).

Identidade: jobs diretos carregam ``source = "direct:<ats>"`` — escopo P1.1
distinto de registry e sf_dataset. O dedup existente colapsa a mesma vaga
cross-fonte pela chave URL (b): a vaga BA direta e a mesma vaga da fatia BA
tem a MESMA URL ``https://www.arbeitsagentur.de/jobsuche/jobdetail/<refnr>``.

Rate limits conservadores (spec §3.3): 1 fetch/dia por fonte (o refresh roda
1x/dia), cap de jobs por fonte por run, paginacao SEQUENCIAL, timeout curto
por request, backoff em 429/5xx (baixo, sem paralelismo agressivo — 1 request
por vez). Falha de fonte = degradacao graciosa: log + registro
``type: direct_fetch`` com status failed e o run segue (NUNCA derruba o
pipeline).
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from internship_finder.filters import is_student_role
from internship_finder.models.job import Job

log = logging.getLogger(__name__)

# --- BA (arbeitsagentur.de jobboerse, API v6 publica) -----------------------
BA_API_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
BA_API_KEY = "jobboerse-jobsuche"  # chave publica do frontend oficial
BA_DETAIL_URL_TEMPLATE = (
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails/{encoded_ref}"
)
# Codigo da facet angebotsart medida ao vivo (02/10): 34 = PRAKTIKUM_TRAINEE
# ({"1": ARBEIT, "2": SELBSTAENDIGKEIT, "34": PRAKTIKUM_TRAINEE, "4": AUSBILDUNG}).
BA_ANGEBOTSART_PRAKTIKUM = "34"
BA_SORT = "veroeffdatum"  # mais recentes primeiro (medido: datas 2026-10-02)

# --- EURES (europa.eu jv-searchengine, API publica) -------------------------
EURES_API_URL = "https://europa.eu/eures/api/jv-searchengine/public/jv-search/search"
# Shape medido ao vivo (02/10): lista de OBJETOS; strings sao rejeitadas com
# 400 invalid-json. Multiplas entries sao ANDadas (79 rows para 3 keywords)
# — 1 keyword por query.
EURES_KEYWORD = "Praktikum"
EURES_SEARCH_CODE = "EVERYWHERE"
EURES_LOCATION_DE = "de"
# F7: locationCodes ACEITA lista e a semantica e OR (probe ao vivo 03/10:
# [de] 35.486 + [nl] 2.435 + [lu] 51 + [fi] 289 + [be] 3.334 = 41.594 total
# para [de,nl,lu,fi,be] — soma exata, nenhum AND). DE primeiro (ordem de
# MOST_RECENT e dominio de volume preservados).
EURES_TARGET_LOCATIONS = ("de", "lu", "nl", "fi", "be")

# --- Limites conservadores (spec §3.3) -------------------------------------
DIRECT_FETCH_TIMEOUT = 20.0  # por request (curto)
DIRECT_FETCH_BUDGET_SECONDS = 600.0  # teto TOTAL do estagio (2 fontes)
BA_PAGE_SIZE = 100
BA_MAX_JOBS = 200  # cap de jobs por fonte por run (spec: ex. <=200)
EURES_PAGE_SIZE = 50
EURES_MAX_JOBS = 200
DIRECT_FETCH_MAX_RETRIES = 3
DIRECT_FETCH_RETRY_BASE_DELAY = 2.0

_USER_AGENT = "internship-finder/0.1 (daily public-source fetch; contact: repo owner)"


# ---------------------------------------------------------------------------
# Transporte (urllib stdlib — mesma dependencia zero do dataset_source)
# ---------------------------------------------------------------------------


def _http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DIRECT_FETCH_TIMEOUT,
    max_retries: int = DIRECT_FETCH_MAX_RETRIES,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any] | None:
    """Request JSON com backoff em 429/5xx; None quando esgotado/nao-JSON.

    Best-effort conservador: 429/5xx => backoff exponencial com Retry-After
    quando presente; outras excecoes de rede => 1 retry curto. Timeout curto
    por tentativa (nunca trava o estagio). NUNCA levanta — falha de fonte e
    degradacao graciosa (spec §3.3).
    """
    import json

    data = None
    hdrs = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)

    last_error: str | None = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read()[:200]
            except Exception:  # noqa: BLE001
                pass
            if exc.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else DIRECT_FETCH_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                )
                sleep(delay)
                continue
            last_error = f"HTTP {exc.code}: {body.decode('utf-8', 'replace')[:120]}"
            break
        except Exception as exc:  # noqa: BLE001 - rede/DNS/timeout
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_retries:
                sleep(DIRECT_FETCH_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                continue
            break
    log.warning("direct_fetch: %s %s falhou apos %d tentativas: %s",
                method, url.split("?")[0], max_retries, last_error)
    return None


def _http_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DIRECT_FETCH_TIMEOUT,
) -> str | None:
    """GET texto simples (detail v4 da BA); None em qualquer falha."""
    hdrs = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - best-effort
        log.warning("direct_fetch: GET %s falhou: %s", url.split("?")[0], exc)
        return None


def _json_loads(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    import json

    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# Bundesagentur: parse item v6 -> Job
# ---------------------------------------------------------------------------


def _ba_headers() -> dict[str, str]:
    return {"X-API-Key": BA_API_KEY}


def _ba_locations_text(item: dict[str, Any]) -> tuple[str | None, str | None]:
    """(location, country_iso) das stellenlokationen do item v6."""
    import re

    locs = item.get("stellenlokationen")
    iso = None
    if isinstance(locs, list) and locs and isinstance(locs[0], dict):
        adresse = locs[0].get("adresse") or {}
        if isinstance(adresse, dict):
            city = str(adresse.get("ort") or "").strip()
            plz = str(adresse.get("plz") or "").strip()
            land = str(adresse.get("land") or "").strip()
            region = str(adresse.get("region") or "").strip()
            parts = [p for p in (f"{plz} {city}".strip() if (plz or city) else "",
                                 region.title() if region else "", land.title() if land else "") if p]
            location = ", ".join(parts) or None
            m = re.search(r"\bDE\b|Deutschland|Germany", location or "", re.IGNORECASE)
            if land.upper() == "DEUTSCHLAND" or m:
                iso = "de"
            return location, iso
    return None, None


def _parse_iso_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _ba_item_to_job(item: dict[str, Any], description: str | None) -> Job | None:
    """Item v6 + description (detail v4 ou None) -> Job (ou None se invalido).

    Reuso integral dos filtros do projeto: ``internship`` via
    ``is_student_role`` (o filtro de facet angebotsart=34 da BA classifica
    PRAKTIKUM_TRAINEE, mas rows "**Praktikum moglich**" de AUSBILDUNG podem
    vazar em buscas por texto — o is_student_role e o gatilho canônico).
    """
    ats_id = str(item.get("referenznummer") or item.get("refnr") or "").strip()
    title = str(
        item.get("stellenangebotsTitel") or item.get("titel")
        or item.get("hauptberuf") or ""
    ).strip()
    if not ats_id or not title:
        return None
    company = str(item.get("firma") or item.get("arbeitgeber") or "").strip() or "Bundesagentur"
    url = f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{urllib.parse.quote(ats_id)}"
    location, iso = _ba_locations_text(item)

    employment_type = "FULL_TIME" if item.get("arbeitszeitVollzeit") is True else None
    et_raw = item.get("vertragsdauer") or item.get("arbeitszeit")
    if employment_type is None and isinstance(et_raw, str):
        employment_type = et_raw  # label da fonte, nao enum

    raw = {k: v for k, v in item.items()
           if v not in (None, "", [], {}) and k != "stellenangebotsBeschreibung"}

    return Job(
        id=f"{company}|direct:bundesagentur:{ats_id}",
        source="direct:bundesagentur",
        title=title,
        company=company,
        location=location,
        country=iso,
        url=url,
        description=description,
        internship=is_student_role(title, description, employment_type),
        posted_at=_parse_iso_date(
            item.get("datumErsteVeroeffentlichung")
            or item.get("aktuelleVeroeffentlichungsdatum")
        ),
        collected_at=datetime.now(UTC),
        external_id=ats_id,
        employment_type=employment_type,
        country_iso=iso,
        raw=raw or None,
    )


# ---------------------------------------------------------------------------
# Bundesagentur: fetch paginado (sequencial) + detail v4 sob demanda
# ---------------------------------------------------------------------------


def fetch_ba_praktikum(
    *,
    max_jobs: int = BA_MAX_JOBS,
    timeout: float = DIRECT_FETCH_TIMEOUT,
    http_json: Callable[..., dict[str, Any] | None] | None = None,
    http_text: Callable[..., str | None] | None = None,
    base_url: str = BA_API_URL,
    hydrate: bool = True,
) -> tuple[list[Job], dict[str, Any]]:
    """Amostra fresca PRAKTIKUM_TRAINEE da BA (angebotsart=34, sort data).

    Paginacao SEQUENCIAL (1 request por vez — rate limit conservador),
    parando em ``max_jobs``. ``hydrate=True``: 1 GET do detail v4 por vaga
    SEM description na listagem (list v6 nao embute texto — probe 02/10).
    Falha de pagina/detail = skip logado, NUNCA derruba (degradacao
    graciosa). Returns ``(jobs, stats)``.
    """
    fetch_json = http_json or _http_json
    fetch_text = http_text or _http_text
    stats: dict[str, Any] = {
        "source": "direct:bundesagentur", "status": "ok", "rows_seen": 0,
        "jobs": 0, "pages": 0, "details_ok": 0, "details_failed": 0,
        "truncated_cap": False, "error": None,
    }
    jobs: list[Job] = []
    seen: set[str] = set()
    page = 1
    import base64 as _b64

    while len(jobs) < max_jobs:
        # size CONSTANTE em todas as paginas: o offset da API e
        # (page-1)*size — variar o size entre paginas recuaria o offset e
        # re-leria rows ja absorvidas (overlap). O cap acontece na ADICAO.
        query = urllib.parse.urlencode({
            "size": BA_PAGE_SIZE,
            "page": page,
            "angebotsart": BA_ANGEBOTSART_PRAKTIKUM,
            "sortierung": BA_SORT,
        })
        payload = fetch_json("GET", f"{base_url}?{query}",
                             headers=_ba_headers(), timeout=timeout)
        if payload is None:
            if page == 1:
                stats["status"] = "failed"
                stats["error"] = "primeira pagina falhou"
                return jobs, stats
            break  # paginas seguintes falharam: entrega o que tem
        items = payload.get("ergebnisliste")
        if not isinstance(items, list) or not items:
            break
        stats["pages"] += 1
        for it in items:
            if not isinstance(it, dict):
                continue
            stats["rows_seen"] += 1
            ats_id = str(it.get("referenznummer") or "").strip()
            if ats_id and ats_id in seen:
                continue  # defesa contra re-envio da API entre paginas
            if ats_id:
                seen.add(ats_id)
            desc: str | None = None
            if hydrate and ats_id:
                encoded = _b64.b64encode(ats_id.encode()).decode()
                detail = _json_loads(fetch_text(
                    BA_DETAIL_URL_TEMPLATE.format(encoded_ref=encoded),
                    headers=_ba_headers(), timeout=timeout,
                ))
                if detail:
                    d = detail.get("stellenangebotsBeschreibung")
                    if isinstance(d, str) and d.strip():
                        desc = d.strip()[:25000]
                        stats["details_ok"] += 1
                    else:
                        stats["details_failed"] += 1
                else:
                    stats["details_failed"] += 1
            job = _ba_item_to_job(it, desc)
            if job is not None:
                jobs.append(job)
                if len(jobs) >= max_jobs:
                    stats["truncated_cap"] = True
                    break
        page += 1
        if page > 20:  # hard cap de paginas (2.000 rows max)
            break
    stats["jobs"] = len(jobs)
    if not jobs and stats["status"] == "ok" and stats["pages"] == 0:
        stats["status"] = "failed"
        stats["error"] = "nenhuma row retornada"
    return jobs, stats


# ---------------------------------------------------------------------------
# EURES: parse jv -> Job
# ---------------------------------------------------------------------------


def _clean_html_text(value: str) -> str:
    import html
    import re as _re

    text = html.unescape(value)
    text = _re.sub(r"<br\s*/?>", "\n", text, flags=_re.IGNORECASE)
    text = _re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = _re.sub(r"[ \t\r\f\v]+", " ", text)
    return text.strip()[:25000] or None


def _eures_description(item: dict[str, Any]) -> str | None:
    """Description do item de busca (translations > description; probe 02/10)."""
    value = item.get("description")
    if not isinstance(value, str) or not value.strip():
        translations = item.get("translations") or {}
        if isinstance(translations, dict):
            for translation in translations.values():
                if isinstance(translation, dict):
                    candidate = translation.get("description")
                    if isinstance(candidate, str) and candidate.strip():
                        value = candidate
                        break
    if not isinstance(value, str) or not value.strip():
        return None
    return _clean_html_text(value)


def _parse_epoch_ms_or_iso(value: Any) -> datetime | None:
    """Epoch-milliseconds (EURES creationDate) OU data ISO (BA). Nunca crash."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            ms = int(value)
        except (TypeError, ValueError):
            return None
        if ms <= 0:
            return None
        return datetime.fromtimestamp(ms / 1000, tz=UTC)
    return _parse_iso_date(value)


def _eures_item_to_job(item: dict[str, Any]) -> Job | None:
    jv_id = item.get("id")
    title = str(item.get("title") or "").strip()
    if not jv_id or not title:
        return None
    jv_id = str(jv_id)
    company = str(
        item.get("employerName") or (item.get("employer") or {}).get("name") or ""
    ).strip() or "EURES"
    url = f"https://europa.eu/eures/portal/jv-se/jv-details/{urllib.parse.quote(jv_id)}?lang=en"

    location = None
    iso = None
    loc_map = item.get("locationMap") or {}
    if isinstance(loc_map, dict) and loc_map:
        country = next(iter(loc_map))
        regions = [r for r in (loc_map[country] or []) if isinstance(r, str)]
        location = f"{country} ({', '.join(regions[:3])})" if regions else str(country)
        iso = str(country).lower() if len(str(country)) == 2 else None

    employment_type = None
    offering = item.get("positionOfferingCode")
    if isinstance(offering, str) and offering.strip():
        employment_type = offering.strip()
    description = _eures_description(item)

    raw = {k: v for k, v in item.items() if v not in (None, "", [], {})}

    return Job(
        id=f"{company}|direct:eures:{jv_id}",
        source="direct:eures",
        title=title,
        company=company,
        location=location,
        country=iso,
        url=url,
        description=description,
        internship=is_student_role(title, description, employment_type),
        posted_at=_parse_epoch_ms_or_iso(item.get("creationDate")),
        collected_at=datetime.now(UTC),
        external_id=jv_id,
        employment_type=employment_type,
        country_iso=iso,
        raw=raw or None,
    )


# ---------------------------------------------------------------------------
# EURES: fetch paginado (sequencial) com keyword Praktikum (EVERYWHERE)
# ---------------------------------------------------------------------------


def _eures_search_body(page: int, rpp: int, location_codes: Any = None) -> dict[str, Any]:
    """Body da busca EURES. F7: ``location_codes`` injetavel (OR — probe 03/10);
    default mantem DE puro (retrocompat total com a F4)."""
    if location_codes is None:
        codes: list[str] = [EURES_LOCATION_DE]
    else:
        codes = [str(c).strip().lower() for c in location_codes if str(c).strip()]
    return {
        "resultsPerPage": rpp,
        "page": page,
        "sortSearch": "MOST_RECENT",
        "keywords": [
            {"keyword": EURES_KEYWORD, "specificSearchCode": EURES_SEARCH_CODE}
        ],
        "publicationPeriod": None,
        "occupationUris": [],
        "skillUris": [],
        "requiredExperienceCodes": [],
        "positionScheduleCodes": [],
        "sectorCodes": [],
        "educationAndQualificationLevelCodes": [],
        "positionOfferingCodes": [],
        "locationCodes": codes,
        "euresFlagCodes": [],
        "otherBenefitsCodes": [],
        "requiredLanguages": [],
        "minNumberPost": None,
        "sessionId": "ats-scrapers",
        "requestLanguage": "en",
    }


def fetch_eures_praktikum(
    *,
    max_jobs: int = EURES_MAX_JOBS,
    timeout: float = DIRECT_FETCH_TIMEOUT,
    http_json: Callable[..., dict[str, Any] | None] | None = None,
    base_url: str = EURES_API_URL,
    location_codes: Any = None,
) -> tuple[list[Job], dict[str, Any]]:
    """Amostra fresca com keyword Praktikum (EVERYWHERE) do EURES.

    1 keyword por query (multiplas entries sao ANDadas — probe 02/10).
    Paginacao SEQUENCIAL, parando em ``max_jobs``. A resposta da BUSCA ja
    embute description (1-2k chars, probe 14) — nenhum request extra por
    vaga. Falha = skip logado, degradacao graciosa.

    F7: ``location_codes`` (OR entre codigos — probe 03/10) amplia a busca
    aos paises-alvo; ``None`` = so DE (retrocompat F4). O country_iso de
    cada Job desce do locationMap da propria resposta (``_eures_item_to_job``)
    — o filtro de pais do pipeline aplica o corte oficial depois.
    """
    fetch_json = http_json or _http_json
    stats: dict[str, Any] = {
        "source": "direct:eures", "status": "ok", "rows_seen": 0,
        "jobs": 0, "pages": 0, "truncated_cap": False, "error": None,
        "location_codes": (
            [EURES_LOCATION_DE] if location_codes is None
            else [str(c).strip().lower() for c in location_codes if str(c).strip()]
        ),
        "jobs_by_country": {},
    }
    jobs: list[Job] = []
    seen: set[str] = set()
    page = 1

    while len(jobs) < max_jobs:
        # size CONSTANTE (offset = (page-1)*rpp): variar recua o offset.
        payload = fetch_json(
            "POST", base_url, payload=_eures_search_body(
                page, EURES_PAGE_SIZE, location_codes),
            timeout=timeout,
        )
        if payload is None:
            if page == 1:
                stats["status"] = "failed"
                stats["error"] = "primeira pagina falhou"
                return jobs, stats
            break
        items = payload.get("jvs")
        if not isinstance(items, list) or not items:
            break
        stats["pages"] += 1
        for it in items:
            if not isinstance(it, dict):
                continue
            stats["rows_seen"] += 1
            jv_id = str(it.get("id") or "").strip()
            if jv_id and jv_id in seen:
                continue
            if jv_id:
                seen.add(jv_id)
            job = _eures_item_to_job(it)
            if job is not None:
                jobs.append(job)
                # F7: contagem por pais (observabilidade do canal secundario)
                code = str(job.country_iso or "?").lower()
                stats["jobs_by_country"][code] = stats["jobs_by_country"].get(code, 0) + 1
                if len(jobs) >= max_jobs:
                    stats["truncated_cap"] = True
                    break
        page += 1
        if page > 8:  # hard cap de paginas (400 rows max)
            break
    stats["jobs"] = len(jobs)
    if not jobs and stats["pages"] == 0 and stats["status"] == "ok":
        stats["status"] = "failed"
        stats["error"] = "nenhuma row retornada"
    return jobs, stats


# ---------------------------------------------------------------------------
# Orcamento do estagio (2 fontes)
# ---------------------------------------------------------------------------


def collect_direct_fetch(
    *,
    budget_seconds: float = DIRECT_FETCH_BUDGET_SECONDS,
    max_jobs: int | None = None,
    ba_fetch: Callable[..., tuple[list[Job], dict[str, Any]]] | None = None,
    eures_fetch: Callable[..., tuple[list[Job], dict[str, Any]]] | None = None,
    now: Callable[[], float] = time.monotonic,
    eures_location_codes: Any = None,
) -> tuple[list[Job], dict[str, Any]]:
    """Estagio F4: BA + EURES direto com filtro de estagio; devolve (jobs, summary).

    Cada fonte e independente e best-effort: falha de UMA nao derruba a
    outra nem o run (registro com status failed por fonte; o summary geral
    carrega ``status: failed`` apenas se AMBAS falharem — o pipeline segue
    com o que houver). Budget checado ENTRE fontes (nao interrompe uma
    fonte em andamento — caps de jobs/paginas ja limitam cada uma).
    ``max_jobs`` e o cap POR FONTE (default 200; medidor de rate limit).
    Fetchers injetados (testes) recebem ``max_jobs`` como kwarg.
    ``eures_location_codes`` (F7): repassado ao EURES (OR de paises-alvo;
    None = so DE, retrocompat). A BA permanece DE — servico publico alemao,
    nao forcar outros paises (spec F7 §3.2).
    """
    from functools import partial

    t0 = now()
    if ba_fetch is not None:
        ba_fn = ba_fetch
    elif max_jobs is not None:
        ba_fn = partial(fetch_ba_praktikum, max_jobs=max_jobs)
    else:
        ba_fn = fetch_ba_praktikum
    if eures_fetch is not None:
        eures_fn = eures_fetch
    elif max_jobs is not None:
        eures_fn = partial(
            fetch_eures_praktikum, max_jobs=max_jobs,
            location_codes=eures_location_codes,
        )
    else:
        eures_fn = partial(
            fetch_eures_praktikum, location_codes=eures_location_codes,
        )
    summary: dict[str, Any] = {
        "source": "direct_fetch", "status": "ok",
        "ba": {}, "eures": {}, "jobs": 0, "duration": 0.0,
        "skipped_budget": False,
    }
    jobs: list[Job] = []

    ba_jobs, ba_stats = ba_fn()
    summary["ba"] = ba_stats
    jobs.extend(ba_jobs)

    if now() - t0 < budget_seconds:
        eures_jobs, eures_stats = eures_fn()
        summary["eures"] = eures_stats
        jobs.extend(eures_jobs)
    else:
        summary["eures"] = {"source": "direct:eures", "status": "skipped_budget",
                           "jobs": 0, "rows_seen": 0, "pages": 0}
        summary["skipped_budget"] = True
        log.warning("direct_fetch: budget de %.0fs estourado; EURES virou skipped_budget",
                    budget_seconds)

    summary["jobs"] = len(jobs)
    summary["duration"] = round(now() - t0, 2)
    if (summary["ba"].get("status") == "failed"
            and summary["eures"].get("status") == "failed"):
        summary["status"] = "failed"
    elif (summary["ba"].get("status") == "failed"
            or summary["eures"].get("status") == "failed"):
        summary["status"] = "partial"
    return jobs, summary
