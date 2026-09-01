"""Observabilidade de consumo: relatorio de health por tenant/ATS.

Consome o JSONL de metricas de execucao (``data/collection_metrics.jsonl``,
ver ``internship_finder.metrics``), produzido pelo modo coleta do CLI, e gera
um relatorio estruturado (dict JSON-serializavel) com resumo por ``source``
(tenant) e por ATS, alem de dois alertas:

- **Queda brusca**: um source cujo ultimo run terminou ``ok`` mas coletou menos
  que ``DROP_THRESHOLD`` da mediana dos ``MIN_OK_HISTORY_FOR_DROP`` runs ok
  anteriores. Com historia curta (menos que o gate) NAO alerta.
- **Erro recorrente**: um source com ``status`` em {timeout, error} nos ultimos
  ``CONSECUTIVE_FAILURES`` runs consecutivos (por ordem de ``run_id``).

O relatorio e um dict JSON-serializavel pronto para ``json.dumps``. O consumo
e defensivo: um registro malformado (JSON invalido, campos ausentes) nunca
derruba — e pulado com um aviso no stderr.

Limiares/gates (constantes nomeadas abaixo; valores justificados na docstring
de cada uma). Sao arbitrarios por natureza — registrar como limitacao.
"""

from __future__ import annotations

import json
import sys
from typing import Any

# --- Constantes de limiar / gate -------------------------------------------
# Numeros magicos evitados: os limites abaixo sao os unicos valores de threshold
# do modulo e ficam centralizados aqui, com a justificativa.

# Numero minimo de runs ok ANTERIORES para um source emitir alerta de queda
# brusca. Um run preciso que a queda atual compare contra a mediana de pelo
# menos 3 observacoes ok previas: com historia curta (1-2 runs), a mediana e
# instavel e um unico valor alto distorceria a comparacao, gerando falso
# positivo. Gate conservador: fontes com menos de 3 amostras ok anteriores nao
# alertam.
MIN_OK_HISTORY_FOR_DROP = 3

# A queda brusca e sinalizada quando o ``collected`` do ultimo run ok e menor
# que 50% (0.5) da mediana dos runs ok anteriores. Um coletor real flutua de
# forma natural (vagas vazam/preenchem), entao 50% separa uma queda forte
# (mediana cai pela metade) de variacao cotidiana — pegando grandes regressoes
# sem disparar em ruido pequeno. Arbitrario; ajustar com dados reais se houver
# ruido excessivo (falso positivo) ou quedas reais nao detectadas.
DROP_THRESHOLD = 0.5

# Numero de runs CONSECUTIVOS com status {timeout, error} para um source emitir
# alerta de erro recorrente. Um unico timeout/erro e comum (rede, site em
# manutencao); dois consecutivos sugerem um problema sistemico no tenant/ATS.
CONSECUTIVE_FAILURES = 2


def _normalize_duration(value: Any) -> float | None:
    """Normaliza ``duration`` (float ou string ``"1.0s"``) para float secundos.

    Strings antigas tinham o sufixo ``s`` (ex.: ``"1.0s"``); registros novos
    sao float. Devolve ``None`` para ``None``/ausente ou valor inparseavel.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    text = str(value).strip().lower()
    if text.endswith("s"):
        text = text[:-1]
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _valid_run_id(value: Any) -> str | None:
    """Devolve o ``run_id`` ordenavel (string) ou ``None`` se ausente."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _tenant_records(records: list[dict], warnings: list[str]) -> list[dict]:
    """Filtra os registros ``type: tenant`` minimamente validos do JSONL.

    Registros malformados (nao-dict, ``type`` ausente/nao-tenant, sem
    ``source`` ou sem ``run_id``/``timestamp`` ordenavel) sao pulados com um
    aviso. Nunca derruba a analise.
    """
    output: list[dict] = []

    def _warn(idx: int, why: str) -> None:
        msg = f"[health] registro {idx} ignorado: {why}"
        print(msg, file=sys.stderr)
        warnings.append(msg)

    for idx, rec in enumerate(records):
        if not isinstance(rec, dict):
            _warn(idx, "nao e um objeto JSON")
            continue
        if rec.get("type") != "tenant":
            continue
        source = rec.get("source")
        if not isinstance(source, str) or not source:
            _warn(idx, "sem source")
            continue
        run_id = _valid_run_id(rec.get("run_id"))
        timestamp = _valid_run_id(rec.get("timestamp"))
        if run_id is None and timestamp is None:
            _warn(idx, "sem run_id nem timestamp para ordenar")
            continue
        status = rec.get("status")
        if not isinstance(status, str):
            _warn(idx, "status invalido")
            continue
        output.append(
            {
                "source": source,
                "ats": (rec.get("ats") if isinstance(rec.get("ats"), str) else (source.split(":", 1)[0] if ":" in source else source)),
                "run_id": run_id,
                "timestamp": timestamp,
                "status": status,
                "collected": rec.get("collected") if isinstance(rec.get("collected"), int) else 0,
                "duration": _normalize_duration(rec.get("duration")),
            }
        )
    return output


