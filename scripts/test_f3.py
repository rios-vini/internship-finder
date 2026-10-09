"""F3 — dataset hospedado como fonte primaria, registry como interesse (test_f3).

Trava o NOVO comportamento da fase (inversao arquitetural):

GRUPO A — Prefilter (dataset_source, streaming CSV):
  A1. Row DE com marcador de estagio -> mantida; contagens batem.
  A2. Row DE sem marcador -> rejeitada; row non-DE com marcador -> rejeitada.
  A3. Row DE com exclusao de tipo (Duales Studium) -> rejeitada.
  A4. Row com iso VAZIO + location DE ("Berlin, DE, 10587") -> mantida
      (fato medido: fatia successfactors tem country_iso vazio).
  A5. Summary com rows_total/rows_prefiltered/per_ats corretos.

GRUPO B — Conversao row -> Job (row_to_job):
  B1. id = "<company>|sf_dataset:<ats>:<ats_id>"; source = "sf_dataset:<ats>".
  B2. Sem ats_id: id com hash sha1 16-hex da URL (mesma regra do adapter).
  B3. internship=True para marcada; raw preserva TUDO menos description.
  B4. country_iso inferido (iso vazio + "Berlin, DE" -> 'de').
  B5. posted_at parseado ou None (nunca crash).
  B6. Row sem title/company/url -> None + contador invalid_rows (nunca crash).

GRUPO C — Dedup cross-fonte:
  C1. Job dataset + job producao MESMA company+URL -> colapsam na chave
      URL (b); registro removed com label 'url'.
  C2. Mesmo external_id mas company divergente NAO colapsa (escopo P1.1).
  C3. mirror-dedup: job sf_dataset e job producao com mesmo requisition_id
      NUNCA pareiam (source diferente = tenant diferente; invariante 9).

GRUPO D — Peso registry (ranking):
  D1. "Robert Bosch GmbH" -> +WEIGHT_REGISTRY_INTEREST (substring casefold).
  D2. "Bosch" exato idem; "SAP" idem; breakdown tem 'registry'.
  D3. "Levio GmbH" (fora do registry) -> 0.
  D4. Invariante aditivo: score(registry) - score(non-registry, mesmo
      resto) == peso.

GRUPO E — Hidratacao sf_dataset (_slug_for/_slug_from_url):
  E1. sf_dataset:workday com URL myworkdayjobs -> slug = URL base.
  E2. sf_dataset:smartrecruiters jobs.smartrecruiters.com/BoschGroup/...
      -> slug BoschGroup.
  E3. sf_dataset:personio <tenant>.jobs.personio.de -> label sem pontos.
  E4. sf_dataset:successfactors -> unsupported_no_detail (sem override),
      vaga preservada.
  E5. Falha de fetch -> vaga preservada com description original.
  E6. Producao (source ats:slug) inalterada: smartrecruiters:BoschGroup
      -> BoschGroup; workday -> URL base.

GRUPO F — CLI (defaults e integracao):
  F1. --dataset default ON no modo --registry (coleta chama o estagio).
  F2. --no-dataset desliga (jobs = so registry).
  F3. Dataset failed -> run segue, exit NAO vira 2 (best-effort).
  F4. --companies explícito: dataset default OFF (compat).

GRUPO G — Budget:
  G1. 2 fatias + budget que so permite a 1a -> segunda vira
      skipped_budget; jobs da 1a presentes; summary registra.

GRUPO H — Registry NAO e filtro (o coracao da F3):
  H1. Job dataset de empresa FORA do registry ("Levio GmbH", DE, estagio,
      area-match) passa pelo funil e chega ao eligible — sem componente
      registry no breakdown.

GRUPO I — JSONL:
  I1. Registro type: dataset com campos novos (run_id, source=sf_dataset,
      per_ats, total_prefiltered, bytes, duration, status).
  I2. Registro run com total_collected somando registry+dataset.

GRUPO J — CI:
  J1. .github/workflows/ci.yml array tests inclui test_f3.

100% OFFLINE: fixtures CSV sinteticas em tempdir; download injetado via
``http_fetch``; nenhum acesso a rede. Padrao da suite: [OK]/[FAIL] e
termina com ``TUDO OK``.

Uso: .venv/bin/python scripts/test_f3.py
"""

