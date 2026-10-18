#!/usr/bin/env python3
''''true; V="$(dirname "$0")/../.venv/bin/python"; [ -x "$V" ] || V=python3; exec "$V" -- "$0" "$@" # '''
"""Suite F49 — higiene do registry: 6 fontes mortas/zeradas silenciosas.

Poliglota de 1 linha (bash: ``exec`` re-invoca sob python3; python: string
no-op) — ``bash scripts/test_f49.py`` e ``python scripts/test_f49.py`` rodam
a mesma suíte; o CI usa ``python scripts/$t.py`` (contrato ci.yml).

Diagnóstico medido 17-18/10/2026 (data/collection_metrics.jsonl até o run
17/10 09:40 + probes manuais UA-honesto documentados no relatório F49;
NADA de rede aqui — fixtures verbatim, zero socket):

- Kuehne+Nagel — o tenant secundário cornerstone:kuehne-nagel MORREU
  (kuehne-nagel.csod.com = NXDOMAIN, probe 18/10); o tenant declarado no
  registry (phenom:nan) está SAUDÁVEL (~1100 vagas/dia). Decisão: MANTER
  (registro morto do runtime; exclusão per-tenant já recusada em 17/09).
- SMA — o tenant secundário oracle (homônimo UAE, decisão 17/09) tem slug
  relativo que o scraper oracle rejeita; successfactors:sma SAUDÁVEL
  (~116/dia). Decisão: MANTER.
- AkzoNobel — regressão REAL: careers.akzonobel.com/sitemal.xml responde
  HTTP 500 (probe 18/10, 0.5s); funcionava até 28/09 (269-272 vagas/dia).
  Swiss Re no MESMO tenant segue ok (40/40) — o 500 é da URL. Decisão:
  MANTER + conserto proposto (lado da empresa; monitorar).
- Lidl — timeout documentado por design (registry.py: feed sob demanda
  ~120 MB; probe 18/10: HTTP 200, TTFB 4.8s, streaming 7.9 MB/30s — o
  tenant timeout de 85s nunca basta). Decisão: MANTER.
- Siemens Healthineers — MIGRAÇÃO DE ATS: a URL avature responde 302 ->
  careers.siemens-healthineers.com/global/en (plataforma Phenom, markers
  cdn.phenompeople.com no probe 18/10); o scraper parseia a homepage
  Phenom = 0 vagas e o health vê "empty" — QUEBRA SILencIOSA, não
  sazonalidade. Decisão: MANTER + conserto proposto (re-validar resolução
  phenom via verify_companies.py e atualizar o registry).
- BCG — o widget BambooHR (embed2.php) passou a servir JSON puro (probe
  18/10: 623 bytes Accept-agnóstico, com as MESMAS 2 vagas Remote de
  07/10); o parser HTML do scraper (bhrPositionID_) acha nada -> "empty".
  Quebra silenciosa de PARSE, não fim das vagas. Decisão: MANTER +
  conserto proposto (parser no pacote upstream ats_scrapers).

VISIBILIDADE (escopo 3 da F49): o digest real de 15-17/10 repetia as mesmas
~7 linhas de problemas (~800 chars = 20% do teto 4096; só o contador mudava
dia a dia); em 16/10 a mensagem ficou a 38 chars do teto (4058/4096) — 1
linha nova e o compactador F6.1 nivel 2 apagaria TODOS os problemas para
"⚠️ N problemas (ver ranking)" (link sem os detalhes). Fix testado aqui:
falha crônica (recurring_error >= CHRONIC_FAILURE_RUNS = 15) colapsa em 1
linha agregada com nomes + contador; falha nova/curta mantém linha própria.

Trava as REGRAS, não contagens vivas (lição F7/F9): fixtures VERBATIM
(linhas type:tenant reais do JSONL de 17/10, campos mínimos), classificação
pela regra VIVA do health.py (build_health_report) e renderização pela
build_message viva. ZERO REDE.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from internship_finder.health import build_health_report  # noqa: E402
from internship_finder.registry import SEED  # noqa: E402
import refresh_daily  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


# ---------------------------------------------------------------------------
# Fixtures VERBATIM — linhas type:tenant reais de data/collection_metrics.jsonl
# (run de 17/10 09:40 UTC), campos mínimos; valores copiados sem invenção.
# ---------------------------------------------------------------------------

F_KN_CSOD_CHRONIC = [{'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-02T09:00:02.543142+00:00', 'timestamp': '2026-10-02T09:10:32.202252+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-03T09:00:02.347210+00:00', 'timestamp': '2026-10-03T09:23:15.808331+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-04T09:00:02.734639+00:00', 'timestamp': '2026-10-04T09:24:14.616135+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-05T09:00:02.914436+00:00', 'timestamp': '2026-10-05T09:23:41.140551+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-06T09:00:02.566746+00:00', 'timestamp': '2026-10-06T09:23:58.256124+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-07T09:00:02.282516+00:00', 'timestamp': '2026-10-07T09:24:02.049496+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-08T09:00:03.323933+00:00', 'timestamp': '2026-10-08T09:24:17.396910+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-09T09:00:02.965409+00:00', 'timestamp': '2026-10-09T09:25:44.737241+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-10T09:00:02.909059+00:00', 'timestamp': '2026-10-10T09:27:36.244442+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-11T09:00:02.439826+00:00', 'timestamp': '2026-10-11T09:26:49.358573+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-12T09:00:02.615257+00:00', 'timestamp': '2026-10-12T09:26:10.273468+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-13T09:00:02.266583+00:00', 'timestamp': '2026-10-13T09:28:49.461242+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-14T09:00:02.782708+00:00', 'timestamp': '2026-10-14T09:31:22.630410+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-15T09:00:02.834853+00:00', 'timestamp': '2026-10-15T09:32:44.588635+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-16T09:00:02.332330+00:00', 'timestamp': '2026-10-16T09:34:07.699795+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-17T09:00:02.925663+00:00', 'timestamp': '2026-10-17T09:32:08.480653+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}]

F_SMA_ORACLE_CHRONIC = [{'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-02T09:00:02.543142+00:00', 'timestamp': '2026-10-02T09:10:32.202934+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-03T09:00:02.347210+00:00', 'timestamp': '2026-10-03T09:23:15.808655+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-04T09:00:02.734639+00:00', 'timestamp': '2026-10-04T09:24:14.616447+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-05T09:00:02.914436+00:00', 'timestamp': '2026-10-05T09:23:41.140878+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-06T09:00:02.566746+00:00', 'timestamp': '2026-10-06T09:23:58.256403+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-07T09:00:02.282516+00:00', 'timestamp': '2026-10-07T09:24:02.049852+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-08T09:00:03.323933+00:00', 'timestamp': '2026-10-08T09:24:17.397442+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-09T09:00:02.965409+00:00', 'timestamp': '2026-10-09T09:25:44.737564+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-10T09:00:02.909059+00:00', 'timestamp': '2026-10-10T09:27:36.244776+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-11T09:00:02.439826+00:00', 'timestamp': '2026-10-11T09:26:49.358937+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-12T09:00:02.615257+00:00', 'timestamp': '2026-10-12T09:26:10.274065+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-13T09:00:02.266583+00:00', 'timestamp': '2026-10-13T09:28:49.461814+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-14T09:00:02.782708+00:00', 'timestamp': '2026-10-14T09:31:22.630878+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-15T09:00:02.834853+00:00', 'timestamp': '2026-10-15T09:32:44.589157+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-16T09:00:02.332330+00:00', 'timestamp': '2026-10-16T09:34:07.700238+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-17T09:00:02.925663+00:00', 'timestamp': '2026-10-17T09:32:08.481119+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}]

F_AKZO_REG_CHRONIC = [{'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-09-26T09:00:03.156225+00:00', 'timestamp': '2026-09-26T09:10:05.606262+00:00', 'status': 'ok', 'collected': 272, 'error_code': None}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-09-27T09:00:02.262867+00:00', 'timestamp': '2026-09-27T09:10:04.944689+00:00', 'status': 'ok', 'collected': 271, 'error_code': None}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-09-28T09:00:02.381149+00:00', 'timestamp': '2026-09-28T09:10:43.042891+00:00', 'status': 'ok', 'collected': 269, 'error_code': None}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-09-29T09:00:02.445884+00:00', 'timestamp': '2026-09-29T09:10:39.684257+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-09-30T09:00:02.885501+00:00', 'timestamp': '2026-09-30T09:10:56.986987+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-01T09:00:02.311411+00:00', 'timestamp': '2026-10-01T09:10:37.939970+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-02T09:00:02.543142+00:00', 'timestamp': '2026-10-02T09:10:32.200752+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-03T09:00:02.347210+00:00', 'timestamp': '2026-10-03T09:23:15.807698+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-04T09:00:02.734639+00:00', 'timestamp': '2026-10-04T09:24:14.615350+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-05T09:00:02.914436+00:00', 'timestamp': '2026-10-05T09:23:41.139930+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-06T09:00:02.566746+00:00', 'timestamp': '2026-10-06T09:23:58.255470+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-07T09:00:02.282516+00:00', 'timestamp': '2026-10-07T09:24:02.048903+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-08T09:00:03.323933+00:00', 'timestamp': '2026-10-08T09:24:17.396031+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-09T09:00:02.965409+00:00', 'timestamp': '2026-10-09T09:25:44.736672+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-10T09:00:02.909059+00:00', 'timestamp': '2026-10-10T09:27:36.243909+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-11T09:00:02.439826+00:00', 'timestamp': '2026-10-11T09:26:49.358028+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-12T09:00:02.615257+00:00', 'timestamp': '2026-10-12T09:26:10.272486+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-13T09:00:02.266583+00:00', 'timestamp': '2026-10-13T09:28:49.460281+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-14T09:00:02.782708+00:00', 'timestamp': '2026-10-14T09:31:22.629660+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-15T09:00:02.834853+00:00', 'timestamp': '2026-10-15T09:32:44.587912+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-16T09:00:02.332330+00:00', 'timestamp': '2026-10-16T09:34:07.699111+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}, {'type': 'tenant', 'source': 'successfactors:careers', 'company': 'AkzoNobel', 'run_id': '2026-10-17T09:00:02.925663+00:00', 'timestamp': '2026-10-17T09:32:08.479991+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'}]

F_LIDL_TIMEOUT = [{'type': 'tenant', 'source': 'successfactors:lidlstiftuP2', 'company': 'Lidl', 'run_id': '2026-10-11T09:00:02.439826+00:00', 'timestamp': '2026-10-11T09:26:49.358593+00:00', 'status': 'ok', 'collected': 22203, 'error_code': None}, {'type': 'tenant', 'source': 'successfactors:lidlstiftuP2', 'company': 'Lidl', 'run_id': '2026-10-12T09:00:02.615257+00:00', 'timestamp': '2026-10-12T09:26:10.273501+00:00', 'status': 'ok', 'collected': 22144, 'error_code': None}, {'type': 'tenant', 'source': 'successfactors:lidlstiftuP2', 'company': 'Lidl', 'run_id': '2026-10-13T09:00:02.266583+00:00', 'timestamp': '2026-10-13T09:28:49.461279+00:00', 'status': 'ok', 'collected': 22054, 'error_code': None}, {'type': 'tenant', 'source': 'successfactors:lidlstiftuP2', 'company': 'Lidl', 'run_id': '2026-10-14T09:00:02.782708+00:00', 'timestamp': '2026-10-14T09:31:22.630452+00:00', 'status': 'timeout', 'collected': 0, 'error_code': 'TIMEOUT'}, {'type': 'tenant', 'source': 'successfactors:lidlstiftuP2', 'company': 'Lidl', 'run_id': '2026-10-15T09:00:02.834853+00:00', 'timestamp': '2026-10-15T09:32:44.588678+00:00', 'status': 'timeout', 'collected': 0, 'error_code': 'TIMEOUT'}]

F_SH_ZERO = [{'type': 'tenant', 'source': 'avature:https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs', 'company': 'Siemens Healthineers', 'run_id': '2026-09-26T09:00:03.156225+00:00', 'timestamp': '2026-09-26T09:10:05.608504+00:00', 'status': 'ok', 'collected': 6, 'error_code': None}, {'type': 'tenant', 'source': 'avature:https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs', 'company': 'Siemens Healthineers', 'run_id': '2026-09-27T09:00:02.262867+00:00', 'timestamp': '2026-09-27T09:10:04.946271+00:00', 'status': 'ok', 'collected': 6, 'error_code': None}, {'type': 'tenant', 'source': 'avature:https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs', 'company': 'Siemens Healthineers', 'run_id': '2026-09-28T09:00:02.381149+00:00', 'timestamp': '2026-09-28T09:10:43.044978+00:00', 'status': 'ok', 'collected': 6, 'error_code': None}, {'type': 'tenant', 'source': 'avature:https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs', 'company': 'Siemens Healthineers', 'run_id': '2026-09-29T09:00:02.445884+00:00', 'timestamp': '2026-09-29T09:10:39.685993+00:00', 'status': 'empty', 'collected': 0, 'error_code': None}, {'type': 'tenant', 'source': 'avature:https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs', 'company': 'Siemens Healthineers', 'run_id': '2026-09-30T09:00:02.885501+00:00', 'timestamp': '2026-09-30T09:10:56.989129+00:00', 'status': 'empty', 'collected': 0, 'error_code': None}, {'type': 'tenant', 'source': 'avature:https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs', 'company': 'Siemens Healthineers', 'run_id': '2026-10-01T09:00:02.311411+00:00', 'timestamp': '2026-10-01T09:10:37.942121+00:00', 'status': 'empty', 'collected': 0, 'error_code': None}]

F_BCG_ZERO = [{'type': 'tenant', 'source': 'bamboohr:bcg', 'company': 'BCG', 'run_id': '2026-10-05T09:00:02.914436+00:00', 'timestamp': '2026-10-05T09:23:41.140001+00:00', 'status': 'ok', 'collected': 3, 'error_code': None}, {'type': 'tenant', 'source': 'bamboohr:bcg', 'company': 'BCG', 'run_id': '2026-10-06T09:00:02.566746+00:00', 'timestamp': '2026-10-06T09:23:58.255512+00:00', 'status': 'ok', 'collected': 3, 'error_code': None}, {'type': 'tenant', 'source': 'bamboohr:bcg', 'company': 'BCG', 'run_id': '2026-10-07T09:00:02.282516+00:00', 'timestamp': '2026-10-07T09:24:02.048951+00:00', 'status': 'ok', 'collected': 3, 'error_code': None}, {'type': 'tenant', 'source': 'bamboohr:bcg', 'company': 'BCG', 'run_id': '2026-10-08T09:00:03.323933+00:00', 'timestamp': '2026-10-08T09:24:17.396130+00:00', 'status': 'empty', 'collected': 0, 'error_code': None}, {'type': 'tenant', 'source': 'bamboohr:bcg', 'company': 'BCG', 'run_id': '2026-10-09T09:00:02.965409+00:00', 'timestamp': '2026-10-09T09:25:44.736739+00:00', 'status': 'empty', 'collected': 0, 'error_code': None}, {'type': 'tenant', 'source': 'bamboohr:bcg', 'company': 'BCG', 'run_id': '2026-10-10T09:00:02.909059+00:00', 'timestamp': '2026-10-10T09:27:36.243970+00:00', 'status': 'empty', 'collected': 0, 'error_code': None}]

F_KN_PHENOM_HEALTHY = [{'type': 'tenant', 'source': 'phenom:nan', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-15T09:00:02.834853+00:00', 'timestamp': '2026-10-15T09:32:44.588619+00:00', 'status': 'ok', 'collected': 1101, 'error_code': None}, {'type': 'tenant', 'source': 'phenom:nan', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-16T09:00:02.332330+00:00', 'timestamp': '2026-10-16T09:34:07.699785+00:00', 'status': 'ok', 'collected': 1109, 'error_code': None}, {'type': 'tenant', 'source': 'phenom:nan', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-17T09:00:02.925663+00:00', 'timestamp': '2026-10-17T09:32:08.480643+00:00', 'status': 'ok', 'collected': 1115, 'error_code': None}]

F_SMA_SF_HEALTHY = [{'type': 'tenant', 'source': 'successfactors:sma', 'company': 'SMA', 'run_id': '2026-10-15T09:00:02.834853+00:00', 'timestamp': '2026-10-15T09:32:44.589147+00:00', 'status': 'ok', 'collected': 113, 'error_code': None}, {'type': 'tenant', 'source': 'successfactors:sma', 'company': 'SMA', 'run_id': '2026-10-16T09:00:02.332330+00:00', 'timestamp': '2026-10-16T09:34:07.700230+00:00', 'status': 'ok', 'collected': 117, 'error_code': None}, {'type': 'tenant', 'source': 'successfactors:sma', 'company': 'SMA', 'run_id': '2026-10-17T09:00:02.925663+00:00', 'timestamp': '2026-10-17T09:32:08.481111+00:00', 'status': 'ok', 'collected': 116, 'error_code': None}]

F_ICIMS_BCG_NEVER = [{'type': 'tenant', 'source': 'icims:bcg', 'company': 'BCG', 'run_id': '2026-10-15T09:00:02.834853+00:00', 'timestamp': '2026-10-15T09:32:44.587995+00:00', 'status': 'empty', 'collected': 0, 'error_code': None}, {'type': 'tenant', 'source': 'icims:bcg', 'company': 'BCG', 'run_id': '2026-10-16T09:00:02.332330+00:00', 'timestamp': '2026-10-16T09:34:07.699218+00:00', 'status': 'empty', 'collected': 0, 'error_code': None}, {'type': 'tenant', 'source': 'icims:bcg', 'company': 'BCG', 'run_id': '2026-10-17T09:00:02.925663+00:00', 'timestamp': '2026-10-17T09:32:08.480059+00:00', 'status': 'empty', 'collected': 0, 'error_code': None}]


# ---------------------------------------------------------------------------
# 0. Sanidade dos fixtures (verbatim de verdade)
# ---------------------------------------------------------------------------

check("0.1 KN csod: 16 registros, todos error/FETCH_ERROR, último run 17/10",
      len(F_KN_CSOD_CHRONIC) == 16
      and all(r["status"] == "error" and r["error_code"] == "FETCH_ERROR"
              for r in F_KN_CSOD_CHRONIC)
      and F_KN_CSOD_CHRONIC[-1]["run_id"].startswith("2026-10-17"))

check("0.2 AkzoNobel: 3 ok (269-272 vagas) + 19 error — transição real 28/09->29/09",
      sum(1 for r in F_AKZO_REG_CHRONIC if r["status"] == "ok") == 3
      and sum(1 for r in F_AKZO_REG_CHRONIC if r["status"] == "error") == 19
      and F_AKZO_REG_CHRONIC[2]["collected"] == 269
      and F_AKZO_REG_CHRONIC[3]["status"] == "error")

check("0.3 Siemens Healthineers: 3 ok com 6 vagas + 3 empty (collected 0)",
      [r["collected"] for r in F_SH_ZERO] == [6, 6, 6, 0, 0, 0]
      and [r["status"] for r in F_SH_ZERO]
      == ["ok", "ok", "ok", "empty", "empty", "empty"])

check("0.4 BCG: 3 ok com 3 vagas + 3 empty; icims:bcg só empty (nunca >0)",
      [r["collected"] for r in F_BCG_ZERO] == [3, 3, 3, 0, 0, 0]
      and all(r["status"] == "empty" for r in F_ICIMS_BCG_NEVER))


def alerts_for(*groups):
    records = [r for g in groups for r in g]
    return build_health_report(records)["alerts"]


def by_type(alerts, type_):
    return [a for a in alerts if a.get("type") == type_]


# ---------------------------------------------------------------------------
# A. Classificação pela regra VIVA do health.py sobre os padrões reais
# ---------------------------------------------------------------------------

kn = alerts_for(F_KN_CSOD_CHRONIC)
rec_kn = by_type(kn, "recurring_error")
check("A1 KN csod (crônica): recurring_error com runs_seq=16 (fixture)",
      len(rec_kn) == 1 and rec_kn[0].get("runs_seq") == 16
      and rec_kn[0].get("source") == "cornerstone:kuehne-nagel")

sma = alerts_for(F_SMA_ORACLE_CHRONIC)
rec_sma = by_type(sma, "recurring_error")
check("A2 SMA oracle (crônica): recurring_error com runs_seq=16 (fixture)",
      len(rec_sma) == 1 and rec_sma[0].get("runs_seq") == 16)

akzo = alerts_for(F_AKZO_REG_CHRONIC)
reg_akzo = by_type(akzo, "regression")
rec_akzo = by_type(akzo, "recurring_error")
check("A3 AkzoNobel (regressão real): regression ok_history=3 + recurring runs_seq=19",
      len(reg_akzo) == 1 and reg_akzo[0].get("ok_history") == 3
      and reg_akzo[0].get("error_code") == "FETCH_ERROR"
      and len(rec_akzo) == 1 and rec_akzo[0].get("runs_seq") == 19)

lidl = alerts_for(F_LIDL_TIMEOUT)
reg_lidl = by_type(lidl, "regression")
rec_lidl = by_type(lidl, "recurring_error")
check("A4 Lidl (timeout curto pós-3 ok): recurring runs_seq=2 + regression ok_history=3 TIMEOUT",
      len(rec_lidl) == 1 and rec_lidl[0].get("runs_seq") == 2
      and len(reg_lidl) == 1 and reg_lidl[0].get("error_code") == "TIMEOUT")

sh = alerts_for(F_SH_ZERO)
zero_sh = by_type(sh, "zero_return")
check("A5 Siemens Healthineers (zerada): zero_return ok_history=3, último ok=6",
      len(zero_sh) == 1 and zero_sh[0].get("ok_history") == 3
      and zero_sh[0].get("last_ok_collected") == 6)

bcg = alerts_for(F_BCG_ZERO)
zero_bcg = by_type(bcg, "zero_return")
check("A6 BCG (zerada): zero_return ok_history=3, último ok=3",
      len(zero_bcg) == 1 and zero_bcg[0].get("ok_history") == 3
      and zero_bcg[0].get("last_ok_collected") == 3)

check("A7 KN phenom (tenant do registry, saudável): NENHUM alerta",
      alerts_for(F_KN_PHENOM_HEALTHY) == [])

check("A8 SMA successfactors (tenant do registry, saudável): NENHUM alerta",
      alerts_for(F_SMA_SF_HEALTHY) == [])

check("A9 icims:bcg (empty-consistente, nunca teve ok>0): NENHUM alerta — o buraco "
      "silencioso POR DESIGN que o relatório F49 documenta",
      alerts_for(F_ICIMS_BCG_NEVER) == [])


# ---------------------------------------------------------------------------
# B. Agregado crônico no digest (renderização viva, build_message)
# ---------------------------------------------------------------------------

SUMMARY_LIVE = {
    "run_id": "2026-10-17T09:00:02.925663+00:00",
    "ok": {"count": 139, "collected": 83394},
    "empty": 12,
    "timeout": [("successfactors:lidlstiftuP2", "Lidl", "TIMEOUT")],
    "error": [
        ("cornerstone:kuehne-nagel", "Kuehne+Nagel", "FETCH_ERROR"),
        ("oracle:fa-exow-saasfaprod1/cx_1", "SMA", "FETCH_ERROR"),
        ("successfactors:careers", "AkzoNobel", "FETCH_ERROR"),
    ],
    "skipped": 0,
    "not_found": 0,
    "source_names": {},
}


def message_for(alerts, summary=None):
    return refresh_daily.build_message(
        summary or SUMMARY_LIVE, alerts, 2, always_notify=True)


combined = (F_LIDL_TIMEOUT + F_KN_CSOD_CHRONIC + F_SMA_ORACLE_CHRONIC
            + F_AKZO_REG_CHRONIC + F_SH_ZERO + F_BCG_ZERO)
alerts_live = build_health_report(combined)["alerts"]
# ING (drop) do run real de 17/10 — alerta NÃO crônico deve renderizar linha própria
alerts_live.append({
    "type": "drop", "source": "workday:ing/icsnldgen", "company": "ING",
    "mediana_anterior": 6, "collected_atual": 1, "pct": 0.167,
})
msg = message_for(alerts_live)
start = msg.find("⚠️ Problemas detectados:")
block = msg[start:] if start >= 0 else ""

check("B1 agregado presente com 3 fontes e contadores reais, ordem por severidade",
      "• 3 fontes em falha crônica (≥15 runs seguidos): AkzoNobel (19 runs), "
      "Kuehne+Nagel (16 runs), SMA (16 runs)" in block)

check("B2 sem linha individual para as crônicas (KN/SMA/AkzoNobel)",
      "Kuehne+Nagel (cornerstone:kuehne-nagel) — erro ao buscar vagas" not in block
      and "SMA (oracle:fa-exow-saasfaprod1/cx_1) — erro ao buscar vagas" not in block
      and "AkzoNobel (successfactors:careers) — erro ao buscar vagas" not in block)

check("B3 Lidl (4 runs < limiar) mantém linha própria com contexto de regressão",
      "Lidl (successfactors:lidlstiftuP2) — sem resposta a tempo (timeout) "
      "· recorrente há 2 runs · antes funcionava (3 runs ok e agora falhou)" in block)

check("B4 zero_return das zeradas renderiza (não é falha crônica de erro)",
      "voltou a zero (empty) após 3 runs com vagas (último ok: 6)" in block
      and "voltou a zero (empty) após 3 runs com vagas (último ok: 3)" in block)

check("B5 drop do ING (alerta fresco) renderiza linha própria",
      "ING (workday:ing/icsnldgen) — queda brusca (collected 1 < 50% da mediana 6 · 0.167)" in block)

check("B6 regression da série crônica é consumida (só o Lidl traz 'antes funcionava')",
      block.count("antes funcionava") == 1)

check("B7 mensagem inteira cabe no teto Telegram (4096) com o agregado",
      len(msg) <= refresh_daily.TELEGRAM_MAX_LEN,
      f"len={len(msg)}")


def msg_boundary(seq):
    alerts = [{"type": "recurring_error", "source": "ats:tenant",
               "company": "Empresa X", "runs_seq": seq}]
    summary = {"run_id": "r", "ok": {"count": 0, "collected": 0}, "empty": 0,
               "timeout": [], "error": [("ats:tenant", "Empresa X", "FETCH_ERROR")],
               "skipped": 0, "not_found": 0, "source_names": {}}
    return message_for(alerts, summary)


m14 = msg_boundary(14)
check("B8 limiar paramétrico: runs_seq=14 (< CHRONIC_FAILURE_RUNS) renderiza linha individual",
      "recorrente há 14 runs" in m14 and "falha crônica" not in m14)

m15 = msg_boundary(15)
check("B9 limiar paramétrico: runs_seq=15 (= limiar) colapsa no agregado singular",
      "• 1 fonte em falha crônica (≥15 runs seguidos): Empresa X (15 runs)" in m15
      and "Empresa X (ats:tenant) — erro ao buscar vagas" not in m15)

alerts_two = [
    {"type": "recurring_error", "source": "ats:a", "company": "Alfa", "runs_seq": 20},
    {"type": "recurring_error", "source": "ats:b", "company": "Beta", "runs_seq": 17},
]
summary_two = {"run_id": "r", "ok": {"count": 0, "collected": 0}, "empty": 0,
               "timeout": [],
               "error": [("ats:a", "Alfa", "FETCH_ERROR"), ("ats:b", "Beta", "FETCH_ERROR")],
               "skipped": 0, "not_found": 0, "source_names": {}}
m2 = message_for(alerts_two, summary_two)
ia, ib = m2.find("Alfa (20 runs)"), m2.find("Beta (17 runs)")
check("B10 2 crônicas => 1 linha agregada, ordenada por runs_seq desc",
      "• 2 fontes em falha crônica (≥15 runs seguidos): Alfa (20 runs), Beta (17 runs)" in m2
      and 0 <= ia < ib)


alerts60 = [{"type": "recurring_error", "source": f"ats:{i}",
             "company": f"Empresa Gigante {i}", "runs_seq": 30}
            for i in range(60)]
summary60 = dict(SUMMARY_LIVE)
summary60["error"] = [("ats:%d" % i, f"Empresa Gigante {i}", "HTTP_500")
                      for i in range(60)]
summary60["timeout"] = []
m60 = message_for(alerts60, summary60)
check("B11 cap de nomes: 60 cronicas => 5 nomes + '+55 outras' "
      "(a linha agregada nao vira muro — provado no test_f61-c)",
      "• 60 fontes em falha crônica (≥15 runs seguidos): Empresa Gigante 0 (30 runs), "
      "Empresa Gigante 1 (30 runs), Empresa Gigante 2 (30 runs), Empresa Gigante 3 (30 runs), "
      "Empresa Gigante 4 (30 runs) +55 outras" in m60
      and "Empresa Gigante 59" not in m60)



# ---------------------------------------------------------------------------
# C. Decisão do dono (4.B, 15/10): MANTER as 6 fontes — registry trava
# ---------------------------------------------------------------------------

def entry(name):
    return next((e for e in SEED if e.name == name), None)


esperado = {
    "Lidl": ("successfactors", "successfactors:lidlstiftuP2"),
    "Siemens Healthineers": ("avature", None),
    "AkzoNobel": ("successfactors", "successfactors:careers"),
    "BCG": ("bamboohr", "bamboohr:bcg"),
    "Kuehne+Nagel": ("phenom", "phenom:nan"),
    "SMA": ("successfactors", "successfactors:sma"),
}
for nome, (ats, tenant) in esperado.items():
    e = entry(nome)
    check(f"C.{nome} presente no registry, habilitada, tenant documentado "
          f"(remoção exige assinatura do dono + atualização deste teste)",
          e is not None and e.enabled and e.ats == ats and e.tenant == tenant,
          f"ats={getattr(e, 'ats', None)} tenant={getattr(e, 'tenant', None)}")


def main() -> int:
    fails = [c for c in CHECKS if not c[1]]
    print(f"F49: {len(CHECKS) - len(fails)} OK, {len(fails)} FAIL")
    for name, _, detail in fails:
        print(f"  FAIL: {name} {detail}")
    print("TUDO OK" if not fails else "HÁ FALHAS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
