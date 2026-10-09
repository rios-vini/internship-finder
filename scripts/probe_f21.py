"""Probe F21 — revalidação ao vivo das fontes Tier 1 (manual, fora do CI).

NAO é teste automatizado (sem assertions, fora do array do CI — mesmo
padrão do manifest_probe.py): consulta as fontes reais UMA vez, sequencial,
com delay, timeout 30s por fonte, UA honesto, e imprime status/bytes/
tempo de cada uma + o summary do estágio completo. Salva snippets em
./probes/ (workspace local, gitignored) para fixtures de test_f21.

Uso: python scripts/probe_f21.py [--stage]   (--stage roda também o
      collect_research_sources real e imprime tempos/contagens por fonte)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

OUT = Path(__file__).resolve().parent.parent / "probes"
UA = "internship-finder-liveness/1.1 (F21 source probe; contact: repo owner)"
TIMEOUT = 30.0
DELAY = 4.0

SOURCES = [
    ("mpg_rss", "https://www.mpg.de/feeds/jobs.rss"),
    ("tu_berlin", "https://www.jobs.tu-berlin.de/stellenausschreibungen"),
    ("leibniz", "https://www.leibniz-gemeinschaft.de/en/careers/jobs"),
    ("arbeitnow", "https://www.arbeitnow.com/api/job-board-api"),
    ("remoteok", "https://remoteok.com/api"),
    ("freehire", "https://freehire.me/api/v1/jobs?limit=100"),
]


def fetch(url: str):
    t0 = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(), time.monotonic() - t0, None
    except Exception as exc:  # noqa: BLE001 - probe: erro é o resultado
        return None, b"", time.monotonic() - t0, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", action="store_true",
                        help="roda também o estágio collect_research_sources real")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    for name, url in SOURCES:
        status, body, dt, err = fetch(url)
        (OUT / f"{name}.txt").write_bytes(body[:5000])
        print(f"{name}: status={status} bytes={len(body)} {dt:.2f}s err={err}")
        time.sleep(DELAY)

    if args.stage:
        from internship_finder.research_sources import collect_research_sources

        jobs, summary = collect_research_sources()
        for name, s in summary.get("sources", {}).items():
            print(f"stage {name}: status={s.get('status')} rows={s.get('rows_seen')} "
                  f"jobs={s.get('jobs')} dur={s.get('duration')}s err={s.get('error')}")
        print(f"TOTAL: {summary.get('jobs')} jobs em {summary.get('duration')}s "
              f"(status={summary.get('status')})")

    print("PROBE F21 CONCLUIDO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