from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder import cli  # noqa: E402
from internship_finder.dataset_source import (  # noqa: E402
    collect_dataset_jobs,
    is_de_row,
    row_is_intern_candidate,
    row_to_job,
)
from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.filters import select_eligible  # noqa: E402
from internship_finder.hydration import _slug_for, hydrate_descriptions  # noqa: E402
from internship_finder.mirror_dedup import deduplicate_mirrors_de_en  # noqa: E402
from internship_finder.models.job import Job  # noqa: E402
from internship_finder.ranking import (  # noqa: E402
    WEIGHT_REGISTRY_INTEREST,
    registry_interest,
    score_job,
)

FAILURES: list[str] = []

DATASET_HEADER = [
    "url", "title", "company", "ats_type", "ats_id", "location",
    "country_iso", "region", "language", "lat", "lon", "is_remote",
    "salary_min", "salary_max", "salary_currency", "salary_period",
    "salary_summary", "employment_type", "department", "team",
    "description", "posted_at", "requisition_id", "apply_url",
    "commitment", "raw",
]


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def make_row(
    *, url: str, title: str, company: str, ats_id: str = "1",
    location: str = "Berlin, DE, 10587", country_iso: str = "",
    description: str = "", employment_type: str = "", posted_at: str = "",
    requisition_id: str = "",
) -> dict:
    row = {k: "" for k in DATASET_HEADER}
    row.update({
        "url": url, "title": title, "company": company,
        "ats_type": "successfactors", "ats_id": ats_id,
        "location": location, "country_iso": country_iso,
        "description": description, "employment_type": employment_type,
        "posted_at": posted_at, "requisition_id": requisition_id,
    })
    return row


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=DATASET_HEADER, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# A. Prefilter
# ---------------------------------------------------------------------------

def test_prefilter() -> None:
    print("== A. Prefilter (streaming, criterios a/b/c) ==")
    check("A1. marcador DE mantido",
          row_is_intern_candidate("Werkstudent:in - Facility Management"))
    check("A2a. sem marcador rejeitado", not row_is_intern_candidate(
        "Senior Manager Supply Chain"))
    check("A2b. marcador non-DE cai no criterio (c)",
          not is_de_row("", "Paris, France"))
    check("A3. exclusao de tipo (Duales Studium)",
          not row_is_intern_candidate("Duales Studium Einkauf (m/w/d)"))
    check("A3b. exclusao JMP", not row_is_intern_candidate(
        "Junior Managers Program (JMP)"))
    check("A4. iso vazio + location DE", is_de_row("", "Berlin, DE, 10587"))
    check("A4b. iso 'de' populado", is_de_row("de", ""))
    check("A4c. location 'Germany - Munich'", is_de_row("", "Germany - Munich"))

    with tempfile.TemporaryDirectory() as tmp:
        rows = [
            make_row(url="https://a/1", title="Werkstudent Data Analytics",
                     company="Acme GmbH"),
            # sem marcador
            make_row(url="https://a/2", title="Supply Chain Manager",
                     company="Acme GmbH"),
            # non-DE
            make_row(url="https://a/3", title="Working Student Analytics",
                     company="Acme NL", location="Amsterdam, NL"),
            # exclusao de tipo
            make_row(url="https://a/4", title="Duales Studium Logistik",
                     company="Acme GmbH"),
            # sem company (invalida no row_to_job, mas prefilter mantem)
            make_row(url="https://a/5", title="Praktikum Einkauf",
                     company=""),
        ]
        csv_path = Path(tmp) / "slice.csv"
        write_csv(csv_path, rows)
        manifest = {"acme": {"csv": str(csv_path), "rows": len(rows)}}
        jobs, summary = collect_dataset_jobs(
            manifest=manifest, sources=["acme"],
            http_fetch=lambda url, dest: (dest.write_bytes(csv_path.read_bytes()),
                                          len(rows))[1],
            workdir=Path(tmp),
        )
        check("A5a. rows_total = 5", summary["rows_total"] == 5,
              str(summary["rows_total"]))
        check("A5b. rows_prefiltered = 2 (rows 1 e 5)",
              summary["rows_prefiltered"] == 2, str(summary["rows_prefiltered"]))
        check("A5c. invalid_rows = 1 (sem company)",
              summary["invalid_rows"] == 1, str(summary["invalid_rows"]))
        check("A5d. jobs = 1", len(jobs) == 1, str(len(jobs)))
        check("A5e. per_ats acme rows/kept",
              summary["per_ats"]["acme"]["rows"] == 5
              and summary["per_ats"]["acme"]["kept"] == 2)
        check("A5f. fatia local apagada (nao acumula disco)",
              not (Path(tmp) / "acme.csv").exists())


