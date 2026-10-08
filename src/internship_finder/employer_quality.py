"""Employer Quality — Fase F15 (mapa curado Kununu/GPTW).

Camada DETERMINÍSTICA, offline e INDEPENDENTE do ranking — o badge ⭐/🏆
INFORMA a decisão de aplicar, não reordena nada (pesos do ranking intocados;
nenhum valor aqui entra no score de relevância).

Padrão REUSADO da F9/F10 (company_intelligence.json / ``company_intel_for``):

- **Match EXATO por company string** (casefold + acentos colapsados via o
  MESMO ``_norm`` do opportunity_intel — sem fuzzy, sem substring);
- **Empresa sem entrada = silêncio gracioso**: ``quality_for`` devolve None,
  a página/digest ficam byte a byte como antes, SEM erro;
- **Arquivo ausente/corrompido = mapa vazio**: o pipeline nunca quebra por
  causa do mapa (best-effort, igual ``load_company_intel``).

Fonte dos dados (F15 §1): mapa é PESQUISA MANUAL versionada em
``config/employer_quality.json`` — cada entrada carrega ``kununu_score``
(0-5), ``kununu_reviews`` (contagem), ``gptw_award`` (ano ou null),
``source_url`` e ``checked`` (data ISO da consulta). O pipeline NUNCA
consulta Kununu/GPTW no build (zero HTTP externo — travado por teste);
a atualização do mapa é curadoria humana, igual ao company_intel.

O cruzamento "ponto ótimo" (F15 §4) é derivado NO BUILD:
volume de vagas eligible × qualidade (Kununu >= 4,0 OU prêmio GPTW) ×
visa_friendly (intel_map F9/F10) — SEM rede, lendo só o dataset local e
os dois arquivos curados versionados.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from internship_finder.opportunity_intel import _norm

# Arquivo curado versionado no repo (config/, NUNCA data/ — data/ é gitignored
# e regenerado todo run; o mapa é curadoria estática).
DEFAULT_EMPLOYER_QUALITY_PATH = Path("config/employer_quality.json")

# Fontes válidas de score por entrada (o mapa registra como foi apurado).
SOURCE_TYPES = ("kununu-profile", "kununu-ranking-2026", "news-quote", "unavailable")

# F15 §4 — critério do cruzamento "ponto ótimo": qualidade =
# Kununu >= 4,0 OU prêmio GPTW (qualquer ano). Ambos são sinais de
# "empresa grande com boa qualidade de trabalho" (a pergunta do dono).
SWEET_SPOT_MIN_SCORE = 4.0
SWEET_SPOT_TOP = 15


def load_employer_quality(path: str | Path | None = None) -> dict[str, dict]:
    """Lê o mapa curado de qualidade de empregador; ``{}`` em qualquer falha.

    Chave: nome da empresa normalizado (``_norm`` — casefold + acentos
    colapsados), igual ao ``load_company_intel``. Entradas com
    ``kununu_score: null`` (perfil "unavailable") ENTRAM no mapa: o badge
    não renderiza (sem score), mas o ``kununu_reviews`` fica auditável.
    Arquivo ausente/JSON quebrado/lista vazia nunca levantam exceção.
    """
    if path is None:
        path = DEFAULT_EMPLOYER_QUALITY_PATH
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = raw.get("companies") if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            return {}
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("company"):
            continue
        out[_norm(entry["company"])] = entry
    return out


def quality_for(job: dict, quality_map: dict[str, dict]) -> dict | None:
    """Entrada de qualidade do empregador da vaga; ``None`` quando não mapeada.

    MESMO contrato do ``company_intel_for`` (F9/F10): match EXATO por
    company string normalizada. Empresa sem entrada = silêncio, sem erro.
    """
    name = str(job.get("company") or "").strip()
    if not name:
        return None
    return quality_map.get(_norm(name))


def _score_of(entry: dict | None) -> float | None:
    """Kununu Score da entrada como float 0-5; ``None`` sem score válido.

    Conservador: valores fora de [0, 5] e não-numéricos devolvem None
    (nunca promovem uma entrada corrompida a "boa" no ponto ótimo).
    """
    if not entry:
        return None
    value = entry.get("kununu_score")
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if isinstance(value, bool) or not 0.0 <= score <= 5.0:
        return None
    return score


def has_gptw(entry: dict | None) -> bool:
    """Entrada carrega prêmio GPTW (ano presente e plausível)?"""
    if not entry:
        return False
    award = entry.get("gptw_award")
    try:
        return 2000 < int(award) < 2100  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def badge_text(entry: dict | None) -> str:
    """Texto curto do badge de qualidade (F15 §2); ``''`` quando não há.

    - Prêmio GPTW vence (mais raro/valioso): ``🏆 GPTW <ano>``;
    - Senão, score Kununu presente: ``⭐ <N,N> · Kununu`` (uma casa
      decimal, vírgula — exibição alemã consistente com a página);
    - Entrada sem score e sem prêmio ("unavailable"): SEM badge —
      a entrada existe para auditoria do mapa, não para render ruído.
    """
    if has_gptw(entry):
        return f"🏆 GPTW {int(entry['gptw_award'])}"
    score = _score_of(entry)
    if score is not None:
        return f"⭐ {score:.1f}".replace(".", ",") + " · Kununu"
    return ""


def sweet_spot_companies(
    jobs: list[dict],
    quality_map: dict[str, dict],
    intel_map: dict[str, dict] | None,
    *,
    min_score: float = SWEET_SPOT_MIN_SCORE,
    top: int = SWEET_SPOT_TOP,
) -> list[dict]:
    """Cruzamento "ponto ótimo" (F15 §4; pura, offline, derivada NO BUILD).

    Empresa entra quando TODOS os três critérios valem:

    1. **volume**: tem vagas eligible no dataset (contagem do próprio
       ``jobs`` passado — o chamador usa o eligible_jobs.json do run);
    2. **qualidade**: Kununu Score >= ``min_score`` (4,0) OU prêmio GPTW;
    3. **visa_friendly**: estado do intel_map F9/F10 (explicit_support ou
       unclear — a MESMA regra de ``opportunity_intel.visa_friendly``,
       consultada pela entrada de company intel da empresa).

    Ordenação: volume DESC (a lista responde "onde aplicar com mais
    chances + boa qualidade", não é um ranking de qualidade). Empresas
    empatadas por volume: score DESC, depois nome (determinístico).
    ``intel_map=None``/empresa sem intel = visa_friendly False = fora
    (critério do dono: o ponto ótimo EXIGE a política de visto).
    """
    from internship_finder.opportunity_intel import company_intel_for, visa_friendly

    volumes: dict[str, int] = {}
    display: dict[str, str] = {}
    for job in jobs:
        name = str(job.get("company") or "").strip()
        if not name:
            continue
        key = _norm(name)
        volumes[key] = volumes.get(key, 0) + 1
        display.setdefault(key, name)

    rows: list[dict] = []
    for key, volume in volumes.items():
        entry = quality_map.get(key)
        if entry is None:
            continue
        score = _score_of(entry)
        gptw = has_gptw(entry)
        if score is None and not gptw:
            continue  # sem sinal de qualidade = não é ponto ótimo
        if score is not None and score < min_score and not gptw:
            continue  # score abaixo do corte e sem prêmio = fora
        if intel_map is None:
            continue
        intel_entry = company_intel_for({"company": display[key]}, intel_map)
        if not visa_friendly(intel_entry):
            continue
        rows.append({
            "company": display[key],
            "eligible": volume,
            "kununu_score": score,
            "gptw_award": entry.get("gptw_award") if gptw else None,
        })
    rows.sort(key=lambda r: (-r["eligible"],
                             -(r["kununu_score"] or 0.0), r["company"]))
    return rows[:top]


def sweet_spot_lines(
    jobs: list[dict],
    quality_map: dict[str, dict],
    intel_map: dict[str, dict] | None,
    *,
    top: int = SWEET_SPOT_TOP,
) -> list[str]:
    """Linhas estáticas da seção "⭐ Ponto ótimo" (F15 §4); ``[]`` quando vazio.

    Formato (1 linha por empresa): ``<nome> · <score|GPTW ano> · N vagas
    eligible ativas``. Pura — a página/digest só imprimem. Zero HTTP.
    """
    rows = sweet_spot_companies(jobs, quality_map, intel_map, top=top)
    if not rows:
        return []
    lines: list[str] = []
    for r in rows:
        if r["gptw_award"] and r["kununu_score"] is None:
            quality = f"🏆 GPTW {int(r['gptw_award'])}"
        elif r["gptw_award"]:
            quality = f"⭐ {r['kununu_score']:.1f}".replace(".", ",") \
                + f" · 🏆 GPTW {int(r['gptw_award'])}"
        else:
            quality = f"⭐ {r['kununu_score']:.1f}".replace(".", ",") + " · Kununu"
        n = r["eligible"]
        lines.append(
            f"{r['company']} · {quality} · {n} vaga{'s' if n != 1 else ''} eligible")
    return lines


__all__ = [
    "DEFAULT_EMPLOYER_QUALITY_PATH",
    "SOURCE_TYPES",
    "SWEET_SPOT_MIN_SCORE",
    "SWEET_SPOT_TOP",
    "load_employer_quality",
    "quality_for",
    "badge_text",
    "has_gptw",
    "sweet_spot_companies",
    "sweet_spot_lines",
]
