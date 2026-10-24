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
1c. **Retencao do collection_metrics.jsonl (F75)** — ``rollup_metrics``
   agrupa os registros de metricas mais antigos que
   ``--metrics-retention-days`` dias (default 90; ``0`` desliga) em UM
   registro ``type: metrics_rollup`` POR DIA (contagem por type + somas dos
   campos numericos por type); dentro do corte o arquivo fica RAW, byte a
   byte. Executada AQUI, em runtime (nunca hand-edit), ANTES do snapshot de
   linhas e da coleta; idempotente e atomica (tmp + os.replace); falha
   NUNCA derruba o run. O raw completo de cada dia cortado segue no
   snapshot do archive de hoje (backup de curto prazo).
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
2b. **Backup do jobs.db (P3) + dataset_seen.db (F70)** — snapshot consistente
   via backup API do sqlite3 (stdlib) para ``data/backups/`` (artefatos
   standalone, sem sidecars WAL; stems proprios ``jobs-<ts>.db`` /
   ``dataset_seen-<ts>.db``); retencao simples ``--backup-retention-days``
   (default 14, 0 desliga) aplicada em seguida AOS DOIS. Falha NUNCA derruba
   o run nem muda o exit code: e logada e (se houver envio) entra na
   mensagem como ``⚠️ Backup ... falhou: ...``.
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
- ``--backup-retention-days N``: retenção dos backups em dias (default 14;
  ``0`` desliga) — cobre jobs.db E dataset_seen.db (F70), no mesmo
  ``data/backups/``.

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
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from internship_finder.health import build_health_report  # reuso — sem camada nova
from internship_finder.metrics_retention import (  # F75 — rollup do JSONL de métricas
    DEFAULT_METRICS_RETENTION_DAYS,
    rollup_metrics,
)
from internship_finder.ranking import rescore_hydrated_jobs  # F56 — re-score pós-hidratação
from internship_finder.storage.sqlite_backup import (  # backup do jobs.db (P3)
    BACKUP_DIR_NAME,
    backup_jobs_db,
    cleanup_backups,
)
import manual_check  # F96: fila manual-check (MANUAL-CHECK.md) + id_collision
import minimal_page  # F6: render da pagina publica (cap 2/empresa F11)
import publish_pages  # publicacao do ranking em GitHub Pages (Fase 1)
import ranking_digest  # digest do ranking no Telegram (Fase 2)
import url_liveness  # F11: vitalidade de URL do top exibido (404/410); F20: soft-dead + hidratacao

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

# Retencao default dos backups (jobs.db + dataset_seen.db, F70) em dias
# (--backup-retention-days). Mesma politica do archive: simples,
# documentada, sem lifecycle complexo.
DEFAULT_BACKUP_RETENTION_DAYS = 14

# Cap default de extracoes LLM por run do enrichment (--enrichment-limit).
# Espelha o DEFAULT_LIMIT do runner (decisao D2: backlog processado
# naturalmente em execucoes futuras, 24 x 16-290s medidos).
DEFAULT_ENRICHMENT_LIMIT = 24
# Corte do ranking do enrichment (--enrichment-top-n): somente as N vagas
# mais bem ranqueadas entram no plano/backlog (decisao do dono 26/09 —
# espelha o top 30 do spike; vagas fora do corte nunca entram por serem
# novas e sao cobertas ao reentrar no corte).
DEFAULT_ENRICHMENT_TOP_N = 30
# F1 (01/10): teto TOTAL de duracao do subprocesso de enrichment em
# segundos. Historico motivador (enrichment_status.json 29-30/09): janela
# NVIDIA degradada com retries ReadTimeout de ~264s/chamada levou o run a
# 17.615s (~4h53) e 5h38 — o cron do dia inteiro perdido segurando o flock.
# O teto e a defesa estrutural do flock: estourado, o subprocesso e morto
# (SIGKILL; o store e atomico por record e o lock interno e flock do SO —
# morte de processo nunca corrompe nem deixa lock preso) e o refresh segue
# com o exit code da coleta. 1800s cobre o run saudavel medido (sweep
# ~40 fetches + 24 extracoes x ~290s pior caso).
DEFAULT_ENRICHMENT_MAX_SECS = 1800

# F1 (01/10): gate de configuracao do enrichment LLM. A flag CLI
# ``--enrichment`` EXISTE e continua funcionando (codigo preservado para
# uso manual sob demanda), mas so surte efeito quando a env var
# ``INTERNSHIP_FINDER_ENRICHMENT=1`` esta presente — o cron de producao
# roda com o default (ausente) e o enrichment fica OFF. Motivo (auditoria
# Fase H + producao 29-30/09): custo alto (5h38/run na janela degradada,
# flock preso ate 14:54, 0/21 extracoes) com retorno zero. Padrao do
# projeto: mesma mecanica da flag INTERNSHIP_FINDER_GEOCODING (geocoding.py).
ENRICHMENT_ENV_FLAG = "INTERNSHIP_FINDER_ENRICHMENT"

# ---------------------------------------------------------------------------
# F20 — higiene do topo: liveness v2 (soft-dead) + hidratacao de descricao.
# O MESMO passe GET sequencial serve aos dois (mesmas URLs). Bounded ao
# top exibido, timeout curto e delay sequencial herdados do url_liveness.
# ---------------------------------------------------------------------------
# Hidratacao: descricao curta = < HYDRATION_SHORT_LIMIT chars (spec: ex. 500).
HYDRATION_SHORT_LIMIT = 500
# Provenance honesta da descricao hidratada (spec F20 item 3).
HYDRATION_SOURCE = "hydrated_topn"

# Marcador de inaplicabilidade revelada pela hidratacao (spec F20 item 3:
# a vaga NAO sai do JSON — so desce do top exibido, como o dead_link).
HYDRATION_INAPPLICABLE_FLAG = "hydration_inapplicable"

# ---------------------------------------------------------------------------
# F65 — hidratacao ALEM do top exibido (janela estendida), flag-gated com
# TETO de fetches/dia. A F20 cobre so o top exibido (apply_company_cap);
# vagas com description curta/vazia fora dessa janela ficam CEGAS aos
# detectores (idioma/visto/sazonalidade/salario — medido pela F60:
# classe B, caso Lidl praktikum_info:13308116, score 9.0, pagina viva com
# JSON-LD de 2524 chars que o pipeline nunca viu). A passagem estendida
# reusa o MESMO passe GET do url_liveness (liveness + parse JSON-LD F22,
# 1 fetch sequencial por vaga) sobre as vagas de description curta FORA
# do top exibido, EM ORDEM DE SCORE (as melhores primeiro), ate o teto
# diario. Regra 9: default OFF — budget 0/ausente/invalido = zero
# mudanca de comportamento (nenhum fetch, JSON byte-identical).
# ---------------------------------------------------------------------------
# Teto diario de fetches da janela estendida (env OU .env, padrao F1):
# INTERNSHIP_FINDER_HYDRATION_BUDGET=N com N inteiro >= 1 liga o estagio;
# 0/ausente/invalido = OFF. O dono decide o custo (relatorio F65 §budget:
# ~2.5s/fetch medidos; N=120 cobre o backlog atual de ~126 cegas).
HYDRATION_BUDGET_ENV_FLAG = "INTERNSHIP_FINDER_HYDRATION_BUDGET"
# Provenance distinta da top-N (HYDRATION_SOURCE): distingue no JSON de
# onde veio o texto e mantem a F25 (backlog "hydration") intocada.
HYDRATION_SOURCE_EXTENDED = "hydrated_extended"
# Teto TOTAL do estagio estendido (rede de patologia: timeout por vaga =
# ~5.2s pior caso; 600s cobre ~110 vagas no pior caso e ~240 na media
# medida — truncacao e logada pelo url_liveness, nunca derruba o run).
EXTENDED_HYDRATION_DEADLINE_S = 600.0

# ---------------------------------------------------------------------------
# F91 — hidratacao dos CEGOS: description para as vagas desc-empty do pool
# (< BLIND_DESCRIPTION_LIMIT chars), terceiro estagio flag-gated (padrao
# F65), budget PROPRIO. Alvo medido 21/10: absolventa 30/30 fetchaveis
# (JSON-LD JobPosting malformado — chars de controle crus + escapes
# invalidos — curado pelo parse leniente F91 no url_liveness) e
# praktikum_info 1/1; sf_dataset:bundesagentur fica FORA da lista de
# fontes: o Passo 0 mediu 74/74 refnrs das cegas MORTOS na fonte (detail
# v4 HTTP 404, pagina publica 410 — o slice do dataset e espelho
# atrasado; os postings vivos, 26/26, a Fase A ja cura diariamente) e a
# spec manda pular fonte incuravel ("se parede, documentar e pular").
# ---------------------------------------------------------------------------

# Teto diario de fetches do estagio dos cegos (env OU .env, padrao F1):
# INTERNSHIP_FINDER_BLIND_HYDRATION_BUDGET=N com N inteiro >= 1 liga;
# 0/ausente/invalido = OFF (regra 9: zero fetch, JSON byte-identical).
# Budget PROPRIO — nao compartilha o poço do F65 (spec F91 item 2).
BLIND_HYDRATION_BUDGET_ENV_FLAG = "INTERNSHIP_FINDER_BLIND_HYDRATION_BUDGET"
# Provenance distinta (hydration / hydrated_topn / hydrated_extended):
# identifica no JSON o texto trazido pelo estagio dos cegos.
HYDRATION_SOURCE_BLIND = "hydrated_blind"
# Limiar "cego" da spec F91 (<50 chars) — NAO confundir com a janela
# F65 (HYDRATION_SHORT_LIMIT=500): cegas sao vagas SEM texto util, a
# janela estendida cobre vagas com texto CURTO.
BLIND_DESCRIPTION_LIMIT = 50
# Fontes atendidas pelo estagio, em ordem de prioridade por volume
# curavel medido no Passo 0 (absolventa 30 > praktikum_info 1). Fontes
# fora da lista (sf_dataset:bundesagentur: mortas na fonte, ver acima;
# sf_dataset:oracle: URL e pagina de BUSCA, nao de vaga) ficam cegas —
# motivo documentado no relatorio da fase.
BLIND_HYDRATION_SOURCES: tuple[str, ...] = ("absolventa", "praktikum_info")
# Timeout por fetch do estagio (pagens de board: 200-300 KB medidos;
# 20s = mesmo teto conservador do direct_fetch).
BLIND_HYDRATION_TIMEOUT_S = 20.0
# Cap de corpo lido por fetch (1 MB — pagina real ~265 KB; protege o
# parse de corpos anomais, mesmo cap logico do liveness).
BLIND_HYDRATION_MAX_BYTES = 1_048_576
# Teto TOTAL do estagio (pior caso patologico: budget inteiro em
# timeouts; 600s cobre 30 timeouts — truncacao logada, nunca derruba).
BLIND_HYDRATION_DEADLINE_S = 600.0


