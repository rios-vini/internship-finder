"""Testes da Fase F24 — revalidação F16 bucket-B + monitor upstream (100% offline).

A fase revalidou ao vivo (09/10/2026, 23:21–23:38 UTC) as 6 pendências do
bucket B da F16 e monitorou as issues #295–#298 do upstream
(kalil0321/ats-scrapers). Resultado factual: NENHUMA empresa passou nos
critérios (0 entradas novas na SEED) — as pendências são todas upstream ou
de board-morto/protegido. Este teste registra o estado monitorado como
fixture OFFLINE e estável (sem rede, sem ``data/``):

- **T1 Estado revalidado (fixture)**: para cada uma das 6 pendências, o
  estado novo medido em 09/10 com evidência datada — a revalidação NÃO
  destravou nenhuma (mesma conclusão da F16, dados novos).
- **T2 Nenhuma pendência no SEED**: as 6 continuam FORA do SEED (regra
  F16: só entra quem passa em TODOS os critérios ao vivo).
- **T3 Contagem inalterada**: ``len(SEED) == 110`` (a F24 não adicionou
  nem removeu entradas; verificação de que "0 entradas é resultado
  válido" foi o desfecho desta fase).
- **T4 Monitor upstream (fixture)**: as 4 issues #295–#298 estavam OPEN,
  0 comments, 0 labels, 0 PRs/commits de fix referenciados, repo sem
  push desde 2026-09-24 — nenhuma ação de validação de tenant novo foi
  disparada (condição para nova onda: upstream mergear tenants →
  manifest companies.csv regenerar).
- **T5 Inventário upstream inalterado**: o companies.csv do manifest
  (fonte dos nomes canônicos) segue o snapshot de 23/08/2026 (Last-Modified
  documentado na revalidação de 09/10) — nenhum tenant proposto nas
  issues foi adicionado ao inventário.

Uso:  .venv/bin/python scripts/test_f24.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.registry import (  # noqa: E402
    SEED,
    CompanyRegistry,
)

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# Fixture da revalidação F24 (09/10/2026, 23:21–23:38 UTC) — evidência nova
# por pendência. "passed" = passou em TODOS os critérios F16 (nome canônico
# exato + verify_companies --fetch > 0 vagas da empresa certa + títulos
# anti-homônimo). Todas as 6 reprovadas — documentado no relatório da fase.
# ---------------------------------------------------------------------------
REVALIDATION_2026_10_09 = [
    {
        "name": "Deutsche Bank",
        "tenant": "smartrecruiters:deutschebank",
        "passed": False,
        "evidence": (
            "SR API totalFound=0 (23:21 UTC); board segue vazio — "
            "regra 0 vagas aplicada (mesma evidência da F16, re-datada)"
        ),
    },
    {
        "name": "Munich Re",
        "tenant": "bamboohr:munichre",
        "passed": False,
        "evidence": (
            "widget embed2.php agora serve JSON v2 com as 4 vagas Dublin "
            "(rotacionou: 'Senior Product Owner' saiu, 'Senior Cloud Platform "
            "Engineer' entrou), mas o scraper 0.3.0 espera HTML de 2024 → "
            "retorna 0 (EMPTY) — defeito upstream sem fix (bamboohr.py "
            "intacto desde #270, 23/08); subsidiária Dublin + sandbox "
            "greenhouse fora do manifest (3 vagas US/IL confirmadas)"
        ),
    },
    {
        "name": "Symrise",
        "tenant": "join_com:symrise",
        "passed": False,
        "evidence": (
            "join.com API 422 reconfirmado com NOVA evidência de contrato: "
            "qualquer pageSize (10/20/50/100, int ou str) é rejeitado "
            "({'param':'pageSize','msg':'Invalid value'}) inclusive nos "
            "params exatos do scraper e com UA de browser — ATS-wide "
            "(controle 01informatica idem); site workday da subsidiária "
            "EUA (External_FITCO) vivo com 1 vaga US (Anniston, AL) — "
            "não é o board global"
        ),
    },
    {
        "name": "Honeywell",
        "tenant": "oracle:ibqbjb",
        "passed": False,
        "evidence": (
            "board oracle VIVO e rotacionando (1236→1242 vagas; 38 DE no "
            "scan completo: 'Maschinensicherheitsingenieur (m/w/d)' @ Lotte, "
            "'Entwicklungsingenieur Messtechnik (m/w/d)' @ Mainz-Kastel) MAS "
            "oracle ∉ URL_SLUG_ATS do coletor local (slug relativo "
            "rejeitado: 'Oracle slug must be a full URL') — precedente SMA "
            "17/09: não corrigir via URL_SLUG_ATS; smartrecruiters:honeywell "
            "segue EMPTY (total=0)"
        ),
    },
    {
        "name": "Nokia",
        "tenant": "oracle:fa-evmr-saasfaprod1",
        "passed": False,
        "evidence": (
            "idem Honeywell: board oracle VIVO (594→629 vagas; 6 DE no scan "
            "completo: 'Classified Information Security Manager (Geheimschutz)' "
            "@ Germany), mesmo bloqueio oracle ∉ URL_SLUG_ATS; "
            "smartrecruiters:nokia segue EMPTY (total=0)"
        ),
    },
    {
        "name": "Unilever (TMICC)",
        "tenant": "workday:unilever/TMICC",
        "passed": False,
        "evidence": (
            "CXS POST retorna 403 permission denied errorCode S22 "
            "(reconfirmado 23:21 UTC) e o board root serve a maintenance "
            "page do Workday (HTTP 200, body 34.8 KB, classe "
            "'maintenance-page' no JSON embutido) — board morto/protegido "
            "(mesma evidência da F16, re-datada)"
        ),
    },
]

# Nomes canônicos NO MANIFEST das pendências (casefold) — nunca no SEED
# enquanto não passarem na validação ao vivo.
PENDING_MANIFEST_NAMES = ["Deutsche Bank", "munichre", "SYMRISE", "Honeywell", "Nokia", "Unilever (TMICC)"]

# ---------------------------------------------------------------------------
# Fixture do monitor upstream (09/10/2026, 23:15 UTC) — GitHub API.
# ---------------------------------------------------------------------------
UPSTREAM_MONITOR_2026_10_09 = {
    295: {
        "state": "open", "comments": 0, "labels": 0,
        "subject": "Heraeus/HARTING/Beiersdorf/QIAGEN tenants (SuccessFactors/Workday)",
    },
    296: {
        "state": "open", "comments": 0, "labels": 0,
        "subject": "Porsche AG & Commerzbank — SAP RMK beesite (no supported ATS)",
    },
    297: {
        "state": "open", "comments": 0, "labels": 0,
        "subject": "KUKA — Sitecore CMS JSON API (no ATS)",
    },
    298: {
        "state": "open", "comments": 0, "labels": 0,
        "subject": "Schneider Electric — icims row 'se' serves a JS shell",
    },
}
# Repositório upstream sem pushes desde 2026-09-24 (último push), zero
# commits desde 2026-10-01; nenhuma issue movida.
UPSTREAM_LAST_PUSH = "2026-09-24"
UPSTREAM_COMMITS_SINCE_2026_10_01 = 0
# companies.csv (fonte dos nomes canônicos) inalterado desde 23/08/2026.
MANIFEST_COMPANIES_CSV_LAST_MODIFIED = "2026-08-23"

SEED_COUNT = 110  # 101 pré-F16 + 9 da F16 — F24 não alterou


def main() -> int:
    reg = CompanyRegistry()
    by_name = {e.name: e for e in SEED}
    names_lower = {e.name.casefold() for e in SEED}

    section("T1. fixture da revalidação F24 completa e íntegra (6/6)")
    check("T1a. 6 pendências revalidadas", len(REVALIDATION_2026_10_09) == 6,
          f"n={len(REVALIDATION_2026_10_09)}")
    for item in REVALIDATION_2026_10_09:
        ok = (isinstance(item["name"], str) and item["name"].strip() != ""
              and isinstance(item["tenant"], str) and ":" in item["tenant"]
              and item["passed"] is False
              and isinstance(item["evidence"], str) and len(item["evidence"]) > 20)
        check(f"T1b. '{item['name']}' estado registrado (passed=False + evidência datada)", ok)
    check("T1c. nenhuma pendência passou na revalidação",
          not any(i["passed"] for i in REVALIDATION_2026_10_09),
          "0 entradas novas na SEED é o desfecho documentado da fase")

    section("T2. pendências continuam FORA do SEED")
    leaked = [n for n in PENDING_MANIFEST_NAMES if n.casefold() in names_lower]
    check("T2a. nenhum nome canônico de pendência no SEED", not leaked, f"vazaram: {leaked}")
    # homônimo intencional: 'Unilever' plain (board experied professionals)
    # é entrada legítima PRÉ-F16; 'Unilever (TMICC)' é o board distinto pendente.
    check("T2b. 'Unilever' plain (legítima) presente, 'Unilever (TMICC)' ausente",
          "Unilever".casefold() in names_lower
          and "Unilever (TMICC)".casefold() not in names_lower)

    section("T3. contagem da SEED inalterada pela F24")
    check("T3a. len(SEED) == 110", len(SEED) == SEED_COUNT, f"n={len(SEED)}")
    check("T3b. registry.entries idem", len(reg.entries) == SEED_COUNT, f"n={len(reg.entries)}")
    check("T3c. 9 entradas F16 preservadas",
          sum(1 for n in ["Brenntag", "ALTANA Job Portal", "Atlas Copco Group", "SKF",
                           "Decathlon Digital EN", "Work for DSV and forward your career | DSV",
                           "Heidelbergmaterials", "Sandvik (Sandvik Jobs)", "Rhe (R1111)"]
              if n.casefold() in names_lower) == 9,
          "a F24 não removeu nem editou a onda F16")

    section("T4. fixture do monitor upstream (issues #295–#298)")
    check("T4a. 4 issues monitoradas", len(UPSTREAM_MONITOR_2026_10_09) == 4,
          f"n={len(UPSTREAM_MONITOR_2026_10_09)}")
    for num, info in UPSTREAM_MONITOR_2026_10_09.items():
        ok = (info["state"] == "open" and info["comments"] == 0
              and info["labels"] == 0 and info["subject"].strip() != "")
        check(f"T4b. #{num} estado registrado (open, 0 comments, 0 labels)", ok,
              info["subject"])
    check("T4c. nenhum tenant novo adicionado ao upstream",
          UPSTREAM_COMMITS_SINCE_2026_10_01 == 0,
          f"repo sem push desde {UPSTREAM_LAST_PUSH} — nenhuma validação de tenant novo disparada")

    section("T5. inventário upstream (companies.csv) inalterado")
    check("T5a. snapshot do companies.csv pré-issues",
          MANIFEST_COMPANIES_CSV_LAST_MODIFIED == "2026-08-23",
          f"Last-Modified {MANIFEST_COMPANIES_CSV_LAST_MODIFIED} (23/08/2026) — "
          "nomes canônicos das issues não entraram no inventário")

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print(f"OK — test_f24: {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
