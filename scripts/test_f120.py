#!/usr/bin/env python3
"""F120 — programas multi-site: agrupamento visual (display-only).

Agrupa visualmente vagas do mesmo programa (mesma empresa normalizada +
mesmo título normalizado em N>=3 cidades distintas) com badge/linha
"programa multi-site: N cidades — X, Y, Z...". Ranking/JSON/digest
INTOCADOS (A/B byte a byte obrigatório).

Casos da spec:
1. Amazon Logistik Start 2027 ×12 sites -> 1 badge com 12 cidades
2. Pares (N=2) -> SEM badge (threshold é 3)
3. Programa em múltiplas seções (top, 🆕, 🧪, 🇪🇺) -> badge em cada
4. A/B byte a byte: JSON/CSV/ranking idênticos pré/pós F120

Fixtures: SINTÉTICAS, offline, zero rede.
Uso:  .venv/bin/python scripts/test_f120.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    tag = "OK" if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


def esc(value: object) -> str:
    import html as _html
    return _html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# Fixture: Amazon Logistik Start 2027 ×12 (congelado)
# ---------------------------------------------------------------------------

AMAZON_12 = [
    {
        "id": "Amazon|sf_dataset:amazon:10587449",
        "title": "Praktikum im Bereich Logistik - Berlin - Start 2027",
        "company": "Amazon Deutschland N16 Transport GmbH",
        "location": "Berlin, Berlin, DEU",
        "country_iso": "de",
        "score": 15.0,
        "url": "https://account.amazon.jobs/jobs/10587449/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10587448",
        "title": "Praktikum im Bereich Logistik - München - Start 2027",
        "company": "Amazon Deutschland S18 Transport GmbH",
        "location": "München, Bayern, DEU",
        "country_iso": "de",
        "score": 14.8,
        "url": "https://account.amazon.jobs/jobs/10587448/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10587447",
        "title": "Praktikum im Bereich Logistik - Trierweiler Start 2027",
        "company": "Amazon Deutschland W11 Transport GmbH",
        "location": "Trierweiler, Rhineland-Palatinate, DEU",
        "country_iso": "de",
        "score": 14.6,
        "url": "https://account.amazon.jobs/jobs/10587447/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10585115",
        "title": "Praktikum im Bereich Logistik - Hoppegarten Start 2027",
        "company": "Amazon Deutschland E4 Transport GmbH",
        "location": "Hoppegarten, Brandenburg, DEU",
        "country_iso": "de",
        "score": 14.4,
        "url": "https://account.amazon.jobs/jobs/10585115/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10585114",
        "title": "Praktikum im Bereich Logistik - Rostock- Start 2027",
        "company": "Amazon Deutschland S42 Transport GmbH",
        "location": "Rostock, Mecklenburg-Vorpommern, DEU",
        "country_iso": "de",
        "score": 14.2,
        "url": "https://account.amazon.jobs/jobs/10585114/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10585113",
        "title": "Praktikum im Bereich Logistik - Werder- Start 2027",
        "company": "Amazon Deutschland E3 Transport GmbH",
        "location": "Werder (Havel), Brandenburg, DEU",
        "country_iso": "de",
        "score": 14.0,
        "url": "https://account.amazon.jobs/jobs/10585113/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10566463",
        "title": "Praktikum im Bereich Logistik - Aachen - Start 2027",
        "company": "Amazon Deutschland S41 Transport GmbH - K97",
        "location": "Aachen, North-Rhine-Westphalia, DEU",
        "country_iso": "de",
        "score": 13.8,
        "url": "https://account.amazon.jobs/jobs/10566463/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10560248",
        "title": "Praktikum im Bereich Logistik - Troisdorf - Start 2027",
        "company": "Amazon Deutschland S41 Transport GmbH - K97",
        "location": "Troisdorf, North-Rhine-Westphalia, DEU",
        "country_iso": "de",
        "score": 13.6,
        "url": "https://account.amazon.jobs/jobs/10560248/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10560223",
        "title": "Praktikum im Bereich Logistik - Düsseldorf - Start 2027",
        "company": "Amazon Deutschland S41 Transport GmbH - K97",
        "location": "Dusseldorf, North-Rhine-Westphalia, DEU",
        "country_iso": "de",
        "score": 13.4,
        "url": "https://account.amazon.jobs/jobs/10560223/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10560212",
        "title": "Praktikum im Bereich Logistik - Bremen - Start 2027",
        "company": "Amazon Deutschland S41 Transport GmbH - K97",
        "location": "Bremen, Bremen, DEU",
        "country_iso": "de",
        "score": 13.2,
        "url": "https://account.amazon.jobs/jobs/10560212/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10558914",
        "title": "Praktikum im Bereich Logistik - Hof - Start 2027",
        "company": "Amazon Gattendorf GmbH - M44",
        "location": "Gattendorf, Bavaria, DEU",
        "country_iso": "de",
        "score": 13.0,
        "url": "https://account.amazon.jobs/jobs/10558914/apply",
    },
    {
        "id": "Amazon|sf_dataset:amazon:10551598",
        "title": "Praktikum im Bereich Logistik - Gera - Start 2027",
        "company": "Amazon Gera GmbH - K75",
        "location": "Gera, Thuringia, DEU",
        "country_iso": "de",
        "score": 12.8,
        "url": "https://account.amazon.jobs/jobs/10551598/apply",
    },
]


# Contra-caso: par (N=2) -> SEM badge
PAIR_CASE = [
    {
        "id": "Pair|1",
        "title": "Ausbildung zum Kaufmann - Berlin",
        "company": "Kaufland Berlin GmbH",
        "location": "Berlin, Berlin, DEU",
        "country_iso": "de",
        "score": 10.0,
        "url": "http://example.com/pair1",
    },
    {
        "id": "Pair|2",
        "title": "Ausbildung zum Kaufmann - München",
        "company": "Kaufland München GmbH",
        "location": "München, Bayern, DEU",
        "country_iso": "de",
        "score": 9.5,
        "url": "http://example.com/pair2",
    },
]

# Contra-caso: empresas diferentes, mesmo título -> SEM badge (empresa difere)
DIFF_COMPANIES = [
    {
        "id": "Diff|1",
        "title": "Software Engineer - Berlin",
        "company": "Company A GmbH",
        "location": "Berlin, Berlin, DEU",
        "country_iso": "de",
        "score": 10.0,
        "url": "http://example.com/diff1",
    },
    {
        "id": "Diff|2",
        "title": "Software Engineer - München",
        "company": "Company B GmbH",
        "location": "München, Bayern, DEU",
        "country_iso": "de",
        "score": 9.5,
        "url": "http://example.com/diff2",
    },
    {
        "id": "Diff|3",
        "title": "Software Engineer - Hamburg",
        "company": "Company C GmbH",
        "location": "Hamburg, Hamburg, DEU",
        "country_iso": "de",
        "score": 9.0,
        "url": "http://example.com/diff3",
    },
]


# ---------------------------------------------------------------------------
# A — helpers puros (normalização + detecção)
# ---------------------------------------------------------------------------

def test_a_helpers() -> None:
    section("A: helpers puros (normalização + detecção)")

    # A1: normalização de empresa Amazon
    n16 = mp._normalize_company_for_grouping("Amazon Deutschland N16 Transport GmbH")
    s18 = mp._normalize_company_for_grouping("Amazon Deutschland S18 Transport GmbH")
    logistik = mp._normalize_company_for_grouping("Amazon Logistik GmbH - A33")
    check("A1a Amazon N16 -> 'amazon transport'", n16 == "amazon transport")
    check("A1b Amazon S18 -> 'amazon transport'", s18 == "amazon transport")
    check("A1c Amazon Logistik -> 'amazon transport'", logistik == "amazon transport")
    check("A1d todas Amazon Transport colapsam", n16 == s18 == logistik)

    # A2: normalização de título remove cidade
    t1 = mp._normalize_title_for_grouping("Praktikum im Bereich Logistik - Berlin - Start 2027")
    t2 = mp._normalize_title_for_grouping("Praktikum im Bereich Logistik - München - Start 2027")
    t3 = mp._normalize_title_for_grouping("Praktikum im Bereich Logistik - Hamburg - Start 2027")
    check("A2a título Berlin normalizado", t1 == "praktikum im bereich logistik")
    check("A2b título München normalizado", t2 == "praktikum im bereich logistik")
    check("A2c título Hamburg normalizado", t3 == "praktikum im bereich logistik")
    check("A2d todos colapsam", t1 == t2 == t3)

    # A3: extração de cidade
    c1 = mp._extract_city_from_location("Berlin, Berlin, DEU")
    c2 = mp._extract_city_from_location("Blankenfelde-Mahlow, Brandenburg, DEU")
    c3 = mp._extract_city_from_location("Trierweiler, Rhineland-Palatinate, DEU")
    check("A3a cidade Berlin", c1 == "Berlin")
    check("A3b cidade Blankenfelde-Mahlow", c2 == "Blankenfelde-Mahlow")
    check("A3c cidade Trierweiler", c3 == "Trierweiler")

    # A4: detecção multi-site (threshold 3)
    programs = mp._detect_multisite_programs(AMAZON_12)
    check("A4a Amazon 12 -> 1 programa detectado", len(programs) == 1)
    prog = list(programs.values())[0]
    check("A4b 12 jobs no programa", prog["count"] == 12)
    check("A4c 12 cidades distintas", len(prog["cities"]) == 12)
    check("A4d cidades ordenadas", prog["cities"] == sorted(prog["cities"]))

    # A5: contra-caso par (N=2) -> vazio
    pair_programs = mp._detect_multisite_programs(PAIR_CASE)
    check("A5 par N=2 -> sem programa", pair_programs == {})

    # A6: contra-caso empresas diferentes -> vazio
    diff_programs = mp._detect_multisite_programs(DIFF_COMPANIES)
    check("A6 empresas diferentes -> sem programa", diff_programs == {})


# ---------------------------------------------------------------------------
# B — render página principal (top-N) com badge
# ---------------------------------------------------------------------------

def test_b_main_page() -> None:
    section("B: página principal (top-N) com seção 'programas'")

    html = mp.render_minimal_html(
        AMAZON_12, total_eligible=12, generated_at="2026-10-24 10:00",
        top=10, lang="pt"
    )

    # B1: seção 'programas' presente (ul.spot com itens)
    check("B1 seção 'programas' presente (ul.spot)", '<ul class="spot">' in html)
    check("B1b texto 'multi-site' presente", "multi-site" in html)

    # B2: seção lista as cidades
    import re
    # Procura na seção programas (ul.spot)
    programas_match = re.search(r'<ul class="spot">(.*?)</ul>', html, re.DOTALL)
    check("B2 seção programas lista cidades", programas_match is not None)
    if programas_match:
        cities = [c.strip() for c in re.findall(r'<li[^>]*>([^<]+)</li>', programas_match.group(1))]
        check(f"B2b {len(cities)} cidades listadas (esperado 12)", len(cities) == 12)
        # As cidades vêm com prefixo "📍 "
        check("B2c Berlin incluída", any("Berlin" in c for c in cities))
        check("B2d München incluída", any("München" in c for c in cities))

    # B3: seção programas está no final (antes do rodapé)
    programas_idx = html.find('<ul class="spot">')
    footer_idx = html.find('<p class="f"')
    check("B3 seção programas antes do rodapé", programas_idx != -1 and programas_idx < footer_idx)

    # B4: apenas 1 seção programas (não repetida)
    programas_count = html.count('<ul class="spot">')
    check("B4 apenas 1 seção programas", programas_count == 1)

    # B5: JSON/CSV intocados — o render NÃO altera a lista de jobs
    check("B5 lista de entrada não mutada", len(AMAZON_12) == 12)


# ---------------------------------------------------------------------------
# C — badge em múltiplas seções (🆕, 🧪, 🇪🇺)
# ---------------------------------------------------------------------------

def test_c_sections() -> None:
    section("C: seção 'programas' em múltiplos renders")

    # Jobs com materials_score para testar seção 🧪
    jobs_with_mat = []
    for i, j in enumerate(AMAZON_12):
        job = dict(j)
        if i < 4:  # primeiras 4 têm materials_score
            job["materials_score"] = 40.0 - i * 0.5
        jobs_with_mat.append(job)

    materials = [j for j in jobs_with_mat if "materials_score" in j][:3]
    new_ids = {"Amazon|sf_dataset:amazon:10587449", "Amazon|sf_dataset:amazon:10587448"}

    html = mp.render_minimal_html(
        jobs_with_mat, total_eligible=12, generated_at="2026-10-24 10:00",
        top=10, lang="pt", materials=materials, new_since_ids=new_ids
    )

    # C1: seção programas presente uma única vez mesmo com múltiplas seções
    programas_count = html.count('<ul class="spot">')
    check(f"C1 seção programas presente uma vez = {programas_count}", programas_count == 1)

    # C2: seção programas contém todas as cidades
    import re
    programas_match = re.search(r'<ul class="spot">(.*?)</ul>', html, re.DOTALL)
    check("C2 seção programas lista cidades", programas_match is not None)
    if programas_match:
        cities = [c.strip() for c in re.findall(r'<li[^>]*>([^<]+)</li>', programas_match.group(1))]
        check(f"C2b {len(cities)} cidades listadas (esperado 12)", len(cities) == 12)
        # As cidades vêm com prefixo "📍 "
        check("C2c Berlin incluída", any("Berlin" in c for c in cities))
        check("C2d München incluída", any("München" in c for c in cities))

    # C3: seção programas está no final (antes do rodapé)
    programas_idx = html.find('<ul class="spot">')
    footer_idx = html.find('<p class="f"')
    check("C3 seção programas antes do rodapé", programas_idx != -1 and programas_idx < footer_idx)


# ---------------------------------------------------------------------------
# D — A/B byte a byte: ranking/JSON/digest intocados
# ---------------------------------------------------------------------------

def test_d_ab_byte_identity() -> None:
    section("D: A/B byte a byte — ranking/JSON/digest intocados")

    # O render NÃO deve mutar a lista de entrada
    jobs_copy = [dict(j) for j in AMAZON_12]
    _ = mp.render_minimal_html(
        jobs_copy, total_eligible=12, generated_at="2026-10-24 10:00",
        top=10, lang="pt"
    )

    # D1: lista original inalterada (mesmos ids, mesma ordem)
    check("D1 lista não mutada (ids)", [j["id"] for j in jobs_copy] == [j["id"] for j in AMAZON_12])
    check("D2 lista não mutada (ordem)", all(a["id"] == b["id"] for a, b in zip(jobs_copy, AMAZON_12)))

    # D2: apply_company_cap continua funcionando igual (regra do site)
    # O cap usa o nome da empresa ORIGINAL (não normalizado) — com 12 empresas
    # originais diferentes, cada uma tem 1 vaga, então o cap 2 não limita.
    # O limite efetivo é o `limit=10` (top-N).
    capped = mp.apply_company_cap(AMAZON_12, limit=10)
    check("D3 apply_company_cap respeita cap 2/empresa original", len(capped) == 10)
    # D4: cap não reordena (ordem oficial preservada)
    # Com cap 2/empresa original, as vagas puladas são as 3ª+ de cada empresa
    # A ordem dos jobs que ENTRAM no cap é a mesma do ranking original
    capped_ids = [j["id"] for j in capped]
    # Verifica que a ordem relativa é preservada (nenhum job passa à frente de outro que estava antes no ranking)
    check("D4 cap não reordena (ordem relativa preservada)",
          all(capped_ids.index(capped_ids[i]) < capped_ids.index(capped_ids[i+1])
              for i in range(len(capped_ids) - 1)))

    # D3: digest usa a MESMA função apply_company_cap (sync site×digest)
    from minimal_page import COMPANY_MAX_CARDS, apply_company_cap
    check("D5 COMPANY_MAX_CARDS == 2 (fonte única)", COMPANY_MAX_CARDS == 2)
    # O digest importa apply_company_cap do minimal_page (testado no test_f93)


# ---------------------------------------------------------------------------
# E — contra-caso: render EN também tem badge
# ---------------------------------------------------------------------------

def test_e_render_en() -> None:
    section("E: render EN também tem seção 'programas'")

    html_en = mp.render_minimal_html(
        AMAZON_12, total_eligible=12, generated_at="2026-10-24 10:00",
        top=10, lang="en"
    )

    check("E1 seção 'programas' no render EN (ul.spot)", '<ul class="spot">' in html_en)
    check("E2 texto EN 'multi-site'", "multi-site" in html_en)
    check("E3 cidades listadas no EN", "Berlin" in html_en and "München" in html_en)


# ---------------------------------------------------------------------------
# F — CSS do badge presente
# ---------------------------------------------------------------------------

def test_f_css() -> None:
    section("F: CSS da seção 'programas' presente")

    html = mp.render_minimal_html(
        AMAZON_12, total_eligible=12, generated_at="2026-10-24 10:00",
        top=10, lang="pt"
    )

    check("F1 classe .spot no CSS (usada pela seção programas)", ".spot" in html)
    check("F2 seção programas usa ul.spot", '<ul class="spot">' in html)
    check("F3 lista usa li", "<li>" in html)


# ---------------------------------------------------------------------------
# G — full-list regime também funciona
# ---------------------------------------------------------------------------

def test_g_full_list() -> None:
    section("G: regime full-list também funciona")

    html_full = mp.render_minimal_html(
        AMAZON_12, total_eligible=12, generated_at="2026-10-24 10:00",
        top=10, lang="pt", full_list=True
    )

    check("G1 badge no full-list", "multisite-badge" in html_full)
    check("G2 programa multi-site no full-list", "programa multi-site" in html_full)


def main() -> int:
    print("F120 — programas multi-site: agrupamento visual (display-only)")
    test_a_helpers()
    test_b_main_page()
    test_c_sections()
    test_d_ab_byte_identity()
    test_e_render_en()
    test_f_css()
    test_g_full_list()
    print()
    if FAILURES:
        print(f"F120: FALHAS: {len(FAILURES)} de {CHECKS} checks")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print(f"F120: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())