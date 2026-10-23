"""F103 -- Flag de re-post/twin no 🆕 do digest (display-only).

Detecta re-posts (mesma vaga, id novo) e twins cross-ATS (mesma vaga,
fonte ATS diferente) comparando o run atual contra o run anterior.
Chave de near-dup: titulo normalizado + empresa normalizada + localizacao
normalizada (sem URL -- re-post muda URL por definicao).

Design constraints:
1. Display-only 🔄, NUNCA exclusao (precedente F62/F95: flag, nao gate).
2. Universo de comparacao: jobs do run anterior (archive/ ou eligible
   carregado pelo digest) -- NAO precisa de historico infinito.
3. Config versionada e fail-closed: config/repost_window.json ausente/
   corrompido = flag OFF sem erro.
4. Metrica no run: repost_flagged: N no stats/JSONL (padrao F75).
"""

from __future__ import annotations

import html as _html
import json
from pathlib import Path
from typing import Any

from internship_finder.dedup import normalize_title, normalize_location

# Emoji constants (avoid escape sequence issues in f-strings)
REPOST_EMOJI = chr(0x1F504)
NEW_EMOJI = chr(0x1F195)

# ---------------------------------------------------------------------------
# Normalizacao de empresa (reuso do ranking_digest._norm_company)
# ---------------------------------------------------------------------------


def _norm_company(value: str | None) -> str:
    """Casefold + colapso de espacos (mesma normalizacao do cap de exibicao)."""
    return " ".join(str(value or "").strip().casefold().split())


# ---------------------------------------------------------------------------
# Chave de near-dup para re-post/twin
# ---------------------------------------------------------------------------


def repost_key(job: dict[str, Any]) -> str | None:
    """Chave deterministica de near-dup: (titulo_norm, empresa_norm, local_norm).

    Retorna None quando algum componente obrigatorio esta vazio --
    sem localizacao, titulos iguais em cidades diferentes NAO fundem
    (mesma regra do tier 3 da dedup).
    """
    company = _norm_company(job.get("company"))
    title = normalize_title(job.get("title"))
    location = normalize_location(job.get("location"))

    if not company or not title or not location:
        return None
    return f"{company}|{title}|{location}"


# ---------------------------------------------------------------------------
# Construcao do indice de chaves do run anterior
# ---------------------------------------------------------------------------


def build_previous_index(previous_jobs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Indice {repost_key: [jobs...]} do run anterior.

    Aceita lista vazia -> indice vazio (nenhum match).
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for job in previous_jobs:
        key = repost_key(job)
        if key is None:
            continue
        index.setdefault(key, []).append(job)
    return index


# ---------------------------------------------------------------------------
# Deteccao de re-post/twin no run atual
# ---------------------------------------------------------------------------


def flag_reposts(
    current_jobs: list[dict[str, Any]],
    previous_index: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], int]:
    """Marca jobs do run atual que sao re-post/twin do run anterior.

    Retorna (jobs_com_flag, total_flagged) onde cada job flagged ganha
    o campo repost_match com info do match (company do match anterior).
    Mutabilidade in-place dos dicts de entrada (padrao do pipeline).

    Regra: match EXATO de chave (titulo_norm + empresa_norm + local_norm).
    Se multiplos jobs no indice anterior batem, usa o primeiro (deterministico
    pela ordem de construcao do indice).
    """
    flagged = 0
    for job in current_jobs:
        key = repost_key(job)
        if key is None:
            continue
        matches = previous_index.get(key)
        if matches:
            # Pega a empresa do primeiro match (display-only)
            match_company = str(matches[0].get("company") or "").strip()
            job["repost_match"] = {
                "company": match_company,
                "key": key,
            }
            flagged += 1
    return current_jobs, flagged


# ---------------------------------------------------------------------------
# Config versionada fail-closed (padrao F66)
# ---------------------------------------------------------------------------


DEFAULT_REPOST_WINDOW_DAYS = 7


