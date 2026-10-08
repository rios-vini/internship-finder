#!/usr/bin/env python3
"""Personal tracker (Fase 8) — decision support + application tracking.

Estado PESSOAL das vagas: status, prioridade, notas, datas de candidatura,
feedback e histórico — armazenados em um banco SQLite PRIVADO
(``data/personal/jobs_personal.db``). ``data/`` é gitignored, portanto o
banco NUNCA é versionado e NUNCA é publicado no GitHub Pages (o publicador
sobe apenas ``index.html`` e o gate ``check_public_safe`` bloqueia qualquer
menção a ``jobs.db``/caminhos privados).

Identidade da vaga = ``Job.id`` canônico (``<company>|<source>:<external_id>``
ou hash da URL), a MESMA chave primária do ``data/jobs.db`` da coleta (P1.1)
— nunca ``title + company``. Nenhum identificador paralelo (§20 da spec).

Status (§1): ``new interesting review applied interview offer rejected
withdrawn ignored``. Shortlist (§6) = ``interesting review applied
interview offer``. Feedback (§11) são motivos livres separados por ``;``
(collect-only — §12: NUNCA altera pesos/score automaticamente).

Histórico (§10): tabela append-only ``job_events`` com UM evento por
mudança (kind + timestamp), suficiente para responder quando a vaga foi
marcada/aplicada/mudou de status/saiu do ranking/desapareceu do ATS — sem
sistema de eventos complexo.

Expiração (§19): ``sync-ranking`` NÃO apaga nada — vagas que saem do
ranking/ATS ganham eventos ``removed_from_ranking``/``ats_gone`` (idempotentes:
no máximo um de cada por vaga) e continuam com status/histórico preservados.

Uso:
    python3 scripts/personal_tracker.py mark <job_id> --status interesting
    python3 scripts/personal_tracker.py mark <id> --status applied --priority high \
        --note "adaptar CV" --next-action "Apply" --effort medium \
        --effort-flags "cv_adaptation;cover_letter"
    python3 scripts/personal_tracker.py applied <id> --date 2026-09-22 [--contact ...]
    python3 scripts/personal_tracker.py feedback <id> --liked --reasons "area;salario"
    python3 scripts/personal_tracker.py note <id> --text "verificar alemão"
    python3 scripts/personal_tracker.py list [--status ...] [--shortlist]
    python3 scripts/personal_tracker.py sync-ranking
    python3 scripts/personal_tracker.py show <id>
    python3 scripts/personal_tracker.py export [--csv PATH]
    python3 scripts/personal_tracker.py metrics
    python3 scripts/personal_tracker.py funnel
    python3 scripts/personal_tracker.py ranking-feedback
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder import app_intel  # noqa: E402  (deadline employer p/ reminders)

# ------------------------------------------------------------------ constantes

STATUSES = (
    "new", "interesting", "review", "applied",
    "interview", "offer", "rejected", "withdrawn", "ignored",
)
SHORTLIST_STATUSES = ("interesting", "review", "applied", "interview", "offer")
PRIORITIES = ("high", "normal", "low")
EFFORTS = ("low", "medium", "high")

DEFAULT_DB = Path("data/personal/jobs_personal.db")
DEFAULT_RANKING = Path("data/eligible_jobs.json")
DEFAULT_JOBS_DB = Path("data/jobs.db")
DEFAULT_CSV = Path("data/personal/shortlist.csv")
TOP_N = 30  # mesmo corte visual/digest do ranking principal

DDL = """
CREATE TABLE IF NOT EXISTS job_status (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    priority TEXT,
    next_action TEXT,
    effort TEXT,
    effort_flags TEXT,
    note TEXT,
    updated_at TEXT NOT NULL,
    first_marked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_events (
    job_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail TEXT,
    PRIMARY KEY (job_id, ts, kind)
);
CREATE TABLE IF NOT EXISTS job_applications (
    job_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    status TEXT,
    response_at TEXT,
    interview_at TEXT,
    contact TEXT
);
"""

EVENT_KINDS = (
    "marked", "priority", "note", "applied_at", "interview_at",
    "response_at", "contact", "status_changed",
    "removed_from_ranking", "ats_gone",
    "feedback_liked", "feedback_ignored",
)


def utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Abre (criando diretório/schema se preciso) o banco pessoal."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    return conn


def add_event(conn: sqlite3.Connection, job_id: str, kind: str,
              detail: str | None = None, ts: str | None = None) -> None:
    """Append-only; PK (job_id, ts, kind) — nunca duplica o MESMO evento."""
    conn.execute(
        "INSERT OR IGNORE INTO job_events (job_id, ts, kind, detail) "
        "VALUES (?, ?, ?, ?)",
        (job_id, ts or utcnow_iso(), kind, detail),
    )


def has_event(conn: sqlite3.Connection, job_id: str, kind: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM job_events WHERE job_id = ? AND kind = ? LIMIT 1",
        (job_id, kind),
    ).fetchone()
    return row is not None


def upsert_status(conn: sqlite3.Connection, job_id: str, status: str, *,
                  priority: str | None = None, next_action: str | None = None,
                  effort: str | None = None, effort_flags: str | None = None,
                  note: str | None = None) -> None:
    """Upsert do estado pessoal; ``first_marked_at`` imutável; campos não
    informados preservam o valor existente (COALESCE)."""
    now = utcnow_iso()
    old = conn.execute(
        "SELECT status FROM job_status WHERE job_id = ?", (job_id,)
    ).fetchone()
    if old is None:
        conn.execute(
            "INSERT INTO job_status (job_id, status, priority, next_action, "
            "effort, effort_flags, note, updated_at, first_marked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, status, priority, next_action, effort, effort_flags,
             note, now, now),
        )
        add_event(conn, job_id, "marked", status)
    else:
        conn.execute(
            "UPDATE job_status SET status = ?, "
            "priority = COALESCE(?, priority), "
            "next_action = COALESCE(?, next_action), "
            "effort = COALESCE(?, effort), "
            "effort_flags = COALESCE(?, effort_flags), "
            "note = COALESCE(?, note), updated_at = ? WHERE job_id = ?",
            (status, priority, next_action, effort, effort_flags, note,
             now, job_id),
        )
        if old["status"] != status:
            add_event(conn, job_id, "status_changed",
                      f"{old['status']} -> {status}")
        else:
            add_event(conn, job_id, "marked", status)


# ------------------------------------------------------------------ comandos

def cmd_mark(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.status not in STATUSES:
        print(f"ERRO: status invalido {args.status!r} (use: {' | '.join(STATUSES)})")
        return 1
    if args.priority is not None and args.priority not in PRIORITIES:
        print(f"ERRO: prioridade invalida {args.priority!r} (use: {' | '.join(PRIORITIES)})")
        return 1
    if args.effort is not None and args.effort not in EFFORTS:
        print(f"ERRO: effort invalido {args.effort!r} (use: {' | '.join(EFFORTS)})")
        return 1
    upsert_status(conn, args.job_id, args.status,
                  priority=args.priority, next_action=args.next_action,
                  effort=args.effort, effort_flags=args.effort_flags,
                  note=args.note)
    if args.priority is not None:
        add_event(conn, args.job_id, "priority", args.priority)
    if args.note is not None:
        add_event(conn, args.job_id, "note", args.note)
    if args.status == "applied":
        # registrar candidatura implicita quando marca applied sem `applied`
        row = conn.execute(
            "SELECT applied_at FROM job_applications WHERE job_id = ?",
            (args.job_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO job_applications (job_id, applied_at, status) "
                "VALUES (?, ?, ?)",
                (args.job_id, utcnow_iso(), args.status),
            )
            add_event(conn, args.job_id, "applied_at", utcnow_iso())
    conn.commit()
    print(f"[OK] {args.job_id} -> status={args.status}"
          + (f" priority={args.priority}" if args.priority else "")
          + (f" note={args.note!r}" if args.note else ""))
    return 0


def _parse_date(value: str | None) -> str:
    """Valida YYYY-MM-DD (ou None -> agora)."""
    if value is None:
        return datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"ERRO: data invalida {value!r} (use YYYY-MM-DD): {exc}")
    return value


def cmd_applied(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    applied_at = _parse_date(args.date)
    conn.execute(
        "INSERT INTO job_applications (job_id, applied_at, status, response_at, "
        "interview_at, contact) VALUES (?, ?, 'applied', ?, ?, ?) "
        "ON CONFLICT(job_id) DO UPDATE SET applied_at = excluded.applied_at, "
        "status = 'applied', "
        "response_at = COALESCE(excluded.response_at, response_at), "
        "interview_at = COALESCE(excluded.interview_at, interview_at), "
        "contact = COALESCE(excluded.contact, contact)",
        (args.job_id, applied_at, args.response, args.interview, args.contact),
    )
    add_event(conn, args.job_id, "applied_at", applied_at)
    if args.interview:
        add_event(conn, args.job_id, "interview_at", args.interview)
    if args.response:
        add_event(conn, args.job_id, "response_at", args.response)
    if args.contact:
        add_event(conn, args.job_id, "contact", args.contact)
    # marcar status applied (idempotente)
    upsert_status(conn, args.job_id, "applied")
    conn.commit()
    print(f"[OK] candidatura registrada: {args.job_id} applied_at={applied_at}")
    return 0


def cmd_feedback(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if bool(args.liked) == bool(args.ignored):
        print("ERRO: informe exatamente um: --liked OU --ignored")
        return 1
    kind = "feedback_liked" if args.liked else "feedback_ignored"
    add_event(conn, args.job_id, kind, args.reasons or "")
    conn.commit()
    print(f"[OK] feedback {kind} registrado para {args.job_id}"
          + (f" (motivos: {args.reasons})" if args.reasons else ""))
    return 0


def cmd_note(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    add_event(conn, args.job_id, "note", args.text)
    row = conn.execute(
        "SELECT status FROM job_status WHERE job_id = ?", (args.job_id,)
    ).fetchone()
    if row is None:
        # nota em vaga nunca marcada: cria estado implicito 'new'
        upsert_status(conn, args.job_id, "new", note=args.text)
    else:
        conn.execute(
            "UPDATE job_status SET note = COALESCE(?, note), updated_at = ? "
            "WHERE job_id = ?",
            (args.text, utcnow_iso(), args.job_id),
        )
    conn.commit()
    print(f"[OK] nota registrada para {args.job_id}: {args.text!r}")
    return 0


def cmd_show(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    st = conn.execute(
        "SELECT * FROM job_status WHERE job_id = ?", (args.job_id,)
    ).fetchone()
    app_row = conn.execute(
        "SELECT * FROM job_applications WHERE job_id = ?", (args.job_id,)
    ).fetchone()
    events = conn.execute(
        "SELECT ts, kind, detail FROM job_events WHERE job_id = ? "
        "ORDER BY ts", (args.job_id,),
    ).fetchall()
    if st is None and app_row is None and not events:
        print(f"(nada registrado para {args.job_id})")
        return 0
    print(f"== {args.job_id}")
    if st is not None:
        d = dict(st)
        print(f"status: {d['status']}  prioridade: {d['priority'] or '-'}  "
              f"next action: {d['next_action'] or '-'}  "
              f"effort: {d['effort'] or '-'}"
              + (f" ({d['effort_flags']})" if d['effort_flags'] else ""))
        print(f"nota: {d['note'] or '-'}")
        print(f"marcado em: {d['first_marked_at']}  atualizado: {d['updated_at']}")
    if app_row is not None:
        a = dict(app_row)
        print(f"candidatura: applied_at={a['applied_at']}  "
              f"resposta: {a['response_at'] or '-'}  "
              f"entrevista: {a['interview_at'] or '-'}  "
              f"contato: {a['contact'] or '-'}")
    if events:
        print("historico:")
        for ev in events:
            det = f": {ev['detail']}" if ev["detail"] else ""
            print(f"  {ev['ts']}  {ev['kind']}{det}")
    return 0


def cmd_list(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    where, params = [], []
    if args.status:
        for s in args.status:
            if s not in STATUSES:
                print(f"ERRO: status invalido {s!r}")
                return 1
        where.append(f"status IN ({','.join('?' * len(args.status))})")
        params.extend(args.status)
    if args.shortlist:
        where.append(f"status IN ({','.join('?' * len(SHORTLIST_STATUSES))})")
        params.extend(SHORTLIST_STATUSES)
    sql = "SELECT job_id, status, priority, next_action, note, updated_at "           "FROM job_status"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC"
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("(shortlist vazia — nada marcado)"
              if args.shortlist else "(nenhuma vaga marcada)")
        return 0
    print(f"{'status':12} {'prio':7} {'job_id':50} nota")
    for r in rows:
        print(f"{r['status']:12} {r['priority'] or '-':7} "
              f"{r['job_id']:50} {r['note'] or ''}")
    # contagem por status (§6)
    counts = conn.execute(
        "SELECT status, COUNT(*) n FROM job_status"
        + (" WHERE status IN ("
           + ",".join("?" * len(SHORTLIST_STATUSES)) + ")"
           if args.shortlist else "")
        + " GROUP BY status ORDER BY status",
        params if args.shortlist else [],
    ).fetchall()
    if counts:
        print("\ncontagem por status:")
        for c in counts:
            print(f"  {c['status']:12} {c['n']}")
    return 0


def load_ranking(ranking_path: Path | str) -> list[dict]:
    try:
        data = json.loads(Path(ranking_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def cmd_sync_ranking(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Detecta vagas da shortlist que sairam do ranking/ATS (§19, idempotente).

    - ``removed_from_ranking``: vaga marcada que NAO esta no eligible atual.
    - ``ats_gone``: vaga marcada que no jobs.db da coleta esta active=0
      (desapareceu do ATS). Status pessoal NUNCA e apagado.
    """
    ranking = load_ranking(args.ranking)
    ranking_ids = {str(j.get("id")) for j in ranking if j.get("id")}
    active_ids: set[str] | None = None
    jobs_db = Path(args.jobs_db)
    if jobs_db.exists():
        try:
            c = sqlite3.connect(str(jobs_db))
            active_ids = {
                row[0] for row in c.execute("SELECT id FROM jobs WHERE active = 1")
            }
            c.close()
        except sqlite3.Error:
            active_ids = None  # jobs.db ilegivel: so o ranking e avaliado
    marked = conn.execute(
        "SELECT job_id FROM job_status"
    ).fetchall()
    n_removed = n_gone = 0
    for row in marked:
        jid = row["job_id"]
        if jid not in ranking_ids and not has_event(conn, jid, "removed_from_ranking"):
            add_event(conn, jid, "removed_from_ranking")
            n_removed += 1
        if active_ids is not None and jid not in active_ids \
                and not has_event(conn, jid, "ats_gone"):
            add_event(conn, jid, "ats_gone")
            n_gone += 1
    conn.commit()
    print(f"[OK] sync-ranking: {len(marked)} marcadas; "
          f"+{n_removed} removed_from_ranking; +{n_gone} ats_gone "
          f"(idempotente — status/historico preservados)")
    return 0


def cmd_export(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """CSV da shortlist/aplicacoes (§23); nunca publica dados pessoais."""
    ranking = load_ranking(args.ranking)
    by_id = {str(j.get("id")): j for j in ranking if j.get("id")}
    rows = conn.execute(
        "SELECT s.job_id, s.status, s.priority, s.note, a.applied_at, "
        "a.response_at, a.interview_at "
        "FROM job_status s LEFT JOIN job_applications a USING (job_id) "
        "ORDER BY s.updated_at DESC"
    ).fetchall()
    out = Path(args.csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["title", "company", "location", "score", "profile",
                    "status", "application_date", "deadline", "personal_priority",
                    "job_id", "note"])
        for r in rows:
            j = by_id.get(r["job_id"], {})
            w.writerow([
                j.get("title", "No longer active"),
                j.get("company", "No longer active"),
                j.get("location", ""),
                j.get("score", ""),
                j.get("profile", "biz"),
                r["status"],
                r["applied_at"] or "",
                j.get("application_deadline", ""),
                r["priority"] or "",
                r["job_id"],
                r["note"] or "",
            ])
    print(f"[OK] export: {out} ({len(rows)} linhas)")
    return 0


def cmd_metrics(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Metricas DESCRITIVAS (§14) — sem previsao, sem inferencia."""
    st = conn.execute(
        "SELECT status, COUNT(*) n FROM job_status GROUP BY status"
    ).fetchall()
    counts = {r["status"]: r["n"] for r in st}
    total_marked = sum(counts.values())
    print("== Metricas descritivas ==")
    for s in STATUSES:
        if counts.get(s):
            print(f"  {s:12} {counts[s]}")
    n_interesting = counts.get("interesting", 0) + counts.get("review", 0)
    n_applied = counts.get("applied", 0) + counts.get("interview", 0) \
        + counts.get("offer", 0)
    if n_interesting:
        print(f"  taxa applied/(interesting+review): "
              f"{n_applied}/{n_interesting} = "
              f"{100.0 * n_applied / n_interesting:.0f}%")
    # tempo medio descoberta -> candidatura via first_seen do jobs.db
    jobs_db = Path(args.jobs_db)
    if jobs_db.exists():
        try:
            c = sqlite3.connect(str(jobs_db))
            first_seen = {
                row[0]: row[1] for row in
                c.execute("SELECT id, first_seen FROM jobs")
            }
            c.close()
        except sqlite3.Error:
            first_seen = {}
        deltas = []
        for r in conn.execute(
            "SELECT job_id, applied_at FROM job_applications"
        ).fetchall():
            fs = first_seen.get(r["job_id"])
            if not fs or not r["applied_at"]:
                continue
            try:
                d0 = datetime.fromisoformat(fs.replace("Z", "+00:00"))
                d1 = datetime.strptime(r["applied_at"], "%Y-%m-%d") \
                    .replace(tzinfo=UTC)
                days = (d1 - d0).days
                if days >= 0:
                    deltas.append(days)
            except ValueError:
                continue
        if deltas:
            print(f"  tempo medio descoberta->candidatura: "
                  f"{sum(deltas) / len(deltas):.1f} dias (n={len(deltas)})")
    # distribuicao por empresa (do ranking quando o id esta presente)
    ranking = load_ranking(args.ranking)
    comp: dict[str, int] = {}
    for j in ranking:
        jid = str(j.get("id"))
        row = conn.execute(
            "SELECT 1 FROM job_status WHERE job_id = ?", (jid,)
        ).fetchone()
        if row and j.get("company"):
            comp[str(j["company"])] = comp.get(str(j["company"]), 0) + 1
    if comp:
        print("  distribuicao por empresa (marcadas no ranking atual):")
        for k in sorted(comp, key=lambda x: -comp[x])[:8]:
            print(f"    {k}: {comp[k]}")
    print(f"  total marcadas: {total_marked}")
    return 0


def cmd_funnel(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Opportunity funnel (§15): contagens por estagio, sem interpretacao."""
    ranking = load_ranking(args.ranking)
    eligible = len(ranking)
    top_ids = {str(j.get("id")) for j in ranking[:TOP_N] if j.get("id")}
    m = conn.execute(
        "SELECT status, COUNT(*) n FROM job_status GROUP BY status"
    ).fetchall()
    counts = {r["status"]: r["n"] for r in m}
    top30_marked = conn.execute(
        "SELECT COUNT(*) n FROM job_status WHERE job_id IN ("
        + ",".join("?" * len(top_ids)) + ")",
        tuple(top_ids),
    ).fetchone()["n"] if top_ids else 0
    print("== Opportunity funnel ==")
    print(f"  Eligible:              {eligible}")
    print(f"  Top 30:                {min(eligible, TOP_N)}")
    print(f"  marcadas no Top 30:    {top30_marked}")
    for label, key in (("Interesting", "interesting"), ("Review", "review"),
                       ("Applied", "applied"), ("Interview", "interview"),
                       ("Offer", "offer")):
        print(f"  {label:22} {counts.get(key, 0)}")
    print("(contagens de fatos; nenhuma interpretacao automatica)")
    return 0


def cmd_ranking_feedback(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Diagnostico ranking vs comportamento (§13) — dados, sem julgamento."""
    ranking = load_ranking(args.ranking)
    top_ids = {str(j.get("id")) for j in ranking[:TOP_N] if j.get("id")}
    rows = conn.execute("SELECT job_id, status FROM job_status").fetchall()
    buckets = {"top30": {}, "outside": {}}
    for r in rows:
        bucket = "top30" if r["job_id"] in top_ids else "outside"
        buckets[bucket][r["status"]] = buckets[bucket].get(r["status"], 0) + 1
    print("== Ranking feedback (Top 30 vs fora) ==")
    for label, key in (("Top 30", "top30"), ("Outside Top 30", "outside")):
        items = ", ".join(
            f"{k}={v}" for k, v in sorted(buckets[key].items())
        ) or "vazio"
        print(f"  {label}: {items}")
    print("(diagnostico descritivo; o ranking NAO aprende com isso — §12)")
    return 0


# ------------------------------------------------------------- F14 (semanal)

# F14 — métricas semanais janela: 7 dias corridos (spec §2.2).
WEEKLY_WINDOW_DAYS = 7


def _parse_event_ts(value: str) -> datetime | None:
    """Parse tolerante do ``ts`` de um evento (ISO com Z ou data pura)."""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _response_status(conn: sqlite3.Connection, job_id: str) -> str | None:
    """Status DE RESPOSTA da vaga, derivado do estado atual (F14; pura).

    "Resposta" = qualquer desfecho pós-candidatura: interview/offer =
    sinal positivo; rejected/withdrawn = fechamento. Status ainda
    ``applied``/`review` = sem resposta (None).
    """
    row = conn.execute(
        "SELECT status FROM job_status WHERE job_id = ?", (job_id,)
    ).fetchone()
    if row is None:
        return None
    if row["status"] in ("interview", "offer"):
        return "positive"
    if row["status"] in ("rejected", "withdrawn"):
        return "closed"
    return None


def weekly_metrics(conn: sqlite3.Connection, *, days: int = WEEKLY_WINDOW_DAYS,
                   ref: "datetime | str | None" = None) -> dict:
    """Métricas da janela semanal (F14 §2.2) a partir de ``job_events``.

    Janela = últimos ``days`` dias corridos (default 7). Conta FATOS do
    append-only ``job_events`` — zero schema novo, zero banco novo:

    - ``applied``: eventos ``applied_at`` cujo ``ts`` (data da
      candidatura registrada no detail) cai na janela;
    - ``responses``: eventos ``response_at``/``interview_at`` na janela
      (resposta recebida — positiva ou negativa);
    - ``response_rate``: (interview+rejected+withdrawn)/applied — aqui
      via eventos: respostas/applied da janela, 0% gracioso quando
      ``applied == 0`` (sem divisão por zero, sem mentira);
    - ``interviews``: eventos ``interview_at`` na janela;
    - ``pending``: candidaturas SEM resposta nenhuma até agora (estado,
      não janela — para contexto da seção de follow-up).

    Datas: o evento ``applied_at`` carrega a data real da candidatura no
    ``detail`` (``cmd_applied`` grava o --date; ``cmd_mark`` grava
    utcnow). O ``ts`` do registro é usado como fallback quando o detail
    não parseia.
    """
    from datetime import date as _date, timedelta as _timedelta
    if ref is None:
        ref = datetime.now(UTC)
    elif isinstance(ref, str):
        ref = datetime.fromisoformat(ref.replace("Z", "+00:00"))
    start = (ref - _timedelta(days=days)).date()

    def _event_date(row: sqlite3.Row):
        # detail (data real da candidatura) com fallback ao ts do evento
        for value in (row["detail"], row["ts"]):
            if not value:
                continue
            try:
                return _date.fromisoformat(str(value)[:10])
            except ValueError:
                continue
        return None

    applied_ids: set[str] = set()
    response_count = 0
    interview_count = 0
    for row in conn.execute(
        "SELECT job_id, ts, kind, detail FROM job_events "
        "WHERE kind IN ('applied_at', 'response_at', 'interview_at')"
    ).fetchall():
        d = _event_date(row)
        if d is None or d < start or d > ref.date():
            continue
        if row["kind"] == "applied_at":
            applied_ids.add(row["job_id"])
        elif row["kind"] == "interview_at":
            interview_count += 1
            response_count += 1
        elif row["kind"] == "response_at":
            response_count += 1

    # aguardando resposta: MESMA semântica da F8 (§9) — reuso direto,
    # zero duplicação de regra (colunas de job_applications).
    pending = waiting_response(conn)

    n_applied = len(applied_ids)
    rate = (100.0 * response_count / n_applied) if n_applied else 0.0
    return {
        "window_days": days,
        "applied": n_applied,
        "responses": response_count,
        "interviews": interview_count,
        "response_rate_pct": round(rate, 1),
        "pending_no_response": pending,
    }


def cmd_weekly(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    """Comando `weekly` (F14 §2.2) — métricas semanais no stdout."""
    m = weekly_metrics(conn, days=args.days)
    print("== Métricas semanais (últimos 7 dias) ==")
    print(f"  candidaturas:        {m['applied']}")
    print(f"  respostas:           {m['responses']}")
    print(f"  entrevistas:         {m['interviews']}")
    print(f"  taxa de resposta:   {m['response_rate_pct']:.0f}% "
          f"({m['responses']}/{m['applied']})"
          + (" — sem candidaturas na janela" if not m["applied"] else ""))
    print(f"  aguardando resposta: {m['pending_no_response']}")
    print("(contagens de fatos do job_events; nenhuma interpretação)")
    return 0


def waiting_response(conn: sqlite3.Connection) -> int:
    """Aplicacoes sem resposta/entrevista (§9 do Telegram)."""
    return conn.execute(
        "SELECT COUNT(*) c FROM job_applications a "
        "LEFT JOIN job_status s USING (job_id) "
        "WHERE a.response_at IS NULL AND a.interview_at IS NULL "
        "AND s.status IN ('applied','review')"
    ).fetchone()["c"]


# ------------------------------------------------------------------ CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Personal tracker (Fase 8): status privado das vagas, "
                    "candidaturas, notas e feedback — banco em "
                    "data/personal/ (gitignored, nunca publicado).")
    p.add_argument("--db", default=str(DEFAULT_DB), metavar="PATH",
                   help=f"banco pessoal (default: {DEFAULT_DB})")
    p.add_argument("--ranking", default=str(DEFAULT_RANKING), metavar="PATH",
                   help=f"ranking elegivel atual (default: {DEFAULT_RANKING})")
    p.add_argument("--jobs-db", default=str(DEFAULT_JOBS_DB), metavar="PATH",
                   help=f"jobs.db da coleta p/ first_seen/active (default: {DEFAULT_JOBS_DB})")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("mark", help="marca/atualiza o estado pessoal da vaga")
    m.add_argument("job_id")
    m.add_argument("--status", required=True,
                   help=f"um de: {' | '.join(STATUSES)}")
    m.add_argument("--priority", choices=PRIORITIES,
                   help="prioridade PESSOAL (independente do score)")
    m.add_argument("--next-action",
                   help="proxima acao curta (ex.: 'Verify German requirement')")
    m.add_argument("--effort", choices=EFFORTS,
                   help="esforco estimado de candidatura")
    m.add_argument("--effort-flags", metavar="A;B",
                   help="ex.: 'cv_adaptation;cover_letter;complex_portal;referral'")
    m.add_argument("--note", help="nota curta pessoal")

    a = sub.add_parser("applied", help="registra candidatura (datas opcionais)")
    a.add_argument("job_id")
    a.add_argument("--date", metavar="YYYY-MM-DD",
                   help="data da candidatura (default: hoje)")
    a.add_argument("--response", metavar="YYYY-MM-DD", help="data de resposta")
    a.add_argument("--interview", metavar="YYYY-MM-DD", help="data de entrevista")
    a.add_argument("--contact", help="contato/origem (ex.: LinkedIn, referral)")

    f = sub.add_parser("feedback", help="por que gostei/ignorei (motivos livres)")
    f.add_argument("job_id")
    g = f.add_mutually_exclusive_group(required=True)
    g.add_argument("--liked", action="store_true")
    g.add_argument("--ignored", action="store_true")
    f.add_argument("--reasons", metavar="a;b;c",
                   help="ex. 'area;empresa;salario' ou 'german_required;visa'")

    n = sub.add_parser("note", help="nota curta por vaga")
    n.add_argument("job_id")
    n.add_argument("--text", required=True)

    s = sub.add_parser("show", help="estado + historico da vaga")
    s.add_argument("job_id")

    l = sub.add_parser("list", help="lista marcadas (filtre por status/shortlist)")
    l.add_argument("--status", action="append",
                   help=f"status a incluir (repita; um de: {' | '.join(STATUSES)})")
    l.add_argument("--shortlist", action="store_true",
                   help=f"so a shortlist ({'/'.join(SHORTLIST_STATUSES)})")

    sub.add_parser("sync-ranking",
                   help="registra saidas do ranking/ATS (idempotente; NAO apaga nada)")

    e = sub.add_parser("export", help="exporta shortlist/aplicacoes em CSV")
    e.add_argument("--csv", default=str(DEFAULT_CSV), metavar="PATH")

    sub.add_parser("metrics", help="metricas descritivas")
    sub.add_parser("funnel", help="opportunity funnel")
    sub.add_parser("ranking-feedback", help="Top 30 vs fora (diagnostico)")
    w = sub.add_parser("weekly", help="metricas semanais (F14): janela de "
                       "7 dias a partir dos job_events")
    w.add_argument("--days", type=int, default=WEEKLY_WINDOW_DAYS,
                   metavar="N", help=f"janela em dias (default {WEEKLY_WINDOW_DAYS})")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    try:
        if args.cmd == "mark":
            return cmd_mark(conn, args)
        if args.cmd == "applied":
            return cmd_applied(conn, args)
        if args.cmd == "feedback":
            return cmd_feedback(conn, args)
        if args.cmd == "note":
            return cmd_note(conn, args)
        if args.cmd == "show":
            return cmd_show(conn, args)
        if args.cmd == "list":
            return cmd_list(conn, args)
        if args.cmd == "sync-ranking":
            return cmd_sync_ranking(conn, args)
        if args.cmd == "export":
            return cmd_export(conn, args)
        if args.cmd == "metrics":
            return cmd_metrics(conn, args)
        if args.cmd == "funnel":
            return cmd_funnel(conn, args)
        if args.cmd == "ranking-feedback":
            return cmd_ranking_feedback(conn, args)
        if args.cmd == "weekly":
            return cmd_weekly(conn, args)
        conn.close()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())


def reminder_jobs(conn: sqlite3.Connection, ranking: list[dict],
                   ref: "object | None" = None,
                   max_days: int = 3) -> list[dict]:
    """Vagas da shortlist com deadline employer ate ``max_days`` dias (§8).

    Usa ``app_intel.deadline_kind``/``days_until`` — SO deadline EMPLOYER
    (estruturado) ou EMPLOYER_TEXTUAL (declarado no texto do anuncio, item 8
    da auditoria) conta como prazo; validade de feed SuccessFactors NUNCA
    (regra Fase 6).
    """
    from datetime import date as _date
    if ref is None:
        ref = _date.today()
    elif isinstance(ref, str):
        ref = _date.fromisoformat(ref)
    by_id = {str(j.get("id")): j for j in ranking if j.get("id")}
    short = conn.execute(
        "SELECT job_id, status FROM job_status WHERE status IN ("
        + ",".join("?" * len(SHORTLIST_STATUSES)) + ")",
        SHORTLIST_STATUSES,
    ).fetchall()
    out = []
    for row in short:
        j = by_id.get(row["job_id"])
        if not j:
            continue  # vaga fora do ranking atual (ja tem evento ats_gone/removed)
        if app_intel.deadline_kind(j) not in ("employer", "employer_textual"):
            continue
        days = app_intel.days_until(app_intel.deadline_date(j), ref)
        if days is not None and 0 <= days <= max_days:
            out.append({
                "job_id": row["job_id"], "status": row["status"],
                "days": days, "title": str(j.get("title") or ""),
                "company": str(j.get("company") or ""),
            })
    out.sort(key=lambda r: r["days"])
    return out


# ------------------------------------------------------- F14 — follow-up

# Dias sem resposta que transformam uma candidatura em pendência de
# follow-up (spec F14 §2.3; configurável por parâmetro).
FOLLOWUP_AFTER_DAYS = 10

# Eventos que NÃO contam como interação posterior à candidatura:
# - ``applied_at``: é a PRÓPRIA candidatura (detail = data real; o ts é
#   o momento do registro, que pode ser posterior à data retroativa);
# - ``marked``: meta-evento do upsert de status (acompanha o registro
#   da candidatura, mesmo ts do applied_at);
# - ``status_changed``: transição de ESTADO — o desfecho (interview/
#   rejected/withdrawn/offer) já tira a vaga pelo filtro status=
#   'applied'; voltar para applied = voltou a esperar (sem resposta),
#   a pendência volta a valer;
# - ``removed_from_ranking``/``ats_gone``: sincronização automática do
#   refresh (o sistema dizendo que a vaga saiu — não uma interação
#   do dono; follow-up segue válido para vaga que saiu do ATS).
# Interações que contam: note, response_at, interview_at, contact,
# priority, feedback_liked/feedback_ignored (ações e desfechos
# registrados pelo dono).
_NON_INTERACTION_KINDS = ("applied_at", "marked", "status_changed",
                          "removed_from_ranking", "ats_gone")

# Kinds cujo ``detail`` carrega uma DATA real (YYYY-MM-DD) — para eles
# a data do evento é o detail (ex.: resposta datada), não o ts do
# registro. Para os demais (note, status_changed, priority, feedback,
# contact) o ts do registro É a data real da interação.
_DATE_DETAIL_KINDS = ("applied_at", "response_at", "interview_at")


def _event_real_date(kind: str, ts: str, detail: "str | None") -> "str | None":
    """Data real (YYYY-MM-DD) de um evento; None quando indatável."""
    from datetime import date as _date
    if kind in _DATE_DETAIL_KINDS and detail:
        try:
            return _date.fromisoformat(str(detail)[:10]).isoformat()
        except ValueError:
            pass
    try:
        return _date.fromisoformat(str(ts)[:10]).isoformat()
    except ValueError:
        return None


def followup_pending(conn: sqlite3.Connection, *, ref=None,
                     after_days: int = FOLLOWUP_AFTER_DAYS,
                     max_shown: int = 5) -> list[dict]:
    """Candidaturas aplicadas há > ``after_days`` dias SEM evento posterior.

    F14 §2.3 — pendências de follow-up, do banco privado
    (``job_applications`` + ``job_events``; zero schema novo):

    - status ATUAL ``applied`` (interview/offer/rejected/withdrawn já
      são desfechos, saem da lista);
    - data da candidatura (``job_applications.applied_at``) há mais de
      ``after_days`` dias em relação a ``ref`` (default hoje);
    - SEM evento de interação posterior à candidatura (nota, resposta,
      entrevista, contato, prioridade, feedback) — meta-eventos do
      registro (``applied_at``/``marked``), transições de status
      (``status_changed`` — o desfecho já é filtrado pelo status atual)
      e eventos de sincronização (``removed_from_ranking``/``ats_gone``)
      NÃO contam.

    Ordem: a mais antiga primeiro (a que está apertando mais). Cap
    ``max_shown`` (digest); ``max_shown<=0`` = sem cap (uso manual).
    Pura: só lê o banco.
    """
    from datetime import date as _date
    if ref is None:
        ref = _date.today()
    elif isinstance(ref, str):
        ref = _date.fromisoformat(ref[:10])
    elif isinstance(ref, datetime):
        ref = ref.date()

    # eventos de interação por vaga (uma leitura única; escala pessoal)
    later_by_job: dict[str, str] = {}
    placeholders = ",".join("?" * len(_NON_INTERACTION_KINDS))
    for ev in conn.execute(
        "SELECT job_id, ts, kind, detail FROM job_events "
        f"WHERE kind NOT IN ({placeholders})",
        _NON_INTERACTION_KINDS,
    ).fetchall():
        d = _event_real_date(ev["kind"], ev["ts"], ev["detail"])
        if d is None:
            continue
        cur = later_by_job.get(ev["job_id"])
        if cur is None or d > cur:
            later_by_job[ev["job_id"]] = d

    rows = conn.execute(
        "SELECT a.job_id, a.applied_at, s.status "
        "FROM job_applications a "
        "JOIN job_status s USING (job_id) "
        "WHERE s.status = 'applied' AND a.applied_at IS NOT NULL"
    ).fetchall()
    out: list[dict] = []
    for row in rows:
        try:
            applied = _date.fromisoformat(str(row["applied_at"])[:10])
        except ValueError:
            continue
        days = (ref - applied).days
        if days <= after_days:
            continue
        if later_by_job.get(row["job_id"], "") > applied.isoformat():
            continue  # interação posterior à candidatura
        out.append({
            "job_id": row["job_id"], "applied_at": str(row["applied_at"]),
            "days": days,
        })
    out.sort(key=lambda r: (-r["days"], r["job_id"]))
    return out if max_shown <= 0 else out[:max_shown]
