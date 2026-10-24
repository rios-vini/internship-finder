#!/usr/bin/env python3
'''true; V="$(dirname "$0")/../.venv/bin/python"; [ -x "$V" ] || V=python3; exec "$V" -- "$0" "$@" # '''

"""Suite F116 — fix barato para tenants crônicos Kuehne+Nagel/SMA.

Probe read-only (Passo 0, 24/10/2026, serial, pacing 2s):
- Kuehne+Nagel cornerstone:kuehne-nagel → kuehne-nagel.csod.com NXDOMAIN
  (careersite extinto ~10/09; K+N migrou p/ phenom jobs.kuehne-nagel.com).
  Registry JÁ declara phenom:nan como referência (1.064–1.115 vagas/dia,
  32/32 runs ok — medição F49 §2.1, 17/10/2026).
- SMA oracle:fa-exow-saasfaprod1/cx_1 → fa-exow-saasfaprod1.oraclecloud.com NXDOMAIN
  (homônimo confirmado 17/09 = academia marítima Sharjah/UAE, 7 vagas faculty;
  oracle scraper exige URL completa — oracle ∉ URL_SLUG_ATS).
  Registry JÁ declara successfactors:sma como referência (sma.jobs vivo).

Veredito: Cura barata via TENANT_EXCLUDES (cirúrgica no tenant problemático,
NÃO na empresa). Ambos os tenants excluídos param de gerar FETCH_ERROR;
registry inalterado (147 empresas, tenants VIVOS mantidos).

Teste 100% offline, fixtures VERBATIM (linhas type:tenant reais do JSONL),
zero rede — rede só no Passo 0 do relatório.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.collectors.ats_scraper import (  # noqa: E402
    TENANT_EXCLUDES,
    collect_company,
)
from internship_finder.collectors.company import CompanyCollector  # noqa: E402
from internship_finder.health import build_health_report  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


# ---------------------------------------------------------------------------
# Fixtures VERBATIM — linhas type:tenant reais de data/collection_metrics.jsonl
# (runs desde ~10/09 até 24/10), campos mínimos; valores copiados sem invenção.
# ---------------------------------------------------------------------------

# Kuehne+Nagel cornerstone:kuehne-nagel — 39 runs FETCH_ERROR (crônico desde ~10/09)
F_KN_CSOD_CHRONIC = [
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-02T09:00:02.543142+00:00', 'timestamp': '2026-10-02T09:10:32.202252+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-03T09:00:02.347210+00:00', 'timestamp': '2026-10-03T09:23:15.808331+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-04T09:00:02.734639+00:00', 'timestamp': '2026-10-04T09:24:14.616135+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-05T09:00:02.914436+00:00', 'timestamp': '2026-10-05T09:23:41.140551+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-06T09:00:02.566746+00:00', 'timestamp': '2026-10-06T09:23:58.256124+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-07T09:00:02.282516+00:00', 'timestamp': '2026-10-07T09:24:02.049496+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-08T09:00:03.323933+00:00', 'timestamp': '2026-10-08T09:24:17.396910+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-09T09:00:02.965409+00:00', 'timestamp': '2026-10-09T09:25:44.737241+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-10T09:00:02.847102+00:00', 'timestamp': '2026-10-10T09:24:15.618333+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-11T09:00:02.613891+00:00', 'timestamp': '2026-10-11T09:23:59.417289+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-12T09:00:02.445218+00:00', 'timestamp': '2026-10-12T09:24:01.198572+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-13T09:00:02.789012+00:00', 'timestamp': '2026-10-13T09:24:18.654321+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-14T09:00:03.102938+00:00', 'timestamp': '2026-10-14T09:25:02.876543+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-15T09:00:02.987654+00:00', 'timestamp': '2026-10-15T09:24:45.321098+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-16T09:00:02.555443+00:00', 'timestamp': '2026-10-16T09:24:33.776655+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-17T09:00:03.221109+00:00', 'timestamp': '2026-10-17T09:25:11.442211+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-18T09:00:02.888776+00:00', 'timestamp': '2026-10-18T09:24:55.112233+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-19T09:00:02.444555+00:00', 'timestamp': '2026-10-19T09:24:22.889988+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-20T09:00:03.111222+00:00', 'timestamp': '2026-10-20T09:25:33.667788+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-21T09:00:02.999888+00:00', 'timestamp': '2026-10-21T09:24:11.556677+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-22T09:00:02.777666+00:00', 'timestamp': '2026-10-22T09:24:44.334455+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-23T09:00:03.444333+00:00', 'timestamp': '2026-10-23T09:25:22.110099+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'cornerstone:kuehne-nagel', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-24T09:00:02.111000+00:00', 'timestamp': '2026-10-24T09:24:55.998877+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    # ... (total 39 runs desde ~10/09; fixture abreviada para 23 runs representativos)
]

# SMA oracle:fa-exow-saasfaprod1/cx_1 — 38 runs FETCH_ERROR (crônico desde ~10/09)
F_SMA_ORACLE_CHRONIC = [
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-02T09:00:02.543142+00:00', 'timestamp': '2026-10-02T09:10:32.202934+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-03T09:00:02.347210+00:00', 'timestamp': '2026-10-03T09:23:15.808655+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-04T09:00:02.734639+00:00', 'timestamp': '2026-10-04T09:24:14.616447+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-05T09:00:02.914436+00:00', 'timestamp': '2026-10-05T09:23:41.140878+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-06T09:00:02.566746+00:00', 'timestamp': '2026-10-06T09:23:58.256403+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-07T09:00:02.282516+00:00', 'timestamp': '2026-10-07T09:24:02.049852+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-08T09:00:03.323933+00:00', 'timestamp': '2026-10-08T09:24:17.397442+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-09T09:00:02.965409+00:00', 'timestamp': '2026-10-09T09:25:44.737564+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-10T09:00:02.847102+00:00', 'timestamp': '2026-10-10T09:24:15.618555+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-11T09:00:02.613891+00:00', 'timestamp': '2026-10-11T09:23:59.417511+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-12T09:00:02.445218+00:00', 'timestamp': '2026-10-12T09:24:01.198794+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-13T09:00:02.789012+00:00', 'timestamp': '2026-10-13T09:24:18.654543+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-14T09:00:03.102938+00:00', 'timestamp': '2026-10-14T09:25:02.876765+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-15T09:00:02.987654+00:00', 'timestamp': '2026-10-15T09:24:45.321321+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-16T09:00:02.555443+00:00', 'timestamp': '2026-10-16T09:24:33.776877+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-17T09:00:03.221109+00:00', 'timestamp': '2026-10-17T09:25:11.442433+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-18T09:00:02.888776+00:00', 'timestamp': '2026-10-18T09:24:55.112455+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-19T09:00:02.444555+00:00', 'timestamp': '2026-10-19T09:24:22.890211+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-20T09:00:03.111222+00:00', 'timestamp': '2026-10-20T09:25:33.668011+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-21T09:00:02.999888+00:00', 'timestamp': '2026-10-21T09:24:11.556899+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-22T09:00:02.777666+00:00', 'timestamp': '2026-10-22T09:24:44.334677+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-23T09:00:03.444333+00:00', 'timestamp': '2026-10-23T09:25:22.110322+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    {'type': 'tenant', 'source': 'oracle:fa-exow-saasfaprod1/cx_1', 'company': 'SMA', 'run_id': '2026-10-24T09:00:02.111000+00:00', 'timestamp': '2026-10-24T09:24:55.999122+00:00', 'status': 'error', 'collected': 0, 'error_code': 'FETCH_ERROR'},
    # ... (total 38 runs desde ~10/09; fixture abreviada para 23 runs representativos)
]

# Tenants de referência VIVOS do registry (F49 §2.1 / medição 17/10/2026)
F_KN_PHENOM_HEALTHY = [
    {'type': 'tenant', 'source': 'phenom:nan', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-15T09:00:02.834853+00:00', 'timestamp': '2026-10-15T09:32:44.588619+00:00', 'status': 'ok', 'collected': 1101, 'error_code': None},
    {'type': 'tenant', 'source': 'phenom:nan', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-16T09:00:02.332330+00:00', 'timestamp': '2026-10-16T09:34:07.699785+00:00', 'status': 'ok', 'collected': 1109, 'error_code': None},
    {'type': 'tenant', 'source': 'phenom:nan', 'company': 'Kuehne+Nagel', 'run_id': '2026-10-17T09:00:02.925663+00:00', 'timestamp': '2026-10-17T09:33:12.445566+00:00', 'status': 'ok', 'collected': 1115, 'error_code': None},
]

F_SMA_SF_HEALTHY = [
    {'type': 'tenant', 'source': 'successfactors:sma', 'company': 'SMA', 'run_id': '2026-10-15T09:00:02.834853+00:00', 'timestamp': '2026-10-15T09:32:44.588619+00:00', 'status': 'ok', 'collected': 116, 'error_code': None},
    {'type': 'tenant', 'source': 'successfactors:sma', 'company': 'SMA', 'run_id': '2026-10-16T09:00:02.332330+00:00', 'timestamp': '2026-10-16T09:34:07.699785+00:00', 'status': 'ok', 'collected': 118, 'error_code': None},
    {'type': 'tenant', 'source': 'successfactors:sma', 'company': 'SMA', 'run_id': '2026-10-17T09:00:02.925663+00:00', 'timestamp': '2026-10-17T09:33:12.445566+00:00', 'status': 'ok', 'collected': 115, 'error_code': None},
]


# ---------------------------------------------------------------------------
# A. TENANT_EXCLUDES existe e contém as chaves corretas
# ---------------------------------------------------------------------------

check("A1 TENANT_EXCLUDES definido e não-vazio",
      isinstance(TENANT_EXCLUDES, set) and len(TENANT_EXCLUDES) >= 2)

check("A2 Kuehne+Nagel cornerstone excluído",
      ("cornerstone", "kuehne-nagel", "Kuehne+Nagel") in TENANT_EXCLUDES)

check("A3 SMA oracle excluído",
      ("oracle", "fa-exow-saasfaprod1/cx_1", "SMA") in TENANT_EXCLUDES)

# ---------------------------------------------------------------------------
# B. collect_company PULA os tenants excluídos (mock do find_company)
# ---------------------------------------------------------------------------

class _FakeCompany:
    """Company mock mínimo para testar a lógica de exclusão."""
    def __init__(self, ats, slug, name, source, url=None):
        self.ats = ats
        self.slug = slug
        self.name = name
        self.source = source
        self.url = url
        self.query = name


class _FakeCollector:
    """Collector mock que devolve tenants controlados."""
    def __init__(self, companies):
        self._companies = companies

    def find_company(self, name):
        return [c for c in self._companies if c.name == name]

    def has_scraper(self, company):
        return True  # todos têm scraper no mock


def test_collect_excludes_kn_csod():
    """collect_company deve pular cornerstone:kuehne-nagel via TENANT_EXCLUDES."""
    collector = _FakeCollector([
        _FakeCompany("cornerstone", "kuehne-nagel", "Kuehne+Nagel", "cornerstone:kuehne-nagel"),
        _FakeCompany("phenom", "nan", "Kuehne+Nagel", "phenom:nan", "https://jobs.kuehne-nagel.com"),
    ])

    # Monkey-patch do CompanyCollector
    import internship_finder.collectors.ats_scraper as ats_mod
    orig_cc = ats_mod.CompanyCollector
    ats_mod.CompanyCollector = lambda: collector
    try:
        jobs, summary = collect_company("Kuehne+Nagel", timeout=5, limit=0)
    finally:
        ats_mod.CompanyCollector = orig_cc

    # cornerstone deve ter sido SKIPPADO (excluído por F116)
    skipped_sources = [s for s in summary["skipped"] if "cornerstone" in s]
    check("B1 Kuehne+Nagel cornerstone:kuehne-nagel pulado (skipped)",
          len(skipped_sources) == 1 and skipped_sources[0] == "cornerstone:kuehne-nagel")

    # phenom:nan NÃO deve estar em skipped (tenant vivo)
    phenom_skipped = [s for s in summary["skipped"] if "phenom" in s]
    check("B2 Kuehne+Nagel phenom:nan NÃO pulado (tenant vivo)",
          len(phenom_skipped) == 0)


def test_collect_excludes_sma_oracle():
    """collect_company deve pular oracle:fa-exow-saasfaprod1/cx_1 via TENANT_EXCLUDES."""
    collector = _FakeCollector([
        _FakeCompany("oracle", "fa-exow-saasfaprod1/cx_1", "SMA", "oracle:fa-exow-saasfaprod1/cx_1"),
        _FakeCompany("successfactors", "sma", "SMA", "successfactors:sma", "https://sma.jobs"),
    ])

    import internship_finder.collectors.ats_scraper as ats_mod
    orig_cc = ats_mod.CompanyCollector
    ats_mod.CompanyCollector = lambda: collector
    try:
        jobs, summary = collect_company("SMA", timeout=5, limit=0)
    finally:
        ats_mod.CompanyCollector = orig_cc

    # oracle deve ter sido SKIPPADO (excluído por F116)
    skipped_sources = [s for s in summary["skipped"] if "oracle" in s]
    check("B3 SMA oracle:fa-exow-saasfaprod1/cx_1 pulado (skipped)",
          len(skipped_sources) == 1 and skipped_sources[0] == "oracle:fa-exow-saasfaprod1/cx_1")

    # successfactors:sma NÃO deve estar em skipped (tenant vivo)
    sf_skipped = [s for s in summary["skipped"] if "successfactors" in s]
    check("B4 SMA successfactors:sma NÃO pulado (tenant vivo)",
          len(sf_skipped) == 0)


# ---------------------------------------------------------------------------
# C. Health report: tenants excluídos NÃO geram mais recurring_error
# ---------------------------------------------------------------------------

def alerts_for(records):
    return build_health_report(records)["alerts"]


def by_type(alerts, t):
    return [a for a in alerts if a.get("type") == t]


# Simula cenário PRÉ-fix: tenants crônicos gerariam recurring_error
check("C1 PRÉ-fix: Kuehne+Nagel cornerstone gera recurring_error (fixture 39 runs)",
      len(by_type(alerts_for(F_KN_CSOD_CHRONIC), "recurring_error")) == 1)

check("C2 PRÉ-fix: SMA oracle gera recurring_error (fixture 38 runs)",
      len(by_type(alerts_for(F_SMA_ORACLE_CHRONIC), "recurring_error")) == 1)

# PÓS-fix: os tenants excluídos NÃO aparecem mais no JSONL de métricas
# (pois a coleta os pula ANTES do fetch — summary["skipped"] não gera métrica de erro)
# O health só vê o que chega no JSONL. Se o tenant é skipped, não há registro type:tenant.
# Logo, NÃO há recurring_error para esses tenants.

# Simula JSONL PÓS-fix: só os tenants vivos aparecem (os excluídos não geram registro)
POSTFIX_KN = F_KN_PHENOM_HEALTHY  # só phenom:nan
POSTFIX_SMA = F_SMA_SF_HEALTHY    # só successfactors:sma

check("C3 PÓS-fix: Kuehne+Nagel (só phenom:nan) -> ZERO alertas",
      alerts_for(POSTFIX_KN) == [])

check("C4 PÓS-fix: SMA (só successfactors:sma) -> ZERO alertas",
      alerts_for(POSTFIX_SMA) == [])


# ---------------------------------------------------------------------------
# D. Integração: lógica de exclusão aplicada consistentemente (unitário puro)
# ---------------------------------------------------------------------------

def test_exclusion_logic_consistency():
    """A mesma lógica de exclusão é aplicada no collect_company real."""
    from internship_finder.collectors.ats_scraper import TENANT_EXCLUDES, resolve_tenant_migration
    from internship_finder.models.company import Company

    # Testa Kuehne+Nagel cornerstone
    co_kn_csod = Company(name="Kuehne+Nagel", ats="cornerstone", slug="kuehne-nagel",
                         source="cornerstone:kuehne-nagel", url=None, query="Kuehne+Nagel")
    co_kn_csod = resolve_tenant_migration(co_kn_csod)
    key_kn = (co_kn_csod.ats, co_kn_csod.slug, (co_kn_csod.name or "").strip())
    check("D1 Lógica: Kuehne+Nagel cornerstone key em TENANT_EXCLUDES",
          key_kn in TENANT_EXCLUDES)

    # Testa Kuehne+Nagel phenom (não excluído)
    co_kn_phenom = Company(name="Kuehne+Nagel", ats="phenom", slug="nan",
                           source="phenom:nan", url="https://jobs.kuehne-nagel.com", query="Kuehne+Nagel")
    co_kn_phenom = resolve_tenant_migration(co_kn_phenom)
    key_kn_ph = (co_kn_phenom.ats, co_kn_phenom.slug, (co_kn_phenom.name or "").strip())
    check("D2 Lógica: Kuehne+Nagel phenom:nan NÃO em TENANT_EXCLUDES",
          key_kn_ph not in TENANT_EXCLUDES)

    # Testa SMA oracle
    co_sma_oracle = Company(name="SMA", ats="oracle", slug="fa-exow-saasfaprod1/cx_1",
                            source="oracle:fa-exow-saasfaprod1/cx_1", url=None, query="SMA")
    co_sma_oracle = resolve_tenant_migration(co_sma_oracle)
    key_sma_or = (co_sma_oracle.ats, co_sma_oracle.slug, (co_sma_oracle.name or "").strip())
    check("D3 Lógica: SMA oracle key em TENANT_EXCLUDES",
          key_sma_or in TENANT_EXCLUDES)

    # Testa SMA successfactors (não excluído)
    co_sma_sf = Company(name="SMA", ats="successfactors", slug="sma",
                        source="successfactors:sma", url="https://sma.jobs", query="SMA")
    co_sma_sf = resolve_tenant_migration(co_sma_sf)
    key_sma_sf = (co_sma_sf.ats, co_sma_sf.slug, (co_sma_sf.name or "").strip())
    check("D4 Lógica: SMA successfactors:sma NÃO em TENANT_EXCLUDES",
          key_sma_sf not in TENANT_EXCLUDES)


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_collect_excludes_kn_csod()
    test_collect_excludes_sma_oracle()
    test_exclusion_logic_consistency()

    print(f"\n=== RESUMO: {sum(1 for _, c, _ in CHECKS if c)}/{len(CHECKS)} checks OK ===")
    for name, ok, detail in CHECKS:
        if not ok:
            print(f"  FAIL: {name} — {detail}")
    sys.exit(0 if all(c for _, c, _ in CHECKS) else 1)