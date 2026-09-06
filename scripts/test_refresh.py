"""Testes do refresh diario (scripts/test_refresh.py) — P2 #17.

Standalone e OFFLINE (tempfile, sem rede, sem escrever em ``data/`` real):
rotacao (arquivos falsos -> archive correto), snapshot de linhas do JSONL +
resumo do run, construcao da mensagem (JSONL fake com anomalia tipo
``smartrecruiters:other`` -> alerta presente; sem anomalia -> sem alerta),
anti-spam/exit codes, config .env, Telegram (url + decisao sem token +
send com mock), comando do subprocesso e dry-run que nao toca ``data/``
(stat antes x depois; bloco real com SKIP quando ``data/`` ausente — padrao CI).

Uso:

    .venv/bin/python scripts/test_refresh.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ (importa refresh_daily)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import refresh_daily as rd  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _tenant(rid: str, source: str, status: str, collected: int,
            error_code: str | None = None) -> dict:
    """Registro tenant minimo (mesmo schema do cli._tenant_record)."""
    return {
        "type": "tenant", "run_id": rid, "timestamp": rid,
        "company": "Acme", "source": source,
        "ats": source.split(":", 1)[0], "status": status,
        "collected": collected,
        "error": None if status not in ("timeout", "error") else "boom",
        "error_code": error_code, "duration": 1.5,
    }


def _run_record(rid: str, total: int, eligible: int, dedup: int = 0) -> dict:
    return {
        "type": "run", "run_id": rid, "timestamp": rid,
        "total_collected": total, "filtered": 60, "dedup_removed": dedup,
        "eligible": eligible,
    }


def test_rotacao() -> None:
    print("== rotacao (backup antes de rodar) ==")
    with tempfile.TemporaryDirectory(prefix="t_rot_") as tmp:
        base = Path(tmp)
        data_dir = base / "data"
        data_dir.mkdir()
        (data_dir / "jobs.json").write_text("J", encoding="utf-8")
        (data_dir / "jobs.csv").write_text("JC", encoding="utf-8")
        (data_dir / "eligible_jobs.json").write_text("E", encoding="utf-8")
        (data_dir / "eligible_jobs.csv").write_text("EC", encoding="utf-8")
        (data_dir / "collection_metrics.jsonl").write_text("M\n", encoding="utf-8")

        archive = rd.rotate(data_dir, data_dir / "archive", "20260905T060000Z")

        check("archive_dir criado em data/archive/<ts>", archive.exists())
        names = sorted(p.name for p in archive.iterdir())
        check("5 arquivos copiados", names == sorted(rd.ROTATE_FILES))
        check("conteudo byte-a-byte",
              (archive / "jobs.json").read_text(encoding="utf-8") == "J"
              and (archive / "collection_metrics.jsonl").read_text(encoding="utf-8") == "M\n")
        check("origem intacta (copia, nao move)",
              (data_dir / "jobs.json").exists() and (data_dir / "collection_metrics.jsonl").exists())

    with tempfile.TemporaryDirectory(prefix="t_rot2_") as tmp:
        base = Path(tmp)
        data_dir = base / "data"
        data_dir.mkdir()
        (data_dir / "jobs.json").write_text("J", encoding="utf-8")  # 4 dos 5
        archive = rd.rotate(data_dir, data_dir / "archive", "ts1")
        check("arquivo ausente e pulado (sem crash)",
              len(list(archive.iterdir())) == 1 and (archive / "jobs.json").exists())


def test_snapshot_e_resumo() -> None:
    print("== snapshot de linhas + resumo do run ==")
    with tempfile.TemporaryDirectory(prefix="t_snap_") as tmp:
        metrics = Path(tmp) / "metrics.jsonl"
        history = [
            _tenant("2026-09-03T06:00:00+00:00", "smartrecruiters:other", "error", 0),
            _tenant("2026-09-04T06:00:00+00:00", "smartrecruiters:other", "error", 0),
        ]
        new = [
            _tenant("2026-09-05T06:00:00+00:00", "successfactors:jobs", "ok", 390),
            _tenant("2026-09-05T06:00:00+00:00", "smartrecruiters:other", "error", 0, "UNKNOWN"),
            _tenant("2026-09-05T06:00:00+00:00", "smartrecruiters:continental", "timeout", 0, "TIMEOUT"),
            _run_record("2026-09-05T06:00:00+00:00", 391, 43, 1),
        ]
        with metrics.open("a", encoding="utf-8") as fh:
            for rec in history + new:
                fh.write(json.dumps(rec) + "\n")

        recs = rd.read_new_records(metrics, len(history))
        check("so as linhas novas sao lidas", len(recs) == len(new))
        summary = rd.summarize_run(recs)
        check("funil do run (bruto/eligible/dedup)",
              summary["total_collected"] == 391 and summary["eligible"] == 43
              and summary["dedup_removed"] == 1)
        check("tenant ok agregado", summary["ok"]["count"] == 1 and summary["ok"]["collected"] == 390)
        check("timeout com error_code", ("smartrecruiters:continental", "TIMEOUT") in summary["timeout"])
        check("error com error_code UNKNOWN", ("smartrecruiters:other", "UNKNOWN") in summary["error"])
        # malformado no meio nao derruba
        with metrics.open("a", encoding="utf-8") as fh:
            fh.write("{not-json}\n")
        recs2 = rd.read_new_records(metrics, len(history))
        check("linha malformada pulada", len(recs2) == len(new))


def test_mensagem_anomalia_presente() -> None:
    print("== mensagem com anomalia (smartrecruiters:other) ==")
    records = [
        _tenant("2026-09-03T06:00:00+00:00", "smartrecruiters:other", "error", 0),
        _tenant("2026-09-04T06:00:00+00:00", "smartrecruiters:other", "error", 0),
        _tenant("2026-09-05T06:00:00+00:00", "smartrecruiters:other", "error", 0),
        _tenant("2026-09-01T06:00:00+00:00", "successfactors:jobs", "ok", 100),
        _tenant("2026-09-02T06:00:00+00:00", "successfactors:jobs", "ok", 50),
        _tenant("2026-09-03T06:00:00+00:00", "successfactors:jobs", "ok", 300),
        _tenant("2026-09-05T06:00:00+00:00", "successfactors:jobs", "ok", 10),  # queda brusca
    ]
    summary = rd.summarize_run([_run_record("r1", 391, 43, 2),
                                _tenant("2026-09-05T06:00:00+00:00", "successfactors:jobs", "ok", 10),
                                _tenant("2026-09-05T06:00:00+00:00", "smartrecruiters:other", "error", 0, "UNKNOWN"),
                                _tenant("2026-09-05T06:00:00+00:00", "smartrecruiters:continental", "timeout", 0, "TIMEOUT")])
    from internship_finder.health import build_health_report
    report = build_health_report(records)
    message = rd.build_message(summary, report["alerts"], exit_code=0)
    check("alerta gerado (health detecta)", len(report["alerts"]) == 2)
    check("mensagem nao e None com anomalia", message is not None)
    check("erro recorrente na mensagem",
          "smartrecruiters:other" in (message or "") and "erro recorrente" in (message or ""))
    check("queda brusca na mensagem",
          "successfactors:jobs" in (message or "") and "queda brusca" in (message or ""))
    check("funil e falhas na mensagem",
          "391" in (message or "") and "TIMEOUT" in (message or ""))
    check("alertas deduplicados por fonte",
          (message or "").count("smartrecruiters:other") == 1)


def test_mensagem_zero_return() -> None:
    print("== mensagem com zero-return (P2 #10) ==")
    summary = rd.summarize_run([_run_record("r1", 391, 43, 2)])
    alerts = [
        {"type": "zero_return", "source": "successfactors:jobs",
         "last_status": "empty", "ok_history": 4, "last_ok_collected": 10},
    ]
    message = rd.build_message(summary, alerts, exit_code=0)
    check("mensagem nao e None", message is not None)
    check("formato zero-return no texto",
          "voltou a zero (empty) após 4 runs com vagas (último ok: 10)" in (message or ""))
    # erro recorrente segue com o formato antigo (sem regressao)
    message2 = rd.build_message(summary, [{"type": "recurring_error",
                                           "source": "sr:x", "runs_seq": 2}], exit_code=0)
    check("formato recurring_error preservado",
          "sr:x — erro recorrente (2 runs consecutivos)" in (message2 or ""))


def test_mensagem_sem_anomalia() -> None:
    print("== sem anomalia -> sem alerta (anti-spam) ==")
    summary = rd.summarize_run([_run_record("r1", 400, 50)])
    check("exit 0 + sem alertas -> None", rd.build_message(summary, [], 0) is None)
    check("+ --always-notify -> mensagem (digest)",
          rd.build_message(summary, [], 0, always_notify=True) is not None)
    check("exit 2 (parcial) -> mensagem mesmo sem alerta",
          rd.build_message(summary, [], 2) is not None
          and "parcial" in rd.build_message(summary, [], 2))
    check("exit 1 (nada coletado) -> mensagem",
          "Nenhuma" in (rd.build_message(summary, [], 1) or ""))
    check("exit 124 (teto do subprocesso) -> mensagem",
          "124" in (rd.build_message(summary, [], 124) or ""))


def test_env_config() -> None:
    print("== config .env ==")
    with tempfile.TemporaryDirectory(prefix="t_env_") as tmp:
        env = Path(tmp) / ".env"
        env.write_text(
            "# comentario\n"
            "TELEGRAM_BOT_TOKEN=\"123:abc\"\n"
            "TELEGRAM_CHAT_ID=695791270\n"
            "LINHA_SEM_IGUAL\n", encoding="utf-8")
        cfg = rd.load_env_config(env)
        check("token lido (aspas removidas)", cfg.get("TELEGRAM_BOT_TOKEN") == "123:abc")
        check("chat id lido", cfg.get("TELEGRAM_CHAT_ID") == "695791270")
        check("linha sem '=' ignorada", "LINHA_SEM_IGUAL" not in cfg)
    check("arquivo ausente -> {} sem crash", rd.load_env_config("/tmp/nao_existe_env_xyz") == {})


def test_telegram() -> None:
    print("== telegram (decisao sem token + send mockado) ==")
    url = rd.telegram_url("TOK")
    check("url sendMessage correta", url == "https://api.telegram.org/botTOK/sendMessage")

    # sem credenciais -> aviso, sem crash, sent=False
    result = rd.notify_or_log({}, "msg", dry_run=False)
    check("sem token -> nao envia, nao crasha",
          result["sent"] is False and result.get("reason") == "no_credentials")

    # dry_run -> imprime e nao envia
    result = rd.notify_or_log({"TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "C"}, "msg", dry_run=True)
    check("dry-run -> sem envio", result.get("dry_run") is True and result["sent"] is False)

    # send com mock: chama a global send_telegram com (token, chat, texto)
    calls: list[tuple] = []

    def fake_send(token: str, chat_id: str, text: str, timeout: float = 30.0) -> dict:
        calls.append((token, chat_id, text))
        return {"ok": True, "result": {"message_id": 1}}

    original = rd.send_telegram
    rd.send_telegram = fake_send
    try:
        result = rd.notify_or_log({"TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "C"}, "msg-1", dry_run=False)
        check("send chamado com credenciais", len(calls) == 1 and calls[0][0] == "T" and calls[0][1] == "C")
        check("send recebe a mensagem", calls and calls[0][2] == "msg-1")
        check("ok:true propaga para o retorno", result["sent"] is True and result["response"]["ok"] is True)
    finally:
        rd.send_telegram = original


def test_comando_subprocesso() -> None:
    print("== comando do subprocesso de coleta ==")
    cmd = rd.collection_command(60)
    check("usa -m internship_finder.cli", cmd[:3] == [sys.executable, "-m", "internship_finder.cli"])
    check("--registry + --timeout 60", cmd[3:] == ["--registry", "--timeout", "60"])


def _data_snapshot(data_dir: Path) -> dict:
    snap = {}
    if not data_dir.exists():
        return snap
    for p in sorted(data_dir.rglob("*")):
        if p.is_file():
            st = p.stat()
            snap[str(p.relative_to(data_dir))] = (st.st_mtime_ns, st.st_size)
    return snap


def test_dry_run_nao_toca_data() -> None:
    print("== dry-run nao escreve em data/ (stat antes == depois) ==")
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    if not data_dir.exists():
        print("  SKIP: sem data/ (CI runner) - bloco real ignorado")
        return
    before = _data_snapshot(data_dir)
    # Nota (CI): o test_hardening, que roda antes no array, pode criar
    # data/collection_metrics.jsonl no cwd do checkout (default de metrics
    # relativo ao cwd). O invariante NAO e "quantos arquivos data/ tem", e sim
    # "o dry-run nao altera nenhum" — antes == depois, qualquer que seja o
    # conteudo inicial.
    print(f"  (data/ com {len(before)} arquivos; dry-run nao pode alterar nenhum)")
    rc = rd.main(["--dry-run"])
    check("dry-run exit 0", rc == 0)
    after = _data_snapshot(data_dir)
    check("data/ intocada (mtime+size iguais)", before == after)


def main() -> int:
    test_rotacao()
    test_snapshot_e_resumo()
    test_mensagem_anomalia_presente()
    test_mensagem_zero_return()
    test_mensagem_sem_anomalia()
    test_env_config()
    test_telegram()
    test_comando_subprocesso()
    test_dry_run_nao_toca_data()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())