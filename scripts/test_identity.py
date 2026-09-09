"""Script standalone — P1.1: identidade Company / ATS tenant / Job.

Prova a correcao arquitetural da identidade: duas empresas no MESMO tenant ATS
com o MESMO ``external_id`` produzem Jobs diferentes, estaveis e
deterministicos — sem colisao em ``Job.id``, dedup, SQLite e lifecycle.

A regra (P1.1):

    identidade da empresa + tenant ATS + identidade externa = Job.id estavel

``source`` (``ats:slug``) identifica o TENANT, nao a empresa: o mesmo tenant
e compartilhado por varias empresas (ex.: ``successfactors:jobs`` cobre
SAP/ZF/Kaufland/...; ``phenom:nan`` cobre DHL/Allianz/Merck/...). O prefixo
``<company>`` entra no id e no escopo da dedup.

Cenarios (os 6 obrigatorios da tarefa):

1. mesmo tenant + mesmo external_id + empresas diferentes -> ids diferentes;
2. mesmo tenant + mesmo external_id + MESMA empresa -> mesmo id (estabilidade);
3. fallback sem external_id: empresas diferentes com URLs equivalentes nao
   colidem (nem no id, nem na dedup);
4. dedup: A+sf:jobs+12345 e B+sf:jobs+12345 NAO sao deduplicados; A duplicado
   continua deduplicando;
5. persistencia SQLite: os dois Jobs coexistam sem sobrescrever um ao outro;
6. lifecycle/historico: o estado historico de A nao sobrescreve nem e
   alterado pelo de B (mesmo tenant + external_id).

Uso:  .venv/bin/python scripts/test_identity.py
"""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.models.job import Job  # noqa: E402
from internship_finder.storage.sqlite_store import SqliteStore, _from_iso  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


# Formato de tenant que reproduz o problema real: MESMO tenant compartilhado.
TENANT = "successfactors:jobs"


def make_company(name: str) -> Company:
    """Company como o collector constroi (name da base, ats/slug do tenant)."""
    return Company(name=name, ats="successfactors", slug="jobs", query=name)


def adapt(item: dict, company: Company) -> Job:
    """Caminho de producao: item cru -> Job via AtsJobAdapter."""
    return AtsJobAdapter().to_job(item, company)


# ---------------------------------------------------------------------------
# 1-3. Job.id: identidade = empresa + tenant + identidade externa
# ---------------------------------------------------------------------------

def test_id_identity() -> None:
    print("== [1-3] Job.id escopado por empresa + tenant + external_id ==")
    A = make_company("A")
    B = make_company("B")

    # --- Caso 1: mesmo tenant, mesmo external_id, empresas diferentes ---
    job_a = adapt({"title": "Intern Procurement", "url": "https://jobs.sap/j/12345",
                   "external_id": "12345"}, A)
    job_b = adapt({"title": "Intern Procurement", "url": "https://jobs.zf/j/12345",
                   "external_id": "12345"}, B)
    check("caso 1: A e B no mesmo tenant com mesmo external_id -> ids diferentes",
          job_a.id != job_b.id, f"{job_a.id!r} == {job_b.id!r}")
    check("caso 1: formato <company>|<source>:<external_id>",
          job_a.id == "A|successfactors:jobs:12345", f"id={job_a.id!r}")
    check("caso 1: company do Job preservada por empresa",
          job_a.company == "A" and job_b.company == "B")
    check("caso 1: source (tenant tecnico) inalterado",
          job_a.source == TENANT and job_b.source == TENANT)

    # --- Caso 2: mesma empresa, mesmo tenant, mesmo external_id -> mesmo id ---
    job_a2 = adapt({"title": "Intern Procurement", "url": "https://jobs.sap/j/12345",
                    "external_id": "12345"}, A)  # re-coleta (execucao posterior)
    check("caso 2: mesma empresa -> mesmo id (estavel entre execucoes)",
          job_a.id == job_a2.id, f"{job_a.id!r} != {job_a2.id!r}")

    # --- Caso 3: fallback SEM external_id, URLs equivalentes (hash) ---
    item_a = {"title": "Intern A", "url": "https://careers.example/job/42"}
    item_b = {"title": "Intern B", "url": "https://careers.example/job/42"}
    fall_a = adapt(item_a, A)
    fall_b = adapt(item_b, B)
    check("caso 3: sem external_id, mesma URL em empresas diff -> ids diferentes",
          fall_a.id != fall_b.id, f"{fall_a.id!r} == {fall_b.id!r}")
    check("caso 3: fallback continua deterministico na mesma empresa",
          adapt(item_a, A).id == fall_a.id)
    check("caso 3: fallback preserva o hash da URL escopado pela empresa",
          fall_a.id == f"A|{TENANT}:" + fall_a.id.split(":")[-1]
          and fall_b.id == f"B|{TENANT}:" + fall_b.id.split(":")[-1])
    check("caso 3: fallback e hash hex curto (mesma regra de antes)",
          len(fall_a.id.rsplit(":", 1)[1]) == 16)


# ---------------------------------------------------------------------------
# 4. Dedup
# ---------------------------------------------------------------------------

