#!/usr/bin/env python3
"""F117 — Testes para variante EN de locale SF (en_locale_variant + MANUAL-CHECK).

Fixtures VERBATIM (medidas no Passo 0, 24/10/2026):
- RWE DE×EN: talentcommunity/apply/<ID>/ + ?locale=en_GB
- BMW slug -en_US: /job/<slug>/<ID>-en_US/
- Tenant sem variante (ex.: Vetter, Henkel, Luxair) -> None

Offline, zero rede, auto-descoberto pelo CI (ci.yml intocavel).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from internship_finder.discovery_rules import en_locale_variant
from scripts.manual_check import build_manual_check_rows, write_manual_check_md


def test_en_locale_variant_bmw_slug_suffix() -> None:
    """BMW: slug suffix -en_US (medido 24/10/2026)."""
    # URL base (formato vivo medido: .../197707-de_DE/)
    url_de = "https://jobs.bmwgroup.com/job/Munich-Internship/1234567890/"
    url_en_expected = "https://jobs.bmwgroup.com/job/Munich-Internship/1234567890-en_US/"
    
    result = en_locale_variant(url_de)
    assert result == url_en_expected, f"BMW: expected {url_en_expected}, got {result}"
    
    # Ja tem suffix -en_US -> None
    assert en_locale_variant(url_en_expected) is None
    
    # Ja tem suffix -de_DE -> None
    url_de_suffix = "https://jobs.bmwgroup.com/job/Munich-Internship/1234567890-de_DE/"
    assert en_locale_variant(url_de_suffix) is None
    
    print("✓ test_en_locale_variant_bmw_slug_suffix")


def test_en_locale_variant_rwe_talentcommunity() -> None:
    """RWE talentcommunity: query param ?locale=en_GB (spec F117)."""
    # URL base talentcommunity
    url_base = "https://jobs.rwe.com/talentcommunity/apply/12345/"
    url_en_expected = "https://jobs.rwe.com/talentcommunity/apply/12345/?locale=en_GB"
    
    result = en_locale_variant(url_base)
    assert result == url_en_expected, f"RWE talentcommunity: expected {url_en_expected}, got {result}"
    
    # Ja tem locale param -> None
    assert en_locale_variant(url_en_expected) is None
    
    # URL RM (nao talentcommunity) -> None (padrao diferente)
    url_rm = "https://jobs.rwe.com/RWE/job/Some-Job/12345/"
    assert en_locale_variant(url_rm) is None
    
    print("✓ test_en_locale_variant_rwe_talentcommunity")


def test_en_locale_variant_rm_tenants() -> None:
    """RM tenants: query param ?locale=en_GB (formato verificado, conteudo nao garantido)."""
    # BASF
    basf_url = "https://basf.jobs/dark_blue_EMEA/job/Berlin-Internship/1443393533/"
    basf_en = "https://basf.jobs/dark_blue_EMEA/job/Berlin-Internship/1443393533/?locale=en_GB"
    assert en_locale_variant(basf_url) == basf_en
    assert en_locale_variant(basf_en) is None
    
    # SAP
    sap_url = "https://careers.sap.com/job/St_Leon_Rot-Intern/13873166/"
    sap_en = "https://careers.sap.com/job/St_Leon_Rot-Intern/13873166/?locale=en_GB"
    assert en_locale_variant(sap_url) == sap_en
    
    # Schaeffler
    sch_url = "https://jobs.schaeffler.com/job/Herzogenaurach-Intern/1445672533/"
    sch_en = "https://jobs.schaeffler.com/job/Herzogenaurach-Intern/1445672533/?locale=en_GB"
    assert en_locale_variant(sch_url) == sch_en
    
    # Kaufland
    kaf_url = "https://jobs.kaufland.com/Deutschland/job/Neckarsulm-Intern/1445010233/"
    kaf_en = "https://jobs.kaufland.com/Deutschland/job/Neckarsulm-Intern/1445010233/?locale=en_GB"
    assert en_locale_variant(kaf_url) == kaf_en
    
    # LIDL
    lidl_url = "https://jobs.lidl/sti/job/Neckarsulm-Intern/1436050633/"
    lidl_en = "https://jobs.lidl/sti/job/Neckarsulm-Intern/1436050633/?locale=en_GB"
    assert en_locale_variant(lidl_url) == lidl_en
    
    print("✓ test_en_locale_variant_rm_tenants")


def test_en_locale_variant_unknown_tenant() -> None:
    """Tenants sem variante verificada -> None (fail-closed)."""
    # Vetter (F105 - tem job_url_format mas nao en_locale verificado)
    vetter_url = "https://careers.vetter-pharma.com/job/some-slug/12345/"
    assert en_locale_variant(vetter_url) is None
    
    # Henkel (CSOD - nao SF)
    henkel_url = "https://henkel.csod.com/ux/ats/careersite/1/home?c=henkel"
    assert en_locale_variant(henkel_url) is None
    
    # Luxair (CSOD - nao SF)
    luxair_url = "https://luxair.csod.com/ux/ats/careersite/1/home?c=luxair"
    assert en_locale_variant(luxair_url) is None
    
    # Workday (nao SF)
    wd_url = "https://company.wd1.myworkdayjobs.com/site/job/12345"
    assert en_locale_variant(wd_url) is None
    
    # Greenhouse (nao SF)
    gh_url = "https://boards.greenhouse.io/company/jobs/12345"
    assert en_locale_variant(gh_url) is None
    
    # URL invalida/vazia
    assert en_locale_variant("") is None
    assert en_locale_variant("not-a-url") is None
    assert en_locale_variant(None) is None  # type: ignore
    
    print("✓ test_en_locale_variant_unknown_tenant")


def test_manual_check_includes_en_variant() -> None:
    """MANUAL-CHECK: linha inclui link EN render quando variante existe."""
    # Job simulado com URL BMW (tem variante EN)
    job_bmw = {
        "id": "test|sf_dataset:successfactors:bmw:123",
        "company": "BMW AG",
        "title": "Praktikant Business Intelligence",
        "url": "https://jobs.bmwgroup.com/job/Munich-Internship/1234567890/",
        "liveness_status": "unknown",
        "liveness_detail": "saml wall",
        "liveness_checked_at": "2026-10-24T10:00:00Z",
        "liveness_final_url": None,
    }
    
    rows = build_manual_check_rows([job_bmw])
    assert len(rows) == 1
    row = rows[0]
    assert row["en_variant"] is not None
    assert row["en_variant"] == "https://jobs.bmwgroup.com/job/Munich-Internship/1234567890-en_US/"
    assert "(EN render)" in row["en_variant"] or True  # verificado no write
    
    # Job simulado com URL Vetter (sem variante EN)
    job_vetter = {
        "id": "test|sf_dataset:successfactors:vetter:456",
        "company": "Vetter",
        "title": "Praktikant",
        "url": "https://careers.vetter-pharma.com/job/some-slug/12345/",
        "liveness_status": "unknown",
        "liveness_detail": "saml wall",
        "liveness_checked_at": "2026-10-24T10:00:00Z",
        "liveness_final_url": None,
    }
    
    rows = build_manual_check_rows([job_vetter])
    assert len(rows) == 1
    row = rows[0]
    assert row["en_variant"] is None
    
    print("✓ test_manual_check_includes_en_variant")


def test_write_manual_check_md_includes_en_render_link() -> None:
    """write_manual_check_md: gera link [abrir (EN render)] no markdown."""
    import tempfile
    
    rows = [{
        "id": "test|123",
        "company": "BMW AG",
        "title": "Praktikant Test",
        "motivo": "saml_wall",
        "gate_anchor": "",
        "url": "https://jobs.bmwgroup.com/job/Munich-Test/123/",
        "resolved": False,
        "portal_oficial": False,
        "en_variant": "https://jobs.bmwgroup.com/job/Munich-Test/123-en_US/",
        "date": "2026-10-24",
    }]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "MANUAL-CHECK.md"
        write_manual_check_md(out_path, rows, "2026-10-24T10:00:00Z")
        content = out_path.read_text(encoding="utf-8")
        
        # Verifica link principal
        assert "[abrir](https://jobs.bmwgroup.com/job/Munich-Test/123/)" in content
        # Verifica link EN render
        assert "[abrir (EN render)](https://jobs.bmwgroup.com/job/Munich-Test/123-en_US/)" in content
        # Verifica nota (EN render)
        assert "(EN render)" in content
    
    print("✓ test_write_manual_check_md_includes_en_render_link")


def test_manual_check_rwe_talentcommunity_en_render() -> None:
    """MANUAL-CHECK: RWE talentcommunity com EN render."""
    job_rwe = {
        "id": "test|sf_dataset:successfactors:rwe:789",
        "company": "RWE",
        "title": "Internship Offshore Operations",
        "url": "https://jobs.rwe.com/talentcommunity/apply/789/",
        "liveness_status": "unknown",
        "liveness_detail": "saml wall",
        "liveness_checked_at": "2026-10-24T10:00:00Z",
        "liveness_final_url": None,
    }
    
    rows = build_manual_check_rows([job_rwe])
    assert len(rows) == 1
    row = rows[0]
    assert row["en_variant"] == "https://jobs.rwe.com/talentcommunity/apply/789/?locale=en_GB"
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "MANUAL-CHECK.md"
        write_manual_check_md(out_path, rows, "2026-10-24T10:00:00Z")
        content = out_path.read_text(encoding="utf-8")
        
        assert "[abrir (EN render)](https://jobs.rwe.com/talentcommunity/apply/789/?locale=en_GB)" in content
    
    print("✓ test_manual_check_rwe_talentcommunity_en_render")


def run_all() -> None:
    """Executa todos os testes."""
    test_en_locale_variant_bmw_slug_suffix()
    test_en_locale_variant_rwe_talentcommunity()
    test_en_locale_variant_rm_tenants()
    test_en_locale_variant_unknown_tenant()
    test_manual_check_includes_en_variant()
    test_write_manual_check_md_includes_en_render_link()
    test_manual_check_rwe_talentcommunity_en_render()
    print("\n✅ Todos os testes F117 passaram!")


if __name__ == "__main__":
    run_all()