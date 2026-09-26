#!/usr/bin/env python3
"""Testes do Personal Tracker (Fase 8) — scripts/test_personal_tracker.py.

Cobre os 20 itens do §25 da spec em blocos standalone ([OK]/[FAIL], exit
0/1), com fixtures em tempdir — NUNCA toca ``data/`` real:

1. marcar Interesting; 2. Review; 3. Applied; 4. application date;
5. nota; 6. prioridade; 7. Interview; 8. Offer; 9. Rejected;
10. vaga desaparecer do ATS; 11. vaga aplicada desaparecer do ranking;
12. shortlist; 13. comparação (Compare Fase 7 segue presente no HTML);
14. deadline reminder; 15. Telegram (personal_sections);
16. exportação; 17. mobile/desktop (hint em <details>); 18. desktop;
19. persistência após novo refresh (sync idempotente); 20. privacidade.

Uso:
    .venv/bin/python scripts/test_personal_tracker.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import personal_tracker as pt  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def fresh_env() -> tuple[Path, Path, Path]:
    """tmpdir com banco pessoal + ranking fake + jobs.db fake."""
    tmp = Path(tempfile.mkdtemp(prefix="pt_test_"))
    db = tmp / "personal" / "jobs_personal.db"
    ranking = tmp / "eligible_jobs.json"
    jobs_db = tmp / "jobs.db"
    return tmp, db, ranking, jobs_db  # type: ignore[return-value]


def seed_jobs_db(jobs_db: Path, rows: list[tuple[str, int]]) -> None:
    conn = sqlite3.connect(str(jobs_db))
    conn.execute(
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, active INTEGER NOT NULL)")
    conn.executemany("INSERT INTO jobs (id, active) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def seed_ranking(ranking: Path, jobs: list[dict]) -> None:
    ranking.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")


def run_cli(db: Path, ranking: Path, jobs_db: Path, *argv: str) -> int:
    base = ["--db", str(db), "--ranking", str(ranking),
            "--jobs-db", str(jobs_db)]
    return pt.main([*base, *argv])


JOB1 = "BMW AG|successfactors:jobs:111"
JOB2 = "SAP|successfactors:jobs:222"
JOB3 = "STIHL|successfactors:jobs:333"


def test_status_flow() -> None:
    print("== bloco 1-9: fluxo de status completo ==")
    tmp, db, ranking, jobs_db = fresh_env()
    seed_jobs_db(jobs_db, [(JOB1, 1), (JOB2, 1), (JOB3, 0)])
    seed_ranking(ranking, [
        {"id": JOB1, "title": "Praktikant Einkauf", "company": "BMW AG",
         "location": "München", "score": 14.0, "country_iso": "de"},
        {"id": JOB2, "title": "Working Student", "company": "SAP",
         "location": "Walldorf", "score": 9.5, "country_iso": "de"},
    ])
    rc = run_cli(db, ranking, jobs_db, "mark", JOB1, "--status", "interesting",
                 "--priority", "high", "--note", "contato procurement",
                 "--effort", "medium", "--effort-flags", "cv_adaptation;cover_letter",
                 "--next-action", "Apply")
    check("1/6: marcar interesting (+nota+prioridade+effort)", rc == 0)
    conn = pt.connect(db)
    st = conn.execute("SELECT * FROM job_status WHERE job_id=?", (JOB1,)).fetchone()
    check("status interesting persistido", st is not None and st["status"] == "interesting")
    check("prioridade high", st is not None and st["priority"] == "high")
    check("nota salva", st is not None and st["note"] == "contato procurement")
    check("effort medium + flags", st is not None and st["effort"] == "medium"
          and st["effort_flags"] == "cv_adaptation;cover_letter")
    check("evento marked registrado",
          pt.has_event(conn, JOB1, "marked"))
    check("evento priority registrado", pt.has_event(conn, JOB1, "priority"))
    check("evento note registrado", pt.has_event(conn, JOB1, "note"))
    conn.close()
    # 2. review
    rc = run_cli(db, ranking, jobs_db, "mark", JOB1, "--status", "review")
    conn = pt.connect(db)
    check("2: alterar para review", rc == 0 and conn.execute(
        "SELECT status FROM job_status WHERE job_id=?", (JOB1,)
    ).fetchone()["status"] == "review")
    check("evento status_changed interesting->review",
          conn.execute("SELECT detail FROM job_events WHERE job_id=? AND "
                       "kind='status_changed'", (JOB1,)).fetchone()["detail"]
          == "interesting -> review")
    conn.close()
    # 3/4. applied + application date
    rc = run_cli(db, ranking, jobs_db, "applied", JOB1, "--date", "2026-09-20",
                 "--contact", "LinkedIn")
    conn = pt.connect(db)
    check("3: marcar applied", rc == 0 and conn.execute(
        "SELECT status FROM job_status WHERE job_id=?", (JOB1,)
    ).fetchone()["status"] == "applied")
    app = conn.execute("SELECT * FROM job_applications WHERE job_id=?",
                       (JOB1,)).fetchone()
    check("4: application date registrada",
          app is not None and app["applied_at"] == "2026-09-20")
    check("contato salvo", app is not None and app["contact"] == "LinkedIn")
    check("evento applied_at", pt.has_event(conn, JOB1, "applied_at"))
    conn.close()
    # 7/8. interview, offer; 9. rejected (em outra vaga)
    check("7: interview", run_cli(db, ranking, jobs_db, "mark", JOB1,
                                  "--status", "interview") == 0)
    rc = run_cli(db, ranking, jobs_db, "applied", JOB1, "--interview",
                 "2026-09-28")
    conn = pt.connect(db)
    check("7b: interview date", conn.execute(
        "SELECT interview_at FROM job_applications WHERE job_id=?",
        (JOB1,)).fetchone()["interview_at"] == "2026-09-28")
    conn.close()
    check("8: offer", run_cli(db, ranking, jobs_db, "mark", JOB1,
                             "--status", "offer") == 0)
    check("9: rejected (vaga 2)", run_cli(db, ranking, jobs_db, "mark", JOB2,
                                         "--status", "rejected") == 0)
    # feedback
    check("11 (feedback): liked com motivos",
          run_cli(db, ranking, jobs_db, "feedback", JOB1, "--liked",
                  "--reasons", "area;empresa") == 0)
    check("11 (feedback): ignored com motivos",
          run_cli(db, ranking, jobs_db, "feedback", JOB2, "--ignored",
                  "--reasons", "german_required;visa") == 0)
    try:
        run_cli(db, ranking, jobs_db, "feedback", JOB1)
        bad = False
    except SystemExit:
        bad = True  # argparse exige --liked OU --ignored (exit 2)
    check("feedback exige um (liked XOR ignored)", bad)


def test_sync_and_persistence() -> None:
    print("== bloco 10-11, 19: saida do ATS/ranking + idempotencia ==")
    tmp, db, ranking, jobs_db = fresh_env()
    seed_jobs_db(jobs_db, [(JOB1, 1), (JOB2, 0), (JOB3, 0)])
    seed_ranking(ranking, [
        {"id": JOB1, "title": "A", "company": "C1", "score": 5.0},
    ])
    run_cli(db, ranking, jobs_db, "applied", JOB2, "--date", "2026-09-19")
    # JOB2 aplicada mas NAO esta no ranking -> removed_from_ranking
    # JOB2 active=0 no jobs.db -> ats_gone
    run_cli(db, ranking, jobs_db, "sync-ranking")
    conn = pt.connect(db)
    check("10: vaga fora do jobs.db/ATS ganha ats_gone",
          pt.has_event(conn, JOB2, "ats_gone"))
    check("11: vaga aplicada fora do ranking ganha removed_from_ranking",
          pt.has_event(conn, JOB2, "removed_from_ranking"))
    st = conn.execute("SELECT status FROM job_status WHERE job_id=?",
                      (JOB2,)).fetchone()
    check("11b: status pessoal PRESERVADO (nao apagado)",
          st is not None and st["status"] == "applied")
    conn.close()
    # 19: novo refresh (sync de novo) NAO duplica eventos
    run_cli(db, ranking, jobs_db, "sync-ranking")
    conn = pt.connect(db)
    n = conn.execute("SELECT COUNT(*) c FROM job_events WHERE job_id=? AND "
                     "kind='removed_from_ranking'", (JOB2,)).fetchone()["c"]
    check("19: sync repetido nao duplica evento (idempotente)", n == 1)
    conn.close()
    # persistencia real: reabrir o banco e conferir
    conn = sqlite3.connect(str(db))
    rows = conn.execute("SELECT COUNT(*) FROM job_status").fetchone()[0]
    conn.close()
    check("19b: banco reaberto mantem estado", rows == 1)


def test_shortlist_and_views() -> None:
    print("== bloco 12, 14, 16: shortlist, deadline, export ==")
    tmp, db, ranking, jobs_db = fresh_env()
    seed_jobs_db(jobs_db, [(JOB1, 1)])
    # deadline curto RELATIVO (hoje +1d): fixture com data fixa expira e
    # quebra o CI por puro drift temporal (visto 26/09: deadline 2026-09-25)
    dl_iso = (datetime.now(UTC).date() + timedelta(days=1)).isoformat() + "T00:00:00Z"
    seed_ranking(ranking, [
        {"id": JOB1, "title": "Praktikant", "company": "BMW AG",
         "location": "München", "score": 14.0,
         "application_deadline": dl_iso},
    ])
    for s in ("interesting", "review", "applied", "offer", "ignored"):
        run_cli(db, ranking, jobs_db, "mark", JOB1 if s != "ignored" else JOB2,
                "--status", s)
    conn = pt.connect(db)
    rows = conn.execute(
        "SELECT COUNT(*) FROM job_status WHERE status IN ("
        + ",".join("?" * len(pt.SHORTLIST_STATUSES)) + ")",
        pt.SHORTLIST_STATUSES).fetchone()[0]
    check("12: shortlist conta apenas os 5 status (ignored fora)", rows == 1)
    conn.close()
    # 16: export CSV com campos exatos
    csv_path = tmp / "out.csv"
    check("16: export csv", run_cli(db, ranking, jobs_db, "export",
                                    "--csv", str(csv_path)) == 0)
    text = csv_path.read_text(encoding="utf-8").splitlines()
    header = text[0].split(",")
    want = {"title", "company", "location", "score", "profile", "status",
            "application_date", "deadline", "personal_priority", "job_id"}
    check("16b: header CSV tem os campos do §23", want.issubset(set(header)))
    # 14: deadline reminder — shortlist com deadline <= 3 dias
    reminders = pt.reminder_jobs(pt.connect(db), pt.load_ranking(ranking))
    # JOB1 tem deadline curto (hoje +1d, kind employer por campo explicito) e
    # status offer -> deve aparecer
    check("14: reminder com deadline curto inclui a vaga da shortlist",
          any(j["job_id"] == JOB1 for j in reminders))
    conn.close()


def test_telegram_sections() -> None:
    print("== bloco 15: secoes pessoais do Telegram (ranking_digest) ==")
    try:
        import ranking_digest
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import ranking_digest
    tmp, db, ranking, jobs_db = fresh_env()
    seed_jobs_db(jobs_db, [(JOB1, 1), (JOB2, 1)])
    # deadline curto RELATIVO (hoje +1d) — mesmo drift temporal do bloco 14
    dl_iso = (datetime.now(UTC).date() + timedelta(days=1)).isoformat() + "T00:00:00Z"
    seed_ranking(ranking, [
        {"id": JOB1, "title": "Praktikant Einkauf", "company": "BMW AG",
         "location": "München", "score": 14.0,
         "application_deadline": dl_iso},
        {"id": JOB2, "title": "Working Student", "company": "SAP",
         "score": 9.5},
    ])
    run_cli(db, ranking, jobs_db, "mark", JOB1, "--status", "interesting")
    run_cli(db, ranking, jobs_db, "applied", JOB2, "--date", "2026-09-20")
    lines = ranking_digest.personal_sections(
        db_path=db, current_path=ranking, ref_date=None)
    check("15: secao reminders presente (shortlist c/ deadline)",
          any("Application reminders" in ln for ln in lines))
    check("15b: secao aguardando resposta presente",
          any("aguardando resposta" in ln for ln in lines))
    joined = "\n".join(lines)
    check("15c: notas pessoais NAO vazam para o Telegram",
          "contato procurement" not in joined)
    # sem banco: silencio (nao quebra o run)
    lines2 = ranking_digest.personal_sections(
        db_path=tmp / "personal" / "missing.db", current_path=ranking,
        ref_date=None)
    check("15d: banco ausente -> secoes vazias (nunca derruba)",
          lines2 == [])
    # banco corrompido: idem
    bad = tmp / "bad.db"
    bad.write_text("not a sqlite file", encoding="utf-8")
    lines3 = ranking_digest.personal_sections(
        db_path=bad, current_path=ranking, ref_date=None)
    check("15e: banco corrompido -> secoes vazias (nunca derruba)",
          lines3 == [])


def test_interface_hint_privacy() -> None:
    print("== bloco 13, 17, 18, 20: interface (hint, compare, privacidade) ==")
    try:
        import interface
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import interface
    jobs = [
        {"id": "X|s:1", "title": "Praktikant Supply Chain", "company": "ACME",
         "location": "München", "country_iso": "de", "score": 10.0,
         "score_breakdown": {"area": 2.0}, "collected_at": "2026-09-21T06:00:00Z",
         "employment_type": "Praktikum", "url": "https://example.com/1"},
        {"id": "Y|s:2", "title": "Working Student Analytics", "company": "GMBH",
         "location": "Berlin", "country_iso": "de", "score": 8.0,
         "score_breakdown": {"area": 2.0}, "collected_at": "2026-09-21T06:00:00Z",
         "employment_type": "Werkstudent", "url": "https://example.com/2"},
    ]
    html = interface.render_html(
        jobs, total=2, source_label="fixture", filters_desc=[],
        generated_at="2026-09-22T00:00:00Z",
        ref_date=__import__("datetime").date(2026, 9, 22),
    )
    check("17/18: hint do tracker presente por vaga (desktop+mobile)",
          "personal_tracker.py" in html)
    check("hint dentro de bloco recolhivel <details>",
          "<details" in html and "personal_tracker" in html)
    check("data-attr do id da vaga exposto",
          'data-job-id="X|s:1"' in html and 'data-job-id="Y|s:2"' in html)
    check("13: Compare opportunities (Fase 7) segue presente",
          "cmp-cb" in html and "Compare opportunities" in html)
    check("20: NENHUM campo pessoal no HTML (status/notas/prioridade)",
          "applied" not in html.lower().replace("application_deadline", "")
          and "shortlist vazia" not in html
          and "job_personal.db" not in html)
    check("20b: banco pessoal NAO mencionado no HTML",
          "jobs_personal" not in html)
    # scores intactos
    check("score data-attr intocado pela fase 8",
          'data-score="10.0"' in html and 'data-score="8.0"' in html)


def test_privacy_gitignore() -> None:
    print("== bloco 20: privacidade — data/ nunca versionada ==")
    root = Path(__file__).resolve().parent.parent
    gi = (root / ".gitignore").read_text(encoding="utf-8")
    check("20c: .gitignore cobre data/ (banco pessoal fora do git)",
          "data/" in gi)


def test_integration_refresh_gate() -> None:
    print("== bloco 15f: gate exit 0 (digest) e falha nao derruba ==")
    # personal_sections e best-effort por design; testar direto o contrato
    # da funcao: banco com shortlist vazia -> sem reminders
    tmp, db, ranking, jobs_db = fresh_env()
    seed_jobs_db(jobs_db, [])
    seed_ranking(ranking, [])
    run_cli(db, ranking, jobs_db, "mark", JOB1, "--status", "ignored")
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import ranking_digest
    except ImportError:
        pass
    lines = ranking_digest.personal_sections(
        db_path=db, current_path=ranking, ref_date=None)
    check("15g: shortlist vazia (so ignored) -> sem reminders",
          not any("Application reminders" in ln for ln in lines))


def main() -> int:
    test_status_flow()
    test_sync_and_persistence()
    test_shortlist_and_views()
    test_telegram_sections()
    test_interface_hint_privacy()
    test_privacy_gitignore()
    test_integration_refresh_gate()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