def load_repost_config(config_path: str | Path | None = None) -> dict[str, Any] | None:
    """Carrega config/repost_window.json; ausente/corrompido = None (flag OFF).

    Schema esperado: {"window_days": int}. Valores invalidos -> None.
    """
    if config_path is None:
        # Default: config/ ao lado do modulo (src/../config/)
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "repost_window.json"
    try:
        data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    window = data.get("window_days")
    if not isinstance(window, int) or window <= 0:
        return None
    return {"window_days": window}


def is_repost_flag_enabled(config: dict[str, Any] | None) -> bool:
    """True quando a flag esta habilitada (config valida presente)."""
    return config is not None


# ---------------------------------------------------------------------------
# Formatacao para digest (linha 🆕)
# ---------------------------------------------------------------------------


REPOST_FLAG_SUFFIX = " " + REPOST_EMOJI + " possivel re-post (de {company} \u2014 ver MANUAL-CHECK)"


def format_repost_suffix(job: dict[str, Any]) -> str:
    """Sufixo 🔄 para a linha 🆕 do digest.

    Retorna string vazia se o job nao tem repost_match.
    """
    match = job.get("repost_match")
    if not match:
        return ""
    company = match.get("company") or "empresa desconhecida"
    return REPOST_FLAG_SUFFIX.format(company=company)


# ---------------------------------------------------------------------------
# Atributo para card da pagina (display-only)
# ---------------------------------------------------------------------------


def repost_card_attr(job: dict[str, Any]) -> str:
    """Atributo data-repost para o card HTML.

    Retorna data-repost="company" quando flagged, string vazia caso contrario.
    """
    match = job.get("repost_match")
    if not match:
        return ""
    company = match.get("company") or "unknown"
    # Escape do valor para atributo HTML (defensivo — o dado vem do
    # dataset). Usa o escape do stdlib (evita literais de entidade
    # HTML no fonte — o escape e derivado, nunca hardcoded).
    safe = _html.escape(str(company), quote=True)
    return ' data-repost="' + safe + '"'


def repost_badge_html(job: dict[str, Any], lang: str = "pt") -> str:
    """Badge discreto re-post para o card (mesma area dos badges F5/F14/F15).

    Retorna HTML do span ou string vazia. lang controla o texto do title.
    """
    match = job.get("repost_match")
    if not match:
        return ""
    company = match.get("company") or "empresa desconhecida"
    if lang == "en":
        title = "Possible re-post from " + company + " \u2014 see MANUAL-CHECK"
    else:
        title = "Possivel re-post de " + company + " \u2014 ver MANUAL-CHECK"
    # Mesmo estilo dos badges .flag (cor amber, tamanho 0.72rem)
    return ' <span class="flag" title="' + title + '">' + REPOST_EMOJI + ' re-post</span>'


# ---------------------------------------------------------------------------
# Metrica para stats/JSONL (padrao F75)
# ---------------------------------------------------------------------------


def repost_metric(flagged_count: int) -> dict[str, int]:
    """Entrada de metrica para collection_metrics.jsonl."""
    return {"repost_flagged": flagged_count}


def count_reposts(
    current_jobs: list[dict[str, Any]],
    previous_jobs: list[dict[str, Any]],
) -> int:
    """Quantos jobs do run atual sao re-post/twin do run anterior (F103).

    Mesma chave e mesma regra de ``flag_reposts`` — funcao de CONTAGEM pura
    para a metrica do run (padrao F75), sem mutar os jobs de entrada.
    """
    _, flagged = flag_reposts(
        [dict(j) for j in current_jobs],  # copias raras: sem mutar entrada
        build_previous_index(previous_jobs),
    )
    return flagged


def count_reposts_from_paths(
    current_path: str | Path,
    previous_path: str | Path,
) -> int:
    """Contagem de re-posts a partir dos DOIS arquivos do run (F103).

    Mesmos arquivos que o digest usa (eligible atual × snapshot da
    rotacao) — resultado deterministico identico ao flag do display.
    Config ausente/corrompida (flag OFF) ou arquivos ilegiveis = 0.
    """
    if not is_repost_flag_enabled(load_repost_config()):
        return 0

    def _load(path: str | Path) -> list[dict[str, Any]]:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        return [j for j in data if isinstance(j, dict)]

    return count_reposts(_load(current_path), _load(previous_path))