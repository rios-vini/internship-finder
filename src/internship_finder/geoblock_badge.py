"""F121 — Badge de risco geoblock absolventa (display-only).

Contexto (sinal 9 do RELATORIO-DIARIO-24/10): o agregador absolventa.de
redireciona /apply para de.talent.com "não disponível no seu país" — 3º caso:
Arvato 23/10, Fricke 24/10 (envio real perdido, corrigido no registro),
wenglor 24/10 marcada em risco. F105 já prefere o portal oficial no
MANUAL-CHECK quando o gêmeo existe; o buraco: vagas SÓ-absolventa SEM gêmeo.

Implementação (display-only):
1. Vagas cuja URL é absolventa.de SEM gêmeo de portal oficial: badge
   "⚠ risco geoblock (agregador absolventa — canal direto recomendado)"
   na página + nota no MANUAL-CHECK quando listado. Ranking/filtros intocados.
2. Passo 0 (medição offline): quantas vagas do snapshot são absolventa-only?
   Top-15 por score no relatório (são candidaturas em risco HOJE).
"""

from __future__ import annotations

import urllib.parse
from typing import Any

# Host do agregador geobloqueante (medido 23/10/2026 — absolventa.de bloqueia do Brasil)
ABSOLVENTA_HOST = "absolventa.de"

# Hosts de portais oficiais conhecidos que são gêmeos de absolventa (medidos no registro)
# F105 já mantém o mapa TENANT_PORTAL_METADATA; aqui usamos o mesmo princípio.
# A lista é extensível por medição (nova entrada no registro -> nova linha).
OFFICIAL_TWIN_HOSTS = (
    "jobsearch.createyourowncareer.com",  # Bertelsmann/Arvato
)

# ---------------------------------------------------------------------------
# Detecção pura: a vaga é absolventa-only (sem gêmeo oficial no mesmo ranking)?
# ---------------------------------------------------------------------------


def _url_host(url: str) -> str:
    """Host da URL (sem www., casefold); '' quando não parseável."""
    try:
        netloc = urllib.parse.urlsplit(str(url or "")).netloc
    except ValueError:
        return ""
    return netloc.removeprefix("www.").casefold()


def is_absolventa_url(job: dict[str, Any]) -> bool:
    """True se a URL da vaga é do agregador absolventa.de."""
    return _url_host(job.get("url") or "") == ABSOLVENTA_HOST


def _host_matches(url: str, hosts: tuple[str, ...]) -> bool:
    host = _url_host(url)
    return bool(host) and any(host == h or host.endswith("." + h) for h in hosts)


def _twin_title_key(title: str) -> str:
    """Chave de título para matching de gêmeo (aproximação do dedup.normalize_title).

    Acentos fora, casefold, tokens alfanuméricos em ordem — o par real (Arvato)
    tem título idêntico; a prova de MESMA vaga fica por conta do overlap
    de descrição (Jaccard >= 0.5 — calibração F105).
    """
    import unicodedata
    import re

    norm = (
        unicodedata.normalize("NFKD", str(title or ""))
        .encode("ascii", "ignore")
        .decode()
    )
    return " ".join(sorted(re.findall(r"[a-z0-9]+", norm.casefold())))


def _desc_tokens(text: str) -> set[str]:
    """Tokens de palavra (≥3 chars, ascii-folded) da descrição."""
    import unicodedata
    import re

    norm = (
        unicodedata.normalize("NFKD", str(text or ""))
        .encode("ascii", "ignore")
        .decode()
    )
    return {w for w in re.findall(r"[a-z]{3,}", norm.casefold())}


def _desc_jaccard(a: str, b: str) -> float | None:
    """Jaccard dos tokens das duas descrições; None quando degenerado."""
    ta, tb = _desc_tokens(a), _desc_tokens(b)
    if not ta or not tb:
        return None
    return len(ta & tb) / len(ta | tb)


def official_portal_twin(job: dict[str, Any], ranking: list[dict[str, Any]]) -> str:
    """URL do portal oficial do gêmeo absolventa (pura; '' = sem gêmeo).

    Dispara SÓ quando:
    - A URL da vaga está no agregador absolventa.de
    - Existe, no MESMO ranking, um registro em portal oficial conhecido
    - Título normalizado IGUAL + mesmo país + overlap de descrição Jaccard >= 0.5

    Sem prova de mesma vaga => '' (nunca inventa alvo).
    """
    url = str(job.get("url") or "").strip()
    if not url or not is_absolventa_url(job):
        return ""

    title_key = _twin_title_key(job.get("title") or "")
    country = str(job.get("country_iso") or "").strip().casefold()
    if not title_key or not country:
        return ""
    desc = str(job.get("description") or "")

    best: tuple[float, str] | None = None
    for other in ranking:
        if not isinstance(other, dict) or other is job:
            continue
        other_url = str(other.get("url") or "").strip()
        if not _host_matches(other_url, OFFICIAL_TWIN_HOSTS):
            continue
        if _twin_title_key(other.get("title") or "") != title_key:
            continue
        if str(other.get("country_iso") or "").strip().casefold() != country:
            continue
        overlap = _desc_jaccard(desc, str(other.get("description") or ""))
        if overlap is None or overlap < 0.5:
            continue
        if best is None or overlap > best[0]:
            best = (overlap, other_url)

    return best[1] if best else ""