# ---------------------------------------------------------------------------
# B. Conversao row -> Job
# ---------------------------------------------------------------------------

def test_row_to_job() -> None:
    print("== B. row -> Job (identidade, raw, inferencia) ==")
    row = make_row(
        url="https://apply.example/job/1", title="Praktikum Data Analytics",
        company="Acme GmbH", ats_id="42",
        description="Beschreibung", employment_type="INTERN",
        posted_at="2026-09-01Z", location="Berlin, DE, 10587",
    )
    job = row_to_job(row, "successfactors")
    check("B1. id escopado company|sf_dataset:ats:ats_id",
          job.id == "Acme GmbH|sf_dataset:successfactors:42", job.id)
    check("B1b. source sf_dataset", job.source == "sf_dataset:successfactors")
    check("B2. sem ats_id -> hash sha1 16-hex da URL", True)  # abaixo
    import hashlib
    row2 = make_row(url="https://apply.example/job/7",
                     title="Praktikum", company="Acme GmbH", ats_id="")
    job2 = row_to_job(row2, "workday")
    want = "Acme GmbH|sf_dataset:workday:" + hashlib.sha1(
        b"https://apply.example/job/7").hexdigest()[:16]
    check("B2b. id por hash igual ao esperado", job2.id == want, job2.id)
    check("B3a. internship True", job.internship is True)
    check("B3b. raw preserva tudo menos description",
          "description" not in (job.raw or {}) and job.raw.get("ats_id") == "42")
    check("B4. country_iso inferido 'de'", job.country_iso == "de",
          str(job.country_iso))
    check("B5. posted_at parseado", job.posted_at is not None)
    row3 = make_row(url="https://x/9", title="Praktikum", company="A",
                    posted_at="nao-data")
    job3 = row_to_job(row3, "greenhouse")
    check("B5b. posted_at invalido -> None (sem crash)",
          job3.posted_at is None)
    check("B6a. sem company -> None", row_to_job(
        make_row(url="https://x/1", title="T", company=""), "greenhouse") is None)
    check("B6b. sem title -> None", row_to_job(
        make_row(url="https://x/1", title="", company="C"), "greenhouse") is None)
    check("B6c. sem url -> None", row_to_job(
        make_row(url="", title="T", company="C"), "greenhouse") is None)


# ---------------------------------------------------------------------------
# C. Dedup cross-fonte
# ---------------------------------------------------------------------------

def _prod_job(url: str, title: str = "Werkstudent Einkauf",
              company: str = "SAP", ext: str = "99") -> dict:
    return {
        "id": f"{company}|successfactors:jobs:{ext}",
        "source": "successfactors:jobs",
        "title": title, "company": company, "url": url,
        "collected_at": "2026-10-02T07:00:00+00:00",
    }


