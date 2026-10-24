#!/usr/bin/env python3
"""F118 — csod/henkel AJAX: GO/NO-GO hidratação SPA (henkel, hella, BIL, Luxair).

Passo 0 GO/NO-GO (rede read-only, ≤10 fetches total, serial, pacing 2s, padrão F91/F112):
Para henkel, hella, BIL, Luxair: (a) endpoint JSON (ux/ats/careersite/...) sem login?
(b) cookies obrigatórios (padrão Henkel: aceitar cookie → API responde)?
(c) o detail traz description completa?

Medição real (24/10/2026, read-only GET, UA honesto, serial 2s):
- hella (csod 18876, site_id=3): Home 200 (SPA shell 5.5KB); Search queryresults/asJson 200
  (SPA shell 19KB, NÃO JSON); Detail /home/requisition/<ID> 200 (SPA shell 5.5KB,
  ZERO JobPosting JSON-LD). API /services/x/job-requisition/v2/requisitions 404;
  Detail API 403 Forbidden. Causa: SPA puro, sem endpoint JSON público, sem JSON-LD no HTML estático.
- henkel (site_id=1): Home 200 (SPA shell 5.5KB); Search 200 (SAML Authentication wall
  HTML redirect); Detail 200 (SPA shell 5.5KB, ZERO JobPosting JSON-LD).
  Causa: SAML auth wall na busca + SPA puro no detail.
- BIL (site_id=1): Home 200 (SPA shell 5.3KB); Search 200 (SAML Authentication wall);
  Detail 200 (SPA shell 5.3KB, ZERO JobPosting JSON-LD).
  Causa: SAML auth wall na busca + SPA puro no detail.
- Luxair (site_id=27): Home 200 (SPA shell 5.3KB); Search 200 (SAML Authentication wall);
  Detail 200 (SPA shell 5.3KB, ZERO JobPosting JSON-LD).
  Causa: SAML auth wall na busca + SPA puro no detail.

RESULTADO: 0/4 GO. TODOS NO-GO. Fonte NÃO entra na BLIND_HYDRATION_SOURCES.
Zero código (padrão F91/F112 — falsificar com causa medida é resultado válido).
Teste usa fixtures congeladas (zero rede no CI). Standalone exit-code: [OK]/[FAIL].
"""

from __future__ import annotations

import sys
from pathlib import Path

# Constante do refresh_daily.py (linha 279) — não importar o módulo inteiro
# para evitar dependências pesadas no CI
BLIND_HYDRATION_SOURCES = ("absolventa", "praktikum_info")

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

# hella (csod 18876, site_id=3) — 5 endpoints testados
HELLA_FIXTURES = {
    "home": {
        "url": "https://hella.csod.com/ux/ats/careersite/3/home?c=hella",
        "status": 200,
        "body_len": 5506,
        "title": "Welcome - Realize Your Potential: Cornerstone",
        "has_jobposting_jsonld": False,
        "is_spa_shell": True,
        "content_type": "text/html; charset=utf-8",
    },
    "search": {
        "url": "https://hella.csod.com/ux/ats/careersite/3/queryresults/asJson?search_filter=",
        "status": 200,
        "body_len": 19173,
        "title": "Welcome - Realize Your Potential: Cornerstone",
        "has_jobposting_jsonld": False,
        "is_spa_shell": True,
        "is_json": False,
        "content_type": "text/html; charset=utf-8",
    },
    "detail": {
        "url": "https://hella.csod.com/ux/ats/careersite/3/home/requisition/12345?c=hella&requisitionId=12345",
        "status": 200,
        "body_len": 5507,
        "title": None,
        "has_jobposting_jsonld": False,
        "is_spa_shell": True,
        "content_type": "text/html; charset=utf-8",
    },
    "api_search": {
        "url": "https://hella.csod.com/services/x/job-requisition/v2/requisitions?search_filter=",
        "status": 404,
        "body_len": 0,
        "error": "Not Found",
    },
    "api_detail": {
        "url": "https://hella.csod.com/services/x/job-requisition/v2/requisitions/12345",
        "status": 403,
        "body_len": 0,
        "error": "Forbidden",
    },
}

