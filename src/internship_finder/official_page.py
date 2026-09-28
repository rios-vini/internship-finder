"""Enriquecimento deterministico via pagina oficial da vaga (Fase D).

Estagio entre ``hydrate_descriptions`` (Fase A) e ``rank_jobs``: para cada
vaga candidata (ver selecao abaixo), faz UM GET da ``job.url``, registra
status/redirect/URL final, procura JSON-LD ``JobPosting``, VALIDA que o
JobPosting e da MESMA vaga e extrai somente campos confiaveis como evidencia
estruturada em ``job["official_page"]``. SEM LLM, SEM browser, SEM novo
banco/arquivo — o pipeline atual e a saida seguem intactos (best-effort:
falha por vaga e contada e o run continua; exit codes inalterados).

Arquitetura (spec Fase D):

    ... dedup -> mirror-dedup -> hydration -> OFFICIAL PAGE (aqui) -> rank

Reuso explicito (AGENTS.md: reuse before new):
    - ``enrichment.fetch.fetch_page``/``classify_page`` — GET com UA/timeout
      (10s/30s) e UMA tentativa, classificacao redirect/404/js-shell;
    - ``app_intel.normalize_text`` — normalizacao da description JSON-LD;
    - ``dedup.normalize_title`` + ``enrichment.fetch.title_match`` — validacao
      de correspondencia JobPosting <-> vaga;
    - ``opportunity_intel.resolve_city_key`` — comparacao de cidade;
    - ``opportunity_intel._to_float_or_none``/``_norm_period`` — numeros e
      periodicidade do baseSalary (placeholder 0.0 do softgarden e rejeitado);
    - ``hydration.TEASER_MAX_CHARS`` — janela de teaser da Fase A.

Selecao (spec secao 3; contada no dataset antes de qualquer GET): vaga e
candidata quando falta description (ausente/teaser) OU deadline OU salario.
Prioridade de fetch: description (ausente > teaser) > deadline > salary; o
limite ``--official-page-limit`` (default 150) corta o lote pelo RANKING
DE PRIORIDADE (nao por ordem de entrada) e e documentado no registro de
metricas.

Status da pagina — a distincao semantica da spec mapeada NO enum ``PageStatus``
que o projeto ja tem (enrichment LLM), preservando cada caso:

    spec                    status (job["official_page"]["status"])  reason
    ----------------------   ------------------------------------   ------
    page_verified           ok                                     -
    redirected (vaga equiv.) redirected                              redirect_target_job
    redirect home/search    redirected                              redirect_target_home
    page_unavailable        not_found | http_error | timeout |     -
                            fetch_error | empty_content
    page_unsupported        js_rendered                            -
    page_mismatch           mismatch                                jobposting_conflict
    (nao tentada)           not_checked                             -
    JSON-LD sem JobPosting  ok (sem extracao)                      no_jobposting

Uma resposta HTTP 200 NAO significa que a vaga existe: ``classify_page``
confere shell de SPA (js_rendered), texto minimo (empty_content) e redirect
para pagina que nao casa com o titulo da vaga (redirected). Alem disso, um
JobPosting encontrado so e usado quando casa com a vaga (identifier/URL/titulo
+ company); conflito forte -> ``page_mismatch`` e o dado ATS prevalece.

Hierarquia de evidencia FIELD-SPECIFIC (spec secao 11):
    - description: so substitui quando a atual e teaser (<TEASER_MAX_CHARS)
      e a do JSON-LD e maior; description completa do ATS NUNCA e tocada
      (``description_source="official_page_jsonld"`` na substituida);
    - salary: so preenche o canonico ``raw.salary_min/max/currency/period``
      quando o ATS nao tem NENHUM (e a estrutura JSON-LD e valida: > 0);
      salario existente permanece, o JSON-LD fica so como evidencia;
    - validThrough / datePosted / identifier: evidencia registrada
      (``valid_through``/``date_posted``/``identifier``), NUNCA promovida a
      ``application_deadline``/``posted_at``/``external_id``;
    - employmentType: evidencia complementar (``employment_type``), NUNCA
      filtro/eligibilidade;
    - jobLocation: comparacao com a cidade atual -> confirmacao
      (``location_relation="confirmed"``) ou conflito
      (``location_relation="conflict"``); a localizacao canonica NUNCA muda
      nesta fase.

Work authorization: o JSON-LD nao traz WA estruturada (auditoria 26/09) —
nenhuma interpretacao semantica aqui; a deteccao textual existente
(``app_intel.work_authorization``) continua sendo a fonte vigente e a
futura fase LLM cobrira os casos semanticos.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from internship_finder.app_intel import normalize_text
from internship_finder.dedup import normalize_title
from internship_finder.enrichment.fetch import (
    classify_page,
    fetch_page,
    title_match,
)
from internship_finder.enrichment.html_norm import normalize_html
from internship_finder.hydration import TEASER_MAX_CHARS
from internship_finder.opportunity_intel import (
    _norm_period,
    _to_float_or_none,
    resolve_city_key,
)

log = logging.getLogger(__name__)

# Teto de leitura da resposta (bytes). Paginas de careers modernas chegam a
# ~550KB; o cap protege contra payloads absurdos sem limitar paginas reais
# (medido no probe 28/09: max 552KB). O requests ja carregou o corpo; o cap
# aplica-se a QUANTIDADE que entra no parsing (string slice antes do soup).
MAX_HTML_BYTES = 1_000_000

# Orcamento total da fase (segundos), checado ENTRE fetchs — mesma garantia
# da hidratacao (HYDRATION_BUDGET_SECONDS): um servidor lento nao pode
# bloquear o refresh. O limite de candidatos (default) e o freio principal;
# o orcamento e a rede de segurança.
OFFICIAL_PAGE_BUDGET_SECONDS = 600.0

# Limite de vagas por execucao (spec secao 3: "primeiro run controlado com
# limite configuravel"). Probe 28/09: ~1.4s por GET -> 150 paginas ~ 3-5 min.
OFFICIAL_PAGE_LIMIT = 150

# Description JSON-LD abaixo disso nao substitui teaser nenhum (evita trocar
# um teaser por outro); alinhado ao MIN_USEFUL_TEXT do fetch LLM.
MIN_REPLACEMENT_DESC_CHARS = 200


# ---------------------------------------------------------------------------
# Selecao de candidatos (sem rede)
# ---------------------------------------------------------------------------


def _raw(job: dict[str, Any]) -> dict[str, Any]:
    """``job["raw"]`` quando e dict; {} caso contrario (nunca quebra)."""
    raw = job.get("raw")
    return raw if isinstance(raw, dict) else {}


def _desc_len(job: dict[str, Any]) -> int:
    return len(str(job.get("description") or "").strip())


def is_candidate(job: dict[str, Any]) -> bool:
    """Criterio da fase (spec secao 3): falta description (ausente/teaser),
    OU deadline, OU salario. Vaga com os tres campos presentes nao gera GET.
    """
    if _desc_len(job) < TEASER_MAX_CHARS:
        return True
    if not job.get("application_deadline"):
        return True
    raw = _raw(job)
    if raw.get("salary_min") is None and raw.get("salary_max") is None:
        return True
    return False


def candidate_priority(job: dict[str, Any]) -> tuple[int, str]:
    """Prioridade de fetch (spec secao 3): 1 sem description; 2 teaser; 3 sem
    deadline; 4 sem salary. Retorna chave de ordenacao ASC (menor = primeiro).
    """
    desc = _desc_len(job)
    if desc == 0:
        return (1, "no_description")
    if desc < TEASER_MAX_CHARS:
        return (2, "teaser_description")
    if not job.get("application_deadline"):
        return (3, "no_deadline")
    return (4, "no_salary")


# ---------------------------------------------------------------------------
# JSON-LD: extracao deterministica
# ---------------------------------------------------------------------------


def _iter_jobpostings(data: Any) -> list[dict[str, Any]]:
    """Percorre JSON-LD (objeto | array | @graph) e devolve todos os objetos
    com ``@type`` contendo ``JobPosting`` (case-insensitive, incluindo
    variantes em array de tipos como ``["JobPosting", "ListItem"]``).
    """
    out: list[dict[str, Any]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if not isinstance(node, dict):
            return
        types = node.get("@type")
        type_list = types if isinstance(types, list) else [types]
        if any("jobposting" in str(t).casefold() for t in type_list if t):
            out.append(node)
            # JobPosting nao aninha outro JobPosting de vaga diferente em
            # @graph dentro dele; nao desce mais.
            return
        graph = node.get("@graph")
        if graph:
            _walk(graph)

    _walk(data)
    return out


def parse_jsonld_blocks(html: str) -> list[Any]:
    """Extrai os conteudos ``<script type="application/ld+json">`` que sao
    JSON valido (invalidos sao ignorados silenciosamente — contados pelo
    chamador quando a pagina inteira nao produziu JobPosting). Sem rede.
    """
    from bs4 import BeautifulSoup  # dependencia ja usada pelo projeto

    soup = BeautifulSoup(html or "", "html.parser")
    parsed: list[Any] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        text = tag.string or tag.get_text()
        if not text or not text.strip():
            continue
        try:
            parsed.append(json.loads(text))
        except (ValueError, TypeError):
            continue  # JSON-LD invalido: ignora bloco, conta depois
    return parsed


# ---------------------------------------------------------------------------
# Validacao JobPosting <-> vaga (spec secao 7)
# ---------------------------------------------------------------------------


def _identifier_values(jp: dict[str, Any]) -> list[str]:
    """Valores candidados a identificador dentro do JobPosting."""
    vals: list[str] = []
    ident = jp.get("identifier")
    if isinstance(ident, dict):
        for key in ("value", "name"):
            v = ident.get(key)
            if isinstance(v, str) and v.strip():
                vals.append(v.strip())
    elif isinstance(ident, str) and ident.strip():
        vals.append(ident.strip())
    return vals


def _url_contains_external_id(final_url: str, job: dict[str, Any]) -> bool:
    """Sinal forte: external_id/requisition_id aparece na URL final."""
    raw = job.get("raw") if isinstance(job.get("raw"), dict) else {}
    ids = [str(job.get(k) or "") for k in ("external_id",)]
    req = str(raw.get("requisition_id") or "")
    if req:
        ids.append(req)
    ids = [i.strip() for i in ids if i.strip()]
    if not ids or not final_url:
        return False
    return any(i in final_url for i in ids)


def match_jobposting(jp: dict[str, Any], job: dict[str, Any], final_url: str) -> bool:
    """True quando ha evidencia suficiente de que o JobPosting e da vaga.

    Ordem (spec secao 7: nao exigir todos; nao aceitar qualquer um):
    1. identifier casa com external_id/requisition_id (forte);
    2. URL final contem external_id/requisition_id (forte);
    3. titulo normalizado identico (``normalize_title``) OU tokens do
       titulo da vaga presentes no JobPosting (title_match do spike contra
       title+description do JP) — combinado com organizacao NAO conflitante.
    """
    # 1. identifier
    job_ids = {str(job.get("external_id") or "").strip().casefold()}
    req = str(_raw(job).get("requisition_id") or "").strip().casefold()
    if req:
        job_ids.add(req)
    job_ids.discard("")
    if job_ids and any(v.casefold() in job_ids for v in _identifier_values(jp)):
        return True
    # 2. URL final
    if _url_contains_external_id(final_url, job):
        return True
    # 3. titulo (+ organizacao quando declarada)
    jp_title = str(jp.get("title") or "")
    if not jp_title:
        return False
    title_same = normalize_title(jp_title) == normalize_title(job.get("title"))
    jp_text = f"{jp_title} {jp.get('description') or ''}"
    title_similar = title_match(job.get("title"), jp_text) >= 0.5
    if not (title_same or title_similar):
        return False
    org = jp.get("hiringOrganization") or {}
    if isinstance(org, dict):
        org_name = str(org.get("name") or "").strip().casefold()
        company = str(job.get("company") or "").strip().casefold()
        if org_name and company and org_name not in company and company not in org_name:
            return False  # organizacao conflitante nao e sinal de confianca
    return True


def _conflict_signal(jp: dict[str, Any], job: dict[str, Any]) -> bool:
    """Conflito FORTE: titulo radicalmente diferente (nenhum token em
    comum apos normalizacao) OU identifier explicitamente diferente do
    external_id da vaga quando ambos existem e NAO ha sinal de URL.
    """
    a = normalize_title(jp.get("title"))
    b = normalize_title(job.get("title"))
    if a and b and a != b and not (set(a.split()) & set(b.split())):
        return True
    ident_vals = [v.casefold() for v in _identifier_values(jp)]
    ext = str(job.get("external_id") or "").strip().casefold()
    if ext and ident_vals and all(v != ext for v in ident_vals):
        return True
    return False


# ---------------------------------------------------------------------------
# Extracao por campo (spec secao 8) — so campos confiaveis
# ---------------------------------------------------------------------------


def _iso_date(value: Any) -> str | None:
    """validThrough/datePosted -> ISO ``YYYY-MM-DD`` (str) ou None.

    Aceita data ISO completa com hora/tz; recusa qualquer coisa que nao
    parseie (nunca inventa). Retorna apenas a DATA (a hora da validade da
    pagina nao e relevante como evidencia e padroniza o armazenamento).
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # data pura ou datetime ISO — corta no 'T'/espaco apos validar
    try:
        date_part = text[:10]
        year, month, day = date_part.split("-")
        if len(year) != 4 or len(month) != 2 or len(day) != 2:
            return None
        int(year), int(month), int(day)
    except (ValueError, AttributeError):
        return None
    return date_part


