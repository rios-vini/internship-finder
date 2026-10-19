#!/usr/bin/env python3
''''true; V="$(dirname "$0")/../.venv/bin/python"; [ -x "$V" ] || V=python3; exec "$V" -- "$0" "$@" # '''
"""Suite F58 — Siemens Healthineers: re-point registry Avature→Phenom.

Poliglota de 1 linha (bash: ``exec`` re-invoca sob python3; python: string
no-op) — ``bash scripts/test_f58.py`` e ``python scripts/test_f58.py`` rodam
a mesma suíte; o CI usa ``python scripts/$t.py`` (contrato ci.yml).

Contexto (F49 §2.5): a URL avature da Siemens responde 302 →
careers.siemens-healthineers.com/global/en (plataforma PHENOM); o scraper
avature parseia 0 vagas = "empty" silencioso por 19+ runs. F58 = re-point
validado com fetch real:

1. **Endpoint validado AO VIVO (18/10)** com o caminho EXATO do pipeline:
   ``get_scraper("phenom", "https://careers.siemens-healthineers.com")``
   com os defaults do scraper (locale en_us / country us — o pipeline NUNCA
   passa kwargs) → **823 vagas em ~3s** (POST /widgets, ddoKey refineSearch;
   csrf seed em /us/en/search-results). 111 vagas com Germany na location;
   **40 passam o filtro REAL ``is_student_role`` AND Germany** (Werkstudent/
   Praktikum/Working Student/Internship/Masterarbeit — Erlangen, Forchheim,
   Kemnath, Rudolstadt). Manifest upstream verificado ao vivo 18/10:
   ``find_company("Siemens Healthineers")`` ainda resolve SÓ a linha
   avature (phenom inexistente no inventário) → a coleta usa o override de
   migração ``TENANT_ATS_OVERRIDES``.

2. **Re-point do registry**: ``ats="avature"`` (tenant None) →
   ``ats="phenom", tenant="phenom:https://careers.siemens-healthineers.com"``
   (URL como slug — mesmo padrão EBM-Papst cornerstone; Company.source =
   ``ats:slug``). A assinatura que o check C do test_f49 exigia é a própria
   card F58 (escopo 2, veredito do dono via onda).

3. **Gate de série aposentada no health (SERIES_STALE_HOURS=36)**: série
   que parou de receber registros (migração/remoção upstream) com último
   estado ``empty`` dispararia zero_return PARA SEMPRE; agora ela é
   aposentada e silencia, com o histórico PRESERVADO no resumo por série.
   Cessação esperada: no 2º cron pós-merge (no 1º o gap ~23,5h < 36h e o
   alerta dispara uma última vez — honesto com a transição).

ZERO REDE nesta suíte: fixtures VERBATIM do fetch validado
(``fixtures/f58_phenom_widgets_first_page.json`` = 1ª página inteira do
POST /widgets com defaults, 100 itens, refineSearch.totalHits=824;
``fixtures/f58_phenom_jobs_de_sample.json`` = 3 jobs DE do mesmo fetch,
2 student + 1 controle negativo) + série de métricas verbatim da avature
(45 registros, 31/08→18/10). Nenhum socket.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ats_scrapers.scrapers.phenom import PhenomScraper  # noqa: E402
from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.collectors import ats_scraper as ats_mod  # noqa: E402
from internship_finder.collectors.ats_scraper import (  # noqa: E402
    TENANT_ATS_OVERRIDES,
    TENANT_URL_OVERRIDES,
    resolve_tenant_migration,
    scraper_slug,
)
from internship_finder.collectors.company import CompanyCollector  # noqa: E402
from internship_finder.filters import infer_country_iso, is_student_role  # noqa: E402
from internship_finder.health import (  # noqa: E402
    SERIES_STALE_HOURS,
    build_health_report,
)
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.registry import SEED  # noqa: E402
from internship_finder.cli import _tenant_record  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX_PAGE = ROOT / "fixtures" / "f58_phenom_widgets_first_page.json"
FIX_DE = ROOT / "fixtures" / "f58_phenom_jobs_de_sample.json"

SH_BASE = "https://careers.siemens-healthineers.com"
SH_TENANT = "phenom:" + SH_BASE
AVATURE_URL = "https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs"
AVATURE_SOURCE = "avature:" + AVATURE_URL

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, cond, detail: str = "") -> bool:
    ok = bool(cond)
    CHECKS.append((name, ok, str(detail)))
    print(f"[{'OK' if ok else 'FAIL'}] {name}"
          + (f" — {detail}" if detail and not ok else ""))
    return ok


# ---------------------------------------------------------------------------
# 0. Sanidade dos fixtures (verbatim do fetch validado 18/10)
# ---------------------------------------------------------------------------

payload = json.loads(FIX_PAGE.read_text(encoding="utf-8"))
rs = payload.get("refineSearch", {})
page_jobs = rs.get("data", {}).get("jobs", [])

check("0.1 fixture 1ª página: refineSearch.data.jobs com 100 itens verbatim",
      len(page_jobs) == 100,
      f"n={len(page_jobs)}")
check("0.2 fixture 1ª página: refineSearch.totalHits == 824",
      rs.get("totalHits") == 824, f"totalHits={rs.get('totalHits')}")

de_jobs = json.loads(FIX_DE.read_text(encoding="utf-8"))
check("0.3 fixture jobs DE: 3 itens do mesmo fetch (2 student + 1 controle)",
      len(de_jobs) == 3
      and {j["ats_id"] for j in de_jobs} == {"P-100630", "P-100420", "P-100734"})


# ---------------------------------------------------------------------------
# A. Parser phenom sobre o fixture verbatim (caminho do pipeline)
# ---------------------------------------------------------------------------

s = PhenomScraper(SH_BASE, timeout=30, include_descriptions=False)
items = s._extract_jobs(payload)
check("A1 _extract_jobs lê refineSearch.data.jobs (100)",
      len(items) == 100, f"n={len(items)}")
check("A2 _extract_total lê refineSearch.totalHits (824)",
      s._extract_total(payload) == 824)
first = s._parse_job(items[0])
check("A3 _parse_job: ats_id R-29591 e company = host (identidade P1.1)",
      first.ats_id == "R-29591"
      and first.company == "careers.siemens-healthineers.com",
      f"ats_id={first.ats_id} company={first.company}")
check("A4 título preserva \\xa0 verbatim (sem normalização silenciosa)",
      "\xa0" in first.title and first.title.startswith("Senior"),
      repr(first.title)[:60])
check("A5 location composta city, state, country",
      first.location == "Newton, Massachusetts, United States of America",
      first.location)
check("A6 URL da vaga composta base+/job/+jobId (item sem jobUrl — honesto)",
      str(first.url) == SH_BASE + "/job/R-29591", str(first.url))
parsed = [s._parse_job(i) for i in items]
check("A7 100/100 parseiam com ats_id único",
      len(parsed) == 100 and len({j.ats_id for j in parsed}) == 100)
check("A8 employment_type None preservado (jobType ausente no item; campo "
      "do tenant é 'type', fora do contrato do scraper — sem invenção)",
      all(j.employment_type is None for j in parsed))


# ---------------------------------------------------------------------------
# B. Contrato do registry re-apontado
# ---------------------------------------------------------------------------

sh_entry = next((e for e in SEED if e.name == "Siemens Healthineers"), None)
check("B1 registry: Siemens Healthineers ats=phenom, tenant=URL validada",
      sh_entry is not None and sh_entry.ats == "phenom"
      and sh_entry.tenant == SH_TENANT,
      f"ats={getattr(sh_entry, 'ats', None)} tenant={getattr(sh_entry, 'tenant', None)}")
check("B2 registry: nome canônico de coleta e enabled intactos",
      sh_entry is not None and sh_entry.enabled and sh_entry.name == "Siemens Healthineers")
check("B3 registry: nenhuma entrada declara avature para Siemens "
      "(a série avature sai do registry)",
      not any(e.ats == "avature" and "siemens" in e.name.casefold()
              for e in SEED))
check("B4 mapa de migração: exatamente a chave Siemens (ats, slug-URL, nome)",
      set(TENANT_ATS_OVERRIDES)
      == {("avature", AVATURE_URL, "Siemens Healthineers")},
      str(set(TENANT_ATS_OVERRIDES)))


# ---------------------------------------------------------------------------
# C. resolve_tenant_migration (override de migração)
# ---------------------------------------------------------------------------

av = Company(name="Siemens Healthineers", ats="avature", slug=AVATURE_URL,
             url=AVATURE_URL, query="Siemens Healthineers", match_kind="exact")
new = resolve_tenant_migration(av)
check("C1 reescrita: ats=phenom, slug=url=URL de careers",
      new.ats == "phenom" and new.slug == SH_BASE and new.url == SH_BASE)
check("C2 source nova == tenant declarado no registry (consistência verde)",
      new.source == SH_TENANT, new.source)
check("C3 scraper_slug(reescrita) devolve a URL (URL_SLUG_ATS)",
      scraper_slug(new) == SH_BASE, scraper_slug(new))
check("C4 função pura: Company original intacta (avature segue avature)",
      av.ats == "avature" and av.source == AVATURE_SOURCE)
check("C5 has_scraper(reescrita) — phenom tem scraper no pacote",
      CompanyCollector().has_scraper(new))
other = Company(name="DHL", ats="phenom", slug="nan",
                url="https://careers.dhl.com")
check("C6 não-migrada devolve ipsis literis (inventário puro)",
      resolve_tenant_migration(other).model_dump() == other.model_dump())
wrong_name = av.model_copy(update={"name": "Siemens AG"})
check("C7 chave estrita: nome diferente NÃO reescreve",
      resolve_tenant_migration(wrong_name).ats == "avature")
check("C8 override de URL da Fase I (SAP) intacto ao lado do novo mapa",
      TENANT_URL_OVERRIDES
      == {("successfactors", "jobs", "SAP"): "https://careers.sap.com"})


# ---------------------------------------------------------------------------
# D. Wiring: collect_company reescreve ANTES do scraper (offline, stubs)
# ---------------------------------------------------------------------------

_adapter = AtsJobAdapter()
_probe_job = _adapter.to_job(dict(de_jobs[0]), new)
_probe_dict = _probe_job.to_dict()

_captured: dict = {}


def _stub_find(self, name, **kwargs):  # noqa: ANN001
    return [av]


def _stub_fetch(company, timeout, include_descriptions, margin=25.0):  # noqa: ANN001
    _captured["company"] = company
    return [_probe_dict]


_orig_find = CompanyCollector.find_company
_orig_fetch = ats_mod.fetch_with_timeout
try:
    CompanyCollector.find_company = _stub_find
    ats_mod.fetch_with_timeout = _stub_fetch
    jobs, summary = ats_mod.collect_company("Siemens Healthineers", timeout=5)
finally:
    CompanyCollector.find_company = _orig_find
    ats_mod.fetch_with_timeout = _orig_fetch

check("D1 coleta: o fetch recebe a Company REESCRITA (source phenom)",
      _captured.get("company", Company(name="x", ats="y", slug="z")).source
      == SH_TENANT,
      str(getattr(_captured.get("company"), "source", None)))
check("D2 summary ok registra a source nova (metrics: série phenom nasce)",
      summary["ok"] and summary["ok"][0][0] == SH_TENANT,
      str(summary["ok"]))
check("D3 Job.id usa a identidade nova: company|source:ats_id",
      jobs and jobs[0].id.startswith("careers.siemens-healthineers.com|"
                                      + SH_TENANT + ":"),
      jobs[0].id if jobs else "sem jobs")
check("D4 summary companies = host dos jobs (P1.1, padrão phenom DHL/Roche)",
      summary["companies"].get(SH_TENANT) == "careers.siemens-healthineers.com",
      str(summary["companies"]))


# ---------------------------------------------------------------------------
# E. Funil com os jobs DE verbatim: as vagas Siemens VOLTAM ao eligible
# ---------------------------------------------------------------------------

werk1, controle, werk2 = (de_jobs[0], de_jobs[1], de_jobs[2])
check("E1 is_student_role nos 2 Werkstudent DE verbatim (positivos)",
      is_student_role(werk1["title"], werk1.get("description"),
                      werk1.get("employment_type"))
      and is_student_role(werk2["title"], werk2.get("description"),
                          werk2.get("employment_type")))
check("E2 controle negativo: 'Internal Control Practitioner' NÃO é student "
      "(substring 'intern' não engana o filtro real)",
      not is_student_role(controle["title"], controle.get("description"),
                          controle.get("employment_type")))
check("E3 infer_country_iso devolve DE para as locations DE verbatim",
      infer_country_iso(location=werk1["location"], country_iso=None) == "de"
      and infer_country_iso(location=werk2["location"], country_iso=None) == "de")
adapted = _adapter.to_job(dict(werk1), new)
check("E4 adaptado: country_iso DE, source phenom, id pela tripla P1.1",
      adapted.country_iso == "de" and adapted.source == SH_TENANT
      and adapted.id == "careers.siemens-healthineers.com|" + SH_TENANT + ":P-100630",
      f"iso={adapted.country_iso} id={adapted.id}")


# ---------------------------------------------------------------------------
# F. Health: gate de série aposentada + histórico de métricas preservado
# ---------------------------------------------------------------------------

# Série VERBATIM da avature em produção (45 registros, 31/08→18/10):
# 15 ok (6/dia) + 3 error SSL (19–21/09) + 7 ok + 20 empty (29/09→18/10).
SERIE_AVATURE = [
    ("2026-08-31T22:29:23.397109+00:00", "ok", 6),
    ("2026-09-05T20:43:07.735642+00:00", "ok", 6),
    ("2026-09-06T06:00:02.424754+00:00", "ok", 6),
    ("2026-09-07T06:00:02.044107+00:00", "ok", 6),
    ("2026-09-08T06:00:02.273517+00:00", "ok", 6),
    ("2026-09-09T06:00:02.337761+00:00", "ok", 6),
    ("2026-09-10T06:00:02.498550+00:00", "ok", 6),
    ("2026-09-11T06:00:01.821416+00:00", "ok", 6),
    ("2026-09-12T06:00:02.533541+00:00", "ok", 6),
    ("2026-09-13T06:00:01.773121+00:00", "ok", 6),
    ("2026-09-14T06:00:01.983958+00:00", "ok", 6),
    ("2026-09-15T06:00:01.975323+00:00", "ok", 6),
    ("2026-09-16T06:00:02.353014+00:00", "ok", 6),
    ("2026-09-17T06:00:02.026399+00:00", "ok", 6),
    ("2026-09-18T06:00:02.489171+00:00", "ok", 6),
    ("2026-09-19T09:00:02.434646+00:00", "error", 0),
    ("2026-09-20T09:00:01.806320+00:00", "error", 0),
    ("2026-09-21T09:00:01.930062+00:00", "error", 0),
    ("2026-09-22T09:00:01.786915+00:00", "ok", 6),
    ("2026-09-23T09:00:01.826298+00:00", "ok", 6),
    ("2026-09-24T09:00:02.015274+00:00", "ok", 6),
    ("2026-09-25T09:00:02.608886+00:00", "ok", 6),
    ("2026-09-26T09:00:03.156225+00:00", "ok", 6),
    ("2026-09-27T09:00:02.262867+00:00", "ok", 6),
    ("2026-09-28T09:00:02.381149+00:00", "ok", 6),
    ("2026-09-29T09:00:02.445884+00:00", "empty", 0),
    ("2026-09-30T09:00:02.885501+00:00", "empty", 0),
    ("2026-10-01T09:00:02.311411+00:00", "empty", 0),
    ("2026-10-02T09:00:02.543142+00:00", "empty", 0),
    ("2026-10-03T09:00:02.347210+00:00", "empty", 0),
    ("2026-10-04T09:00:02.734639+00:00", "empty", 0),
    ("2026-10-05T09:00:02.914436+00:00", "empty", 0),
    ("2026-10-06T09:00:02.566746+00:00", "empty", 0),
    ("2026-10-07T09:00:02.282516+00:00", "empty", 0),
    ("2026-10-08T09:00:03.323933+00:00", "empty", 0),
    ("2026-10-09T09:00:02.965409+00:00", "empty", 0),
    ("2026-10-10T09:00:02.909059+00:00", "empty", 0),
    ("2026-10-11T09:00:02.439826+00:00", "empty", 0),
    ("2026-10-12T09:00:02.615257+00:00", "empty", 0),
    ("2026-10-13T09:00:02.266583+00:00", "empty", 0),
    ("2026-10-14T09:00:02.782708+00:00", "empty", 0),
    ("2026-10-15T09:00:02.834853+00:00", "empty", 0),
    ("2026-10-16T09:00:02.332330+00:00", "empty", 0),
    ("2026-10-17T09:00:02.925663+00:00", "empty", 0),
    ("2026-10-18T09:00:02.232332+00:00", "empty", 0),
]


def _tenant(run_id, source, company, status, collected, error_code=None):
    return {"type": "tenant", "run_id": run_id, "timestamp": run_id,
            "source": source, "company": company, "status": status,
            "collected": collected, "error_code": error_code}


serie_av = [_tenant(rid, AVATURE_SOURCE, "Siemens Healthineers", st, col)
            for rid, st, col in SERIE_AVATURE]

# F1: série fresca (sozinha, último registro = mais recente do relatório)
# → zero_return dispara normal: o gate não supra-alimenta.
rep_hoje = build_health_report(list(serie_av))
zr = [a for a in rep_hoje["alerts"] if a["type"] == "zero_return"]
check("F1 série fresca: zero_return dispara com ok_history=22, último ok=6",
      len(zr) == 1 and zr[0].get("ok_history") == 22
      and zr[0].get("last_ok_collected") == 6,
      str(zr))

# F2/F3: pós-migração — cron grava a série phenom, a avature para de
# receber registros; no 2º cron o gap passa de 36h e ela aposenta.
PH_OK = [("2026-10-19T09:00:02.100000+00:00", 823),
         ("2026-10-20T09:00:02.200000+00:00", 831)]
sim = list(serie_av) + [
    _tenant(rid, SH_TENANT, "Siemens Healthineers", "ok", col)
    for rid, col in PH_OK]
rep_pos = build_health_report(sim)
zr_pos = [a for a in rep_pos["alerts"]
          if a["type"] == "zero_return" and a["source"] == AVATURE_SOURCE]
check("F2 pós-migração (+2 dias sem registros avature): zero_return CESSA "
      "(série aposentada pelo gate)",
      not zr_pos, str(zr_pos))
src_map = {s["source"]: s for s in rep_pos["sources"]}
av_summary = src_map.get(AVATURE_SOURCE)
check("F3 histórico de métricas PRESERVADO: série avature segue no resumo "
      "(45 runs, último empty) — só os alertas silenciam",
      av_summary is not None and av_summary["total_runs"] == 45
      and av_summary["last_status"] == "empty",
      str(av_summary))
ph_summary = src_map.get(SH_TENANT)
check("F4 série nova nasce no resumo: phenom ok, 831, sem alertas",
      ph_summary is not None and ph_summary["last_status"] == "ok"
      and ph_summary["last_collected"] == 831
      and not any(a["source"] == SH_TENANT for a in rep_pos["alerts"]),
      str(ph_summary))

# F5: limiar — no 1º cron pós-migração o gap é ~24h (< 36h): o alerta
# dispara uma última vez (honesto com a transição); só depois de 36h cessa.
gap24 = list(serie_av) + [
    _tenant("2026-10-19T09:00:02.100000+00:00", SH_TENANT,
            "Siemens Healthineers", "ok", 823)]
rep24 = build_health_report(gap24)
check("F5 limiar: 1º cron pós-migração (gap 24h < SERIES_STALE_HOURS) → "
      "zero_return AINDA dispara (transição honesta)",
      any(a["type"] == "zero_return" for a in rep24["alerts"]))
gap37 = list(serie_av) + [
    _tenant("2026-10-19T09:00:02.100000+00:00", AVATURE_SOURCE,
            "Siemens Healthineers", "empty", 0),
    _tenant("2026-10-20T22:00:02.100000+00:00", SH_TENANT,
            "Siemens Healthineers", "ok", 823)]
rep37 = build_health_report(gap37)
check("F6 limiar: gap 37h (> SERIES_STALE_HOURS=36) → zero_return cessa",
      not any(a["type"] == "zero_return" and a["source"] == AVATURE_SOURCE
              for a in rep37["alerts"]),
      f"SERIES_STALE_HOURS={SERIES_STALE_HOURS}")

# F7: fail-open — registro com run_id não-ISO no fim da série nunca é
# aposentado por erro de parsing (o alerta segue visível).
bad_date = [_tenant("2026-09-01T09:00:00+00:00", AVATURE_SOURCE,
                    "Siemens Healthineers", "ok", 6),
            _tenant("2026-09-02T09:00:00+00:00", AVATURE_SOURCE,
                    "Siemens Healthineers", "ok", 6),
            _tenant("2026-09-03T09:00:00+00:00", AVATURE_SOURCE,
                    "Siemens Healthineers", "ok", 6),
            _tenant("data-invalida", AVATURE_SOURCE,
                    "Siemens Healthineers", "empty", 0),
            _tenant("2026-09-10T09:00:00+00:00", "other:src", "Outra", "ok", 9)]
rep_bad = build_health_report(bad_date)
check("F7 fail-open: run_id não-ISO → série segue elegível a alertas",
      any(a["type"] == "zero_return" and a["source"] == AVATURE_SOURCE
          for a in rep_bad["alerts"]))

# F8: registro de métricas da série nova — mesmo shape do JSONL (contadores
# intactos; a mudança de universo é aditiva: nova série, mesmo contrato).
rec = _tenant_record("2026-10-19T09:00:02.100000+00:00",
                     "Siemens Healthineers", SH_TENANT, "ok", 823, "3.0s")
check("F8 _tenant_record da série phenom: type/company/ats/collected shape "
      "do JSONL (company = nome do registry, ats = prefixo da source)",
      rec["type"] == "tenant" and rec["company"] == "Siemens Healthineers"
      and rec["ats"] == "phenom" and rec["status"] == "ok"
      and rec["collected"] == 823 and rec["duration"] == 3.0
      and rec["error"] is None and rec["error_code"] is None,
      str(rec))


def main() -> int:
    fails = [c for c in CHECKS if not c[1]]
    print(f"\nF58: {len(CHECKS) - len(fails)} OK, {len(fails)} FAIL")
    for name, _, detail in fails:
        print(f"  FAIL: {name} {detail}")
    print("TUDO OK" if not fails else "HÁ FALHAS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