def has_absolventa_geoblock_risk(job: dict[str, Any], ranking: list[dict[str, Any]]) -> bool:
    """True se a vaga é absolventa-only (tem risco geoblock).

    Vaga SÓ-absolventa = URL absolventa.de E sem gêmeo oficial no mesmo ranking.
    """
    return is_absolventa_url(job) and not official_portal_twin(job, ranking)


# ---------------------------------------------------------------------------
# Texto do badge (display-only)
# ---------------------------------------------------------------------------

GEOBLOCK_BADGE_TEXT_PT = "⚠ risco geoblock (agregador absolventa — canal direto recomendado)"
GEOBLOCK_BADGE_TEXT_EN = "⚠ geoblock risk (absolventa aggregator — direct channel recommended)"

# Nota para o MANUAL-CHECK (mesmo padrão do F105: sufixo na linha)
MANUAL_CHECK_GEOBLOCK_SUFFIX = " _(risco geoblock: agregador absolventa — canal direto recomendado)_"


def geoblock_badge_html(job: dict[str, Any], ranking: list[dict[str, Any]], lang: str = "pt") -> str:
    """HTML do badge discreto para o card (mesma área dos badges .flag).

    Retorna HTML do span ou string vazia.
    """
    if not has_absolventa_geoblock_risk(job, ranking):
        return ""
    text = GEOBLOCK_BADGE_TEXT_EN if lang == "en" else GEOBLOCK_BADGE_TEXT_PT
    # Mesmo estilo dos badges .flag (cor amber, tamanho 0.72rem)
    return f' <span class="flag" title="{text}">{text}</span>'


def geoblock_manual_check_suffix(job: dict[str, Any], ranking: list[dict[str, Any]]) -> str:
    """Sufixo para a linha do MANUAL-CHECK quando a vaga listada tem risco."""
    if not has_absolventa_geoblock_risk(job, ranking):
        return ""
    return MANUAL_CHECK_GEOBLOCK_SUFFIX


# ---------------------------------------------------------------------------
# Passo 0 — medição offline (snapshot -> relatório)
# ---------------------------------------------------------------------------


def measure_absolventa_only(ranking: list[dict[str, Any]]) -> dict[str, Any]:
    """Mede quantas vagas do snapshot são absolventa-only e top-15 por score.

    Retorna dict com:
    - total_absolventa: total de vagas com URL absolventa.de
    - absolventa_only: vagas absolventa SEM gêmeo oficial (risco geoblock)
    - absolventa_with_twin: vagas absolventa COM gêmeo oficial (F105 cobre)
    - top15_risk: top 15 absolventa-only por score (candidaturas em risco HOJE)
    """
    absolventa_jobs = [j for j in ranking if is_absolventa_url(j)]
    absolventa_only = [j for j in absolventa_jobs if has_absolventa_geoblock_risk(j, ranking)]
    absolventa_with_twin = [j for j in absolventa_jobs if not has_absolventa_geoblock_risk(j, ranking)]

    # Top 15 por score (decrescente)
    top15 = sorted(absolventa_only, key=lambda j: float(j.get("score") or 0.0), reverse=True)[:15]
    top15_risk = [
        {
            "rank": i + 1,
            "id": j.get("id"),
            "title": j.get("title"),
            "company": j.get("company"),
            "location": j.get("location"),
            "score": j.get("score"),
            "url": j.get("url"),
        }
        for i, j in enumerate(top15)
    ]

    return {
        "total_absolventa": len(absolventa_jobs),
        "absolventa_only": len(absolventa_only),
        "absolventa_with_twin": len(absolventa_with_twin),
        "top15_risk": top15_risk,
    }


def format_measurement_report(measurement: dict[str, Any]) -> str:
    """Formata o relatório de medição (Markdown)."""
    lines = [
        "# F121 — Medição offline: absolventa-only (risco geoblock)",
        "",
        f"- Total vagas absolventa.de no snapshot: **{measurement['total_absolventa']}**",
        f"- Com gêmeo portal oficial (F105 cobre): **{measurement['absolventa_with_twin']}**",
        f"- **SÓ-absolventa (risco geoblock): {measurement['absolventa_only']}**",
        "",
        "## Top 15 por score (candidaturas em risco HOJE)",
        "",
    ]
    if not measurement["top15_risk"]:
        lines.append("_Nenhuma vaga absolventa-only no snapshot._")
    else:
        lines.append("| # | Score | Título | Empresa | Local | URL |")
        lines.append("|---|-------|--------|---------|-------|-----|")
        for item in measurement["top15_risk"]:
            title = str(item["title"] or "").replace("|", "\\|")[:60]
            company = str(item["company"] or "").replace("|", "\\|")
            location = str(item["location"] or "—").replace("|", "\\|")
            url = str(item["url"] or "")
            lines.append(
                f"| {item['rank']} | {item['score']:.1f} | {title} | {company} | {location} | [abrir]({url}) |"
            )
    return "\n".join(lines)