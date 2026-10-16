#!/usr/bin/env python3
"""F41 — Testes do event log de candidaturas (append-only) + ingest + view.

100% OFFLINE (nenhum socket/HTTP). Fixtures VERBATIM; tudo em tempdir — NUNCA
toca ``data/`` de produção. Blocos standalone ([OK]/[FAIL], exit 0/1):

A. parse PURO: mapeamento de event_type (applied/rejected/offer/note, PT/EN/DE),
   empresa derivada do eligible, event_type explícito vence o texto, schema
   exato (6 chaves), job_id desconhecido ACEITO (unmatched), mensagem sem
   vaga SKIPADA, determinismo.
B. log append-only + idempotência: replay do mesmo dump = no-op; o arquivo
   NUNCA é reescrito (prefixo do 1º ingest preservado byte a byte).
C. rebuild determinístico: 2 rebuilds = mesmo estado; ts embaralhado -> mesmo
   estado; 'note' não altera status.
D. tracker vira VIEW: ingest -> job_status derivado do log; 2º rebuild = 0
   mudanças; comandos existentes (mark/applied/note/list/show) vivos; CLI
   grava desfecho no log; log ao lado do --db.
E. ZERO rede: sockets bloqueados, ingest+rebuild+parse passam; nenhum import
   de rede no application_log.py.

Uso: .venv/bin/python scripts/test_f41.py
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/

import application_log as alog  # noqa: E402
import personal_tracker as pt  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# --------------------------------------------------------------- fixtures

JOB_BMW = "BMW AG|successfactors:jobs:111"
JOB_SAP = "SAP|successfactors:jobs:222"
JOB_STIHL = "STIHL|successfactors:jobs:333"

ELIGIBLE = [
    {"id": JOB_BMW, "title": "Praktikant Einkauf", "company": "BMW AG"},
    {"id": JOB_SAP, "title": "Working Student Analytics", "company": "SAP"},
    {"id": JOB_STIHL, "title": "Praktikum Supply Chain", "company": "STIHL"},
]

# Dump VERBATIM de mensagens (schema do application_log.py) — formatos variados
# PT/EN/DE, datas fora de ordem, id desconhecido e uma mensagem sem vaga.
DUMP = {
    "dump_version": 1,
    "generated_at": "2026-10-15T23:00:00Z",
    "messages": [
        {"message_id": "tg:501", "date": "2026-10-15T09:00:00Z",
         "job_id": JOB_BMW, "text": "apliquei hoje, enviei o CV pelo portal"},
        {"message_id": "tg:502", "date": "2026-10-14T18:30:00Z",
         "text": "SAP — unfortunately not selected, Absage per email"},
        {"message_id": "tg:503", "date": "2026-10-16T07:15:00Z",
         "job_id": JOB_STIHL, "text": "Zusage! they offered me the internship"},
        {"message_id": "tg:504", "date": "2026-10-15T12:00:00Z",
         "job_id": JOB_BMW, "event_type": "note",
         "text": "verificar prazo de visto antes de responder"},
        {"message_id": "tg:505", "date": "2026-10-15T12:05:00Z",
         "job_id": "GhostGmbH|smartrecruiters:GhostGmbH:999",
         "company": "GhostGmbH", "text": "interview scheduled for next week"},
        {"message_id": "tg:506", "date": "2026-10-15T12:10:00Z",
         "text": "obrigado!"},
    ],
}

SIX_KEYS = {"message_id", "ts", "job_id", "company", "event_type", "source"}


def write_dump(tmp: Path, dump: dict, name: str = "dump.json") -> Path:
    p = tmp / name
    p.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    return p


def fresh_env() -> tuple[Path, Path, Path, Path]:
    tmp = Path(tempfile.mkdtemp(prefix="f41_test_"))
    db = tmp / "personal" / "jobs_personal.db"
    ranking = tmp / "eligible_jobs.json"
    log = tmp / "personal" / "application_events.jsonl"
    ranking.write_text(json.dumps(ELIGIBLE, ensure_ascii=False), encoding="utf-8")
    return tmp, db, ranking, log


def run_cli(db: Path, ranking: Path, log: Path, *argv: str) -> int:
    base = ["--db", str(db), "--ranking", str(ranking), "--log", str(log)]
    return pt.main([*base, *argv])


# ------------------------------------------------------------------ bloco A


def test_parse_pure() -> None:
    section("A: parse PURO (offline)")
    events = alog.parse_mensagens(DUMP["messages"], ELIGIBLE)
    by_mid = {e["message_id"]: e for e in events}
    check("A1. 5 eventos (mensagem sem vaga é SKIPADA)", len(events) == 5,
          f"n={len(events)}")
    check("A2. applied mapeado do texto PT",
          by_mid["tg:501"]["event_type"] == "applied")
    check("A3. rejected mapeado do EN (Absage/unfortunately)",
          by_mid["tg:502"]["event_type"] == "rejected")
    check("A4. offer mapeado do DE (Zusage)", by_mid["tg:503"]["event_type"] == "offer")
    check("A5. event_type explícito vence o texto ('note')",
          by_mid["tg:504"]["event_type"] == "note")
    check("A6. interview no id desconhecido",
          by_mid["tg:505"]["event_type"] == "interview")
    check("A7. empresa derivada do eligible",
          by_mid["tg:501"]["company"] == "BMW AG"
          and by_mid["tg:502"]["company"] == "SAP")
    check("A8. job_id desconhecido ACEITO (unmatched) com empresa da mensagem",
          by_mid["tg:505"]["job_id"] == "GhostGmbH|smartrecruiters:GhostGmbH:999"
          and by_mid["tg:505"]["company"] == "GhostGmbH")
    check("A9. empresa por nome casando 1 job do eligible (SAP no texto)",
          by_mid["tg:502"]["job_id"] == JOB_SAP)
    check("A10. schema do evento = exatamente as 6 chaves F41",
          all(set(e.keys()) == SIX_KEYS for e in events))
    check("A11. source default = telegram",
          all(e["source"] == "telegram" for e in events))
    rep = alog.parse_report(DUMP["messages"], ELIGIBLE)
    check("A12. sumário: matched=4 unmatched=1 skipped=1",
          (rep["matched"], rep["unmatched"], rep["skipped"]) == (4, 1, 1),
          f"m={rep['matched']} u={rep['unmatched']} s={rep['skipped']}")
    check("A13. pura/determinística (2 chamadas idênticas)",
          alog.parse_mensagens(DUMP["messages"], ELIGIBLE) == events)
    check("A14. pretty-id conhecido no texto (sem campo job_id)",
          alog.parse_mensagens(
              [{"message_id": "x", "date": "2026-10-15T00:00:00Z",
                "text": f"apliquei: {JOB_STIHL}"}], ELIGIBLE
          )[0]["job_id"] == JOB_STIHL)


# ------------------------------------------------------------------ bloco B


def test_log_append_only() -> None:
    section("B: log append-only + idempotência")
    tmp, _db, _ranking, log = fresh_env()
    r1 = alog.ingest_dump(DUMP, eligible=ELIGIBLE, log_path=log)
    check("B1. 1º ingest appenda 5 eventos", r1["appended"] == 5
          and r1["skipped_duplicates"] == 0, f"appended={r1['appended']}")
    raw1 = log.read_bytes()
    lines1 = log.read_text(encoding="utf-8").splitlines()
    check("B2. log tem 5 linhas JSON", len(lines1) == 5)
    check("B3. toda linha é um objeto JSON com as 6 chaves",
          all(set(json.loads(ln).keys()) == SIX_KEYS for ln in lines1))
    # replay do MESMO dump = no-op (idempotência por message_id)
    r2 = alog.ingest_dump(DUMP, eligible=ELIGIBLE, log_path=log)
    raw2 = log.read_bytes()
    check("B4. replay = no-op (0 appendados, 5 duplicados)",
          r2["appended"] == 0 and r2["skipped_duplicates"] == 5,
          f"appended={r2['appended']} dup={r2['skipped_duplicates']}")
    check("B5. arquivo byte a byte idêntico no replay", raw1 == raw2)
    check("B6. append-only: 1º ingest é PREFIXO do estado atual",
          raw2.startswith(raw1) and len(raw2) == len(raw1))
    # novo evento (id novo) só APENDA
    extra = {"messages": [{"message_id": "tg:507",
                           "date": "2026-10-16T08:00:00Z",
                           "job_id": JOB_BMW,
                           "text": "interview marcada para 22/10"}]}
    r3 = alog.ingest_dump(extra, eligible=ELIGIBLE, log_path=log)
    raw3 = log.read_bytes()
    check("B7. evento novo APPENDA (6 linhas) e preserva o prefixo",
          r3["appended"] == 1 and len(raw3.splitlines()) == 6
          and raw3.startswith(raw1))
    check("B8. event_type do evento novo = interview",
          alog.read_events(log)[-1]["event_type"] == "interview")


# ------------------------------------------------------------------ bloco C


def test_rebuild_determinism() -> None:
    section("C: rebuild determinístico (view)")
    events = alog.parse_mensagens(DUMP["messages"], ELIGIBLE)
    s1 = alog.rebuild_status(events)
    s2 = alog.rebuild_status(events)
    check("C1. 2 rebuilds = mesmo estado", s1 == s2)
    check("C2. BMW = applied (note posterior NÃO muda status)",
          s1[JOB_BMW]["status"] == "applied"
          and s1[JOB_BMW]["last_event_type"] == "note",
          f"{s1[JOB_BMW]['status']}/{s1[JOB_BMW]['last_event_type']}")
    check("C3. SAP = rejected", s1[JOB_SAP]["status"] == "rejected")
    check("C4. STIHL = offer", s1[JOB_STIHL]["status"] == "offer")
    check("C5. Ghost = interview (unmatched ainda entra na view)",
          s1["GhostGmbH|smartrecruiters:GhostGmbH:999"]["status"] == "interview")
    # ts embaralhado -> MESMO estado final
    shuffled = list(reversed(events))
    check("C6. ts/ordem embaralhada -> mesmo estado",
          alog.rebuild_status(shuffled) == s1)
    # note isolado não define status
    only_note = alog.rebuild_status([{
        "message_id": "n", "ts": "2026-10-15T00:00:00Z", "job_id": "X|s:1",
        "company": "", "event_type": "note", "source": "cli"}])
    check("C7. evento 'note' isolado não define status (status=None)",
          only_note["X|s:1"]["status"] is None)


# ------------------------------------------------------------------ bloco D


def test_tracker_view_and_cli() -> None:
    section("D: tracker vira VIEW + comandos vivos")
    tmp, db, ranking, log = fresh_env()
    dump_path = write_dump(tmp, DUMP)
    rc = run_cli(db, ranking, log, "ingest", "--dump", str(dump_path))
    check("D1. ingest CLI rc=0", rc == 0)
    conn = pt.connect(db)
    st = {r["job_id"]: r["status"]
          for r in conn.execute("SELECT job_id, status FROM job_status")}
    check("D2. view reflete o log (BMW applied / SAP rejected / STIHL offer)",
          st.get(JOB_BMW) == "applied" and st.get(JOB_SAP) == "rejected"
          and st.get(JOB_STIHL) == "offer", f"{st}")
    check("D3. id desconhecido também entra na view (interview)",
          st.get("GhostGmbH|smartrecruiters:GhostGmbH:999") == "interview")
    # 2º rebuild = 0 mudanças (determinismo no banco)
    r = pt.rebuild_view(conn, log)
    check("D4. 2º rebuild = 0 inseridas / 0 atualizadas",
          r["inserted"] == 0 and r["changed"] == 0, f"{r}")
    conn.close()
    # replay do dump via CLI -> no-op (idempotente) e view inalterada
    raw_before = log.read_bytes()
    run_cli(db, ranking, log, "ingest", "--dump", str(dump_path))
    check("D5. replay via CLI não altera o log", log.read_bytes() == raw_before)
    # comandos existentes vivos + espelhamento no log
    check("D6. mark interesting (comando vivo)",
          run_cli(db, ranking, log, "mark", JOB_BMW, "--status", "interesting",
                  "--priority", "high") == 0)
    check("D7. applied (comando vivo) grava desfecho no log",
          run_cli(db, ranking, log, "applied", JOB_SAP, "--date", "2026-10-10") == 0)
    log_sap = [e for e in alog.read_events(log)
               if e["job_id"] == JOB_SAP and e["source"] == "cli"]
    check("D8. evento cli:applied presente (source=cli, ts=data real)",
          any(e["event_type"] == "applied" and e["ts"].startswith("2026-10-10")
              for e in log_sap), f"{log_sap}")
    check("D9. list rc=0", run_cli(db, ranking, log, "list") == 0)
    check("D10. show rc=0", run_cli(db, ranking, log, "show", JOB_BMW) == 0)
    check("D11. note (comando vivo) + weekly/funnel/metrics rc=0",
          run_cli(db, ranking, log, "note", JOB_STIHL, "--text", "x") == 0
          and run_cli(db, ranking, log, "weekly") == 0
          and run_cli(db, ranking, log, "funnel") == 0
          and run_cli(db, ranking, log, "metrics") == 0)
    # log ao lado do --db quando --log não é passado
    import argparse
    ns = argparse.Namespace(db=str(db), log=None)
    check("D12. log default = ao lado do --db",
          pt.resolve_log_path(ns) == Path(db).parent / "application_events.jsonl")


# ------------------------------------------------------------------ bloco E


def test_zero_network() -> None:
    section("E: ZERO rede")
    import ast

    src = Path(alog.__file__).read_text(encoding="utf-8")
    # 'telegram' é VALOR legítimo do campo ``source`` (o dump é exportado do
    # Telegram) — o que não pode existir é CLIENTE/ENDPOINT de rede. Checamos
    # os IMPORTS (AST, não substring) e URLs de API.
    imported: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    banned_mods = {"requests", "urllib", "http", "socket", "smtplib",
                   "telegram", "telebot", "aiohttp", "httpx", "ftplib"}
    check("E1. nenhum import de cliente de rede no application_log.py",
          not (imported & banned_mods), f"imports={sorted(imported)}")
    check("E1b. nenhuma URL de API / esquema http no application_log.py",
          "api.telegram.org" not in src and "http://" not in src
          and "https://" not in src)

    blocked: list[str] = []

    def _fail_connect(self, address):  # noqa: ANN001
        blocked.append(str(address))
        raise OSError("socket externo bloqueado pela suíte F41")

    orig_connect = socket.socket.connect
    socket.socket.connect = _fail_connect  # type: ignore[method-assign]
    try:
        tmp, db, ranking, log = fresh_env()
        dump_path = write_dump(tmp, DUMP)
        rc = run_cli(db, ranking, log, "ingest", "--dump", str(dump_path))
        check("E2. ingest+rebuild com sockets bloqueados rc=0", rc == 0)
        check("E3. nenhum socket externo tentado", blocked == [],
              f"blocked={blocked[:3]}")
    finally:
        socket.socket.connect = orig_connect  # type: ignore[method-assign]


def main() -> int:
    test_parse_pure()
    test_log_append_only()
    test_rebuild_determinism()
    test_tracker_view_and_cli()
    test_zero_network()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print(f"TUDO OK ({CHECKS} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