def _extract_salary(jp: dict[str, Any]) -> dict[str, Any] | None:
    """baseSalary -> ``{"min","max","currency","period"}`` quando estruturado
    e VALIDO (valores > 0 — placeholder 0.0 do softgarden e rejeitado; moeda
    preservada; periodo normalizado via ``_norm_period``). None caso
    contrario — nunca um salario inventado/estimado.
    """
    base = jp.get("baseSalary")
    if not isinstance(base, dict):
        return None
    currency = str(base.get("currency") or "").strip().upper() or None
    value = base.get("value")
    if isinstance(value, dict):
        lo = _to_float_or_none(value.get("minValue"))
        hi = _to_float_or_none(value.get("maxValue"))
        unit = _norm_period(value.get("unitText"))
    elif isinstance(value, (int, float)):
        lo = hi = _to_float_or_none(value)
        unit = None
    else:
        return None
    if lo is None and hi is None:
        return None
    if lo is None:
        lo = hi
    if hi is None:
        hi = lo
    assert lo is not None and hi is not None
    if lo <= 0 or hi <= 0:
        return None  # placeholder/invalido (softgarden 0.0) nao e salario
    return {"min": lo, "max": hi, "currency": currency, "period": unit}


def _extract_employment_type(jp: dict[str, Any]) -> str | None:
    """employmentType -> primeiro valor quando lista (medido: ['OTHER'])."""
    et = jp.get("employmentType")
    if isinstance(et, list):
        et = et[0] if et else None
    if isinstance(et, str) and et.strip():
        return et.strip()
    return None


