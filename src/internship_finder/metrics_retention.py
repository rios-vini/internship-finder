"""F75 — Retenção do ``collection_metrics.jsonl``: rollup diário além do corte.

PROBLEMA (âncora 19/10): ``data/collection_metrics.jsonl`` cresce SEM
retenção — 1,87 MB, ~5,3k registros, 31/08→19/10, ~110 linhas/run do cron
(1 registro ``tenant`` por empresa). O arquivo é append-only (``write_metrics``
da coleta) e lido pelo health (``build_health_report``), pelo funil
(``funnel_report.load_run_records``) e pelo digest (seção 📅). Sem corte,
cresce para sempre.

REGRA (F75, item 3 da spec — ``~/.hermes/handoff/f75-analitica/ESPECIFICACAO.md``):

- Dentro do corte (default ``90`` dias — ``DEFAULT_METRICS_RETENTION_DAYS``,
  ajustável pelo dono via ``--metrics-retention-days`` do refresh; ``0``
  desliga): registros RAW, byte a byte, intocados.
- ALÉM do corte: registros agrupados por DIA em UM registro
  ``type: metrics_rollup`` por dia — contagem por ``type`` e SOMA dos campos
  numéricos escalares POR type (``run.total_collected`` e ``tenant.collected``
  têm semânticas distintas; somá-los juntos mentiria). Campos textuais
  (company/source/error) são detalhe por registro e somem — o RAW completo
  de cada dia continua nos snapshots ``data/archive/<ts>/`` pelo prazo do
  ``--retention-days`` do archive (backup de curto prazo; o rollup é a
  retenção de longo prazo).

PROPRIEDADES (contrato de teste):

- ``Idempotente``: registros ``metrics_rollup`` já existentes NUNCA são
  re-agregados — um segundo run é no-op (``changed=False``) e o arquivo
  não é reescrito.
- ``Nunca destrói``: linha vazia/corrompida e registro sem timestamp
  legível ficam RAW (conservador — o corte só agarra o que consegue
  datar). Arquivo ausente = no-op, nunca lança para o chamador do
  refresh (best-effort, padrão backup do jobs.db).
- ``Atômico``: escreve ``<path>.tmp`` + ``os.replace`` — morte de
  processo no meio nunca deixa arquivo parcial.
- ``Determinável``: ``now`` injetável para testes; sem ``now`` usa o
  relógio vivo.
- ``Executada pelo refresh em runtime`` (passo 1c, ANTES do snapshot de
  linhas ``skip_lines`` e ANTES da coleta, que só APPENDE) — NUNCA
  hand-edit em data/ (regra P0 3).

Efeito nos consumidores (documentado, aceito):

- ``health`` (``_tenant_records`` filtra ``type == "tenant"``): séries
  perdem os pontos >90d — mediana comparada passa a olhar a janela viva
  (era o espírito do health: estado ATUAL, não histórico eterno).
- ``funil/digest`` (drift semanal = 7 runs; trend idem): janela de 7
  muito menor que 90 — nada muda no dia a dia.

Uso::

    from internship_finder.metrics_retention import rollup_metrics
    summary = rollup_metrics(Path("data/collection_metrics.jsonl"),
                            retention_days=90)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Default do corte em dias (dono ajusta via --metrics-retention-days; 0 = off).
DEFAULT_METRICS_RETENTION_DAYS = 90

# Marcador de tipo dos registros agregados (consumidores existentes filtram
# por type — health ignora, funnel ignora; novos consumidores têm um tipo
# novo e auto-descritivo).
ROLLUP_TYPE = "metrics_rollup"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    """Timestamp ISO do registro (``timestamp`` ou ``run_id`` de fallback).

    Formatos vivos no arquivo: ``2026-08-31T22:35:04.842305+00:00`` (o
    ``utcnow_iso`` da coleta). Tolerante a ``Z`` final (ISO 8601). Qualquer
    coisa não-datatável devolve None (o registro fica RAW — nunca destrói).
    """
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_number(value: Any) -> bool:
    """Escalar numérico somável (bool NUNCA — é flag, não medida)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _accumulate(bucket: dict, record: dict) -> None:
    """Soma um registro RAW no bucket do dia (contagem por type + somas)."""
    rtype = str(record.get("type") or "?")
    per_type = bucket.setdefault(rtype, {"count": 0, "sums": {}})
    per_type["count"] += 1
    sums = per_type["sums"]
    for key, value in record.items():
        if key in ("type", "timestamp", "run_id"):
            continue  # identidade do registro, não medida
        if _is_number(value):
            sums[key] = sums.get(key, 0) + value


def rollup_metrics(
    metrics_path: str | Path,
    *,
    retention_days: int = DEFAULT_METRICS_RETENTION_DAYS,
    now: datetime | None = None,
) -> dict:
    """Rollup diário dos registros além do corte — raw recente + agregado antigo.

    Lê ``metrics_path``, agrupa os registros datáveis mais antigos que
    ``now - retention_days`` em um registro ``metrics_rollup`` POR DIA e
    reescreve o arquivo atomicamente: [rollups por dia, em ordem] +
    [registros raw na ordem original]. Retorna o resumo da operação
    (dict JSON-serializável — o refresh loga):

        {"changed": bool, "rolled_days": int, "rolled_records": int,
         "raw_kept": int, "retention_days": int, "path": str,
         "reason": str}   # reason quando changed=False

    ``retention_days <= 0`` desliga (no-op, arquivo intocado). Arquivo
    ausente/vazio = no-op. Nunca lança por conteúdo (linha corrompida é
    preservada RAW); erros de E/O propagam para o chamador decidir log.
    """
    path = Path(metrics_path)
    summary = {
        "changed": False,
        "rolled_days": 0,
        "rolled_records": 0,
        "raw_kept": 0,
        "retention_days": retention_days,
        "path": str(path),
        "reason": "",
    }
    if retention_days <= 0:
        summary["reason"] = "retenção desligada (retention_days <= 0)"
        return summary
    if not path.exists():
        summary["reason"] = "arquivo ausente"
        return summary
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        summary["reason"] = "arquivo ausente"
        return summary

    ref = now or _now_utc()
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    cutoff = ref - timedelta(days=retention_days)

    raw: list[str] = []
    days: dict[str, dict] = {}
    day_order: list[str] = []
    rolled_records = 0
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            raw.append(line)
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            raw.append(line)  # corrompido: nunca destrói
            continue
        if not isinstance(record, dict):
            raw.append(line)
            continue
        if record.get("type") == ROLLUP_TYPE:
            raw.append(line)  # já agregado: idempotência
            continue
        ts = _parse_ts(record.get("timestamp")) or _parse_ts(record.get("run_id"))
        if ts is None or ts >= cutoff:
            raw.append(line)
            continue
        day = ts.date().isoformat()
        if day not in days:
            days[day] = {}
            day_order.append(day)
        _accumulate(days[day], record)
        rolled_records += 1

    summary["raw_kept"] = len(raw)
    if not days:
        summary["reason"] = "nenhum registro além do corte"
        return summary

    out: list[str] = []
    for day in day_order:
        rollup = {
            "type": ROLLUP_TYPE,
            "date": day,
            "timestamp": ref.isoformat(),
            "rolled_records": sum(
                per["count"] for per in days[day].values()),
            "by_type": {rtype: {"count": per["count"], "sums": per["sums"]}
                        for rtype, per in sorted(days[day].items())},
        }
        out.append(json.dumps(rollup, ensure_ascii=False))
    out.extend(raw)

    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    summary["changed"] = True
    summary["rolled_days"] = len(day_order)
    summary["rolled_records"] = rolled_records
    return summary
