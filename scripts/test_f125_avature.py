#!/usr/bin/env python3
"""F125 (avature) — ATS Avature (família nova): Siemens Energy + TenneT (offline).

NOTA DE ARQUIVO: esta suíte vive em ``test_f125_avature.py`` porque o nome
simples ``test_f125.py`` pertence historicamente à fase F12.5 (hotfix das
URLs do Top-5 no Telegram, 05/10) — colisão de numeração detectada na
união da onda F123–F128 e resolvida aqui (26/10).

O QUE A F125 FEZ (contexto da medição 26/10): 2 tenants Avature descobertos
via caça manual — portais modernos com Algolia/InstantSearch (JS pesado),
mas AMBOS expõem feed RSS funcional em /feed/ com pubDate + job URL estável.

- Siemens Energy (jobs.siemens-energy.com): RSS em
  /en_US/jobs/SearchJobsGermany/feed/?folderRecordsPerPage=20; job URL
  format: /jobs/FolderDetail/<slug>/<ID>/; pubDate presente; filtro DE via
  country-specific search pages (SearchJobsGermany, SearchJobsUS, etc.)

- TenneT (careers.tennet.eu): RSS em
  /en_US/careers/SearchJobs/feed/?jobRecordsPerPage=20; job URL format:
  /careers/JobDetail/<slug>/<ID>/; pubDate presente; multinacional NL/DE —
  filtro DE crítico (location parsing ou country-specific feeds).

Registry +2 (151→153); nova regra discovery 'avature' em discovery_rules.py;
TenantJobUrlFormat p/ ambos (F105); URL_SLUG_ATS inclui 'avature'.
Testes 100% OFFLINE: fixtures RSS VERBATIM congeladas, zero rede.
Parse pubDate/description, job_url_format_status, dedup, liveness F94.

Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
Uso:  .venv/bin/python scripts/test_f125.py
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.discovery_rules import (  # noqa: E402
    TENANT_JOB_URL_FORMATS,
    Invalid,
    RULES,
    classify,
    job_url_format_status,
    rule_for,
)
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.models.job import Job  # noqa: E402
from internship_finder.registry import SEED  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

FX = ROOT / "fixtures" / "f125"


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name if not detail else f"{name} — {detail}")


def section(name: str) -> None:
    print(f"\n--- {name} ---")


def _parse_rss(path: Path) -> list[dict]:
    """Parse RSS feed verbatim, return list of item dicts."""
    tree = ET.parse(path)
    root = tree.getroot()
    items = []
    for item in root.findall(".//item"):
        d = {}
        for child in item:
            # Remove namespace
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            d[tag] = child.text
        items.append(d)
    return items


def _parse_pubdate(text: str | None) -> datetime | None:
    """Parse RFC 2822 pubDate (e.g., 'Fri, 23 Oct 2026 2:00:00 GMT')."""
    if not text:
        return None
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(text).astimezone(UTC)
    except Exception:
        return None


# ======================================================================
# [A] Registry — 2 novas entradas no SEED (paramétrico test_registry)
# ======================================================================
def group_a() -> None:
    section("[A] Registry: 2 entradas F125 presentes no SEED")

    f125_entries = {
        "Siemens Energy": ("avature", "avature:https://jobs.siemens-energy.com"),
        "TenneT": ("avature", "avature:https://careers.tennet.eu"),
    }

    for name, (expected_ats, expected_tenant) in f125_entries.items():
        entry = next((e for e in SEED if e.name == name), None)
        check(f"{name} existe no SEED", entry is not None)
        if entry:
            check(f"{name}.ats == '{expected_ats}'", entry.ats == expected_ats)
            check(f"{name}.tenant == '{expected_tenant}'", entry.tenant == expected_tenant)
            check(f"{name}.enabled == True", entry.enabled is True)

    # Registry count baseline (SEED tinha 151 antes da F125, agora 153)
    check("Registry count == 153 (151 + 2 F125)", len(SEED) == 153)


# ======================================================================
# [B] Discovery Rules — regra 'avature' presente e coerente
# ======================================================================
def group_b() -> None:
    section("[B] Discovery Rules: regra 'avature' registrada e coerente")

    rule = rule_for("avature")
    check("rule_for('avature') existe", rule is not None)
    if rule:
        check("rule.ats == 'avature'", rule.ats == "avature")
        check("rule.url_as_slug == True", rule.url_as_slug is True)
        check("rule.resolvable == False", rule.resolvable is False)
        check("rule.csv_columns == ('name', 'slug', 'url')", rule.csv_columns == ("name", "slug", "url"))
        check("'SearchJobs' em rule.canonical_endpoint (HTML real do scraper instalado — cura da união)",
              "SearchJobs" in rule.canonical_endpoint)
        check("'JobDetail' em rule.jobs_signal (anchors HTML)", "JobDetail" in rule.jobs_signal)
        check("Invalid.UNRESOLVABLE_URL em rule.invalid", Invalid.UNRESOLVABLE_URL in rule.invalid)
        check("rule.sample_url == jobs.siemens-energy.com", rule.sample_url == "https://jobs.siemens-energy.com")

    # Cobertura: 'avature' deve aparecer no registry (via SEED)
    reg_ats = {e.ats for e in SEED if e.ats}
    check("'avature' em registry_ats()", "avature" in reg_ats)

    # Drift check: regras sem ATS no registry / ATS sem regra
    from internship_finder.discovery_rules import coverage
    cov = coverage()
    check("Nenhum ATS do registry sem regra (missing_rules vazio)", cov["missing_rules"] == [])


# ======================================================================
# [C] Fixtures RSS — parse verbatim e extração de campos
# ======================================================================
def group_c() -> None:
    section("[C] Fixtures RSS: parse verbatim + campos obrigatórios")

    # Siemens Energy DE feed
    siemens_items = _parse_rss(FX / "siemens_energy_de.xml")
    check("Siemens Energy DE feed: >= 10 items", len(siemens_items) >= 10)

    for i, item in enumerate(siemens_items[:3]):
        title = item.get("title", "")
        link = item.get("link", "")
        guid = item.get("guid", "")
        pubdate = item.get("pubDate", "")
        desc = item.get("description", "")

        check(f"SE[{i}] title não vazio", bool(title.strip()))
        check(f"SE[{i}] link presente e formato FolderDetail", bool(link) and "/FolderDetail/" in link)
        check(f"SE[{i}] guid == link (isPermaLink=true)", guid == link)
        check(f"SE[{i}] pubDate presente e parseável", _parse_pubdate(pubdate) is not None)
        # description pode ser vazio (location) ou ter país
        if desc:
            check(f"SE[{i}] description string", isinstance(desc, str))

    # TenneT feed
    tennet_items = _parse_rss(FX / "tennet.xml")
    check("TenneT feed: >= 10 items", len(tennet_items) >= 10)

    for i, item in enumerate(tennet_items[:3]):
        title = item.get("title", "")
        link = item.get("link", "")
        guid = item.get("guid", "")
        pubdate = item.get("pubDate", "")

        check(f"TT[{i}] title não vazio", bool(title.strip()))
        check(f"TT[{i}] link presente e formato JobDetail", bool(link) and "/JobDetail/" in link)
        check(f"TT[{i}] guid == link (isPermaLink=true)", guid == link)
        check(f"TT[{i}] pubDate presente e parseável", _parse_pubdate(pubdate) is not None)

    # Verifica job IDs estáveis (extraídos da URL)
    se_ids = {re.search(r"/(\d+)/?$", item.get("link", "")).group(1) for item in siemens_items if re.search(r"/(\d+)/?$", item.get("link", ""))}
    tt_ids = {re.search(r"/(\d+)/?$", item.get("link", "")).group(1) for item in tennet_items if re.search(r"/(\d+)/?$", item.get("link", ""))}
    check("Siemens Energy: job IDs únicos", len(se_ids) == len(siemens_items))
    check("TenneT: job IDs únicos", len(tt_ids) == len(tennet_items))
    check("IDs não se sobrepõem entre tenants", se_ids.isdisjoint(tt_ids))


# ======================================================================
# [D] Adapter — normalização via AtsJobAdapter (company + source)
# ======================================================================
def group_d() -> None:
    section("[D] Adapter: normalização Job (company, source, external_id, posted_at)")

    # Company objects como o runtime resolve
    se_company = Company(
        name="Siemens Energy",
        ats="avature",
        slug="https://jobs.siemens-energy.com",
        url="https://jobs.siemens-energy.com",
        source="avature:https://jobs.siemens-energy.com",
    )
    tt_company = Company(
        name="TenneT",
        ats="avature",
        slug="https://careers.tennet.eu",
        url="https://careers.tennet.eu",
        source="avature:https://careers.tennet.eu",
    )

    adapter = AtsJobAdapter()

    # Helper: pré-processa item RSS para campos que o adapter espera
    # (no scraper real, isso acontece no fetch do AvatureScraper)
    def _prep_rss_item(item: dict, link_key: str = "link") -> dict:
        out = dict(item)
        link = item.get(link_key, "")
        # external_id do final da URL: /FolderDetail/.../123456 ou /JobDetail/.../123456
        m = re.search(r"/(\d+)/?$", link)
        if m:
            out["external_id"] = m.group(1)
            out["ats_id"] = m.group(1)  # fallback chain do adapter
            out["job_id"] = m.group(1)
        # posted_at do pubDate (RFC 2822) — adapter _parse_dt só aceita ISO 8601
        # converter RFC 2822 -> ISO 8601 para o adapter
        pub = item.get("pubDate") or item.get("pubdate")
        if pub:
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(pub)
                iso = dt.isoformat().replace("+00:00", "Z")
            except Exception:
                iso = pub
            out["posted_at"] = iso
            out["postedAt"] = iso
            out["date_posted"] = iso
            out["datePosted"] = iso
            out["publication_date"] = iso
            out["published_at"] = iso
            out["created_at"] = iso
            out["createdAt"] = iso
        return out

    # Siemens Energy sample item
    se_item_raw = {
        "title": "Supplier Quality Engineer (f/m/d)",
        "link": "https://jobs.siemens-energy.com/jobs/FolderDetail/Supplier-Quality-Engineer-f-m-d/274959",
        "guid": "https://jobs.siemens-energy.com/jobs/FolderDetail/Supplier-Quality-Engineer-f-m-d/274959",
        "pubDate": "Thu, 05 Jun 2025 00:00:00 +0000",
        "description": "",
    }
    se_item = _prep_rss_item(se_item_raw)

    se_job = adapter.to_job(se_item, se_company)
    check("SE job.title correto", se_job.title == "Supplier Quality Engineer (f/m/d)")
    check("SE job.company == 'Siemens Energy'", se_job.company == "Siemens Energy")
    check("SE job.source == 'avature:https://jobs.siemens-energy.com'", se_job.source == "avature:https://jobs.siemens-energy.com")
    check("SE job.external_id == '274959'", se_job.external_id == "274959")
    check("SE job.posted_at == 2025-06-05", se_job.posted_at == datetime(2025, 6, 5, tzinfo=UTC))
    check("SE job.url == link do RSS", se_job.url == se_item["link"])
    check("SE job.id começa com 'Siemens Energy|avature:https://jobs.siemens-energy.com:'", se_job.id.startswith("Siemens Energy|avature:https://jobs.siemens-energy.com:"))

    # TenneT sample item
    tt_item_raw = {
        "title": "Power System EMT Specialist",
        "link": "https://careers.tennet.eu/careers/JobDetail/Power-System-EMT-Specialist/99587",
        "guid": "https://careers.tennet.eu/careers/JobDetail/Power-System-EMT-Specialist/99587",
        "pubDate": "Wed, 22 Oct 2025 00:00:00 +0000",
        "description": "",
    }
    tt_item = _prep_rss_item(tt_item_raw)

    tt_job = adapter.to_job(tt_item, tt_company)
    check("TT job.title correto", tt_job.title == "Power System EMT Specialist")
    check("TT job.company == 'TenneT'", tt_job.company == "TenneT")
    check("TT job.source == 'avature:https://careers.tennet.eu'", tt_job.source == "avature:https://careers.tennet.eu")
    check("TT job.external_id == '99587'", tt_job.external_id == "99587")
    check("TT job.posted_at == 2025-10-22", tt_job.posted_at == datetime(2025, 10, 22, tzinfo=UTC))
    check("TT job.url == link do RSS", tt_job.url == tt_item["link"])
    check("TT job.id começa com 'TenneT|avature:https://careers.tennet.eu:'", tt_job.id.startswith("TenneT|avature:https://careers.tennet.eu:"))

    # Dedup: mesmo external_id + mesmo source + mesma company = mesmo ID
    se_job2 = adapter.to_job(se_item, se_company)
    check("SE dedup: mesmo item -> mesmo ID", se_job.id == se_job2.id)

    # Empresas diferentes, mesmo external_id -> IDs diferentes (escopo company)
    tt_item_same_id = _prep_rss_item(dict(tt_item_raw, link=tt_item_raw["link"].replace("99587", "274959"), guid=tt_item_raw["guid"].replace("99587", "274959")))
    tt_job_same_ext = adapter.to_job(tt_item_same_id, tt_company)
    check("Cross-tenant dedup: IDs diferentes para external_id igual", se_job.id != tt_job_same_ext.id)


# ======================================================================
# [E] F105 — job_url_format_status (guard de formato vivo)
# ======================================================================
def group_e() -> None:
    section("[E] F105: job_url_format_status p/ Siemens Energy + TenneT")

    # Siemens Energy URLs
    se_current = "https://jobs.siemens-energy.com/jobs/FolderDetail/Supplier-Quality-Engineer-f-m-d/274959/"
    se_current_noslash = "https://jobs.siemens-energy.com/jobs/FolderDetail/Supplier-Quality-Engineer-f-m-d/274959"
    check("SE URL com trailing slash -> 'current'", job_url_format_status(se_current) == "current")
    check("SE URL sem trailing slash -> 'current'", job_url_format_status(se_current_noslash) == "current")

    # TenneT URLs
    tt_current = "https://careers.tennet.eu/careers/JobDetail/Power-System-EMT-Specialist/99587/"
    tt_current_noslash = "https://careers.tennet.eu/careers/JobDetail/Power-System-EMT-Specialist/99587"
    check("TT URL com trailing slash -> 'current'", job_url_format_status(tt_current) == "current")
    check("TT URL sem trailing slash -> 'current'", job_url_format_status(tt_current_noslash) == "current")

    # URLs inválidas/outros tenants -> None (silêncio honesto)
    check("URL inexistente -> None", job_url_format_status("https://example.com/job/123") is None)
    check("URL vazia -> None", job_url_format_status("") is None)
    check("None -> None", job_url_format_status(None) is None)

    # Verifica que as chaves existem no dict
    check("'siemens_energy' em TENANT_JOB_URL_FORMATS", "siemens_energy" in TENANT_JOB_URL_FORMATS)
    check("'tennet' em TENANT_JOB_URL_FORMATS", "tennet" in TENANT_JOB_URL_FORMATS)

    se_fmt = TENANT_JOB_URL_FORMATS["siemens_energy"]
    tt_fmt = TENANT_JOB_URL_FORMATS["tennet"]
    check("SE fmt.ats == 'avature'", se_fmt.ats == "avature")
    check("TT fmt.ats == 'avature'", tt_fmt.ats == "avature")
    check("SE fmt.legacy == ()", se_fmt.legacy == ())
    check("TT fmt.legacy == ()", tt_fmt.legacy == ())


# ======================================================================
# [F] Classificador discovery — classify() p/ avature
# ======================================================================
def group_f() -> None:
    section("[F] Classificador: classify() p/ avature (status 200 + jobs > 0)")

    # Sucesso: HTTP 200 + jobs > 0
    verdict = classify("avature", status=200, job_count=15, url="https://jobs.siemens-energy.com")
    check("classify avature 200+jobs -> valid=True", verdict.valid is True)
    check("classify avature reason contém jobs_vivas", "vagas vivas" in verdict.reason)

    # Branded shell: 200 mas 0 jobs
    verdict0 = classify("avature", status=200, job_count=0, url="https://jobs.siemens-energy.com")
    check("classify avature 200+0jobs -> BRANDED_SHELL", verdict0.valid is False and verdict0.reason == Invalid.BRANDED_SHELL)

    # 404
    verdict404 = classify("avature", status=404, url="https://jobs.siemens-energy.com")
    check("classify avature 404 -> HTTP_NOT_FOUND", verdict404.valid is False and verdict404.reason == Invalid.HTTP_NOT_FOUND)

    # Erro de rede
    verdict_net = classify("avature", status=0, error="timeout", url="https://jobs.siemens-energy.com")
    check("classify avature timeout -> UNREACHABLE", verdict_net.valid is False and verdict_net.reason == Invalid.UNREACHABLE)


# ======================================================================
# [G] Liveness F94 — posted_at ausente não exclui (flag, não delete)
# ======================================================================
def group_g() -> None:
    section("[G] Liveness F94: posted_at ausente -> flag, NUNCA delete por stale")

    # Item sem pubDate no RSS (simulado)
    se_company = Company(
        name="Siemens Energy",
        ats="avature",
        slug="https://jobs.siemens-energy.com",
        url="https://jobs.siemens-energy.com",
        source="avature:https://jobs.siemens-energy.com",
    )
    adapter = AtsJobAdapter()

    item_no_date = {
        "title": "Test Job No Date",
        "link": "https://jobs.siemens-energy.com/jobs/FolderDetail/Test-Job/999999",
        "guid": "https://jobs.siemens-energy.com/jobs/FolderDetail/Test-Job/999999",
        "pubDate": "",  # vazio
        "description": "Germany",
    }

    job = adapter.to_job(item_no_date, se_company)
    check("posted_at None quando pubDate ausente", job.posted_at is None)
    check("Job ainda criado (não descartado)", job.id is not None and job.title == "Test Job No Date")
    check("Job marcado como internship se título sugerir", job.internship is not None)


# ======================================================================
# [H] URL_SLUG_ATS — avature incluído
# ======================================================================
def group_h() -> None:
    section("[H] URL_SLUG_ATS: 'avature' presente")

    from internship_finder.collectors.ats_scraper import URL_SLUG_ATS
    check("'avature' em URL_SLUG_ATS", "avature" in URL_SLUG_ATS)


# ======================================================================
# MAIN
# ======================================================================
def main() -> int:
    print("=" * 70)
    print("F125 TEST SUITE — Avature (Siemens Energy + TenneT)")
    print("=" * 70)

    group_a()
    group_b()
    group_c()
    group_d()
    group_e()
    group_f()
    group_g()
    group_h()

    print(f"\n=== SUMMARY: {CHECKS} checks, {len(FAILURES)} failures ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())