def _extract_location(jp: dict[str, Any]) -> dict[str, Any] | None:
    """jobLocation (Place/PostalAddress ou lista) -> dict plano com city/
    region/postal/country/addressLine. Telecommute info preservada quando
    declarada (``@type`` contendo telecommute) como flag adicional.
    """
    loc = jp.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return None
    addr = loc.get("address")
    if not isinstance(addr, dict):
        return None
    out: dict[str, Any] = {}
    mapping = {
        "addressLocality": "city",
        "addressRegion": "region",
        "postalCode": "postal_code",
        "addressCountry": "country",
        "streetAddress": "street",
    }
    for src, dst in mapping.items():
        v = addr.get(src)
        if isinstance(v, str) and v.strip():
            out[dst] = v.strip()
        elif isinstance(v, dict):
            name = v.get("name")
            if isinstance(name, str) and name.strip():
                out[dst] = name.strip()
    if not out:
        return None
    types = loc.get("@type")
    if isinstance(types, str) and "telecommute" in types.casefold():
        out["telecommute"] = True
    elif isinstance(types, list) and any(
        "telecommute" in str(t).casefold() for t in types
    ):
        out["telecommute"] = True
    return out


def _extract_description(jp: dict[str, Any]) -> str | None:
    """description do JobPosting -> texto plano normalizado (reuso de
    ``normalize_text``: html.unescape + strip tags + whitespace). Nao aplica
    cap aqui (o cap de leitura da pagina ja limitou o input); o teor segue
    integral como evidencia.
    """
    desc = jp.get("description")
    if not isinstance(desc, str) or not desc.strip():
        return None
    text = normalize_text(desc)
    return text or None


