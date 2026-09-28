"""Montagem do input do LLM (spec §6 + §12) — texto JÁ COLETADO, sem rede.

Prioridade do TEXTO DE EXTRACAO:

1. ``job.description``; se teaser (vazia OU <400 chars) E
   ``official_page.jsonld.description`` existir, usa a do JSON-LD.
2. Campos estruturados via ``structured_fields`` (title/location/
   employment_type/commitment/department) como bloco rotulado — dados do
   feed, nao texto de extracao livre.
3. Bloco ``official_page`` (status + valid_through + location confirmed +
   salary JSON-LD) COMO CONTEXTO MARCADO (§12): status js_rendered/
   page_unavailable e registrado com instrucao explicita de NAO inferir
   conteudo da pagina; teaser phenom e marcado explicitamente como teaser.

Cap ~12k chars (CONTENT_LIMIT=12000 do v1); truncagem registrada
(``input_truncated=True`` + marcador no texto). O MESMO texto e salvo no
record (``llm_input``) — reprodutibilidade do manual review (§17).
"""

from __future__ import annotations

from typing import Any

from internship_finder.app_intel import normalize_text
from internship_finder.spike_e.schema import CONTENT_LIMIT, EVIDENCE_MAX_CHARS

TEASER_MAX_CHARS = 400


def _sf(job: dict[str, Any]) -> dict[str, str]:
    """Campos estruturados uteis (leitura read-only, funcoes puras)."""
    from internship_finder import structured_fields as sf
    return {
        "title": str(job.get("title") or ""),
        "location": str(job.get("location") or ""),
        "employment_type": str(job.get("employment_type") or "")
        or str(sf.employment_type_enum(job) or ""),
        "commitment": str(sf.commitment_label(job) or ""),
        "department": str(sf.department(job) or ""),
    }


def _official_page_block(job: dict[str, Any]) -> tuple[str, bool]:
    """Bloco de contexto marcado (§12); retorna (bloco, is_teaser)."""
    op = job.get("official_page")
    if not isinstance(op, dict):
        return "", False
    lines: list[str] = []
    status = str(op.get("status") or "")
    jsonld = op.get("jsonld") if isinstance(op.get("jsonld"), dict) else {}
    is_teaser = len(job.get("description") or "") < TEASER_MAX_CHARS
    lines.append("[OFFICIAL PAGE CONTEXT - metadata only, not job text]")
    lines.append(f"page_status: {status}")
    if str(job.get("source") or "").startswith("phenom:") and is_teaser:
        lines.append(
            "note: the job description above is ONLY A SHORT TEASER "
            "(<400 chars) from the feed; the full description is behind a "
            "JS-rendered page that could not be collected. Do NOT guess or "
            "infer the full description content."
        )
    elif status in ("js_rendered", "page_unavailable", "not_found",
                    "http_error", "timeout", "fetch_error", "empty_content"):
        lines.append(
            "note: the official page content is NOT available "
            "(JS-rendered or fetch problem). Do NOT infer page content "
            "from this URL or status."
        )
    if jsonld:
        if jsonld.get("valid_through"):
            lines.append(f"valid_through: {jsonld['valid_through']}")
        if jsonld.get("location"):
            lines.append(f"location_confirmed: {jsonld['location']}")
        if jsonld.get("salary"):
            lines.append(f"jsonld_salary: {jsonld['salary']}")
        if jsonld.get("date_posted"):
            lines.append(f"date_posted: {jsonld['date_posted']}")
    return "\n".join(lines), is_teaser


def build_input(job: dict[str, Any]) -> tuple[str, bool, bool]:
    """Monta o input normalizado. Retorna (llm_input, truncated, is_teaser).

    Ordem: job description (ou jsonld description para teasers) ->
    structured fields rotulados -> official page context. Cap 12k chars
    aplicado SOBRE O TEXTO DE EXTRACAO (description), preservando os
    blocos estruturados inteiros no fim (nunca cortados no meio).
    """
    desc = str(job.get("description") or "")
    op = job.get("official_page")
    jsonld = op.get("jsonld") if isinstance(op, dict) else None
    jsonld = jsonld if isinstance(jsonld, dict) else {}
    is_teaser = len(desc) < TEASER_MAX_CHARS
    desc_source = "job.description"
    if is_teaser and jsonld.get("description"):
        desc = str(jsonld["description"])
        desc_source = "official_page.jsonld.description"
        is_teaser = False  # jsonld description e conteudo real, nao teaser
    else:
        # Texto normalizado (spec §6: NAO mandar HTML bruto; a MESMA
        # normalizacao dos detectores — app_intel.normalize_text — remove
        # tags/entidades; preserva o texto literal citavel como evidence).
        desc = normalize_text(desc)

    sf = _sf(job)
    sf_lines = [f"[STRUCTURED FIELDS - feed data, from the job listing]",
                f"title: {sf['title']}",
                f"location: {sf['location']}",
                f"employment_type: {sf['employment_type']}",
                f"commitment: {sf['commitment']}",
                f"department: {sf['department']}"]

    ctx_block, ctx_teaser = _official_page_block(job)
    is_teaser = is_teaser or ctx_teaser

    # Cap do texto de extracao: 12k total incluindo blocos estruturais.
    # Margem para as linhas de cabecalho/truncagem (~80 chars).
    overhead = (sum(len(l) + 1 for l in sf_lines) + len(ctx_block)
                + len(desc_source) + 192)
    budget = CONTENT_LIMIT - overhead
    truncated = False
    if len(desc) > budget:
        desc = desc[:budget]
        truncated = True

    parts = [f"[JOB DESCRIPTION TEXT - source: {desc_source}]"]
    if truncated:
        parts.append("[NOTE: text truncated to fit the input limit]")
    parts.append(desc)
    parts.extend(sf_lines)
    if ctx_block:
        parts.append(ctx_block)
    return "\n".join(parts), truncated, is_teaser


def evidence_in_input(evidence: str | None, llm_input: str) -> bool:
    """§17-1: a evidencia (normalizada) aparece no texto do input?

    Comparacao tolerante: casefold + colapso de whitespace, remocao de
    pontuacao lateral. Evidencia ausente -> False (flag
    ``evidence_not_found`` na analise; o manual review decide FP vs
    alucinacao).
    """
    if not evidence:
        return False

    def norm(s: str) -> str:
        return " ".join(s.casefold().split())

    return norm(evidence) in norm(llm_input)
