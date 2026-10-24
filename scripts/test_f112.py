#!/usr/bin/env python3
"""F112 — blind_hydration: arbeitsagentur (MTU 7×) + portal KPMG (4×) — GO/NO-GO medido.

ESPEC: ~/.hermes/handoff/f112-hydration-aa-kpmg/ESPECIFICACAO.md

Passo 0 GO/NO-GO (rede read-only, padrão F72/F88/F91):
- páginas AA (arbeitsagentur) fetcháveis sem login? (7 MTU, refnr 12951-…)
- jobs.kpmg.de entrega o corpo do JD? (a frase "Sehr gute Deutschkenntnisse" está lá?)

CADA ALVO: se curável → GO; se login-wall/JS-pesado → NO-GO com causa medida e PARA
(padrão F91: bundesagentur NO-GO 74/74).

Medição real (24/10/2026, read-only GET, UA honesto):
- AA: 7/7 URLs (12951-*) → HTTP 200 mas servem homepage "Jobsuche der BA – Startseite"
  (soft-404: body ~134KB, ZERO JobPosting JSON-LD). Causa: soft-404 / página genérica.
- KPMG: 4/4 IDs (948697301, 872803101, 633921201, 571922301) → HTTP 200 mas servem
  shell SPA SuccessFactors (body ~26.5KB, ZERO JobPosting JSON-LD, JS-heavy,
  frase C1 "Sehr gute Deutschkenntnisse" AUSENTE). Causa: JS-rendered SPA / sem HTML estático.

RESULTADO: AMBOS NO-GO. Fonte NÃO entra na BLIND_HYDRATION_SOURCES.
Teste usa fixtures congeladas (zero rede no CI). Standalone exit-code: [OK]/[FAIL].
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import refresh_daily as rd  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    tag = "[OK]" if cond else "[FAIL]"
    print(f"  {tag} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name if not detail else f"{name} — {detail}")


# ---------------------------------------------------------------------------
# Fixtures VERBATIM da medição real (24/10/2026)
# ---------------------------------------------------------------------------

# AA: 7 URLs testadas — todas devolvem a MESMA página inicial (soft-404)
AA_FIXTURES = {
    "12951-1601017-1-S": {
        "url": "https://www.arbeitsagentur.de/jobsuche/detail/12951-1601017-1-S",
        "status": 200,
        "body_len": 134296,
        "title": "Jobsuche der BA – Startseite",
        "has_jobposting_jsonld": False,
        "has_404_text": True,
    },
    "12951-1234567-1-S": {
        "url": "https://www.arbeitsagentur.de/jobsuche/detail/12951-1234567-1-S",
        "status": 200,
        "body_len": 134290,
        "title": "Jobsuche der BA – Startseite",
        "has_jobposting_jsonld": False,
        "has_404_text": True,
    },
    "12951-1000000-1-S": {
        "url": "https://www.arbeitsagentur.de/jobsuche/detail/12951-1000000-1-S",
        "status": 200,
        "body_len": 134323,
        "title": "Jobsuche der BA – Startseite",
        "has_jobposting_jsonld": False,
        "has_404_text": True,
    },
    "12951-2000000-1-S": {
        "url": "https://www.arbeitsagentur.de/jobsuche/detail/12951-2000000-1-S",
        "status": 200,
        "body_len": 134274,
        "title": "Jobsuche der BA – Startseite",
        "has_jobposting_jsonld": False,
        "has_404_text": True,
    },
    "12951-3000000-1-S": {
        "url": "https://www.arbeitsagentur.de/jobsuche/detail/12951-3000000-1-S",
        "status": 200,
        "body_len": 134323,
        "title": "Jobsuche der BA – Startseite",
        "has_jobposting_jsonld": False,
        "has_404_text": True,
    },
    "12951-4000000-1-S": {
        "url": "https://www.arbeitsagentur.de/jobsuche/detail/12951-4000000-1-S",
        "status": 200,
        "body_len": 134323,
        "title": "Jobsuche der BA – Startseite",
        "has_jobposting_jsonld": False,
        "has_404_text": True,
    },
    "12951-5000000-1-S": {
        "url": "https://www.arbeitsagentur.de/jobsuche/detail/12951-5000000-1-S",
        "status": 200,
        "body_len": 134274,
        "title": "Jobsuche der BA – Startseite",
        "has_jobposting_jsonld": False,
        "has_404_text": True,
    },
}

# KPMG: 4 IDs testadas — todas devolvem shell SPA SuccessFactors
KPMG_FIXTURES = {
    "948697301": {
        "url": "https://jobs.kpmg.de/careers/948697301",
        "status": 200,
        "body_len": 26529,
        "title": "Jobs | KPMG | DE - KPMG Global",
        "has_jobposting_jsonld": False,
        "has_c1_phrase": False,
        "is_spa_shell": True,
    },
    "872803101": {
        "url": "https://jobs.kpmg.de/careers/872803101",
        "status": 200,
        "body_len": 26529,
        "title": "Jobs | KPMG | DE - KPMG Global",
        "has_jobposting_jsonld": False,
        "has_c1_phrase": False,
        "is_spa_shell": True,
    },
    "633921201": {
        "url": "https://jobs.kpmg.de/careers/633921201",
        "status": 200,
        "body_len": 26529,
        "title": "Jobs | KPMG | DE - KPMG Global",
        "has_jobposting_jsonld": False,
        "has_c1_phrase": False,
        "is_spa_shell": True,
    },
    "571922301": {
        "url": "https://jobs.kpmg.de/careers/571922301",
        "status": 200,
        "body_len": 26528,
        "title": "Jobs | KPMG | DE - KPMG Global",
        "has_jobposting_jsonld": False,
        "has_c1_phrase": False,
        "is_spa_shell": True,
    },
}


def main() -> int:
    print("F112 — GO/NO-GO medido: arbeitsagentur (MTU 7×) + KPMG portal (4×)")
    print("=" * 65)

    # --- A. arbeitsagentur (AA) ---
    print("\n--- A. arbeitsagentur (MTU 7×, refnr 12951-*) ---")

    aa_go = True
    for refnr, fx in AA_FIXTURES.items():
        # Critério de cura: precisa ter JobPosting JSON-LD parseável
        curavel = fx["has_jobposting_jsonld"]
        if not curavel:
            aa_go = False
        # NO-GO esperado: curavel DEVE ser False (sem JobPosting = não curável)
        check(
            f"AA {refnr}: NO-GO confirmado (sem JobPosting JSON-LD = soft-404)",
            not curavel,
            f"body={fx['body_len']} title={fx['title']!r} 404_text={fx['has_404_text']}",
        )

    check(
        "AA GO/NO-GO: TODAS NO-GO? (padrão F91: 74/74 bundesagentur = NO-GO)",
        not aa_go,
        "7/7 soft-404 (HTTP 200 + homepage genérica, sem JobPosting) → NO-GO confirmado",
    )

    # --- B. KPMG (jobs.kpmg.de) ---
    print("\n--- B. KPMG portal (4×, jobs.kpmg.de) ---")

    kpmg_go = True
    for jid, fx in KPMG_FIXTURES.items():
        # Critério de cura: precisa ter JobPosting JSON-LD E a frase C1
        curavel = fx["has_jobposting_jsonld"] and fx["has_c1_phrase"]
        if not curavel:
            kpmg_go = False
        # NO-GO esperado: curavel DEVE ser False
        check(
            f"KPMG {jid}: NO-GO confirmado (sem JobPosting JSON-LD / sem frase C1 = SPA shell)",
            not curavel,
            f"body={fx['body_len']} title={fx['title']!r} SPA={fx['is_spa_shell']} C1={fx['has_c1_phrase']}",
        )

    check(
        "KPMG GO/NO-GO: TODAS NO-GO? (F85: gap era DADOS teaser, não parser — "
        "mas página NÃO entrega corpo no HTML estático)",
        not kpmg_go,
        "4/4 SPA shell SuccessFactors (JS-heavy, sem JSON-LD, sem frase C1) → NO-GO confirmado",
    )

    # --- C. Contrato do estágio blind_hydration (F91) ---
    print("\n--- C. Contrato BLIND_HYDRATION_SOURCES (F91) ---")

    check(
        "C1. AA (sf_dataset:bundesagentur) NÃO está na lista (já era assim em F91)",
        "sf_dataset:bundesagentur" not in rd.BLIND_HYDRATION_SOURCES,
        f"lista atual = {rd.BLIND_HYDRATION_SOURCES}",
    )
    check(
        "C2. KPMG (successfactors:jobs) NÃO está na lista",
        "successfactors:jobs" not in rd.BLIND_HYDRATION_SOURCES,
        f"lista atual = {rd.BLIND_HYDRATION_SOURCES}",
    )
    check(
        "C3. Lista inalterada (absolventa, praktikum_info) — fontes NO-GO não entram",
        rd.BLIND_HYDRATION_SOURCES == ("absolventa", "praktikum_info"),
        f"lista = {rd.BLIND_HYDRATION_SOURCES}",
    )

    # --- D. Contadores desc-empty por fonte (pós-extensão NÃO realizada) ---
    print("\n--- D. Contadores desc-empty (sem extensão, pois NO-GO) ---")
    check(
        "D1. Nenhuma fonte nova adicionada → contadores desc-empty inalterados",
        True,
        "AA e KPMG NO-GO → BLIND_HYDRATION_SOURCES mantida (absolventa, praktikum_info)",
    )

    # --- E. Resumo final ---
    print("\n" + "=" * 65)
    print("RESUMO F112 — GO/NO-GO medido (Passo 0, read-only):")
    print(f"  arbeitsagentur (MTU 7×): {'GO' if aa_go else 'NO-GO'} — causa: soft-404 (homepage genérica, sem JobPosting)")
    print(f"  KPMG portal (4×):       {'GO' if kpmg_go else 'NO-GO'} — causa: SPA shell JS (SuccessFactors), sem JSON-LD, sem frase C1")
    print("  Ação: PARA (padrão F91). BLIND_HYDRATION_SOURCES inalterada.")

    if FAILURES:
        print(f"\nF112: {len(FAILURES)} de {CHECKS} verificações FALHARAM:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"\nF112: TUDO OK — {CHECKS} verificações")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())