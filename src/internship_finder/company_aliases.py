#!/usr/bin/env python3
"""F92 — canonicalização de empresa + guards de location (ingestão).

Estágio de NORMALIZAÇÃO (não é dedup) aplicado no ``cli.main`` ENTRE
``select_eligible`` e ``deduplicate`` (spec F92: ANTES do dedup):

- **Aliases canônicos de empresa** (classes 1 e 2): o mapa versionado
  ``config/company_aliases.json`` (label sujo -> nome canônico) reescreve o
  CAMPO ``company`` — label-lixo upstream ("SUSONITY" = portal da Merck;
  "Fa Exdu Saasfaprod1" = Daimler Buses) e descasamento dataset×dataset
  ("peeces" × "Peeces GmbH"). O dedup passa a casar os pares por nome
  canônico e o display (página/digest) mostra "Merck KGaA", não "SUSONITY".
  Diferente do F54 (display-only no render) e do F66 (identidade-only no
  cross_source_dedup): aqui o DADO muda — é o estágio de ingestão.

- **Guards de location** (classe 4): strip do prefixo postal alemão
  ("70469 Stuttgart, …" -> "Stuttgart, …"; regex da spec ``^\\d{5}\\s+``,
  a cidade fica) e location vazia/None -> valor do campo ``raw`` quando
  existir, senão sentinela "—" (o display já renderizava "—" para vazio
  via ``_short_location`` F6/F12 — o guard unifica o sentinela no DADO e o
  ``dedup.normalize_location`` o trata como AUSENTE, preservando o
  guardrail "sem localização não funde").

Classe 3 (razão legal de subsidiária) NÃO é tratada aqui por design (spec
item 3): collapse de subsidiária muda contagens de cap por empresa — só
relatório, implementação exige ordem do dono.

Disciplina de degradação (padrão F66/F13): mapa ausente/ilegível/ambíguo
-> ``{}`` e o estágio segue sem aliases; NUNCA derruba o run. Normalização
não é dedup: aplica-se também com ``--no-dedup``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Default ancorado NO PACOTE (CWD-independente: o cron roda da raiz, testes
# de tmpdir passam path explícito — o default serve o checkout em qualquer
# diretório de invocação; o F66 usa path relativo ao CWD, aqui não).
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPANY_ALIASES_PATH = _REPO_ROOT / "config" / "company_aliases.json"

# F92 classe 4 — sentinela de localização desconhecida. ``dedup.normalize_location``
# devolve "" para este valor (contrato testado no test_f92): os tiers
# company+title+location continuam exigindo localização REAL.
MISSING_LOCATION = "—"

# F92 classe 4 — prefixo postal alemão ("70469 Stuttgart, BW" -> "Stuttgart, BW").
# count=1: só o prefixo inicial; cidade e região permanecem.
_POSTAL_PREFIX_RE = re.compile(r"^\d{5}\s+")

# Ordem de fallback no raw (medido 21/10: join_com/eures carregam
# raw['location']; absolventa/jobmensa não têm raw utilizável — raw=None/{}).
_RAW_LOCATION_KEYS = ("location", "city", "ort", "stadt")


def load_company_aliases(path: str | Path | None = None) -> dict[str, str]:
    """Mapa de aliases canônicos F92 (chave casefold -> nome canônico).

    Lê ``config/company_aliases.json`` (ou ``path`` explícito). O arquivo é
    OPCIONAL por design — ausente/ilegível/corrompido/estrutura inválida ->
    ``{}`` e o estágio segue SEM aliases (degradação graciosa, mesma
    disciplina do ``load_watchlist`` F13 / ``load_company_aliases`` F66;
    nunca crasha o run).

    Validações fail-closed (curadoria ambígua rejeita INTEIRA -> ``{}``):
    (1) ``aliases`` precisa ser dict não-vazio de str->str;
    (2) chave ou valor vazio/só-espaços;
    (3) duas chaves que colidem no casefold com valores distintos;
    (4) auto-alias (chave == valor no casefold) é descartado como no-op;
    (5) CICLO/CADEIA: valor cujo casefold é outra CHAVE do mapa (A->B, B->C)
        rejeita o mapa inteiro — o estágio aplica exatamente UM passo.
    """
    target = Path(path) if path is not None else DEFAULT_COMPANY_ALIASES_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    aliases = raw.get("aliases")
    if not isinstance(aliases, dict) or not aliases:
        return {}
    out: dict[str, str] = {}
    for key, value in aliases.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return {}
        k = key.strip().casefold()
        v = value.strip()
        if not k or not v:
            return {}
        if k == v.casefold():
            continue  # auto-alias: no-op silencioso
        if k in out and out[k] != v:
            return {}  # colisão casefold com valores distintos: ambíguo
        out[k] = v
    keys_cf = set(out)
    for value in out.values():
        if value.casefold() in keys_cf:
            return {}  # ciclo/chain: valor é também chave — rejeita inteiro
    return out


def apply_company_aliases(
    jobs: list[dict[str, Any]],
    aliases: dict[str, str],
) -> int:
    """Reescreve ``job['company']`` pela forma canônica (mutação in place).

    Match casefold EXATO da string inteira (nunca substring — regra
    Levio/TYTAN). Retorna quantas vagas foram canonizadas. ``id``/``url``/
    ``raw`` NÃO mudam: o id é identidade técnica (dataset_seen, JSONL,
    tier external_id fallback) e seguir com o label de origem mantém o
    first_seen estável entre runs — a canonização é reversível.
    """
    if not aliases:
        return 0
    applied = 0
    for job in jobs:
        company = job.get("company")
        if not isinstance(company, str) or not company.strip():
            continue
        canonical = aliases.get(company.strip().casefold())
        if canonical is None:
            continue
        job["company"] = canonical
        applied += 1
    return applied


def location_guard(location: str | None, raw: Any) -> str:
    """Guard de location de UMA vaga (classe 4): postal strip / raw / "—"."""
    loc = str(location or "").strip()
    if loc:
        return _POSTAL_PREFIX_RE.sub("", loc, count=1)
    if isinstance(raw, dict):
        for key in _RAW_LOCATION_KEYS:
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return _POSTAL_PREFIX_RE.sub("", value.strip(), count=1)
    return MISSING_LOCATION


def apply_location_guards(jobs: list[dict[str, Any]]) -> dict[str, int]:
    """Aplica o guard de location a todas as vagas (mutação in place).

    Retorna contagens para o relatório do CLI:
    - ``location_postal_stripped``: prefixo postal removido (cidade fica);
    - ``location_filled_from_raw``: vazia/None preenchida do ``raw``;
    - ``location_missing_sentinel``: sem localização em lugar nenhum ->
      sentinela "—" (dedup a trata como ausente; display mostra "—").
    """
    stats = {
        "location_postal_stripped": 0,
        "location_filled_from_raw": 0,
        "location_missing_sentinel": 0,
    }
    for job in jobs:
        original = job.get("location")
        raw = job.get("raw")
        loc = str(original or "").strip()
        if loc:
            cleaned = _POSTAL_PREFIX_RE.sub("", loc, count=1)
            if cleaned != loc:
                job["location"] = cleaned
                stats["location_postal_stripped"] += 1
            continue  # já tinha localização: nunca reescreve por igual
        filled = None
        if isinstance(raw, dict):
            for key in _RAW_LOCATION_KEYS:
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    filled = _POSTAL_PREFIX_RE.sub("", value.strip(), count=1)
                    break
        if filled is not None:
            job["location"] = filled
            stats["location_filled_from_raw"] += 1
        else:
            job["location"] = MISSING_LOCATION
            stats["location_missing_sentinel"] += 1
    return stats


def apply_ingest_normalization(
    jobs: list[dict[str, Any]],
    aliases: dict[str, str] | None = None,
) -> dict[str, int]:
    """Estágio F92 completo (aliases + guards); devolve contagens.

    ``aliases=None`` carrega do default versionado (fail-closed ``{}``).
    Os dicts de ``jobs`` são cópias próprias do pipeline (``to_dict``/
    ``normalize_job_dict`` no ``cli.main``) — mutação in place é segura.
    """
    if aliases is None:
        aliases = load_company_aliases()
    applied = apply_company_aliases(jobs, aliases)
    guard_stats = apply_location_guards(jobs)
    stats = {"company_aliases_applied": applied}
    stats.update(guard_stats)
    return stats


def print_ingest_normalization(stats: dict[str, int]) -> None:
    """Relatório de 1 bloco do estágio F92 (log do cron; determinístico)."""
    print("=== Normalização de ingestão (F92) ===")
    print(f"  empresas canônicas : {stats.get('company_aliases_applied', 0)}")
    print(
        "  location           : "
        f"{stats.get('location_postal_stripped', 0)} postal strip · "
        f"{stats.get('location_filled_from_raw', 0)} do raw · "
        f"{stats.get('location_missing_sentinel', 0)} sem local (—)"
    )
