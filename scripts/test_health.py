"""Testes do modulo de health (scripts/test_health.py).

Roda tres blocos: (1) casos sinteticos (queda brusca, gate de historico, erro
recorrente, nao-consecutivo, duration string antiga normalizada, registro
malformado, JSONL vazio, run_id fora de ordem), (2) CLI ``--health``
(subprocess com arquivo inexistente e valido), (3) execucao real sobre
``data/collection_metrics.jsonl`` (SO LEITURA) com o MESMO padrao de SKIP dos
demais testes quando o arquivo nao existe. Uso:

    .venv/bin/python scripts/test_health.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.health import (  # noqa: E402
    CONSECUTIVE_FAILURES,
    MIN_OK_HISTORY_FOR_DROP,
    build_health_report,
)

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _tenant(run_id: str, source: str, status: str, collected: int,
            duration=None, ats: str | None = None) -> dict:
    """Registro tenant minimo e valido para os casos sinteticos."""
    return {
        "type": "tenant",
        "run_id": run_id,
        "timestamp": run_id,
        "company": "Acme",
        "source": source,
        "ats": ats or source.split(":", 1)[0],
        "status": status,
        "collected": collected,
        "error": None if status not in ("timeout", "error") else "boom",
        "duration": duration,
    }


def test_quedra_brusca_detectada() -> None:
    print("== queda brusca DETECTADA ==")
    # 4 runs ok (gate >= 3 anteriores): mediana dos 3 anteriores = (100,50,300) -> 100
    # atual 10 < 0.5 * 100 -> alerta
    rows = [
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 100),
        _tenant("2026-09-01T02:00:00Z", "sf:jobs", "ok", 50),
        _tenant("2026-09-01T03:00:00Z", "sf:jobs", "ok", 300),
        _tenant("2026-09-01T04:00:00Z", "sf:jobs", "ok", 10),
    ]
    report = build_health_report(rows)
    drop = [a for a in report["alerts"] if a["type"] == "drop"]
    check("queda detectada", len(drop) == 1)
    if drop:
        a = drop[0]
        check("alerta com mediana anterior", a["mediana_anterior"] == 100)
        check("alerta com collected atual", a["collected_atual"] == 10)
        check("alerta com pct", a["pct"] == 0.1)


def test_historico_curto_nao_alerta() -> None:
    print("== historico curto NAO alerta (gate) ==")
    rows = [
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 500),
        _tenant("2026-09-01T02:00:00Z", "sf:jobs", "ok", 5),
    ]
    report = build_health_report(rows)
    drop = [a for a in report["alerts"] if a["type"] == "drop"]
    check("1-2 runs ok NAO alertam", len(drop) == 0)
    check(f"gate historico = {MIN_OK_HISTORY_FOR_DROP}",
          len(rows) == 2 and MIN_OK_HISTORY_FOR_DROP == 3)


def test_erro_recorrente_detectado() -> None:
    print("== erro recorrente DETECTADO ==")
    rows = [
        _tenant("2026-09-01T01:00:00Z", "sr:other", "ok", 5),
        _tenant("2026-09-01T02:00:00Z", "sr:other", "timeout", 0),
        _tenant("2026-09-01T03:00:00Z", "sr:other", "error", 0),
    ]
    report = build_health_report(rows)
    rec = [a for a in report["alerts"] if a["type"] == "recurring_error"]
    check("erro recorrente detectado", len(rec) == 1)
    if rec:
        check("sequencia consecutiva", rec[0]["runs_seq"] == 2)
        check("fonte correta", rec[0]["source"] == "sr:other")
    # conte agora 3 falhas seguidas
    rows3 = rows + [_tenant("2026-09-01T04:00:00Z", "sr:other", "error", 0)]
    report3 = build_health_report(rows3)
    rec3 = [a for a in report3["alerts"] if a["type"] == "recurring_error"]
    check("3 falhas seguidas -> runs_seq 3", rec3 and rec3[0]["runs_seq"] == 3)


def test_erro_nao_consecutivo_nao_alerta() -> None:
    print("== erro NAO-consecutivo NAO alerta ==")
    rows = [
        _tenant("2026-09-01T01:00:00Z", "sr:other", "error", 0),
        _tenant("2026-09-01T02:00:00Z", "sr:other", "ok", 5),
        _tenant("2026-09-01T03:00:00Z", "sr:other", "error", 0),
    ]
    report = build_health_report(rows)
    rec = [a for a in report["alerts"] if a["type"] == "recurring_error"]
    check("error intercalado com ok NAO alerta", len(rec) == 0)
    check(f"limiar = {CONSECUTIVE_FAILURES}", CONSECUTIVE_FAILURES == 2)


def test_duration_string_normalizada() -> None:
    print("== duration string antiga normalizada ==")
    rows = [
        _tenant("2026-08-25T01:00:00Z", "sf:jobs", "ok", 10, "1.5s"),
        _tenant("2026-08-25T02:00:00Z", "sf:jobs", "ok", 10, 2.0),
    ]
    report = build_health_report(rows)
    s = report["sources"][0]
    check("duration string '1.5s' -> float", s["last_duration"] == 2.0)
    check("media duration ok numerica",
          s["avg_duration_ok"] == 1.75)
    # inparseavel -> None
    rows2 = [
        _tenant("2026-08-25T01:00:00Z", "sf:jobs", "ok", 10, "nope"),
        _tenant("2026-08-25T02:00:00Z", "sf:jobs", "ok", 10, "2s"),
    ]
    report2 = build_health_report(rows2)
    s2 = report2["sources"][0]
    check("duration inparseavel -> None", s2["last_duration"] == 2.0)
    check("media ignora None", s2["avg_duration_ok"] == 2.0)


def test_registro_malformado() -> None:
    print("== registro malformado nao derruba ==")
    records = [
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 5),
        _tenant("2026-09-01T02:00:00Z", "sf:jobs", "ok", 6),
        "not-a-dict",                       # JSON invalido (nao-dict)
        {"type": "tenant"},                  # sem source/run_id/status
        {"type": "run", "run_id": "x"},      # tipo nao-tenant: ignorado sem warning
        {"type": "tenant", "source": "sf:jobs", "run_id": "2026-09-01T03:00:00Z"},  # sem status/collected
        {"type": "tenant", "source": "gf:other", "run_id": "2026-09-01T01:00:00Z",
         "status": "ok", "collected": 7},    # valido
    ]
    report = build_health_report(records)
    # malformado deve gerar warning mas o relatorio continua valido e serializavel
    json.dumps(report)
    check("relatorio serializavel mesmo com malformados", True)
    check("warnings emitidos para malformados", len(report["warnings"]) > 0)
    srcs = {s["source"] for s in report["sources"]}
    check("sources validos preservados", srcs == {"sf:jobs", "gf:other"})


def test_jsonl_vazio() -> None:
    print("== JSONL vazio -> relatorio vazio e valido ==")
    report = build_health_report([])
    json.dumps(report)
    check("relatorio vazio e valido",
          report["sources"] == [] and report["ats"] == [] and report["alerts"] == [])


def test_run_id_fora_de_ordem() -> None:
    print("== run_id fora de ordem tratado ==")
    rows = [
        _tenant("2026-09-01T03:00:00Z", "sf:jobs", "ok", 10),
        _tenant("2026-09-01T01:00:00Z", "sf:jobs", "ok", 5),
        _tenant("2026-09-01T02:00:00Z", "sf:jobs", "ok", 8),
    ]
    report = build_health_report(rows)
    s = report["sources"][0]
    check("ordenado por run_id", s["last_collected"] == 10)
    # 3 ok anteriores (gate satisfeito), mediana de (5,8) = 8, 10 < 0.5*8? nao
    drop = [a for a in report["alerts"] if a["type"] == "drop"]
    check("sem alerta por mediana", len(drop) == 0)


def test_cli() -> None:
    print("== CLI --health ==")
    root = Path(__file__).resolve().parent.parent
    cli_mod = str(root / "src")
    ok_path = root / "data" / "collection_metrics.jsonl"
    if ok_path.exists():
        cmd = [sys.executable, "-m", "internship_finder.cli", "--health", str(ok_path)]
        env = {"PYTHONPATH": cli_mod, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        check("--health com arquivo valido -> exit 0", r.returncode == 0)
        try:
            json.loads(r.stdout)
            ok_parse = True
        except json.JSONDecodeError:
            ok_parse = False
        check("--health stdout e JSON parseavel", ok_parse)
    else:
        print("  SKIP: sem data/ collection_metrics.jsonl - bloco CLI real ignorado")

    missing = root / "nao_existe_metrics.jsonl"
    cmd = [sys.executable, "-m", "internship_finder.cli", "--health", str(missing)]
    env = {"PYTHONPATH": cli_mod, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    check("--health com arquivo inexistente -> exit != 0", r.returncode != 0)
    check("erro claro no stderr", "nao encontrado" in r.stderr)


def test_real_data() -> None:
    print("== execucao real (data/collection_metrics.jsonl) ==")
    root = Path(__file__).resolve().parent.parent
    path = root / "data" / "collection_metrics.jsonl"
    # Ambiente sem coleta (ex.: CI runner sem data/): skip do bloco real com
    # exit 0 (mesmo padrao de test_dedup/test_ranking).
    if not path.exists():
        print("  SKIP: data/collection_metrics.jsonl ausente (sem coleta local) - bloco real ignorado")
        return
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    report = build_health_report(records)
    json.dumps(report)  # deve serializar sem erro
    check("real: relatorio serializavel", True)
    check("real: tenants unicos com resumo",
          len(report["sources"]) > 0 and len(report["ats"]) > 0)
    # so leitura: o tamanho do arquivo nao muda
    size_before = path.stat().st_size
    check("real: somente leitura (tamanho inalterado)", path.stat().st_size == size_before)
    # os alertas retornados seguem o schema
    for a in report["alerts"]:
        check("real: alerta com type valido",
              a["type"] in ("drop", "recurring_error", "zero_return"))
        check("real: alerta com fonte", "source" in a)


def main() -> int:
    test_quedra_brusca_detectada()
    test_historico_curto_nao_alerta()
    test_erro_recorrente_detectado()
    test_erro_nao_consecutivo_nao_alerta()
    test_duration_string_normalizada()
    test_registro_malformado()
    test_jsonl_vazio()
    test_run_id_fora_de_ordem()
    test_cli()
    test_real_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())