def test_dedup_cross_source() -> None:
    print("== C. dedup cross-fonte (chave b; escopo P1.1) ==")
    # C1: mesma company + mesma URL normalizada (barra final) -> colapsa
    ds = row_to_job(make_row(
        url="https://jobs.example.com/job/99",
        title="Werkstudent Einkauf", company="SAP",
        description="vaga completa"), "successfactors").to_dict()
    prod = _prod_job("https://jobs.example.com/job/99/")
    out, stats, removed = deduplicate([ds, prod])
    check("C1a. colapsam para 1 vaga", len(out) == 1, str(len(out)))
    check("C1b. remocao pela chave url", stats.get("url") == 1, str(stats))
    check("C1c. vencedor tem description (regra _prefer)",
          bool(out[0].get("description")))
    check("C1d. registro removed com label 'url'",
          removed and removed[0][2] == "url")
    # C2: mesmo external_id, company divergente NAO colapsa
    ds2 = row_to_job(make_row(
        url="https://jobs2.example.com/job/99",
        title="Werkstudent", company="Outra GmbH"), "successfactors").to_dict()
    prod2 = _prod_job("https://jobs2.example.com/job/99", company="SAP")
    out2, stats2, _ = deduplicate([ds2, prod2])
    check("C2. escopo company+source: ids iguais nao colapsam",
          len(out2) == 2 and not stats2, str((len(out2), stats2)))
    # C3: mirror-dedup nunca casa cross-fonte (source diferente = outro tenant)
    m_ds = row_to_job(make_row(
        url="https://m.example/1", title="Praktikum Logistik EN",
        company="SAP", requisition_id="REQ-1"), "successfactors").to_dict()
    m_prod = _prod_job("https://m.example/2",
                       title="Praktikum Logistik", company="SAP", ext="7")
    m_prod["raw"] = {"requisition_id": "REQ-1"}
    m_ds["raw"] = {"requisition_id": "REQ-1"}
    # removes a chave (c) classica (company+title+location) da equacao: o
    # par tem locations DIFERENTES, entao so a chave mirror poderia unir.
    m_ds["location"] = "Berlin, DE"
    m_prod["location"] = "Munich, DE"
    out3, mstats, _ = deduplicate_mirrors_de_en([m_ds, m_prod])
    check("C3. mirror-dedup nao remove cross-fonte",
          len(out3) == 2 and mstats.get("mirrors_de_en") == 0,
          str((len(out3), mstats)))


# ---------------------------------------------------------------------------
# D. Peso registry
# ---------------------------------------------------------------------------

def test_registry_weight() -> None:
    print("== D. componente registry (lista de interesse) ==")
    check("D1. Robert Bosch GmbH (substring casefold)",
          registry_interest("Robert Bosch GmbH") == WEIGHT_REGISTRY_INTEREST)
    check("D2a. Bosch exato", registry_interest("Bosch") == WEIGHT_REGISTRY_INTEREST)
    check("D2b. SAP", registry_interest("SAP") == WEIGHT_REGISTRY_INTEREST)
    check("D2c. breakdown tem 'registry'",
          "registry" in score_job({
              "id": "x", "source": "s", "title": "Werkstudent",
              "company": "Bosch", "url": "https://a/1",
              "location": "Berlin, DE", "country_iso": "de",
              "collected_at": "2026-10-02T07:00:00+00:00"}).breakdown)
    check("D3. Levio GmbH fora do registry -> 0",
          registry_interest("Levio GmbH") == 0.0)
    base = {
        "id": "x", "source": "s", "title": "Werkstudent",
        "url": "https://a/1", "location": "Berlin, DE",
        "country_iso": "de", "collected_at": "2026-10-02T07:00:00+00:00",
    }
    s_reg = score_job({**base, "company": "Robert Bosch GmbH"})
    s_out = score_job({**base, "company": "Levio GmbH"})
    check("D4. invariante aditivo == peso",
          abs((s_reg.total - s_out.total) - WEIGHT_REGISTRY_INTEREST) < 1e-9,
          f"{s_reg.total} vs {s_out.total}")


