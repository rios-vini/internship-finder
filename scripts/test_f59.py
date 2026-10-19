#!/usr/bin/env python3
''''true; V="$(dirname "$0")/../.venv/bin/python"; [ -x "$V" ] || V=python3; exec "$V" -- "$0" "$@" # '''
"""Suite F59 — BCG/BambooHR: quebra de parse upstream + registro local.

Poliglota de 1 linha (bash: ``exec`` re-invoca sob python3; python: string
no-op) — ``bash scripts/test_f59.py`` e ``python scripts/test_f59.py`` rodam
a mesma suíte; o CI usa ``python scripts/$t.py`` (contrato ci.yml).

F59 (19/10): o widget BambooHR (embed2.php) serve JSON PURO desde ~08/10
(probe ao vivo 19/10: HTTP 200, 623 bytes, Accept-agnóstico, as MESMAS 2
vagas Remote de 07/10 dentro de ``departments[].positions[]``); o parser
HTML do pacote upstream (marcador ``bhrPositionID_``) acha 0 vagas =
"empty" silencioso. Quebra de PARSE, não fim das vagas — o conserto é
UPSTREAM: kalil0321/ats-scrapers PR #300 (detecção content-based +
extração de ``departments[].positions[]`` no mesmo formato de saída do
camininho HTML; caminho HTML inalterado byte a byte).

O parser é upstream — aqui NÃO há parser local para testar. Esta suíte
trava SÓ o registro e a documentação (escopos 3-4 da card F59):

1. REGISTRO: entry BCG permanece no SEED verbatim (name/ats/tenant,
   habilitada) — remoção de fonte exige assinatura do dono (decisão
   F49 §2.6: MANTER + conserto proposto).
2. DOCUMENTAÇÃO registry.py: comentário F59 na entry BCG aponta a
   condição (embed2.php JSON) e o PR upstream #300.
3. DOCUMENTAÇÃO health.py: ``_detect_zero_return`` documenta que o
   zero_return de bamboohr:bcg dispara LEGITIMAMENTE até o upstream
   mergear + release (expectativa honesta, não regressão nova).
4. EXPECTATIVA EXECUTÁVEL: sobre a série real VERBATIM (22 ok com vagas
   + 11 empty, 16/09→18/10), zero_return DISPARA com ok_history == 22
   (propriedade do fixture congelado, nunca de data/ vivo); no primeiro
   run pós-fix (variante sintética do último registro com vagas de
   volta) o alerta CESSA sozinho. icims:bcg (secundário
   empty-consistente que nunca coletou) segue SEM alerta por design
   (gate de histórico; buraco documentado na F49 §2.6).
5. SEM FORK LOCAL: nenhum módulo bamboohr em src/internship_finder — o
   scraper continua vindo do pacote upstream ats_scrapers.

ZERO REDE: fixtures verbatim de data/collection_metrics.jsonl (linhas
type:tenant reais, campos mínimos, copiadas sem invenção — extração de
19/10, pós-cron 18/10) + classificação pela regra VIVA do health.py
(``build_health_report``). Nenhum socket; data/ intocado.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from internship_finder.health import (  # noqa: E402
    MIN_OK_HISTORY_FOR_ZERO_RETURN,
    build_health_report,
)
from internship_finder.registry import SEED  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_SRC = (ROOT / "src" / "internship_finder" / "registry.py").read_text(encoding="utf-8")
HEALTH_SRC = (ROOT / "src" / "internship_finder" / "health.py").read_text(encoding="utf-8")

PR_MARKER = "PR #300"
UPSTREAM = "kalil0321/ats-scrapers"

CHECKS: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


# ---------------------------------------------------------------------------
# Fixtures VERBATIM — linhas type:tenant reais de data/collection_metrics.jsonl
# (série COMPLETA bamboohr:bcg 16/09→18/10 + últimos 3 do icims:bcg), campos
# mínimos; valores copiados sem invenção.
# ---------------------------------------------------------------------------
F_BCG_SERIES = [{'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-16T06:00:02.353014+00:00',
  'timestamp': '2026-09-16T06:09:49.827263+00:00',
  'status': 'ok',
  'collected': 2,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-17T06:00:02.026399+00:00',
  'timestamp': '2026-09-17T06:10:12.844671+00:00',
  'status': 'ok',
  'collected': 2,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-18T06:00:02.489171+00:00',
  'timestamp': '2026-09-18T06:10:29.501067+00:00',
  'status': 'ok',
  'collected': 2,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-19T09:00:02.434646+00:00',
  'timestamp': '2026-09-19T09:10:16.764095+00:00',
  'status': 'ok',
  'collected': 2,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-20T09:00:01.806320+00:00',
  'timestamp': '2026-09-20T09:10:11.835450+00:00',
  'status': 'ok',
  'collected': 2,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-21T09:00:01.930062+00:00',
  'timestamp': '2026-09-21T09:10:34.297161+00:00',
  'status': 'ok',
  'collected': 2,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-22T09:00:01.786915+00:00',
  'timestamp': '2026-09-22T09:10:23.361899+00:00',
  'status': 'ok',
  'collected': 2,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-23T09:00:01.826298+00:00',
  'timestamp': '2026-09-23T09:10:22.211933+00:00',
  'status': 'ok',
  'collected': 2,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-24T09:00:02.015274+00:00',
  'timestamp': '2026-09-24T09:10:29.342080+00:00',
  'status': 'ok',
  'collected': 2,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-25T09:00:02.608886+00:00',
  'timestamp': '2026-09-25T09:10:28.528162+00:00',
  'status': 'ok',
  'collected': 4,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-26T09:00:03.156225+00:00',
  'timestamp': '2026-09-26T09:10:05.606394+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-27T09:00:02.262867+00:00',
  'timestamp': '2026-09-27T09:10:04.944789+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-28T09:00:02.381149+00:00',
  'timestamp': '2026-09-28T09:10:43.042989+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-29T09:00:02.445884+00:00',
  'timestamp': '2026-09-29T09:10:39.684336+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-09-30T09:00:02.885501+00:00',
  'timestamp': '2026-09-30T09:10:56.987104+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-01T09:00:02.311411+00:00',
  'timestamp': '2026-10-01T09:10:37.940080+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-02T09:00:02.543142+00:00',
  'timestamp': '2026-10-02T09:10:32.200903+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-03T09:00:02.347210+00:00',
  'timestamp': '2026-10-03T09:23:15.807749+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-04T09:00:02.734639+00:00',
  'timestamp': '2026-10-04T09:24:14.615403+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-05T09:00:02.914436+00:00',
  'timestamp': '2026-10-05T09:23:41.140001+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-06T09:00:02.566746+00:00',
  'timestamp': '2026-10-06T09:23:58.255512+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-07T09:00:02.282516+00:00',
  'timestamp': '2026-10-07T09:24:02.048951+00:00',
  'status': 'ok',
  'collected': 3,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-08T09:00:03.323933+00:00',
  'timestamp': '2026-10-08T09:24:17.396130+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-09T09:00:02.965409+00:00',
  'timestamp': '2026-10-09T09:25:44.736739+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-10T09:00:02.909059+00:00',
  'timestamp': '2026-10-10T09:27:36.243970+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-11T09:00:02.439826+00:00',
  'timestamp': '2026-10-11T09:26:49.358093+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-12T09:00:02.615257+00:00',
  'timestamp': '2026-10-12T09:26:10.272610+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-13T09:00:02.266583+00:00',
  'timestamp': '2026-10-13T09:28:49.460398+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-14T09:00:02.782708+00:00',
  'timestamp': '2026-10-14T09:31:22.629725+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-15T09:00:02.834853+00:00',
  'timestamp': '2026-10-15T09:32:44.587986+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-16T09:00:02.332330+00:00',
  'timestamp': '2026-10-16T09:34:07.699213+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-17T09:00:02.925663+00:00',
  'timestamp': '2026-10-17T09:32:08.480053+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'bamboohr:bcg',
  'company': 'BCG',
  'run_id': '2026-10-18T09:00:02.232332+00:00',
  'timestamp': '2026-10-18T09:30:50.995023+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None}]


F_ICIMS_BCG_SERIES = [{'type': 'tenant',
  'source': 'icims:bcg',
  'company': 'BCG',
  'run_id': '2026-10-16T09:00:02.332330+00:00',
  'timestamp': '2026-10-16T09:34:07.699218+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'icims:bcg',
  'company': 'BCG',
  'run_id': '2026-10-17T09:00:02.925663+00:00',
  'timestamp': '2026-10-17T09:32:08.480059+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None},
 {'type': 'tenant',
  'source': 'icims:bcg',
  'company': 'BCG',
  'run_id': '2026-10-18T09:00:02.232332+00:00',
  'timestamp': '2026-10-18T09:30:50.995028+00:00',
  'status': 'empty',
  'collected': 0,
  'error_code': None}]


def _zero_return(alerts):
    return [
        a
        for a in alerts
        if a.get("type") == "zero_return" and a.get("source") == "bamboohr:bcg"
    ]


# ---------------------------------------------------------------------------
# A. Registro mantido + documentação apontando o PR upstream
# ---------------------------------------------------------------------------

bcg = next((e for e in SEED if e.name == "BCG"), None)
check(
    "A1 entry BCG no SEED verbatim (bamboohr / bamboohr:bcg) e habilitada — "
    "remoção de fonte exige assinatura do dono (decisão F49 §2.6)",
    bcg is not None and bcg.enabled and bcg.ats == "bamboohr"
    and bcg.tenant == "bamboohr:bcg",
    f"ats={getattr(bcg, 'ats', None)} tenant={getattr(bcg, 'tenant', None)}",
)

check(
    "A2 registry.py documenta a condição F59 na entry BCG (embed2.php JSON, "
    f"departments[].positions[], {UPSTREAM} {PR_MARKER}, sem fork local)",
    all(
        m in REGISTRY_SRC
        for m in ("F59", "embed2.php", "departments[].positions[]", UPSTREAM, PR_MARKER)
    ),
)

_zr_start = HEALTH_SRC.index("def _detect_zero_return")
_zr_end = HEALTH_SRC.index("def _detect_regression")
_zr_doc = HEALTH_SRC[_zr_start:_zr_end]
check(
    "A3 health.py (_detect_zero_return) documenta a expectativa honesta: "
    f"alerta legítimo de bamboohr:bcg até o {PR_MARKER} merge + release",
    all(m in _zr_doc for m in ("bamboohr:bcg", PR_MARKER, "LEGITIMAMENTE")),
)

# ---------------------------------------------------------------------------
# B. Expectativa executável: alerta dispara no estado quebrado, cessa pós-fix
# ---------------------------------------------------------------------------

zr_broken = _zero_return(build_health_report(F_BCG_SERIES)["alerts"])
check(
    f"B1 zero_return DISPARA na série real verbatim (22 ok + 11 empty, "
    f"16/09→18/10): ok_history >= {MIN_OK_HISTORY_FOR_ZERO_RETURN} (== 22, "
    "propriedade do fixture congelado) e last_status empty",
    len(zr_broken) == 1
    and zr_broken[0].get("ok_history") == 22
    and zr_broken[0].get("last_status") == "empty",
    f"zr={zr_broken}",
)

# Variante sintética pós-fix: mesma série, o run do dia volta a coletar
# (estado esperado no primeiro cron após o upstream mergear + release).
_fixed = [dict(r) for r in F_BCG_SERIES]
_last = _fixed[-1]
_last["run_id"] = "2026-10-19T09:00:02.000000+00:00"
_last["timestamp"] = "2026-10-19T09:10:00.000000+00:00"
_last["status"] = "ok"
_last["collected"] = 2
zr_fixed = _zero_return(build_health_report(_fixed)["alerts"])
check(
    "B2 pós-fix (variante sintética do último registro com vagas de volta): "
    "zero_return CESSA sozinho — o alerta é o estado quebrado, não ruído",
    zr_fixed == [],
    f"zr={zr_fixed}",
)

zr_icims = [
    a
    for a in build_health_report(F_ICIMS_BCG_SERIES)["alerts"]
    if a.get("type") == "zero_return"
]
check(
    "B3 icims:bcg (secundário empty-consistente, nunca coletou >0) segue "
    "SEM zero_return por design (gate de histórico; buraco documentado "
    "F49 §2.6, não regressão)",
    zr_icims == [],
    f"zr={zr_icims}",
)

# ---------------------------------------------------------------------------
# C. Sem fork local do parser — conserto na camada do defeito (upstream)
# ---------------------------------------------------------------------------

_local_bamboo = sorted(str(p) for p in ROOT.glob("src/internship_finder/**/bamboo*.py"))
_collector_src = (
    ROOT / "src" / "internship_finder" / "collectors" / "ats_scraper.py"
).read_text(encoding="utf-8")
check(
    "C1 NENHUM fork local: 0 módulos bamboohr em src/internship_finder e o "
    "coletador importa o scraper do pacote upstream "
    "(ats_scrapers...get_scraper)",
    not _local_bamboo
    and "from ats_scrapers.scrapers import get_scraper" in _collector_src,
    f"locals={_local_bamboo}",
)

from ats_scrapers.scrapers import BambooHRScraper  # noqa: E402

check(
    "C2 o pacote upstream instalado provê BambooHRScraper (a classe vem do "
    "ats_scrapers; o fix do JSON entra por release do upstream, não por "
    "patch local)",
    BambooHRScraper is not None,
)


def main() -> int:
    fails = [c for c in CHECKS if not c[1]]
    print(f"F59: {len(CHECKS) - len(fails)} OK, {len(fails)} FAIL")
    for name, _, detail in fails:
        print(f"  FAIL: {name} {detail}")
    print("TUDO OK" if not fails else "HÁ FALHAS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
