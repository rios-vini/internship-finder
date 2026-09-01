"""Persistencia SQLite do historico de cada vaga entre coletas (P1 #5).

Grava o snapshot de cada run de coleta em um banco ``sqlite3`` (stdlib). Para
cada vaga registra:

- ``first_seen``: timestamp da 1a coleta em que a vaga apareceu (imutavel);
- ``last_seen``: timestamp da ultima coleta em que apareceu;
- ``active``: 1 se visivel na ultima coleta, 0 se nao veio;
- ``archived``: 1 quando uma vaga ativa deixa de ser vista, 0 se voltar
  (reativada) num run futuro.

O schema espelha o Job canonico (``src/internship_finder/models/job.py``) mais
esses quatro campos de vida. **A identidade da vaga e o campo ``id`` do Job** —
estavel por construcao (o hardening ACH-08 garantiu ids sem dependencia de
URL/external_id). Por isso a chave primaria e ``id`` (TEXT) e o upsert e feito
por ele.

A persistencia roda **no processo pai**, apos o merge dos jobs vindos dos
subprocessos do scraper (escritor unico; sqlite nao e usado em subprocesso).
Uma falha de escrita nunca derruba a coleta: ``run`` captura a excecao de
``sqlite3``, loga e segue.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from internship_finder.models.job import Job

log = logging.getLogger("internship_finder.storage.sqlite")

# Colunas do Job canonico persistidas no schema (``id`` e a PK, listada na DDL).
# Datetimes viram TEXT ISO 8601 UTC; ``raw`` (dict) vira JSON; bools INTEGER.
JOB_COLUMNS = [
    "source",
    "title",
    "company",
    "location",
    "country",
    "remote",
    "url",
    "description",
    "internship",
    "posted_at",
    "collected_at",
    "application_deadline",
    "external_id",
    "employment_type",
    "country_iso",
    "raw",
]

# Campos de vida acrescentados alem do Job canonico.
LIFECYCLE_COLUMNS = ["first_seen", "last_seen", "active", "archived"]

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    country TEXT,
    remote INTEGER,
    url TEXT NOT NULL,
    description TEXT,
    internship INTEGER NOT NULL DEFAULT 0,
    posted_at TEXT,
    collected_at TEXT NOT NULL,
    application_deadline TEXT,
    external_id TEXT,
    employment_type TEXT,
    country_iso TEXT,
    raw TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0
)
"""

_ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _to_iso(value: datetime | None) -> str | None:
    """Escreve datetime como TEXT ISO 8601 UTC (``…Z``). None permanece None."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return value.strftime(_ISO_FMT)


def _from_iso(text: str | None) -> datetime | None:
    """Le TEXT ISO 8601 de volta como datetime aware UTC. None permanece None."""
    if not text:
        return None
    try:
        return datetime.strptime(text, _ISO_FMT).replace(tzinfo=UTC)
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            log.warning("timestamp SQLite invalido: %r", text)
            return None


class SqliteStore:
    """Escritor/leitor unico do historico de vagas em um banco sqlite3.

    Seguro para uso exclusivo no processo pai (apos o merge). A conexao usa WAL
    e ``row_factory`` para linha-dict. ``run`` aplica o run completo num unico
    commit (transacao por run).
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None
        self._error: str | None = None
        try:
            conn = sqlite3.connect(str(self.path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(DDL)
            conn.commit()
            self._conn = conn
        except sqlite3.Error as exc:  # caminho inacessivel, disco cheio, etc.
            self._error = f"{type(exc).__name__}: {exc}"
            log.error("sqlite indisponivel em %s: %s", self.path, self._error)

    def close(self) -> None:
        """Fecha a conexao. Seguro chamar mais de uma vez."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _upsert(self, job: Job) -> str:
        """Insere ou atualiza uma vaga vista neste run.

        INSERT na 1a vez (``first_seen = last_seen = collected_at``, active=1);
        UPDATE depois (``last_seen = collected_at``, active=1, archived=0 —
        reativacao quando volta). Devolve ``"inserted"`` | ``"updated"`` |
        ``"reactivated"``.
        """
        seen_at = _to_iso(job.collected_at)
        row = self._conn.execute(
            "SELECT first_seen, archived FROM jobs WHERE id = ?", (job.id,)
        ).fetchone()
        if row is None:
            self._conn.execute(
                """INSERT INTO jobs (id, source, title, company, location, country,
                     remote, url, description, internship, posted_at, collected_at,
                     application_deadline, external_id, employment_type, country_iso,
                     raw, first_seen, last_seen, active, archived)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0)""",
                (
                    job.id,
                    job.source,
                    job.title,
                    job.company,
                    job.location,
                    job.country,
                    int(bool(job.remote)) if job.remote is not None else None,
                    job.url,
                    job.description,
                    int(bool(job.internship)),
                    _to_iso(job.posted_at),
                    seen_at,
                    _to_iso(job.application_deadline),
                    job.external_id,
                    job.employment_type,
                    job.country_iso,
                    json.dumps(job.raw, ensure_ascii=False) if job.raw is not None else None,
                    seen_at,
                    seen_at,
                ),
            )
            return "inserted"
        was_archived = row["archived"] == 1
        self._conn.execute(
            """UPDATE jobs SET source=?, title=?, company=?, location=?, country=?,
                 remote=?, url=?, description=?, internship=?, posted_at=?,
                 collected_at=?, application_deadline=?, external_id=?,
                 employment_type=?, country_iso=?, raw=?, last_seen=?, active=1,
                 archived=0
               WHERE id=?""",
            (
                job.source, job.title, job.company, job.location, job.country,
                int(bool(job.remote)) if job.remote is not None else None,
                job.url, job.description, int(bool(job.internship)),
                _to_iso(job.posted_at), seen_at, _to_iso(job.application_deadline),
                job.external_id, job.employment_type, job.country_iso,
                json.dumps(job.raw, ensure_ascii=False) if job.raw is not None else None,
                seen_at, job.id,
            ),
        )
        return "reactivated" if was_archived else "updated"

    def run(self, jobs: Iterable[Job]) -> dict[str, int]:
        """Persiste um run de coleta completo.

        Faz upsert de todas as vagas vistas agora; depois arquiva
        (``active=0, archived=1``) as que estavam ativas e NAO vieram neste run.
        Um unico commit ao final (transacao por run). Devolve
        ``{"inserted": n, "reactivated": n}``.

        Uma falha de escrita (``sqlite3.Error``) e logada e nao lanca
        (a coleta continua).
        """
        inserted = 0
        reactivated = 0
        if self._conn is None:
            log.error(
                "sqlite store indisponivel (%s); run ignorado",
                self._error or "conexao fechada",
            )
            return {"inserted": inserted, "reactivated": reactivated}
        try:
            ids_now: set[str] = set()
            for job in jobs:
                status = self._upsert(job)
                if status == "inserted":
                    inserted += 1
                elif status == "reactivated":
                    reactivated += 1
                ids_now.add(job.id)
            self._archive_not_seen(ids_now)
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            log.error("sqlite falhou ao persistir run: %s", exc)
        return {"inserted": inserted, "reactivated": reactivated}

    def _archive_not_seen(self, ids_seen: set[str]) -> None:
        """Active=1 que nao veio neste run -> active=0, archived=1."""
        if not ids_seen:
            self._conn.execute("UPDATE jobs SET active=0, archived=1 WHERE active=1")
            return
        placeholders = ",".join("?" * len(ids_seen))
        self._conn.execute(
            f"UPDATE jobs SET active=0, archived=1 WHERE active=1 "
            f"AND id NOT IN ({placeholders})",
            tuple(sorted(ids_seen)),
        )

    def get(self, job_id: str) -> sqlite3.Row | None:
        """Le uma linha do banco (leitura/tests). None se nao existir."""
        return self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

    def __enter__(self) -> "SqliteStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()