def _extract_identifier(jp: dict[str, Any]) -> str | None:
    """identifier (PropertyValue) -> valor bruto preservado como evidencia
    (JAMAIS promovido a ``job["external_id"]`` nesta fase).
    """
    vals = _identifier_values(jp)
    return vals[0] if vals else None


def extract_fields(jp: dict[str, Any]) -> dict[str, Any]:
    """JobPosting validado -> dict de evidencia (chaves snake_case)."""
    return {
        "title": (str(jp.get("title")).strip() or None)
        if isinstance(jp.get("title"), str) else None,
        "valid_through": _iso_date(jp.get("validThrough")),
        "date_posted": _iso_date(jp.get("datePosted")),
        "salary": _extract_salary(jp),
        "employment_type": _extract_employment_type(jp),
        "location": _extract_location(jp),
        "description": _extract_description(jp),
        "identifier": _extract_identifier(jp),
    }


def _location_relation(loc: dict[str, Any] | None, job: dict[str, Any]) -> str | None:
    """Relacao cidade JSON-LD x cidade atual: confirmed | conflict | None.

    Comparacao via ``resolve_city_key`` (aliases munich->munchen etc.) sobre
    a cidade do JSON-LD e a primeira parte da ``job.location`` (formato
    "Cidade, Regiao" do dataset). Sem cidade em um dos lados -> None (nao
    sabe, nao afirma). A localizacao canonica NUNCA muda nesta fase.
    """
    if not loc or not loc.get("city"):
        return None
    job_loc = str(job.get("location") or "").split(",")[0].strip()
    if not job_loc:
        return None
    a = resolve_city_key(loc["city"])
    b = resolve_city_key(job_loc)
    if not a or not b:
        return None
    return "confirmed" if a == b else "conflict"