# ---------------------------------------------------------------------------
# E. Hidratacao sf_dataset
# ---------------------------------------------------------------------------

def test_hydration_sf_dataset() -> None:
    print("== E. hidratacao sf_dataset (slug derivado da URL) ==")
    wd = {"source": "sf_dataset:workday",
          "url": "https://acme.wd103.myworkdayjobs.com/acmeCareers/job/1"}
    check("E1. workday -> URL base",
          _slug_for("workday", wd) == "https://acme.wd103.myworkdayjobs.com/acmeCareers")
    sr = {"source": "sf_dataset:smartrecruiters",
          "url": "https://jobs.smartrecruiters.com/BoschGroup/741000/"}
    check("E2. smartrecruiters -> BoschGroup",
          _slug_for("smartrecruiters", sr) == "BoschGroup")
    pe = {"source": "sf_dataset:personio",
          "url": "https://tenant-x.jobs.personio.de/job/1"}
    check("E3. personio -> label sem pontos",
          _slug_for("personio", pe) == "tenant-x")
    # E4: successfactors fora do mapa de detail -> unsupported, preservada
    job_sf = {
        "id": "Acme GmbH|sf_dataset:successfactors:5",
        "source": "sf_dataset:successfactors", "title": "Werkstudent",
        "company": "Acme GmbH", "url": "https://careers.acme/job/5",
        "location": "Berlin, DE", "country_iso": "de",
        "description": "", "collected_at": "2026-10-02T07:00:00+00:00",
    }
    out, stats = hydrate_descriptions([dict(job_sf)])
    check("E4a. unsupported_no_detail (sem endpoint)",
          stats["unsupported_no_detail"] == 1, str(stats))
    check("E4b. vaga preservada", len(out) == 1
          and out[0]["title"] == "Werkstudent")
    # E5: falha de fetch -> vaga preservada SEM description fabricada. A
    # vaga entra como candidata (description vazia), o scraper injetado
    # levanta e a excecao vira hydration_failed; description permanece
    # ausente (ausencia != dado falso).
    job_sr = dict(job_sf, source="sf_dataset:smartrecruiters",
                  description="",
                  url="https://jobs.smartrecruiters.com/BoschGroup/1")

    class BoomScraper:
        def get_description(self, job):
            raise RuntimeError("network down")

    out5, stats5 = hydrate_descriptions(
        [dict(job_sr)], scraper_factory=lambda ats, slug: BoomScraper(),
        budget_seconds=5)
    check("E5a. falha de fetch contada", stats5["hydration_failed"] == 1,
          str(stats5))
    check("E5b. vaga preservada, sem description fabricada",
          len(out5) == 1 and not out5[0].get("description"))
    # E6: producao (ats:slug) inalterada
    check("E6a. smartrecruiters:BoschGroup -> BoschGroup",
          _slug_for("smartrecruiters", {"source": "smartrecruiters:BoschGroup",
                                        "url": "x"}) == "BoschGroup")
    check("E6b. workday producao -> URL base",
          _slug_for("workday", {"source": "workday:acme/x",
                                "url": "https://acme.wd3.myworkdayjobs.com/x/job/1"})
          == "https://acme.wd3.myworkdayjobs.com/x")


# ---------------------------------------------------------------------------
# F. CLI: defaults, --no-dataset, falha best-effort
# ---------------------------------------------------------------------------

COLLECT_SUMMARY = {
    "ok": [("successfactors:acme", 1, "1.0s")], "empty": [], "timeout": [],
    "failed": [], "skipped": [], "not_found": False, "companies": {},
}


