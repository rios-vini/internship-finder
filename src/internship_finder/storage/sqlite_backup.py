"""Backup simples e seguro do ``jobs.db`` (P3) — snapshot via backup API do sqlite3.

O historico SQLite (``data/jobs.db``, first_seen/last_seen/active/archived) e
acumulativo e NAO rotaciona a cada run — por isso merece backup proprio,
independente do archive de JSONs (``data/archive/``). Este modulo implementa o
mecanismo minimo:

- **Mecanismo**: ``sqlite3.Connection.backup()`` (Online Backup API do SQLite,
  stdlib) com a origem aberta em modo **read-only** (``file:...?mode=ro``). A
  API copia o banco pagina a pagina obtendo um snapshot CONSISTENTE mesmo se a
  origem estiver em uso (WAL) — copiar o arquivo cru poderia capturar um estado
  intermediario de escrita. A origem nunca e escrita pela rotina de backup.
- **Artefato standalone**: apos o backup, ``PRAGMA journal_mode=DELETE`` no
  destino consolida qualquer estado WAL no arquivo principal e remove os
  sidecars ``-wal``/``-shm`` — o backup final e um unico arquivo SQLite
  independente, utilizavel com qualquer leitor e restauravel com um ``cpy``.
- **Atomicidade**: o backup e escrito num arquivo temporario NO MESMO
  diretorio (mesmo filesystem) e so entra no nome final via ``os.replace``
  (atomico). Falha em qualquer ponto -> temporario + sidecars removidos; um
  backup nunca fica pela metade nem substitui um backup valido anterior.
- **Validacao minima**: ``PRAGMA quick_check`` no arquivo temporario ANTES do
  ``os.replace`` (checagem de integridade de paginas; mais barata que
  ``integrity_check`` integral, suficiente para validar o artefato).
- **Nomes**: ``jobs-YYYYMMDDTHHMMSSZ.db`` (UTC, mesmo formato de timestamp dos
  archives) — permite multiplos backups com historico ordenavel.
- **Retencao simples**: ``cleanup_backups`` remove backups mais antigos que N
  dias (N=0 desliga); nomes fora do formato sao preservados com aviso. Sem
  lifecycle complexo (deliberado): mesma politica do archive, documentada.

Falhas NUNCA tocam a origem: levantam excecao para o chamador decidir como
reportar (o ``refresh_daily`` loga e inclui a linha ``⚠️ Backup ... falhou`` na
mensagem do Telegram; nunca derruba o run nem altera o exit code da coleta).
"""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("internship_finder.storage.backup")

# Diretorio default dos backups, relativo ao diretorio do banco: ``data/backups``
# (jobs.db vive em data/). Coerente com data/archive/: ambos sob data/.
BACKUP_DIR_NAME = "backups"

# Formato do timestamp no nome do backup (UTC) — igual ao dos archives
# (refresh_daily.ARCHIVE_TS_FORMAT) para leitura humana e ordenacao.
BACKUP_TS_FORMAT = "%Y%m%dT%H%M%SZ"

# Modo do arquivo de backup: mesmo 0644 dos demais artefatos de data/
# (mkstemp cria 0600 — ajustamos antes do os.replace).
_BACKUP_MODE = 0o644


def backup_filename(ts: str) -> str:
    """Nome do arquivo de backup para um timestamp (``jobs-<ts>.db``)."""
    return f"jobs-{ts}.db"


def _parse_backup_ts(name: str) -> datetime | None:
    """Timestamp UTC de um nome de backup (``jobs-YYYYMMDDTHHMMSSZ.db``).

    None se o nome nao estiver no formato esperado (defensivo: esses arquivos
    sao preservados pela retencao, nunca apagados por engano).
    """
    if not name.startswith("jobs-") or not name.endswith(".db"):
        return None
    try:
        return datetime.strptime(
            name[len("jobs-"):-len(".db")], BACKUP_TS_FORMAT
        ).replace(tzinfo=UTC)
    except ValueError:
        return None


