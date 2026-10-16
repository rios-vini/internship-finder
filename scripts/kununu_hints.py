"""Probe F44 — kununu_hints: MANCHETES de score novo para alvo sem Kununu.

NAO é teste automatizado e NAO faz parte do CI/cron (mesmo padrão do
probe_f21.py): comando MANUAL, best-effort, para o RITUAL HUMANO da F44
("automatize o gatilho, humanize o fetch"):

    1. ``intel_freshness`` aponta os alvos da watchlist SEM score no
       mapa F15 (seção ⏰ do digest / relatório offline);
    2. ESTE probe consulta a busca pública do Kununu UMA vez por alvo
       (delay entre elas, timeout curto, UA honesto) e imprime, para
       cada resultado plausível, "possível score novo, verificar" + a
       URL — o HUMANO abre, confere e faz a curadoria (atualizar
       kununu_score/sources/checked no ``config/employer_quality.json``;
       o intel só é editado junto com sources/checked);
    3. NUNCA escreve em arquivo algum (o mapa F15 é curadoria manual —
       o pipeline não escreve nele, por design F15).

Degradação graciosa (contrato): bloqueado/403/timeout/qualquer erro ->
a empresa é pulada em silêncio; nada é impresso para ela. O exit code
é SEMPRE 0 (probe: o erro é o resultado, não uma falha do comando).

Uso:

    python scripts/kununu_hints.py [--top 5] [--timeout 10] [--delay 4]

    # alvos vêm do intel_freshness (mesmos arquivos versionados);
    # --top limita quantos alvos sondar na sessão (default 5: o ritual
    # é humano, 30s/empresa — sondar 27 de uma vez é anti-produto).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import intel_freshness as ifr  # noqa: E402

UA = ("internship-finder-kununu-hints/1.0 (F44 manual probe; "
      "contact: repo owner)")
SEARCH_URL = "https://www.kununu.com/de/search"
# Padrão tolerante do snippet de busca: "3,8" ou "3.8" com até 1 decimal
# (o Kununu exibe com vírgula; aceitamos os dois por tolerância).
_SCORE_RE = re.compile(r"([0-4](?:[.,]\d{1,2})?)\s*(?:/|von)\s*5")


def _fetch(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — probe: erro é o resultado
        return None, ""


def probe_company(name: str, *, timeout: float) -> tuple[str, str | None]:
    """Sonda a busca pública por ``name``; (url, score_text|None).

    Retorna a URL consultada e, se a página trouxer um snippet com
    score plausível, o texto cru do match (o HUMANO verifica antes de
    curar — o probe nunca afirma score, só aponta "possível").
    """
    q = urllib.parse.quote_plus(name)
    url = f"{SEARCH_URL}?q={q}"
    status, body = _fetch(url, timeout)
    if status != 200 or not body:
        return url, None
    m = _SCORE_RE.search(body)
    if not m:
        return url, None
    return url, m.group(1)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="F44 — kununu_hints: probe MANUAL de possíveis "
                    "scores novos (best-effort; NUNCA escreve no mapa).")
    parser.add_argument("--top", type=int, default=5,
                        help="quantos alvos sondar (default 5)")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="timeout por requisição em segundos (default 10)")
    parser.add_argument("--delay", type=float, default=4.0,
                        help="delay entre requisições em segundos (default 4)")
    parser.add_argument("--intel", default=str(root / ifr.INTEL_DEFAULT))
    parser.add_argument("--watchlist", default=str(root / ifr.WATCHLIST_DEFAULT))
    parser.add_argument("--employer-quality",
                        default=str(root / ifr.QUALITY_DEFAULT))
    args = parser.parse_args(argv)

    watchlist = ifr.load_watchlist_companies(args.watchlist)
    quality = ifr.load_employer_quality_companies(args.employer_quality)
    targets = ifr.no_kununu_targets(watchlist, quality, top=0)
    if not targets:
        print("nenhum alvo sem Kununu (mapa F15 cobre a watchlist) — nada a sondar")
        return 0
    subset = targets[:max(0, args.top)]
    print(f"{len(targets)} alvo(s) sem score no mapa; sondando {len(subset)} "
          f"(timeout {args.timeout:g}s, delay {args.delay:g}s, UA honesto)")
    found = 0
    for name in subset:
        url, score_text = probe_company(name, timeout=args.timeout)
        if score_text is None:
            # degradação graciosa: bloqueio/403/timeout/sem snippet ->
            # NADA é impresso para a empresa (silêncio, não ruído)
            pass
        else:
            found += 1
            print(f"possível score novo, verificar: {name} — snippet "
                  f"\"{score_text}\" — {url}")
        time.sleep(args.delay)
    if found == 0:
        print("nenhum snippet de score recuperado (bloqueio/403/sem "
              "indexação) — CDP attach manual segue sendo o ritual")
    else:
        print(f"{found} possível(is) score(s) novo(s) — HUMANO verifica e "
              "cura (kununu_score + sources/checked no mapa F15; o probe "
              "NUNCA escreve)")
    print("PROBE F44 (kununu_hints) CONCLUIDO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
