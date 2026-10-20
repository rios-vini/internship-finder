#!/usr/bin/env python3
"""Watchdog do override SAP (--no-agent, F74) — detecta dívida morta, NÃO remove.

CONTEXTO (âncoras medidas 19-20/10/2026): o override local
``TENANT_URL_OVERRIDES[("successfactors", "jobs", "SAP")] = "https://careers.sap.com"``
(Fase I, src/internship_finder/collectors/ats_scraper.py) existe porque o
inventário upstream aponta o careers da SAP para o host morto
``jobs.sap.com``. O conserto correto está no upstream: PR #292
(kalil0321/ats-scrapers, do dono, fase F2, aberto 01/10/2026 — 1 linha em
``ats-companies/successfactors.csv``) aguardando mantenedor. Quando o PR
for mergeado (ou o manifest vivo mudar a fatia SAP por outro caminho), o
override vira dívida morta — e o dono precisa SABER para remover.

O watchdog checa a cada tick (read-only, ~2 requests):

1. PR #292 upstream — GitHub REST (``state``/``merged``);
2. shape da fatia SAP no manifest VIVO (``storage.stapply.ai`` →
   ``by_ats_companies.successfactors.csv`` → linha ``SAP`` do companies.csv:
   tripla name,slug,url ancorada em ``ANCHORED_SHAPE``).

CRITÉRIO DE ALERTA (spec F74): PR #292 MERGEADO **OU** shape da fatia mudou
(linha alterada, ausente, ou fatia/manifest fora da forma ancorada) →
stdout com alerta (o cron no-agent entrega o stdout no Telegram) + 1 linha
no log ``sap_override_watchdog.log``. Frase literal do critério:
``override SAP pode ser obsoleto — remover é decisão do dono``.

PADRÃO casa (github_status_watchdog.py): alerta SÓ EM MUDANÇA de estado.
Estado observado persistido em ``.sap_override_watchdog_state`` (nunca
/tmp — sobrevive a reboot); mesma situação = tick silencioso (stdout
vazio = nada entregue, R$ 0). Primeira execução já degradada = alerta na
hora. Transição que NÃO dispara (ex.: PR closed sem merge — override
segue necessário) atualiza o estado em silêncio: o watchdog vigia a
OBSOLESCÊNCIA do override, não a biografia do PR.

O que ele NUNCA faz: NÃO remove o override, NÃO mergeia upstream, NÃO
escreve no repo/produção — só lê e alerta (a remoção é ato do dono).

CHECKLIST DE REMOÇÃO DO OVERRIDE (quando o alerta chegar; decisão do dono):
1. Confirmar o fix upstream PUBLICADO: PR mergeado + release PyPI do
   ats-scrapers + ``pip install -U`` (merge sem release não muda o
   pacote instalado — mesmo raciocínio do patch BambooHR F59.1).
2. Conferir que o manifest vivo traz ``SAP,jobs,https://careers.sap.com``
   (ou a forma nova) E que o pacote instalado resolve a linha nova.
3. Remover a entrada de ``TENANT_URL_OVERRIDES`` em
   ``src/internship_finder/collectors/ats_scraper.py`` + o teste
   correspondente (``test_fasei`` B1) + atualizar este watchdog.
4. Verificar a coleta SAP ao vivo (careers.sap.com/sitemal.xml ~900 itens).

KILL-SWITCH: env ``SAP_OVERRIDE_WATCHDOG`` (default ON; ``0`` = desligado —
o script sai em silêncio sem tocar na rede). Kill operacional do cron:
``hermes cron`` → pause/remove do job ``watchdog-sap-override`` (a tool
cronjob), depois apagar state/log em ``~/.hermes/scripts/``. O watchdog
self-remove de fato quando o checklist acima terminar (item 3).

Falha do próprio check (rede, HTTP, JSON/schema quebrado) = stdout de erro
+ exit 1 (aviso de falha SEMPRE entregue — watchdog quebrado não falha em
silêncio). Rate limit do GitHub (403/429 sem token) recorre 1x ao token do
``git credential fill`` (nunca hardcoded, nunca impresso).

Zero dependências além da stdlib; data/ intocada; produção intocada.
"""

