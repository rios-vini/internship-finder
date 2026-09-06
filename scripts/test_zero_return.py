"""Testes do detector de zero-return (scripts/test_zero_return.py) — P2 #10.

Standalone e OFFLINE (sem rede, sem escrever em ``data/``): casos sinteticos
via ``build_health_report`` (detecta com gate satisfeito, gate curto NAO
alerta, empty-consistente NAO alerta, ok depois de empty NAO alerta, ordem de
``run_id``, coexistencia com os demais alertas, malformado nao derruba) + bloco
real sobre ``data/collection_metrics.jsonl`` (SO LEITURA; baseline esperada: 0
alertas de zero-return no historico real — medido 05/09 — com SKIP sem o
arquivo, padrao CI). Uso:

    .venv/bin/python scripts/test_zero_return.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.health import (  # noqa: E402
    MIN_OK_HISTORY_FOR_ZERO_RETURN,
    build_health_report,
)

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _tenant(rid: str, source: str, status: str, collected: int,
            error_code: str | None = None) -> dict:
    """Registro tenant minimo e valido (mesmo schema do cli._tenant_record)."""
    return {
        "type": "tenant", "run_id": rid, "timestamp": rid,
        "company": "Acme", "source": source,
        "ats": source.split(":", 1)[0], "status": status,
        "collected": collected,
        "error": None if status not in ("timeout", "error") else "boom",
        "error_code": error_code, "duration": 1.5,
    }


def _zero(records: list[dict]) -> list[dict]:
    """Alertas zero_return do relatorio de health."""
    return build_health_report(records)["alerts"]


def test_zero_return_detectado() -> None:
    print("== zero-return DETECTADO (gate satisfeito) ==")
    rows = [
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 100),
        _tenant("2026-09-01T02:00:00Z", "sf:jobs", "ok", 50),
        _tenant("2026-09-01T03:00:00Z", "sf:jobs", "ok", 300),
        _tenant("2026-09-01T04:00:00Z", "sf:jobs", "ok", 10),
        _tenant("2026-09-02T01:00:00Z", "sf:jobs", "empty", 0),
    ]
    zr = [a for a in _zero(rows) if a["type"] == "zero_return"]
    check("alerta presente", len(zr) == 1)
    if zr:
        a = zr[0]
        check("fonte correta", a["source"] == "sf:jobs")
        check("ok_history conta os ok>0 anteriores", a["ok_history"] == 4)
        check("last_ok_collected = ultimo ok", a["last_ok_collected"] == 10)
    check(f"gate = {MIN_OK_HISTORY_FOR_ZERO_RETURN}",
          MIN_OK_HISTORY_FOR_ZERO_RETURN == 3)


def test_historico_curto_nao_alerta() -> None:
    print("== historico curto NAO alerta (gate) ==")
    rows = [
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 500),
        _tenant("2026-09-01T02:00:00Z", "sf:jobs", "ok", 5),
        _tenant("2026-09-02T01:00:00Z", "sf:jobs", "empty", 0),
    ]
    check("2 ok>0 + empty NAO alertam", _zero(rows) == [])
    # exatamente no limite: 3 ok>0 -> alerta
    rows3 = rows + [_tenant("2026-09-01T03:00:00Z", "sf:jobs", "ok", 7)]
    check("3 ok>0 + empty alertam (limite do gate)", len(_zero(rows3)) == 1)


def test_empty_consistente_nao_alerta() -> None:
    print("== empty-consistente (anti-caso: bamboohr:sap) NAO alerta ==")
    rows = [
        _tenant("2026-08-31T01:00:00Z", "bamboohr:sap", "empty", 0),
        _tenant("2026-09-01T01:00:00Z", "bamboohr:sap", "empty", 0),
        _tenant("2026-09-05T01:00:00Z", "bamboohr:sap", "empty", 0),
    ]
    check("nunca teve ok>0 -> sem alerta", _zero(rows) == [])


def test_ok_depois_de_empty_nao_alerta() -> None:
    print("== ok depois de empty NAO alerta (ultimo != empty) ==")
    rows = [
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 10),
        _tenant("2026-09-01T02:00:00Z", "sf:jobs", "ok", 20),
        _tenant("2026-09-01T03:00:00Z", "sf:jobs", "ok", 30),
        _tenant("2026-09-02T01:00:00Z", "sf:jobs", "empty", 0),
        _tenant("2026-09-05T01:00:00Z", "sf:jobs", "ok", 40),  # recuperou
    ]
    check("recuperado -> sem alerta", _zero(rows) == [])


def test_ordem_run_id() -> None:
    print("== ordem por run_id (entrada fora de ordem) ==")
    rows = [
        _tenant("2026-09-05T01:00:00Z", "sf:jobs", "empty", 0),  # mais recente
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 100),
        _tenant("2026-09-02T01:00:00Z", "sf:jobs", "ok", 200),
        _tenant("2026-09-03T01:00:00Z", "sf:jobs", "ok", 300),
        _tenant("2026-09-04T01:00:00Z", "sf:jobs", "ok", 400),
    ]
    zr = [a for a in _zero(rows) if a["type"] == "zero_return"]
    check("ordena por run_id e detecta o empty mais recente", len(zr) == 1)
    # inverso: o mais recente (por run_id) e ok -> sem alerta
    rows2 = [
        _tenant("2026-09-05T01:00:00Z", "sf:jobs", "ok", 400),
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 100),
        _tenant("2026-09-02T01:00:00Z", "sf:jobs", "empty", 0),
        _tenant("2026-09-03T01:00:00Z", "sf:jobs", "ok", 300),
        _tenant("2026-09-04T01:00:00Z", "sf:jobs", "ok", 200),
    ]
    check("empty no meio + ultimo ok -> sem alerta", _zero(rows2) == [])


def test_coexistencia_com_outros_alertas() -> None:
    print("== coexistencia: zero-return + recurring_error no mesmo relatorio ==")
    rows = [
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 100),
        _tenant("2026-09-02T01:00:00Z", "sf:jobs", "ok", 200),
        _tenant("2026-09-03T01:00:00Z", "sf:jobs", "ok", 300),
        _tenant("2026-09-04T01:00:00Z", "sf:jobs", "ok", 400),
        _tenant("2026-09-05T01:00:00Z", "sf:jobs", "empty", 0),
        _tenant("2026-09-04T01:00:00Z", "sr:other", "error", 0),
        _tenant("2026-09-05T01:00:00Z", "sr:other", "error", 0),
    ]
    alerts = _zero(rows)
    types = {a["type"] for a in alerts}
    check("zero_return presente", "zero_return" in types)
    check("recurring_error presente", "recurring_error" in types)
    check("1 alerta por fonte", len(alerts) == 2)


def test_malformado_nao_derruba() -> None:
    print("== registro malformado nao derruba a deteccao ==")
    rows = [
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 100),
        _tenant("2026-09-02T01:00:00Z", "sf:jobs", "ok", 200),
        _tenant("2026-09-03T01:00:00Z", "sf:jobs", "ok", 300),
        "not-a-dict",  # malformado
        {"type": "tenant", "source": "sf:jobs"},  # incompleto
        _tenant("2026-09-04T01:00:00Z", "sf:jobs", "ok", 400),
        _tenant("2026-09-05T01:00:00Z", "sf:jobs", "empty", 0),
    ]
    report = build_health_report(rows)
    json.dumps(report, ensure_ascii=False)  # serializavel
    zr = [a for a in report["alerts"] if a["type"] == "zero_return"]
    check("detecta mesmo com malformados", len(zr) == 1)
    check("warnings emitidos", len(report["warnings"]) > 0)


def test_real_data() -> None:
    print("== execucao real (data/collection_metrics.jsonl — LEITURA) ==")
    root = Path(__file__).resolve().parent.parent
    path = root / "data" / "collection_metrics.jsonl"
    if not path.exists():
        print("  SKIP: sem data/collection_metrics.jsonl (CI runner) - bloco real ignorado")
        return
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    report = build_health_report(records)
    json.dumps(report, ensure_ascii=False)
    check("real: relatorio serializavel", True)
    check("real: 0 zero-return no historico (baseline 05/09)",
          not any(a["type"] == "zero_return" for a in report["alerts"]))
    for a in report["alerts"]:
        check(f"real: alerta {a['type']} com schema valido",
              a["type"] in ("drop", "recurring_error", "zero_return") and "source" in a)
    size_before = path.stat().st_size
    check("real: somente leitura (tamanho inalterado)", path.stat().st_size == size_before)


def main() -> int:
    test_zero_return_detectado()
    test_historico_curto_nao_alerta()
    test_empty_consistente_nao_alerta()
    test_ok_depois_de_empty_nao_alerta()
    test_ordem_run_id()
    test_coexistencia_com_outros_alertas()
    test_malformado_nao_derruba()
    test_real_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())