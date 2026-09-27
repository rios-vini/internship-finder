"""Hidratacao seletiva de descriptions das vagas ELEGIVEIS (Fase A).

Estagio entre ``deduplicate`` e ``rank_jobs``: vagas elegiveis cuja
``description`` esta vazia/None ganham a description completa via
``ats-scrapers 0.3.0`` — SEM novas camadas, SEM pool proprio (a API
``BaseScraper.get_description`` e a forma direta da biblioteca).

Contrato (AGENTS.md):

- **O ``raw`` e o contrato**: nenhuma informacao e destruida — a hidratacao
  apenas preenche ``description`` ausente; description existente NUNCA e
  sobrescrita (``get_description`` ja retorna o valor existente quando ha).
- **Ausencia != dado falso**: falha de fetch nao fabrica texto — a vaga
  continua com a description que tinha (nenhuma) e o run segue.
- **Best-effort**: qualquer excecao por vaga e capturada, contada como
  ``hydration_failed`` e o pipeline continua. Hidratacao e enriquecimento,
  nao requisito de elegibilidade — falha nunca altera exit codes.

Selecao (criterio da fase): apenas eligible pos-dedup com ``description``
vazia/None. Teasers curtos (ex.: phenom, mediana ~301 chars) NAO sao
candidatos nesta fase — o contador observacional ``phenom_teaser_count``
apenas registra a situacao para uma futura fase de official-page enrichment.

Proveniencia: ``description_source`` distingue description do feed (campo
ausente/None = coleta original) da description hidratada (``"hydration"``).

ATS com endpoint de detail na 0.3.0 (overrides de ``get_description``):
smartrecruiters, workday, eightfold, personio. Softgarden e resolvido na
COLETA (feed traz a description de graca com ``include_descriptions=True``,
excecao explicita e local em ``collectors/ats_scraper.py`` — sem custo
adicional de requests); phenom NAO tem endpoint de detail na 0.3.0 e fica
fora do mapa.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import Any

from ats_scrapers.models import Job as UpstreamJob
from ats_scrapers.scrapers import get_scraper

log = logging.getLogger(__name__)

# Limite por CHAMADA de detail (segundos). Repassa ao construtor do scraper
# (``timeout``) — o mesmo mecanismo que a coleta usa por tenant; o default dos
# scrapers da 0.3.0 e 30.0s. NOTA: o param ``max_fetch_seconds`` do Workday
# guarda apenas o ``afetch`` em massa (deadline dentro de ``_exhaust_query``);
# ``get_description`` cria um httpx.AsyncClient(timeout=self.timeout) proprio
# e NUNCA consulta ``max_fetch_seconds`` — passar o param seria inerte, o
# limite efetivo por chamada e o ``timeout`` do construtor.
HYDRATION_TIMEOUT = 30.0

# Orcamento TOTAL da hidratacao (segundos), checado ENTRE vagas: estourou ->
# candidatos restantes viram ``hydration_skipped``. Garante que um tenant
# lento nao bloqueia indefinidamente o refresh (spec item 6).
HYDRATION_BUDGET_SECONDS = 600.0

# Cap de tamanho da description hidratada — mesmo limite do
# ``BaseScraper.enrich_descriptions`` da 0.3.0 (base.py trunca [:25_000]).
HYDRATION_DESCRIPTION_CAP = 25_000

# Janela observacional de teaser (chars) — SO para o contador de metricas,
# nunca para selecionar candidatos nesta fase.
TEASER_MAX_CHARS = 400

# Mapa de construcao do scraper por ATS (o contrato da fase): qual slug
# passar ao construtor para cada ATS com override de ``get_description`` na
# 0.3.0. Fora do mapa -> ``unsupported_no_detail`` (vaga preservada, NENHUMA
# tentativa de fetch — nunca construir scraper com slug invalido). Phenom
# fica fora: sem override e sem endpoint de detail na 0.3.0.
_WORKDAY_URL_RE = re.compile(r"^(https://[^/]+\.myworkdayjobs\.com/[^/?#]+)")


def _slug_for(ats: str, job: dict[str, Any]) -> str | None:
    """Slug que o construtor do scraper espera para ``ats`` nesta vaga.

    - smartrecruiters/eightfold/personio: sufixo do ``source`` (``ats:slug``).
    - workday: URL de careers base derivada da ``job.url``
      (``https://{co}.{wdN}.myworkdayjobs.com/{site}``) — o scraper exige a
      URL completa (mesma regra de ``URL_SLUG_ATS`` da coleta) e extrai o
      externalPath do proprio ``job.url`` quando ``raw.externalPath`` falta.
    """
    if ats in ("smartrecruiters", "eightfold", "personio"):
        source = job.get("source") or ""
        return source.split(":", 1)[1].strip() if ":" in source else None
    if ats == "workday":
        url = str(job.get("url") or "")
        match = _WORKDAY_URL_RE.match(url)
        return match.group(1) if match else None
    return None


def _to_upstream(job: dict[str, Any]) -> UpstreamJob | None:
    """Reconstroi o ``ats_scrapers.models.Job`` que ``get_description`` espera.

    ``ats_type``/``title``/``company``/``url`` sao obrigatorios no modelo
    upstream; ``description`` fica None (e o que motiva o fetch). Retorna
    ``None`` (vaga preservada, contada como ``unsupported_no_detail``) quando
    o dict nao carrega os obrigatorios — nunca deixa a validacao pydantic
    derrubar o pipeline.
    """
    try:
        raw = job.get("raw") if isinstance(job.get("raw"), dict) else None
        # str -> HttpUrl/ATSType: pydantic coage na validacao (ATSType e um
        # StrEnum; URL invalida levanta e vira unsupported, nao excecao solta).
        return UpstreamJob(
            url=job.get("url") or "",  # type: ignore[arg-type]
            title=str(job.get("title") or ""),
            company=str(job.get("company") or ""),
            ats_type=(job.get("source") or "").split(":", 1)[0],  # type: ignore[arg-type]
            ats_id=job.get("external_id") or (raw or {}).get("ats_id"),
            raw=raw,
        )
    except Exception:  # noqa: BLE001 - upstream malformado nao derruba o run
        return None


def hydrate_descriptions(
    jobs: list[dict[str, Any]],
    *,
    scraper_factory: Callable[[str, str], Any] | None = None,
    timeout: float = HYDRATION_TIMEOUT,
    budget_seconds: float = HYDRATION_BUDGET_SECONDS,
    now: Callable[[], float] = time.monotonic,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Preenche ``description`` das vagas com description ausente, in place.

    Retorna ``(jobs, stats)`` — a MESMA lista (mutada in place, sem trocar a
    identidade/ordem) e as estatisticas da fase. Criterio: description
    vazia/None (teasers nao sao candidatos nesta fase). Por vaga:

    - ``already_has_description``: tem description -> nunca e tocada.
    - ``unsupported_no_detail``: ATS fora do mapa ou slug nao derivavel ->
      preservada, nenhuma tentativa de fetch.
    - ``hydration_success``: ``get_description`` devolveu texto -> description
      preenchida + ``description_source`` = ``"hydration"``.
    - ``hydration_failed``: excecao/None/vazio -> vaga preservada com a
      description existente, pipeline segue.
    - ``hydration_skipped``: orcamento total esgotado -> candidatos restantes
      preservados sem tentativa.

    ``scraper_factory(ats, slug)`` (injetavel, default: ``get_scraper`` real
    com ``timeout``/``include_descriptions=False``) permite testes 100%
    offline. Os scrapers sao construidos uma vez por (ats, slug) e reusados.
    """
    factory = scraper_factory or _default_scraper_factory(timeout)
    stats: dict[str, Any] = {
        "eligible_before_hydration": len(jobs),
        "hydration_candidates": 0,
        "hydration_success": 0,
        "hydration_failed": 0,
        "hydration_skipped": 0,
        "already_has_description": 0,
        "unsupported_no_detail": 0,
        "description_coverage_before": 0,
        "description_coverage_after": 0,
        "hydration_duration": 0.0,
        "feed_description_count": 0,
        "hydration_description_count": 0,
        "phenom_teaser_count": 0,
        "by_ats": {},
    }

    t0 = now()
    scrapers: dict[tuple[str, str], Any] = {}
    budget_deadline = t0 + budget_seconds

    def ats_stats(ats: str) -> dict[str, int]:
        return stats["by_ats"].setdefault(
            ats, {"candidates": 0, "success": 0, "failed": 0,
                  "already": 0, "unsupported": 0}
        )

    for job in jobs:
        description = str(job.get("description") or "").strip()
        if description:
            stats["already_has_description"] += 1
            ats = (job.get("source") or "").split(":", 1)[0]
            ats_stats(ats)["already"] += 1
            if ats == "phenom" and len(description) < TEASER_MAX_CHARS:
                stats["phenom_teaser_count"] += 1
            continue

        stats["hydration_candidates"] += 1
        ats = (job.get("source") or "").split(":", 1)[0]
        entry = ats_stats(ats)
        entry["candidates"] += 1

        slug = _slug_for(ats, job)
        upstream = _to_upstream(job) if slug else None
        if slug is None or upstream is None:
            entry["unsupported"] += 1
            stats["unsupported_no_detail"] += 1
            continue

        if now() >= budget_deadline:
            stats["hydration_skipped"] += 1
            continue

        try:
            key = (ats, slug)
            if key not in scrapers:
                scrapers[key] = factory(ats, slug)
            scraper = scrapers[key]
            fetched = scraper.get_description(upstream)
        except Exception as exc:  # noqa: BLE001 - best-effort, nunca fatal
            stats["hydration_failed"] += 1
            entry["failed"] += 1
            log.warning("hydration falhou p/ %s (%s): %s",
                        job.get("id"), ats, exc)
            continue

        text = str(fetched).strip() if fetched is not None else ""
        if not text:
            stats["hydration_failed"] += 1
            entry["failed"] += 1
            continue

        job["description"] = text[:HYDRATION_DESCRIPTION_CAP]
        job["description_source"] = "hydration"
        stats["hydration_success"] += 1
        entry["success"] += 1

    stats["hydration_duration"] = round(now() - t0, 2)
    covered = sum(
        1 for j in jobs if str(j.get("description") or "").strip()
    )
    stats["description_coverage_after"] = covered
    stats["description_coverage_before"] = covered - stats["hydration_success"]
    stats["feed_description_count"] = stats["already_has_description"]
    stats["hydration_description_count"] = stats["hydration_success"]
    return jobs, stats


def _default_scraper_factory(timeout: float) -> Callable[[str, str], Any]:
    """Factory real: ``get_scraper(ats, slug, timeout=..., include_descriptions=False)``.

    ``include_descriptions=False`` deixa explicito que o caminho e detail por
    vaga (``get_description``), NAO coleta em massa do tenant (``afetch``) —
    nenhum override de ``get_description`` consulta o flag na 0.3.0.
    """
    def factory(ats: str, slug: str) -> Any:
        return get_scraper(
            ats, slug, timeout=timeout, include_descriptions=False
        )
    return factory


def print_hydration_report(stats: dict[str, Any]) -> None:
    """Imprime o resumo da hidratacao (visibilidade no stdout do run)."""
    total = stats.get("eligible_before_hydration", 0)
    before = stats.get("description_coverage_before", 0)
    after = stats.get("description_coverage_after", 0)
    print("\n=== Hidratacao seletiva de descriptions ===")
    print(f"  elegiveis          : {total}")
    print(f"  ja com description : {stats.get('already_has_description', 0)}")
    print(f"  candidatos         : {stats.get('hydration_candidates', 0)}")
    print(f"  hidratadas         : {stats.get('hydration_success', 0)}")
    print(f"  falhas             : {stats.get('hydration_failed', 0)}")
    print(f"  sem endpoint (ATS) : {stats.get('unsupported_no_detail', 0)}")
    print(f"  skip (orcamento)   : {stats.get('hydration_skipped', 0)}")
    print(f"  cobertura antes    : {before}/{total} "
          f"({100 * before / total:.1f}%)" if total else "  cobertura antes    : -")
    print(f"  cobertura depois   : {after}/{total} "
          f"({100 * after / total:.1f}%)" if total else "  cobertura depois   : -")
    print(f"  duracao            : {stats.get('hydration_duration', 0.0):.1f}s")
    by_ats = stats.get("by_ats", {})
    if any(v.get("candidates") for v in by_ats.values()):
        print("  por ATS (candidatos/ok/falha/sem-endpoint):")
        for ats in sorted(by_ats):
            v = by_ats[ats]
            if v.get("candidates"):
                print(f"    {ats:<16} {v['candidates']:>3} / {v['success']:>3} "
                      f"/ {v['failed']:>3} / {v.get('unsupported', 0):>3}")
    teaser = stats.get("phenom_teaser_count", 0)
    if teaser:
        print(f"  phenom teaser (<{TEASER_MAX_CHARS} chars, so observa): {teaser}")