# ---------------------------------------------------------------------------
# F87 — flag "não-avaliável" (display + digest, NUNCA exclusão) + liveness
# no 1º sighting. Princípio: não gastar a análise do dono em coisa que não
# presta. (a) O flag acende quando a descrição que chegou ao eligible não dá
# base de julgamento: vazia (0 chars úteis — caso Amazon Koblenz JS-vazio,
# TYTAN, Impulsgrad), abaixo do limiar medido (caso henkel 89534: 584 chars
# de SAML wall, sem idioma/início/duração) ou com padrão textual de
# login-wall/placeholder. É SINAL (badge ⚠️ + linha no digest), não filtro —
# a vaga segue eligible, visível e ranqueada. Passo 0 (20/10, corpus 704):
# mediana 2.490 chars, p25 1.469 — limiar 600 (~26% do p25) pega a wall do
# henkel sem incendiar o corpus (136/704 com desc < 600, 103 delas vazias).
# A hidratação CURA: F20/F65 trazendo texto >= limiar sem wall => o flag
# apaga (a anotação recomputa TODO run). (b) Candidatas NOVAS (primeira
# aparição do ID contra o snapshot arquivado — MESMO diff do digest, que
# cobre sf_dataset:/direct: que nunca passam pelo SQLite) ganham 1 fetch
# barato do url_liveness ANTES da janela de análise; 404/410 => mecanismo
# F39 de remoção do JSON; 200-falso textual (Festo "bereits besetzt") =>
# morta para display (🔗 + desce do top; fica no JSON, semântica F20);
# timeout/rede NUNCA prova morte (nada de falso-positivo). Budget: teto
# diário HERDADO do F65 (MESMO knob INTERNSHIP_FINDER_HYDRATION_BUDGET; o
# que o intake gasta abate do F65 no mesmo run — um só poço). Default OFF
# (budget 0 = regra 9: nenhuma mudança até o dono ligar).
# ---------------------------------------------------------------------------
NOT_ASSESSABLE_FLAG = "not_assessable"
ASSESSABLE_MIN_CHARS = 600
# Padrões de login-wall/placeholder (Passo 0: saml/anmelden/"required…sign
# in" = 0 hits no corpus 704 — defensivos, zero FP medido; "please add a
# text" = 1 hit real, placeholder literal do template henkel 89300).
# "sign in"/"login" NUS: 16 falso-positivos medidos ("design in…",
# "cascading", "InDesign") — fora do detector.
_LOGIN_WALL_RE = re.compile(
    r"saml|anmelden|required.{0,80}sign\s?in|please add a text",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# F39 — remoção automática de hard-dead. Critério de "confirmado": o
# veredito JÁ EXISTENTE do estágio de vitalidade — HTTP 404/410
# (url_liveness.DEAD_STATUS), a MESMA resposta que marcava o badge F11;
# nenhum critério novo é inventado. Soft-dead (marcador de corpo /
# redirect-para-homepage / shell SPA — SOFT_DEAD_MARKERS/SPA_SHELL_*) e
# inaplicáveis de hidratação mantêm a semântica F20/F25: ficam no JSON,
# descem do topo com badge próprio — o corpo transitório pode ser
# falso-positivo (e a URL está viva). DNS/timeout/403/429 continuam
# IGNORADOS pelo estágio (bloqueio de bot/rede — nunca provam morte).
# ---------------------------------------------------------------------------

# Kill switch da F39 (mesmo padrão dos kill switches existentes): env var
# presente => remoção desligada e o run segue com o comportamento F20
# (vaga morta fica no JSON, só desce do topo com badge).
DEAD_REMOVAL_ENV_FLAG = "INTERNSHIP_FINDER_DEAD_REMOVAL_OFF"

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

    ``--registry``: coleta das empresas do registry (fonte de interesse).
    ``--dataset`` (F3): coleta TAMBEM do dataset hospedado do ats-scrapers
    (fonte primaria) e concatena no MESMO funil. Passado EXPLICITAMENTE —
    apesar de ser o default do modo --registry — para o contrato do refresh
    ficar visivel na linha de comando do subprocesso (o cron nao passa
    flags de coleta; este comando e a unica porta de entrada).
    ``--direct-fetch`` (F4): amostra diaria DIRETA das APIs publicas BA
    (angebotsart=34) e EURES (keywords Praktikum) com filtro de estagio
    nativo — mesmo espirito do --dataset: explicito no contrato, default
    ON no --registry, cap conservador de jobs por fonte.
    ``--country de,lu,nl,fi,be`` (F7): escopo multi-pais da producao —
    DE primario + LU/NL/FI/BE canal secundario (visa_policy por pais no
    company_intel). O cron NAO muda (flags/schedule intocados): esta e a
    unica porta de entrada do escopo, como --dataset/--direct-fetch.
    ``--sqlite data/jobs.db``: persistencia first_seen/last_seen/active/
    archived (P1 #5); a flag e idempotente e falha de escrita nunca derruba
    a coleta. O ``jobs.db`` nao e rotacionado (historico acumulativo). Os
    jobs do dataset NAO entram no lifecycle (invariante F3 §7.8): sao fonte
    efemera re-derivada a cada run; so as unidades de coleta do registry
    persistem. Jobs do direct_fetch (F4) seguem a MESMA regra: fonte
    efemera, re-derivada a cada run.
    """
    from internship_finder.countries import TARGET_COUNTRIES
    return [
        sys.executable, "-m", "internship_finder.cli",
        "--registry",
        "--dataset",
        "--direct-fetch",
        "--country", ",".join(TARGET_COUNTRIES),
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

# F49 (18/10) — falha CRÔNICA: recurring_error com >= CHRONIC_FAILURE_RUNS
# runs consecutivos colapsa em 1 linha agregada no bloco "Problemas
# detectados" (proporcionalidade). Medição que motivou o limiar: o digest
# real de 15-17/10 repetia as mesmas ~7 linhas de problemas (~800 chars =
# 20% do teto de 4096), com o contador como ÚNICA mudança diária — papel de
# parede que esconde problema novo atrás de falha conhecida. Em 16/10 a
# mensagem inteira ficou a 38 chars do teto (4058/4096): 1 linha nova e o
# compactador F6.1 nivel 2 apagaria TODOS os problemas para "⚠️ N problemas
# (ver ranking)" — link que não carrega os detalhes. 15 runs consecutivos
# = 2+ semanas de cron diário: falha mais nova segue com linha própria
# (sinal de estado); a crônica vira 1 linha com nomes + contador por série
# (a decisão por fonte vive no relatório de fontes F49 e no JSONL).
CHRONIC_FAILURE_RUNS = 15

# F49 — quantos NOMES a linha agregada lista antes do "+N outras": com
# muitas séries crônicas a própria linha viraria um muro (test_f61-c mediu
# 60 séries => ~1.3k chars com nome+contador para todas). O total de fontes
# segue no começo da linha ("N fontes em falha crônica"); o estado por
# série vive no JSONL e no relatório de fontes.
CHRONIC_NAMES_SHOWN = 5


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
    seen_backup_error: str | None = None,
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
            or backup_error or seen_backup_error or publish_error):
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
    # F49 — séries em falha crônica (recurring_error com runs_seq >=
    # CHRONIC_FAILURE_RUNS): (nome, runs_seq), colapsadas em 1 linha
    # agregada no fim do bloco (proporcionalidade; ver a constante).
    chronic: list[tuple[str, int]] = []

    def _chronic_seq(rec: dict | None) -> int | None:
        """runs_seq do alerta recorrente quando >= CHRONIC_FAILURE_RUNS."""
        if rec is None:
            return None
        try:
            seq = int(rec.get("runs_seq") or 0)
        except (TypeError, ValueError):
            return None
        return seq if seq >= CHRONIC_FAILURE_RUNS else None

    for src, company, code in failures:
        rec = _recurring_for(src or "", company or "")
        seq = _chronic_seq(rec)
        if seq is not None:
            # F49: crônica — sem linha própria (papel de parede medido:
            # as mesmas linhas por 19-32 runs; só o contador mudava).
            # ``seen`` marca a série: os alertas regression/zero_return
            # dela não renderizam linha duplicada (dedup existente).
            chronic.append((company or src, seq))
            seen.add((src or "", company or ""))
            continue
        text = f"• {_friendly_source(src, source_names, company)} — {_error_text(code)}"
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
            seq = _chronic_seq(a)
            if seq is not None:
                # F49: crônica pelo caminho do alerta (sem falha no resumo
                # do run) — mesmo tratamento do caminho de falha acima.
                chronic.append((company or src, seq))
                seen.add((src, company))
                continue
            problems.append(
                f"• {_friendly_source(src, source_names, company)} — erro recorrente "
                f"({a.get('runs_seq')} runs consecutivos)"
            )
    if chronic:
        # F49 — 1 linha agregada (proporcionalidade): nomes + contador por
        # série, a mais antiga primeiro; a decisão por fonte (manter/
        # consertar/remover) vive no relatório de fontes F49 e o estado
        # bruto no JSONL de métricas. Nomes limitados a CHRONIC_NAMES_SHOWN
        # (com muitas séries a linha viria ela própria um muro — provado no
        # test_f61-c com 60 séries; o total segue no começo da linha).
        chronic.sort(key=lambda item: -item[1])
        shown = chronic[:CHRONIC_NAMES_SHOWN]
        parts = ", ".join(f"{name} ({seq} runs)" for name, seq in shown)
        extra = len(chronic) - len(shown)
        if extra > 0:
            parts += f" +{extra} outras"
        plural = "" if len(chronic) == 1 else "s"
        problems.append(
            f"• {len(chronic)} fonte{plural} em falha crônica "
            f"(≥{CHRONIC_FAILURE_RUNS} runs seguidos): {parts}"
        )
    if problems:
        lines.append("")
        lines.append("⚠️ Problemas detectados:")
        lines.extend(problems)
    # F6.1 — captura os indices da lista de problemas (para o compactador
    # resumi-la em contagem quando a base precisar encolher; -1 = sem lista).
    problems_start = len(lines) - len(problems) if problems else -1
    n_problems = len(problems)

    if disk_warning:
        lines.append("")
        lines.append(f"⚠️ Disco: {disk_pct}% usado")
    if backup_error:
        lines.append("")
        lines.append(f"⚠️ Backup do jobs.db falhou: {backup_error}")
    if seen_backup_error:
        lines.append("")
        lines.append(f"⚠️ Backup do dataset_seen.db falhou: {seen_backup_error}")
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
        # Telegram aceita no maximo 4096 chars. F6.1 — o encurtamento tem
        # PRIORIDADE de secoes (bug real 03/10: digest de 2.214 vagas
        # colapsou INTEIRO em 1 linha e matou o Top 5 do dia — a feature
        # mais valiosa do produto). Ordem de preservacao:
        #   (1) base operacional INTEGRA (como sempre);
        #   (2) secao ⚡ Top 5 do dia com apply_urls (o produto);
        #   (3) secoes 🆕 Novas e 🎯 Empresas-alvo (F13) — COLAPSAM para
        #       contagem quando aperta (1 linha cada), NUNCA sao dropadas
        #       inteiras (bug F11×F6.1: 05/10 a mensagem de 4414 chars
        #       derrubava 🆕 e 🎯 juntas);
        #   (4) headers 🧪 Materials e 🇪🇺 EU non-DE (F36.1) — mesma regra:
        #       colapsam ao header (1 linha, o corpo cede espaço), NUNCA
        #       dropadas inteiras (bug latente: 🧪 não aparecia no digest
        #       compactado desde 28/09; 🇪🇺 estreou invisível — a família
        #       de seções fantasma da página);
        #   (5) 🔗 link do ranking completo por ULTIMO.
        # O resto do digest (perfil, novas, mudancas, materials-corpo,
        # eu-corpo, enrichment, pessoais) e cortado/resumido — o link leva
        # ao ranking completo.
        link = next(
            (line for line in reversed(digest_lines) if line.startswith("🔗")),
            digest_lines[-1],
        )
        base = lines[:base_len]
        top5 = ranking_digest.top5_section_lines(digest_lines)
        # F13 — extracoes das secoes 🆕/🎯 (header+corpo; [] quando ausentes)
        # e o header de cada uma, que JA carrega a contagem do dia (o
        # "colapso para contagem" = manter so o header, padrao do
        # "(+N outras novas — ver página)" da F11 e do "⚠️ N problemas"
        # do N2 — o header e a linha mais densa e barata da secao).
        new_since = ranking_digest.new_since_section_lines(digest_lines)
        watch = ranking_digest.watchlist_section_lines(digest_lines)
        # F36.1 — headers 🧪/🇪🇺: última camada de seção do compact (o
        # corpo cede espaço às ⚡/🆕/🎯; o header identifica a seção e o
        # link leva ao resto). [] quando a seção não existe no dia.
        profile_headers = ranking_digest.materials_section_lines(digest_lines)[:1] \
            + ranking_digest.eu_section_lines(digest_lines)[:1]
        # F14 — extracao da secao ⏰ Follow-up (padrao das demais; []
        # quando ausente). No compact a ⏰ colapsa ANTES do Top 5
        # (prioridade: base > 🆕 > ⚡ Top 5 > 🎯 > ⏰ — o follow-up e
        # lembrete de pendencia cronica, o Top 5 e o produto do dia).
        followup = ranking_digest.followup_section_lines(digest_lines)
        # F44 — extração da seção ⏰ Intel de empresas (padrão F36.1: []
        # quando ausente). No compact colapsa ao header ANTES da ⏰
        # Follow-up: prioridade: ... > 🎯 > ⏰ Follow-up > ⏰ Intel — a
        # seção é gatilho de curadoria (meta-informação), abaixo das
        # pendências pessoais e do produto do dia; o header carrega as
        # contagens e o corpo (exemplos) cede espaço primeiro.
        intel_fresh = ranking_digest.intel_section_lines(digest_lines)
        # F45 — extração da seção 📅 Funil & sazonalidade (padrão F44: []
        # quando ausente). No compact colapsa ao header DEPOIS da ⏰ Intel
        # (spec F45: "sua seção semanal entra depois disso") e exibe por
        # último, antes do 🔗 link, após as seções pessoais; o header com
        # as contagens sobrevive em todos os níveis.
        funnel_sect = ranking_digest.funnel_section_lines(digest_lines)
        # F75 — alerta de gêmeos residuais (>20 grupos cross-source no
        # elegível): 1 linha ⚠️ que entra em TODOS os níveis do compact —
        # é o ALERTA da medida (a linha informativa 👯 normal segue o
        # destino das demais medições). [] quando não há alerta no dia.
        twins_alert = ranking_digest.twins_alert_lines(digest_lines)
        # Base com a lista de problemas resumida em contagem (computada UMA
        # vez, pura; o slice termina em base_len porque ``lines`` ja contem
        # o digest anexado, que e reconstruido abaixo pelas secoes + top5 +
        # link). Usada a partir do nivel 2; o nivel 1 usa ``base`` integra.
        summarized = (lines[:problems_start]
                      + [f"⚠️ {n_problems} problemas (ver ranking)"]
                      + lines[problems_start + n_problems:base_len]) \
            if problems_start >= 0 else base
        if not top5:
            # Digest sem secao ⚡ (ranking vazio/erro na montagem):
            # comportamento pre-F6.1 preservado — 1 linha com o link.
            compact = (f"ℹ️ Resumo do ranking encurtado (mensagem longa) — "
                       f"ranking completo: {link}")
            text = "\n".join(base + ["", compact])
        else:
            # Montagem por PRIORIDADE F13 (greedy decrescente): tenta a
            # mensagem mais completa que cabe; cada nivel de aperto colapsa
            # a secao de MENOR prioridade que ainda esta inteira — 🎯
            # (empresas-alvo) colapsa antes da 🆕 (novas), que colapsa
            # antes do Top 5 (que so perde linhas no teto defensivo N3).
            # As duas nunca desaparecem: o header com contagem sobrevive.
            def _fits(parts: list[str]) -> bool:
                return len("\n".join(parts)) <= TELEGRAM_MAX_LEN

            # niveis de COLAPSO de cada secao: [header, ...corpo]
            ns_full = new_since or []
            wl_full = watch or []
            fu_full = followup or []
            # Ordem de colapso (greedy F13 + F14): 🎯 colapsa antes da
            # 🆕; a ⏰ (F14) colapsa PRIMEIRO de todas — a pendencia
            # cronica abre espaco para o produto do dia (Top 5) e para
            # as novidades. Nenhuma secao e dropada inteira: quando
            # todas as variantes ainda estouram, nivel 2/3 mantem os
            # headers com contagem.
            # F44 — a ⏰ Intel de empresas colapsa antes da ⏰ Follow-up
            # (gatilho de curadoria < pendência pessoal); o header com
            # as contagens sobrevive em todos os níveis (padrão F36.1).
            in_full = intel_fresh or []
            # F45 — a 📅 Funil & sazonalidade entra DEPOIS da ⏰ Intel na
            # cadeia de colapso (meta-informação semanal < pendência
            # pessoal; "sua seção semanal entra depois disso"); header com
            # contagens sobrevive (padrão F36.1/F44). Ausente -> [] e a
            # cadeia degenera na de antes (variantes extras são no-op).
            fn_full = funnel_sect or []
            variants: list[tuple[list[str], list[str], list[str],
                                 list[str], list[str]]] = []
            for in_collapsed, fn_collapsed, fu_collapsed, wl_collapsed, ns_collapsed in (
                    (False, False, False, False, False),
                    (True, False, False, False, False),
                    (True, True, False, False, False),
                    (True, True, True, False, False),
                    (True, True, True, True, False),
                    (True, True, True, True, True)):
                ns_part = [ns_full[0]] if ns_full and ns_collapsed else ns_full
                wl_part = [wl_full[0]] if wl_full and wl_collapsed else wl_full
                fu_part = [fu_full[0]] if fu_full and fu_collapsed else fu_full
                in_part = [in_full[0]] if in_full and in_collapsed else in_full
                fn_part = [fn_full[0]] if fn_full and fn_collapsed else fn_full
                variants.append((ns_part, wl_part, fu_part, in_part, fn_part))

            text = None
            for ns_part, wl_part, fu_part, in_part, fn_part in variants:
                # Ordem de exibicao = ordem do digest (F13 §2.3): 🆕 antes
                # do ⚡, 🎯 depois do ⚡ — so o colapso muda, nunca o layout.
                # F36.1: os headers 🧪/🇪🇺 ocupam a posicao relativa que tem
                # no digest inteiro (antes da 🆕) e viram bloco PROPRIO
                # separado por linha em branco — o contrato dos extratores
                # e "corpo ate o proxima linha em branco", entao secoes
                # coladas sem blank corromperiam top5_section_lines(msg).
                # F14: a ⏰ vem das secoes pessoais (depois do 🎯, antes
                # do link) e mantem essa posicao no compact.
                # F44: a ⏰ Intel de empresas vem imediatamente ANTES da
                # ⏰ Follow-up (mesma posição relativa do digest inteiro —
                # so o colapso muda, nunca o layout, regra F13 §2.3).
                parts = base + [""]
                if profile_headers:
                    parts += profile_headers + [""]
                if ns_part:
                    parts += ns_part
                parts += top5
                if wl_part:
                    parts += wl_part
                if in_part:
                    parts += in_part
                if fu_part:
                    parts += fu_part
                # F45 — a 📅 exibe por último, antes do link (a posição
                # relativa do digest inteiro; só o colapso muda).
                if fn_part:
                    parts += fn_part
                # F75 — o alerta de gêmeos entra por ÚLTIMO antes do link
                # (posição relativa do digest inteiro).
                if twins_alert:
                    parts += twins_alert
                parts += ["", link]
                if _fits(parts):
                    text = "\n".join(parts)
                    break
            if text is None:
                # Nivel 2: a base inteira + tudo colapsado + Top 5 AINDA
                # estoura — a lista de problemas da base ja esta resumida
                # em ``summarized`` (1 linha de contagem; o bloco mais caro
                # e menos denso da base, os detalhes vivem no ranking).
                for ns_part, wl_part, fu_part, in_part, fn_part in variants:
                    parts = summarized + [""]
                    if profile_headers:
                        parts += profile_headers + [""]
                    if ns_part:
                        parts += ns_part
                    parts += top5
                    if wl_part:
                        parts += wl_part
                    if in_part:
                        parts += in_part
                    if fu_part:
                        parts += fu_part
                    if fn_part:
                        parts += fn_part
                    if twins_alert:
                        parts += twins_alert
                    parts += ["", link]
                    if _fits(parts):
                        text = "\n".join(parts)
                        break
            if text is None:
                # Nivel 3 (teto defensivo da secao ⚡): mantem o header do
                # Top 5 e adiciona LINHAS INTEIRAS que couberem — mesma
                # semantica de linhas inteiras do format_top5, sem
                # aritmetica de budget paralela. 🆕/🎯/⏰ seguem
                # colapsadas (so o header com contagem).
                ns_part = [ns_full[0]] if ns_full else []
                wl_part = [wl_full[0]] if wl_full else []
                fu_part = [fu_full[0]] if fu_full else []
                in_part = [in_full[0]] if in_full else []
                # F45 — a 📅 segue colapsada ao header no nível 3.
                fn_part = [fn_full[0]] if fn_full else []
                # F36.1 — headers de perfil seguem colapsados no nível 3
                # (1 linha cada; bloco próprio blank-separado, como nos
                # demais níveis — o contrato dos extratores exige). Guard
                # igual ao dos níveis 1/2: seções ausentes não geram bloco
                # em branco duplicado.
                prof_block = profile_headers + [""] if profile_headers else []
                kept: list[str] = [top5[0]]
                for line in top5[1:]:
                    candidate = (summarized + [""] + prof_block + ns_part + kept
                                 + wl_part + in_part + fu_part + fn_part
                                 + twins_alert
                                 + [line] + ["", link])
                    if len("\n".join(candidate)) > TELEGRAM_MAX_LEN:
                        break
                    kept.append(line)
                if len(kept) > 1:
                    parts = summarized + [""] + prof_block + ns_part + kept + wl_part \
                        + in_part + fu_part + fn_part + twins_alert + ["", link]
                    text = "\n".join(parts)
                else:
                    # Ultimo recurso: NENHUMA linha de vaga cabe — linha
                    # unica com o link (comportamento pre-F6.1).
                    compact = (f"ℹ️ Resumo do ranking encurtado "
                               f"(mensagem longa) — ranking completo: "
                               f"{link}")
                    text = "\n".join(base + ["", compact])
    return text


# --- telegram --------------------------------------------------------------

def _splice_section_before_link(digest_lines: list[str],
                                section_lines: list[str]) -> list[str]:
    """Insere ``section_lines`` antes do link (última linha do digest),
    RE-CRIANDO o separador blank do link (F45).

    O extrator do compact (``_section_by_prefix``) para no blank depois
    do corpo — sem o blank re-criado a 🔗 seria ENGOLIDA pela seção (link
    duplicado na mensagem compacta). O blank pré-link existente é
    CONSUMIDO pela seção (blank inicial dela), nunca duplicado. Usada
    pelo splice da seção 📅 no main (best-effort: listas vazias ->
    devolve o digest intacto).
    """
    if not section_lines or not digest_lines:
        return digest_lines
    head = list(digest_lines[:-1])
    if head and not str(head[-1]).strip():
        head = head[:-1]
    return head + list(section_lines) + ["", digest_lines[-1]]


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


def _run_dry_run(retention_days: int = DEFAULT_RETENTION_DAYS,
                 metrics_retention_days: int = DEFAULT_METRICS_RETENTION_DAYS
                 ) -> int:
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
        # F75 — rollup do JSONL de métricas, DEMONSTRADO aqui no dry-run
        # (em produção roda ANTES da coleta; o seeding sintético deste fluxo
        # já escreve os records "novos", então o rollup é exibido APÓS a
        # leitura do snapshot para não desfazer a contagem — o health logo
        # abaixo lê o estado PÓS-rollup, que é o que interessa demonstrar).
        # Datas sintéticas 08-30..09-05 ficam DENTRO do corte de 90d com o
        # relógio vivo; passe --metrics-retention-days 30 para vê-lo agir.
        roll = rollup_metrics(metrics, retention_days=metrics_retention_days)
        print(f"metrics rollup F75: {json.dumps(roll, ensure_ascii=False)}")
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
            # F13: watchlist do tempdir do dry-run (nao existe — radar off;
            # em producao o caminho e o do checkout real).
            watchlist_path=base / "config" / "company_watchlist.json",
            # F15: mapa de qualidade do tempdir do dry-run (nao existe —
            # Top 5 sem ⭐; em producao o caminho e o do checkout real).
            employer_quality_path=base / "config" / "employer_quality.json",
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


def _applicability_metrics_record(ranking: list, run_id: str | None = None) -> dict:
    """F37 — registro ``type: applicability`` (contagem derivada "aplicavel").

    ``applicable = eligible - flagged`` por motivo (flag
    ``hydration_inapplicable``), exposto no metrics para o header de
    universo (cards F43/F44 consomem). Conta TODO flag presente no JSON
    (novo OU herdado de re-run — mesma semantica do conjunto
    ``backlog_inapplicable_ids``). Pura: nao grava nada.
    """
    from internship_finder.filters import APPLICABILITY_EXCLUSION_REASONS

    flagged_by_reason = {
        reason: sum(
            1
            for j in ranking
            if isinstance(j, dict)
            and j.get(HYDRATION_INAPPLICABLE_FLAG) == reason
        )
        for reason in APPLICABILITY_EXCLUSION_REASONS
    }
    return {
        "type": "applicability",
        "run_id": run_id or utcnow_iso(),
        "timestamp": utcnow_iso(),
        "eligible": len(ranking),
        "flagged": sum(flagged_by_reason.values()),
        "applicable": len(ranking) - sum(flagged_by_reason.values()),
        **{f"flagged_{r}": v for r, v in flagged_by_reason.items()},
    }


def _remove_hard_dead(ranking: list, hard_dead_ids: set[str],
                      hard_dead_status: dict[str, int]) -> dict:
    """F39 — remove do ``ranking`` (in place) as vagas com URL hard-dead
    confirmada (HTTP 404/410 do estágio de vitalidade) e devolve as stats
    do passe::

        {"removed": int, "removed_ids": list[str],
         "removed_entries": list[dict]({"id", "status", "url"}),
         "already_removed": int, "already_removed_ids": list[str],
         "by_status": dict[str, int]}

    O id removido SAI COMPLETAMENTE do eligible_jobs.json (o JSON de
    saída do pipeline não contém hard-dead — nem como vaga, nem como
    registro; contadores e provenance ficam na métrica diária
    ``dead_link_removal`` e no log, padrão F25/hydration_reassessment).
    Idempotente por construção: no re-run sem re-coleta o id já não
    está no JSON/logo não chega ao liveness; id hard-dead ausente do
    ranking (churn da coleta entre o check e a escrita) é contado como
    ``already_removed`` e não gera evento.
    """
    removed_rows: list[dict] = []
    already_ids: list[str] = []
    by_status: dict[str, int] = {}
    for jid in sorted(hard_dead_ids):
        jid = str(jid or "")
        if not jid:
            continue
        idx = next(
            (i for i, rec in enumerate(ranking)
             if isinstance(rec, dict) and str(rec.get("id") or "") == jid),
            None,
        )
        if idx is None:
            # Vaga não está mais no JSON (churn da coleta): exclusão é
            # no-op — idempotência por construção (re-run sem re-coleta
            # nunca re-remove) e nenhum evento inventado.
            already_ids.append(jid)
            continue
        rec = ranking[idx]
        ranking.pop(idx)
        status = int(hard_dead_status.get(jid) or 0)
        removed_rows.append({
            "id": jid, "status": status,
            "url": str(rec.get("url") or ""),
        })
        by_status[str(status)] = by_status.get(str(status), 0) + 1
    return {
        "removed": len(removed_rows),
        "removed_ids": [rec["id"] for rec in removed_rows],
        "removed_entries": removed_rows,
        "already_removed": len(already_ids),
        "already_removed_ids": list(already_ids),
        "by_status": by_status,
    }


def _extract_liveness_details(
        stats: dict | None) -> tuple[set[str], dict[str, int]]:
    """F39 — extrai (hard_dead_ids, hard_dead_status) dos stats do
    ``check_liveness`` (compat graciosa: stats legado/mock sem as chaves
    F39 => conjuntos vazios = nada a excluir; comportamento pré-F39)."""
    stats = stats if isinstance(stats, dict) else {}
    ids = stats.get("hard_dead_ids") or set()
    status = stats.get("hard_dead_status") or {}
    return (
        {str(j) for j in ids if j},
        {str(k): int(v) for k, v in status.items()
         if str(v).lstrip("-").isdigit()},
    )


# ---------------------------------------------------------------------------
# F87 — flag "não-avaliável": detector puro + anotação idempotente. Display
# e digest leem o CAMPO (``not_assessable``), nunca recomputam — os A/B de
# SHA congelado da página continuam byte a byte com fixtures sem o campo,
# e a cura pela hidratação é a recomputação do run seguinte.
# ---------------------------------------------------------------------------
def assessability_reason(job: dict) -> str | None:
    """F87 — motivo do flag "não-avaliável" (pura; ``None`` = avaliável).

    Ordem de diagnóstico (o mais específico primeiro):

    - ``desc_vazia``: descrição ausente/vazia/só-espaço — caso Amazon
      Koblenz (JS-vazio em todas as fontes), TYTAN, Impulsgrad;
    - ``login_wall``: padrão textual de wall/placeholder no corpo
      (``saml``/``anmelden``/``required…sign in``/placeholder "please add
      a text") — o texto que passou é fragmento atrás de autenticação ou
      buraco de template (caso henkel 89300);
    - ``desc_curta``: descrição abaixo de ``ASSESSABLE_MIN_CHARS`` (600,
      Passo 0) — provável truncamento sem os campos de julgamento (caso
      henkel 89534: 584 chars de SAML wall).

    Counter-case (medido, contrato do teste): descrição curta LEGÍTIMA
    (frase completa, 300-500 chars) TAMBÉM acende ``desc_curta`` — o flag
    é SINAL display-only (⚠️ no card + linha no digest), NUNCA exclusão:
    a vaga segue eligible, ranqueada e clicável.
    """
    desc = str(job.get("description") or "")
    if not desc.strip():
        return "desc_vazia"
    if _LOGIN_WALL_RE.search(desc):
        return "login_wall"
    if len(desc) < ASSESSABLE_MIN_CHARS:
        return "desc_curta"
    return None


def _annotate_assessability(ranking: list) -> dict:
    """F87 — anota o flag ``not_assessable`` no ranking (in place).

    Idempotente: recomputa TODO run sobre a lista inteira. O flag acende
    quando a descrição não dá base de julgamento e APAGA quando a
    hidratação (F20 top-N ou F65 estendida) trouxe texto suficiente — a
    cura é efeito colateral da recomputação, sem mecanismo novo. Nada de
    exclusão: ordem, score e emprego ficam intatos (o CSV nem muda — o
    campo é JSON-only, padrão dos flags de hidratação).

    Devolve contadores para log/métrica::

        {"total", "flagged" (novos), "by_reason" (população atual),
         "cleared" (curados), "cleared_ids"}
    """
    total = flagged = cleared = 0
    by_reason: dict[str, int] = {}
    cleared_ids: list[str] = []
    for job in ranking:
        if not isinstance(job, dict):
            continue
        total += 1
        reason = assessability_reason(job)
        had = bool(job.get(NOT_ASSESSABLE_FLAG))
        if reason:
            job[NOT_ASSESSABLE_FLAG] = reason
            by_reason[reason] = by_reason.get(reason, 0) + 1
            if not had:
                flagged += 1
        elif had:
            job.pop(NOT_ASSESSABLE_FLAG, None)
            cleared += 1
            cleared_ids.append(str(job.get("id") or ""))
    return {
        "total": total,
        "flagged": flagged,
        "by_reason": by_reason,
        "cleared": cleared,
        "cleared_ids": cleared_ids,
    }


# ---------------------------------------------------------------------------
# F94 — Liveness v2: estado persistente por vaga + stale_posting (ITEM 1 da
# delegação, o DELTA da F87). A F87 mata/remove mas não deixa estado
# CONSULTÁVEL por vaga; estes annotators gravam o veredito NO REGISTRO
# (``liveness_status: alive|dead|unknown`` + ``liveness_checked_at``) e a
# idade do posting (``stale_posting`` + ``posting_age_days``). Todos
# display/digest-agnósticos: NENHUM filtro/exclusão lê estes campos — a
# semântica de morte/remoção continua EXCLUSIVA dos mecanismos F11/F20/F39.
# ---------------------------------------------------------------------------
LIVENESS_STATUS_FIELD = "liveness_status"
LIVENESS_CHECKED_AT_FIELD = "liveness_checked_at"
# F96 — persistidos junto ao estado (mesmo passe): o DETALHE do veredito
# (o "porquê" — saml wall / http 403 / network / marker) alimenta o motivo
# da fila manual-check, e o ALVO FINAL do redirect segue no registro quando
# a vaga está viva (link direto da fila; final de IdP/homepage nunca vira).
LIVENESS_DETAIL_FIELD = "liveness_detail"
LIVENESS_FINAL_URL_FIELD = "liveness_final_url"
MANUAL_CHECK_FIELD = "manual_check_required"
STALE_POSTING_FIELD = "stale_posting"
POSTING_AGE_DAYS_FIELD = "posting_age_days"

# F94 item 3 — idade do posting por tipo (spec: estágio ~30–45d, permanente
# ~90d). O flag acende no TOPO da janela medida (45d): abaixo disso um
# estágio é idade normal de ciclo (a janela 30–45 é o território de atenção,
# não de flag). Permanente = ``job_type_of == "permanente"`` (F86: sinal
# full-time SEM marcador estudantil); tudo que é estágio-família (None/
# hiwi/werkstudent/tese — o corpus eligible é Praktikum-centríco por
# construção) usa 45d.
STALE_POSTING_DAYS_INTERNSHIP = 45
STALE_POSTING_DAYS_PERMANENT = 90


def _annotate_liveness_state(
    ranking: list, verdicts: dict, manual_ids: set[str], checked_at: str,
) -> dict:
    """F94 item 1 — grava o veredito de liveness NO REGISTRO (in place).

    Para cada vaga CHECADA neste passe (``stats["verdicts"]`` do
    ``url_liveness.check_liveness_v2``): ``liveness_status`` =
    ``alive|dead|unknown`` + ``liveness_checked_at`` (timestamp ISO do
    passe). Vagas NÃO checadas neste run (fora do top/budget) ficam com o
    estado do run anterior — é a PERSISTÊNCIA que a spec pede: estado por
    vaga consultável entre runs. Vagas com wall SAML ganham
    ``manual_check_required: true`` (e o campo APAGA quando um run
    posterior acha a vaga viva — cura idempotente, padrão F87).

    Nada de exclusão aqui: hard-dead sai do JSON pelo mecanismo F39 (o
    annotator roda antes e o registro removido leva o veredito junto);
    soft-dead/unknown/alive ficam no JSON com o estado honesto.

    Devolve contadores::  {"annotated", "alive", "dead", "unknown",
    "manual_check_required"}
    """
    by_id: dict[str, dict] = {}
    for job in ranking:
        if isinstance(job, dict):
            jid = str(job.get("id") or "")
            if jid and jid not in by_id:
                by_id[jid] = job
    manual = set(str(i) for i in (manual_ids or()))
    annotated = alive = dead = unknown = manual_n = 0
    for raw_id, raw_verdict in (verdicts or {}).items():
        job = by_id.get(str(raw_id))
        if job is None:
            continue  # id fora do ranking (ex.: já removido por F39)
        verdict = raw_verdict if isinstance(raw_verdict, dict) else {}
        status = str(verdict.get("status") or "").strip().lower()
        if status not in ("alive", "dead", "unknown"):
            continue  # veredito malformado: estado anterior permanece
        job[LIVENESS_STATUS_FIELD] = status
        job[LIVENESS_CHECKED_AT_FIELD] = checked_at
        # F96 — detalhe do veredito consultável (motivo da fila manual-check
        # lê isto) + alvo final do redirect quando a vaga está VIVA (o
        # "link direto" da fila). ``alive`` gerencia o campo do alvo: sem
        # redirect no run => campo apaga (cura idempotente, padrão F87);
        # dead/unknown mantêm o anterior (persistência F94 — veredito de
        # hoje não apaga evidência de ontem).
        job[LIVENESS_DETAIL_FIELD] = str(verdict.get("detail") or "")
        verdict_final = str(verdict.get("final_url") or "").strip()
        if status == "alive" and verdict_final:
            job[LIVENESS_FINAL_URL_FIELD] = verdict_final
        elif status == "alive":
            job.pop(LIVENESS_FINAL_URL_FIELD, None)
        annotated += 1
        if status == "alive":
            alive += 1
        elif status == "dead":
            dead += 1
        else:
            unknown += 1
        if status == "unknown" and str(raw_id) in manual:
            job[MANUAL_CHECK_FIELD] = True
            manual_n += 1
        else:
            # cura idempotente: wall SAML saiu (run achou a vaga) => flag apaga
            job.pop(MANUAL_CHECK_FIELD, None)
    return {
        "annotated": annotated, "alive": alive, "dead": dead,
        "unknown": unknown, "manual_check_required": manual_n,
    }


def posting_age_days(job: dict, now: datetime, first_seen: str | None = None):
    """F94 item 3 — idade do posting em dias (pura; evidência primeiro).

    Fonte primária: ``posted_at`` JÁ COLETADO pela pipeline (nunca
    inferido). Fallback: ``first_seen`` do caderno F70
    (``dataset_seen.db`` — o universo dataset pós-prefilter; vagas sem
    posted_at no feed ganham a idade da primeira aparição). Sem nenhuma
    das duas => ``None``: SEM evidência de idade nada é flagrado
    (AGENTS.md: ausência vale ``None``, nunca dado fabricado).

    Devolve ``(idade_em_dias, fonte)`` com fonte
    ``"posted_at"|"first_seen"``; idades negativas (clock skew/posting no
    futuro) viram 0. Aceita ISO com timezone (shape real do JSON) e sem
    (assumida UTC).
    """
    posted = str(job.get("posted_at") or "").strip()
    seen = str(first_seen or "").strip()
    for source, raw in (("posted_at", posted), ("first_seen", seen)):
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(raw)
        except ValueError:
            continue  # ilegível => tenta o fallback, nunca inventa
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        age = (now - ts).total_seconds() / 86400.0
        return (max(age, 0.0), source)
    return None


def stale_posting_threshold_days(job: dict) -> int:
    """F94 item 3 — limite de idade por tipo de vaga (pura).

    ``permanente`` (F86 ``job_type_of``) => 90d; o resto do corpus
    (estágio-família: Praktikum/intern, hiwi, werkstudent, tese) => 45d.
    Falha de import => 45d (o Limiar conservador do estágio — nunca
    derruba o run).
    """
    try:
        from internship_finder.filters import job_type_of
        if job_type_of(job.get("title"), job.get("description")) == "permanente":
            return STALE_POSTING_DAYS_PERMANENT
    except Exception:  # noqa: BLE001 — detector é sinal, nunca gate
        pass
    return STALE_POSTING_DAYS_INTERNSHIP


def _annotate_stale_posting(
    ranking: list, now: datetime, seen_db_path=None,
) -> dict:
    """F94 item 3 — flag ``stale_posting`` por tipo NO REGISTRO (in place).

    Idempotente: recomputa TODO run sobre a lista inteira — acende acima
    do limite do tipo (45d estágio / 90d permanente) e APAGA quando a
    idade volta para baixo (re-post zera ``posted_at``; a cura é
    efeito colateral da recomputação, padrão F87). O flag é SINAL
    (display/digest leem o CAMPO, nunca recomputam; NUNCA exclusão —
    vaga velha pode estar VIVA, o caso Lidl re-post). Sem evidência de
    idade (sem posted_at E sem caderno) => campos APAGADOS, vaga
    intocada. Zero rede; best-effort TOTAL.

    Devolve contadores para log/métrica::
        {"total", "stale", "cleared", "no_evidence", "by_source",
         "by_threshold"}
    """
    from internship_finder.dataset_seen import job_seen_history
    total = stale = cleared = no_evidence = 0
    by_source: dict[str, int] = {}
    by_threshold: dict[str, int] = {}
    for job in ranking:
        if not isinstance(job, dict):
            continue
        total += 1
        first_seen = None
        jid = str(job.get("id") or "")
        if seen_db_path is not None and jid:
            history = job_seen_history(seen_db_path, jid)
            if history is not None:
                first_seen = history[0]
        age = posting_age_days(job, now, first_seen)
        if age is None:
            if STALE_POSTING_FIELD in job or POSTING_AGE_DAYS_FIELD in job:
                cleared += 1  # tinha flag de run anterior, perdeu a evidência
            job.pop(STALE_POSTING_FIELD, None)
            job.pop(POSTING_AGE_DAYS_FIELD, None)
            no_evidence += 1
            continue
        age_days, source = age
        by_source[source] = by_source.get(source, 0) + 1
        threshold = stale_posting_threshold_days(job)
        by_threshold[str(threshold)] = by_threshold.get(str(threshold), 0) + 1
        if age_days > threshold:
            job[STALE_POSTING_FIELD] = True
            job[POSTING_AGE_DAYS_FIELD] = int(age_days)
            stale += 1
        else:
            if STALE_POSTING_FIELD in job or POSTING_AGE_DAYS_FIELD in job:
                cleared += 1
            job.pop(STALE_POSTING_FIELD, None)
            job.pop(POSTING_AGE_DAYS_FIELD, None)
    return {
        "total": total, "stale": stale, "cleared": cleared,
        "no_evidence": no_evidence, "by_source": by_source,
        "by_threshold": by_threshold,
    }


def _reassess_hydrated_applicability(job: dict) -> str | None:
    """F20 item 3 — re-avalia a aplicabilidade da vaga com a descricao
    hidratada, REUSANDO a funcao pura da cascata (F18 + F37:
    ``filters.applicability_exclusion_reason`` verbatim). Devolve o motivo
    de inaplicabilidade ("german_required"/"master_required"/... F37) ou
    None (aplicavel).

    F37 (14/10): a re-avaliacao herda o MESMO veredito dos filtros do
    pipeline — a funcao completa, nao apenas german/master. Os dois call
    sites (select_eligible do pipeline e este) sempre concordam por
    construcao.

    So olha titulo + descricao HIDRATADA (o texto que a hidratacao
    revelou — o ponto do estagio). Falha de import = None (nunca derruba;
    a vaga fica como estava).
    """
    try:
        from internship_finder.filters import applicability_exclusion_reason
        return applicability_exclusion_reason(job)
    except Exception:  # noqa: BLE001 — re-avaliacao nunca derruba o estagio
        return None


def _reassess_backlog_applicability(ranking: list) -> dict:
    """F25 — re-avalia a aplicabilidade do BACKLOG inteiro de vagas
    hidratadas, REUSANDO a mesma re-avaliacao da F20
    (``_reassess_hydrated_applicability`` -> detetores puros da F18).

    Fecha o buraco do estagio Fase A: ``hydrate_descriptions`` roda DEPOIS
    de ``filters.select_eligible`` e nunca re-avalia — vagas cuja descricao
    hidratada revela german/master required ficavam no backlog sem marcador
    (medição 12/10: 126 de 783 no eligible real, 16,1%, incluindo o topo do
    ranking). Candidatos deste passe: TODAS as vagas com
    ``description_source == "hydration"`` (a provenance da Fase A, gravada
    por ``internship_finder.hydration.hydrate_descriptions``) que AINDA NAO
    tem ``hydration_inapplicable`` — ja-flagadas nunca re-flagam
    (idempotente). Vagas NAO-hidratadas NUNCA sao tocadas: sem a descricao
    completa o detetor e executado sobre evidencia parcial e o F18 ja
    cuidou do feed.

    Mutacao in place (mesma lista, mesma ordem, nenhum outro campo); a
    persistencia atomica e responsabilidade do chamador (mecanica
    ``_write_json_atomic`` existente). Devolve os counts do passe::
    ``{"reassessed": N, "newly_flagged": M, "by_reason": {...}}``.
    """
    reassessed = 0
    newly_flagged = 0
    by_reason: dict[str, int] = {}
    for job in ranking:
        if not isinstance(job, dict):
            continue
        if job.get("description_source") != "hydration":
            continue
        if job.get(HYDRATION_INAPPLICABLE_FLAG):
            continue
        reassessed += 1
        reason = _reassess_hydrated_applicability(job)
        if reason:
            job[HYDRATION_INAPPLICABLE_FLAG] = reason
            newly_flagged += 1
            by_reason[reason] = by_reason.get(reason, 0) + 1
    return {"reassessed": reassessed, "newly_flagged": newly_flagged,
            "by_reason": by_reason}


def _remove_json_excluded(ranking: list) -> dict:
    """F37.3 — EXCLUSÃO TOTAL do eligible (decisão do dono 15/10: "german_
    required: exclusão total aprovada"). Remove do ``ranking`` (in place) as
    vagas cujo motivo de inaplicabilidade — o flag F20/F25
    ``hydration_inapplicable``, atribuído pelo detector ÚNICO
    ``filters.applicability_exclusion_reason`` — está em
    ``filters.APPLICABILITY_JSON_EXCLUSION_REASONS`` (hoje ``german_required``).

    Mesmo caminho de exclusão do eligible da F39 (``_remove_hard_dead``): o id
    SAI do ``eligible_jobs.json`` e a provenance fica na métrica diária
    ``applicability_exclusion`` (motivo + contadores por motivo + ids/entradas).
    Diferença: a F39 mexe no que a coleta entrega (URL morta); aqui só muda o
    que PERMANECE no arquivo de saída — score, ordem e coleta intocados.

    Lê o flag já atribuído (o MESMO veredito do detector único) e NÃO
    re-executa o detector: nenhum segundo mecanismo. Motivos fora do
    subconjunto (master_required, thesis_title, ...) mantêm o design F25
    intacto — ficam no JSON com a flag e só descem do topo exibido.
    Idempotente: re-run sobre o JSON já limpo não acha flag => 0 removidos,
    sem evento inventado.

    Devolve ``{"removed", "removed_ids", "removed_entries", "by_reason"}``;
    ``removed_entries`` = ``[{"id","reason","company","title"}]`` (auditável).
    """
    from internship_finder.filters import is_json_exclusion_reason

    removed: list[dict] = []
    kept: list = []
    for job in ranking:
        reason = (
            job.get(HYDRATION_INAPPLICABLE_FLAG)
            if isinstance(job, dict) else None
        )
        if is_json_exclusion_reason(reason):
            removed.append({
                "id": str(job.get("id") or ""),
                "reason": str(reason),
                "company": str(job.get("company") or ""),
                "title": str(job.get("title") or ""),
            })
        else:
            kept.append(job)
    if removed:
        ranking[:] = kept
    by_reason: dict[str, int] = {}
    for entry in removed:
        by_reason[entry["reason"]] = by_reason.get(entry["reason"], 0) + 1
    return {
        "removed": len(removed),
        "removed_ids": [entry["id"] for entry in removed],
        "removed_entries": removed,
        "by_reason": by_reason,
    }


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


# ---------------------------------------------------------------------------
# F65 — hidratacao estendida (alem do top exibido) com teto de fetches/dia
# ---------------------------------------------------------------------------


def _hydration_budget(
    config_path: Path | str | None,
    *,
    flag: str = HYDRATION_BUDGET_ENV_FLAG,
) -> int:
    """Teto diario de fetches de um estagio de hidratacao (pura).

    Fonte (mesmo padrao do gate F1 ``ENRICHMENT_ENV_FLAG``): env herdada
    OU a MESMA chave no ``.env`` (``load_env_config``); a env tem
    precedencia sobre o arquivo. Parse FAIL-SAFE: ausente, vazia,
    nao-inteira ou negativa => ``0`` (OFF). Default OFF (regra 9): zero
    mudanca de comportamento ate o dono ligar — ``0`` = o estagio nem le
    o JSON (byte-identical garantido).

    ``flag`` (F91): chave lida — default o knob historico do F65
    (``INTERNSHIP_FINDER_HYDRATION_BUDGET``, tambem compartilhado pelo
    intake F87); o estagio dos cegos passa o budget PROPRIO
    (``BLIND_HYDRATION_BUDGET_ENV_FLAG``).
    """
    raw = os.environ.get(flag)
    if raw is None and config_path is not None:
        try:
            raw = load_env_config(config_path).get(flag)
        except Exception:  # noqa: BLE001 — .env ilegivel => OFF, nunca derruba
            return 0
    if raw is None:
        return 0
    try:
        return max(0, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 0


def _extended_hydration_candidates(
    ranking: list,
    shown_ids: "set[str]",
    *,
    short_description_limit: int = HYDRATION_SHORT_LIMIT,
) -> list:
    """F65 — candidatas da janela estendida (pura, offline-testavel).

    Ordem OFICIAL do ranking preservada (a lista vem ordenada do
    ``rank_jobs``/F56 = score desc) — hidratacao "as melhores primeiro"
    (spec F65). Candidata = vaga FORA do top exibido (``shown_ids``) com
    description curta/vazia (< ``short_description_limit`` chars, o MESMO
    limite da F20). O topo nunca entra: o passe F20 ja gastou 1 fetch nele
    neste run — a janela estendida e exatamente "tudo que a F20 NAO cobre"
    (sem double fetch, sem re-decidir o corte do topo).
    """
    candidates: list[dict] = []
    for job in ranking:
        if not isinstance(job, dict):
            continue
        jid = str(job.get("id") or "")
        if not jid or jid in shown_ids:
            continue
        desc = job.get("description")
        if desc is None or len(str(desc)) < short_description_limit:
            candidates.append(job)
    return candidates


def _run_extended_hydration(
    data_dir: Path,
    metrics_path: Path,
    *,
    run_id: str | None = None,
    config_path: Path | str | None = None,
    log=None,
    opener=None,
    budget_override: int | None = None,
) -> dict:
    """F65 — estagio de hidratacao estendida (alem do top exibido).

    F87: ``budget_override`` = poço COMPARTILHADO — o liveness de intake
    (mesmo knob, mesmo run) gasta primeiro e o que sobrou chega aqui
    (``main`` passa o restante; ``None`` = comportamento F65 exato, lê o
    knob direto — usado pelos testes/chamadas avulsas).

    Fecha a classe B da F60: vagas com description curta/vazia fora da
    janela F20 (top exibido) ficavam CEGAS aos detectores F60/F61 mesmo
    com a pagina viva expondo o texto (caso Lidl ``praktikum_info:
    13308116``). Este estagio reusa o passe GET do ``url_liveness``
    (liveness + parse JSON-LD F22, 1 fetch sequencial por vaga, timeout/
    delay/UA herdados) sobre as candidatas em ordem de score, ate o teto
    ``INTERNSHIP_FINDER_HYDRATION_BUDGET`` fetches/dia.

    Contrato:

    - **Flag-gated + kill switch (regra 9)**: budget 0/ausente/invalido
      => UMA linha de log e retorno imediato — nenhum fetch, nenhuma
      leitura de arquivo, JSON byte-identical (comportamento F20 exato).
    - **Provenance**: vaga hidratada ganha ``description_source=
      "hydrated_extended"`` + ``description_hydrated_at`` (distinta da
      top-N ``"hydrated_topn"``; a F25 do backlog "hydration" nao toca).
    - **Re-avaliacao honesta**: a MESMA ``_reassess_hydrated_applicability``
      da F20 roda sobre o texto revelado — german_required acende e a
      varredura F37.3 (que roda DEPOIS deste estagio no main) remove do
      JSON; outros motivos so demovem do top exibido (semantica F25).
    - **F56**: score recomputado SOMENTE das hidratadas (a causa real —
      a descricao mudou) e lista reordenada com o desempate oficial.
    - **Mortas NAO sao marcadas aqui**: o veredito de morte do passe
      estendido e apenas CONTADO (``dead_seen``) — a semantica de morte
      (badge/remocao F39) pertence a janela do topo; a janela estendida
      so hidrata (o corpo morto nunca hidrata, pelo proprio gate do
      url_liveness). Vagas 410 voltam a ser candidatas amanha (o slice
      diario recria o JSON) — custo limitado pelo budget, documentado.
    - **Best-effort TOTAL**: qualquer falha vira log/retorno parcial; o
      exit code do refresh NUNCA muda por causa deste estagio. Escrita
      atomica (JSON+CSV) reusando o padrao da F20 (store atomico).
    - ``opener`` injetavel (testes/CI sem rede; default urlopen).

    Devolve o dict de contadores gravado na metrica ``extended_hydration``
    (``{"budget", "blind_candidates", "fetched", "hydrated", ...}``);
    ``{"budget": 0, "status": "off"}`` quando desligado.
    """
    def _info(msg: str, *args) -> None:
        if log is not None:
            log.info(msg, *args)
        else:
            print("F65: " + (msg % args if args else msg))

    def _warn(msg: str, *args) -> None:
        if log is not None:
            log.warning(msg, *args)
        else:
            print("F65(WARN): " + (msg % args if args else msg))

    budget = (_hydration_budget(config_path)
              if budget_override is None else max(0, int(budget_override)))
    if budget <= 0:
        _info("hidratacao estendida DESLIGADA (default OFF; ligue com %s=N "
              "no .env — N fetches/dia, regra 9: budget 0 = comportamento "
              "F20 exato)", HYDRATION_BUDGET_ENV_FLAG)
        return {"budget": 0, "status": "off"}

    eligible_path = data_dir / "eligible_jobs.json"
    try:
        ranking = json.loads(
            eligible_path.read_text(encoding="utf-8")
        ) if eligible_path.exists() else []
    except Exception as exc:  # noqa: BLE001 — JSON ilegivel => estagio pula
        _warn("hidratacao estendida: %s ilegivel (%s: %s) — estagio pulado",
              eligible_path, type(exc).__name__, exc)
        return {"budget": budget, "status": "unreadable_eligible"}

    shown_ids = {
        str(j.get("id") or "")
        for j in minimal_page.apply_company_cap(ranking)
        if isinstance(j, dict)
    } - {""}
    candidates = _extended_hydration_candidates(ranking, shown_ids)
    fetched = candidates[:budget]

    t0 = time.monotonic()
    record = {
        "type": "extended_hydration",
        "run_id": run_id or utcnow_iso(),
        "timestamp": utcnow_iso(),
        "budget": budget,
        "blind_candidates": len(candidates),
        "fetched": len(fetched),
        "hydrated": 0,
        "hydration_failed": 0,
        "dead_seen": 0,
        "newly_inapplicable": 0,
        "by_reason": {},
        "duration_s": 0.0,
    }
    if fetched:
        dead_ext, bodies, liveness_stats = url_liveness.check_liveness_v2(
            fetched,
            deadline_s=EXTENDED_HYDRATION_DEADLINE_S,
            log=log,
            opener=opener,
            want_bodies=True,
            short_description_limit=HYDRATION_SHORT_LIMIT,
        )
        hydrated_ids: set[str] = set()
        by_reason: dict[str, int] = {}
        for job in fetched:
            jid = str(job.get("id") or "")
            new_desc = bodies.get(jid)
            if not new_desc:
                continue
            job["description"] = new_desc
            job["description_source"] = HYDRATION_SOURCE_EXTENDED
            job["description_hydrated_at"] = utcnow_iso()
            hydrated_ids.add(jid)
            reason = _reassess_hydrated_applicability(job)
            if reason:
                job[HYDRATION_INAPPLICABLE_FLAG] = reason
                by_reason[reason] = by_reason.get(reason, 0) + 1
                _info("hidratacao estendida revelou %s em %s — desce do "
                      "topo exibido (german_required sai na varredura "
                      "F37.3 deste run)", reason, jid)
        # Mortas do passe estendido NUNCA sao marcadas (janela do topo e
        # dona da semantica de morte) — so contadas para o relatorio.
        record.update({
            "hydrated": len(hydrated_ids),
            "hydrated_ids": sorted(hydrated_ids),
            "hydration_failed": int(liveness_stats.get(
                "hydration_failed", 0) or 0),
            "dead_seen": len(dead_ext),
            "newly_inapplicable": sum(by_reason.values()),
            "by_reason": by_reason,
            "duration_s": round(time.monotonic() - t0, 1),
        })
        if hydrated_ids:
            # F56 — re-score APENAS das hidratadas estendidas (mesma causa
            # real da F20: a descricao mudou) + reordenacao oficial.
            try:
                rescored = rescore_hydrated_jobs(
                    ranking, hydrated_ids, now=datetime.now(UTC))
                _info("F56: score recomputado para %d vaga(s) hidratada(s) "
                      "pela janela estendida", rescored)
            except Exception as exc:  # noqa: BLE001 — re-score nunca derruba
                _warn("F65: re-score pos-hidratacao falhou (JSON segue com "
                      "scores pre-hidratacao): %s: %s",
                      type(exc).__name__, exc)
            # Persistencia atomica (padrao F20): JSON + CSV (score e coluna
            # do contrato CSV — mesmo cuidado da F56 top-N). Falha de
            # escrita NUNCA derruba o run.
            try:
                from internship_finder.cli import (_write_json_atomic,
                                                   _write_atomic,
                                                   _dump_csv)
                _write_json_atomic(ranking, eligible_path)
                _write_atomic(
                    eligible_path.with_suffix(".csv"),
                    lambda fh: _dump_csv(fh, ranking))
                _info("F65: %d descricao(oes) estendida(s) persistida(s) "
                      "em %s", len(hydrated_ids), eligible_path)
            except Exception as exc:  # noqa: BLE001
                _warn("F65: hidratacao estendida nao persistida (JSON "
                      "segue com descricoes originais): %s: %s",
                      type(exc).__name__, exc)
        _info("estagio F65 (hidratacao estendida): budget=%d, %d cega(s), "
              "%d fetch(es), %d hidratada(s), %d inaplicavel(is) novo(s), "
              "%d morta(s) vista(s) (nao marcadas), %.1fs",
              budget, len(candidates), record["fetched"], record["hydrated"],
              record["newly_inapplicable"], record["dead_seen"],
              record["duration_s"])
    else:
        _info("hidratacao estendida: 0 candidata(s) cega(s) fora do top "
              "exibido neste run (budget %d intocado)", budget)

    try:
        from internship_finder.metrics import write_metrics
        write_metrics(metrics_path, [record])
    except Exception as exc:  # noqa: BLE001 — metrica e best-effort
        _warn("F65: metrica extended_hydration nao gravada: %s: %s",
              type(exc).__name__, exc)
    return record


# ---------------------------------------------------------------------------
# F91 — hidratacao dos CEGOS (desc-empty) por pagina publica com JSON-LD.
# ---------------------------------------------------------------------------

def _blind_hydration_candidates(
    ranking: list,
    *,
    limit: int = BLIND_DESCRIPTION_LIMIT,
    sources: tuple[str, ...] = BLIND_HYDRATION_SOURCES,
) -> dict[str, list]:
    """F91 — candidatas do estagio dos cegos (pura, offline-testavel).

    Cega = description com menos de ``limit`` chars (limiar da spec F91,
    <50) — SEM texto util para os detectores (skills/idioma ficam no
    estado default). O corte e por COMPRIMENTO, nao por provenance: vaga
    com description curtissima de qualquer fonte continua cega e pode
    ser curada (o preenchimento so acontece se o texto novo for MAIOR —
    nunca piora).

    Ordem OFICIAL do ranking preservada dentro de cada fonte (a lista
    vem ordenada do ``rank_jobs``/F56 = score desc — "as melhores
    primeiro", spec F91 item 2). Fontes agrupadas na ordem de prioridade
    de ``sources`` (volume curavel medido no Passo 0: absolventa 30 >
    praktikum_info 1; sf_dataset:bundesagentur fora — mortas na fonte).

    Devolve ``{fonte: [vagas...]}; as fontes fora da lista ficam de fora
    (contadas pelo chamador para o relatorio, nunca fetchadas).
    """
    by_source: dict[str, list] = {s: [] for s in sources}
    for job in ranking:
        if not isinstance(job, dict):
            continue
        desc = job.get("description")
        if desc is not None and len(str(desc)) >= limit:
            continue
        src = str(job.get("source") or "")
        if src in by_source:
            by_source[src].append(job)
    return by_source


def _default_blind_fetch_page(
    url: str,
    *,
    timeout: float = BLIND_HYDRATION_TIMEOUT_S,
    max_bytes: int = BLIND_HYDRATION_MAX_BYTES,
) -> str | None:
    """F91 — GET da pagina da vaga (default injetavel; None em falha).

    Boards atendidos (absolventa/praktikum_info) servem HTML estatico
    com JSON-LD (sem parede JS — Passo 0: 31/31 fetchaveis). UA explicito
    do projeto (mesma string do ``direct_fetch``), timeout curto, corpo
    lido com cap ``max_bytes``. Erro/timeout/HTTP != 200 => ``None``
    (o chamador conta ``failed`` e preserva a vaga — Fase A pattern).
    """
    if not url or not str(url).startswith(("http://", "https://")):
        return None
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": ("internship-finder/0.1 "
                           "(daily public-source fetch; contact: repo owner)"),
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(max_bytes + 1)
        if len(body) > max_bytes:
            log.warning("F91: corpo de %s excede %d bytes — truncado",
                        str(url).split("?")[0], max_bytes)
            body = body[:max_bytes]
        return body.decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 — best-effort por vaga
        log.warning("F91: GET %s falhou: %s",
                    str(url).split("?")[0], exc)
        return None


def _run_blind_hydration(
    data_dir: Path,
    metrics_path: Path,
    *,
    run_id: str | None = None,
    config_path: Path | str | None = None,
    log=None,
    fetch_page=None,
    budget_override: int | None = None,
) -> dict:
    """F91 — estagio de hidratacao dos cegos (desc-empty do pool).

    Terceiro estagio flag-gated (padrao F65), budget PROPRIO
    (``INTERNSHIP_FINDER_BLIND_HYDRATION_BUDGET``; default 0 = OFF,
    regra 9 — zero fetch, JSON byte-identical). Roda DEPOIS do F20
    (top) e do F65 (janela estendida): pega o que AINDA esta cego —
    fontes cujo texto so existe na pagina propria (absolventa/
    praktikum_info) e cujo JSON-LD malformado so parseia com o fix
    leniente F91 do ``url_liveness``. O topo exibido ENTRA (o F20 busca
    a pagina destas fontes e falha no parse estrito — o fetch do F91 e
    parse leniente, nao double-fetch do mesmo recurso util).

    Por vaga: fetch da pagina -> ``parse_job_description`` (gates F22:
    JSON-LD JobPosting >= 120 chars, cap 16 KB, so se maior que a atual)
    -> description preenchida + provenance ``hydrated_blind`` ->
    re-avaliacao honesta (``_reassess_hydrated_applicability``: texto
    que revela ``german_required`` ganha o marcador e desce do topo —
    a varredura F37.3 deste run remove em sequencia). Re-score F56 das
    hidratadas + persistencia atomica JSON/CSV (score e coluna do
    contrato CSV). Falha de fetch/parse: vaga preservada + contador
    ``failed`` da fonte (Fase A pattern) — NUNCA derruba o run.

    Devolve o registro gravado na metrica ``blind_hydration``;
    ``{"budget": 0, "status": "off"}`` quando desligado.
    """
    def _info(msg: str, *args) -> None:
        if log is not None:
            log.info(msg, *args)
        else:
            print("F91: " + (msg % args if args else msg))

    def _warn(msg: str, *args) -> None:
        if log is not None:
            log.warning(msg, *args)
        else:
            print("F91(WARN): " + (msg % args if args else msg))

    budget = (_hydration_budget(config_path, flag=BLIND_HYDRATION_BUDGET_ENV_FLAG)
              if budget_override is None else max(0, int(budget_override)))
    if budget <= 0:
        _info("hidratacao dos cegos DESLIGADA (default OFF; ligue com "
              "%s=N no .env — N fetches/dia, regra 9: budget 0 = JSON "
              "byte-identical)",
              BLIND_HYDRATION_BUDGET_ENV_FLAG)
        return {"budget": 0, "status": "off"}

    eligible_path = data_dir / "eligible_jobs.json"
    try:
        ranking = json.loads(
            eligible_path.read_text(encoding="utf-8")
        ) if eligible_path.exists() else []
    except Exception as exc:  # noqa: BLE001 — JSON ilegivel => estagio pula
        _warn("hidratacao dos cegos: %s ilegivel (%s: %s) — estagio pulado",
              eligible_path, type(exc).__name__, exc)
        return {"budget": budget, "status": "unreadable_eligible"}

    fetch = fetch_page or _default_blind_fetch_page
    by_source = _blind_hydration_candidates(ranking)
    blind_total = sum(
        1 for j in ranking
        if isinstance(j, dict) and (
            j.get("description") is None
            or len(str(j.get("description"))) < BLIND_DESCRIPTION_LIMIT)
    )

    t0 = time.monotonic()
    record = {
        "type": "blind_hydration",
        "run_id": run_id or utcnow_iso(),
        "timestamp": utcnow_iso(),
        "budget": budget,
        "blind_total": blind_total,
        "candidates": sum(len(v) for v in by_source.values()),
        "by_source": {
            s: {"candidates": len(v), "fetched": 0, "hydrated": 0,
                "failed": 0, "skipped": 0}
            for s, v in by_source.items()
        },
        "fetched": 0,
        "hydrated": 0,
        "failed": 0,
        "newly_inapplicable": 0,
        "by_reason": {},
        "duration_s": 0.0,
    }
    hydrated_ids: set[str] = set()
    by_reason: dict[str, int] = {}
    remaining = budget

    for source in BLIND_HYDRATION_SOURCES:
        for job in by_source.get(source, []):
            if remaining <= 0:
                record["by_source"][source]["skipped"] += 1
                continue
            if time.monotonic() - t0 > BLIND_HYDRATION_DEADLINE_S:
                _warn("estagio dos cegos: teto de %.0fs atingido — %d "
                      "candidata(s) restante(s) ficam cegas ate o proximo "
                      "run", BLIND_HYDRATION_DEADLINE_S,
                      sum(len(v) for v in by_source.values()) - record["fetched"])
                remaining = 0
                record["by_source"][source]["skipped"] += 1
                continue
            entry = record["by_source"][source]
            entry["fetched"] += 1
            record["fetched"] += 1
            remaining -= 1
            jid = str(job.get("id") or "")
            current = str(job.get("description") or "")
            try:
                html = fetch(str(job.get("url") or ""))
                new_desc = url_liveness.parse_job_description(html) \
                    if html else None
            except Exception as exc:  # noqa: BLE001 — por vaga, nunca fatal
                _warn("hidratacao dos cegos: %s falhou (%s: %s) — vaga "
                      "preservada", jid, type(exc).__name__, exc)
                new_desc = None
            if not new_desc or len(new_desc) <= len(current):
                entry["failed"] += 1
                record["failed"] += 1
                continue
            job["description"] = new_desc
            job["description_source"] = HYDRATION_SOURCE_BLIND
            job["description_hydrated_at"] = utcnow_iso()
            hydrated_ids.add(jid)
            entry["hydrated"] += 1
            reason = _reassess_hydrated_applicability(job)
            if reason:
                job[HYDRATION_INAPPLICABLE_FLAG] = reason
                by_reason[reason] = by_reason.get(reason, 0) + 1
                _info("hidratacao dos cegos revelou %s em %s — desce do "
                      "topo exibido (varredura F37.3 deste run remove do "
                      "JSON)", reason, jid)

    record.update({
        "hydrated": len(hydrated_ids),
        "hydrated_ids": sorted(hydrated_ids),
        "newly_inapplicable": sum(by_reason.values()),
        "by_reason": by_reason,
        "duration_s": round(time.monotonic() - t0, 1),
    })
    if hydrated_ids:
        # F56 — re-score APENAS das hidratadas (causa real: a descricao
        # mudou) + reordenacao oficial. Best-effort: falha NUNCA derruba.
        try:
            rescored = rescore_hydrated_jobs(
                ranking, hydrated_ids, now=datetime.now(UTC))
            _info("F56: score recomputado para %d vaga(s) hidratada(s) "
                  "pelo estagio dos cegos", rescored)
        except Exception as exc:  # noqa: BLE001 — re-score nunca derruba
            _warn("F91: re-score pos-hidratacao falhou (JSON segue com "
                  "scores pre-hidratacao): %s: %s", type(exc).__name__, exc)
        # Persistencia atomica (padrao F65): JSON + CSV (score e coluna do
        # contrato CSV — mesmo cuidado da F56 top-N). Falha NUNCA derruba.
        try:
            from internship_finder.cli import (_write_json_atomic,
                                               _write_atomic,
                                               _dump_csv)
            _write_json_atomic(ranking, eligible_path)
            _write_atomic(
                eligible_path.with_suffix(".csv"),
                lambda fh: _dump_csv(fh, ranking))
            _info("F91: %d descricao(oes) de cegas persistida(s) em %s",
                  len(hydrated_ids), eligible_path)
        except Exception as exc:  # noqa: BLE001
            _warn("F91: hidratacao dos cegos nao persistida (JSON segue "
                  "com descricoes originais): %s: %s",
                  type(exc).__name__, exc)
        # Cura do flag F87 e automatica: _annotate_assessability (mais
        # abaixo no run) recomputa TODO ranking DEPOIS deste estagio e
        # apaga not_assessable das vagas que ganharam texto suficiente.
    _info("estagio F91 (cegos): budget=%d, %d cega(s) total(is), %d "
          "candidata(s), %d fetch(es), %d hidratada(s), %d falha(s), %d "
          "inaplicavel(is) novo(s), %.1fs",
          budget, record["blind_total"], record["candidates"],
          record["fetched"], record["hydrated"], record["failed"],
          record["newly_inapplicable"], record["duration_s"])

    try:
        from internship_finder.metrics import write_metrics
        write_metrics(metrics_path, [record])
    except Exception as exc:  # noqa: BLE001 — metrica e best-effort
        _warn("F91: metrica blind_hydration nao gravada: %s: %s",
              type(exc).__name__, exc)
    return record


def _intake_liveness(
    data_dir: Path,
    archive_dir: Path,
    metrics_path: Path,
    *,
    run_id: str | None = None,
    config_path: Path | str | None = None,
    log=None,
    opener=None,
) -> dict:
    """F87 — liveness no 1º sighting: 1 fetch barato por candidata NOVA.

    As duas mortas do registro (Festo St. Ingbert, Simvia) gastaram
    análise do dono porque o ``url_liveness`` (F11/F20) só roda no top
    EXIBIDO — a vaga entra, sobe e é analisada antes de qualquer check.
    Este estágio roda ANTES da janela de análise, sobre as candidatas
    NOVAS (primeira aparição do ID contra o snapshot arquivado da rotação
    — MESMO diff ``new_since_previous`` do digest, que cobre ids
    ``sf_dataset:``/``direct:`` que nunca passam pelo SQLite), e reusa a
    maquinaria do ``url_liveness`` (MESMO passe GET, timeout 5s, UA
    honesto, 1 request por vaga).

    Contrato:

    - **Budget-limited (herdado do F65, regra 9)**: o MESMO knob
      ``INTERNSHIP_FINDER_HYDRATION_BUDGET`` governa os dois estágios —
      0/ausente/inválido => UMA linha de log e retorno imediato (nenhum
      fetch, JSON byte-identical). O ``main`` abate o gasto do intake do
      F65 no mesmo run (um só poço diário).
    - **Hard-dead (404/410) => mecanismo F39**: ``_remove_hard_dead`` no
      ranking + reescrita atômica do JSON — a vaga NÃO entra na janela
      de análise como avaliável (o respetivo kill switch da F39 vale).
    - **200-falso textual (Festo "bereits besetzt") => morta para
      display**: entra no conjunto de mortas que desce do top exibido e
      ganha 🔗; FICA no JSON (semântica F20/F39: remoção do JSON é
      exclusiva do hard-dead — o corpo 200 transitório pode ser FP).
    - **Timeout/DNS/403/429 NUNCA provam morte**: ignorados pelo estágio
      (padrão F11/F20 — nada de falso-positivo por rede).
    - **Sem baseline (primeiro run)**: sem snapshot arquivado não há
      como estabelecer "nova" — nada é checado (o diff começa no run
      seguinte, MESMO contrato do digest; nunca varrer o corpus inteiro).
    - **Best-effort TOTAL**: qualquer falha vira log/retorno parcial; o
      exit code do refresh NUNCA muda por causa deste estágio.
    - ``opener`` injetável (testes/CI sem rede; default urlopen).

    Devolve o dict gravado na métrica ``intake_liveness`` (com
    ``dead_ids`` — lista — para o chamador unir às superfícies exibidas);
    ``{"budget": 0, "status": "off"}`` quando desligado.
    """
    def _info(msg: str, *args) -> None:
        if log is not None:
            log.info(msg, *args)
        else:
            print("F87: " + (msg % args if args else msg))

    def _warn(msg: str, *args) -> None:
        if log is not None:
            log.warning(msg, *args)
        else:
            print("F87(WARN): " + (msg % args if args else msg))

    budget = _hydration_budget(config_path)
    if budget <= 0:
        _info("liveness de intake DESLIGADO (default OFF; MESMO knob %s=N "
              "do F65 liga os dois — regra 9: budget 0 = zero fetch)",
              HYDRATION_BUDGET_ENV_FLAG)
        return {"budget": 0, "status": "off"}

    eligible_path = data_dir / "eligible_jobs.json"
    try:
        ranking = json.loads(
            eligible_path.read_text(encoding="utf-8")
        ) if eligible_path.exists() else []
    except Exception as exc:  # noqa: BLE001 — JSON ilegivel => estagio pula
        _warn("liveness de intake: %s ilegivel (%s: %s) — estagio pulado",
              eligible_path, type(exc).__name__, exc)
        return {"budget": budget, "status": "unreadable_eligible"}

    previous_path = archive_dir / "eligible_jobs.json"
    previous: list | None = None
    try:
        previous = json.loads(
            previous_path.read_text(encoding="utf-8")
        ) if previous_path.exists() else None
    except Exception as exc:  # noqa: BLE001 — snapshot ilegivel = sem baseline
        _warn("liveness de intake: snapshot anterior ilegivel (%s: %s) — "
              "nada checado neste run", type(exc).__name__, exc)
        previous = None
    if previous is None:
        _info("liveness de intake: sem snapshot do run anterior — nada a "
              "checar (o diff de novas começa no próximo run, MESMO "
              "contrato do digest; nunca varrer o corpus inteiro)")
        record = {
            "type": "intake_liveness",
            "run_id": run_id or utcnow_iso(),
            "timestamp": utcnow_iso(),
            "budget": budget,
            "status": "no_baseline",
            "new_candidates": 0, "fetched": 0, "dead": 0,
            "hard_dead": 0, "soft_dead": 0, "net_errors": 0,
            "removed": 0, "removed_ids": [], "removed_entries": [],
            "duration_s": 0.0, "dead_ids": [],
        }
        try:
            from internship_finder.metrics import write_metrics
            write_metrics(metrics_path, [record])
        except Exception as exc:  # noqa: BLE001 — metrica e best-effort
            _warn("F87: metrica intake_liveness nao gravada: %s: %s",
                  type(exc).__name__, exc)
        return record

    prev_ids = {
        str(j.get("id") or "")
        for j in previous if isinstance(j, dict)
    } - {""}
    new_jobs = [
        j for j in ranking
        if isinstance(j, dict) and str(j.get("id") or "")
        and str(j.get("id")) not in prev_ids
    ]
    fetched_jobs = new_jobs[:budget]
    record = {
        "type": "intake_liveness",
        "run_id": run_id or utcnow_iso(),
        "timestamp": utcnow_iso(),
        "budget": budget,
        "new_candidates": len(new_jobs),
        "fetched": len(fetched_jobs),
        "dead": 0, "hard_dead": 0, "soft_dead": 0, "net_errors": 0,
        "removed": 0, "removed_ids": [], "removed_entries": [],
        "duration_s": 0.0, "dead_ids": [],
    }
    if not fetched_jobs:
        _info("liveness de intake: 0 candidata(s) nova(s) fora do "
              "snapshot anterior (budget %d intocado)", budget)
        try:
            from internship_finder.metrics import write_metrics
            write_metrics(metrics_path, [record])
        except Exception as exc:  # noqa: BLE001 — metrica e best-effort
            _warn("F87: metrica intake_liveness nao gravada: %s: %s",
                  type(exc).__name__, exc)
        return record

    t0 = time.monotonic()
    # MESMA maquinaria F11/F20/F87 do top exibido: 1 GET sequencial por
    # vaga (timeout 5s, UA honesto); want_bodies=False — o corpo serve só
    # ao veredito (soft-dead/200-falso), sem hidratação aqui (a janela do
    # topo e a estendida continuam donas dela).
    dead, _bodies, lstats = url_liveness.check_liveness_v2(
        fetched_jobs, want_bodies=False, log=log, opener=opener)
    # F94 — veredito por vaga NO REGISTRO (estado persistente consultável
    # entre runs): alive/dead/unknown + liveness_checked_at; wall SAML
    # (csod) ganha manual_check_required. Anota ANTES da remoção F39 — o
    # hard-dead removido leva o veredito junto (o registro sai do JSON);
    # os demais ficam com o estado honesto.
    liveness_state = _annotate_liveness_state(
        ranking,
        lstats.get("verdicts") or {},
        set(lstats.get("manual_check_required") or []),
        utcnow_iso(),
    )
    if liveness_state["annotated"]:
        _info("F94 vereditos de intake: %d anotado(s) — %d viva(s), "
              "%d morta(s), %d unknown (%d wall SAML)",
              liveness_state["annotated"], liveness_state["alive"],
              liveness_state["dead"], liveness_state["unknown"],
              liveness_state["manual_check_required"])
    hard_ids, hard_status = _extract_liveness_details(lstats)
    removal: dict = {}
    if os.environ.get(DEAD_REMOVAL_ENV_FLAG) != "1":
        removal = _remove_hard_dead(ranking, hard_ids, hard_status)
        if removal["removed"]:
            try:
                from internship_finder.cli import _write_json_atomic
                _write_json_atomic(ranking, eligible_path)
            except Exception as exc:  # noqa: BLE001 — persistencia best-effort
                _warn("F87: exclusão de intake não persistida (veredito "
                      "segue no registro): %s: %s", type(exc).__name__, exc)
    else:
        _info("F87: remoção de intake DESLIGADA (%s presente) — semântica "
              "F20 preservada", DEAD_REMOVAL_ENV_FLAG)
    # F94 — persiste os vereditos quando a remoção F39 NÃO reescreveu o
    # JSON neste passe (best-effort; falha nunca derruba o estágio).
    if liveness_state["annotated"] and not removal.get("removed"):
        try:
            from internship_finder.cli import _write_json_atomic
            _write_json_atomic(ranking, eligible_path)
        except Exception as exc:  # noqa: BLE001 — persistencia best-effort
            _warn("F94: vereditos de intake não persistidos (o registro "
                  "segue sem o estado): %s: %s", type(exc).__name__, exc)
    soft_ids = set(dead) - set(hard_ids)
    record.update({
        "dead": len(dead),
        "hard_dead": len(hard_ids),
        "soft_dead": len(soft_ids),
        "net_errors": int(lstats.get("net_errors") or 0),
        # F94 — vereditos persistidos no registro por este passe
        "verdict_annotated": liveness_state["annotated"],
        "verdict_alive": liveness_state["alive"],
        "verdict_dead": liveness_state["dead"],
        "verdict_unknown": liveness_state["unknown"],
        "verdict_manual_check": liveness_state["manual_check_required"],
        "removed": removal.get("removed", 0),
        "removed_ids": removal.get("removed_ids", []),
        "removed_entries": removal.get("removed_entries", []),
        "already_removed": removal.get("already_removed", 0),
        "duration_s": round(time.monotonic() - t0, 1),
        "dead_ids": sorted(str(i) for i in dead),
    })
    _info("liveness de intake: %d nova(s), %d fetch(es), %d morta(s) "
          "(%d hard-dead, %d soft/200-falso), %d removida(s) do JSON, "
          "%d erro(s) de rede ignorado(s), %.1fs",
          len(new_jobs), len(fetched_jobs), len(dead), len(hard_ids),
          len(soft_ids), removal.get("removed", 0),
          record["net_errors"], record["duration_s"])
    try:
        from internship_finder.metrics import write_metrics
        write_metrics(metrics_path, [record])
    except Exception as exc:  # noqa: BLE001 — metrica e best-effort
        _warn("F87: metrica intake_liveness nao gravada: %s: %s",
              type(exc).__name__, exc)
    return record


def run_enrichment(root: Path, exit_code: int, eligible: int, limit: int,
                   top_n: int, config: dict | None,
                   max_secs: float = DEFAULT_ENRICHMENT_MAX_SECS) -> None:
    """Fase 2 — enrichment incremental LLM apos o fluxo principal.

    Subprocesso standalone ``scripts/enrichment_run.py`` (mesmo padrao da
    coleta). Gates de entrada:

    - **F1 (01/10) gate de configuracao** ``INTERNSHIP_FINDER_ENRICHMENT=1``
      (env herdada OU injecao a partir do ``.env``): ausente -> pulado com
      log. O cron de producao roda sem a env var e o enrichment fica OFF
      (retorno zero comprovado: 0/21 em 5h38 na janela degradada 29/09;
      17.615s e 6/22 no 30/09). A flag ``--enrichment`` so e efetiva COM a
      env var — reativa manual sob demanda:
      ``INTERNSHIP_FINDER_ENRICHMENT=1 ... --enrichment``.
    - **gate UNICO** ``publish_pages.publication_allowed(exit_code,
      eligible)`` — a MESMA decisao da publicacao/digest (auditoria 23/09):
      refresh invalido (exit 1/124 ou eligible 0) -> enrichment pulado com
      log; o ranking que o enrichment consumiria nao e confiavel;
    - ``NVIDIA_API_KEY``: heranca de ``os.environ`` OU injecao a partir do
      ``.env`` (``load_env_config``); ausente em ambos -> pulado com log —
      NUNCA e erro e a key jamais vai para log/exception.

    ``top_n`` limita o plano as N vagas mais bem ranqueadas do dia
    (decisao do dono 26/09): vagas fora do corte nunca entram no backlog
    por serem novas; seus records ficam preservados no store e a cobertura
    acontece no dia em que a vaga reentrar no corte.

    F1 (01/10) teto de tempo ``max_secs``: o subprocesso roda com
    ``timeout``; estourado, e morto e reportado como linha de log (o run de
    5h38 da janela degradada motivou o teto — ver constante). O store do
    enrichment e atomico por record (upsert + ``os.replace``) e o lock
    interno e flock do SO: morte de processo nunca corrompe dados nem
    deixa lock preso. O exit code do refresh NUNCA muda por causa do
    enrichment (spec secao 5).

    Qualquer exit do subprocesso vira UMA linha de log (``enrichment: exit
    3 (concorrencia)``) e qualquer excecao vira ``enrichment FALHOU: ...``.
    O exit code do refresh NUNCA muda por causa do enrichment (spec secao
    5: ``refresh exit 0`` + ``enrichment parcialmente falho`` e estado
    operacionalmente valido). stdout/stderr herdados: o resumo do run cai
    no log do cron.
    """
    if not publish_pages.publication_allowed(exit_code, eligible):
        log.info("enrichment pulado (refresh inválido: exit %d, eligible %s)",
                 exit_code, eligible)
        return
    if os.environ.get(ENRICHMENT_ENV_FLAG) != "1" and (
            config or {}).get(ENRICHMENT_ENV_FLAG) != "1":
        log.info(
            "enrichment desligado por configuração (default OFF; reative com "
            "%s=1 no .env + --enrichment) — retorno zero comprovado na janela "
            "NVIDIA degradada (0/21 em 5h38, 29/09)",
            ENRICHMENT_ENV_FLAG,
        )
        return
    env = {**os.environ}
    key = env.get("NVIDIA_API_KEY") or (config or {}).get("NVIDIA_API_KEY")
    if not key:
        log.info("enrichment pulado: NVIDIA_API_KEY ausente (env/.env)")
        return
    env["NVIDIA_API_KEY"] = key
    command = [
        sys.executable, "scripts/enrichment_run.py",
        "--limit", str(limit),
        "--top-n", str(top_n),
        "--input", "data/eligible_jobs.json",
        "--output", "data/enrichment/enrichment_results.jsonl",
    ]
    log.info("enrichment: subprocesso %s (cwd=%s, teto %.0fs)",
             " ".join(command), root, max_secs)
    try:
        proc = subprocess.run(command, cwd=root, env=env, check=False,
                               timeout=max_secs)
    except subprocess.TimeoutExpired:
        # F1: teto estourado — subprocesso morto pelo timeout. O store e
        # atomico por record e o lock interno e flock do SO: nada corrompe,
        # nada fica preso. O refresh segue com o exit da coleta.
        log.error("enrichment estourou o teto de %.0fs e foi morto "
                  "(defesa do flock; o refresh segue)", max_secs)
        return
    except Exception as exc:  # noqa: BLE001 — enrichment nunca derruba o refresh
        log.error("enrichment FALHOU: %s: %s", type(exc).__name__, exc)
        return
    if proc.returncode == 0:
        log.info("enrichment: concluido (exit 0)")
    else:
        # exit 1 = setup (key/modelo/input); 2 = nada processado;
        # 3 = concorrencia. Tudo e dado do enrichment — o refresh segue.
        log.info("enrichment: exit %d (falha é dado; refresh segue)",
                 proc.returncode)



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
                        help="retencao dos backups (jobs.db/dataset_seen.db) "
                        f"em dias (default {DEFAULT_BACKUP_RETENTION_DAYS}; "
                        "0 = desligado)")
    # F75 — retencao do collection_metrics.jsonl: rollup diario alem do corte
    # (raw recente + agregado antigo). O DONO AJUSTA o corte por aqui.
    parser.add_argument("--metrics-retention-days", type=_non_negative_int,
                        default=DEFAULT_METRICS_RETENTION_DAYS, metavar="N",
                        help="F75: retencao do collection_metrics.jsonl em "
                        "dias — alem do corte os registros viram rollup "
                        "diario agregado (raw recente + agregado antigo; "
                        f"default {DEFAULT_METRICS_RETENTION_DAYS}; "
                        "0 = desligado)")
    parser.add_argument("--pages-dir", default=None, metavar="PATH",
                        help="clone de deploy do GitHub Pages (branch gh-pages). "
                        "Quando informado, o ranking do run e publicado "
                        "automaticamente apos a coleta (gate UNICO "
                        "publication_allowed: eligible > 0 com exit 0 ou exit 2 "
                        "= parcial com falhas perifericas). Default: "
                        "publicacao desligada.")
    parser.add_argument("--enrichment", action="store_true",
                        help="roda o enrichment incremental LLM (scripts/"
                        "enrichment_run.py) apos o fluxo principal. Requer "
                        "TAMBEM a env INTERNSHIP_FINDER_ENRICHMENT=1 (F1: "
                        "default OFF no cron; reativacao manual sob demanda). "
                        "MESMO gate da publicacao (publication_allowed: exit "
                        "0/2 com eligible > 0); falha do enrichment NUNCA "
                        "muda o exit code do refresh. Default: desligado.")
    parser.add_argument("--enrichment-limit", type=_non_negative_int,
                        default=DEFAULT_ENRICHMENT_LIMIT, metavar="N",
                        help="cap de extracoes LLM por run do enrichment "
                        f"(default {DEFAULT_ENRICHMENT_LIMIT}; passa --limit "
                        "ao enrichment_run.py)")
    parser.add_argument("--enrichment-top-n", type=_non_negative_int,
                        default=DEFAULT_ENRICHMENT_TOP_N, metavar="N",
                        help="corte do ranking do enrichment: somente as N "
                        "vagas mais bem ranqueadas entram no plano/backlog "
                        f"(default {DEFAULT_ENRICHMENT_TOP_N}; passa --top-n "
                        "ao enrichment_run.py); vagas fora do corte ficam "
                        "com records preservados e sao cobertas ao reentrar")
    parser.add_argument("--enrichment-max-secs", type=float,
                        default=DEFAULT_ENRICHMENT_MAX_SECS, metavar="N",
                        help="F1: teto total de duracao do subprocesso de "
                        f"enrichment em segundos (default "
                        f"{DEFAULT_ENRICHMENT_MAX_SECS:.0f}); estourado, o "
                        "subprocesso e morto (store atomico, lock flock do "
                        "SO — nada corrompe, nada fica preso) e o refresh "
                        "segue com o exit da coleta. Defesa do flock contra "
                        "janelas degradadas do provider LLM")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.dry_run:
        return _run_dry_run(args.retention_days,
                            args.metrics_retention_days)

    root = repo_root()
    data_dir = root / "data"
    metrics_path = data_dir / "collection_metrics.jsonl"
    archive_root = data_dir / "archive"
    config_path = Path(args.config) if args.config else root / ".env"

    log.info("refresh: rotacao antiga -> archive (config=%s)", config_path)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = rotate(data_dir, archive_root, ts)
    cleanup_archive(archive_root, args.retention_days)

    # 1c. F75 — retenção do collection_metrics.jsonl: rollup DIÁRIO dos
    # registros além do corte (raw recente + agregado antigo). Roda ANTES
    # do snapshot de linhas (``skip_lines``) para o run enxergar o arquivo
    # pós-rollup, e ANTES da coleta (que só APPENDE — nada é perdido no
    # ar). O RAW completo de cada dia cortado segue no snapshot do archive
    # de hoje (backup de curto prazo). Best-effort: falha loga e o run
    # segue (padrão do backup do jobs.db) — NUNCA muda o exit code.
    try:
        roll = rollup_metrics(metrics_path,
                              retention_days=args.metrics_retention_days)
        if roll.get("changed"):
            log.info("metrics rollup F75: %d dia(s) antigo(s) agregado(s) "
                     "(%d registros -> %d rollups; %d raw mantidos)",
                     roll.get("rolled_days"), roll.get("rolled_records"),
                     roll.get("rolled_days"), roll.get("raw_kept"))
        else:
            log.info("metrics rollup F75: nada a fazer (%s)",
                     roll.get("reason") or "sem registros além do corte")
    except Exception as exc:  # noqa: BLE001 — retenção nunca derruba o run
        log.warning("metrics rollup F75 FALHOU (run segue): %s", exc)

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
    # F70 — backup do dataset_seen.db (caderno do universo pos-prefilter):
    # mesma mecanica/diretorio/retencao do jobs.db (stem proprio
    # ``dataset_seen-<ts>.db`` — sem colisao de nome). Justificativa da
    # extensao (spec F70 item 6, decisao do executor): o caderno e a
    # UNICA memoria do universo EFEMERO do dataset (jobs.db nao cobre
    # dataset jobs, §7.8) — perda = furos permanentes em first_seen que
    # nenhuma re-derivacao recupera. Volume: ~24k rows/dia (~4-5 MB/dia
    # com indice; ~1,2-1,5 GB/ano) — o custo de retencao (default 14d)
    # e visivel e o knob ``--backup-retention-days`` cobre os DOIS
    # arquivos. Ausente (primeiro run pos-merge) NAO e falha: pula.
    seen_backup_error: str | None = None
    seen_db = data_dir / "dataset_seen.db"
    if seen_db.exists():
        try:
            seen_backup = backup_jobs_db(seen_db)
            log.info("backup do dataset_seen.db criado: %s", seen_backup)
        except Exception as exc:  # noqa: BLE001 — caderno e operacional
            seen_backup_error = f"{type(exc).__name__}: {exc}"
            log.error("backup do dataset_seen.db FALHOU: %s", seen_backup_error)
    else:
        log.info("sem %s; backup do caderno dataset_seen pulado", seen_db)
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

    # F87 — liveness no 1º sighting (ANTES da janela de análise): 1 fetch
    # barato por candidata NOVA (diff vs o snapshot arquivado — o mesmo do
    # digest), budget herdado do F65 (mesmo knob; default 0 = OFF). Roda
    # ANTES do passe F20 do top (hard-dead removido aqui não gasta fetch
    # lá). Best-effort TOTAL: falha vira log e o run segue sem as marcas.
    intake_dead_ids: set[str] = set()
    intake_stats: dict = {}
    try:
        intake_stats = _intake_liveness(
            data_dir, archive_dir, metrics_path,
            run_id=summary.get("run_id"),
            config_path=config_path, log=log)
        intake_dead_ids = {
            str(i) for i in (intake_stats.get("dead_ids") or []) if i}
    except Exception as exc:  # noqa: BLE001 — F87 nunca derruba o run
        log.warning("F87: liveness de intake falhou (run segue sem as "
                    "marcas): %s: %s", type(exc).__name__, exc)

    # F11/F20 — vitalidade de URL do top exibido (ANTES de publicar;
    # best-effort TOTAL: qualquer falha vira log e o publish segue SEM
    # mortas marcadas — o pipeline NUNCA derruba por causa do check).
    # F11: 404/410 = morta (desce do top exibido; a proxima sobe).
    # F20: soft-dead (marcador de corpo / redirect-para-homepage / shell
    # SPA) tem a MESMA semantica; o MESMO passe GET hidrata a descricao
    # das vagas vivas com texto curto (< HYDRATION_SHORT_LIMIT) e a
    # re-avaliacao F18 (german_level/requires_master) sobre a descricao
    # hidratada pode demover a vaga do top exibido (marcador honesto
    # hydration_inapplicable — fica no JSON). A hidratacao NUNCA
    # re-adiciona vaga removida pela F18 — so demove o que ela revelou.
    # 403/429/timeout = bloqueio de bot/rede, ignora. Falha total de rede:
    # nenhuma marca. Roda apenas quando ha publicacao (o check existe
    # para servir a pagina publicada) e o corte e o MESMO da pagina.
    dead_ids: set[str] = set()
    inapplicable_ids: set[str] = set()
    hydration_stats: dict = {}
    removal_stats: dict = {}  # F39 — stats da remoção de hard-dead (auditoria)
    pages_dir = Path(args.pages_dir).expanduser() if args.pages_dir else None
    if pages_dir is not None:
        try:
            ranking = json.loads(
                (data_dir / "eligible_jobs.json").read_text(encoding="utf-8")
            ) if (data_dir / "eligible_jobs.json").exists() else []
            top_shown = minimal_page.apply_company_cap(ranking)
            if top_shown:
                t0 = time.monotonic()
                result = url_liveness.check_liveness(
                    top_shown, log=log, return_details=True,
                    short_description_limit=HYDRATION_SHORT_LIMIT,
                )
                # Compat graciosa de API: retorno set (mock/terceiro) =
                # apenas ids mortos, sem hidratacao — o estagio NUNCA
                # derruba por causa de um formato inesperado.
                if isinstance(result, set):
                    dead_ids, hydrated_bodies, hydration_stats = result, {}, {}
                else:
                    dead_ids, hydrated_bodies, hydration_stats = result
                # F94 — veredito por vaga NO REGISTRO (estado persistente):
                # alive/dead/unknown + liveness_checked_at; wall SAML ganha
                # manual_check_required. Anota ANTES da remoção F39 e da
                # hidratação (as reescritas seguintes carregam os campos; a
                # persistência explícita cobre o run sem remoção/hidratação).
                liveness_state = _annotate_liveness_state(
                    ranking,
                    hydration_stats.get("verdicts") or {},
                    set(hydration_stats.get("manual_check_required") or []),
                    utcnow_iso(),
                )
                if liveness_state["annotated"]:
                    log.info(
                        "F94 vereditos do top exibido: %d anotado(s) — "
                        "%d viva(s), %d morta(s), %d unknown (%d wall SAML)",
                        liveness_state["annotated"], liveness_state["alive"],
                        liveness_state["dead"], liveness_state["unknown"],
                        liveness_state["manual_check_required"])
                # F39 — remoção de hard-dead confirmado: ids HTTP 404/410
                # SEPARADOS dos soft-dead nos stats do liveness (extração
                # tolerante — stats sem as chaves F39 = nada a excluir).
                # Kill switch (env var presente => remoção OFF, run segue
                # com o comportamento F20: vaga morta fica no JSON). O
                # passe remove o registro do ranking in place e REESCREVE
                # o JSON atômico ANTES do publish — o arquivo de saída do
                # pipeline NÃO contém o hard-dead (nem badge, nem
                # registro); provenance fica na métrica diária
                # ``dead_link_removal`` + log. Idempotente por construção:
                # re-run sem re-coleta não re-remove (o id já não está no
                # arquivo).
                if os.environ.get(DEAD_REMOVAL_ENV_FLAG) != "1":
                    hard_dead_ids, hard_dead_status = \
                        _extract_liveness_details(hydration_stats)
                    removal_stats = _remove_hard_dead(
                        ranking, hard_dead_ids, hard_dead_status)
                    if removal_stats["removed"]:
                        try:
                            from internship_finder.cli import _write_json_atomic
                            _write_json_atomic(
                                ranking, data_dir / "eligible_jobs.json")
                        except Exception as exc:  # noqa: BLE001
                            log.warning("F39: exclusão não persistida (run "
                                        "segue; veredito segue no liveness):"
                                        " %s: %s", type(exc).__name__, exc)
                    if removal_stats["removed"] or removal_stats["already_removed"]:
                        log.info(
                            "F39 remoção: %d hard-dead(s) saíram do "
                            "eligible/display %s, %d já ausente(s) %s",
                            removal_stats["removed"],
                            removal_stats["by_status"],
                            removal_stats["already_removed"],
                            removal_stats["already_removed_ids"])
                    else:
                        log.info("F39 remoção: nenhum hard-dead confirmado "
                                 "no top exibido deste run")
                else:
                    removal_stats = {}
                    log.info("F39 remoção DESLIGADA (%s presente): "
                             "semântica F20 preservada",
                             DEAD_REMOVAL_ENV_FLAG)
                # F94 — persiste os vereditos quando a remoção F39 NÃO
                # reescreveu o JSON (a reescrita da remoção/hidratação já
                # carrega os campos — anotação in place no ranking).
                # Best-effort: falha nunca derruba o run.
                if liveness_state["annotated"] and not removal_stats.get("removed"):
                    try:
                        from internship_finder.cli import _write_json_atomic
                        _write_json_atomic(
                            ranking, data_dir / "eligible_jobs.json")
                    except Exception as exc:  # noqa: BLE001
                        log.warning(
                            "F94: vereditos não persistidos (página/digest "
                            "seguem; o estado fica só no log): %s: %s",
                            type(exc).__name__, exc)
                # Hidratacao: aplica a descricao completa nas vagas vivas
                # (provenance honesta; descricao original NUNCA piora) e
                # re-avalia aplicabilidade com as regras da F18.
                inapplicable_ids: set[str] = set()
                hydrated_jobs = 0
                hydrated_ids: set[str] = set()  # F56 — ids efetivamente hidratados
                for job in top_shown:
                    jid = str(job.get("id") or "")
                    new_desc = hydrated_bodies.get(jid)
                    if new_desc:
                        job["description"] = new_desc
                        job["description_source"] = HYDRATION_SOURCE
                        job["description_hydrated_at"] = utcnow_iso()
                        hydrated_jobs += 1
                        hydrated_ids.add(jid)
                        reason = _reassess_hydrated_applicability(job)
                        if reason:
                            job[HYDRATION_INAPPLICABLE_FLAG] = reason
                            inapplicable_ids.add(jid)
                            log.info(
                                "hidratacao: %s revelou %s — desce do "
                                "top exibido (fica no JSON)", jid, reason)
                if hydrated_jobs:
                    # F56 — re-score pós-hidratação ANTES de persistir: este
                    # estágio enriquece a description DEPOIS do rank_jobs da
                    # coleta; sem recompute o score gravado fica congelado no
                    # estado pré-hidratação (achado F55 §4: language 0.0
                    # gravado vs +1.5 recomputado; hidratada sobe de rank).
                    # Recomputa SOMENTE as hidratadas (causa real: a descrição
                    # mudou), com o MESMO desempate do rank_jobs, e reordena
                    # a lista — publish e digest leem ESTE arquivo. now aware
                    # como a coleta usa (F38). Idempotente: no run seguinte a
                    # descrição hidratada deixa de ser candidata (texto
                    # longo), então não há nova hidratação nem oscilação.
                    # Best-effort: falha NUNCA derruba o run (JSON segue com
                    # os scores pré-hidratação, semântica anterior à F56).
                    try:
                        rescored = rescore_hydrated_jobs(
                            ranking, hydrated_ids, now=datetime.now(UTC))
                        log.info("F56: score recomputado para %d vaga(s) "
                                 "hidratada(s) pos-hidratacao", rescored)
                    except Exception as exc:  # noqa: BLE001 — re-score nunca derruba o run
                        log.warning("F56: re-score pos-hidratacao falhou (JSON "
                                    "segue com scores pre-hidratacao): %s: %s",
                                    type(exc).__name__, exc)
                    # Persiste a hidratacao no eligible_jobs.json (o
                    # publish renderiza por subprocesso que LE o arquivo).
                    # Escrita atomica reusando a funcao do CLI; a rotacao
                    # deste run ja preservou o snapshot anterior no
                    # archive. O CSV nao muda (description fora do contrato
                    # ACH-18 por design). Best-effort: falha de escrita
                    # NUNCA derruba o run (a pagina publica simplesmente
                    # fica com as descricoes originais).
                    try:
                        from internship_finder.cli import (_write_json_atomic,
                                                           _write_atomic,
                                                           _dump_csv)
                        _write_json_atomic(
                            ranking, data_dir / "eligible_jobs.json")
                        # F56 — ``score`` ESTÁ em CSV_COLUMNS: o CSV derivado
                        # precisa acompanhar o re-score (o argumento "o CSV
                        # não muda" vale para description, fora do contrato
                        # ACH-18; score é coluna do contrato). Mesma escrita
                        # atômica do save_outputs.
                        _write_atomic(
                            (data_dir / "eligible_jobs.json").with_suffix(".csv"),
                            lambda fh: _dump_csv(fh, ranking))
                        log.info("hidratacao: %d descricao(oes) persistida(s) "
                                 "em %s", hydrated_jobs,
                                 data_dir / "eligible_jobs.json")
                    except Exception as exc:  # noqa: BLE001
                        log.warning("hidratacao nao persistida (pagina segue "
                                    "com descricoes originais): %s: %s",
                                    type(exc).__name__, exc)
                # Demotion exibida: mortas + inaplicaveis-apos-hidratacao
                # saem do top (mesma mecanica do dead_link). O publish
                # recebe os DOIS conjuntos — badge "🔗 morta" SO para as
                # mortas (URL realmente morta); as inaplicaveis ganham
                # badge proprio "🚫 inaplicável" no render (URL viva,
                # aplicabilidade revelada pela descricao completa).
                excluded_ids = dead_ids | inapplicable_ids
                if excluded_ids:
                    log.info("liveness: %d vaga(s) do top marcadas "
                             "(mortas+inaplicaveis) — descem do topo "
                             "exibido", len(excluded_ids))
                log.info("estagio F20 (vitalidade+hidratacao): %.1fs, "
                         "stats=%s", time.monotonic() - t0, hydration_stats)
        except Exception as exc:  # noqa: BLE001 — vitalidade nunca derruba o run
            log.warning("estagio de vitalidade falhou (publish segue sem "
                        "marcas): %s: %s", type(exc).__name__, exc)

        # F65 — hidratacao estendida: as vagas de description curta/vazia
        # FORA do top exibido (cegas a F20 — classe B da F60, caso Lidl
        # praktikum_info:13308116), em ordem de score, ate o teto diario
        # INTERNSHIP_FINDER_HYDRATION_BUDGET (default 0 = OFF, regra 9:
        # nenhuma mudanca ate o dono ligar). MESMO gate de publicacao da
        # F20 (so roda com --pages-dir); best-effort TOTAL; mortas do
        # passe estendido NUNCA sao marcadas (so contadas) — a janela do
        # topo e dona da semantica de morte. Roda ANTES da F25/F37.3
        # para que os german_required revelados pelo texto hidratado
        # sejam removidos do JSON pela varredura F37.3 DESTE run.
        try:
            extended_hydration_stats = _run_extended_hydration(
                data_dir, metrics_path,
                run_id=summary.get("run_id"),
                config_path=config_path,
                log=log,
                # F87 — poço compartilhado: o que o intake gastou abate do
                # teto diário do F65 no MESMO run (um só orçamento de
                # fetches; intake OFF = comportamento F65 exato).
                budget_override=max(0, _hydration_budget(config_path)
                                    - int(intake_stats.get("fetched") or 0)))
            if extended_hydration_stats.get("hydrated"):
                log.info("F65 resumo: %d vaga(s) sairam da cegueira "
                         "(janela estendida)",
                         extended_hydration_stats["hydrated"])
        except Exception as exc:  # noqa: BLE001 — F65 nunca derruba o run
            log.warning("F65: hidratacao estendida falhou (run segue, "
                        "exit %d preservado): %s: %s",
                        exit_code, type(exc).__name__, exc)

        # F91 — hidratacao dos CEGOS: as desc-empty do pool (<50 chars)
        # de fontes cujo texto so existe na pagina propria (absolventa,
        # praktikum_info — JSON-LD malformado curado pelo parse leniente
        # desta fase no url_liveness). Terceiro estagio flag-gated
        # (padrao F65), budget PROPRIO
        # (INTERNSHIP_FINDER_BLIND_HYDRATION_BUDGET; default 0 = OFF,
        # regra 9: nenhuma mudanca ate o dono ligar). Roda DEPOIS do F20
        # e do F65 — pega o que AINDA esta cego (incluindo o topo: o F20
        # busca a pagina destas fontes e falha no parse estrito).
        # sf_dataset:bundesagentur fica FORA (Passo 0: 74/74 refnrs
        # mortos na fonte — espelho atrasado; as vivas a Fase A cura).
        # Best-effort TOTAL; re-score F56 + persistencia atomica;
        # german_required revelado desce via marcador + F37.3 deste run.
        try:
            blind_hydration_stats = _run_blind_hydration(
                data_dir, metrics_path,
                run_id=summary.get("run_id"),
                config_path=config_path,
                log=log)
            if blind_hydration_stats.get("hydrated"):
                log.info("F91 resumo: %d vaga(s) sairam da cegueira "
                         "(estagio dos cegos)",
                         blind_hydration_stats["hydrated"])
        except Exception as exc:  # noqa: BLE001 — F91 nunca derruba o run
            log.warning("F91: hidratacao dos cegos falhou (run segue, "
                        "exit %d preservado): %s: %s",
                        exit_code, type(exc).__name__, exc)

    # F25 — reavaliacao de aplicabilidade do BACKLOG hidratado: TODA vaga
    # com description_source=="hydration" que ainda nao tem o marcador
    # passa pela MESMA re-avaliacao da F20 (_reassess_hydrated_applicability
    # -> detetores puros da F18). Fecha o buraco do estagio Fase A
    # (hydrate_descriptions roda DEPOIS do select_eligible e nunca
    # re-avalia; medição 12/10: 126/783 hidratadas german-required sem
    # marcador, incluindo o topo do ranking). O passe e local (zero rede),
    # muta in place (mesma ordem, nenhum outro campo) e persiste com a
    # escrita atomica existente; as flagadas descem das superfícies
    # exibidas (MESMA semântica F20: ficam no JSON). Idempotente: vaga
    # ja marcada NUNCA e re-flagada. Best-effort TOTAL: falha vira log e o
    # run segue com o exit da coleta.
    backlog_stats: dict = {}
    excl_stats: dict = {}
    backlog_inapplicable_ids: set[str] = set()
    try:
        ranking = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8")
        ) if (data_dir / "eligible_jobs.json").exists() else []
        backlog_stats = _reassess_backlog_applicability(ranking)
        # F37.3 — EXCLUSÃO TOTAL do eligible: remove do JSON os registros cujo
        # motivo está em ``APPLICABILITY_JSON_EXCLUSION_REASONS`` (hoje só
        # ``german_required``; decisão do dono 15/10). Roda DEPOIS do passe F25
        # e sobre o JSON do disco — pega os flags do passe do topo (F20,
        # persistidos acima) E os do backlog; o flag é o MESMO veredito do
        # detector único, então não há segundo mecanismo nem detector novo.
        excl_stats = _remove_json_excluded(ranking)
        if backlog_stats["newly_flagged"] or excl_stats["removed"]:
            try:
                from internship_finder.cli import _write_json_atomic
                _write_json_atomic(ranking, data_dir / "eligible_jobs.json")
            except Exception as exc:  # noqa: BLE001 — persistencia best-effort
                log.warning("F25: flags do backlog nao persistidas (JSON "
                            "segue sem os marcadores): %s: %s",
                            type(exc).__name__, exc)
        if backlog_stats["newly_flagged"]:
            log.info("F25 backlog: %d hidratada(s) reavaliada(s), %d "
                     "nova(s) inaplicavel(is) %s — descem do topo exibido "
                     "(ficam no JSON)",
                     backlog_stats["reassessed"],
                     backlog_stats["newly_flagged"],
                     backlog_stats["by_reason"])
        else:
            log.info("F25 backlog: %d hidratada(s) reavaliada(s), nenhuma "
                     "nova inaplicavel", backlog_stats["reassessed"])
        if excl_stats["removed"]:
            log.info("F37.3 exclusao total do eligible: %d vaga(s) SAIRAM do "
                     "eligible_jobs.json %s (motivos de exclusao total — "
                     "decisao do dono 15/10)",
                     excl_stats["removed"], excl_stats["by_reason"])
        else:
            log.info("F37.3 exclusao total do eligible: nenhuma vaga a "
                     "remover neste run")
        # Semantica F20: flag => demovida das superficies exibidas. TODO
        # flag no JSON conta (nova OU herdada de run anterior no mesmo
        # arquivo — ex. re-run sem re-coleta), nao so as deste passe: a
        # colecao reescreve o JSON a cada run (o modelo Job nao carrega o
        # campo), mas um re-run do refresh sobre o mesmo JSON precisa
        # continuar demovendo as ja marcadas.
        backlog_inapplicable_ids = {
            str(j.get("id") or "")
            for j in ranking
            if isinstance(j, dict) and j.get(HYDRATION_INAPPLICABLE_FLAG)
        } - {""}
        try:
            from internship_finder.metrics import write_metrics
            write_metrics(metrics_path, [{
                "type": "hydration_reassessment",
                "run_id": summary.get("run_id") or utcnow_iso(),
                "timestamp": utcnow_iso(),
                **backlog_stats,
            }])
        except Exception as exc:  # noqa: BLE001 — metrica e best-effort
            log.warning("F25: registro de metricas do backlog nao gravado: "
                        "%s: %s", type(exc).__name__, exc)
        # F37.3 — provenance da EXCLUSÃO TOTAL (padrão F37/F39: motivo +
        # contador por motivo + ids/entradas que SAÍRAM do eligible). Sempre
        # gravado (0 no dia sem exclusões = baseline auditável). Append-only,
        # best-effort: falha NUNCA derruba o run.
        try:
            from internship_finder.metrics import write_metrics as _wm_excl
            _wm_excl(metrics_path, [{
                "type": "applicability_exclusion",
                "run_id": summary.get("run_id") or utcnow_iso(),
                "timestamp": utcnow_iso(),
                "removed": excl_stats.get("removed", 0),
                "by_reason": excl_stats.get("by_reason", {}),
                "removed_ids": excl_stats.get("removed_ids", []),
                "removed_entries": excl_stats.get("removed_entries", []),
            }])
        except Exception as exc:  # noqa: BLE001 — metrica e best-effort
            log.warning("F37.3: metrica applicability_exclusion nao gravada: "
                        "%s: %s", type(exc).__name__, exc)
        # F37 — contagem derivada "aplicavel" (= eligible − flagged) por
        # motivo, exposta no metrics para o header de universo (cards
        # F43/F44 consomem). Registro proprio, nao toca no "run" do
        # pipeline; falha e best-effort (o run segue).
        try:
            from internship_finder.metrics import write_metrics as _wm
            _wm(metrics_path, [
                _applicability_metrics_record(
                    ranking, summary.get("run_id")
                )
            ])
        except Exception as exc:  # noqa: BLE001 — metrica e best-effort
            log.warning("F37: metrica de aplicabilidade nao gravada: "
                        "%s: %s", type(exc).__name__, exc)
    except Exception as exc:  # noqa: BLE001 — F25 nunca derruba o run
        log.warning("F25: reavaliacao do backlog falhou (run segue sem as "
                    "marcas do backlog): %s: %s", type(exc).__name__, exc)

    # F87 — anotação do flag "não-avaliável" (display + digest, NUNCA
    # exclusão): recomputa TODO run sobre a lista inteira — acende quando
    # a descrição não dá base de julgamento (vazia / < 600 chars medidos /
    # login-wall) e APAGA quando a hidratação (F20/F65, que rodou acima)
    # trouxe texto suficiente. Zero rede, idempotente; persiste ANTES do
    # publish/digest para que ambos leiam o campo. Best-effort TOTAL.
    assess_stats: dict = {}
    try:
        ranking = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8")
        ) if (data_dir / "eligible_jobs.json").exists() else []
        assess_stats = _annotate_assessability(ranking)
        if assess_stats.get("flagged") or assess_stats.get("cleared"):
            try:
                from internship_finder.cli import _write_json_atomic
                _write_json_atomic(ranking, data_dir / "eligible_jobs.json")
            except Exception as exc:  # noqa: BLE001 — persistencia best-effort
                log.warning("F87: flag não-avaliável não persistida (página/"
                            "digest seguem sem os ⚠️): %s: %s",
                            type(exc).__name__, exc)
        if assess_stats.get("flagged") or assess_stats.get("cleared"):
            log.info("F87 não-avaliáveis: %d flaggada(s) %s, %d curada(s) "
                     "(hidratação/truncamento reverteu) em %d vaga(s)",
                     assess_stats.get("flagged", 0),
                     assess_stats.get("by_reason", {}),
                     assess_stats.get("cleared", 0),
                     assess_stats.get("total", 0))
        else:
            log.info("F87 não-avaliáveis: %d flaggada(s) no acervo (por "
                     "motivo %s), nada novo neste run",
                     sum(assess_stats.get("by_reason", {}).values()),
                     assess_stats.get("by_reason", {}))
        try:
            from internship_finder.metrics import write_metrics
            write_metrics(metrics_path, [{
                "type": "assessability",
                "run_id": summary.get("run_id") or utcnow_iso(),
                "timestamp": utcnow_iso(),
                **assess_stats,
            }])
        except Exception as exc:  # noqa: BLE001 — metrica e best-effort
            log.warning("F87: metrica assessability nao gravada: %s: %s",
                        type(exc).__name__, exc)
    except Exception as exc:  # noqa: BLE001 — F87 nunca derruba o run
        log.warning("F87: anotação não-avaliável falhou (run segue sem os "
                    "⚠️): %s: %s", type(exc).__name__, exc)

    # F94 item 3 — flag stale_posting por tipo (display/digest leem o
    # CAMPO, NUNCA recomputam; NUNCA exclusão — vaga velha pode estar
    # VIVA no site, o caso Lidl re-post). posted_at coletado como fonte
    # primária; caderno F70 first_seen como fallback (dataset sem
    # posted_at — ex. workday airbus). Zero rede, idempotente; persiste
    # ANTES do publish/digest. Best-effort TOTAL.
    try:
        ranking = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8")
        ) if (data_dir / "eligible_jobs.json").exists() else []
        stale_stats = _annotate_stale_posting(
            ranking, now=datetime.now(UTC),
            seen_db_path=data_dir / "dataset_seen.db")
        if stale_stats.get("stale") or stale_stats.get("cleared"):
            try:
                from internship_finder.cli import _write_json_atomic
                _write_json_atomic(ranking, data_dir / "eligible_jobs.json")
            except Exception as exc:  # noqa: BLE001 — persistencia best-effort
                log.warning("F94: stale_posting não persistido (página/"
                            "digest seguem sem o flag): %s: %s",
                            type(exc).__name__, exc)
            log.info("F94 stale_posting: %d flaggada(s) (limiar por tipo "
                     "%s, idade por fonte %s), %d curada(s) em %d vaga(s)",
                     stale_stats.get("stale", 0),
                     stale_stats.get("by_threshold", {}),
                     stale_stats.get("by_source", {}),
                     stale_stats.get("cleared", 0),
                     stale_stats.get("total", 0))
        else:
            log.info("F94 stale_posting: %d flaggada(s) no acervo (fonte "
                     "%s, limiar %s), nada novo neste run (%d sem "
                     "evidência de idade)",
                     stale_stats.get("stale", 0),
                     stale_stats.get("by_source", {}),
                     stale_stats.get("by_threshold", {}),
                     stale_stats.get("no_evidence", 0))
        try:
            from internship_finder.metrics import write_metrics
            write_metrics(metrics_path, [{
                "type": "stale_posting",
                "run_id": summary.get("run_id") or utcnow_iso(),
                "timestamp": utcnow_iso(),
                **stale_stats,
            }])
        except Exception as exc:  # noqa: BLE001 — metrica e best-effort
            log.warning("F94: metrica stale_posting nao gravada: %s: %s",
                        type(exc).__name__, exc)
    except Exception as exc:  # noqa: BLE001 — F94 nunca derruba o run
        log.warning("F94: anotação stale_posting falhou (run segue sem os "
                    "flags): %s: %s", type(exc).__name__, exc)

    # F107 — lista COMPLETA das novas em data/NEW-<date>.md (mesmo estágio
    # do MANUAL-CHECK; display-only). O diff URL-honesto
    # (``ranking_digest.new_postings_diff``) classifica os IDs novos do
    # snapshot anterior em "genuinamente novas" (URL ausente) e
    # "re-sightings" (mesma URL, ID reciclado) — o 🆕 do digest mostra o
    # TOTAL real + a fatia Top-30 + o ponteiro para o arquivo, que carrega
    # TODAS as novas (o cap 4096 do Telegram é físico; a lista vive no
    # ARQUIVO). Roda DEPOIS da anotação F94 (o ⏳ lê o campo persistido) e
    # ANTES do digest (o header referencia o caminho). Best-effort TOTAL.
    new_list_display: str | None = None
    try:
        prev_path = archive_dir / "eligible_jobs.json"
        prev_ranking = None
        if prev_path.exists():
            prev_ranking = json.loads(
                prev_path.read_text(encoding="utf-8"))
        cur_path = data_dir / "eligible_jobs.json"
        cur_ranking: list = []
        if cur_path.exists():
            cur_ranking = json.loads(cur_path.read_text(encoding="utf-8"))
        postings_diff = ranking_digest.new_postings_diff(
            cur_ranking, prev_ranking)
        if postings_diff and postings_diff.get("genuinely_new"):
            date_str = f"{datetime.now(UTC):%Y-%m-%d}"
            new_list_path = data_dir / ranking_digest.NEW_LIST_FILE.format(
                date=date_str)
            text = ranking_digest.new_list_markdown(
                postings_diff, cur_ranking,
                previous_name=prev_path.parent.name,
                generated_at=utcnow_iso())
            new_list_path.write_text(text, encoding="utf-8")
            new_list_display = f"data/{new_list_path.name}"
            log.info(
                "F107 novas: %d genuinamente nova(s) (%d no Top-30), "
                "%d re-sighting(s) de IDs reciclados -> %s",
                len(postings_diff["genuinely_new"]),
                ranking_digest.top_new_count(
                    cur_ranking, postings_diff["genuinely_new"]),
                len(postings_diff.get("re_seen") or []),
                new_list_display)
    except Exception as exc:  # noqa: BLE001 — F107 nunca derruba o run
        log.warning("F107: lista de novas nao gravada (run segue normal): "
                    "%s: %s", type(exc).__name__, exc)

    # F25 — as inaplicáveis do backlog hidratado descem das superfícies
    # exibidas JUNTO com as do liveness (MESMA semântica F20: o publish
    # recebe o conjunto unificado de inaplicáveis; mortas seguem separadas
    # p/ o badge "🔗 morta" nunca mentir sobre uma vaga viva).
    inapplicable_ids = inapplicable_ids | backlog_inapplicable_ids
    # F37.3 — as vagas EXCLUÍDAS do JSON não são mais "inaplicáveis exibidas":
    # saíram de vez. Nem a página nem o digest devem receber ids que já não
    # estão no eligible (o filtro de exibição é por id — id ausente seria
    # inócuo, mas o conjunto honesto é o dos que AINDA estão no JSON).
    if excl_stats.get("removed"):
        inapplicable_ids -= set(excl_stats.get("removed_ids") or [])

    # Fase 1 — publicacao do ranking em GitHub Pages (apos a coleta e o health;
    # nunca derruba o run: falha vira publish_error, reportada no Telegram).
    publish_error: str | None = None
    if pages_dir is not None:
        try:
            changed = publish_pages.publish_ranking(
                root, pages_dir,
                exit_code=exit_code,
                eligible=summary.get("eligible") or 0,
                run_id=summary.get("run_id") or utcnow_iso(),
                dead_link_ids=dead_ids | intake_dead_ids,
                **({"inapplicable_ids": inapplicable_ids}
                   if inapplicable_ids else {}),
            )
            if changed:
                log.info("ranking publicado em GitHub Pages (branch gh-pages)")
        except Exception as exc:  # noqa: BLE001 — publicacao e operacional, nao critica
            publish_error = f"{type(exc).__name__}: {exc}"
            log.error("publicacao GitHub Pages FALHOU: %s", publish_error)
    else:
        log.info("publicacao GitHub Pages desligada (sem --pages-dir)")

    # F39 — métrica diária de auditoria da remoção de hard-dead (padrão
    # JSONL do ``write_metrics``; mesmo pattern dos contadores de
    # aplicabilidade/hidratação). Provenance COMPLETA por id removido
    # (id, status HTTP, url) — auditável sem tocar o JSON de vagas.
    # Append-only, best-effort: falha vira log e NUNCA derruba o run.
    try:
        from internship_finder.metrics import write_metrics
        write_metrics(metrics_path, [{
            "type": "dead_link_removal",
            "run_id": summary.get("run_id") or utcnow_iso(),
            "timestamp": utcnow_iso(),
            "removed": removal_stats.get("removed", 0),
            "already_removed": removal_stats.get("already_removed", 0),
            "by_status": removal_stats.get("by_status", {}),
            "removed_entries": removal_stats.get("removed_entries", []),
        }])
    except Exception as exc:  # noqa: BLE001 — métrica é best-effort
        log.warning("F39: métrica dead_link_removal nao gravada: %s: %s",
                    type(exc).__name__, exc)

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
                # F13 — radar de empresas-alvo: watchlist versionada no repo
                # (config/company_watchlist.json; ausente = radar off, o
                # digest sai byte a byte igual ao de antes).
                watchlist_path=root / "config" / "company_watchlist.json",
                # F15 — mapa de qualidade do empregador: versionado no repo
                # (config/employer_quality.json; ausente = Top 5 sem ⭐,
                # o digest sai byte a byte igual ao de antes).
                employer_quality_path=root / "config" / "employer_quality.json",
                # F44 — gatilho de frescor do intel: os MESMOS três
                # arquivos versionados do relatório offline
                # (scripts/intel_freshness.py). Zero gatilhos = seção
                # ⏰ ausente; best-effort: nunca derruba o digest.
                intel_freshness_paths=(
                    root / "company_intel" / "company_intelligence.json",
                    root / "config" / "company_watchlist.json",
                    root / "config" / "employer_quality.json",
                ),
                # F25 — os DOIS Top 5 cortam as demovidas das superfícies
                # exibidas (mortas do liveness + inaplicáveis pós-hidratação,
                # backlog incluído): a vaga seguinte sobe, mesma semântica
                # da página. O JSON/CSV ficam intocados. F87: mortas do
                # 1º sighting (intake) entram no MESMO conjunto.
                excluded_ids=dead_ids | inapplicable_ids | intake_dead_ids,
                # F107 — display do artefato da lista completa das novas
                # (data/NEW-<date>.md, gravado acima): entra no header do 🆕.
                new_list_path=new_list_display,
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
        # F45 — seção 📅 Funil & sazonalidade (última antes do link, APÓS
        # as seções pessoais — a ordem F44 "⏰ Intel imediatamente antes
        # da 📌 Follow-up" fica intacta). Fontes: metrics do run + event
        # log F41 + ranking vivo; best-effort TOTAL (sem dados legíveis
        # = seção ausente, digest byte a byte o de antes). O digest montado
        # sem ranking (digest_lines None) não ganha a seção — o funil é
        # meta-informação do pipeline, não substituto de ranking.
        try:
            fn_lines = ranking_digest.funnel_seasonality_section(
                metrics_path=data_dir / "collection_metrics.jsonl",
                events_path=data_dir / "personal" / "application_events.jsonl",
                eligible_path=data_dir / "eligible_jobs.json",
            )
            if fn_lines and digest_lines:
                digest_lines = _splice_section_before_link(digest_lines,
                                                           fn_lines)
        except Exception as exc:  # noqa: BLE001 — F45 nunca derruba o run
            log.warning("secao F45 (funil & sazonalidade) nao montada "
                        "(run segue normal): %s", exc)
        try:
            _sync_personal_ranking(root, data_dir)
        except Exception as exc:  # noqa: BLE001 — sync nunca derruba o run
            log.warning("sync-ranking pessoal falhou (run segue normal): %s", exc)
        # F96 — fila manual-check (MANUAL-CHECK.md): UMA linha por item
        # não-avaliável/borderline (F87), liveness unknown (F94),
        # id_collision (ITEM 7-typo) e external_agreement_gate (F105 —
        # acordo padrão assinado pela universidade, gate EXTERNO), com
        # link DIRETO (alvo final dos redirects rdr/jump; F105: portal
        # oficial preferido ao agregador geobloqueado) e data do sighting.
        # Estágio LOCAL (zero rede), junto ao digest; best-effort TOTAL:
        # falha vira log e o run segue com o exit da coleta. Fila
        # PARALELA: nenhuma vaga sai do ranking/Top-5 (doutrina F87
        # mantida pela spec F96).
        try:
            mc_stats = manual_check.generate_manual_check(
                data_dir, generated_at=utcnow_iso(),
                seen_db_path=data_dir / "dataset_seen.db",
            )
            log.info(
                "F96 manual-check: %d linha(s) na fila (colisao de id: "
                "%d, gate de acordo externo: %d) — %s", mc_stats["rows"],
                mc_stats["collisions"]["flagged"],
                mc_stats["gates"]["flagged"], mc_stats["path"])
        except Exception as exc:  # noqa: BLE001 — F96 nunca derruba o run
            log.warning("F96: MANUAL-CHECK.md nao gerado (run segue "
                        "normal): %s: %s", type(exc).__name__, exc)
    else:
        log.info("digest/sync pulados (exit %d com eligible %s — gate "
                  "publication_allowed negativo)", exit_code,
                  summary.get("eligible"))

    # F103 — métrica de re-post/twin flagged (display-only; padrão F75).
    # Mesmas entradas do digest (eligible atual × snapshot da rotação) —
    # resultado determinístico idêntico ao flag do display. Best-effort.
    try:
        from internship_finder.repost_flag import count_reposts_from_paths
        repost_flagged_count = count_reposts_from_paths(
            data_dir / "eligible_jobs.json",
            archive_dir / "eligible_jobs.json")
        if repost_flagged_count > 0:
            from internship_finder.repost_flag import repost_metric
            metric_entry = repost_metric(repost_flagged_count)
            metric_entry.update({
                "type": "repost_flag",
                "run_id": summary.get("run_id") or utcnow_iso(),
                "timestamp": utcnow_iso(),
            })
            with (data_dir / "collection_metrics.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(metric_entry, ensure_ascii=False) + "\n")
            log.info("F103 repost_flagged: %d", repost_flagged_count)
    except Exception as exc:  # noqa: BLE001 — métrica nunca derruba o run
        log.warning("F103: métrica de re-post nao gravada (run segue): %s", exc)

    message = build_message(summary, report["alerts"], exit_code,
                            always_notify=args.always_notify,
                            disk_pct=disk_pct,
                            backup_error=backup_error,
                            seen_backup_error=seen_backup_error,
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

    # Fase 2 — enrichment incremental (apos TODOS os dados principais e a
    # mensagem: refresh -> eligibility -> ranking -> outputs -> enrichment).
    # Gates: --enrichment (default OFF) + INTERNSHIP_FINDER_ENRICHMENT=1 (F1,
    # default OFF — o cron de producao roda sem a env var) + gate UNICO
    # publication_allowed + NVIDIA_API_KEY (env herdado OU .env). Best-effort
    # TOTAL: qualquer exit/exception/timeout vira log de UMA linha e o exit
    # code do refresh NUNCA muda por causa do enrichment (spec secao 5).
    if args.enrichment:
        try:
            run_enrichment(root, exit_code, summary.get("eligible") or 0,
                           args.enrichment_limit, args.enrichment_top_n,
                           load_env_config(config_path),
                           max_secs=args.enrichment_max_secs)
        except Exception as exc:  # noqa: BLE001 — enrichment nunca derruba o refresh
            log.error("enrichment FALHOU: %s: %s", type(exc).__name__, exc)
    else:
        log.info("enrichment desligado (sem --enrichment)")

    # P1.3: o exit code final e o da coleta (0/1/2; 124 = teto estourado).
    # Toda a observabilidade (health/metricas/Telegram/limpeza/run_info) ja
    # rodou acima — so o status entregue ao SO muda. Antes o refresh sempre
    # terminava em 0 e o cron/systemd interpretavam falha como sucesso.
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())