from __future__ import annotations

import csv as _csv
import datetime as _dt
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# --- âncoras do critério F74 (re-verificar antes de editar; Passo 0) --------

PR_API_URL = "https://api.github.com/repos/kalil0321/ats-scrapers/pulls/292"
PR_HTML_URL = "https://github.com/kalil0321/ats-scrapers/pull/292"
MANIFEST_URL = "https://storage.stapply.ai/jobhive/v1/manifest.json"

ATS_KEY = "successfactors"          # fatia do manifest (by_ats_companies)
COMPANY_NAME = "SAP"                # identidade EXATA da chave do override
ANCHORED_SHAPE = ("SAP", "jobs", "https://jobs.sap.com")  # verbatim 20/10
ANCHORED_CSV_HEADER = ("name", "slug", "url")             # verbatim 20/10

OVERRIDE_KEY = ("successfactors", "jobs", "SAP")
OVERRIDE_URL = "https://careers.sap.com"
OVERRIDE_SRC = "src/internship_finder/collectors/ats_scraper.py"

ALERT_PHRASE = "override SAP pode ser obsoleto — remover é decisão do dono"
USER_AGENT = "hermes-sap-override-watchdog/1.0 (F74)"

# --- knobs (env; defaults sanos — padrão disk/scraper/github watchdogs) ------

DEFAULT_STATE = Path("~/.hermes/scripts/.sap_override_watchdog_state")
DEFAULT_LOG = Path("~/.hermes/scripts/sap_override_watchdog.log")


class SapWatchdogError(Exception):
    """Falha do próprio check (transporte/parse) — exit 1, nunca alerta falso."""


# --- avaliação pura (offline-testável; fixtures no test_f74) ----------------


def pr_state(pr: dict) -> str:
    """Classifica o payload do PR #292: open | merged | closed_unmerged.

    Surpresa de schema = SapWatchdogError (o dono olha; nunca silêncio).
    """
    if not isinstance(pr, dict):
        raise SapWatchdogError(f"payload do PR não é objeto: {type(pr).__name__}")
    state = pr.get("state")
    merged = pr.get("merged")
    if state == "open" and merged is False:
        return "open"
    if state == "closed" and merged is True:
        return "merged"
    if state == "closed" and merged is False:
        return "closed_unmerged"
    raise SapWatchdogError(
        f"payload do PR #292 fora do contrato (state={state!r}, merged={merged!r})")


def sap_csv_url(manifest: object) -> str | None:
    """URL do companies.csv da fatia successfactors no manifest vivo.

    None = fatia fora da forma ancorada (ausente/movida) — SEMÂNTICO: é
    mudança de mundo observada, vira alerta, não erro de check.
    """
    if not isinstance(manifest, dict):
        return None
    by_ats = manifest.get("by_ats_companies")
    if not isinstance(by_ats, dict):
        return None
    slice_ = by_ats.get(ATS_KEY)
    if not isinstance(slice_, dict):
        return None
    url = slice_.get("csv")
    if isinstance(url, str) and url:
        return url
    return None