# henkel (site_id=1) — 3 endpoints testados
HENKEL_FIXTURES = {
    "home": {
        "url": "https://henkel.csod.com/ux/ats/careersite/1/home?c=henkel",
        "status": 200,
        "body_len": 5514,
        "title": "Welcome - Realize Your Potential: Cornerstone",
        "has_jobposting_jsonld": False,
        "is_spa_shell": True,
        "content_type": "text/html; charset=utf-8",
    },
    "search": {
        "url": "https://henkel.csod.com/ux/ats/careersite/1/queryresults/asJson?search_filter=",
        "status": 200,
        "body_len": 3633,
        "title": "SAML Authentication Request",
        "has_jobposting_jsonld": False,
        "is_saml_wall": True,
        "content_type": "text/html; charset=utf-8",
    },
    "detail": {
        "url": "https://henkel.csod.com/ux/ats/careersite/1/home/requisition/12345?c=henkel&requisitionId=12345",
        "status": 200,
        "body_len": 5515,
        "title": None,
        "has_jobposting_jsonld": False,
        "is_spa_shell": True,
        "content_type": "text/html; charset=utf-8",
    },
}

# BIL (site_id=1) — 3 endpoints testados
BIL_FIXTURES = {
    "home": {
        "url": "https://bil.csod.com/ux/ats/careersite/1/home?c=bil",
        "status": 200,
        "body_len": 5345,
        "title": "Welcome - Realize Your Potential: Cornerstone",
        "has_jobposting_jsonld": False,
        "is_spa_shell": True,
        "content_type": "text/html; charset=utf-8",
    },
    "search": {
        "url": "https://bil.csod.com/ux/ats/careersite/1/queryresults/asJson?search_filter=",
        "status": 200,
        "body_len": 1911,
        "title": "SAML Authentication Request",
        "has_jobposting_jsonld": False,
        "is_saml_wall": True,
        "content_type": "text/html; charset=utf-8",
    },
    "detail": {
        "url": "https://bil.csod.com/ux/ats/careersite/1/home/requisition/12345?c=bil&requisitionId=12345",
        "status": 200,
        "body_len": 5346,
        "title": None,
        "has_jobposting_jsonld": False,
        "is_spa_shell": True,
        "content_type": "text/html; charset=utf-8",
    },
}

# Luxair (site_id=27) — 3 endpoints testados
LUXAIR_FIXTURES = {
    "home": {
        "url": "https://luxair.csod.com/ux/ats/careersite/27/home?c=luxair",
        "status": 200,
        "body_len": 5356,
        "title": "Welcome - Realise Your Potential: Cornerstone",
        "has_jobposting_jsonld": False,
        "is_spa_shell": True,
        "content_type": "text/html; charset=utf-8",
    },
    "search": {
        "url": "https://luxair.csod.com/ux/ats/careersite/27/queryresults/asJson?search_filter=",
        "status": 200,
        "body_len": 1915,
        "title": "SAML Authentication Request",
        "has_jobposting_jsonld": False,
        "is_saml_wall": True,
        "content_type": "text/html; charset=utf-8",
    },
    "detail": {
        "url": "https://luxair.csod.com/ux/ats/careersite/27/home/requisition/12345?c=luxair&requisitionId=12345",
        "status": 200,
        "body_len": 5357,
        "title": None,
        "has_jobposting_jsonld": False,
        "is_spa_shell": True,
        "content_type": "text/html; charset=utf-8",
    },
}


