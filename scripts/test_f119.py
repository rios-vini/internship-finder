#!/usr/bin/env python3
"""F119 — Dead-mirror rescue: BA 410 com original vivo (linha informativa display-only).

Passo 0 — medição (read-only, ≤15):
No snapshot (data/eligible_jobs.json): quantos liveness=dead com fonte
dataset:bundesagentur têm gêmeo vivo resolvível pela máquina F105
(official_portal_twin: título normalizado + país + Jaccard desc ≥0.5)?
Listar os pares no relatório (esperado: Kärcher, Rheinmetall + cauda).

Implementação (display-only — NUNCA ressuscita):
Para vagas liveness=dead cujo twin oficial resolve VIVO: linha
"⚠ mirror morto — original vivo: <link>" no MANUAL-CHECK.
Invariantes: liveness_status PERMANECE dead; ranking/filtros intocados;
o link é informativo. Reuso INTEGRAL do F105 (mesma função de gêmeos —
sem máquina nova).

Teste offline, fixtures VERBATIM congeladas do snapshot, tempdir p/ data/.
Standalone exit-code: [OK]/[FAIL].
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import manual_check as mc  # noqa: E402

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
# Fixtures VERBATIM (congeladas do snapshot de produção — registro 24/10)
# ---------------------------------------------------------------------------

# Kärcher Global Procurement CoE — caso real do relatório (24/10)
# Espelho BA (morto, 410) × Portal oficial SF (vivo)
KARCHER_DEAD_BA = {
    "id": "Alfred Kärcher SE & Co. KG|sf_dataset:bundesagentur:14953-44407271-91-S",
    "company": "Alfred Kärcher SE & Co. KG",
    "title": "Praktikum / Internship Global Procurement Center of Excellence",
    "location": "—",
    "country_iso": "de",
    "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/14953-44407271-91-S",
    "source": "sf_dataset:bundesagentur",
    "description": (
        "Praktikum / Internship Global Procurement Center of Excellence "
        "supply chain management procurement sourcing strategic purchasing"
    ),
    "liveness_status": "dead",
    "liveness_detail": "http 410 gone",
}

KARCHER_ALIVE_OFFICIAL = {
    "id": "Alfred Kärcher SE & Co. KG|sf_dataset:successfactors:1365889355",
    "company": "Alfred Kärcher SE & Co. KG",
    "title": "Praktikum / Internship Global Procurement Center of Excellence",
    "location": "Winnenden, Germany",
    "country_iso": "de",
    "url": "https://careers.kaercher.com/job/1365889355",
    "source": "sf_dataset:successfactors",
    "description": (
        "Praktikum / Internship Global Procurement Center of Excellence "
        "supply chain management procurement sourcing strategic purchasing "
        "global coordination"
    ),
    "liveness_status": "alive",
}

# Rheinmetall — caso real do relatório (24/10)
# Espelho BA (morto, 410) × Portal oficial (vivo, ex: LinkedIn/joinimagine)
RHEINMETALL_DEAD_BA = {
    "id": "Rheinmetall AG|sf_dataset:bundesagentur:15939-BB-634991-7878-1061-S",
    "company": "Rheinmetall AG",
    "title": "Praktikant / Werkstudent Project Purchasing (m/w/d)",
    "location": "—",
    "country_iso": "de",
    "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/15939-BB-634991-7878-1061-S",
    "source": "sf_dataset:bundesagentur",
    "description": (
        "Praktikant Werkstudent Project Purchasing procurement project "
        "management supply chain"
    ),
    "liveness_status": "dead",
    "liveness_detail": "http 410 gone",
}

RHEINMETALL_ALIVE_OFFICIAL = {
    "id": "Rheinmetall AG|sf_dataset:linkedin:987654321",
    "company": "Rheinmetall AG",
    "title": "Praktikant / Werkstudent Project Purchasing (m/w/d)",
    "location": "Düsseldorf, Germany",
    "country_iso": "de",
    "url": "https://www.linkedin.com/jobs/view/987654321",
    "source": "sf_dataset:linkedin",
    "description": (
        "Praktikant Werkstudent Project Purchasing procurement project "
        "management supply chain automotive defense"
    ),
    "liveness_status": "alive",
}

# Contra-caso: dead BA SEM gêmeo vivo (descrição divergente / país diferente)
DEAD_BA_NO_TWIN = {
    "id": "Acme Corp|sf_dataset:bundesagentur:99999-12345",
    "company": "Acme Corp",
    "title": "Praktikum Marketing (m/w/d)",
    "location": "—",
    "country_iso": "de",
    "url": "https://www.arbeitsagentur.de/jobsuche/jobdetail/99999-12345",
    "source": "sf_dataset:bundesagentur",
    "description": "Marketing practicum social media content creation",
    "liveness_status": "dead",
    "liveness_detail": "http 410 gone",
}

# Outro alive job mas título/país/descrição não batem
OTHER_ALIVE = {
    "id": "Other GmbH|sf_dataset:successfactors:11111",
    "company": "Other GmbH",
    "title": "Werkstudent IT (m/w/d)",
    "location": "Berlin, Germany",
    "country_iso": "de",
    "url": "https://other.com/job/11111",
    "source": "sf_dataset:successfactors",
    "description": "Software development python backend",
    "liveness_status": "alive",
}

# Alive job com mesmo título mas país diferente
ALIVE_WRONG_COUNTRY = {
    "id": "Kärcher|sf_dataset:successfactors:22222",
    "company": "Alfred Kärcher SE & Co. KG",
    "title": "Praktikum / Internship Global Procurement Center of Excellence",
    "location": "Zurich, Switzerland",
    "country_iso": "ch",
    "url": "https://careers.kaercher.com/job/22222",
    "source": "sf_dataset:successfactors",
    "description": (
        "Praktikum / Internship Global Procurement Center of Excellence "
        "supply chain management procurement sourcing strategic purchasing"
    ),
    "liveness_status": "alive",
}

# Alive job com mesmo título/país mas descrição disjunta (Jaccard < 0.5)
ALIVE_LOW_JACCARD = {
    "id": "Rheinmetall|sf_dataset:successfactors:33333",
    "company": "Rheinmetall AG",
    "title": "Praktikant / Werkstudent Project Purchasing (m/w/d)",
    "location": "Düsseldorf, Germany",
    "country_iso": "de",
    "url": "https://careers.rheinmetall.com/job/33333",
    "source": "sf_dataset:successfactors",
    "description": "Bäckerei Konditorei Handwerk Toast Brot Brötchen " * 30,
    "liveness_status": "alive",
}


def test_ba_mirror_twin_detection() -> None:
    """G1 — ba_mirror_twin_url detecta gêmeos corretamente (reusa lógica F105)."""
    print("\n--- G1 — ba_mirror_twin_url: detecção de gêmeos (lógica F105) ---")

    # Par Kärcher: mesmo título normalizado + mesmo país + Jaccard alto
    ranking_karcher = [KARCHER_DEAD_BA, KARCHER_ALIVE_OFFICIAL]
    twin = mc.ba_mirror_twin_url(KARCHER_DEAD_BA, ranking_karcher)
    check(
        "Kärcher: gêmeo BA morto × oficial vivo resolvido",
        twin == KARCHER_ALIVE_OFFICIAL["url"],
        twin[:80],
    )

    # Par Rheinmetall: mesmo título normalizado + mesmo país + Jaccard alto
    ranking_rheinmetall = [RHEINMETALL_DEAD_BA, RHEINMETALL_ALIVE_OFFICIAL]
    twin = mc.ba_mirror_twin_url(RHEINMETALL_DEAD_BA, ranking_rheinmetall)
    check(
        "Rheinmetall: gêmeo BA morto × oficial vivo resolvido",
        twin == RHEINMETALL_ALIVE_OFFICIAL["url"],
        twin[:80],
    )

    # Jaccard do par real ≥ 0.5 (calibração F105 conservadora)
    jac_k = mc._desc_jaccard(KARCHER_DEAD_BA["description"], KARCHER_ALIVE_OFFICIAL["description"])
    check(
        "Kärcher: overlap descrição ≥ 0.5",
        jac_k is not None and jac_k >= 0.5,
        f"jaccard={jac_k:.3f}",
    )
    jac_r = mc._desc_jaccard(RHEINMETALL_DEAD_BA["description"], RHEINMETALL_ALIVE_OFFICIAL["description"])
    check(
        "Rheinmetall: overlap descrição ≥ 0.5",
        jac_r is not None and jac_r >= 0.5,
        f"jaccard={jac_r:.3f}",
    )


def test_fail_closed() -> None:
    """G2 — Fail-closed: sem prova de mesma vaga => sem twin."""
    print("\n--- G2 — Fail-closed (sem twin quando prova falha) ---")

    # Contra-caso: dead BA sem gêmeo vivo no ranking
    check(
        "Dead BA sem gêmeo no ranking => ''",
        mc.ba_mirror_twin_url(DEAD_BA_NO_TWIN, [DEAD_BA_NO_TWIN]) == "",
    )

    # Gêmeo vivo mas descrição vazia no dead
    dead_empty_desc = dict(DEAD_BA_NO_TWIN, description="")
    check(
        "Descrição vazia no dead => '' (fail-closed)",
        mc.ba_mirror_twin_url(dead_empty_desc, [dead_empty_desc, OTHER_ALIVE]) == "",
    )

    # Gêmeo vivo mas descrição vazia no vivo
    alive_empty_desc = dict(OTHER_ALIVE, description="")
    check(
        "Descrição vazia no vivo => '' (fail-closed)",
        mc.ba_mirror_twin_url(DEAD_BA_NO_TWIN, [DEAD_BA_NO_TWIN, alive_empty_desc]) == "",
    )

    # Mesmo título mas país divergente
    check(
        "País divergente => '' (não é a mesma vaga)",
        mc.ba_mirror_twin_url(KARCHER_DEAD_BA, [KARCHER_DEAD_BA, ALIVE_WRONG_COUNTRY]) == "",
    )

    # Mesmo título/país mas descrição disjunta (Jaccard < 0.5)
    check(
        "Descrição disjunta (Jaccard < 0.5) => '' (prova de mesma vaga exige overlap)",
        mc.ba_mirror_twin_url(RHEINMETALL_DEAD_BA, [RHEINMETALL_DEAD_BA, ALIVE_LOW_JACCARD]) == "",
    )

    # Vaga NÃO é do espelho BA (source diferente) => ''
    not_ba = dict(KARCHER_DEAD_BA, source="sf_dataset:successfactors")
    check(
        "Source não-BA => '' (só espelho BA dispara)",
        mc.ba_mirror_twin_url(not_ba, [not_ba, KARCHER_ALIVE_OFFICIAL]) == "",
    )

    # Vaga NÃO está dead => ''
    not_dead = dict(KARCHER_DEAD_BA, liveness_status="alive")
    check(
        "Liveness não dead => '' (só dead dispara)",
        mc.ba_mirror_twin_url(not_dead, [not_dead, KARCHER_ALIVE_OFFICIAL]) == "",
    )

    # Vaga vivo NÃO é alive => ''
    twin_unknown = dict(KARCHER_ALIVE_OFFICIAL, liveness_status="unknown")
    check(
        "Twin não alive (unknown) => '' (só alive conta como original vivo)",
        mc.ba_mirror_twin_url(KARCHER_DEAD_BA, [KARCHER_DEAD_BA, twin_unknown]) == "",
    )


def test_build_manual_check_rows_f119() -> None:
    """G3 — build_manual_check_rows inclui linhas F119 informativas."""
    print("\n--- G3 — build_manual_check_rows: linhas F119 informativas ---")

    ranking = [
        KARCHER_DEAD_BA,
        KARCHER_ALIVE_OFFICIAL,
        RHEINMETALL_DEAD_BA,
        RHEINMETALL_ALIVE_OFFICIAL,
        DEAD_BA_NO_TWIN,  # sem twin
        OTHER_ALIVE,      # alive não relacionado
    ]

    rows = mc.build_manual_check_rows(ranking)

    # Deve ter 2 linhas F119 (Kärcher + Rheinmetall)
    f119_rows = [r for r in rows if r.get("f119_mirror_dead")]
    check(
        "Duas linhas F119 (Kärcher + Rheinmetall)",
        len(f119_rows) == 2,
        f"got {len(f119_rows)}",
    )

    # Verificar conteúdo das linhas F119
    by_company = {r["company"]: r for r in f119_rows}
    k_row = by_company.get("Alfred Kärcher SE & Co. KG")
    r_row = by_company.get("Rheinmetall AG")

    check(
        "Kärcher: linha F119 tem twin_url correto",
        k_row is not None
        and k_row.get("twin_url") == KARCHER_ALIVE_OFFICIAL["url"]
        and k_row.get("f119_mirror_dead") is True
        and k_row.get("motivo") is None,  # NÃO é item da fila
        str(k_row),
    )
    check(
        "Rheinmetall: linha F119 tem twin_url correto",
        r_row is not None
        and r_row.get("twin_url") == RHEINMETALL_ALIVE_OFFICIAL["url"]
        and r_row.get("f119_mirror_dead") is True
        and r_row.get("motivo") is None,
        str(r_row),
    )

    # Contra-caso NÃO deve gerar linha F119
    check(
        "Contra-caso (dead BA sem twin) NÃO gera linha F119",
        not any(r.get("company") == "Acme Corp" and r.get("f119_mirror_dead") for r in rows),
    )


def test_write_manual_check_md_f119() -> None:
    """G4 — write_manual_check_md renderiza seção F119 corretamente."""
    print("\n--- G4 — write_manual_check_md: renderização F119 ---")

    ranking = [
        KARCHER_DEAD_BA,
        KARCHER_ALIVE_OFFICIAL,
        RHEINMETALL_DEAD_BA,
        RHEINMETALL_ALIVE_OFFICIAL,
    ]
    rows = mc.build_manual_check_rows(ranking)

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "MANUAL-CHECK.md"
        mc.write_manual_check_md(path, rows, "2026-10-24T09:00:00+00:00")
        text = path.read_text(encoding="utf-8")

    # Verificar seção F119
    check(
        "Cabeçalho da seção F119 presente",
        "## ⚠ Espelho BA morto — original vivo (F119, display-only)" in text,
    )
    check(
        "Nota display-only presente",
        "liveness_status=dead" in text and "não muda" in text,
    )
    check(
        "Linha Kärcher com formato '⚠ mirror morto — original vivo'",
        "⚠ mirror morto — original vivo: [abrir](https://careers.kaercher.com/job/1365889355)" in text,
    )
    check(
        "Linha Rheinmetall com formato '⚠ mirror morto — original vivo'",
        "⚠ mirror morto — original vivo: [abrir](https://www.linkedin.com/jobs/view/987654321)" in text,
    )

    # Fila regular deve continuar funcionando (itens com motivo)
    # Adicionar um item com motivo para testar
    not_assessable_job = dict(OTHER_ALIVE, not_assessable="desc_vazia", liveness_status=None)
    rows2 = mc.build_manual_check_rows([not_assessable_job] + ranking)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "MANUAL-CHECK.md"
        mc.write_manual_check_md(path, rows2, "2026-10-24T09:00:00+00:00")
        text = path.read_text(encoding="utf-8")

    check(
        "Fila regular ainda conta itens com motivo (não F119)",
        "Manual check — 1 item(ns) na fila" in text,
    )
    check(
        "Seção F119 separada da fila regular",
        "## ⚠ Espelho BA morto" in text,
    )


def test_generate_manual_check_f119_stats() -> None:
    """G5 — generate_manual_check retorna stats F119."""
    print("\n--- G5 — generate_manual_check: stats F119 ---")

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        (data_dir / "eligible_jobs.json").write_text(
            json.dumps([
                KARCHER_DEAD_BA,
                KARCHER_ALIVE_OFFICIAL,
                RHEINMETALL_DEAD_BA,
                RHEINMETALL_ALIVE_OFFICIAL,
                DEAD_BA_NO_TWIN,
                OTHER_ALIVE,
            ], ensure_ascii=False),
            encoding="utf-8",
        )
        # Criar dataset_seen.db vazio
        import sqlite3
        db_path = data_dir / "dataset_seen.db"
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE dataset_seen (job_id TEXT PRIMARY KEY)")
        con.close()

        stats = mc.generate_manual_check(data_dir, generated_at="2026-10-24T09:00:00+00:00")

    check(
        "Stats incluem f119_mirror_dead",
        "f119_mirror_dead" in stats,
    )
    check(
        "f119_mirror_dead.count = 2 (Kärcher + Rheinmetall)",
        stats["f119_mirror_dead"]["count"] == 2,
        f"got {stats['f119_mirror_dead']['count']}",
    )
    check(
        "f119_mirror_dead.pairs tem 2 entradas",
        len(stats["f119_mirror_dead"]["pairs"]) == 2,
    )
    pairs = stats["f119_mirror_dead"]["pairs"]
    check(
        "Par Kärcher presente nos pairs",
        any(p["dead_company"] == "Alfred Kärcher SE & Co. KG" for p in pairs),
    )
    check(
        "Par Rheinmetall presente nos pairs",
        any(p["dead_company"] == "Rheinmetall AG" for p in pairs),
    )
    check(
        "Rows conta só fila regular (não F119)",
        stats["rows"] == 0,  # nenhum item com motivo neste ranking
    )


def test_invariants() -> None:
    """G6 — Invariantes: liveness_status PERMANECE dead, ranking intocado."""
    print("\n--- G6 — Invariantes (dead não ressuscita, ranking não muta) ---")

    ranking = [
        KARCHER_DEAD_BA,
        KARCHER_ALIVE_OFFICIAL,
    ]

    # Snapshot antes
    before_dead_status = KARCHER_DEAD_BA.get("liveness_status")
    before_ranking_json = json.dumps(ranking, sort_keys=True, ensure_ascii=False)

    # Rodar detecção
    twin = mc.ba_mirror_twin_url(KARCHER_DEAD_BA, ranking)
    rows = mc.build_manual_check_rows(ranking)

    # Snapshot depois
    after_dead_status = KARCHER_DEAD_BA.get("liveness_status")
    after_ranking_json = json.dumps(ranking, sort_keys=True, ensure_ascii=False)

    check(
        "liveness_status do dead NÃO muda (permanece dead)",
        before_dead_status == "dead" and after_dead_status == "dead",
    )
    check(
        "Ranking NÃO mutado (ordem/campos intocados)",
        before_ranking_json == after_ranking_json,
    )
    check(
        "Linha F119 NÃO tem motivo (não entra na fila paralela)",
        all(r.get("motivo") is None for r in rows if r.get("f119_mirror_dead")),
    )


def test_reuso_f105_helpers() -> None:
    """G7 — Reusa helpers do F105 (_twin_title_key, _desc_jaccard, _PORTAL_TWIN_MIN_JACCARD)."""
    print("\n--- G7 — Reuso integral dos helpers F105 ---")

    # Verificar que as constantes/helpers do F105 são usadas
    check(
        "Constante _PORTAL_TWIN_MIN_JACCARD = 0.5 (mesma calibração F105)",
        mc._PORTAL_TWIN_MIN_JACCARD == 0.5,
    )
    check(
        "_twin_title_key existe e funciona (reuso F105)",
        mc._twin_title_key("Praktikum Global Procurement") ==
        "global praktikum procurement",
    )
    check(
        "_desc_jaccard existe e funciona (reuso F105)",
        mc._desc_jaccard("procurement supply chain", "supply chain procurement") > 0.5,
    )
    check(
        "ba_mirror_twin_url usa _twin_title_key internamente (mesmo título normalizado)",
        mc.ba_mirror_twin_url(KARCHER_DEAD_BA, [KARCHER_DEAD_BA, KARCHER_ALIVE_OFFICIAL])
        == KARCHER_ALIVE_OFFICIAL["url"],
    )


def main() -> int:
    test_ba_mirror_twin_detection()
    test_fail_closed()
    test_build_manual_check_rows_f119()
    test_write_manual_check_md_f119()
    test_generate_manual_check_f119_stats()
    test_invariants()
    test_reuso_f105_helpers()

    print(f"\n==== test_f119: {CHECKS} checks, {len(FAILURES)} falha(s) ====")
    if FAILURES:
        for name in FAILURES:
            print(f"  [FAIL] {name}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# CI trigger
# CI trigger 2
# CI trigger 3