# ---------------------------------------------------------------------------
# Aplicacao da hierarquia de evidencia (spec secao 11)
# ---------------------------------------------------------------------------


def _apply_description(job: dict[str, Any], jp_desc: str | None, stats: dict[str, Any]) -> None:
    """Substitui a description SO quando a atual e teaser e a do JSON-LD e
    substancialmente melhor (>= MIN_REPLACEMENT_DESC_CHARS). Description
    ATS completa NUNCA e tocada. Proveniencia via ``description_source``.
    """
    if not jp_desc:
        return
    current = str(job.get("description") or "").strip()
    if len(current) >= TEASER_MAX_CHARS:
        stats["descriptions_unchanged"] += 1
        return
    if len(jp_desc) < MIN_REPLACEMENT_DESC_CHARS or len(jp_desc) <= len(current):
        stats["descriptions_unchanged"] += 1
        return
    job["description"] = jp_desc
    job["description_source"] = "official_page_jsonld"
    stats["descriptions_improved"] += 1


def _apply_salary(job: dict[str, Any], sal: dict[str, Any] | None, stats: dict[str, Any]) -> None:
    """Preenche ``raw.salary_*`` SOMENTE quando o ATS nao tem NENHUM salario
    estruturado (regra clara da spec §8.B: sem sobrescrever). Salario
    existente permanece intocado; o JSON-LD ja ficou como evidencia em
    ``official_page.salary``.
    """
    if not sal:
        return
    raw = _raw(job)
    if raw.get("salary_min") is not None or raw.get("salary_max") is not None:
        stats["salaries_unchanged_ats_wins"] += 1
        return
    raw.setdefault("salary_min", sal["min"])
    raw.setdefault("salary_max", sal["max"])
    if sal.get("currency"):
        raw.setdefault("salary_currency", sal["currency"])
    if sal.get("period"):
        raw.setdefault("salary_period", sal["period"])
    # garante que o job dict carrega o raw mutado (job["raw"] pode ser o
    # MESMO dict ja referenciado; setdefault cobre ambos os casos)
    job["raw"] = raw
    stats["salaries_filled"] += 1


# ---------------------------------------------------------------------------
# Estagio principal
# ---------------------------------------------------------------------------


