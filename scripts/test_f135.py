#!/usr/bin/env python3
"""F135 — Twins cross-idioma/tenant no dedup: RWE, TI, BASF (offline fixtures).

Reproduz os 3 casos REAIS do relatório do dono (25-26/10):

1. RWE: variante DE (1449811933 d/w/m) reportada como NOVA em 25/10 quando
   a EN (1449811833 d/f/m) já tinha sido vista/aplicada em 24/10 — MESMO
   Anzeigencode 93871. normalize_title JÁ produz chave idêntica.

2. Texas Instruments: 25011485 duplicado no acervo — mesma vaga em dois sites
   oracle (site_number=CX#25011485 vs site_number=CX_1#25011485), URLs
   distintas → dedup por URL não funde.

3. BASF HR: re-postada com ID novo (1445672533 hoje vs 1445672433 ontem)
   → nova de novo no diff.

Este teste verifica que:
- cross_source_dedup funde os 3 casos intra-run (já funcionava)
- CrossSourceDedupStore detecta re-entradas cross-run (NOVO F135)
- new_postings_diff usa a MESMA chave dedup e não reporta re-entradas
- compute_cross_source_dedup_key produz chaves idênticas para os pares
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.cross_source_dedup import deduplicate_cross_source  # noqa: E402
from internship_finder.cross_source_dedup_store import (  # noqa: E402
    CrossSourceDedupStore,
    compute_cross_source_dedup_key,
)
from internship_finder.dedup import normalize_url  # noqa: E402
import ranking_digest  # noqa: E402

FAILS = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global FAILS
    tag = "[OK]" if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f" ({extra})" if extra and not cond else ""))
    if not cond:
        FAILS += 1


def section(title: str) -> None:
    print(f"\n== {title}")


# ---------------------------------------------------------------------------
# FIXTURES VERBATIM — 3 casos reais
# ---------------------------------------------------------------------------

# RWE: Anzeigencode 93871 — DE (d/w/m) vs EN (d/f/m)
RWE_DE = {
    "id": "RWE|sf_dataset:successfactors:1449811933",
    "source": "sf_dataset:successfactors",
    "external_id": "1449811933",
    "company": "RWE",
    "title": "Werkstudent (d/w/m) ArkonA D Offshore Operations Student Windfarm Working",
    "location": "Essen, Nordrhein-Westfalen, Deutschland",
    "country": "de",
    "url": "https://jobs.rwe.com/job/1449811933",
    "raw": {"anzeigencode": "93871", "requisition_id": "93871"},
}

RWE_EN = {
    "id": "RWE|successfactors:jobs:1449811833",
    "source": "successfactors:jobs",
    "external_id": "1449811833",
    "company": "RWE AG",
    "title": "Working Student (d/f/m) ArkonA D Offshore Operations Student Windfarm Working",
    "location": "Essen, North Rhine Westfalia, DE",
    "country": "de",
    "url": "https://jobs.rwe.com/job/1449811833",
    "raw": {"anzeigencode": "93871", "requisition_id": "93871"},
}

# Texas Instruments: mesmo external_id, Oracle CX vs CX_1
TI_CX = {
    "id": "Texas Instruments|oracle:https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX:25011485",
    "source": "oracle:https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX",
    "external_id": "25011485",
    "company": "Texas Instruments",
    "title": "Supply Chain Intern (m/f/d)",
    "location": "Freising, Bayern, Deutschland",
    "country": "de",
    "url": "https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/requisition/25011485",
}

TI_CX1 = {
    "id": "Texas Instruments|oracle:https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1:25011485",
    "source": "oracle:https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1",
    "external_id": "25011485",
    "company": "Texas Instruments",
    "title": "Supply Chain Intern (m/f/d)",
    "location": "Freising, Bavaria, DE",
    "country": "de",
    "url": "https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisition/25011485",
}

# BASF: re-postagem com ID novo
BASF_OLD = {
    "id": "BASF|successfactors:jobs:1445672433",
    "source": "successfactors:jobs",
    "external_id": "1445672433",
    "company": "BASF",
    "title": "Praktikant (m/w/d) Procurement",
    "location": "Ludwigshafen, Rheinland-Pfalz, Deutschland",
    "country": "de",
    "url": "https://jobs.basf.com/job/1445672433",
}

BASF_NEW = {
    "id": "BASF|sf_dataset:bundesagentur:1445672533",
    "source": "sf_dataset:bundesagentur",
    "external_id": "1445672533",
    "company": "BASF SE",
    "title": "Praktikant Procurement (alle Geschlechter)",
    "location": "Ludwigshafen, Rheinland-Pfalz, DE",
    "country": "de",
    "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/1445672533",
}


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

def test_compute_key_identity() -> None:
    section("F135.1 compute_cross_source_dedup_key: pares produzem chave IDÊNTICA")

    # RWE: Anzeigencode deve ser a chave
    key_rwe_de = compute_cross_source_dedup_key(RWE_DE)
    key_rwe_en = compute_cross_source_dedup_key(RWE_EN)
    check("RWE DE/EN: mesma chave via Anzeigencode", key_rwe_de == key_rwe_en,
          f"DE={key_rwe_de} EN={key_rwe_en}")
    check("RWE: chave usa prefixo anzeigencode", key_rwe_de.startswith("anzeigencode:"))

    # TI: Oracle site_number normalizado
    key_ti_cx = compute_cross_source_dedup_key(TI_CX)
    key_ti_cx1 = compute_cross_source_dedup_key(TI_CX1)
    check("TI CX/CX_1: mesma chave via oracle_site normalizado", key_ti_cx == key_ti_cx1,
          f"CX={key_ti_cx} CX1={key_ti_cx1}")
    check("TI: chave usa prefixo oracle_site", key_ti_cx.startswith("oracle_site:"))

    # BASF: company+title+city fallback
    key_basf_old = compute_cross_source_dedup_key(BASF_OLD)
    key_basf_new = compute_cross_source_dedup_key(BASF_NEW)
    check("BASF old/new: mesma chave via company_title_city", key_basf_old == key_basf_new,
          f"OLD={key_basf_old} NEW={key_basf_new}")
    check("BASF: chave usa prefixo company_title_city", key_basf_old.startswith("company_title_city:"))


def test_intra_run_dedup() -> None:
    section("F135.2 cross_source_dedup intra-run: 3 casos fundem (regressão F48)")

    # RWE
    out, stats, removed = deduplicate_cross_source([copy.deepcopy(RWE_DE), copy.deepcopy(RWE_EN)])
    check("RWE: funde para 1 vaga", len(out) == 1 and stats.get("cross_source_mirror") == 1,
          f"out={len(out)} stats={stats}")

    # TI
    out, stats, removed = deduplicate_cross_source([copy.deepcopy(TI_CX), copy.deepcopy(TI_CX1)])
    check("TI: funde para 1 vaga", len(out) == 1 and stats.get("cross_source_mirror") == 1,
          f"out={len(out)} stats={stats}")

    # BASF
    out, stats, removed = deduplicate_cross_source([copy.deepcopy(BASF_OLD), copy.deepcopy(BASF_NEW)])
    check("BASF: funde para 1 vaga", len(out) == 1 and stats.get("cross_source_mirror") == 1,
          f"out={len(out)} stats={stats}")


def test_cross_run_store() -> None:
    section("F135.3 CrossSourceDedupStore: detecta re-entradas cross-run")

    with tempfile.TemporaryDirectory(prefix="f135_store_") as tmp:
        store_path = Path(tmp) / "cross_source_dedup.db"
        run1 = "2026-10-24T09:00:00+00:00"
        run2 = "2026-10-25T09:00:00+00:00"

        # Run 1: vê RWE EN, TI CX, BASF OLD
        store1 = CrossSourceDedupStore(store_path, run1)
        assert store1._open()

        key_rwe_en = store1.compute_key(RWE_EN)
        key_ti_cx = store1.compute_key(TI_CX)
        key_basf_old = store1.compute_key(BASF_OLD)

        check("RWE EN key computed", bool(key_rwe_en))
        check("TI CX key computed", bool(key_ti_cx))
        check("BASF OLD key computed", bool(key_basf_old))

        store1.write(key_rwe_en, RWE_EN["id"])
        store1.write(key_ti_cx, TI_CX["id"])
        store1.write(key_basf_old, BASF_OLD["id"])
        store1.close()

        # Run 2: chega RWE DE, TI CX_1, BASF NEW — devem ser detectados como re-entradas
        store2 = CrossSourceDedupStore(store_path, run2)
        assert store2._open()

        check("RWE DE: has_key = True (re-entrada)", store2.has_key(store2.compute_key(RWE_DE)))
        check("TI CX_1: has_key = True (re-entrada)", store2.has_key(store2.compute_key(TI_CX1)))
        check("BASF NEW: has_key = True (re-entrada)", store2.has_key(store2.compute_key(BASF_NEW)))

        # Vaga genuinamente nova NÃO deve ter has_key
        new_job = {
            "id": "NewCo|sf_dataset:bundesagentur:999999",
            "source": "sf_dataset:bundesagentur",
            "external_id": "999999",
            "company": "NewCo GmbH",
            "title": "Praktikum Data Science (m/w/d)",
            "location": "Berlin, DE",
            "country": "de",
            "url": "https://example.com/999999",
        }
        check("Nova vaga: has_key = False", not store2.has_key(store2.compute_key(new_job)))

        store2.close()


def test_new_postings_diff() -> None:
    section("F135.4 new_postings_diff: usa chave dedup e NÃO reporta re-entradas")

    # Snapshot anterior (run 24/10): RWE EN, TI CX, BASF OLD
    previous = [copy.deepcopy(RWE_EN), copy.deepcopy(TI_CX), copy.deepcopy(BASF_OLD)]

    # Run atual (25/10): chegam RWE DE, TI CX_1, BASF NEW + 1 vaga genuinamente nova
    genuinely_new_job = {
        "id": "NewCo|sf_dataset:bundesagentur:999999",
        "source": "sf_dataset:bundesagentur",
        "external_id": "999999",
        "company": "NewCo GmbH",
        "title": "Praktikum Data Science (m/w/d)",
        "location": "Berlin, DE",
        "country": "de",
        "url": "https://example.com/999999",
    }
    current = [copy.deepcopy(RWE_DE), copy.deepcopy(TI_CX1), copy.deepcopy(BASF_NEW), genuinely_new_job]

    diff = ranking_digest.new_postings_diff(current, previous)
    check("diff não é None", diff is not None)
    if diff:
        check("new_ids tem 4 IDs", len(diff["new_ids"]) == 4)
        check("genuinely_new tem 1 vaga (NewCo)", len(diff["genuinely_new"]) == 1,
              f"genuinely_new={len(diff['genuinely_new'])}")
        check("re_seen tem 3 vagas (RWE, TI, BASF)", len(diff["re_seen"]) == 3,
              f"re_seen={len(diff['re_seen'])}")
        # A vaga genuinamente nova deve ser a NewCo
        if diff["genuinely_new"]:
            check("genuinely_new[0] é NewCo", diff["genuinely_new"][0]["id"] == genuinely_new_job["id"])


def test_dedup_with_store_integration() -> None:
    section("F135.5 Integração: deduplicate_cross_source com store marca re_entry")

    with tempfile.TemporaryDirectory(prefix="f135_integ_") as tmp:
        store_path = Path(tmp) / "cross_source_dedup.db"
        run1 = "2026-10-24T09:00:00+00:00"
        run2 = "2026-10-25T09:00:00+00:00"

        # Run 1: processa RWE EN, TI CX, BASF OLD
        store1 = CrossSourceDedupStore(store_path, run1)
        assert store1._open()
        out1, stats1, _ = deduplicate_cross_source(
            [copy.deepcopy(RWE_EN), copy.deepcopy(TI_CX), copy.deepcopy(BASF_OLD)],
            store=store1
        )
        check("Run 1: 3 vagas sobrevivem (sem pares cross-fonte no mesmo run)", len(out1) == 3)
        store1.close()

        # Run 2: processa RWE DE, TI CX_1, BASF NEW — devem ser marcados re_entry
        store2 = CrossSourceDedupStore(store_path, run2)
        assert store2._open()
        out2, stats2, _ = deduplicate_cross_source(
            [copy.deepcopy(RWE_DE), copy.deepcopy(TI_CX1), copy.deepcopy(BASF_NEW)],
            store=store2
        )
        # Todas 3 são re-entradas — não devem entrar no eligible (são filtradas pelo pipeline depois)
        # Mas o dedup intra-run ainda roda — se vierem no mesmo run, fundem entre si
        check("Run 2: 3 vagas marcadas re_entry",
              all(j.get("re_entry") for j in out2), f"re_entry flags: {[j.get('re_entry') for j in out2]}")
        store2.close()


def test_url_normalization_ti() -> None:
    section("F135.6 URL normalization: Oracle CX vs CX_1 são DIFERENTES (URL), mas MESMA chave dedup")

    url_cx = normalize_url(TI_CX["url"])
    url_cx1 = normalize_url(TI_CX1["url"])
    check("URLs normalizadas são DIFERENTES", url_cx != url_cx1)
    check("Mas chaves dedup são IGUAIS",
          compute_cross_source_dedup_key(TI_CX) == compute_cross_source_dedup_key(TI_CX1))


def main() -> int:
    test_compute_key_identity()
    test_intra_run_dedup()
    test_cross_run_store()
    test_new_postings_diff()
    test_dedup_with_store_integration()
    test_url_normalization_ti()

    print()
    if FAILS:
        print(f"FALHAS: {FAILS}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())