"""F135 — Persistent store for cross-source dedup keys.

Tracks dedup identities across runs so that twins arriving on different days
(RWE DE/EN, TI CX/CX_1, BASF repost) are recognized as the SAME vacancy.

The store is append-only, keys-only (like dataset_seen), and best-effort:
- ``(run_id, dedup_key, job_id, first_seen, last_seen)``
- Primary key: ``(run_id, dedup_key)`` — one entry per dedup_key per run
- Index on ``dedup_key`` for fast "have we seen this key before?" queries
- Never derails the run on failure (degrades to no-op with forensics)

Dedup key format (deterministic, same as cross_source_dedup grouping):
- ``anzeigencode:<code>`` when Anzeigencode/jobcode present in raw
- ``company_title_city:<company_id>:<title_key>:<city_key>`` otherwise
- ``oracle_site:<normalized_site>:<ext_id>`` for Oracle site_number normalization
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from internship_finder.dedup import normalize_url
from internship_finder.metrics import utcnow_iso

log = logging.getLogger(__name__)

# Default path relative to repo root (same convention as collection_metrics.jsonl)
DEFAULT_STORE_PATH = Path("data/cross_source_dedup.db")

STORE_TABLE = "cross_source_dedup"
STORE_INDEX = "csd_dedup_key"

# Flush every N writes (bounded loss on crash)
FLUSH_EVERY = 5000

_SCHEMA_SQL = (
    f"CREATE TABLE IF NOT EXISTS {STORE_TABLE} ("
    "    run_id     TEXT NOT NULL,"
    "    dedup_key  TEXT NOT NULL,"
    "    job_id     TEXT NOT NULL,"
    "    first_seen TEXT NOT NULL,"
    "    last_seen  TEXT NOT NULL,"
    f"    PRIMARY KEY (run_id, dedup_key)"
    ")"
)
_INDEX_SQL = f"CREATE INDEX IF NOT EXISTS {STORE_INDEX} ON {STORE_TABLE} (dedup_key)"


class CrossSourceDedupStore:
    """Append-only best-effort store for cross-source dedup keys.

    Usage (caller owns lifecycle — creates, passes to pipeline, closes in finally):

        with CrossSourceDedupStore(path, run_id) as store:
            key = store.compute_key(job)
            if store.has_key(key):
                # job is a re-entry, not genuinely new
            store.write(key, job_id)

    - ``run_id``: identity of the run (same as JSONL — ``utcnow_iso`` from CLI)
    - ``written``: write attempts offered (INSERTs; duplicates within run ignored by PK)
    - ``failed``/``error``: forensics of degraded store — pipeline NEVER fails because of store
    """

    def __init__(
        self,
        db_path: Path | str,
        run_id: str,
        seen_at: str | None = None,
        flush_every: int = FLUSH_EVERY,
    ) -> None:
        self.db_path = Path(db_path)
        self.run_id = str(run_id)
        self.seen_at = str(seen_at) if seen_at is not None else utcnow_iso()
        self.flush_every = max(1, int(flush_every))
        self.written = 0
        self.failed = False
        self.error: str | None = None
        self._conn: sqlite3.Connection | None = None
        self._pending = 0

    # -- Public API ---------------------------------------------------------

    def compute_key(self, job: dict[str, Any]) -> str:
        """Compute the deterministic dedup key for a job.

        Priority order:
        1. Anzeigencode/jobcode from raw (strongest cross-source signal)
        2. Oracle site_number normalization (CX# <-> CX_1#)
        3. Company+title+city (fallback, same as cross_source_dedup grouping)
        """
        raw = job.get("raw") if isinstance(job.get("raw"), dict) else {}

        # 1. Anzeigencode / jobcode (RWE case) — strongest signal
        for field in ("anzeigencode", "jobcode", "job_code", "reference_number", "ref_num"):
            val = raw.get(field)
            if val is not None:
                return f"anzeigencode:{str(val).strip().casefold()}"

        # 2. Oracle site_number normalization (TI case)
        source = str(job.get("source") or "").lower()
        if source.startswith("oracle:"):
            url = job.get("url") or ""
            # Extract site_number from Oracle URL: .../sites/CX_1/... or .../sites/CX/...
            # Normalize CX_1 <-> CX (they're the same tenant)
            import re
            match = re.search(r"/sites/([^/]+)/", url)
            if match:
                site = match.group(1).lower()
                # Normalize: cx_1 and cx are the same Oracle tenant
                if site in ("cx_1", "cx"):
                    site = "cx_normalized"
                ext_id = job.get("external_id") or ""
                return f"oracle_site:{site}:{ext_id}"

        # 3. Fallback: company+title+city (same as cross_source_dedup grouping)
        from internship_finder.cross_source_dedup import (
            city_key,
            company_identity,
            canonical_company,
            _de_en_title_key,
            load_company_aliases,
        )
        aliases = load_company_aliases()
        company = canonical_company(job.get("company"), aliases)
        cid = company_identity(company)
        if not cid:
            # No usable company identity — fall back to URL (weakest)
            url = normalize_url(job.get("url"))
            if url:
                return f"url:{url}"
            return f"job_id:{job.get('id', '')}"

        title_key = _de_en_title_key(job.get("title"))
        city = city_key(job.get("location"))
        if not title_key or not city:
            url = normalize_url(job.get("url"))
            if url:
                return f"url:{url}"
            return f"job_id:{job.get('id', '')}"

        return f"company_title_city:{','.join(sorted(cid))}:{title_key}:{city}"

    def has_key(self, dedup_key: str) -> bool:
        """Check if this dedup_key has been seen in ANY previous run."""
        if self.failed or not dedup_key:
            return False
        if self._conn is None and not self._open():
            return False
        assert self._conn is not None
        try:
            row = self._conn.execute(
                f"SELECT 1 FROM {STORE_TABLE} WHERE dedup_key = ? LIMIT 1",
                (dedup_key,),
            ).fetchone()
            return row is not None
        except Exception as exc:  # noqa: BLE001 — best-effort
            self._disable(exc)
            return False

    def write(self, dedup_key: str, job_id: str) -> None:
        """Record that this dedup_key was seen in this run (streaming)."""
        if self.failed or not dedup_key or not job_id:
            return
        if self._conn is None and not self._open():
            return
        assert self._conn is not None
        try:
            self._conn.execute(
                f"INSERT OR IGNORE INTO {STORE_TABLE} "
                "(run_id, dedup_key, job_id, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.run_id, dedup_key, str(job_id), self.seen_at, self.seen_at),
            )
            self.written += 1
            self._pending += 1
            if self._pending >= self.flush_every:
                self._conn.commit()
                self._pending = 0
        except Exception as exc:  # noqa: BLE001 — best-effort
            self._disable(exc)

    def get_history(self, dedup_key: str) -> tuple[str, str] | None:
        """History of a dedup_key: (first_seen, last_seen) across ALL runs."""
        if not dedup_key:
            return None
        path = self.db_path
        if not path.exists():
            return None
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                row = conn.execute(
                    f"SELECT MIN(first_seen), MAX(last_seen) FROM {STORE_TABLE} WHERE dedup_key = ?",
                    (dedup_key,),
                ).fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return None
        if not row or row[0] is None:
            return None
        return (row[0], row[1])

    def close(self) -> None:
        """Flush final + close; idempotent and never raises."""
        if self._conn is None:
            return
        conn, self._conn = self._conn, None
        try:
            conn.commit()
        except Exception as exc:  # noqa: BLE001 — best-effort
            self._disable(exc, conn=conn)
            return
        try:
            conn.close()
        except Exception:  # noqa: BLE001 — close failure irrelevant
            pass

    # -- Internals ----------------------------------------------------------

    def _open(self) -> bool:
        """Open (creating) the database; return False + disable on failure."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(_SCHEMA_SQL)
            conn.execute(_INDEX_SQL)
            conn.commit()
            self._conn = conn
            return True
        except Exception as exc:  # noqa: BLE001 — best-effort
            self._disable(exc)
            return False

    def _disable(
        self,
        exc: BaseException,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Degrade to no-op with forensics — once."""
        if not self.failed:
            self.failed = True
            self.error = f"{type(exc).__name__}: {exc}"
            log.error(
                "cross_source_dedup_store: store degraded (%s); pipeline continues "
                "without cross-run dedup — forensics in error",
                self.error,
            )
        conn = conn if conn is not None else self._conn
        self._conn = None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    # -- Context manager ----------------------------------------------------

    def __enter__(self) -> "CrossSourceDedupStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def load_cross_source_dedup_store(
    path: Path | str | None = None,
    run_id: str | None = None,
) -> CrossSourceDedupStore | None:
    """Factory for the cross-source dedup store (best-effort, never raises).

    Returns ``None`` if store cannot be initialized (degraded).
    """
    target = Path(path) if path is not None else DEFAULT_STORE_PATH
    rid = run_id or utcnow_iso()
    store = CrossSourceDedupStore(target, rid)
    # Test open to catch early failures
    if store._open():
        return store
    return None


def compute_cross_source_dedup_key(job: dict[str, Any]) -> str:
    """Compute the deterministic cross-source dedup key for a job (standalone).

    This is the SAME logic as ``CrossSourceDedupStore.compute_key`` but as a
    pure function for use in ranking_digest.new_postings_diff (F135).

    Priority order:
    1. Anzeigencode/jobcode from raw (strongest cross-source signal)
    2. Oracle site_number normalization (CX# <-> CX_1#)
    3. Company+title+city (fallback, same as cross_source_dedup grouping)
    """
    raw = job.get("raw") if isinstance(job.get("raw"), dict) else {}

    # 1. Anzeigencode / jobcode (RWE case) — strongest signal
    for field in ("anzeigencode", "jobcode", "job_code", "reference_number", "ref_num"):
        val = raw.get(field)
        if val is not None:
            return f"anzeigencode:{str(val).strip().casefold()}"

    # 2. Oracle site_number normalization (TI case)
    source = str(job.get("source") or "").lower()
    if source.startswith("oracle:"):
        url = job.get("url") or ""
        # Extract site_number from Oracle URL: .../sites/CX_1/... or .../sites/CX/...
        # Normalize CX_1 <-> CX (they're the same tenant)
        import re
        match = re.search(r"/sites/([^/]+)/", url)
        if match:
            site = match.group(1).lower()
            # Normalize: cx_1 and cx are the same Oracle tenant
            if site in ("cx_1", "cx"):
                site = "cx_normalized"
            ext_id = job.get("external_id") or ""
            return f"oracle_site:{site}:{ext_id}"

    # 3. Fallback: company+title+city (same as cross_source_dedup grouping)
    from internship_finder.cross_source_dedup import (
        city_key,
        company_identity,
        canonical_company,
        _de_en_title_key,
        load_company_aliases,
    )
    aliases = load_company_aliases()
    company = canonical_company(job.get("company"), aliases)
    cid = company_identity(company)
    if not cid:
        # No usable company identity — fall back to URL (weakest)
        from internship_finder.dedup import normalize_url
        url = normalize_url(job.get("url"))
        if url:
            return f"url:{url}"
        return f"job_id:{job.get('id', '')}"

    title_key = _de_en_title_key(job.get("title"))
    city = city_key(job.get("location"))
    if not title_key or not city:
        from internship_finder.dedup import normalize_url
        url = normalize_url(job.get("url"))
        if url:
            return f"url:{url}"
        return f"job_id:{job.get('id', '')}"

    return f"company_title_city:{','.join(sorted(cid))}:{title_key}:{city}"