def enrich_official_pages(
    jobs: list[dict[str, Any]],
    *,
    transport: Any | None = None,
    limit: int | None = OFFICIAL_PAGE_LIMIT,
    budget_seconds: float = OFFICIAL_PAGE_BUDGET_SECONDS,
    now: Callable[[], float] = time.monotonic,
    clock: Callable[[], str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Estagio Fase D: evidencia estruturada da pagina oficial por vaga.

    Best-effort (como a hidratacao Fase A): qualquer falha por vaga e
    capturada, contada e o pipeline segue; UMA vaga com pagina quebrada
    nunca interrompe o refresh. Retorna ``(jobs, stats)`` — a MESMA lista,
    mutada in place (identidade/ordem preservadas; nenhuma vaga removida).

    ``transport`` injetavel (padrao ``RequestsTransport``) -> testes 100%
    offline. ``limit`` corta o lote por PRIORIDADE (sem description >
    teaser > sem deadline > sem salary); ``limit=0`` ou ``None`` = sem
    limite. ``budget_seconds`` e checado ENTRE fetchs.
    """
    from datetime import datetime, timezone

    def _ts() -> str:
        if clock is not None:
            return clock()
        return datetime.now(timezone.utc).isoformat()

    stats: dict[str, Any] = {
        "type": "official_page",
        "eligible_before": len(jobs),
        "candidates_total": 0,
        "candidates_by_reason": {"no_description": 0, "teaser_description": 0,
                                 "no_deadline": 0, "no_salary": 0},
        "candidates_fetched": 0,
        "candidates_skipped_limit": 0,
        "candidates_skipped_budget": 0,
        "already_enriched": 0,
        "http_success": 0,
        "http_errors": 0,
        "redirects": 0,
        "redirects_target_job": 0,
        "pages_redirect_other": 0,
        "pages_unavailable": 0,
        "pages_unsupported": 0,
        "pages_mismatch": 0,
        "pages_ok": 0,
        "jsonld_found": 0,
        "jsonld_invalid_only": 0,
        "jobposting_found": 0,
        "jobposting_matched": 0,
        "jobposting_conflict": 0,
        "descriptions_improved": 0,
        "descriptions_unchanged": 0,
        "salaries_filled": 0,
        "salaries_unchanged_ats_wins": 0,
        "deadlines_new": 0,
        "locations_confirmed": 0,
        "locations_conflict": 0,
        "employment_types_found": 0,
        "duration_seconds": 0.0,
        "by_ats": {},
    }

    t0 = now()
    deadline_ts = t0 + budget_seconds

    # Selecao: candidatos por prioridade (estavel: prioridade, depois ordem
    # original — determinismo garantido para o A/B).
    candidates: list[tuple[int, str, int, dict[str, Any]]] = []
    for idx, job in enumerate(jobs):
        if job.get("official_page", {}).get("status"):
            stats["already_enriched"] += 1
            continue
        if not is_candidate(job):
            continue
        prio, reason = candidate_priority(job)
        stats["candidates_total"] += 1
        stats["candidates_by_reason"][reason] += 1
        candidates.append((prio, reason, idx, job))
    candidates.sort(key=lambda c: (c[0], c[2]))

    # Breakout Phenom (spec secoes 10/14): teaser -> description util e o
    # ganho central esperado da fase; medido separadamente.
    stats["phenom"] = {
        "candidates": sum(
            1 for _, _, _, j in candidates
            if str(j.get("source") or "").split(":", 1)[0] == "phenom"
        ),
        "jsonld": 0,
        "description_improved": 0,
        "desc_chars_before": 0,
        "desc_chars_after": 0,
    }

    if limit:
        keep, cut = candidates[:limit], candidates[limit:]
        stats["candidates_skipped_limit"] += len(cut)
        candidates = keep

    def ats_of(job: dict[str, Any]) -> str:
        return str(job.get("source") or "").split(":", 1)[0]

    def ats_stats(ats: str) -> dict[str, int]:
        return stats["by_ats"].setdefault(
            ats, {"candidates": 0, "fetched": 0, "ok": 0, "jsonld": 0,
                  "jobposting": 0, "errors": 0}
        )

    for prio, reason, idx, job in candidates:
        ats = ats_of(job)
        entry = ats_stats(ats)
        entry["candidates"] += 1
        is_phenom = ats == "phenom"
        desc_before = len(str(job.get("description") or "").strip())

        if now() >= deadline_ts:
            stats["candidates_skipped_budget"] += 1
            continue
        stats["candidates_fetched"] += 1
        entry["fetched"] += 1

        url = str(job.get("url") or "")
        base_ev: dict[str, Any] = {
            "original_url": url,
            "status": "not_checked",
            "reason": None,
        }
        try:
            resp = fetch_page(url, transport=transport)
            html = (resp.html or "")[:MAX_HTML_BYTES]
            if resp.html and len(resp.html) > MAX_HTML_BYTES:
                base_ev["html_truncated"] = True
            # reuso fiel do padrao LLM (runner.py): classify_page espera o
            # texto normalizado por normalize_html (remove script/nav/etc.)
            text = normalize_html(html) if html else ""
            page_status = classify_page(resp, text, job)
            base_ev["http_status"] = resp.http_status
            base_ev["final_url"] = resp.final_url
            base_ev["status"] = page_status
            if resp.http_status == 200:
                stats["http_success"] += 1
            elif resp.http_status is not None:
                stats["http_errors"] += 1
            if resp.error:
                entry["errors"] += 1

            # Redirect HTTP ocorrido (URL final != original): registrado
            # SEMPRE (spec secao 5) — job.url NUNCA e alterado.
            url_changed = bool(
                resp.final_url and url and resp.final_url != url
            )
            if url_changed:
                stats["redirects"] += 1

            if page_status == "ok":
                stats["pages_ok"] += 1
                entry["ok"] += 1
                if url_changed:
                    # redirect para pagina de vaga EQUIVALENTE (conteudo casa
                    # com o titulo): evidencia valida, redirect auditavel.
                    stats["redirects_target_job"] += 1
                    base_ev["reason"] = "redirect_target_job"
            elif page_status in ("not_found", "http_error", "timeout",
                                 "fetch_error", "empty_content"):
                stats["pages_unavailable"] += 1
            elif page_status == "js_rendered":
                stats["pages_unsupported"] += 1
            elif page_status == "redirected":
                # redirect para home/search/landing: conteudo NUNCA vira
                # evidencia da vaga (spec secao 5).
                stats["pages_redirect_other"] += 1
                base_ev["reason"] = "redirect_target_other"

            # JSON-LD: procura JobPosting SOMENTE em pagina verificada
            # (ok = 200 + conteudo casa com a vaga). Pagina redirect/home
            # nunca vira evidencia (spec secao 5).
            if page_status == "ok":
                blocks = parse_jsonld_blocks(html)
                postings: list[dict[str, Any]] = []
                for block in blocks:
                    postings.extend(_iter_jobpostings(block))
                if blocks:
                    stats["jsonld_found"] += 1
                    entry["jsonld"] += 1
                    if is_phenom:
                        stats["phenom"]["jsonld"] += 1
                else:
                    stats["jsonld_invalid_only"] += 1
                if not postings:
                    base_ev["reason"] = "no_jobposting"
                else:
                    stats["jobposting_found"] += 1
                    entry["jobposting"] += 1
                    final_url = resp.final_url or url
                    matched = next(
                        (p for p in postings if match_jobposting(p, job, final_url)),
                        None,
                    )
                    if matched is None:
                        if any(_conflict_signal(p, job) for p in postings):
                            base_ev["status"] = "mismatch"
                            base_ev["reason"] = "jobposting_conflict"
                            stats["pages_mismatch"] += 1
                            stats["jobposting_conflict"] += 1
                        else:
                            base_ev["reason"] = "no_match"
                    else:
                        stats["jobposting_matched"] += 1
                        fields = extract_fields(matched)
                        # hierarquia de evidencia por campo
                        _apply_description(job, fields["description"], stats)
                        _apply_salary(job, fields["salary"], stats)
                        if fields["valid_through"]:
                            stats["deadlines_new"] += 1
                        if fields["employment_type"]:
                            stats["employment_types_found"] += 1
                        rel = _location_relation(fields["location"], job)
                        if rel == "confirmed":
                            stats["locations_confirmed"] += 1
                        elif rel == "conflict":
                            stats["locations_conflict"] += 1
                        fields["location_relation"] = rel
                        base_ev["jsonld"] = fields
        except Exception as exc:  # noqa: BLE001 - best-effort por vaga
            base_ev["status"] = "fetch_error"
            base_ev["reason"] = f"internal:{type(exc).__name__}"
            stats["pages_unavailable"] += 1
            entry["errors"] += 1
            log.warning("official-page falhou p/ %s (%s): %s",
                        job.get("id"), ats, exc)

        base_ev["checked_at"] = _ts()
        job["official_page"] = base_ev
        if is_phenom:
            desc_after = len(str(job.get("description") or "").strip())
            stats["phenom"]["desc_chars_before"] += desc_before
            stats["phenom"]["desc_chars_after"] += desc_after
            if desc_after > desc_before and desc_after >= MIN_REPLACEMENT_DESC_CHARS:
                stats["phenom"]["description_improved"] += 1

    stats["duration_seconds"] = round(now() - t0, 2)
    return jobs, stats


def print_official_page_report(stats: dict[str, Any]) -> None:
    """Resumo no stdout do run (mesmo padrao da hidratacao)."""
    print("\n=== Official page enrichment (Fase D) ===")
    print(f"  elegiveis              : {stats.get('eligible_before', 0)}")
    print(f"  candidatos (total)     : {stats.get('candidates_total', 0)} "
          f"(sem desc {stats['candidates_by_reason']['no_description']}, "
          f"teaser {stats['candidates_by_reason']['teaser_description']}, "
          f"sem deadline {stats['candidates_by_reason']['no_deadline']}, "
          f"sem salary {stats['candidates_by_reason']['no_salary']})")
    print(f"  paginas tentadas       : {stats.get('candidates_fetched', 0)}")
    print(f"  HTTP 200               : {stats.get('http_success', 0)}")
    print(f"  HTTP errors            : {stats.get('http_errors', 0)}")
    print(f"  redirects (HTTP)       : {stats.get('redirects', 0)} "
          f"(p/ vaga equivalente: {stats.get('redirects_target_job', 0)})")
    print(f"  redirect p/ home/outra : {stats.get('pages_redirect_other', 0)}")
    print(f"  indisponiveis          : {stats.get('pages_unavailable', 0)}")
    print(f"  incompativeis (JS)     : {stats.get('pages_unsupported', 0)}")
    print(f"  mismatch               : {stats.get('pages_mismatch', 0)}")
    print(f"  ok                     : {stats.get('pages_ok', 0)}")
    print(f"  JSON-LD valido         : {stats.get('jsonld_found', 0)}")
    print(f"  JobPosting encontrado  : {stats.get('jobposting_found', 0)}")
    print(f"  JobPosting matched     : {stats.get('jobposting_matched', 0)}")
    print(f"  descriptions melhoradas: {stats.get('descriptions_improved', 0)}")
    print(f"  descriptions sem mudanca: {stats.get('descriptions_unchanged', 0)}")
    print(f"  salaries preenchidos   : {stats.get('salaries_filled', 0)}")
    print(f"  validThrough (evidencia): {stats.get('deadlines_new', 0)}")
    print(f"  locations conf./confl.  : "
          f"{stats.get('locations_confirmed', 0)}/"
          f"{stats.get('locations_conflict', 0)}")
    print(f"  employmentTypes        : {stats.get('employment_types_found', 0)}")
    ph = stats.get("phenom") or {}
    if ph.get("candidates"):
        print(f"  phenom: {ph['candidates']} cand / {ph['jsonld']} jsonld / "
              f"{ph['description_improved']} desc melhor "
              f"({ph['desc_chars_before']} -> {ph['desc_chars_after']} chars)")
    print(f"  duracao                : {stats.get('duration_seconds', 0.0):.1f}s")
    by_ats = stats.get("by_ats", {})
    if any(v.get("candidates") for v in by_ats.values()):
        print("  por ATS (cand/fetch/ok/jsonld/jp/erro):")
        for ats in sorted(by_ats):
            v = by_ats[ats]
            if v.get("candidates"):
                print(f"    {ats:<16} {v['candidates']:>3} / {v['fetched']:>3} "
                      f"/ {v['ok']:>3} / {v['jsonld']:>3} / {v['jobposting']:>3} "
                      f"/ {v['errors']:>3}")