def sap_shape(csv_text: str) -> tuple[str, str, str] | None:
    """Tupla (name, slug, url) da linha SAP do companies.csv; None se ausente.

    Header ancorado EXATO ``name,slug,url``: schema que mudou é erro de
    check (SapWatchdogError) — a mensagem diz "atualize o watchdog", não
    "linha sumiu" (que seria mentira). Nome é match EXATO em campo[0]
    (Sapiens/SAP Gold Partner nunca casam); o módulo csv resolve aspas.
    """
    if not isinstance(csv_text, str):
        raise SapWatchdogError("companies.csv não é texto (transporte?)")
    try:
        reader = _csv.reader(io.StringIO(csv_text))
        header = next(reader, None)
    except _csv.Error as exc:
        raise SapWatchdogError(f"companies.csv ilegível: {exc}") from exc
    if tuple(header or ()) != ANCHORED_CSV_HEADER:
        raise SapWatchdogError(
            f"header do companies.csv mudou: {header!r} != "
            f"{ANCHORED_CSV_HEADER!r} — atualizar o watchdog (F74)")
    for row in reader:
        if row and row[0] == COMPANY_NAME:
            padded = (list(row) + ["", ""])[:3]
            return (padded[0], padded[1], padded[2])
    return None


def trigger_reasons(state: str, shape: tuple[str, str, str] | None) -> list[str]:
    """Motivos de obsolescência; [] = override segue vivo e necessário."""
    reasons: list[str] = []
    if state == "merged":
        reasons.append(
            f"PR #292 upstream MERGEADO (kalil0321/ats-scrapers; {PR_HTML_URL})")
    if shape is None:
        reasons.append(
            "fatia SAP ausente do manifest vivo na forma ancorada "
            f"({','.join(ANCHORED_SHAPE)} em by_ats_companies.{ATS_KEY}.csv)")
    elif shape != ANCHORED_SHAPE:
        reasons.append(
            f"shape da fatia SAP mudou: ancorado "
            f"{','.join(ANCHORED_SHAPE)} -> observado {','.join(shape)}")
    return reasons


def signature(state: str, shape: tuple[str, str, str] | None) -> str:
    """Linha de estado (state file) — comparação de mudança é string pura."""
    shape_s = "ausente" if shape is None else "|".join(shape)
    return f"pr={state};shape={shape_s}"


def format_alert(
    reasons: list[str],
    pr: dict | None,
    manifest: object,
    shape: tuple[str, str, str] | None,
) -> str:
    """Texto do alerta (stdout → Telegram). Frase literal do critério dentro."""
    pr = pr if isinstance(pr, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}
    observed = "ausente" if shape is None else ",".join(shape)
    merged_at = pr.get("merged_at") or "?"
    updated_at = manifest.get("updated_at") or "?"
    lines = [
        f"SAP-OVERRIDE-WATCHDOG (F74): {ALERT_PHRASE}.",
        "",
        "Motivo(s) detectado(s):",
    ]
    lines += [f"- {r}" for r in reasons]
    lines += [
        "",
        f"Override local: TENANT_URL_OVERRIDES{OVERRIDE_KEY!r} = {OVERRIDE_URL!r}",
        f"em {OVERRIDE_SRC} (Fase I). O upstream corrigir a URL torna o",
        "override dívida morta — mas só o dono decide remover.",
        "",
        f"Evidência: PR {PR_HTML_URL} (merged_at={merged_at}) | manifest",
        f"{MANIFEST_URL} (updated_at={updated_at}) | shape observado: {observed}.",
        "",
        "O watchdog NÃO remove nada e NÃO mergeia upstream. Checklist de",
        "remoção no docstring de scripts/watchdog_sap_override.py (release",
        "PyPI + upgrade ANTES de tirar o override; test_fasei B1 junto).",
    ]
    return "\n".join(lines)


# --- I/O live (urllib; o token do credential fill NUNCA é impresso) ----------


