"""Amostra da spike (spec §5) — selecao estratificada DETERMINISTICA.

Buckets (regra fixada pelo orquestrador, decisao 2):

- a) 10 WA-gap: estado deterministico ``not_mentioned``/``unclear`` COM
  description >1500 chars — os 10 com a MAIOR description (concentra os
  casos onde o LLM pode achar algo; o gap e o objetivo da spike).
- b) 5 Phenom teaser (source ``phenom:*``, desc <400 chars).
- c) 5 official-page problem: status ``js_rendered`` preferivel, senao
  ``not_found``/``http_error`` (na ordem; resto page_problem se faltar).
- d) 5 condicionais/ambiguos: marcadores condicionais (§18) no texto,
  SEM WA deterministico informativo (state em not_mentioned/unclear).
- e) 5 controle: WA deterministico ``existing_required``/``support`` +
  desc "normal" (>400 chars), escolha ALEATORIA com seed fixa (20260928),
  desempate por job_id.

REGRA DE EXCLUSAO: um job entra em UM bucket (prioridade a>b>c>d>e; quem
ja foi escolhido nao e re-escolhido). ``sample.json`` documenta ids,
company, source, url, bucket e o motivo da selecao; desvios da composicao
planejada sao registrados no proprio artefato.
"""

from __future__ import annotations

import random
from typing import Any

SAMPLE_SEED = 20260928  # seed documentada (reprodutivel)
PLAN = {"a_wa_gap": 10, "b_phenom_teaser": 5, "c_page_problem": 5,
        "d_conditional": 5, "e_control": 5}

TEASER_MAX_CHARS = 400
WA_GAP_MIN_DESC = 1500

# Marcadores condicionais (§18) — vocabulario do dataset medido 28/09.
CONDITIONAL_MARKERS: tuple[str, ...] = (
    "ggf.", "ggf ", "falls erforderlich", "falls notwendig", "falls gegeben",
    "if applicable", "if required", "if necessary", "where applicable",
    "where required", "sofern erforderlich", "nach moeglichkeit",
    "nach möglichkeit",
    "may sponsor", "case by case", "case-by-case", "sponsorship may",
    "may be available", "depending on role", "eligible positions",
    "eligible roles", "where required", "visa sponsorship may",
)

_PAGE_PROBLEM_ORDER = (
    "js_rendered", "not_found", "http_error", "timeout",
    "fetch_error", "empty_content",
)


def _wa_state(job: dict[str, Any]) -> str:
    """Lado deterministico (app_intel, funcao pura) — import tardio."""
    from internship_finder import app_intel
    text = f"{job.get('title') or ''} {job.get('description') or ''}"
    return app_intel.work_authorization(text)["state"]


def _official_status(job: dict[str, Any]) -> str | None:
    op = job.get("official_page")
    if isinstance(op, dict):
        return str(op.get("status") or "") or None
    return None


def _desc_len(job: dict[str, Any]) -> int:
    return len(job.get("description") or "")


def _norm_desc_len(job: dict[str, Any]) -> int:
    """Comprimento do TEXTO REAL (tags HTML removidas, app_intel)."""
    from internship_finder import app_intel
    return len(app_intel.normalize_text(job.get("description") or ""))


def _has_conditional(job: dict[str, Any]) -> bool:
    text = f"{job.get('title') or ''} {job.get('description') or ''}".casefold()
    return any(m in text for m in CONDITIONAL_MARKERS)


