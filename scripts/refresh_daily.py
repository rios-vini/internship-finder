#!/usr/bin/env python3
"""Refresh diario da coleta + alertas (Telegram) — P2 #17.

Rotina standalone de producao: faz a COLETA REAL do registry (subprocesso do
CLI), avalia o health sobre o JSONL atualizado (reusa ``build_health_report``
de ``src/internship_finder/health.py`` — sem camada nova) e envia alerta via
Telegram SOMENTE em anomalia (anti-spam). Uso:

    .venv/bin/python scripts/refresh_daily.py                 # producao
    .venv/bin/python scripts/refresh_daily.py --dry-run       # demonstrativo, sem rede/data
    .venv/bin/python scripts/refresh_daily.py --always-notify # digest diario (documentado, nao default)

Fluxo:

1. **Backup/rotacao** — copia os arquivos reais de ``data/``
   (``jobs.json``/``.csv``, ``eligible_jobs.json``/``.csv`` e
   ``collection_metrics.jsonl``) para ``data/archive/<timestamp>/`` ANTES de
   rodar. Preserva o snapshot anterior (rollback = copiar de volta; o
   ``run_info.json`` gravado no archive registra o run que o substituiu).
   Copia, nao move: a origem fica intacta ate o CLI gravar por cima.
1b. **Retencao do archive** — ``cleanup_archive`` apaga ``data/archive/<ts>``
   cujo timestamp no nome (formato ``YYYYMMDDTHHMMSSZ``) seja mais antigo
   que ``--retention-days`` dias (default 14; ``0`` desliga). Roda APOS a
   rotacao; loga o que removeu (ou "nada a limpar").
2. **Coleta real** — subprocesso ``python -m internship_finder.cli
   --registry --timeout <T> --sqlite data/jobs.db`` (cwd = raiz do repo;
   env = ambiente do chamador + ``PYTHONPATH=src``; stdout/stderr herdados —
   caem no log do cron). ``--sqlite`` persiste first_seen/last_seen/active/
   archived no ``data/jobs.db`` (idempotente; falha de escrita nunca derruba
   a coleta; o ``jobs.db`` NAO e rotacionado — historico acumulativo). Exit
   0 = ok; 1 = nada eligible/coletado; 2 = parcial com falhas reais (dados
   salvos). O exit code final do refresh e o do subprocesso (P1.3): 0/1/2,
   ou 124 quando o teto de tempo e estourado — o cron/systemd distingue
   sucesso de falha.
2b. **Backup do jobs.db (P3)** — snapshot consistente via backup API do
   sqlite3 (stdlib) para ``data/backups/jobs-<ts>.db`` (artefato standalone,
   sem sidecars WAL); retencao simples ``--backup-retention-days`` (default
   14, 0 desliga) aplicada em seguida. Falha NUNCA derruba o run nem muda o
   exit code: e logada e (se houver envio) entra na mensagem como
   ``⚠️ Backup do jobs.db falhou: ...``.
2c. **Publicacao GitHub Pages (Fase 1, opcional via ``--pages-dir``)** —
   quando informado, apos coleta/health o ranking do run e publicado na
   branch ``gh-pages`` (reusa ``scripts/interface.py`` para o HTML,
   verificacao de seguranca, escrita atomica, commit+push — ver
   ``scripts/publish_pages.py``). Gate: a decisao UNICA de publicacao parcial
   segura vive em ``publish_pages.publication_allowed`` (auditoria 23/09) —
   publica com ``eligible > 0`` em runs ok (exit 0) OU parciais com falhas
   perifericas de fontes individuais (exit 2); dataset vazio (exit 1), run
   truncado (exit 124) ou exit inesperado nunca publicam (a pagina anterior
   permanece). Falha NUNCA derruba o run: entra na mensagem como
   ``⚠️ Publicação GitHub Pages falhou: ...``.
3. **Health** — ``build_health_report`` sobre o conteudo COMPLETO do JSONL
   apos o run (defensivo: malformados nunca derrubam). Os registros do run
   atual sao isolados por snapshot de linhas (antes x depois), sem adivinhar
   run_id.
4. **Alerta** — 1 mensagem por run, alertas deduplicados por fonte.
   Dispara quando: exit != 0 (run falhou/parcial), OU o relatorio tem alertas
   (queda brusca / erro recorrente), OU ``--always-notify`` (digest diario,
   nao default). Sem anomalia -> sem envio. Credenciais em ``.env``
   (gitignored): ``TELEGRAM_BOT_TOKEN`` e ``TELEGRAM_CHAT_ID``; sem token ->
   aviso no log e NAO envia (nunca crasha).
4b. **Disco** — mede o uso do filesystem que contem ``data/``
   (``shutil.disk_usage``) apos a coleta; acima de 80% loga warning e a
   mensagem do Telegram ganha a linha ``⚠️ Disco: N% usado`` (esse aviso
   tambem dispara o envio, mesmo sem anomalia).

Flags:

- ``--dry-run``: sem rede, sem escrever em ``data/`` — usa um tempdir com
  dados sinteticos (rotacao + limpeza + backup do jobs.db + health +
  mensagem validados; a mensagem e impressa, nada e enviado). Exit 0.
- ``--config PATH``: arquivo de configuracao (default ``.env`` na raiz;
  formato ``CHAVE=VALOR``, ``#`` comenta).
- ``--always-notify``: envia o resumo mesmo sem anomalia (digest; documentado,
  nao e o default).
- ``--timeout N``: timeout por scraper passado ao CLI (default 60).
- ``--max-collection-secs N``: teto total do subprocesso de coleta (default
  5400 = 90 min; a coleta completa de 101 empresas e ~10-30 min em media
  (mais lenta se muitas falhas de timeout/erro por tenant). Estourado:
  mensagem "run falhou (timeout do subprocesso)".
- ``--retention-days N``: retencao do archive em dias (default 14; ``0`` =
  desligado; negativo rejeitado com erro claro via argparse).
- ``--backup-retention-days N``: retencao dos backups do jobs.db em dias
  (default 14; ``0`` = desligado; mesma politica do archive).

Concorrencia: o cron usa ``flock -n`` (ver README) para nunca sobrepor runs;
este script nao reimplementa lock.

Limitação conhecida (documentada em MASTER_PLAN/README): o arquivo JSONL
acumula lixo historico de validacao (registros ``type: tenant`` de mocks, sem
run_id de coleta real; ex.: ``smartrecruiters:other`` 70x ``error``). O health
e defensivo (malformados pulados) mas o lixo VALIDO entra nas contagens por
fonte — uma fonte que so tem lixo emitira "erro recorrente" em TODO run ate o
JSONL ser limpo (1 alerta por fonte por run; nao ha dedup entre runs).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from internship_finder.health import build_health_report  # reuso — sem camada nova
from internship_finder.storage.sqlite_backup import (  # backup do jobs.db (P3)
    BACKUP_DIR_NAME,
    backup_jobs_db,
    cleanup_backups,
)
import publish_pages  # publicacao do ranking em GitHub Pages (Fase 1)
import ranking_digest  # digest do ranking no Telegram (Fase 2)

log = logging.getLogger("refresh_daily")

# Arquivos de data/ rotacionados a cada run (fonte de dados + metricas).
# O ``jobs.db`` do SQLite NAO entra aqui de proposito: e historico
# acumulativo (first_seen/last_seen/active/archived), nao snapshot por run
# (data/ e gitignored).
ROTATE_FILES = [
    "jobs.json",
    "jobs.csv",
    "eligible_jobs.json",
    "eligible_jobs.csv",
    "collection_metrics.jsonl",
]

# Nome dos archives: YYYYMMDDTHHMMSSZ (UTC).
ARCHIVE_TS_FORMAT = "%Y%m%dT%H%M%SZ"

# Aviso de disco: percentual de uso do filesystem de data/ acima do qual o
# refresh loga warning e inclui a linha "Disco" na mensagem do Telegram.
DISK_WARN_PCT = 80

# Limite de texto do sendMessage do Telegram (4096 caracteres). O digest do
# ranking (Fase 2) e anexado ao fim; em runs com MUITAS anomalias a mensagem
# base ja consome quase todo o limite — o digest vira 1 linha compacta com o
# link do ranking completo (nunca perde a saida para o ranking, e o envio
# nunca falha por tamanho).
TELEGRAM_MAX_LEN = 4096

# Retencao default do archive em dias (--retention-days).
DEFAULT_RETENTION_DAYS = 14

# Retencao default dos backups do jobs.db em dias (--backup-retention-days).
# Mesma politica do archive: simples, documentada, sem lifecycle complexo.
DEFAULT_BACKUP_RETENTION_DAYS = 14

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Nomes das chaves aceitas no .env.
ENV_TOKEN = "TELEGRAM_BOT_TOKEN"
ENV_CHAT = "TELEGRAM_CHAT_ID"


def utcnow_iso() -> str:
    """Timestamp UTC atual em ISO 8601 (mesmo formato das metricas)."""
    return datetime.now(UTC).isoformat()


def repo_root() -> Path:
    """Raiz do repositorio (este script vive em ``scripts/``)."""
    return Path(__file__).resolve().parents[1]


# --- config ----------------------------------------------------------------

def load_env_config(path: Path | str) -> dict:
    """Le ``CHAVE=VALOR`` de um arquivo .env simples (``#`` comenta, linhas
    em branco puladas). Arquivo inexistente/ilegivel -> dict vazio (o envio
    vira aviso, nunca crasha)."""
    config: dict = {}
    path = Path(path)
    if not path.exists():
        log.warning("config %s nao encontrado; sem credenciais de Telegram", path)
        return config
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.warning("config %s ilegivel (%s); sem credenciais de Telegram", path, exc)
        return config
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        config[key.strip()] = value.strip().strip('"').strip("'")
    return config


# --- rotacao ---------------------------------------------------------------

def rotate(data_dir: Path, archive_root: Path, ts: str) -> Path:
    """Copia os arquivos reais de ``data_dir`` para ``archive_root/<ts>/``.

    Copia (nao move): a origem fica intacta ate o CLI da coleta gravar por
    cima. Arquivos ausentes sao pulados com aviso. Devolve o diretorio do
    archive. Rollback = copiar de volta o conteudo de ``archive_root/<ts>/``.
    """
    archive_dir = archive_root / ts
    archive_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in ROTATE_FILES:
        src = data_dir / name
        if not src.exists():
            log.warning("rotacao: %s ausente (primeiro run?); pulado", src)
            continue
        dst = archive_dir / name
        shutil.copy2(src, dst)
        copied += 1
        log.info("rotacao: backup %s -> %s", src, dst)
    log.info("rotacao: %d arquivos arquivados em %s", copied, archive_dir)
    return archive_dir


def _parse_archive_ts(name: str) -> datetime | None:
    """Timestamp UTC de um nome de archive (``YYYYMMDDTHHMMSSZ``); None se
    o nome nao estiver no formato esperado."""
    try:
        return datetime.strptime(name, ARCHIVE_TS_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def cleanup_archive(archive_root: Path, retention_days: int,
                    now: datetime | None = None) -> list[Path]:
    """Aplica a retencao: apaga ``archive_root/<ts>`` mais antigos que
    ``retention_days`` dias (``0`` = desligado). Nomes fora do formato
    ``YYYYMMDDTHHMMSSZ`` sao preservados (defensivo) com aviso. Devolve a
    lista dos diretorios removidos (log/testes). Chamada APOS a rotacao.
    """
    removed: list[Path] = []
    if retention_days <= 0:
        log.info("limpeza: retencao desligada (--retention-days %d); nada a limpar",
                 retention_days)
        return removed
    if not archive_root.exists():
        log.info("limpeza: %s nao existe; nada a limpar", archive_root)
        return removed
    now = now or datetime.now(UTC)
    for child in sorted(archive_root.iterdir()):
        if not child.is_dir():
            continue
        ts = _parse_archive_ts(child.name)
        if ts is None:
            log.warning("limpeza: %s fora do formato %s; preservado",
                        child.name, ARCHIVE_TS_FORMAT)
            continue
        age_days = (now - ts).total_seconds() / 86400.0
        if age_days >= retention_days:
            shutil.rmtree(child)
            removed.append(child)
            log.info("limpeza: removido %s (idade %.1f dias)", child.name, age_days)
    if not removed:
        log.info("limpeza: nada a limpar")
    return removed


def _non_negative_int(value: str) -> int:
    """Tipo argparse: inteiro >= 0 (negativo rejeitado com erro claro)."""
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"valor invalido: {value!r} (esperado inteiro nao negativo)")
    if parsed < 0:
        raise argparse.ArgumentTypeError(
            f"retencao negativa ({parsed}) nao faz sentido; use 0 para desligar")
    return parsed


def disk_usage_pct(path: Path) -> int | None:
    """Percentual de uso (0-100, arredondado) do filesystem que contem
    ``path``; None se nao der para medir (diretorio inexistente/inacessivel).
    """
    try:
        total, used, _free = shutil.disk_usage(path)
    except OSError as exc:
        log.warning("disco: uso de %s inacessivel (%s)", path, exc)
        return None
    if total <= 0:
        return None
    return int(round(used / total * 100))


# --- coleta via subprocesso ------------------------------------------------

def collection_command(timeout: float) -> list[str]:
    """Linha de comando da coleta real (subprocesso, cwd = raiz do repo).

    ``--sqlite data/jobs.db``: persistencia first_seen/last_seen/active/
    archived (P1 #5); a flag e idempotente e falha de escrita nunca derruba
    a coleta. O ``jobs.db`` nao e rotacionado (historico acumulativo).
    """
    return [
        sys.executable, "-m", "internship_finder.cli",
        "--registry",
        "--timeout", str(timeout),
        "--sqlite", "data/jobs.db",
    ]


def run_collection(command: list[str], cwd: Path, max_secs: float) -> subprocess.CompletedProcess:
    """Roda a coleta como subprocesso, herdando stdout/stderr (cai no log do
    cron). Erro/estouro do teto vira ``timeout`` no processo retornado.

    O env herda o ambiente do chamador (ex.: ``INTERNSHIP_FINDER_GEOCODING=1``
    definido no cron precisa chegar ao CLI) e sobrescreve apenas o que o run
    exige (PYTHONPATH=src e PATH fixo).
    """
    env = {**os.environ, "PYTHONPATH": str(cwd / "src"), "PATH": "/usr/bin:/bin"}
    log.info("coleta: subprocesso %s (cwd=%s)", " ".join(command), cwd)
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            timeout=max_secs,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.error("coleta: subprocesso estourou o teto de %.0fs", max_secs)
        return subprocess.CompletedProcess(command, 124)  # 124 = timeout (convencao)


# --- metricas do run -------------------------------------------------------

def _count_lines(path: Path) -> int:
    """Numero de linhas de um arquivo (0 se ausente)."""
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def read_new_records(path: Path, skip_lines: int) -> list[dict]:
    """Le as linhas de ``path`` a partir de ``skip_lines`` (snapshot antes x
    depois do run). Linhas malformadas sao puladas com aviso — nunca derrubam.
    """
    records: list[dict] = []
    if skip_lines < 0:
        skip_lines = 0
    with path.open(encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            if idx < skip_lines:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                log.warning("registro %d inparseavel; pulado", idx)
                continue
            if isinstance(rec, dict):
                records.append(rec)
    return records


def summarize_run(records: list[dict]) -> dict:
    """Resumo do run atual (registros novos do JSONL) para a mensagem.

    ``type: run`` -> totais do funil (total_collected/filtered/dedup_removed/
    eligible + run_id/timestamp). ``type: tenant`` -> contagem por status,
    com ``(source, company, error_code)`` para timeout/error (``company`` e a
    empresa do registro QUE FALHOU — auditoria 23/09: tenants sao
    compartilhados, atribuir pelo primeiro company do source apontava a
    empresa errada; ``UNKNOWN`` quando o registro antigo nao tem codigo).
    """
    summary: dict = {
        "run_id": None,
        "timestamp": None,
        "total_collected": None,
        "filtered": None,
        "dedup_removed": None,
        "eligible": None,
        "ok": {"count": 0, "collected": 0},
        "empty": 0,
        "skipped": 0,
        "not_found": 0,
        "timeout": [],
        "error": [],
        "source_names": {},  # source -> company do registro (nome amigavel, P3 #35)
    }
    for rec in records:
        rtype = rec.get("type")
        if rtype == "run":
            summary["run_id"] = rec.get("run_id") or summary["run_id"]
            summary["timestamp"] = rec.get("timestamp") or summary["timestamp"]
            for key in ("total_collected", "filtered", "dedup_removed", "eligible"):
                value = rec.get(key)
                if isinstance(value, (int, float)):
                    summary[key] = int(value)
        elif rtype == "tenant":
            status = rec.get("status")
            source = rec.get("source") or "?"
            company = rec.get("company") or ""
            code = rec.get("error_code")
            if source not in summary["source_names"]:
                summary["source_names"][source] = rec.get("company")
            if status == "ok":
                summary["ok"]["count"] += 1
                collected = rec.get("collected")
                if isinstance(collected, (int, float)):
                    summary["ok"]["collected"] += int(collected)
            elif status == "empty":
                summary["empty"] += 1
            elif status == "skipped":
                summary["skipped"] += 1
            elif status == "not_found":
                summary["not_found"] += 1
            elif status == "timeout":
                summary["timeout"].append((source, company, code or "UNKNOWN"))
            elif status == "error":
                summary["error"].append((source, company, code or "UNKNOWN"))
    return summary


def _fmt(n: int) -> str:
    """Numero no formato pt-BR (37.373), legivel no Telegram."""
    return f"{n:,}".replace(",", ".")


# --- mensagem --------------------------------------------------------------

# Traducao didatica dos codigos de erro estruturados (P1 #7 / errors.py) —
# a UX do alerta (P3 #35) fala portugues, nao codigo.
ERROR_CODE_TEXT = {
    "TIMEOUT": "sem resposta a tempo (timeout)",
    "FETCH_ERROR": "erro ao buscar vagas",
    "NORMALIZATION_ERROR": "erro ao normalizar dados",
    "UNKNOWN": "erro desconhecido",
}


def _error_text(code: str | None) -> str:
    """Traduz um codigo de erro estruturado em linguagem natural."""
    if not code:
        return "erro"
    return ERROR_CODE_TEXT.get(code, f"erro [{code}]")


def _friendly_source(source: str, source_names: dict,
                     company: str | None = None) -> str:
    """Nome amigavel da fonte: ``'Empresa (source)'``.

    Auditoria 23/09 (tenant compartilhado): quando a chamada conhece a
    empresa exata do registro (``company`` — vaga que falhou ou serie do
    alerta), ELA tem prioridade sobre ``source_names`` (que guarda o
    PRIMEIRO company visto no source e pode apontar outra empresa que
    compartilha o mesmo tenant ATS — ex.: erro da SAP reportado como BMW
    em ``successfactors:jobs``). Sem company conhecida, mantem o
    comportamento antigo (primeiro company do run ou o source cru).
    """
    if company:
        return f"{company} ({source})"
    name = (source_names or {}).get(source)
    return f"{name} ({source})" if name else source


def build_message(
    summary: dict,
    report_alerts: list[dict],
    exit_code: int,
    *,
    always_notify: bool = False,
    disk_pct: int | None = None,
    backup_error: str | None = None,
    publish_error: str | None = None,
    digest_lines: list[str] | None = None,
) -> str | None:
    """Monta a mensagem de alerta/digest; ``None`` = nada a enviar (anti-spam:
    sem anomalia, sem falha e sem ``--always-notify``, nao envia).

    Formato didatico (P3 #35, 07/09): status em linguagem natural ("X de Y
    fontes falharam"), nomes amigaveis de empresa, codigos de erro traduzidos
    e reincidencia ("recorrente ha N runs"). Auditoria 23/09 (item 3): cada
    falha e atribuida a empresa do REGISTRO QUE FALHOU (identidade
    ``(source, company)``), nao ao primeiro company do source — tenants
    compartilhados (ex.: ``successfactors:jobs`` = SAP e BMW) nao trocam mais
    de empresa. ``disk_pct``: percentual de uso do filesystem de ``data/``;
    quando maior que ``DISK_WARN_PCT`` a mensagem ganha a linha
    ``⚠️ Disco: N% usado`` e o aviso tambem dispara o envio. Chamadores passam
    o valor medido (ou None). Alertas deduplicados por fonte (1 por fonte por
    run)."""
    alerts = sorted(report_alerts, key=lambda a: (a.get("source", ""), a.get("type", "")))
    disk_warning = disk_pct is not None and disk_pct > DISK_WARN_PCT
    if not (always_notify or exit_code != 0 or alerts or disk_warning
            or backup_error or publish_error):
        return None

    source_names = summary.get("source_names") or {}
    lines: list[str] = ["📊 internship-finder · refresh diário"]
    lines.append(f"run {summary.get('run_id') or '-'}")
    lines.append("")

    ok = summary.get("ok", {})
    # Falhas do run como (source, company, code) — company do registro que
    # falhou (item 3 da auditoria 23/09). Registros antigos sem company
    # (tupla de 2) caem em "" e mantem o nome amigavel do source.
    def _failure_tuple(item):
        src, company, code = item[0], "", "UNKNOWN"
        if len(item) >= 3:
            src, company, code = item[0], item[1] or "", item[2] or "UNKNOWN"
        elif len(item) == 2:
            src, code = item[0], item[1] or "UNKNOWN"
        return src, company, code

    failures = list(dict.fromkeys(
        tuple(f) for f in (
            list(summary.get("timeout", [])) + list(summary.get("error", [])))))
    failures = [_failure_tuple(f) for f in failures]
    n_fail = len(failures)
    n_sources = (ok.get("count", 0) + summary.get("empty", 0) + n_fail
                 + summary.get("skipped", 0) + summary.get("not_found", 0))

    if exit_code == 0 and n_fail == 0:
        lines.append("✅ Coleta concluída")
    elif exit_code == 1:
        lines.append("⚠️ Nenhuma vaga elegível encontrada (exit 1)")
    else:
        lines.append(f"⚠️ Coleta parcial: {n_fail} de {n_sources} fontes falharam")
        if exit_code == 124:
            lines.append("  Detalhe: o run estourou o tempo máximo (exit 124)")
        elif exit_code not in (0, 2):
            lines.append(f"  Detalhe: falha de execução do run (exit {exit_code})")

    total = summary.get("total_collected")
    if total is not None:
        eligible = summary.get("eligible")
        dedup = summary.get("dedup_removed") or 0
        lines.append(
            f"Vagas: {_fmt(total)} brutas → {_fmt(eligible or 0)} elegíveis"
            + (f" ({_fmt(dedup)} duplicata removida)" if dedup == 1
               else f" ({_fmt(dedup)} duplicatas removidas)" if dedup else "")
        )
    if n_sources:
        lines.append(
            f"Fontes: {ok.get('count', 0)} ok ({_fmt(ok.get('collected', 0))} vagas)"
            f" · {summary.get('empty', 0)} sem vagas"
            f" · timeout {len(summary.get('timeout', []))}"
            f" · erro {len(summary.get('error', []))}"
            f" · puladas {summary.get('skipped', 0)}"
            f" · sem tenant {summary.get('not_found', 0)}"
        )

    # Problemas detectados: alertas do health + falhas do run, 1 por serie
    # (source, company) (anti-spam; auditoria 23/09, item 3): dois companies
    # no mesmo source sao problemas DIFERENTES e aparecem separados, cada um
    # com o proprio nome. Alertas recurring/regression da MESMA serie ganham
    # anotacao na propria linha de falha (padrao do recurring existente);
    # alertas de outras series renderizam linha propria.
    recurring_alerts = [a for a in alerts if a.get("type") == "recurring_error"]
    regression_alerts = [a for a in alerts if a.get("type") == "regression"]
    recurring_by_key = {
        (a.get("source") or "?", a.get("company") or ""): a
        for a in recurring_alerts
    }
    regression_by_key = {
        (a.get("source") or "?", a.get("company") or ""): a
        for a in regression_alerts
    }

    def _recurring_for(src: str, company: str):
        rec = recurring_by_key.get((src, company))
        if rec is not None:
            return rec
        same_src = [a for a in recurring_alerts if a.get("source") == src]
        # compat com o comportamento antigo: source com UMA serie recorrente
        # continua ganhando o sufixo (caso nao-ambiguo); com multiplas series
        # exige company exato para nao atribuir reincidencia a empresa errada
        if len(same_src) == 1:
            return same_src[0]
        return None

    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for src, company, code in failures:
        text = f"• {_friendly_source(src, source_names, company)} — {_error_text(code)}"
        rec = _recurring_for(src or "", company or "")
        if rec is not None:
            text += f" · recorrente há {rec.get('runs_seq', '?')} runs"
        reg = regression_by_key.get((src or "", company or ""))
        if reg is not None:
            # item 4: a falha do run ganha o contexto historico (a serie
            # funcionava antes) — alerta de regressao da MESMA serie nao
            # renderiza linha duplicada.
            text += (f" · antes funcionava ({reg.get('ok_history', '?')} runs ok"
                     f" e agora falhou)")
        problems.append(text)
        seen.add((src or "", company or ""))
    for a in alerts:
        src = a.get("source", "?") or "?"
        company = a.get("company") or ""
        if (src, company) in seen:
            continue
        if a.get("type") == "drop":
            problems.append(
                f"• {_friendly_source(src, source_names, company)} — queda brusca "
                f"(collected {a.get('collected_atual')} < 50% da mediana "
                f"{a.get('mediana_anterior')} · {a.get('pct')})"
            )
        elif a.get("type") == "zero_return":
            problems.append(
                f"• {_friendly_source(src, source_names, company)} — voltou a zero (empty) após "
                f"{a.get('ok_history')} runs com vagas (último ok: {a.get('last_ok_collected')})"
            )
        elif a.get("type") == "regression":
            # item 4 da auditoria 23/09: empresa historicamente ok que passou
            # a falhar. Quando a serie tambem falhou no run atual, o contexto
            # ja foi anotado na linha de falha acima (dedup); aqui so chega a
            # regressao de serie SEM falha correspondente no resumo do run.
            problems.append(
                f"• {_friendly_source(src, source_names, company)} — estava funcionando "
                f"e falhou ({_error_text(a.get('error_code'))})"
            )
        else:  # recurring sem falha correspondente no run atual
            problems.append(
                f"• {_friendly_source(src, source_names, company)} — erro recorrente "
                f"({a.get('runs_seq')} runs consecutivos)"
            )
    if problems:
        lines.append("")
        lines.append("⚠️ Problemas detectados:")
        lines.extend(problems)

    if disk_warning:
        lines.append("")
        lines.append(f"⚠️ Disco: {disk_pct}% usado")
    if backup_error:
        lines.append("")
        lines.append(f"⚠️ Backup do jobs.db falhou: {backup_error}")
    if publish_error:
        lines.append("")
        lines.append(f"⚠️ Publicação GitHub Pages falhou: {publish_error}")
    # Fase 2 — digest do ranking (perfil, novas vagas no Top 30, Top 5,
    # mudancas e link do ranking completo). Anexado ao FIM da mensagem: o
    # resumo operacional acima fica intocado e o link e sempre a ultima
    # linha. ``digest_lines`` ja vem com espaco em branco separador inicial;
    # sem digest (dataset vazio/truncado ou falha na montagem), nada e
    # anexado.
    base_len = len(lines)
    if digest_lines:
        lines.extend(digest_lines)
    text = "\n".join(lines)
    if digest_lines and len(text) > TELEGRAM_MAX_LEN:
        # Telegram aceita no maximo 4096 chars. A mensagem base (operacional)
        # e preservada INTEGRA; o digest vira 1 linha com o link — melhor do
        # que nao chegar nada (sendMessage devolveria 400).
        link = next(
            (line for line in reversed(digest_lines) if line.startswith("🔗")),
            digest_lines[-1],
        )
        compact = (f"ℹ️ Resumo do ranking encurtado (mensagem longa) — "
                   f"ranking completo: {link}")
        text = "\n".join(lines[:base_len] + ["", compact])
    return text


# --- telegram --------------------------------------------------------------

def telegram_url(token: str) -> str:
    """URL do sendMessage para um token (testavel sem rede)."""
    return TELEGRAM_API.format(token=token)


def send_telegram(token: str, chat_id: str, text: str, timeout: float = 30.0) -> dict:
    """Envia ``text`` via Bot API sendMessage; devolve o JSON da resposta.

    Qualquer falha de rede/HTTP levanta excecao (o chamador trata e loga —
    o refresh nunca crasha por causa do envio).
    """
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        telegram_url(token), data=payload, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def notify_or_log(config: dict, message: str, *, dry_run: bool) -> dict:
    """Envia OU loga a decisao; nunca levanta. Devolve o resultado do envio.

    - ``dry_run``: imprime a mensagem e nao envia (``sent=False``).
    - sem token/chat no config: aviso e nao envia (``sent=False``).
    - senao: chama ``send_telegram``; falha de rede -> erro logado e
      ``sent=False`` (o refresh nao pode cair por causa da notificacao).
    """
    if dry_run:
        print("\n===== MENSAGEM (DRY-RUN — nada enviado) =====")
        print(message)
        print("==============================================")
        return {"sent": False, "dry_run": True}
    token = config.get(ENV_TOKEN)
    chat_id = config.get(ENV_CHAT)
    if not token or not chat_id:
        log.warning(
            "alerta nao enviado: %s/%s ausentes no config (defina em .env)",
            ENV_TOKEN if not token else "ok",
            ENV_CHAT if not chat_id else "ok",
        )
        return {"sent": False, "reason": "no_credentials"}
    try:
        response = send_telegram(token, chat_id, message)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        log.error("alerta nao enviado: falha no sendMessage (%s)", exc)
        return {"sent": False, "reason": "send_error", "error": str(exc)}
    log.info("telegram response: %s", json.dumps(response, ensure_ascii=False))
    return {"sent": bool(response.get("ok")), "response": response}


# --- dry-run (dados sinteticos, sem rede/data) -----------------------------

def _seed_dry_run(data_dir: Path) -> tuple[int, int]:
    """Cria data_dir com arquivos falsos + JSONL sintetico com historia e um
    run novo com anomalia (padrao ``smartrecruiters:other`` do JSONL real).
    Devolve ``(linhas_de_historia, linhas_novas)`` para o snapshot.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "jobs.json").write_text(
        json.dumps([{"id": "sf:1", "title": "Working Student Supply Chain",
                     "company": "SAP", "country_iso": "de"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "jobs.csv").write_text("id,title\nsf:1,Working Student Supply Chain\n", encoding="utf-8")
    (data_dir / "eligible_jobs.json").write_text(
        json.dumps([{"id": "sf:1", "title": "Working Student Supply Chain",
                     "company": "SAP", "country_iso": "de", "score": 6.0}], ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "eligible_jobs.csv").write_text(
        "id,title,score\nsf:1,Working Student Supply Chain,6.0\n", encoding="utf-8")

    # jobs.db sintetico (historico SQLite) para o dry-run exercitar o backup
    # do passo 2b sem tocar no data/ real.
    db = data_dir / "jobs.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, title TEXT NOT NULL)")
    conn.executemany(
        "INSERT INTO jobs (id, title) VALUES (?, ?)",
        [("sf:1", "Working Student Supply Chain"), ("sf:2", "Intern Analytics")])
    conn.commit()
    conn.close()

    def tenant(rid: str, source: str, status: str, collected: int,
               company: str = "Acme", error_code: str | None = None) -> dict:
        return {
            "type": "tenant", "run_id": rid, "timestamp": rid,
            "company": company, "source": source,
            "ats": source.split(":", 1)[0], "status": status,
            "collected": collected,
            "error": None if status not in ("timeout", "error") else "boom",
            "error_code": error_code, "duration": 1.5,
        }

    history = [
        tenant("2026-08-30T06:00:00+00:00", "successfactors:jobs", "ok", 400, "SAP"),
        tenant("2026-08-31T06:00:00+00:00", "successfactors:jobs", "ok", 380, "SAP"),
        tenant("2026-09-01T06:00:00+00:00", "successfactors:jobs", "ok", 410, "SAP"),
        tenant("2026-09-02T06:00:00+00:00", "successfactors:jobs", "ok", 395, "SAP"),
        tenant("2026-09-03T06:00:00+00:00", "smartrecruiters:other", "error", 0),
        tenant("2026-09-04T06:00:00+00:00", "smartrecruiters:other", "error", 0),
        tenant("2026-09-04T12:00:00+00:00", "smartrecruiters:other", "error", 0),
    ]
    new = [
        tenant("2026-09-05T06:00:00+00:00", "successfactors:jobs", "ok", 390, "SAP"),
        tenant("2026-09-05T06:00:00+00:00", "smartrecruiters:other", "error", 0, "Bosch", "UNKNOWN"),
        tenant("2026-09-05T06:00:00+00:00", "smartrecruiters:continental", "timeout", 0, "Continental", "TIMEOUT"),
        {
            "type": "run", "run_id": "2026-09-05T06:00:00+00:00",
            "timestamp": "2026-09-05T06:01:00+00:00",
            "total_collected": 391, "filtered": 44, "dedup_removed": 1, "eligible": 43,
        },
    ]
    with (data_dir / "collection_metrics.jsonl").open("a", encoding="utf-8") as fh:
        for rec in history + new:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Archive antigo (fora da retencao) para o dry-run exercitar a limpeza.
    old_archive = data_dir / "archive" / "20200101T000000Z"
    old_archive.mkdir(parents=True)
    (old_archive / "jobs.json").write_text("{}", encoding="utf-8")
    return len(history), len(new)


def _run_dry_run(retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Fluxo dry-run: tempdir com dados sinteticos; valida rotacao, limpeza
    do archive, snapshot de linhas, health, resumo e mensagem. Nunca toca
    ``data/`` nem a rede."""
    with tempfile.TemporaryDirectory(prefix="refresh_dryrun_") as tmp:
        base = Path(tmp)
        data_dir = base / "data"
        archive_root = base / "data" / "archive"
        hist, new = _seed_dry_run(data_dir)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        print(f"== DRY-RUN (tempdir {base}) ==")
        archive_dir = rotate(data_dir, archive_root, ts)
        print(f"== limpeza do archive (--retention-days {retention_days}) ==")
        removed = cleanup_archive(archive_root, retention_days)
        restantes = sorted(p.name for p in archive_root.iterdir())
        print(f"archives removidos: {len(removed)}; restantes: {restantes}")
        metrics = data_dir / "collection_metrics.jsonl"
        new_records = read_new_records(metrics, hist)
        print(f"linhas novas lidas: {len(new_records)} (esperado {new})")
        print("== backup do jobs.db (passo 2b do refresh) ==")
        try:
            bk = backup_jobs_db(data_dir / "jobs.db")
            print(f"backup criado: {bk}")
        except Exception as exc:  # noqa: BLE001 — dry-run reporta e segue
            print(f"backup do jobs.db FALHOU: {type(exc).__name__}: {exc}")
        removed_bk = cleanup_backups(
            data_dir / BACKUP_DIR_NAME, retention_days)
        print(f"backups removidos pela retencao ({retention_days}d): "
              f"{len(removed_bk)}")
        summary = summarize_run(new_records)
        print("resumo:", json.dumps(summary, ensure_ascii=False, default=str))
        records = read_new_records(metrics, 0)
        report = build_health_report(records)
        print("alertas health:", json.dumps(report["alerts"], ensure_ascii=False))
        print("== digest do ranking (Fase 2) ==")
        digest = ranking_digest.digest_sections(
            data_dir / "eligible_jobs.json",
            archive_dir / "eligible_jobs.json",
            pages_url=ranking_digest.resolve_pages_url(base),
        )
        print("digest montado:",
              "sim" if digest else "nao (sem ranking atual)", 
              f"({len(digest)} linhas)" if digest else "")
        message = build_message(summary, report["alerts"], exit_code=0,
                                digest_lines=digest)
        notify_or_log({}, message, dry_run=True)
        print(f"archive criado: {archive_dir} ({len(list(archive_dir.iterdir()))} arquivos)")
        print("DRY-RUN OK: data/ real intocada, sem rede, sem envio.")
        return 0


# --- fluxo de producao -----------------------------------------------------

def _archive_run_info(archive_dir: Path, summary: dict, alert_count: int,
                      publish_error: str | None = None) -> None:
    """Registra no archive o run que substituiu o snapshot (best-effort)."""
    info = {
        "rotated_at": utcnow_iso(),
        "run_id": summary.get("run_id"),
        "exit_code": summary.get("_exit_code"),
        "total_collected": summary.get("total_collected"),
        "eligible": summary.get("eligible"),
        "alerts": alert_count,
    }
    if publish_error:
        info["publish_error"] = publish_error
    try:
        (archive_dir / "run_info.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("run_info.json nao gravado: %s", exc)


def _sync_personal_ranking(root: Path, data_dir: Path) -> None:
    """Fase 8 — sync-ranking diario do banco pessoal (best-effort).

    Registra (idempotentemente) saidas do ranking/ATS das vagas marcadas,
    chamando o CLI do personal_tracker como subprocesso com os caminhos do
    checkout REAL (root), nunca do clone de teste. Falha NUNCA derruba o
    run (o chamador envolve em try/except) e o banco ausente e criado pelo
    proprio tracker na primeira marcacao.
    """
    import subprocess as _sp
    script = root / "scripts" / "personal_tracker.py"
    if not script.exists():
        log.info("sync-ranking pessoal pulado (scripts/personal_tracker.py ausente)")
        return
    cmd = [
        sys.executable, str(script),
        "--db", str(data_dir / "personal" / "jobs_personal.db"),
        "--ranking", str(data_dir / "eligible_jobs.json"),
        "--jobs-db", str(data_dir / "jobs.db"),
        "sync-ranking",
    ]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    proc = _sp.run(cmd, cwd=root, capture_output=True, text=True, timeout=60,
                   env=env)
    if proc.returncode == 0:
        log.info("sync-ranking pessoal: %s", proc.stdout.strip()[:200])
    else:
        log.warning("sync-ranking pessoal exit %d: %s",
                    proc.returncode, (proc.stderr or proc.stdout).strip()[:200])



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh diario da coleta (rotacao + coleta real + health"
        " + alerta Telegram em anomalia).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="sem rede e sem escrever em data/ (tempdir com dados sinteticos)")
    parser.add_argument("--config", default=None, metavar="PATH",
                        help="arquivo .env com TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID (default: .env na raiz)")
    parser.add_argument("--always-notify", action="store_true",
                        help="envia o resumo mesmo sem anomalia (digest diario; nao e o default)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="timeout por scraper passado ao CLI (default 60)")
    parser.add_argument("--max-collection-secs", type=float, default=5400.0,
                        help="teto total do subprocesso de coleta em segundos (default 5400)")
    parser.add_argument("--retention-days", type=_non_negative_int,
                        default=DEFAULT_RETENTION_DAYS, metavar="N",
                        help="retencao do archive em dias "
                        f"(default {DEFAULT_RETENTION_DAYS}; 0 = desligado)")
    parser.add_argument("--backup-retention-days", type=_non_negative_int,
                        default=DEFAULT_BACKUP_RETENTION_DAYS, metavar="N",
                        help="retencao dos backups do jobs.db em dias "
                        f"(default {DEFAULT_BACKUP_RETENTION_DAYS}; 0 = desligado)")
    parser.add_argument("--pages-dir", default=None, metavar="PATH",
                        help="clone de deploy do GitHub Pages (branch gh-pages). "
                        "Quando informado, o ranking do run e publicado "
                        "automaticamente apos a coleta (gate UNICO "
                        "publication_allowed: eligible > 0 com exit 0 ou exit 2 "
                        "= parcial com falhas perifericas). Default: "
                        "publicacao desligada.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.dry_run:
        return _run_dry_run(args.retention_days)

    root = repo_root()
    data_dir = root / "data"
    metrics_path = data_dir / "collection_metrics.jsonl"
    archive_root = data_dir / "archive"
    config_path = Path(args.config) if args.config else root / ".env"

    log.info("refresh: rotacao antiga -> archive (config=%s)", config_path)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = rotate(data_dir, archive_root, ts)
    cleanup_archive(archive_root, args.retention_days)

    skip_lines = _count_lines(metrics_path)
    proc = run_collection(collection_command(args.timeout), root, args.max_collection_secs)
    exit_code = proc.returncode

    # 2b. Backup do jobs.db (P3): snapshot consistente pos-coleta, via backup
    # API do sqlite3 (stdlib). Falha NUNCA derruba o run nem muda o exit code
    # — e reportada no log e (se houver envio) na mensagem do Telegram.
    # Banco ausente (ex.: primeiro run) NAO e falha: nada a copiar, pula.
    backup_error: str | None = None
    jobs_db = data_dir / "jobs.db"
    if jobs_db.exists():
        try:
            backup_path = backup_jobs_db(jobs_db)
            log.info("backup do jobs.db criado: %s", backup_path)
        except Exception as exc:  # noqa: BLE001 — backup e operacional, nao critico
            backup_error = f"{type(exc).__name__}: {exc}"
            log.error("backup do jobs.db FALHOU: %s", backup_error)
    else:
        log.info("sem %s; backup do jobs.db pulado", jobs_db)
    try:
        removed_backups = cleanup_backups(
            data_dir / BACKUP_DIR_NAME, args.backup_retention_days)
        if removed_backups:
            log.info("backup cleanup: %d backup(s) removido(s)",
                     len(removed_backups))
    except Exception as exc:  # noqa: BLE001 — limpeza nunca derruba o run
        log.error("backup cleanup falhou: %s", exc)

    new_records = read_new_records(metrics_path, skip_lines)
    summary = summarize_run(new_records)
    summary["_exit_code"] = exit_code
    log.info("run %s: exit %d, %d registros novos (bruto %s, eligible %s)",
             summary.get("run_id"), exit_code, len(new_records),
             summary.get("total_collected"), summary.get("eligible"))

    records = read_new_records(metrics_path, 0)  # JSONL completo (defensivo)
    report = build_health_report(records)
    log.info("health: %d alertas", len(report["alerts"]))

    disk_pct = disk_usage_pct(data_dir)
    disk_pct = disk_pct if disk_pct is not None and disk_pct > DISK_WARN_PCT else None
    if disk_pct is not None:
        log.warning("disco: filesystem de %s com %d%% de uso (>= %d%%)",
                    data_dir, disk_pct, DISK_WARN_PCT)

    # Fase 1 — publicacao do ranking em GitHub Pages (apos a coleta e o health;
    # nunca derruba o run: falha vira publish_error, reportada no Telegram).
    publish_error: str | None = None
    pages_dir = Path(args.pages_dir).expanduser() if args.pages_dir else None
    if pages_dir is not None:
        try:
            changed = publish_pages.publish_ranking(
                root, pages_dir,
                exit_code=exit_code,
                eligible=summary.get("eligible") or 0,
                run_id=summary.get("run_id") or utcnow_iso(),
            )
            if changed:
                log.info("ranking publicado em GitHub Pages (branch gh-pages)")
        except Exception as exc:  # noqa: BLE001 — publicacao e operacional, nao critica
            publish_error = f"{type(exc).__name__}: {exc}"
            log.error("publicacao GitHub Pages FALHOU: %s", publish_error)
    else:
        log.info("publicacao GitHub Pages desligada (sem --pages-dir)")

    # Fase 2 — digest do ranking para o Telegram. MESMO gate UNICO da
    # publicacao (``publish_pages.publication_allowed``, auditoria 23/09): um
    # run parcial (exit 2) com vagas validas e um ranking oficial tao bom
    # quanto o de um run perfeito — as falhas perifericas de fontes
    # individuais (Lidl timeout, K+N NXDOMAIN...) ja sao reportadas no resumo
    # operacional acima, e o "estado anterior" continua vindo do snapshot da
    # rotacao (``archive_dir/eligible_jobs.json``). Dataset vazio ou run
    # truncado (exit 1/124) nao montam digest (nao ha ranking confiavel).
    # Falha ao montar NUNCA derruba o run: vira log e a mensagem segue sem
    # digest.
    digest_lines: list[str] | None = None
    if publish_pages.publication_allowed(exit_code, summary.get("eligible") or 0):
        try:
            digest_lines = ranking_digest.digest_sections(
                current_path=data_dir / "eligible_jobs.json",
                previous_path=archive_dir / "eligible_jobs.json",
                pages_url=ranking_digest.resolve_pages_url(root),
            )
        except Exception as exc:  # noqa: BLE001 — digest e best-effort
            log.warning("digest do ranking nao montado (run segue normal): %s", exc)
        # Fase 8 — sync-ranking + secoes PESSOAIS do digest (banco privado
        # data/personal/jobs_personal.db). Best-effort TOTAL: banco ausente,
        # corrompido ou falha qualquer -> secoes vazias/log, o run segue.
        # As secoes entram ANTES do link (o link continua a ultima linha);
        # se a mensagem final estourar 4096, o compactador existente preserva
        # a base + link (secoes pessoais somem no compact — documentado).
        try:
            personal_lines = ranking_digest.personal_sections(
                db_path=data_dir / "personal" / "jobs_personal.db",
                current_path=data_dir / "eligible_jobs.json",
            )
            if personal_lines and digest_lines:
                # insere antes do link (ultima linha do digest)
                digest_lines = digest_lines[:-1] + personal_lines + [digest_lines[-1]]
            elif personal_lines and digest_lines is None:
                digest_lines = personal_lines
        except Exception as exc:  # noqa: BLE001 — pessoal nunca derruba o run
            log.warning("secoes pessoais nao montadas (run segue normal): %s", exc)
        try:
            _sync_personal_ranking(root, data_dir)
        except Exception as exc:  # noqa: BLE001 — sync nunca derruba o run
            log.warning("sync-ranking pessoal falhou (run segue normal): %s", exc)
    else:
        log.info("digest/sync pulados (exit %d com eligible %s — gate "
                  "publication_allowed negativo)", exit_code,
                  summary.get("eligible"))

    message = build_message(summary, report["alerts"], exit_code,
                            always_notify=args.always_notify,
                            disk_pct=disk_pct,
                            backup_error=backup_error,
                            publish_error=publish_error,
                            digest_lines=digest_lines)
    if message is None:
        print("Sem anomalia — nenhum envio (anti-spam).")
    else:
        print("\n===== MENSAGEM =====")
        print(message)
        print("=====================")
        result = notify_or_log(load_env_config(config_path), message, dry_run=False)
        if result.get("dry_run"):
            pass
        elif not result.get("sent"):
            log.warning("envio nao confirmado: %s",
                        result.get("reason") or result.get("error") or "desconhecido")

    _archive_run_info(archive_dir, summary, len(report["alerts"]),
                      publish_error=publish_error)
    # P1.3: o exit code final e o da coleta (0/1/2; 124 = teto estourado).
    # Toda a observabilidade (health/metricas/Telegram/limpeza/run_info) ja
    # rodou acima — so o status entregue ao SO muda. Antes o refresh sempre
    # terminava em 0 e o cron/systemd interpretavam falha como sucesso.
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())