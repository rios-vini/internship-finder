"""F70 — dataset_seen: o caderno do universo pos-prefilter (L5).

O estagio dataset (F3) deriva ~5,8M rows do CSV hospedado para ~24k
vagas/dia pos-prefilter (ancora 19/10: 24.526 kept / 23.798 jobs) e
essas vagas NAO entram no lifecycle do ``jobs.db`` (invariante §7.8:
a fonte e efemera, re-derivada a cada run). Este modulo e o CADERNO
delas: um SQLite SEPARADO (``data/dataset_seen.db`` — o ``jobs.db`` e
intocado) com tabela append-only keys-only que responde "esta vaga ja
foi vista antes?" (a pergunta que o ``jobs.db`` nao pode responder
para o universo do dataset) e sustenta serie temporal, drift e "novas
esta semana" (fases futuras; F69 le daqui).

Design (spec F70):

- **Append-only keys-only**: ``(run_id, job_id, first_seen, last_seen)``
  com ``PRIMARY KEY (run_id, job_id)``; gravacao via ``INSERT OR
  IGNORE`` — nenhuma linha e jamais alterada ou removida.
  ``first_seen``/``last_seen`` recebem o ts do run NA INSERCAO (as
  duas colunas carregam o mesmo valor no INSERT); o primeiro/ultimo
  visto REAL de uma vaga deriva por MIN/MAX sobre as linhas dela
  (query servida pelo indice secundario em ``job_id``).
- **Streaming**: o writer grava row a row no ponto pos-prefilter do
  estagio dataset (``_prefilter_slice``), com commit periodico
  (``FLUSH_EVERY``) — o universo NUNCA e materializado em memoria pelo
  caderno e a janela de perda num crash e no maximo um flush.
- **Best-effort TOTAL** (§7.8: caderno, NAO fonte de verdade): nenhuma
  falha do caderno (disco cheio, diretorio ausente, arquivo corrompido)
  derruba ou altera a coleta — o writer se auto-desabilita, loga UMA
  vez e vira no-op; a falha vira forense no registro dataset
  (``seen_error``), greppavel no JSONL.
- **LAZY**: o arquivo so nasce no PRIMEIRO write. Runs com 0 vagas
  validas nao criam arquivo vazio — e testes que mockam o estagio
  (test_f3) nao poluem ``data/``.

O que entra no caderno: todo Job VALIDO do estagio dataset (pos-prefilter
E pos-validacao — rows invalidas, sem company/title/url, nao tem
identidade para anotar). ``job.id`` e a chave
(``<company>|sf_dataset:<ats>:<ats_id>``), mesma identidade do funil.

Volume (ancoras 19/10): ~24k linhas/dia, ~4-5 MB/dia com indice,
~1,2-1,5 GB/ano — documentado na spec e coberto pelo backup diario do
refresh (mesma mecanica/retencao do ``jobs.db``, stem proprio
``dataset_seen-<ts>.db`` em ``data/backups/``).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from internship_finder.metrics import utcnow_iso

log = logging.getLogger(__name__)

# Caminho default do caderno, relativo ao cwd do run (mesma convencao
# do ``data/collection_metrics.jsonl`` do CLI: producao roda na raiz do
# repo). O ``jobs.db`` (lifecycle) e OUTRO arquivo, nunca aberto aqui.
SEEN_DB_PATH = Path("data/dataset_seen.db")

SEEN_TABLE = "dataset_seen"
SEEN_INDEX = "dataset_seen_job_id"

# Commits periodicos do writer: bounded-loss num crash (<= um flush de
# linhas do run corrente) + write lock curto. 24k/dia -> ~5 commits/run.
FLUSH_EVERY = 5000

# Schema F70 (literal da spec): keys-only, append-only, PK (run_id, job_id).
_SCHEMA_SQL = (
    f"CREATE TABLE IF NOT EXISTS {SEEN_TABLE} (\n"
    "    run_id     TEXT NOT NULL,\n"
    "    job_id     TEXT NOT NULL,\n"
    "    first_seen TEXT NOT NULL,\n"
    "    last_seen  TEXT NOT NULL,\n"
    "    PRIMARY KEY (run_id, job_id)\n"
    ")"
)
# A query importante ("esta vaga ja foi vista antes?") filtra por job_id
# sem a run — sem este indice ela seria um scan da tabela inteira.
_INDEX_SQL = (
    f"CREATE INDEX IF NOT EXISTS {SEEN_INDEX} ON {SEEN_TABLE} (job_id)"
)


class DatasetSeenWriter:
    """Writer append-only best-effort do caderno (context manager).

    Uso (o chamador e dono do ciclo de vida — cria, passa ao estagio
    dataset, fecha no finally, le as stats para o registro):

        with DatasetSeenWriter(path, run_id) as seen:
            seen.write(job_id)          # nunca levanta

    - ``run_id``: identidade do run (a mesma do JSONL — ``utcnow_iso``
      do CLI). ``seen_at`` default: ts UTC do momento da criacao do
      writer (inicio do estagio) — e o valor gravado em
      first_seen/last_seen de TODAS as linhas do run.
    - ``written``: tentativas de gravacao pos-validacao (INSERTs
      oferecidos; duplicatas dentro do run sao ignoradas pela PK).
    - ``failed``/``error``: forenses do writer degradado — o estagio
      NAO falha por causa do caderno, apenas reporta.
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

    # -- API -------------------------------------------------------------

    def write(self, job_id: str) -> None:
        """Grava ``(run_id, job_id, ts, ts)`` — streaming, nunca levanta.

        Primeiro write abre o banco e cria o schema se ausente (LAZY —
        o construtor nao toca disco). Qualquer falha: log UMA vez,
        writer auto-desabilita (no-op para sempre) — o caderno nunca
        derruba o estagio (invariante §7.8).
        """
        if self.failed or not job_id:
            return
        if self._conn is None and not self._open():
            return
        assert self._conn is not None  # garantido por _open()
        try:
            self._conn.execute(
                f"INSERT OR IGNORE INTO {SEEN_TABLE} "
                "(run_id, job_id, first_seen, last_seen) "
                "VALUES (?, ?, ?, ?)",
                (self.run_id, str(job_id), self.seen_at, self.seen_at),
            )
            self.written += 1
            self._pending += 1
            if self._pending >= self.flush_every:
                self._conn.commit()
                self._pending = 0
        except Exception as exc:  # noqa: BLE001 — caderno e best-effort
            self._disable(exc)

    def close(self) -> None:
        """Flush final + fecha; idempotente e nunca levanta."""
        if self._conn is None:
            return
        conn, self._conn = self._conn, None
        try:
            conn.commit()
        except Exception as exc:  # noqa: BLE001 — best-effort TOTAL
            self._disable(exc, conn=conn)
            return
        try:
            conn.close()
        except Exception:  # noqa: BLE001 — fechar falho e irrelevante
            pass

    # -- internos ---------------------------------------------------------

    def _open(self) -> bool:
        """Abre (criando) o banco; devolve False + desabilita se falhar."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(_SCHEMA_SQL)
            conn.execute(_INDEX_SQL)
            conn.commit()
            self._conn = conn
            return True
        except Exception as exc:  # noqa: BLE001 — caderno e best-effort
            self._disable(exc)
            return False

    def _disable(
        self,
        exc: BaseException,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """Degrada o writer para no-op com forense — uma unica vez."""
        if not self.failed:
            self.failed = True
            self.error = f"{type(exc).__name__}: {exc}"
            log.error(
                "dataset_seen: caderno degradado (%s); o estagio segue "
                "sem o caderno — registro dataset carrega seen_error",
                self.error,
            )
        conn = conn if conn is not None else self._conn
        self._conn = None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — best-effort TOTAL
                pass

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> "DatasetSeenWriter":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def job_seen_history(
    db_path: Path | str,
    job_id: str,
) -> tuple[str, str] | None:
    """Historico de uma vaga no caderno: ``(first_seen, last_seen)``.

    A query importante da spec — "esta vaga ja foi vista antes?" —
    respondida por MIN/MAX sobre as linhas do ``job_id`` (servida pelo
    indice secundario). ``None`` = nunca vista (ou caderno ausente):
    leitura do caderno e tolerante por design — arquivo inexistente,
    tabela ausente ou banco ilegivel NUNCA derrubam quem consulta
    (fases futuras — F69 e derivadas — leem daqui).
    """
    path = Path(db_path)
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                f"SELECT MIN(first_seen), MAX(last_seen) FROM {SEEN_TABLE} "
                "WHERE job_id = ?",
                (str(job_id),),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:  # sem tabela / banco ilegivel -> nunca vista
        return None
    if not row or row[0] is None:
        return None
    return (row[0], row[1])