def _sort_key(rec: dict) -> tuple:
    """Chave de ordenacao: run_id (ISO 8601, ordenavel como string) e fallback timestamp."""
    if rec.get("run_id") is not None:
        return (0, rec["run_id"])
    return (1, rec.get("timestamp") or "")


def _summary_per_source(rows: list[dict]) -> dict:
    """Resumo por source (tenant): ultimo estado + medias dos runs ok."""
    ok_rows = [r for r in rows if r["status"] == "ok"]
    last = rows[-1]
    if ok_rows:
        dur_ok = [r["duration"] for r in ok_rows if r["duration"] is not None]
        med_duration = round(sum(dur_ok) / len(dur_ok), 3) if dur_ok else None
    else:
        med_duration = None
    return {
        "source": last["source"],
        "last_status": last["status"],
        "last_collected": last["collected"],
        "last_duration": last["duration"],
        "avg_collected_ok": round(sum(r["collected"] for r in ok_rows) / len(ok_rows), 2) if ok_rows else None,
        "avg_duration_ok": med_duration,
        "total_runs": len(rows),
        "ok_runs": len(ok_rows),
    }


def _detect_drops(rows: list[dict]) -> list[dict]:
    """Queda brusca no ultimo run ok de um source, com gate de historico."""
    ok_rows = [r for r in rows if r["status"] == "ok"]
    if len(ok_rows) <= MIN_OK_HISTORY_FOR_DROP:
        return []
    prior = ok_rows[:-1]
    last = ok_rows[-1]
    history = [r["collected"] for r in prior]
    median = sorted(history)[len(history) // 2]
    if median == 0:
        return []
    pct = last["collected"] / median
    if pct < DROP_THRESHOLD:
        return [
            {
                "type": "drop",
                "source": last["source"],
                "mediana_anterior": median,
                "collected_atual": last["collected"],
                "pct": round(pct, 3),
            }
        ]
    return []


def _detect_consecutive_failures(rows: list[dict]) -> list[dict]:
    """Erro recorrente: runs mais recentes consecutivos em {timeout, error}.

    Conta a sequencia CONSECUTIVA de falhas a partir do run mais recente
    (por ordem de ``run_id``) e somente alerta quando essa sequencia chega a
    ``CONSECUTIVE_FAILURES``. ``runs_seq`` traz o tamanho real da sequencia
    (ex.: 3 falhas -> ``runs_seq`` 3), nao apenas o limiar.
    """
    count = 0
    source = None
    for r in reversed(rows):
        if r["status"] in ("timeout", "error"):
            count += 1
            source = r["source"]
        else:
            break
    if count >= CONSECUTIVE_FAILURES and source is not None:
        return [{"type": "recurring_error", "source": source, "runs_seq": count}]
    return []


def build_health_report(
    records: list[dict], warnings: list[str] | None = None
) -> dict:
    """Gera o relatorio de health a partir dos registros do JSONL.

    A entrada e a saida de ``internship_finder.metrics.read_metrics`` (ou
    equivalente). Devolve um dict JSON-serializavel com ``summary_per_source``,
    ``summary_per_ats`` e ``alerts``.
    """
    _warnings: list[str] = []
    tenants = _tenant_records(records, _warnings)
    if warnings is not None:
        warnings.extend(_warnings)

    by_source: dict[str, list[dict]] = {}
    for rec in tenants:
        by_source.setdefault(rec["source"], []).append(rec)
    for rows in by_source.values():
        rows.sort(key=_sort_key)

    sources = []
    for src in sorted(by_source):
        rows = by_source[src]
        s = _summary_per_source(rows)
        s["alerts"] = _detect_drops(rows) + _detect_consecutive_failures(rows)
        sources.append(s)

    alert_sources = [a for s in sources for a in s["alerts"]]

    by_ats: dict[str, list[dict]] = {}
    for rec in tenants:
        by_ats.setdefault(rec["ats"], []).append(rec)

    ats_summaries = []
    for ats in sorted(by_ats):
        rows = by_ats[ats]
        ok_rows = [r for r in rows if r["status"] == "ok"]
        dur_ok = [r["duration"] for r in ok_rows if r["duration"] is not None]
        ats_summaries.append(
            {
                "ats": ats,
                "sources": len({r["source"] for r in rows}),
                "total_runs": len(rows),
                "ok_runs": len(ok_rows),
                "fail_runs": sum(1 for r in rows if r["status"] in ("timeout", "error")),
                "last_status": rows[-1]["status"],
                "last_collected": rows[-1]["collected"],
                "last_duration": rows[-1]["duration"],
                "avg_collected_ok": round(sum(r["collected"] for r in ok_rows) / len(ok_rows), 2) if ok_rows else None,
                "avg_duration_ok": round(sum(dur_ok) / len(dur_ok), 3) if dur_ok else None,
            }
        )

    return {
        "sources": sources,
        "ats": ats_summaries,
        "alerts": alert_sources,
        "warnings": _warnings,
    }