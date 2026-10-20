"""F80 — Integridade do estagio dataset (test_f80).

Trava o comportamento NOVO da fase (guards L1/L2, counted!=declared,
frescor, zero-post-guard, sanidade KEY_BUILD):

GRUPO A — L1 validate_manifest (fail-loud, direto):
  A1. Manifest vivo-shape (version + stats.schema_version "2.0", colunas,
      by_ats) -> devolve by_ats.
  A2. stats.schema_version "3.0" -> ValueError.
  A3. version top-level "3.0" (stats ok) -> ValueError (guard escuta
      TODOS os candidatos presentes — probe passo 0: a versao vive
      duplicada no manifest vivo).
  A4. Sem versao alguma -> ValueError.
  A5. Coluna exigida pelo prefilter ausente -> ValueError com o NOME.
  A6. by_ats ausente -> ValueError.
  A7. stats ausente (sem schema_columns) -> ValueError.
  A8. Hatch: env INTERNSHIP_FINDER_ALLOW_SCHEMA_VERSION=9.9 libera SO a
      versao 9.9 (3.0 continua falhando; warn-only NAO existe).

GRUPO B — Guard VALENDO no caminho INJETADO (a armadilha da spec F80):
  B1. collect(manifest=<completo, versao 3.0>) -> status failed com
      ValueError no error, 0 jobs, SEM tocar o download (guard exercitado
      offline — guard dentro de fetch_manifest nao seria testado aqui).
  B2. collect(manifest bom) -> status ok + manifest_generated_at gravado
      no summary (frescor).

GRUPO C — fetch_manifest offline (file://):
  C1. Corpo nao-JSON (HTML/Cloudflare) -> ValueError claro com os
      primeiros chars do corpo (antes: erro critico de json.loads).
  C2. JSON valido -> devolve o manifest COMPLETO (by_ats DENTRO).

GRUPO D — L2 sha256 por fatia (streaming vs declarado):
  D1. Hash declarado CORRETO -> fatia ok, sem forenses.
  D2. Hash MISMATCH -> fatia failed + forenses hash_declared/hash_computed;
      DEMAIS fatias prosseguem; jobs da fatia corrompida AUSENTES.
  D3. Meta sem sha256 (injecao de teste) -> warning path, fatia processada.
  D4. _http_fetch REAL via file:// -> (bytes, sha256) corretos.

GRUPO E — counted != declared ("contadas" = TODAS as iteradas):
  E1. Divergencia -> fatia failed + rows_declared/rows_counted (forenses).
  E2. skipped_budget NAO gera falso positivo (fatia incompleta).
  E3. Fatia failed por hash NAO acumula counted!=declared.
  E4. Fatia meta 0/0 passa naturalmente.
  E5. rows declaradas AUSENTES no meta -> sem check, fatia ok.

GRUPO F — Frescor (gravação SEM limiar; o limiar e fase futura):
  F1. summary manifest_generated_at em toda execucao (B2 cobre; assert
      direto aqui).
  F2. _dataset_record ganha manifest_generated_at (par com timestamp).
  F3. Retrocompat: summary SEM o campo -> registro com None.

GRUPO G — Zero-post-guard (cli):
  G1. 0 prefilteradas + rows_total > 1M -> anomaly "zero_prefiltered".
  G2. Fronteira: rows_total == 1_000_000 exato -> SEM anomaly.
  G3. Prefilter normal -> SEM anomaly.

GRUPO H — Sanidade KEY_BUILD (row_to_job valida ats_type ANTES do source):
  H1-H6. "nan"/"None"/"NaN"/"  "/vazio/None/nao-string -> ValueError.
  H7. ats_type valido -> source/id corretos (regressao).
  H8. Integracao: fatia "nan" no manifest -> veneno CONFINADO (entry
      failed, 0 jobs com source envenenado, demais fatias ok).

GRUPO J — CI: test_f80 na suite descoberta (auto-discovery F78).

100% OFFLINE: manifest injetado, download via fakes/file:// — zero rede.
Padrao da suite: [OK]/[FAIL] e termina com ``TUDO OK``.

Uso: .venv/bin/python scripts/test_f80.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.cli import _dataset_record  # noqa: E402
from internship_finder.dataset_source import (  # noqa: E402
    ALLOWED_SCHEMA_VERSIONS,
    ALLOW_SCHEMA_VERSION_ENV,
    PREFILTER_REQUIRED_COLUMNS,
    _http_fetch,
    collect_dataset_jobs,
    fetch_manifest,
    row_to_job,
    validate_manifest,
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
) -> dict:
    row = {k: "" for k in DATASET_HEADER}
    row.update({
        "url": url, "title": title, "company": company,
        "ats_type": "successfactors", "ats_id": ats_id,
        "location": location, "country_iso": country_iso,
        "description": description, "employment_type": employment_type,
        "posted_at": posted_at,
    })
    return row


def write_csv(path: Path, rows: list[dict]) -> bytes:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=DATASET_HEADER, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path.read_bytes()


def full_manifest(
    by_ats: dict,
    *,
    version: str | None = "2.0",
    schema_version: str | None = "2.0",
    columns: list[str] | None = None,
    with_stats: bool = True,
    generated_at: str = "2026-10-20T14:30:04.258003+00:00",
) -> dict:
    """Manifest no shape VIVO (probe passo 0): version + stats + by_ats."""
    data: dict = {}
    if version is not None:
        data["version"] = version
    data["generated_at"] = generated_at
    if with_stats:
        data["stats"] = {
            "schema_version": schema_version,
            "schema_columns": list(columns if columns is not None else DATASET_HEADER),
        }
    data["by_ats"] = by_ats
    return data


def fetch_from(paths: dict[str, Path]):
    """Fake de download: meta['csv'] aponta para arquivo LOCAL; contrato
    F80 ``(bytes, sha256)`` — hash REAL do que foi escrito."""
    def fetch(url, dest):
        src = paths[str(url)]
        data = src.read_bytes()
        dest.write_bytes(data)
        return len(data), hashlib.sha256(data).hexdigest()
    return fetch


def raises_value_error(fn, *args, **kwargs) -> tuple[bool, str]:
    try:
        fn(*args, **kwargs)
    except ValueError as exc:
        return True, str(exc)
    return False, ""


# ---------------------------------------------------------------------------
# A. L1 validate_manifest (fail-loud)
# ---------------------------------------------------------------------------

def test_l1_validate() -> None:
    print("== A. L1 validate_manifest (allowlist versao + subset colunas) ==")
    by = {"acme": {"csv": "https://x/acme.csv", "rows": 1}}
    good = full_manifest(by)
    out = validate_manifest(good)
    check("A1. manifest vivo-shape -> by_ats", out == by, str(out))

    # hatch limpo: testes negativos nao podem herdar env do operador
    saved = os.environ.pop(ALLOW_SCHEMA_VERSION_ENV, None)
    try:
        ok, msg = raises_value_error(
            validate_manifest, full_manifest(by, schema_version="3.0"))
        check("A2. stats.schema_version 3.0 -> ValueError", ok, msg)
        check("A2b. mensagem nomeia a versao", "3.0" in msg, msg)

        ok, msg = raises_value_error(
            validate_manifest, full_manifest(by, version="3.0"))
        check("A3. version top-level 3.0 -> ValueError (guard escuta todos)",
              ok, msg)

        ok, msg = raises_value_error(
            validate_manifest, full_manifest(by, version=None, schema_version=None))
        check("A4. sem versao alguma -> ValueError", ok, msg)

        cols = [c for c in DATASET_HEADER if c != "posted_at"]
        ok, msg = raises_value_error(
            validate_manifest, full_manifest(by, columns=cols))
        check("A5. coluna exigida ausente -> ValueError", ok, msg)
        check("A5b. mensagem nomeia 'posted_at'", "posted_at" in msg, msg)

        no_by = full_manifest({})
        ok, msg = raises_value_error(validate_manifest, no_by)
        check("A6. by_ats vazio -> ValueError", ok, msg)

        ok, msg = raises_value_error(
            validate_manifest, full_manifest(by, with_stats=False))
        check("A7. sem stats/schema_columns -> ValueError", ok, msg)

        # hatch: libera SO a versao listada
        os.environ[ALLOW_SCHEMA_VERSION_ENV] = "9.9"
        out99 = validate_manifest(full_manifest(by, version="9.9", schema_version="9.9"))
        check("A8a. hatch env=9.9 libera manifest 9.9", out99 == by)
        ok, msg = raises_value_error(
            validate_manifest, full_manifest(by, schema_version="3.0"))
        check("A8b. hatch 9.9 NAO libera 3.0", ok, msg)
        del os.environ[ALLOW_SCHEMA_VERSION_ENV]
        # so UMA coluna nova upstream (SUBSET, nao igualdade): passa
        cols_plus = DATASET_HEADER + ["coluna_nova_upstream"]
        out_sub = validate_manifest(full_manifest(by, columns=cols_plus))
        check("A9. coluna NOVA upstream (subset) -> passa", out_sub == by)
        check("A10. constantes: allowlist {'2.0'} + 9 colunas exigidas",
              set(ALLOWED_SCHEMA_VERSIONS) == {"2.0"}
              and len(PREFILTER_REQUIRED_COLUMNS) == 9,
              f"allow={sorted(ALLOWED_SCHEMA_VERSIONS)}")
    finally:
        if saved is None:
            os.environ.pop(ALLOW_SCHEMA_VERSION_ENV, None)
        else:
            os.environ[ALLOW_SCHEMA_VERSION_ENV] = saved


# ---------------------------------------------------------------------------
# B. Guard VALENDO no caminho INJETADO (armadilha documentada)
# ---------------------------------------------------------------------------

def test_guard_injected_path() -> None:
    print("== B. L1 exercitado no caminho INJETADO (testes offline) ==")
    with tempfile.TemporaryDirectory() as tmp:
        rows = [make_row(url="https://a/1", title="Werkstudent Analytics",
                         company="Acme GmbH")]
        csv_path = Path(tmp) / "slice.csv"
        write_csv(csv_path, rows)
        by = {"acme": {"csv": str(csv_path), "rows": 1}}
        bad = full_manifest(by, version="3.0")
        calls = {"n": 0}

        def _fetch(url, dest):
            calls["n"] += 1
            return 0, "x"

        jobs, summary = collect_dataset_jobs(
            manifest=bad, http_fetch=_fetch, workdir=Path(tmp))
        check("B1a. manifest 3.0 injetado -> status failed",
              summary.get("status") == "failed", str(summary))
        check("B1b. error carrega ValueError",
              "ValueError" in str(summary.get("error")), str(summary.get("error")))
        check("B1c. 0 jobs (guard aborta antes do loop)", not jobs)
        check("B1d. download NUNCA chamado (aborto no gargalo)",
              calls["n"] == 0, f"calls={calls['n']}")
        check("B1e. manifest_generated_at None (sem manifest valido)",
              summary.get("manifest_generated_at") is None)

        good = full_manifest(by)
        jobs2, summary2 = collect_dataset_jobs(
            manifest=good, http_fetch=fetch_from({str(csv_path): csv_path}),
            workdir=Path(tmp))
        check("B2a. manifest bom injetado -> status ok",
              summary2.get("status") == "ok", str(summary2))
        check("B2b. frescor: manifest_generated_at gravado no summary",
              summary2.get("manifest_generated_at")
              == "2026-10-20T14:30:04.258003+00:00",
              str(summary2.get("manifest_generated_at")))
        check("B2c. 1 job coletado (caminho injetado segue vivo)",
              summary2.get("jobs") == 1)


# ---------------------------------------------------------------------------
# C. fetch_manifest offline (file://)
# ---------------------------------------------------------------------------

def test_fetch_manifest_offline() -> None:
    print("== C. fetch_manifest: corpo nao-JSON -> erro claro ==")
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "wall.html"
        html.write_text(
            "<!DOCTYPE html><html><body>Cloudflare wall</body></html>",
            encoding="utf-8")
        ok, msg = raises_value_error(fetch_manifest, html.as_uri())
        check("C1a. corpo HTML -> ValueError", ok, msg)
        check("C1b. mensagem mostra o comeco do corpo (~200 chars)",
              "<!DOCTYPE html>" in msg, msg)
        check("C1c. mensagem diz que nao e JSON", "nao e JSON" in msg, msg)

        good = Path(tmp) / "manifest.json"
        payload = full_manifest({"acme": {"csv": "https://x/a.csv", "rows": 1}})
        good.write_text(json.dumps(payload), encoding="utf-8")
        data = fetch_manifest(good.as_uri())
        check("C2a. JSON valido -> manifest COMPLETO (by_ats DENTRO)",
              isinstance(data, dict) and "by_ats" in data and "stats" in data,
              str(sorted(data.keys())))
        check("C2b. by_ats preservado", data["by_ats"]["acme"]["rows"] == 1)


# ---------------------------------------------------------------------------
# D. L2 sha256 por fatia
# ---------------------------------------------------------------------------

def test_l2_sha256() -> None:
    print("== D. L2 sha256 por fatia (streaming vs declarado) ==")
    with tempfile.TemporaryDirectory() as tmp:
        rows_a = [make_row(url="https://a/1", title="Werkstudent Analytics",
                           company="A GmbH"),
                  make_row(url="https://a/2", title="Praktikum Einkauf",
                           company="A GmbH")]
        rows_b = [make_row(url="https://b/1", title="Working Student Data",
                           company="B GmbH")]
        pa, pb = Path(tmp) / "a.csv", Path(tmp) / "b.csv"
        ha = hashlib.sha256(write_csv(pa, rows_a)).hexdigest()
        hb = hashlib.sha256(write_csv(pb, rows_b)).hexdigest()
        by = {
            "acme": {"csv": str(pa), "rows": 2, "sha256": ha},
            "broken": {"csv": str(pb), "rows": 1, "sha256": "0" * 64},
        }
        jobs, summary = collect_dataset_jobs(
            manifest=full_manifest(by),
            http_fetch=fetch_from({str(pa): pa, str(pb): pb}),
            workdir=Path(tmp))
        e_ok = summary["per_ats"]["acme"]
        e_bad = summary["per_ats"]["broken"]
        check("D1a. hash correto -> fatia ok", e_ok["failed"] is False, str(e_ok))
        check("D1b. sem forenses na fatia ok",
              "hash_declared" not in e_ok and "hash_computed" not in e_ok)
        check("D2a. hash MISMATCH -> fatia failed", e_bad["failed"] is True,
              str(e_bad))
        check("D2b. forenses hash_declared/hash_computed",
              e_bad.get("hash_declared") == "0" * 64
              and e_bad.get("hash_computed") == hb, str(e_bad))
        check("D2c. failed_slices == 1", summary["failed_slices"] == 1,
              str(summary["failed_slices"]))
        check("D2d. fatia corrompida NAO vira jobs (prefilter pulado)",
              not any(j.url == "https://b/1" for j in jobs))
        check("D2e. DEMAIS fatias prosseguem",
              e_ok["kept"] == 2 and summary["jobs"] == 2,
              str(summary["per_ats"]))
        check("D2f. fatia corrompida: rows nao contadas no acervo",
              e_bad.get("rows", 0) == 0 and summary["rows_total"] == 2,
              str(summary["rows_total"]))

        by3 = {"acme": {"csv": str(pa), "rows": 2}}  # SEM sha256 (injecao)
        jobs3, s3 = collect_dataset_jobs(
            manifest=full_manifest(by3), http_fetch=fetch_from({str(pa): pa}),
            workdir=Path(tmp))
        check("D3a. meta sem sha256 -> fatia processada (warning path)",
              s3["per_ats"]["acme"]["failed"] is False
              and s3["jobs"] == 2, str(s3["per_ats"]))
        check("D3b. sem forenses", "hash_declared" not in s3["per_ats"]["acme"])

        dest = Path(tmp) / "down.bin"
        nbytes, digest = _http_fetch(pa.as_uri(), dest)
        expected = pa.read_bytes()
        check("D4a. _http_fetch REAL: devolve (bytes, sha256) do arquivo",
              nbytes == len(expected)
              and digest == hashlib.sha256(expected).hexdigest(),
              f"n={nbytes} sha={digest[:12]}")
        check("D4b. conteudo em disco idempotente", dest.read_bytes() == expected)


# ---------------------------------------------------------------------------
# E. counted != declared por fatia
# ---------------------------------------------------------------------------

def test_counted_declared() -> None:
    print("== E. counted != declared ('contadas' = TODAS as iteradas) ==")
    with tempfile.TemporaryDirectory() as tmp:
        # E1: declara 5, csv tem 3 (2 kept) -> divergencia
        rows = [make_row(url="https://a/1", title="Werkstudent A", company="A GmbH"),
                make_row(url="https://a/2", title="Praktikum B", company="A GmbH"),
                make_row(url="https://a/3", title="Senior Manager", company="A GmbH")]
        pa = Path(tmp) / "a.csv"
        sha = hashlib.sha256(write_csv(pa, rows)).hexdigest()
        by = {"acme": {"csv": str(pa), "rows": 5, "sha256": sha}}
        jobs, summary = collect_dataset_jobs(
            manifest=full_manifest(by), http_fetch=fetch_from({str(pa): pa}),
            workdir=Path(tmp))
        e = summary["per_ats"]["acme"]
        check("E1a. divergencia -> fatia failed", e["failed"] is True, str(e))
        check("E1b. forenses rows_declared=5/rows_counted=3",
              e.get("rows_declared") == 5 and e.get("rows_counted") == 3, str(e))
        check("E1c. failed_slices == 1", summary["failed_slices"] == 1)
        check("E1d. 'contadas' = TODAS iteradas (3, nao so as 2 kept)",
              summary["rows_total"] == 3, str(summary["rows_total"]))
        check("E1e. design: jobs da fatia divergente PERMANECEM (best-effort "
              "+ forenses; documentado no relatorio)",
              summary["jobs"] == 2, str(summary["jobs"]))

        # E2: skipped_budget NAO gera falso positivo (fatia INCOMPLETA)
        pb = Path(tmp) / "b.csv"
        write_csv(pb, [make_row(url="https://b/1", title="Werkstudent B",
                                company="B GmbH")])
        by2 = {"acme": {"csv": str(pa), "rows": 3, "sha256": sha},
               "zzz": {"csv": str(pb), "rows": 999, "sha256": "f" * 64}}
        clock = {"t": 0.0}

        def now() -> float:
            return clock["t"]

        def fetch_adv(url, dest):
            src = pa if str(url) == str(pa) else pb
            data = src.read_bytes()
            dest.write_bytes(data)
            clock["t"] += 10.0
            return len(data), hashlib.sha256(data).hexdigest()

        jobs2, s2 = collect_dataset_jobs(
            manifest=full_manifest(by2), budget_seconds=5.0, now=now,
            http_fetch=fetch_adv, workdir=Path(tmp))
        e_zzz = s2["per_ats"]["zzz"]
        check("E2a. 2a fatia skipped_budget (clock fake)",
              e_zzz["skipped_budget"] is True, str(e_zzz))
        check("E2b. skipped_budget SEM falso positivo counted!=declared",
              "rows_declared" not in e_zzz and "rows_counted" not in e_zzz,
              str(e_zzz))
        check("E2c. failed_slices == 0", s2["failed_slices"] == 0,
              str(s2["failed_slices"]))

        # E3: fatia failed por hash NAO acumula counted!=declared
        by3 = {"acme": {"csv": str(pa), "rows": 999, "sha256": "0" * 64}}
        jobs3, s3 = collect_dataset_jobs(
            manifest=full_manifest(by3), http_fetch=fetch_from({str(pa): pa}),
            workdir=Path(tmp))
        e3 = s3["per_ats"]["acme"]
        check("E3a. hash mismatch -> failed SEM forenses de rows",
              e3["failed"] is True and "rows_declared" not in e3, str(e3))
        check("E3b. failed_slices == 1 (nao 2)", s3["failed_slices"] == 1)

        # E4: fatia meta 0/0 passa naturalmente
        pmeta = Path(tmp) / "meta.csv"
        write_csv(pmeta, [])
        by4 = {"meta": {"csv": str(pmeta), "rows": 0,
                        "sha256": hashlib.sha256(pmeta.read_bytes()).hexdigest()}}
        jobs4, s4 = collect_dataset_jobs(
            manifest=full_manifest(by4),
            http_fetch=fetch_from({str(pmeta): pmeta}), workdir=Path(tmp))
        e4 = s4["per_ats"]["meta"]
        check("E4a. fatia meta 0/0 passa (0==0)",
              e4["failed"] is False and e4["rows"] == 0, str(e4))

        # E5: rows AUSENTES no meta (injecao) -> sem check
        by5 = {"acme": {"csv": str(pa), "sha256": sha}}
        jobs5, s5 = collect_dataset_jobs(
            manifest=full_manifest(by5), http_fetch=fetch_from({str(pa): pa}),
            workdir=Path(tmp))
        check("E5a. meta sem 'rows' -> fatia ok (sem falso positivo)",
              s5["per_ats"]["acme"]["failed"] is False,
              str(s5["per_ats"]["acme"]))


# ---------------------------------------------------------------------------
# F. Frescor (gravacao SEM limiar — o limiar e fase futura com historico)
# ---------------------------------------------------------------------------

def test_freshness_record() -> None:
    print("== F. Frescor: par (run_ts, generated_at) gravado SEM limiar ==")
    summary = {"status": "ok", "rows_total": 100, "rows_prefiltered": 5,
               "manifest_generated_at": "2026-10-19T14:30:04.258003+00:00"}
    rec = _dataset_record("run_x", summary)
    check("F2a. registro dataset ganha manifest_generated_at",
          rec.get("manifest_generated_at") == "2026-10-19T14:30:04.258003+00:00",
          str(rec.get("manifest_generated_at")))
    check("F2b. registro tem timestamp do run (par completo)",
          bool(rec.get("timestamp")))
    rec_old = _dataset_record("run_y", {"status": "ok", "rows_total": 10,
                                        "rows_prefiltered": 1})
    check("F3. retrocompat: summary SEM o campo -> registro com None",
          rec_old.get("manifest_generated_at") is None,
          str(rec_old.get("manifest_generated_at")))
    check("F4. SEM limiar/alerta de frescor nesta fase (so o par)",
          "fresh" not in json.dumps(rec).lower()
          and "stale" not in json.dumps(rec).lower())


# ---------------------------------------------------------------------------
# G. Zero-post-guard (anomalia estrutural greppavel)
# ---------------------------------------------------------------------------

def test_zero_post_guard() -> None:
    print("== G. Zero-post-guard (0 prefilteradas E acervo > 1M) ==")
    base = {"status": "ok", "invalid_rows": 721, "jobs": 0,
            "manifest_generated_at": "2026-10-19T14:30:04+00:00"}
    rec1 = _dataset_record(
        "r1", {**base, "rows_total": 5_805_212, "rows_prefiltered": 0})
    check("G1a. colapso silencioso -> anomaly zero_prefiltered",
          rec1.get("anomaly") == "zero_prefiltered", str(rec1))
    check("G1b. greppavel no JSONL (serializa)",
          "zero_prefiltered" in json.dumps(rec1))
    rec2 = _dataset_record(
        "r2", {**base, "rows_total": 1_000_000, "rows_prefiltered": 0})
    check("G2. fronteira 1M exato -> SEM anomaly (>)",
          "anomaly" not in rec2, str(rec2.get("anomaly")))
    rec3 = _dataset_record(
        "r3", {**base, "rows_total": 5_805_212, "rows_prefiltered": 24_526})
    check("G3. prefilter normal -> SEM anomaly", "anomaly" not in rec3)
    rec4 = _dataset_record(
        "r4", {"status": "failed", "rows_total": 0, "rows_prefiltered": 0})
    check("G4. estagio failed 0/0 -> SEM anomaly (sem acervo)",
          "anomaly" not in rec4)


# ---------------------------------------------------------------------------
# H. Sanidade KEY_BUILD (ats_type validado ANTES de compor source)
# ---------------------------------------------------------------------------

def test_key_build_sanity() -> None:
    print("== H. KEY_BUILD: ats_type 'nan'/'None'/vazio -> ValueError ==")
    row = make_row(url="https://a/1", title="Praktikum Data", company="Acme GmbH")
    for label, bad in [("H1. 'nan'", "nan"), ("H2. 'None'", "None"),
                       ("H3. 'NaN' (case-insensitive)", "NaN"),
                       ("H4. so espacos", "   "), ("H5. vazio", "")]:
        ok, msg = raises_value_error(row_to_job, row, bad)
        check(f"{label} -> ValueError", ok, msg)
    ok, msg = raises_value_error(row_to_job, row, None)
    check("H5b. None -> ValueError", ok, msg)
    ok, msg = raises_value_error(row_to_job, row, 123)
    check("H5c. nao-string (123) -> ValueError", ok, msg)

    job = row_to_job(row, "successfactors")
    check("H7a. ats_type valido -> source sf_dataset:successfactors",
          job is not None and job.source == "sf_dataset:successfactors",
          job.source if job else "None")
    check("H7b. id escopado company|sf_dataset:ats:ats_id",
          job is not None and job.id == "Acme GmbH|sf_dataset:successfactors:1",
          job.id if job else "None")

    # H8: integracao — fatia "nan" no manifest -> veneno CONFINADO
    with tempfile.TemporaryDirectory() as tmp:
        rows_a = [make_row(url="https://a/1", title="Werkstudent A",
                           company="A GmbH")]
        pa = Path(tmp) / "a.csv"
        write_csv(pa, rows_a)
        by = {"acme": {"csv": str(pa), "rows": 1},
              "nan": {"csv": str(pa), "rows": 1}}
        jobs, summary = collect_dataset_jobs(
            manifest=full_manifest(by), http_fetch=fetch_from({str(pa): pa}),
            workdir=Path(tmp))
        e_nan = summary["per_ats"]["nan"]
        check("H8a. fatia 'nan' -> failed (veneno confinado)",
              e_nan["failed"] is True, str(e_nan))
        check("H8b. NENHUM job com source envenenado",
              not any("nan" in (j.source or "") for j in jobs),
              str([j.source for j in jobs]))
        check("H8c. fatia sao prossegue (acme ok, 1 job)",
              summary["per_ats"]["acme"]["failed"] is False
              and summary["jobs"] == 1, str(summary["per_ats"]))
        check("H8d. failed_slices == 1", summary["failed_slices"] == 1)


# ---------------------------------------------------------------------------
# J. CI membership (auto-discovery F78)
# ---------------------------------------------------------------------------

def test_ci_membership() -> None:
    print("== J. CI: test_f80 na suite descoberta (auto-discovery F78) ==")
    import ci_discover_tests  # F78: suite = descoberta de scripts/test_*.py
    names = ci_discover_tests.discover_tests()
    check("J1. suite descoberta do CI inclui test_f80",
          "test_f80" in names, f"{len(names)} suites")


def main() -> int:
    test_l1_validate()
    print()
    test_guard_injected_path()
    print()
    test_fetch_manifest_offline()
    print()
    test_l2_sha256()
    print()
    test_counted_declared()
    print()
    test_freshness_record()
    print()
    test_zero_post_guard()
    print()
    test_key_build_sanity()
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
