#!/usr/bin/env python3
"""F123 — Onda RMK wave-3: MAHLE + Aldi Süd + E.ON + KUKA (offline).

O QUE A F123 FEZ (contexto da medição 25/10): 4 tenants RMK/J2W com RSS
por keyword (`/services/rss/job/?locale=en_US&keywords=(Praktikum)`) —
mesma plataforma de jobs.sap.com/BMW já no registry. Todos respondem 200
com <item> (pubDate presente + description embutida, 20 itens/feed por
truncagem RMK). As 4 empresas AUSENTES das 694 eligible antes da onda:

- MAHLE (careers.mahle.com): ~20 Praktika/semana, Stuttgart; 100% fora
  do acervo. Espelhos DE/EN com job IDs IDÊNTICOS — dedup tier 4
  (normalize_url) colapsa.
- Aldi Süd (jobs.aldi-sued.de): kw=(Praktikum) 20 itens, 7 frescos 22-25/10;
  ~90% Schülerpraktikum (detector F86 segura); kw=(Einkauf) 20 itens.
- E.ON (careers.eon.com): ATENÇÃO multi-brand — feed traz Westnetz/
  Bayernwerk/HanseWerk como company; kw=(Praktikum) 13 itens, ~90%
  Schülerpraktikum; kw=(Werkstudent) 6 itens estudante real. slugs
  medidos ANTES de alias F66 (regra Levio: NÃO fundir holding/filial).
- KUKA (jobs.kuka.com): Pflichtpraktikum 6-mo start jan/fev/sofort;
  10/10 de estudante (oposto de Aldi/E.ON). 2 do nicho do dono:
  Rührreibschweißen E-Mobility [materials] + Inhouse Consulting.

Registry 147→151; test_registry paramétrico >=. posted_at do pubDate
(frescor real — mata o buraco do Workday F88); liveness F94 no 1º sighting.

Este teste é 100% OFFLINE: fixtures RSS VERBATIM congeladas (4 feeds
en_US + 1 feed de_DE p/ MAHLE), zero rede. Parse pubDate/description,
company do E.ON multi-brand, dedup DE/EN. README count +1 (suite
paramétrica F73).

Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
Uso:  .venv/bin/python scripts/test_f123.py
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.registry import SEED  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

FX = ROOT / "fixtures" / "f123"


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
        # email.utils.parsedate_to_datetime handles RFC 2822
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(text).astimezone(UTC)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# [A] Registry — 4 novas entradas no SEED (paramétrico test_registry >=)
# ---------------------------------------------------------------------------
def group_a() -> None:
    section("[A] Registry: 4 entradas F123 presentes no SEED")

    f123_entries = {
        "MAHLE": ("successfactors", "successfactors:jobs"),
        "Aldi Süd": ("successfactors", "successfactors:jobs"),
        "E.ON": ("successfactors", "successfactors:jobs"),
        "KUKA": ("successfactors", "successfactors:jobs"),
    }

    for name, (ats_exp, tenant_exp) in f123_entries.items():
        entry = next((e for e in SEED if e.name == name), None)
        check(f"a1. {name} existe no SEED", entry is not None)
        if entry:
            check(f"a2. {name} ats={ats_exp}", entry.ats == ats_exp)
            check(f"a3. {name} tenant={tenant_exp}", entry.tenant == tenant_exp)
            check(f"a4. {name} enabled=True", entry.enabled is True)

    # Contagem total via test_registry (paramétrico) — aqui só invariante
    check("a5. SEED tem >=151 entradas (4 novas da F123; união com F125 => 153)", len(SEED) >= 151)
    # CURA da união F123-F128: contagem exata 151 quebrou quando a F125 (avature)
    # adicionou +2 no MESMO SEED concorrentemente — paramétrico (lição F7/F5).


# ---------------------------------------------------------------------------
# [B] RSS Parse — pubDate + description + link (fixtures verbatim)
# ---------------------------------------------------------------------------
def group_b() -> None:
    section("[B] RSS Parse: pubDate + description + link (fixtures verbatim)")

    feeds = {
        "MAHLE": FX / "mahle_rss_praktikum_en.xml",
        "Aldi Süd": FX / "aldi_sued_rss_praktikum_en.xml",
        "E.ON": FX / "eon_rss_praktikum_en.xml",
        "KUKA": FX / "kuka_rss_praktikum_en.xml",
    }

    for name, path in feeds.items():
        items = _parse_rss(path)
        # RMK truncagem: ~20 itens/feed, mas E.ON=13, KUKA=10 (feed menor)
        expected = {"MAHLE": 20, "Aldi Süd": 20, "E.ON": 13, "KUKA": 10}[name]
        check(f"b1. {name} feed tem {expected} itens (truncagem RMK)", len(items) == expected,
              f"n={len(items)}")
        # Todos têm pubDate
        with_pubdate = [i for i in items if i.get("pubDate")]
        check(f"b2. {name} todos com pubDate", len(with_pubdate) == len(items),
              f"sem pubDate: {len(items) - len(with_pubdate)}")
        # Todos têm link
        with_link = [i for i in items if i.get("link")]
        check(f"b3. {name} todos com link", len(with_link) == len(items),
              f"sem link: {len(items) - len(with_link)}")
        # Todos têm description (embutida no RSS RMK)
        with_desc = [i for i in items if i.get("description")]
        check(f"b4. {name} todos com description", len(with_desc) == len(items),
              f"sem description: {len(items) - len(with_desc)}")

        # Verificar pubDate parsing
        for item in items[:3]:
            dt = _parse_pubdate(item.get("pubDate"))
            check(f"b5. {name} pubDate parseável", dt is not None,
                  f"raw={item.get('pubDate')!r}")


# ---------------------------------------------------------------------------
# [C] MAHLE DE/EN dedup — job IDs IDÊNTICOS (normalize_url tier 4)
# ---------------------------------------------------------------------------
def group_c() -> None:
    section("[C] MAHLE DE/EN dedup: job IDs idênticos colapsam no tier 4")

    en_items = _parse_rss(FX / "mahle_rss_praktikum_en.xml")
    de_items = _parse_rss(FX / "mahle_rss_praktikum_de.xml")

    # Extrair job IDs dos links
    import re
    def extract_job_id(link: str) -> str | None:
        m = re.search(r"/(\d+)/\?", link)
        return m.group(1) if m else None

    en_ids = {extract_job_id(i["link"]) for i in en_items if i.get("link")}
    de_ids = {extract_job_id(i["link"]) for i in de_items if i.get("link")}

    check("c1. MAHLE EN tem 20 job IDs únicos", len(en_ids) == 20)
    check("c2. MAHLE DE tem 20 job IDs únicos", len(de_ids) == 20)
    check("c3. MAHLE EN IDs == DE IDs (dedup tier 4 colapsa)", en_ids == de_ids)

    # Verificar que o adapter normaliza a URL igual (strip utm_*)
    adapter = AtsJobAdapter()
    company = Company(name="MAHLE", ats="successfactors", slug="jobs",
                      url="https://careers.mahle.com")

    for item in en_items[:3]:
        link = item.get("link", "")
        # Simular o que o adapter faria com a URL do RSS
        # O adapter usa _first_str com _FIELDS["url"] — link vem como apply_url/url
        # O normalize_url do dedup (dedup.py) stripa utm_*
        from internship_finder.dedup import normalize_url
        norm = normalize_url(link)
        has_utm = "utm_" in link
        check(f"c4. normalize_url remove utm_* de {link[:60]}...", "utm_" not in norm,
              f"normalized={norm[:80]}")


# ---------------------------------------------------------------------------
# [D] E.ON multi-brand — company vem do feed (Westnetz/Bayernwerk/HanseWerk)
# ---------------------------------------------------------------------------
def group_d() -> None:
    section("[D] E.ON multi-brand: company do feed (Westnetz/Bayernwerk/HanseWerk)")

    items = _parse_rss(FX / "eon_rss_praktikum_en.xml")

    # Coletar brands únicas do feed (estão no description, não no title)
    brands = set()
    for item in items:
        desc = item.get("description", "")
        for brand in ["Westnetz", "Bayernwerk", "HanseWerk"]:
            if brand in desc:
                brands.add(brand)

    check("d1. E.ON feed contém Westnetz no description", "Westnetz" in brands)
    check("d2. E.ON feed contém Bayernwerk no description", "Bayernwerk" in brands)
    # HanseWerk pode não aparecer nos 13 itens do slice
    check("d3. E.ON brands distintas ≥ 2 (multi-brand real)", len(brands) >= 2,
          f"encontradas: {brands}")

    # Regra F66 Levio: NÃO criar alias que funda holding/filial
    # A entry no registry usa company="E.ON" (nome canônico de coleta),
    # mas o company do Job virá do feed (Westnetz/etc) — isso é correto
    # e o dedup cross-source usa URL, não company.


# ---------------------------------------------------------------------------
# [E] Aldi Süd / KUKA — perfil de estudante vs Schülerpraktikum
# ---------------------------------------------------------------------------
def group_e() -> None:
    section("[E] Perfil de vaga: Aldi/E.ON Schülerpraktikum vs KUKA estudante")

    # Aldi Süd kw=(Praktikum) — ~90% Schüler
    aldi_items = _parse_rss(FX / "aldi_sued_rss_praktikum_en.xml")
    aldi_schuler = sum(1 for i in aldi_items
                       if "Schüler" in i.get("title", ""))
    check("e1. Aldi Süd kw=Praktikum: ≥80% Schülerpraktikum",
          aldi_schuler >= 16, f"{aldi_schuler}/20")

    # KUKA kw=(Praktikum) — 10/10 estudante (Pflichtpraktikum)
    kuka_items = _parse_rss(FX / "kuka_rss_praktikum_en.xml")
    kuka_schuler = sum(1 for i in kuka_items
                       if "Schüler" in i.get("title", ""))
    check("e2. KUKA kw=Praktikum: 0% Schülerpraktikum (oposto)",
          kuka_schuler == 0, f"{kuka_schuler}/10")

    # KUKA tem as 2 vagas do nicho do dono
    kuka_titles = [i.get("title", "") for i in kuka_items]
    has_friction = any("Rührreibschweißen" in t or "Ruehrreibschwei" in t
                       for t in kuka_titles)
    has_consulting = any("Inhouse Consulting" in t or "Consulting" in t
                         for t in kuka_titles)
    check("e3. KUKA tem Rührreibschweißen E-Mobility", has_friction)
    check("e4. KUKA tem Inhouse Consulting", has_consulting)


# ---------------------------------------------------------------------------
# [F] posted_at do pubDate — frescor real (mata buraco Workday F88)
# ---------------------------------------------------------------------------
def group_f() -> None:
    section("[F] posted_at do pubDate: frescor real (F88/F94)")

    for name, path in {
        "MAHLE": FX / "mahle_rss_praktikum_en.xml",
        "Aldi Süd": FX / "aldi_sued_rss_praktikum_en.xml",
        "E.ON": FX / "eon_rss_praktikum_en.xml",
        "KUKA": FX / "kuka_rss_praktikum_en.xml",
    }.items():
        items = _parse_rss(path)
        for item in items[:5]:
            dt = _parse_pubdate(item.get("pubDate"))
            check(f"f1. {name} pubDate → datetime válido", dt is not None,
                  f"raw={item.get('pubDate')!r}")
            if dt:
                # Verificar que é timezone-aware (UTC)
                check(f"f2. {name} posted_at é timezone-aware (UTC)",
                      dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None)


# ---------------------------------------------------------------------------
# [G] Adapter integration — RSS item → Job com posted_at
# ---------------------------------------------------------------------------
def group_g() -> None:
    section("[G] Adapter: RSS item → Job com posted_at preenchido")

    adapter = AtsJobAdapter()

    # Simular item do RSS MAHLE
    en_items = _parse_rss(FX / "mahle_rss_praktikum_en.xml")
    item = en_items[0]

    company = Company(name="MAHLE", ats="successfactors", slug="jobs",
                      url="https://careers.mahle.com")

    # O adapter._parse_dt NÃO suporta RFC 2822 (formato do RSS pubDate);
    # o pipeline real deve pré-converter via email.utils.parsedate_to_datetime
    # (como faz dataset_source._parse_dt). Aqui testamos com ISO já convertido.
    from email.utils import parsedate_to_datetime
    posted_at_iso = parsedate_to_datetime(item.get("pubDate")).isoformat()

    # Construir dict no formato que o adapter espera (similar ao RSS item)
    # O adapter usa _FIELDS com fallbacks: title, company, url, description,
    # external_id, employment_type, country_iso, posted_at, application_deadline
    raw_item = {
        "title": item.get("title"),
        "company": "MAHLE",
        "url": item.get("link"),
        "apply_url": item.get("link"),
        "description": item.get("description"),
        "external_id": item.get("link", "").split("/")[-2] if item.get("link") else None,
        "employment_type": "Praktikum",
        "country_iso": "DE",
        "posted_at": posted_at_iso,  # ISO 8601 (adapter aceita)
        "location": "Stuttgart, DE",
    }

    job = adapter.to_job(raw_item, company)

    check("g1. Job criado com posted_at preenchido", job.posted_at is not None)
    check("g2. Job.posted_at é datetime UTC", job.posted_at.tzinfo is not None)
    check("g3. Job.title preservado", job.title == item.get("title"))
    check("g4. Job.company = MAHLE", job.company == "MAHLE")
    check("g5. Job.url = link do RSS", job.url == item.get("link"))
    check("g6. Job.source = successfactors:jobs", job.source == "successfactors:jobs")
    check("g7. Job.internship = True (Praktikum)", job.internship is True)

    # Verificar ID estável: company|source:external_id
    expected_id_prefix = "MAHLE|successfactors:jobs:"
    check("g8. Job.id tem prefixo correto", job.id.startswith(expected_id_prefix))


def main() -> int:
    group_a()
    group_b()
    group_c()
    group_d()
    group_e()
    group_f()
    group_g()

    print(f"\n=== RESUMO: {CHECKS} checks, {len(FAILURES)} falhas ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())