def _git_token() -> str | None:
    """Token do git credential fill (fallback de rate limit), ou None."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True, text=True, timeout=15, check=False)
        for line in out.stdout.splitlines():
            if line.startswith("password="):
                value = line.split("=", 1)[1]
                return value or None
    except Exception:
        return None
    return None


def _http_bytes(url: str, timeout: float, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _timeout() -> float:
    return float(os.environ.get("SAP_OVERRIDE_WATCHDOG_TIMEOUT", "20"))


def fetch_pr() -> dict:
    """PR #292 via GitHub REST (repo público). 403/429 → 1 retry com token."""
    headers = {"Accept": "application/vnd.github+json"}
    timeout = _timeout()
    try:
        return json.loads(_http_bytes(PR_API_URL, timeout, headers))
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            token = _git_token()
            if token:
                try:
                    return json.loads(_http_bytes(
                        PR_API_URL, timeout,
                        {**headers, "Authorization": f"Bearer {token}"}))
                except urllib.error.HTTPError as exc2:
                    raise SapWatchdogError(
                        f"PR #292: HTTP {exc2.code} mesmo com token "
                        "(rate limit compartilhado do IP?)") from exc2
        raise SapWatchdogError(
            f"PR #292: HTTP {exc.code} (api.github.com)") from exc
    except SapWatchdogError:
        raise
    except Exception as exc:
        raise SapWatchdogError(f"PR #292: {exc}") from exc


def fetch_manifest() -> object:
    """Manifest vivo (o MESMO que o pipeline consome; dataset_source)."""
    try:
        return json.loads(_http_bytes(MANIFEST_URL, _timeout()))
    except Exception as exc:
        raise SapWatchdogError(f"manifest: {exc}") from exc


def fetch_csv(url: str) -> str:
    """companies.csv da fatia (resolvido pelo manifest, nunca hardcoded)."""
    try:
        return _http_bytes(url, _timeout()).decode("utf-8", errors="replace")
    except Exception as exc:
        raise SapWatchdogError(f"companies.csv: {exc}") from exc


# --- estado (padrão github_status_watchdog: nunca /tmp; atômico) -------------


def _expand(path: str | Path | None, default: Path) -> Path:
    """Path absoluto (env expanduser) — default = ~/.hermes/scripts/ da casa."""
    return Path(os.path.expanduser(str(path if path is not None else default)))


def _read_state(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8").strip()
        return content or None
    except OSError:
        return None


def _write_state(path: Path, sig: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(sig + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# --- main (fetchers/paths injetáveis — a suíte test_f74 roda 100% offline) ---


def main(
    fetch_pr=fetch_pr,
    fetch_manifest=fetch_manifest,
    fetch_csv=fetch_csv,
    state_path: str | Path | None = None,
    log_path: str | Path | None = None,
) -> int:
    """Um tick do watchdog. 0 = silêncio/alerta; 1 = falha do próprio check.

    Fetchers e paths injetáveis: a suíte ``test_f74`` exerce TODOS os
    caminhos 100% offline (padrão test_f59_1); o cron roda os defaults
    vivos. Estado só é escrito em check BEM-SUCEDIDO (github_status
    watchdog: falha não corrompe a última observação boa).
    """
    if os.environ.get("SAP_OVERRIDE_WATCHDOG", "1") == "0":
        return 0  # kill-switch: sem rede, sem estado, sem output

    state = _expand(state_path, DEFAULT_STATE)
    log = _expand(log_path, DEFAULT_LOG)

    try:
        pr = fetch_pr()
        manifest = fetch_manifest()
        url = sap_csv_url(manifest)
        shape = sap_shape(fetch_csv(url)) if url is not None else None
        pr_s = pr_state(pr)
        reasons = trigger_reasons(pr_s, shape)
        sig = signature(pr_s, shape)
        prev = _read_state(state)
        if reasons and prev != sig:
            msg = format_alert(reasons, pr, manifest, shape)
            try:
                stamp = _dt.datetime.now(_dt.timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ")
                _append_log(log, f"{stamp} F74 {'; '.join(reasons)}")
            except OSError as exc:
                msg += f"\n(log de alertas indisponível: {exc})"
            print(msg)
        _write_state(state, sig)
        return 0
    except SapWatchdogError as exc:
        print(f"SAP-OVERRIDE-WATCHDOG: falha no check: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