def _one_job(name="Acme") -> list[Job]:
    return [Job(
        id=f"{name}|successfactors:acme:1", source="successfactors:acme",
        title="Praktikum Data Analytics", company=name,
        url=f"https://acme.example/job/1", location="Berlin, DE",
        country_iso="de", collected_at="2026-10-02T07:00:00+00:00",
    )]


def test_cli_dataset_flow() -> None:
    print("== F. CLI: --dataset default/falha/off ==")
    with tempfile.TemporaryDirectory() as tmp:
        metrics = f"{tmp}/m.jsonl"

        def _collect(name, **kw):
            return _one_job(), COLLECT_SUMMARY

        # F1: --registry (default ON) — o estagio dataset roda (stubado)
        ds_row = make_row(url="https://acme.example/job/1",
                          title="Praktikum Data Analytics", company="Acme",
                          description="full text")
        slice_path = Path(tmp) / "fx.csv"
        write_csv(slice_path, [ds_row])
        fake_manifest = {"successfactors": {"csv": str(slice_path)}}

        def _fetch(url, dest):
            dest.write_bytes(slice_path.read_bytes())
            return len(slice_path.read_bytes())

        with patch.object(cli, "collect_company", side_effect=_collect), \
             patch.object(cli, "collect_dataset_jobs") as cds:
            cds.side_effect = lambda **kw: (
                [row_to_job(ds_row, "successfactors")],
                {"status": "ok", "rows_total": 1, "rows_prefiltered": 1,
                 "invalid_rows": 0, "jobs": 1,
                 "per_ats": {"successfactors": {"rows": 1, "kept": 1}},
                 "skipped_budget": 0, "failed_slices": 0,
                 "bytes_downloaded": 100, "duration": 0.1})
            rc = cli.main(["--registry", "--companies", "SAP", "--no-direct-fetch",
                           "--no-research-sources",
                           "--output", f"{tmp}/j1.json",
                           "--filter-output", f"{tmp}/e1.json",
                           "--metrics", metrics])
        check("F1. --registry roda estagio dataset (default ON)",
              cds.called and rc == 0, f"rc={rc} called={cds.called}")

        # F2: --no-dataset desliga
        with patch.object(cli, "collect_company", side_effect=_collect), \
             patch.object(cli, "collect_dataset_jobs") as cds2:
            rc = cli.main(["--registry", "--companies", "SAP", "--no-dataset", "--no-direct-fetch",
                           "--no-research-sources",
                           "--output", f"{tmp}/j2.json",
                           "--filter-output", f"{tmp}/e2.json",
                           "--metrics", metrics])
            check("F2. --no-dataset desliga o estagio",
                  not cds2.called and rc == 0, f"rc={rc}")

        # F3: dataset failed -> run segue, exit NAO vira 2
        # (F21: --no-research-sources para isolar o contrato do dataset —
        # o estagio research_sources e default ON no --registry)
        with patch.object(cli, "collect_company", side_effect=_collect), \
             patch.object(cli, "collect_dataset_jobs") as cds3:
            cds3.side_effect = RuntimeError("manifest down")
            rc = cli.main(["--registry", "--companies", "SAP", "--no-direct-fetch",
                           "--no-research-sources",
                           "--output", f"{tmp}/j3.json",
                           "--filter-output", f"{tmp}/e3.json",
                           "--metrics", metrics])
            check("F3. dataset failed: run segue sem exit 2",
                  rc == 0, f"rc={rc}")
            raw3 = json.loads(Path(f"{tmp}/j3.json").read_text(encoding="utf-8"))
            check("F3b. jobs.json so com registry jobs", len(raw3) == 1)
            # registro dataset failed no JSONL
            lines = [json.loads(x) for x in
                     Path(metrics).read_text(encoding="utf-8").splitlines() if x.strip()]
            ds_recs = [r for r in lines if r.get("type") == "dataset"]
            check("F3c. registro dataset status=failed no JSONL",
                  any(r.get("status") == "failed" for r in ds_recs))

        # F4: --companies explícito -> dataset default OFF
        with patch.object(cli, "collect_company", side_effect=_collect), \
             patch.object(cli, "collect_dataset_jobs") as cds4:
            rc = cli.main(["--companies", "Acme",
                           "--output", f"{tmp}/j4.json",
                           "--filter-output", f"{tmp}/e4.json",
                           "--metrics", metrics])
            check("F4. --companies puro: dataset OFF por default",
                  not cds4.called and rc == 0, f"rc={rc}")