def build_sample(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retorna a amostra: lista de dicts com job + bucket + reason.

    Deterministica e reprodutivel (seed fixa para o bucket e). Nunca
    reordena o dataset de entrada; empates seguem a ordem do dataset.
    """
    chosen: dict[str, dict[str, Any]] = {}  # job_id -> entry
    order: list[str] = []

    def take(job: dict[str, Any], bucket: str, reason: str) -> None:
        jid = str(job.get("id"))
        if jid in chosen:
            return
        chosen[jid] = {
            "job_id": jid,
            "company": job.get("company"),
            "source": job.get("source"),
            "url": job.get("url"),
            "bucket": bucket,
            "selection_reason": reason,
            "job": job,
        }
        order.append(jid)

    # (a) WA-gap: not_mentioned/unclear com desc >1500 (raw, medido pelo
    #     orquestrador: 298 no dataset), os 10 com MAIOR TEXTO REAL.
    #     AJUSTE IN-RULE (V1, documentado): ranking por comprimento
    #     NORMALIZADO (app_intel.normalize_text remove tags HTML) — em 3
    #     feeds do dataset o comprimento raw e ~90% noise de HTML
    #     (exemplo extremo: 25k raw -> 2.3k de texto real), o oposto do
    #     intent "concentra os casos onde o LLM pode achar algo"
    #     (spec §6: nao mandar HTML bruto).
    wa_gap = [
        j for j in jobs
        if _wa_state(j) in ("not_mentioned", "unclear")
        and _desc_len(j) > WA_GAP_MIN_DESC
    ]
    for job in sorted(wa_gap, key=lambda j: -_norm_desc_len(j))[: PLAN["a_wa_gap"]]:
        take(job, "a_wa_gap",
             f"WA-gap deterministic {_wa_state(job)}, texto normalizado "
             f"{_norm_desc_len(job)} chars (raw {_desc_len(job)}; "
             f"top-{PLAN['a_wa_gap']} maiores conteudos do gap)")

    # (b) Phenom teaser.
    phenom = [
        j for j in jobs
        if str(j.get("source") or "").startswith("phenom:")
        and _desc_len(j) < TEASER_MAX_CHARS
    ]
    for job in phenom[: PLAN["b_phenom_teaser"]]:
        take(job, "b_phenom_teaser",
             f"phenom teaser (desc {_desc_len(job)} chars < {TEASER_MAX_CHARS})")

    # (c) Official-page problem: js_rendered preferivel, senao outros.
    for status in _PAGE_PROBLEM_ORDER:
        if len([e for e in chosen.values() if e["bucket"] == "c_page_problem"]) \
                >= PLAN["c_page_problem"]:
            break
        pool = [j for j in jobs if _official_status(j) == status]
        for job in pool:
            if len([e for e in chosen.values()
                    if e["bucket"] == "c_page_problem"]) >= PLAN["c_page_problem"]:
                break
            take(job, "c_page_problem",
                 f"official_page.status={status} (sem conteudo util da pagina)")

    # (d) Condicionais/ambiguos (marcadores §18), ainda nao escolhidos.
    #     REALIDADE do dataset 28/09: 42 jobs com marcador; 40 deles sao
    #     WA det existing_required (o proprio marcador "ggf. ... Erlaubnis"
    #     alimenta o detector) — exatamente os casos ambiguos onde a spec
    #     §7-A manda ser conservador. NAO restringimos por estado WA.
    cond = [j for j in jobs if _has_conditional(j)]
    for job in cond[: PLAN["d_conditional"]]:
        take(job, "d_conditional",
             f"marcador condicional §18 no texto (WA det: {_wa_state(job)})")

    # (e) Controle: WA informativo (existing_required/support) + desc
    #     normal; escolha aleatoria com seed fixa, desempate por job_id.
    control_pool = [
        j for j in jobs
        if _wa_state(j) in ("existing_required", "support")
        and _desc_len(j) >= TEASER_MAX_CHARS
    ]
    rng = random.Random(SAMPLE_SEED)
    shuffled = sorted(control_pool, key=lambda j: str(j.get("id")))
    rng.shuffle(shuffled)
    for job in shuffled[: PLAN["e_control"]]:
        take(job, "e_control",
             f"controle: WA deterministico informativo ({_wa_state(job)}), "
             f"desc {_desc_len(job)} chars, seed {SAMPLE_SEED}")

    return [chosen[jid] for jid in order]


def sample_composition(sample: list[dict[str, Any]]) -> dict[str, int]:
    """Contagem real por bucket (para sample.json + conferencia V1)."""
    out: dict[str, int] = {}
    for entry in sample:
        out[entry["bucket"]] = out.get(entry["bucket"], 0) + 1
    return out