def test_dedup_company_scope() -> None:
    print("== [4] dedup escopado por (empresa, tenant, external_id) ==")
    A, B = make_company("A"), make_company("B")
    job_a = adapt({"title": "Intern", "url": "https://x/1", "external_id": "12345"}, A)
    job_b = adapt({"title": "Intern", "url": "https://y/1", "external_id": "12345"}, B)
    job_a2 = adapt({"title": "Intern", "url": "https://z/1", "external_id": "12345"}, A)

    # A vs B (mesmo tenant + external_id) -> NAO deduplicam
    out, _, _ = deduplicate([job_a.to_dict(), job_b.to_dict()])
    check("caso 4: A e B com mesmo tenant+external_id -> 2 vagas", len(out) == 2,
          f"out={len(out)}")
    # A duplicado -> deduplica (mesma identidade externa)
    out2, stats2, _ = deduplicate([job_a.to_dict(), job_a2.to_dict()])
    check("caso 4: A repetido -> 1 vaga (external_id deduplica dentro da empresa)",
          len(out2) == 1, f"out={len(out2)}")
    check("caso 4: dedup interna contabilizada por external_id",
          stats2.get("external_id") == 1, f"stats={stats2}")

    # caso 3 (persistencia da nao-colisao): mesma URL, empresas diff -> separados
    item = {"title": "Intern", "url": "https://careers.example/job/42"}
    same_url_a = adapt(item, A).to_dict()
    same_url_b = adapt(item, B).to_dict()
    out3, _, _ = deduplicate([same_url_a, same_url_b])
    check("caso 3: mesma URL, empresas diff -> nao deduplicam por URL",
          len(out3) == 2, f"out={len(out3)}")
    out4, _, _ = deduplicate([same_url_a, adapt(item, A).to_dict()])
    check("caso 3: mesma URL, MESMA empresa -> deduplica por URL (estabilidade)",
          len(out4) == 1, f"out={len(out4)}")

    # chave (c) company+title+location segue escopada por empresa (regressao)
    from internship_finder.dedup import KEY_COMPANY_TITLE_LOCATION
    t = "Intern Procurement"
    ctl_a = adapt({"title": t, "url": "https://a/1", "external_id": "1",
                   "location": "Berlin"}, A).to_dict()
    ctl_b = adapt({"title": t, "url": "https://b/1", "external_id": "2",
                   "location": "Berlin"}, B).to_dict()
    out5, stats5, _ = deduplicate([ctl_a, ctl_b])
    check("regressao: company+title+location nao funde empresas diferentes",
          len(out5) == 2 and KEY_COMPANY_TITLE_LOCATION not in stats5)


# ---------------------------------------------------------------------------
# 5-6. SQLite + lifecycle
# ---------------------------------------------------------------------------

def make_seen_job(company: str, collected_at: datetime, url: str) -> Job:
    """Job no formato do pipeline (id gerado pelo adapter) com timestamp fixo."""
    c = make_company(company)
    raw = adapt({"title": "Intern", "url": url, "external_id": "12345"}, c).to_dict()
    raw["collected_at"] = collected_at.isoformat().replace("+00:00", "Z")
    return Job(**raw)


def test_sqlite_and_lifecycle() -> None:
    print("== [5-6] SQLite + lifecycle: estados por empresa nao colidem ==")
    t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 2, 10, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 9, 3, 10, 0, 0, tzinfo=UTC)

    with tempfile.TemporaryDirectory() as td:
        store = SqliteStore(Path(td) / "jobs.db")
        job_a = make_seen_job("A", t1, "https://a/1")   # id A|successfactors:jobs:12345
        job_b = make_seen_job("B", t2, "https://b/1")   # id B|successfactors:jobs:12345

        # --- Caso 5: os dois Jobs coexistem no SQLite ---
        store.run([job_a, job_b])
        row_a = store.get(job_a.id)
        row_b = store.get(job_b.id)
        check("caso 5: ids distintos", job_a.id != job_b.id,
              f"{job_a.id!r} == {job_b.id!r}")
        check("caso 5: ambos persistidos (2 linhas, sem sobrescrever)",
              row_a is not None and row_b is not None)
        check("caso 5: linhas independentes (company distinta por linha)",
              row_a["company"] == "A" and row_b["company"] == "B")
        check("caso 5: ambos ativos no run em que apareceram",
              row_a["active"] == 1 and row_b["active"] == 1)

        # --- Caso 6: run2 so ve B -> A arquivado; B novo (first_seen proprio) ---
        stats2 = store.run([job_b])
        row_a2 = store.get(job_a.id)
        row_b2 = store.get(job_b.id)
        check("caso 6: B repetido nao e novo (updated)", stats2["inserted"] == 0)
        check("caso 6: A arquivado (nao veio no run2)", row_a2["archived"] == 1)
        check("caso 6: B permanece ativo", row_b2["active"] == 1)
        check("caso 6: first_seen de B e o run DELE (nao herdou o de A)",
              _from_iso(row_b["first_seen"]) == t2,
              f"{_from_iso(row_b['first_seen'])!r}")
        check("caso 6: first_seen de A imutavel (nao sobrescrito por B)",
              _from_iso(row_a2["first_seen"]) == t1,
              f"{_from_iso(row_a2['first_seen'])!r}")

        # --- run3: A volta; B segue ativo; historico preservado por empresa ---
        stats3 = store.run([job_a, job_b])
        row_a3 = store.get(job_a.id)
        row_b3 = store.get(job_b.id)
        store.close()
        check("caso 6: A reativado no run3", stats3["reactivated"] == 1
              and row_a3["active"] == 1 and row_a3["archived"] == 0)
        check("caso 6: A volta com first_seen original (t1)", _from_iso(row_a3["first_seen"]) == t1)
        check("caso 6: B segue ativo e intacto", row_b3["active"] == 1
              and _from_iso(row_b3["first_seen"]) == t2)


def main() -> int:
    print("Script standalone — P1.1: identidade Company / ATS tenant / Job")
    test_id_identity()
    test_dedup_company_scope()
    test_sqlite_and_lifecycle()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())