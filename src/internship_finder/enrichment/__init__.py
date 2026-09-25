"""Camada de enrichment por LLM (isolada) — v1.

Fluxo: selecao deterministica da amostra -> fetch da pagina oficial ->
normalizacao HTML->texto -> extracao GLM-5.3-Flash (JSON estruturado com
evidencias) -> EnrichmentRecord validado (pydantic) -> JSONL persistente
(escrita atomica, upsert incremental).

Ferramenta STANDALONE (``scripts/enrichment_run.py``): NENHUM modulo
existente importa este pacote; a camada pode falhar POR COMPLETO sem
impedir coleta, eligibility, dedup, ranking, Telegram ou publicacao. A
LLM apenas ENRIQUECE com evidencia — nunca decide eligibility, score ou
ranking, e nunca substitui um detector deterministico.
"""

from internship_finder.enrichment import (  # noqa: F401
    fetch,
    html_norm,
    llm,
    runner,
    schema,
    store,
)
from internship_finder.enrichment.schema import (  # noqa: F401
    EnrichmentRecord,
    PageStatus,
    WAValue,
    build_record,
    fields_from_llm,
)
from internship_finder.enrichment.store import EnrichmentStore

__all__ = [
    "EnrichmentRecord",
    "EnrichmentStore",
    "PageStatus",
    "WAValue",
    "build_record",
    "fields_from_llm",
    "fetch",
    "html_norm",
    "llm",
    "runner",
    "schema",
    "store",
]
