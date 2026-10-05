"""Vitalidade de URL do top exibido (F11) — HEAD barato antes de publicar.

O feed da Bundesagentur nunca remove vagas preenchidas (medicao 04/10: vaga
SAP do topo com posted 25/08 retornando 410 Gone; mediana de idade das 502
vagas BA = 49 dias). O ranking continua correto, mas o usuario clica em
anuncios mortos. Este estagio verifica os URLs do topo EXIBIDO antes da
publicacao e devolve o conjunto de ids com link confirmadamente morto.

Regras (spec F11, item 3):

- **So 404/410 = morta** ( Gone). A vaga desce do top exibido; a proxima
  sobe. Nada e removido do JSON/CSV (data/ e intocavel — sao a base).
- **403/429/timeout/DNS = bloqueio de bot ou rede**: ignora, nao marca
  nada (marcar por 403 derrubaria vagas vivas de sites com bot-wall).
- **Falha total do estagio** (rede fora: nenhuma resposta HTTP recebida):
  log + devolve conjunto VAZIO — o pipeline nunca derruba por causa do
  check e nunca marca mortas sem evidencia.
- **Deadline defensivo**: estourou, devolve o que ja foi confirmado
  (404/410 observados com resposta HTTP real) e loga.

Check e sobre ``job.url`` (o link do titulo do card — o caso medido da
vaga SAP era o job.url em 410). ``apply_url`` nao e verificado (duplicaria
requests; o botao e honesto por construcao F6: so existe com URL real).
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path

__all__ = [
    "LIVENESS_UA", "LIVENESS_TIMEOUT_S", "LIVENESS_DELAY_S",
    "LIVENESS_DEADLINE_S", "check_liveness",
]

# UA honesto e identificavel (spec: "UA honesto") — nao imita browser.
LIVENESS_UA = "internship-finder-liveness/1.0 (job ranking link check)"

LIVENESS_TIMEOUT_S = 5.0   # timeout por request (spec: curto, ~5s)
LIVENESS_DELAY_S = 0.2    # pausa curta entre requests sequenciais
LIVENESS_DEADLINE_S = 240.0  # teto TOTAL do estagio (50 reqs * ~4.8s pior caso)

# Status que significam "anuncio removido para sempre" (spec: so 404/410).
_DEAD_STATUS = frozenset({404, 410})


def check_liveness(
    jobs: list[dict],
    *,
    timeout: float = LIVENESS_TIMEOUT_S,
    delay: float = LIVENESS_DELAY_S,
    deadline_s: float = LIVENESS_DEADLINE_S,
    opener=None,
    log=None,
) -> set[str]:
    """HEAD nos ``job.url`` (http/https) de ``jobs``; devolve ids mortos.

    ``jobs``: lista ORDENADA do topo exibido (o chamador decide o corte —
    refresh_daily passa o top-50 exibido pos regra 2/empresa). Cada job
    contribui no maximo 1 request. ``opener`` injetavel (testes/CI sem
    rede; default ``urllib.request.urlopen``). ``log`` = logging.Logger
    opcional. Best-effort TOTAL: qualquer problema interno devolve um
    conjunto possivelmente vazio — nunca levanta.
    """
    def _info(msg: str, *args) -> None:
        if log is not None:
            log.info(msg, *args)
        else:
            print("liveness: " + (msg % args if args else msg))

    def _warn(msg: str, *args) -> None:
        if log is not None:
            log.warning(msg, *args)
        else:
            print("liveness(WARN): " + (msg % args if args else msg))

    open_url = opener or urllib.request.urlopen
    started = time.monotonic()
    dead: set[str] = set()
    attempts = 0
    http_responses = 0  # qualquer resposta HTTP recebida (inclui 404/410)
    net_errors = 0
    try:
        for idx, job in enumerate(jobs):
            jid = str(job.get("id") or "")
            url = str(job.get("url") or "").strip()
            if not jid or not url.lower().startswith(("http://", "https://")):
                continue  # sem id/url verificavel: nao marcavel
            if time.monotonic() - started > deadline_s:
                _warn("deadline de %.0fs atingido apos %d checks; "
                      "seguindo com %d morta(s) confirmada(s)",
                      deadline_s, attempts, len(dead))
                break
            if idx > 0 and delay > 0:
                time.sleep(delay)
            attempts += 1
            req = urllib.request.Request(
                url, method="HEAD", headers={"User-Agent": LIVENESS_UA},
            )
            try:
                with open_url(req, timeout=timeout):
                    http_responses += 1  # 2xx/3xx: viva
            except urllib.error.HTTPError as exc:
                # HTTPError E uma resposta HTTP do servidor (site no ar).
                http_responses += 1
                if exc.code in _DEAD_STATUS:
                    dead.add(jid)
                    _info("morta %s: %s -> HTTP %d", jid, url, exc.code)
            except Exception:  # noqa: BLE001 — timeout/DNS/SSL/bloqueio
                net_errors += 1  # 403/429 chegam como HTTPError; rede nao
    except Exception as exc:  # noqa: BLE001 — estagio nunca derruba o run
        _warn("estagio falhou (%s: %s); seguindo sem novas marcas",
              type(exc).__name__, exc)
        return dead
    # Falha TOTAL de rede: nenhuma resposta HTTP de nenhuma tentativa —
    # nao ha evidencia de nada; nao marca ninguem (spec).
    if attempts > 0 and http_responses == 0 and net_errors == attempts:
        _warn("falha total de rede (%d/%d tentativas sem resposta HTTP); "
              "NENHUMA vaga marcada", net_errors, attempts)
        return set()
    _info("%d checks: %d morta(s), %d erro(s) de rede ignorado(s)",
          attempts, len(dead), net_errors)
    return dead


if __name__ == "__main__":  # uso manual: python scripts/url_liveness.py data/eligible_jobs.json
    import json
    import sys

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/eligible_jobs.json")
    jobs = json.loads(path.read_text(encoding="utf-8"))
    top = jobs[: int(sys.argv[2]) if len(sys.argv) > 2 else 50]
    print("dead ids:", sorted(check_liveness(top)))