def _validate(db_path: Path) -> None:
    """Checagem minima de integridade: ``PRAGMA quick_check`` == ``"ok"``."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        result = conn.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        conn.close()
    if result != "ok":
        raise sqlite3.DatabaseError(f"backup invalido: quick_check = {result!r}")


def backup_jobs_db(
    db_path: Path | str,
    backup_dir: Path | str | None = None,
    ts: str | None = None,
) -> Path:
    """Snapshot consistente e standalone de ``db_path`` em ``backup_dir``.

    Devolve o caminho do backup criado (``backup_dir/jobs-<ts>.db``). O
    ``ts`` default e o agora em UTC (formato ``YYYYMMDDTHHMMSSZ``); injetar
    ``ts`` e usado por testes.

    - origem aberta read-only (o backup API le a origem; nada nela e escrito);
    - artefato final em modo ``journal_mode=DELETE`` (arquivo unico, sem
      sidecars WAL — portavel e restauravel por copia simples);
    - escrita atomica: temporario no mesmo filesystem + ``os.replace``;
    - falha: excecao propagada e nenhum arquivo temporario/residual fica no
      diretorio (o banco principal nunca e tocado).
    """
    db_path = Path(db_path)
    if backup_dir is None:
        backup_dir = db_path.parent / BACKUP_DIR_NAME
    else:
        backup_dir = Path(backup_dir)
    if not db_path.exists():
        raise FileNotFoundError(f"sem banco para backup: {db_path}")
    ts = ts or datetime.now(UTC).strftime(BACKUP_TS_FORMAT)
    backup_dir.mkdir(parents=True, exist_ok=True)
    final = backup_dir / backup_filename(ts)

    # Temporario no MESMO diretorio do destino (mesmo filesystem -> os.replace
    # atomico). Prefixo pontilhado: nao polui a listagem do diretorio.
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{backup_filename(ts)}.", suffix=".tmp", dir=backup_dir)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(str(tmp))
            try:
                src.backup(dst)
                # Consolida o WAL herdado do header da origem e deixa o
                # arquivo em journal_mode=DELETE: backup = 1 arquivo, sem
                # sidecars, independente da origem.
                dst.execute("PRAGMA journal_mode=DELETE")
            finally:
                dst.close()
        finally:
            src.close()
        _validate(tmp)
        os.chmod(tmp, _BACKUP_MODE)
        os.replace(tmp, final)
    except BaseException:
        for leftover in (tmp, Path(str(tmp) + "-wal"), Path(str(tmp) + "-shm")):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:  # pragma: no cover — cleanup best-effort
                log.warning("nao foi possivel remover temporario %s", leftover)
        raise
    log.info("backup do jobs.db: %s -> %s (%d bytes)",
             db_path, final, final.stat().st_size)
    return final


def cleanup_backups(
    backup_dir: Path | str,
    retention_days: int,
    now: datetime | None = None,
) -> list[Path]:
    """Retencao simples: remove backups mais antigos que ``retention_days``.

    ``0`` desliga a limpeza. Nomes fora do formato ``jobs-YYYYMMDDTHHMMSSZ.db``
    sao preservados (defensivo) com aviso. Devolve a lista dos removidos.
    Diretorio inexistente -> sem crash, nada a remover. Espelha a politica do
    archive (``cleanup_archive`` do refresh_daily) — sem lifecycle complexo.
    """
    removed: list[Path] = []
    backup_dir = Path(backup_dir)
    if retention_days <= 0:
        log.info("backup cleanup: retencao desligada (%d dias); nada a limpar",
                 retention_days)
        return removed
    if not backup_dir.exists():
        log.info("backup cleanup: %s nao existe; nada a limpar", backup_dir)
        return removed
    now = now or datetime.now(UTC)
    for child in sorted(backup_dir.iterdir()):
        if not child.is_file():
            continue
        ts = _parse_backup_ts(child.name)
        if ts is None:
            log.warning("backup cleanup: %s fora do formato %s; preservado",
                        child.name, f"jobs-<ts>.db ({BACKUP_TS_FORMAT})")
            continue
        age_days = (now - ts).total_seconds() / 86400.0
        if age_days >= retention_days:
            child.unlink(missing_ok=True)
            removed.append(child)
            log.info("backup cleanup: removido %s (idade %.1f dias)",
                     child.name, age_days)
    if not removed:
        log.info("backup cleanup: nada a limpar")
    return removed