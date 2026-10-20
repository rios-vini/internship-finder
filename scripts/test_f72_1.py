"""Testes F72.1 — correção AkzoNobel: SuccessFactors -> Phenom (F58 gemelo).

Achado da auditoria viva F72 (20/10/2026): ``careers.akzonobel.com/sitemal.xml``
responde HTTP 500 persistente (feed legacy SuccessFactors morto desde
~29/09/2026) enquanto o portal vive na plataforma **Phenom** (raiz 303 ->
``/gb/en`` HTTP 200, assinatura ``data-ph-id``). Série do JSONL de métricas:
28 runs ``ok`` (~270 vagas/dia, 08–28/09) -> 22 runs ``FETCH_ERROR
collected=0`` (29/09–20/10) — coleta cega com a empresa viva, o MESMO
padrão F58 (Siemens Healthineers: Avature -> Phenom).

Correção (este PR): override de migração em ``TENANT_ATS_OVERRIDES`` +
re-point do registry para ``phenom:https://careers.akzonobel.com``. Esta
suíte trava a correção, 100% OFFLINE (zero rede):

0. **Sanidade dos fixtures** — VERBATIM do fetch validado ao vivo 20/10
   (``f72_akzo_widgets_first_page.json`` = 1ª página inteira do POST
   /widgets com defaults, 100 itens, refineSearch.totalHits=225;
   ``f72_akzo_jobs_sample.json`` = 3 items do mesmo fetch: 2 student +
   1 controle);
1. **Parser phenom sobre o fixture AkzoNobel** (caminho do pipeline):
   _extract_jobs/_extract_total + _parse_job (identidade
   company == careers.akzonobel.com, jobId -> ats_id, URL base+/job/+id,
   location "Köln, DEU" preservada — o board AkzoNobel usa ``jobId``,
   campo distinto do board Siemens ``ats_id`` do f58);
2. **Contrato do registry re-apontado** — AkzoNobel ats=phenom,
   tenant=phenom:https://careers.akzonobel.com (forma F71: phenom = token
   OU URL https completa; tenant NÃO compartilhado — URL é por empresa);
   a entrada successfactors:careers MORREU (re-point total, sem linha
   morta);
3. **Override de migração** — ``resolve_tenant_migration`` reescreve a
   Company resolvida (successfactors, careers.akzonobel.com, AkzoNobel)
   para (phenom, URL) com url=URL; o override F58 do Siemens Healthineers
   PERMANECE (regressão); empresa fora do mapa inalterada (inércia);
   ``scraper_slug`` devolve a URL (phenom ∈ URL_SLUG_ATS);
4. **Consistência** — tenant novo declarado == resolvido -> ``consistent``
   (o desfecho de coleta pós-correção); a linha antiga declarada contra
   resoluções novas seria ``drift`` (a direção que a correção evita).

Uso: .venv/bin/python scripts/test_f72_1.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent / "src"))

from ats_scrapers.scrapers.phenom import PhenomScraper  # noqa: E402
from internship_finder.collectors.ats_scraper import (  # noqa: E402
    TENANT_ATS_OVERRIDES,
    resolve_tenant_migration,
    scraper_slug,
)
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.registry import SEED, tenant_consistency_status  # noqa: E402

ROOT = SCRIPTS.parent
FIX_PAGE = ROOT / "fixtures" / "f72_akzo_widgets_first_page.json"
FIX_SAMPLE = ROOT / "fixtures" / "f72_akzo_jobs_sample.json"

AKZO_URL = "https://careers.akzonobel.com"
AKZO_TENANT = "phenom:" + AKZO_URL

FAILURES: list[str] = []
N = 0


def check(name: str, cond, detail: str = "") -> None:
    global N
    N += 1
    ok = bool(cond)
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("F72.1 — AkzoNobel SuccessFactors->Phenom (offline, fixtures verbatim 20/10)")

    # --- 0. Sanidade dos fixtures (verbatim do fetch validado) ---
    print("0. sanidade dos fixtures")
    payload = json.loads(FIX_PAGE.read_text(encoding="utf-8"))
    rs = payload.get("refineSearch", {})
    page_jobs = rs.get("data", {}).get("jobs", [])
    check("0.1 1ª página: refineSearch.data.jobs com 100 itens verbatim",
          len(page_jobs) == 100, f"n={len(page_jobs)}")
    check("0.2 1ª página: refineSearch.totalHits == 225 (medição ao vivo 20/10)",
          rs.get("totalHits") == 225, f"totalHits={rs.get('totalHits')}")
    sample = json.loads(FIX_SAMPLE.read_text(encoding="utf-8"))
    check("0.3 sample: 3 items do mesmo fetch (2 student + 1 controle)",
          len(sample) == 3
          and {str(j.get("jobId")) for j in sample} == {"28874", "52686", "56026"})

    # --- 1. Parser phenom sobre o fixture AkzoNobel (caminho do pipeline) ---
    print("1. parser phenom sobre o board AkzoNobel (fixtures verbatim)")
    s = PhenomScraper(AKZO_URL, timeout=30, include_descriptions=False)
    items = s._extract_jobs(payload)
    check("1a _extract_jobs lê refineSearch.data.jobs (100)",
          len(items) == 100, f"n={len(items)}")
    check("1b _extract_total lê refineSearch.totalHits (225)",
          s._extract_total(payload) == 225)
    parsed = [s._parse_job(i) for i in sample]
    check("1c 3/3 items da sample parseiam (jobId presente em todos)",
          all(p is not None for p in parsed))
    student_de = parsed[0]
    check("1d student DE: ats_id=jobId 28874, title 'Praktikum / "
          "Studententätigkeit', loc 'Köln, DEU'",
          student_de.ats_id == "28874"
          and student_de.title.startswith("Praktikum")
          and student_de.location == "Köln, DEU",
          f"ats_id={student_de.ats_id} title={student_de.title!r} "
          f"loc={student_de.location!r}")
    all_ids = {p.company for p in parsed}
    check("1e identidade P1.1: company == careers.akzonobel.com (host) em TODOS",
          all_ids == {"careers.akzonobel.com"}, f"companies={sorted(all_ids)}")
    check("1f URL da vaga composta base+/job/+jobId",
          str(student_de.url) == AKZO_URL + "/job/28874", str(student_de.url))
    check("1g controle não-student: 'Technical Application Specialist' "
          "(Biên Hòa, VNM) — sample não é 100% student",
          parsed[2].title.startswith("Technical Application")
          and "VNM" in parsed[2].location)
    all_parsed = [s._parse_job(i) for i in items]
    check("1h 100/100 da 1ª página parseiam com ats_id único",
          all(p is not None for p in all_parsed)
          and len({p.ats_id for p in all_parsed}) == 100)

    # --- 2. Contrato do registry re-apontado ---
    print("2. registry re-apontado")
    entry = next((e for e in SEED if e.name == "AkzoNobel"), None)
    check("2a AkzoNobel ats=phenom, tenant=phenom:https://careers.akzonobel.com",
          entry is not None and entry.ats == "phenom"
          and entry.tenant == AKZO_TENANT,
          f"ats={getattr(entry, 'ats', None)} tenant={getattr(entry, 'tenant', None)}")
    check("2b entrada successfactors:careers MORREU (re-point total)",
          not any(e.name == "AkzoNobel" and e.ats == "successfactors"
                  for e in SEED))
    prefix, slug = AKZO_TENANT.split(":", 1)
    from urllib.parse import urlparse

    check("2c forma F71: split(':',1) -> prefixo phenom + slug-URL https "
          "válida (host com ponto) — ':' extra é legal DENTRO de slug-URL",
          prefix == "phenom" and slug.startswith("https://")
          and "." in urlparse(slug).netloc and not any(c.isspace() for c in slug),
          f"prefix={prefix!r} slug={slug!r}")
    check("2d enabled (empresa segue operacional)",
          entry is not None and entry.enabled)

    # --- 3. Override de migração (mesma chave de identidade do F58) ---
    print("3. override TENANT_ATS_OVERRIDES (linha morta upstream)")
    # Resolução REAL do runtime (medida ao vivo 20/10): o manifest upstream
    # traz slug="careers" + url separada (successfactors ∈ URL_SLUG_ATS: o
    # DESAMBIGUADOR é a URL) — a chave do override usa o SLUG do manifest,
    # não a URL (distinto do F58, onde a linha avature traz a URL COMO slug).
    legacy = Company(name="AkzoNobel", ats="successfactors", slug="careers",
                     url=AKZO_URL, query="AkzoNobel", match_kind="exact")
    fixed = resolve_tenant_migration(legacy)
    check("3a resolve_tenant_migration reescreve p/ (phenom, URL)",
          fixed.ats == "phenom" and fixed.slug == AKZO_URL,
          f"ats={fixed.ats} slug={fixed.slug}")
    check("3b Company.url setado junto (hidratação/scraper_slug leem de lá)",
          fixed.url == AKZO_URL)
    check("3c chave completa no mapa: (successfactors, slug 'careers', AkzoNobel)",
          TENANT_ATS_OVERRIDES.get(
              ("successfactors", "careers", "AkzoNobel")) == ("phenom", AKZO_URL))
    check("3d regressão F58: override Siemens Healthineers PERMANECE",
          TENANT_ATS_OVERRIDES.get(
              ("avature",
               "https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs",
               "Siemens Healthineers"))
          == ("phenom", "https://careers.siemens-healthineers.com"))
    untouched = Company(name="Bosch", ats="smartrecruiters", slug="BoschGroup",
                        url=None, query="Bosch", match_kind="exact")
    check("3e inércia: empresa fora do mapa inalterada",
          resolve_tenant_migration(untouched) == untouched)
    check("3f scraper_slug devolve a URL p/ phenom (URL_SLUG_ATS)",
          scraper_slug(fixed) == AKZO_URL)
    wrong_name = Company(name="Outra Empresa", ats="successfactors",
                         slug="careers", url=AKZO_URL, query="x",
                         match_kind="exact")
    check("3g nome EXATO da empresa na chave: homônimo não é reescrito",
          resolve_tenant_migration(wrong_name).ats == "successfactors")
    swiss_re = Company(name="Swiss Re", ats="successfactors", slug="careers",
                       url="https://careers.swissre.com", query="Swiss Re",
                       match_kind="exact")
    check("3h slug COMPARTILHADO 'careers': Swiss Re NÃO é reescrito "
          "(mesmo slug, empresa/URL distintas — série saudável 40/40)",
          resolve_tenant_migration(swiss_re) == swiss_re)

    # --- 4. Consistência declarado x runtime na direção da correção ---
    print("4. consistência (direção da correção)")
    check("4a tenant novo declarado == resolvido -> consistent",
          tenant_consistency_status(AKZO_TENANT, [AKZO_TENANT]) == "consistent")
    check("4b linha antiga contra resolução nova seria drift (evitada)",
          tenant_consistency_status("successfactors:careers", [AKZO_TENANT]) == "drift")
    check("4c resolução multi (phenom novo + SF morto upstream) -> multi, "
          "declarado presente",
          tenant_consistency_status(
              AKZO_TENANT, ["successfactors:careers", AKZO_TENANT]) == "multi")

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"F72.1: {len(FAILURES)} de {N} verificações FALHARAM:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"F72.1: TUDO OK — {N} verificações")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
