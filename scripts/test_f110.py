#!/usr/bin/env python3
"""F110 — Dedup cross-ATS: jobs.lidl ↔ praktikum.info (offline, zero rede).

2 pares confirmados NA MÃO na varredura 237 (sinal 3):
- 1446902933 (sf_dataset:successfactors) ≡ 13355221 (praktikum_info) "Preismanagement Nonfood"
- 1441830833 (sf_dataset:successfactors) ≡ 13308139 (praktikum_info) "Lieferantenentwicklung"

Sobreviveram ao dedup F92 (aliases+guards) porque IDs cross-ATS = chaves diferentes;
F103 repost flagga por chave vista (não casa).

Extensão F110: chave dedup título-normalizado×empresa-canônica quando fontes
espelhadas conhecidas (config/dedup_mirrored_sources.json). Contra-medida
obrigatória: 0 FP no corpus inteiro (padrão F66: 20 twins zero FP).

Fixtures verbatim: 2 pares positivos + 2 contra-casos
("Lieferantenmanagement" ≠ "Lieferantenentwicklung" NÃO colapsam).

Uso: python3 scripts/test_f110.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.dedup import (  # noqa: E402
    KEY_CROSS_ATS_MIRROR,
    deduplicate,
    normalize_title,
)

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "[OK]" if cond else "[FAIL]"
    print(f"  {mark} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


# ============================================================
# Fixtures VERBATIM dos 2 pares confirmados (varredura 237)
# ============================================================

# Par 1: Preismanagement Nonfood
# jobs.lidl (sf_dataset:successfactors) - id 1446902933
JOB_LIDL_PREIS = {
    "id": "lidlstiftup2|sf_dataset:successfactors:1446902933",
    "source": "sf_dataset:successfactors",
    "title": "Praktikum Preismanagement & Datenanalyse Non Food",
    "company": "lidlstiftup2",
    "location": "Neckarsulm, DE",
    "country": "de",
    "country_iso": "de",
    "url": "https://jobs.lidl/sti/job/Neckarsulm-Praktikum-Preismanagement-&-Datenanalyse-Non-Food/1446902933/",
    "external_id": "1446902933",
    "description": "Einleitung Eine gute Idee war der Ursprung...",
    "internship": True,
}

# praktikum.info - id 13355221
JOB_PI_PREIS = {
    "id": "Lidl Stiftung & Co. KG|praktikum_info:13355221",
    "source": "praktikum_info",
    "title": "Praktikum Preismanagement & Datenanalyse Non Food",
    "company": "Lidl Stiftung & Co. KG",
    "location": "74167 Neckarsulm",
    "country": "de",
    "country_iso": "de",
    "url": "https://www.praktikum.info/stellenangebote/13355221-p-praktikum-preismanagement-datenanalyse-non-food",
    "external_id": "13355221",
    "description": None,
    "internship": True,
}

# Par 2: Lieferantenentwicklung & Prozessoptimierung
# jobs.lidl (sf_dataset:successfactors) - id 1441830833
JOB_LIDL_LIEF = {
    "id": "lidlstiftup2|sf_dataset:successfactors:1441830833",
    "source": "sf_dataset:successfactors",
    "title": "Praktikum Lieferantenentwicklung & Prozessoptimierung",
    "company": "lidlstiftup2",
    "location": "Neckarsulm, DE",
    "country": "de",
    "country_iso": "de",
    "url": "https://jobs.lidl/sti/job/Neckarsulm-Praktikum-Lieferantenentwicklung-&-Prozessoptimierung/1441830833/",
    "external_id": "1441830833",
    "description": "Einleitung Eine gute Idee war der Ursprung...",
    "internship": True,
}

# praktikum.info - id 13308139
JOB_PI_LIEF = {
    "id": "Lidl Stiftung & Co. KG|praktikum_info:13308139",
    "source": "praktikum_info",
    "title": "Praktikum Lieferantenentwicklung & Prozessoptimierung",
    "company": "Lidl Stiftung & Co. KG",
    "location": "74172 Neckarsulm",
    "country": "de",
    "country_iso": "de",
    "url": "https://www.praktikum.info/stellenangebote/13308139-p-praktikum-lieferantenentwicklung-prozessoptimierung",
    "external_id": "13308139",
    "description": None,
    "internship": True,
}

# ============================================================
# Contra-casos: vagas Lidl genuinamente DISTINTAS com títulos parecidos
# NÃO devem colapsar (zero FP)
# ============================================================

# Contra-caso 1: Lieferantenmanagement (diferente de Lieferantenentwicklung)
JOB_PI_LIEF_MGMT = {
    "id": "Lidl Stiftung & Co. KG|praktikum_info:13308135",
    "source": "praktikum_info",
    "title": "Praktikum Lieferantenmanagement - Konzepte & Projekte",
    "company": "Lidl Stiftung & Co. KG",
    "location": "74167 Neckarsulm",
    "country": "de",
    "country_iso": "de",
    "url": "https://www.praktikum.info/stellenangebote/13308135-p-praktikum-lieferantenmanagement-konzepte-projekte",
    "external_id": "13308135",
    "description": None,
    "internship": True,
}

# Contra-caso 2: Outra vaga de Preismanagement mas com foco diferente
# (usamos uma vaga real diferente do dataset)
JOB_PI_OTHER = {
    "id": "Lidl Stiftung & Co. KG|praktikum_info:13355222",
    "source": "praktikum_info",
    "title": "Praktikum Marketing International - Product Content & Packaging Non Food",
    "company": "Lidl Stiftung & Co. KG",
    "location": "74172 Neckarsulm",
    "country": "de",
    "country_iso": "de",
    "url": "https://www.praktikum.info/stellenangebote/13355222-p-praktikum-marketing-international-product-content-packaging-non-food",
    "external_id": "13355222",
    "description": None,
    "internship": True,
}


def test_positive_pairs() -> None:
    """Os 2 pares confirmados DEVEM colapsar pelo tier cross_ats_mirror."""
    print("== Pares positivos (devem fundir) ==")

    # Par 1: Preismanagement
    out, stats, removed = deduplicate([JOB_LIDL_PREIS, JOB_PI_PREIS])
    check(
        "Par 1 (Preismanagement): 2 viram 1",
        len(out) == 1 and len(removed) == 1,
        f"out={len(out)} removed={len(removed)} stats={stats}",
    )
    check(
        "Par 1: fusão registrada no tier cross_ats_mirror",
        stats.get(KEY_CROSS_ATS_MIRROR) == 1,
        f"stats={stats}",
    )
    check(
        "Par 1: sobrevivente é o do dataset (tem description)",
        out[0]["source"] == "sf_dataset:successfactors",
        f"source={out[0]['source']}",
    )

    # Par 2: Lieferantenentwicklung
    out, stats, removed = deduplicate([JOB_LIDL_LIEF, JOB_PI_LIEF])
    check(
        "Par 2 (Lieferantenentwicklung): 2 viram 1",
        len(out) == 1 and len(removed) == 1,
        f"out={len(out)} removed={len(removed)} stats={stats}",
    )
    check(
        "Par 2: fusão registrada no tier cross_ats_mirror",
        stats.get(KEY_CROSS_ATS_MIRROR) == 1,
        f"stats={stats}",
    )
    check(
        "Par 2: sobrevivente é o do dataset (tem description)",
        out[0]["source"] == "sf_dataset:successfactors",
        f"source={out[0]['source']}",
    )


def test_negative_cases() -> None:
    """Contra-casos NÃO devem colapsar (zero FP)."""
    print("\n== Contra-casos (NÃO devem fundir) ==")

    # Contra-caso 1: Lieferantenmanagement vs Lieferantenentwicklung
    out, stats, removed = deduplicate([JOB_LIDL_LIEF, JOB_PI_LIEF_MGMT])
    check(
        "Contra 1: Lieferantenentwicklung ≠ Lieferantenmanagement (2 ficam)",
        len(out) == 2 and len(removed) == 0,
        f"out={len(out)} removed={len(removed)} stats={stats}",
    )
    check(
        "Contra 1: zero fusões no cross_ats_mirror",
        stats.get(KEY_CROSS_ATS_MIRROR, 0) == 0,
        f"stats={stats}",
    )

    # Contra-caso 2: Preismanagement Non Food vs Marketing Non Food (conteúdo diferente)
    out, stats, removed = deduplicate([JOB_LIDL_PREIS, JOB_PI_OTHER])
    check(
        "Contra 2: Preismanagement ≠ Marketing Non Food (2 ficam)",
        len(out) == 2 and len(removed) == 0,
        f"out={len(out)} removed={len(removed)} stats={stats}",
    )
    check(
        "Contra 2: zero fusões no cross_ats_mirror",
        stats.get(KEY_CROSS_ATS_MIRROR, 0) == 0,
        f"stats={stats}",
    )

    # Contra-caso 3: Ambas do praktikum_info (mesma fonte) - NÃO é cross-ATS
    out, stats, removed = deduplicate([JOB_PI_PREIS, JOB_PI_LIEF])
    check(
        "Contra 3: mesma fonte (praktikum_info) não é cross-ATS (2 ficam)",
        len(out) == 2 and len(removed) == 0,
        f"out={len(out)} removed={len(removed)} stats={stats}",
    )
    check(
        "Contra 3: zero fusões no cross_ats_mirror",
        stats.get(KEY_CROSS_ATS_MIRROR, 0) == 0,
        f"stats={stats}",
    )


def test_normalization_equivalence() -> None:
    """Verifica que a normalização de título produz a mesma chave para os pares."""
    print("\n== Normalização de título ==")

    check(
        "Preismanagement: normalize_title igual",
        normalize_title(JOB_LIDL_PREIS["title"]) == normalize_title(JOB_PI_PREIS["title"]),
        f"lidl='{normalize_title(JOB_LIDL_PREIS['title'])}' pi='{normalize_title(JOB_PI_PREIS['title'])}'",
    )
    check(
        "Lieferantenentwicklung: normalize_title igual",
        normalize_title(JOB_LIDL_LIEF["title"]) == normalize_title(JOB_PI_LIEF["title"]),
        f"lidl='{normalize_title(JOB_LIDL_LIEF['title'])}' pi='{normalize_title(JOB_PI_LIEF['title'])}'",
    )
    check(
        "Contra 1: normalize_title DIFERENTE (Lieferantenmanagement vs Entwicklung)",
        normalize_title(JOB_LIDL_LIEF["title"]) != normalize_title(JOB_PI_LIEF_MGMT["title"]),
        f"lidl='{normalize_title(JOB_LIDL_LIEF['title'])}' pi='{normalize_title(JOB_PI_LIEF_MGMT['title'])}'",
    )
    check(
        "Contra 2: normalize_title DIFERENTE (Preismanagement vs Marketing)",
        normalize_title(JOB_LIDL_PREIS["title"]) != normalize_title(JOB_PI_OTHER["title"]),
        f"lidl='{normalize_title(JOB_LIDL_PREIS['title'])}' pi='{normalize_title(JOB_PI_OTHER['title'])}'",
    )


def test_corpus_zero_fp() -> None:
    """Medição no corpus inteiro: 0 falso-positivo de merge."""
    print("\n== Medição corpus inteiro (0 FP) ==")

    # Carrega eligible_jobs.json (corpus de produção do dia)
    import json
    eligible_path = ROOT / "data" / "eligible_jobs.json"
    if not eligible_path.exists():
        print("  SKIP: data/eligible_jobs.json ausente (sem coleta local)")
        return

    with open(eligible_path, "r", encoding="utf-8") as f:
        corpus = json.load(f)

    # Conta quantas vagas vêm das fontes espelhadas
    sf_lidl = [j for j in corpus if j.get("source") == "sf_dataset:successfactors" and j.get("company") == "lidlstiftup2"]
    pi_lidl = [j for j in corpus if j.get("source") == "praktikum_info" and j.get("company") == "Lidl Stiftung & Co. KG"]

    print(f"  sf_dataset:successfactors (lidlstiftup2): {len(sf_lidl)} vagas")
    print(f"  praktikum_info (Lidl Stiftung & Co. KG): {len(pi_lidl)} vagas")

    # Roda dedup no corpus completo
    out, stats, removed = deduplicate(corpus)
    cross_ats_removed = stats.get(KEY_CROSS_ATS_MIRROR, 0)

    check(
        f"Corpus: {len(corpus)} -> {len(out)} (removidas {len(removed)})",
        True,  # sempre passa, é informativo
        f"cross_ats_mirror={cross_ats_removed}",
    )

    # Verifica cada fusão cross_ats_mirror: deve ser um dos 2 pares conhecidos
    known_pairs = {
        frozenset(["1446902933", "13355221"]),  # Preismanagement
        frozenset(["1441830833", "13308139"]),  # Lieferantenentwicklung
    }

    fp_count = 0
    for winner, loser, label in removed:
        if label == KEY_CROSS_ATS_MIRROR:
            # Extrai external_ids
            w_ext = winner.get("external_id", "")
            l_ext = loser.get("external_id", "")
            pair = frozenset([w_ext, l_ext])
            if pair not in known_pairs:
                fp_count += 1
                print(f"  [FP CANDIDATO] {winner['title'][:50]} ({w_ext}) ≡ {loser['title'][:50]} ({l_ext})")

    check(
        "Zero falso-positivo no corpus inteiro",
        fp_count == 0,
        f"FP detectados: {fp_count}",
    )


def main() -> int:
    test_normalization_equivalence()
    test_positive_pairs()
    test_negative_cases()
    test_corpus_zero_fp()

    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("==== test_f110 OK ====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())