# ---------------------------------------------------------------------------
# G. Budget entre fatias
# ---------------------------------------------------------------------------

def test_budget() -> None:
    print("== G. budget entre fatias ==")
    with tempfile.TemporaryDirectory() as tmp:
        rows_a = [make_row(url="https://a/1", title="Werkstudent Analytics",
                           company="A GmbH")]
        rows_b = [make_row(url="https://b/1", title="Praktikum Einkauf",
                           company="B GmbH")]
        pa, pb = Path(tmp) / "a.csv", Path(tmp) / "b.csv"
        write_csv(pa, rows_a)
        write_csv(pb, rows_b)
        manifest = {"aaa": {"csv": str(pa)}, "bbb": {"csv": str(pb)}}

        def fetch(url, dest):
            src = pa if str(url).endswith("a.csv") else pb
            dest.write_bytes(src.read_bytes())
            return 10

        # clock fake: t0=0; budget 5s; a 1a fatia termina em t=10 -> a 2a
        # estoura o budget e vira skipped_budget
        clock = {"t": 0.0}

        def now():
            return clock["t"]

        def fetch_advance(url, dest):
            res = fetch(url, dest)
            clock["t"] += 10.0  # cada fatia consome 10s
            return res

        jobs, summary = collect_dataset_jobs(
            manifest=manifest, budget_seconds=5.0,
            http_fetch=fetch_advance, now=now, workdir=Path(tmp),
        )
        check("G1a. 2a fatia skipped_budget",
              summary["per_ats"]["bbb"]["skipped_budget"] is True,
              str(summary["per_ats"]))
        check("G1b. jobs da 1a fatia presentes", len(jobs) == 1)
        check("G1c. summary skipped_budget = 1",
              summary["skipped_budget"] == 1)
        check("G1d. status ok (a 1a coletou)", summary["status"] == "ok")


# ---------------------------------------------------------------------------
# H. Registry NAO e filtro (coracao da F3)
# ---------------------------------------------------------------------------

def test_registry_not_filter() -> None:
    print("== H. empresa FORA do registry chega ao eligible ==")
    # "Levio GmbH": fora do registry (fato medido §2.6 — 39 intern-DE),
    # DE + estagio + area-match -> deve passar pelo funil inteiro.
    ds_job = row_to_job(make_row(
        # F18: título HÍBRIDO (Werkstudent + Praktikum) — Werkstudent puro
        # sairia pelo hard exclude de aplicabilidade; o híbrido fica e o
        # bloco continua testando o componente registry (não-filtro).
        url="https://careers.levio.de/job/9",
        title="Werkstudent / Praktikum Data Analytics (m/w/d)",
        company="Levio GmbH", description="sap reporting python",
        employment_type="INTERN"), "successfactors")
    selected, counts = select_eligible([ds_job.to_dict()], country="de")
    check("H1a. job fora do registry passa pelo funil",
          len(selected) == 1, str(counts))
    scored = score_job(selected[0])
    check("H1b. sem componente registry (score nao bonificado)",
          scored.breakdown.get("registry") == 0.0, str(scored.breakdown))
    # contraste: mesma vaga na Bosch (registry) ganha +1.0
    bosch = row_to_job(make_row(
        url="https://jobs.bosch.com/job/9",
        title="Werkstudent / Praktikum Data Analytics (m/w/d)",
        company="Robert Bosch GmbH", description="sap reporting python",
        employment_type="INTERN"), "successfactors")
    sel_b, _ = select_eligible([bosch.to_dict()], country="de")
    scored_b = score_job(sel_b[0])
    check("H1c. mesma vaga no registry ganha o componente",
          scored_b.breakdown.get("registry") == WEIGHT_REGISTRY_INTEREST)