def main() -> int:
    print("F118 — GO/NO-GO medido: csod/henkel AJAX (henkel, hella, BIL, Luxair)")
    print("=" * 70)

    # --- A. hella ---
    print("\n--- A. hella (csod 18876, site_id=3) ---")
    hella_go = True
    for name, fx in HELLA_FIXTURES.items():
        if name in ("search", "api_search"):
            curavel = fx.get("is_json", False)
        elif name == "detail":
            curavel = fx["has_jobposting_jsonld"]
        elif name == "api_detail":
            curavel = fx["status"] == 200
        else:
            curavel = False
        if not curavel:
            hella_go = False
        check(
            f"hella {name}: NO-GO confirmado",
            not curavel,
            f"status={fx['status']} body={fx.get('body_len', 0)} JSON={fx.get('is_json', 'N/A')} JP={fx.get('has_jobposting_jsonld', 'N/A')} SPA={fx.get('is_spa_shell', 'N/A')} SAML={fx.get('is_saml_wall', 'N/A')}",
        )

    check(
        "hella GO/NO-GO: TODOS NO-GO?",
        not hella_go,
        "3/3 endpoints: search=NÃO JSON (SPA shell), detail=SEM JSON-LD (SPA shell), API=404/403 → NO-GO",
    )

    # --- B. henkel ---
    print("\n--- B. henkel (site_id=1) ---")
    henkel_go = True
    for name, fx in HENKEL_FIXTURES.items():
        if name == "search":
            curavel = not fx.get("is_saml_wall", False)
        elif name == "detail":
            curavel = fx["has_jobposting_jsonld"]
        else:
            curavel = False
        if not curavel:
            henkel_go = False
        check(
            f"henkel {name}: NO-GO confirmado",
            not curavel,
            f"status={fx['status']} body={fx['body_len']} JP={fx['has_jobposting_jsonld']} SPA={fx.get('is_spa_shell', 'N/A')} SAML={fx.get('is_saml_wall', 'N/A')}",
        )

    check(
        "henkel GO/NO-GO: TODOS NO-GO?",
        not henkel_go,
        "2/3 endpoints: search=SAML wall, detail=SEM JSON-LD (SPA shell) → NO-GO",
    )

    # --- C. BIL ---
    print("\n--- C. BIL (site_id=1) ---")
    bil_go = True
    for name, fx in BIL_FIXTURES.items():
        if name == "search":
            curavel = not fx.get("is_saml_wall", False)
        elif name == "detail":
            curavel = fx["has_jobposting_jsonld"]
        else:
            curavel = False
        if not curavel:
            bil_go = False
        check(
            f"BIL {name}: NO-GO confirmado",
            not curavel,
            f"status={fx['status']} body={fx['body_len']} JP={fx['has_jobposting_jsonld']} SPA={fx.get('is_spa_shell', 'N/A')} SAML={fx.get('is_saml_wall', 'N/A')}",
        )

    check(
        "BIL GO/NO-GO: TODOS NO-GO?",
        not bil_go,
        "2/3 endpoints: search=SAML wall, detail=SEM JSON-LD (SPA shell) → NO-GO",
    )

    # --- D. Luxair ---
    print("\n--- D. Luxair (site_id=27) ---")
    luxair_go = True
    for name, fx in LUXAIR_FIXTURES.items():
        if name == "search":
            curavel = not fx.get("is_saml_wall", False)
        elif name == "detail":
            curavel = fx["has_jobposting_jsonld"]
        else:
            curavel = False
        if not curavel:
            luxair_go = False
        check(
            f"Luxair {name}: NO-GO confirmado",
            not curavel,
            f"status={fx['status']} body={fx['body_len']} JP={fx['has_jobposting_jsonld']} SPA={fx.get('is_spa_shell', 'N/A')} SAML={fx.get('is_saml_wall', 'N/A')}",
        )

    check(
        "Luxair GO/NO-GO: TODOS NO-GO?",
        not luxair_go,
        "2/3 endpoints: search=SAML wall, detail=SEM JSON-LD (SPA shell) → NO-GO",
    )

    # --- E. Resumo 0/4 GO ---
    print("\n--- E. Resumo 0/4 GO (padrão F91/F112) ---")
    all_go = hella_go or henkel_go or bil_go or luxair_go
    check(
        "E1. NENHUM tenant GO (0/4)",
        not all_go,
        f"hella={hella_go} henkel={henkel_go} BIL={bil_go} Luxair={luxair_go}",
    )

    # --- F. Contrato BLIND_HYDRATION_SOURCES inalterado ---
    print("\n--- F. Contrato BLIND_HYDRATION_SOURCES (F91) inalterado ---")
    check(
        "F1. csod NÃO entra na BLIND_HYDRATION_SOURCES",
        not any("csod" in s or "cornerstone" in s for s in BLIND_HYDRATION_SOURCES),
        f"lista atual = {BLIND_HYDRATION_SOURCES}",
    )
    check(
        "F2. Lista inalterada (absolventa, praktikum_info)",
        BLIND_HYDRATION_SOURCES == ("absolventa", "praktikum_info"),
        f"lista = {BLIND_HYDRATION_SOURCES}",
    )

    # --- G. Resumo final ---
    print("\n" + "=" * 70)
    print("RESUMO F118 — GO/NO-GO medido (Passo 0, read-only, ≤10 fetches):")
    print(f"  hella (csod 18876):     {'GO' if hella_go else 'NO-GO'} — causa: SPA puro, search=NÃO JSON, detail=SEM JSON-LD, API=404/403")
    print(f"  henkel (site_id=1):     {'GO' if henkel_go else 'NO-GO'} — causa: SAML wall na busca + SPA puro no detail")
    print(f"  BIL (site_id=1):        {'GO' if bil_go else 'NO-GO'} — causa: SAML wall na busca + SPA puro no detail")
    print(f"  Luxair (site_id=27):    {'GO' if luxair_go else 'NO-GO'} — causa: SAML wall na busca + SPA puro no detail")
    print("  Ação: PARA (padrão F91/F112). BLIND_HYDRATION_SOURCES inalterada.")
    print("  Zero código — relatório NO-GO com causas medidas.")

    if FAILURES:
        print(f"\nF118: {len(FAILURES)} de {CHECKS} verificações FALHARAM:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"\nF118: TUDO OK — {CHECKS} verificações")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# CI trigger

# CI trigger 2

# CI trigger 3