# ---------------------------------------------------------------------------
# I. JSONL (registro dataset + run somando registry+dataset)
# ---------------------------------------------------------------------------

def test_jsonl_records() -> None:
    print("== I. registros JSONL (dataset + run) ==")
    with tempfile.TemporaryDirectory() as tmp:
        metrics = Path(tmp) / "m2.jsonl"

        def _collect(name, **kw):
            return _one_job(), COLLECT_SUMMARY

        ds_row = make_row(url="https://acme.example/job/2",
                          title="Praktikum Data Analytics", company="Acme",
                          description="full")
        slice_path = Path(tmp) / "fx.csv"
        write_csv(slice_path, [ds_row])

        def _fetch(url, dest):
            dest.write_bytes(slice_path.read_bytes())
            return len(slice_path.read_bytes())

        with patch.object(cli, "collect_company", side_effect=_collect), \
             patch.object(cli, "collect_dataset_jobs") as cds:
            cds.side_effect = lambda **kw: (
                [row_to_job(ds_row, "successfactors")],
                {"status": "ok", "rows_total": 1, "rows_prefiltered": 1,
                 "invalid_rows": 0, "jobs": 1,
                 "per_ats": {"successfactors": {"rows": 1, "kept": 1,
                                                 "skipped_budget": False,
                                                 "failed": False}},
                 "skipped_budget": 0, "failed_slices": 0,
                 "bytes_downloaded": 123, "duration": 0.2})
            rc = cli.main(["--registry", "--companies", "SAP", "--no-direct-fetch",
                           "--no-research-sources",
                           "--output", f"{tmp}/j5.json",
                           "--filter-output", f"{tmp}/e5.json",
                           "--metrics", str(metrics)])
        lines = [json.loads(x) for x in
                 metrics.read_text(encoding="utf-8").splitlines() if x.strip()]
        ds_rec = next((r for r in lines if r.get("type") == "dataset"), None)
        run_rec = next((r for r in lines if r.get("type") == "run"), None)
        check("I1a. registro dataset existe", ds_rec is not None)
        if ds_rec:
            for field in ("run_id", "timestamp", "source", "per_ats",
                          "total_prefiltered", "bytes_downloaded", "duration",
                          "status"):
                check(f"I1b. dataset.{field} presente", field in ds_rec)
            check("I1c. source=sf_dataset", ds_rec["source"] == "sf_dataset")
            check("I1d. per_ats com rows por fatia",
                  ds_rec["per_ats"]["successfactors"]["rows"] == 1)
        check("I2. run.total_collected soma registry+dataset",
              run_rec is not None and run_rec["total_collected"] == 2,
              str(run_rec and run_rec["total_collected"]))


# ---------------------------------------------------------------------------
# J. CI membership
# ---------------------------------------------------------------------------

def test_ci_membership() -> None:
    print("== J. CI: test_f3 no array do workflow ==")
    root = Path(__file__).resolve().parent.parent
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    check("J1. tests=(...) inclui test_f3", "test_f3" in ci)


def main() -> int:
    test_prefilter()
    print()
    test_row_to_job()
    print()
    test_dedup_cross_source()
    print()
    test_registry_weight()
    print()
    test_hydration_sf_dataset()
    print()
    test_cli_dataset_flow()
    print()
    test_budget()
    print()
    test_registry_not_filter()
    print()
    test_jsonl_records()
    print()
    test_ci_membership()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
