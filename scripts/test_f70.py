"""F70 — dataset_seen: o caderno do universo pos-prefilter (test_f70).

Trava o comportamento NOVO da fase (writer append-only keys-only,
streaming pos-prefilter, best-effort TOTAL §7.8, backup estendido):

GRUPO A — Writer basico + schema (tmp db, append puro):
  A1. LAZY: construtor nao toca disco; arquivo so nasce no 1o write.
  A2. 3 writes -> 3 linhas; colunas/valores conformes (run_id, job_id,
      first_seen=last_seen=ts do run).
  A3. PRIMARY KEY (run_id, job_id) existe e e agressiva (INSERT direto
      duplicado -> IntegrityError — o OR IGNORE do writer e necessario).
  A4. Indice secundario dataset_seen_job_id existe (a query
      "esta vaga ja foi vista antes?" nao pode ser um scan).
  A5. Flush periodico: segunda conexao VE os primeiros commits ANTES do
      close (streaming com perda limitada a um flush).
  A6. close() idempotente.

GRUPO B — Idempotencia por run (INSERT OR IGNORE):
  B1. Mesmo job_id 2x no MESMO run -> 1 linha (written conta tentativas).
  B2. Dois writers no MESMO run_id (re-run) -> 1 linha; first_seen do
      PRIMEIRO preservado (linha ja gravada nunca e reescrita).
  B3. Runs diferentes -> linhas novas (append entre runs); MIN/MAX
      sobre job_id deriva o first/last REAL.

GRUPO C — Invariante §7.8 (best-effort TOTAL — caderno nunca derruba):
  C1. Caminho impossivel (pai e arquivo) -> write nao levanta; writer
      degradado (failed + error), virando no-op.
  C2. close() apos degradacao nao levanta.
  C3. Writes pos-degradacao sao no-op (written congela).
  C4. job_id vazio -> no-op silencioso (sem falha, sem linha).

GRUPO D — Reader (query do indice, tolerante):
  D1. Arquivo inexistente -> None. D2. Banco sem tabela -> None.
  D3. Vaga vista em 2 runs -> (MIN, MAX). D4. Vaga nunca vista -> None.

GRUPO E — Integracao STREAMING no estagio dataset (fixtures F80):
  E1. Jobs validos anotados no momento da criacao; rows pre-prefilter
      rejeitadas e rows invalidas (sem identidade) FORA do caderno.
  E2. Fatia failed (hash mismatch) -> jobs dela fora do caderno.
  E3. A/B: coleta com e sem caderno -> jobs e summary IDENTICOS (zero
      impacto no funil).
  E4. Caderno degradado NAO derruba a coleta (status ok, jobs intactos).
  E5. collect NAO injeta seen_* no summary (dono do ciclo de vida e o
      chamador — contrato documentado).

GRUPO F — CLI _run_dataset_stage (writer + forenses no registro):
  F1. Writer passado ao estagio; registro carrega seen_written; linhas
      no db tmp.
  F2. Estagio failed (excecao) -> registro failed + seen_written=0 +
      writer fechado SEM criar arquivo (lazy).
  F3. Writer degradado -> registro ok com seen_error greppavel; estagio
      segue com seus jobs.

GRUPO G — Backup estendido (stem + retencao + refresh integrado):
  G1. backup_filename retrocompat (jobs-) + stem dataset_seen.
  G2. jobs.db e dataset_seen.db no MESMO ts -> 2 artefatos distintos
      (sem colisao de nome no data/backups/).
  G3. Artefato standalone (sem sidecars WAL) e integro.
  G4. _parse_backup_ts aceita os 2 stems; stem desconhecido -> None
      (preservado pela retencao).
  G5. cleanup_backups remove jobs E dataset_seen velhos; preserva
      estranhos e novos.
  G6. Refresh integrado: rd.main cria jobs-<ts>.db E dataset_seen-<ts>.db;
      caderno de producao intacto (bytes iguais).

GRUPO H — Registro dataset (forenses JSONL):
  H1. seen_written/seen_error carregam no registro.
  H2. Retrocompat: summary sem os campos -> 0/None.
  H3. Serializa em JSON (greppavel no collection_metrics.jsonl).

GRUPO I — Invariante append-only (lock de fonte):
  I1. dataset_seen.py nao contem caminho de mutacao (UPDATE/DELETE).
  I2. Re-runs nunca alteram linhas antigas (bytes das linhas identicos).

GRUPO J — CI: test_f70 na suite descoberta (auto-discovery F78).

100% OFFLINE: manifest injetado, download via fakes, dbs em tmpdir —
zero rede, data/ intocada. Padrao da suite: [OK]/[FAIL] e termina com
``TUDO OK``.

Uso: .venv/bin/python scripts/test_f70.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ (refresh_daily)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.cli import _dataset_record, _run_dataset_stage  # noqa: E402
from internship_finder.dataset_seen import (  # noqa: E402
    SEEN_INDEX,
    SEEN_TABLE,
    DatasetSeenWriter,
    job_seen_history,
)
from internship_finder.dataset_source import (  # noqa: E402
    collect_dataset_jobs,
    row_to_job,
)
from internship_finder.storage.sqlite_backup import (  # noqa: E402
    _parse_backup_ts,
    backup_filename,
    backup_jobs_db,
    cleanup_backups,
)
import refresh_daily as rd  # noqa: E402
from internship_finder import cli as cli_mod  # noqa: E402

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
    """Fake de download: meta['csv'] aponta para arquivo LOCAL."""
    def fetch(url, dest):
        src = paths[str(url)]
        data = src.read_bytes()
        dest.write_bytes(data)
        return len(data), hashlib.sha256(data).hexdigest()
    return fetch


def seen_rows(db: Path) -> list[tuple]:
    """Todas as linhas do caderno (ordenadas) — leitura de teste."""
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(
            f"SELECT run_id, job_id, first_seen, last_seen FROM {SEEN_TABLE} "
            "ORDER BY run_id, job_id").fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# A. Writer basico + schema (append puro)
# ---------------------------------------------------------------------------

def test_writer_basico() -> None:
    print("== A. Writer: lazy, schema, PK, indice, flush ==")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "dataset_seen.db"
        w = DatasetSeenWriter(db, "run-1", seen_at="2026-10-20T09:00:00+00:00")
        check("A1a. LAZY: construtor nao cria arquivo", not db.exists())
        w.write("Acme|sf_dataset:acme:1")
        check("A1b. 1o write cria o arquivo", db.exists())
        w.write("Bosch|sf_dataset:acme:2")
        w.write("Zeiss|sf_dataset:acme:3")
        w.close()
        rows = seen_rows(db)
        check("A2a. 3 linhas (append puro)", len(rows) == 3, str(rows))
        check("A2b. colunas conformes (run_id, job_id, first, last)",
              all(r[0] == "run-1" and r[2] == r[3]
                  and r[2] == "2026-10-20T09:00:00+00:00" for r in rows),
              str(rows))
        check("A2c. job_id preservado literal",
              [r[1] for r in rows] == ["Acme|sf_dataset:acme:1",
                                       "Bosch|sf_dataset:acme:2",
                                       "Zeiss|sf_dataset:acme:3"], str(rows))

        conn = sqlite3.connect(str(db))
        dup = None
        try:
            # A3: a PK e real — INSERT direto duplicado explode (o OR
            # IGNORE do writer e o que mantem a idempotencia).
            conn.execute(
                f"INSERT INTO {SEEN_TABLE} (run_id, job_id, first_seen, last_seen) "
                "VALUES ('run-1', 'Acme|sf_dataset:acme:1', 'x', 'y')")
            conn.commit()
        except sqlite3.IntegrityError as exc:
            dup = str(exc)
        finally:
            conn.close()
        check("A3. PK (run_id, job_id) agressiva (INSERT dup -> IntegrityError)",
              dup is not None, str(dup))
        conn = sqlite3.connect(str(db))
        try:
            indexes = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                f"AND tbl_name='{SEEN_TABLE}'").fetchall()]
        finally:
            conn.close()
        check("A4. indice secundario em job_id existe",
              SEEN_INDEX in indexes, str(indexes))

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "seen_flush.db"
        w = DatasetSeenWriter(db, "run-f", seen_at="2026-10-20T09:00:00+00:00",
                              flush_every=2)
        w.write("j1")
        w.write("j2")
        w.write("j3")
        # A5: ANTES do close, uma segunda conexao ja ve o 1o flush
        # (commit periodico — streaming com perda limitada a um flush).
        conn = sqlite3.connect(str(db))
        try:
            visible = conn.execute(
                f"SELECT COUNT(*) FROM {SEEN_TABLE}").fetchone()[0]
        finally:
            conn.close()
        check("A5a. flush periodico visivel pre-close (2 de 3)", visible == 2,
              f"visivel={visible}")
        w.close()
        w.close()
        check("A5b. close final consolida (3 linhas)", len(seen_rows(db)) == 3)
        check("A6. close() idempotente (2x sem erro)", not w.failed)


# ---------------------------------------------------------------------------
# B. Idempotencia por run (INSERT OR IGNORE)
# ---------------------------------------------------------------------------

def test_idempotencia() -> None:
    print("== B. Idempotencia por run (INSERT OR IGNORE) ==")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "seen.db"
        w = DatasetSeenWriter(db, "run-1", seen_at="2026-10-20T09:00:00+00:00")
        w.write("job-a")
        w.write("job-a")  # mesma fatia 2x (row duplicada upstream)
        w.close()
        check("B1a. mesmo job 2x no mesmo run -> 1 linha",
              len(seen_rows(db)) == 1, str(seen_rows(db)))
        check("B1b. written conta TENTATIVAS (2)", w.written == 2, str(w.written))

        # B2: re-run do MESMO run_id (crash + retry) -> linha antiga
        # intocada, sem duplicar.
        w2 = DatasetSeenWriter(db, "run-1", seen_at="2026-10-20T10:30:00+00:00")
        w2.write("job-a")
        w2.close()
        rows = seen_rows(db)
        check("B2a. re-run mesmo run_id -> 1 linha (sem duplicata)",
              len(rows) == 1, str(rows))
        check("B2b. first_seen do PRIMEIRO writer preservado",
              len(rows) == 1 and rows[0][2] == "2026-10-20T09:00:00+00:00",
              str(rows))

        # B3: runs diferentes -> append; MIN/MAX deriva first/last real.
        w3 = DatasetSeenWriter(db, "run-2", seen_at="2026-10-20T12:00:00+00:00")
        w3.write("job-a")
        w3.close()
        rows = seen_rows(db)
        check("B3a. run novo -> linha nova (2 no total)", len(rows) == 2, str(rows))
        hist = job_seen_history(db, "job-a")
        check("B3b. MIN/MAX deriva (first, last) da vaga",
              hist == ("2026-10-20T09:00:00+00:00",
                       "2026-10-20T12:00:00+00:00"), str(hist))

# ---------------------------------------------------------------------------
# C. Invariante §7.8 — best-effort TOTAL
# ---------------------------------------------------------------------------

def test_best_effort() -> None:
    print("== C. §7.8: caderno degradado nunca derruba nada ==")
    with tempfile.TemporaryDirectory() as tmp:
        blocker = Path(tmp) / "arquivo.txt"
        blocker.write_text("sou um arquivo, nao diretorio", encoding="utf-8")
        broken_db = blocker / "dataset_seen.db"  # pai e ARQUIVO -> impossivel
        w = DatasetSeenWriter(broken_db, "run-x")
        raised: list[str] = []
        try:
            w.write("job-1")
            w.write("job-2")
            w.close()
        except Exception as exc:  # noqa: BLE001 — NAO deve acontecer
            raised.append(f"{type(exc).__name__}: {exc}")
        check("C1z. write/close NUNCA levantam (§7.8)", not raised,
              "; ".join(raised))
        check("C1a. write em caminho impossivel nao levanta", True)
        check("C1b. writer degradado (failed)", w.failed)
        check("C1c. forense error preenchida", bool(w.error), str(w.error))
        check("C1d. arquivo jamais criado", not broken_db.exists())
        w.write("job-3")
        check("C3. write pos-degradacao e no-op (written congela)",
              w.written == 0, str(w.written))
        w.close()
        w.close()
        check("C2. close apos degradacao e idempotente", True)

        # C4: job_id vazio — no-op silencioso (sem falha, sem linha)
        with tempfile.TemporaryDirectory() as tmp2:
            db2 = Path(tmp2) / "s.db"
            w4 = DatasetSeenWriter(db2, "run-y")
            w4.write("")
            w4.write(None)  # type: ignore[arg-type]
            w4.close()
            check("C4. job_id vazio/None -> sem falha, sem linha, sem arquivo",
                  not w4.failed and w4.written == 0 and not db2.exists(),
                  f"failed={w4.failed} written={w4.written}")


# ---------------------------------------------------------------------------
# D. Reader (a query do indice — tolerante por design)
# ---------------------------------------------------------------------------

def test_reader() -> None:
    print("== D. job_seen_history: query do indice, tolerante ==")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "s.db"
        check("D1. arquivo inexistente -> None",
              job_seen_history(db, "nada") is None)
        sqlite3.connect(str(db)).close()  # banco vazio SEM tabela
        check("D2. banco sem tabela -> None (sem crash)",
              job_seen_history(db, "nada") is None)
        w = DatasetSeenWriter(db, "r1", seen_at="2026-10-19T09:00:00+00:00")
        w.write("vista-2-runs")
        w.write("vista-1-run")
        w.close()
        w2 = DatasetSeenWriter(db, "r2", seen_at="2026-10-20T09:00:00+00:00")
        w2.write("vista-2-runs")
        w2.close()
        hist2 = job_seen_history(db, "vista-2-runs")
        check("D3. vaga de 2 runs -> (MIN, MAX)",
              hist2 == ("2026-10-19T09:00:00+00:00",
                        "2026-10-20T09:00:00+00:00"), str(hist2))
        hist1 = job_seen_history(db, "vista-1-run")
        check("D3b. vaga de 1 run -> (ts, ts)",
              hist1 == ("2026-10-19T09:00:00+00:00",
                        "2026-10-19T09:00:00+00:00"), str(hist1))
        check("D4. vaga nunca vista -> None",
              job_seen_history(db, "nunca-vista") is None)


# ---------------------------------------------------------------------------
# E. Integracao STREAMING no estagio dataset
# ---------------------------------------------------------------------------

def _two_slices(tmp: str) -> tuple[dict, dict, list]:
    """Duas fatias: aaa (1 valida + 1 rejeitada no prefilter + 1 invalida)
    e bbb (1 valida). Devolve (by_ats, paths, expected_job_ids)."""
    rows_a = [
        make_row(url="https://a/1", title="Werkstudent Analytics",
                 company="A GmbH", ats_id="11"),
        make_row(url="https://a/2", title="Senior Manager",  # nao-intern
                 company="A GmbH", ats_id="12"),
        make_row(url="https://a/3", title="Praktikum Einkauf",
                 company="", ats_id="13"),  # sem company -> invalida
    ]
    rows_b = [make_row(url="https://b/1", title="Working Student Data",
                       company="B GmbH", ats_id="21")]
    pa, pb = Path(tmp) / "fixture_aaa.csv", Path(tmp) / "fixture_bbb.csv"
    ha, hb = hashlib.sha256(write_csv(pa, rows_a)).hexdigest(), \
        hashlib.sha256(write_csv(pb, rows_b)).hexdigest()
    by = {
        "aaa": {"csv": str(pa), "rows": 3, "sha256": ha},
        "bbb": {"csv": str(pb), "rows": 1, "sha256": hb},
    }
    paths = {str(pa): pa, str(pb): pb}
    expected = ["A GmbH|sf_dataset:aaa:11", "B GmbH|sf_dataset:bbb:21"]
    return by, paths, expected


def test_integracao_dataset() -> None:
    print("== E. Integracao streaming no estagio dataset ==")
    with tempfile.TemporaryDirectory() as tmp:
        by, paths, expected = _two_slices(tmp)
        db = Path(tmp) / "seen.db"
        seen = DatasetSeenWriter(db, "run-e",
                                  seen_at="2026-10-20T09:00:00+00:00")
        jobs, summary = collect_dataset_jobs(
            manifest=full_manifest(by), http_fetch=fetch_from(paths),
            workdir=Path(tmp), seen=seen)
        seen.close()
        check("E1a. 2 jobs coletados (cenario basico)", len(jobs) == 2,
              str(len(jobs)))
        rows = seen_rows(db)
        check("E1b. caderno tem exatamente os 2 jobs validos",
              sorted(r[1] for r in rows) == sorted(expected), str(rows))
        check("E1c. row rejeitada no prefilter (nao-intern) FORA do caderno",
              not any(":12" in r[1] for r in rows), str(rows))
        check("E1d. row invalida (sem company, sem identidade) FORA",
              not any(":13" in r[1] for r in rows), str(rows))
        check("E1e. run_id anotado", all(r[0] == "run-e" for r in rows))
        check("E5. collect NAO injeta seen_* no summary (dono = chamador)",
              "seen_written" not in summary and "seen_error" not in summary,
              str(sorted(summary.keys())))

        # E2: fatia failed por hash -> seus jobs ficam FORA do caderno
        bad = dict(by)
        bad["bbb"] = {**by["bbb"], "sha256": "0" * 64}
        db2 = Path(tmp) / "seen2.db"
        seen2 = DatasetSeenWriter(db2, "run-e2",
                                  seen_at="2026-10-20T09:00:00+00:00")
        jobs2, s2 = collect_dataset_jobs(
            manifest=full_manifest(bad), http_fetch=fetch_from(paths),
            workdir=Path(tmp), seen=seen2)
        seen2.close()
        rows2 = [r[1] for r in seen_rows(db2)]
        check("E2a. fatia hash-mismatch failed", s2["failed_slices"] == 1)
        check("E2b. jobs da fatia corrompida fora do caderno",
              rows2 == ["A GmbH|sf_dataset:aaa:11"], str(rows2))

        # E3: A/B — com e sem caderno: jobs e summary IDENTICOS
        # (clock fake => duration deterministico; zero impacto no funil).
        by3, paths3, _ = _two_slices(tmp)
        jobs_no, s_no = collect_dataset_jobs(
            manifest=full_manifest(by3), http_fetch=fetch_from(paths3),
            workdir=Path(tmp), now=lambda: 0.0)
        db3 = Path(tmp) / "seen3.db"
        seen3 = DatasetSeenWriter(db3, "run-e3")
        jobs_w, s_w = collect_dataset_jobs(
            manifest=full_manifest(by3), http_fetch=fetch_from(paths3),
            workdir=Path(tmp), now=lambda: 0.0, seen=seen3)
        seen3.close()
        check("E3a. A/B: jobs identicos com/sem caderno",
              [j.id for j in jobs_no] == [j.id for j in jobs_w],
              f"{len(jobs_no)} vs {len(jobs_w)}")
        check("E3b. A/B: summary identico com/sem caderno",
              s_no == s_w, "diff de summary")

        # E4: caderno degradado NAO derruba a coleta
        blocker = Path(tmp) / "blk.txt"
        blocker.write_text("x", encoding="utf-8")
        seen4 = DatasetSeenWriter(blocker / "s.db", "run-e4")
        jobs4, s4 = collect_dataset_jobs(
            manifest=full_manifest(by), http_fetch=fetch_from(paths),
            workdir=Path(tmp), seen=seen4)
        seen4.close()
        check("E4a. coleta segue ok com caderno degradado",
              s4["status"] == "ok" and len(jobs4) == 2,
              f"{s4['status']}/{len(jobs4)}")
        check("E4b. writer degradado reportado no objeto (failed)",
              seen4.failed and bool(seen4.error), str(seen4.error))


# ---------------------------------------------------------------------------
# F. CLI _run_dataset_stage (writer + forenses no registro dataset)
# ---------------------------------------------------------------------------

def _fake_job(url: str, company: str, ats_id: str):
    row = make_row(url=url, title="Werkstudent F70", company=company,
                   ats_id=ats_id)
    job = row_to_job(row, "successfactors")
    assert job is not None  # fixture valida por construcao
    return job


def test_cli_stage() -> None:
    print("== F. CLI: _run_dataset_stage cria/fecha writer + registro ==")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "seen.db"
        j1 = _fake_job("https://a/1", "A GmbH", "1")
        j2 = _fake_job("https://b/1", "B GmbH", "2")

        def fake_collect(**kw):
            seen = kw.get("seen")
            assert seen is not None  # F70: o writer CHEGA ao estagio
            for j in (j1, j2):
                seen.write(j.id)
            return [j1, j2], {"status": "ok", "rows_total": 2,
                              "rows_prefiltered": 2, "invalid_rows": 0,
                              "jobs": 2, "per_ats": {}, "skipped_budget": 0,
                              "failed_slices": 0, "bytes_downloaded": 10,
                              "duration": 0.1}

        with mock.patch.object(cli_mod, "collect_dataset_jobs",
                               side_effect=fake_collect):
            jobs, record = _run_dataset_stage("run-f", 10.0, seen_db=db)
        assert record is not None  # _run_dataset_stage sempre devolve registro
        check("F1a. jobs do estagio preservados", len(jobs) == 2)
        check("F1b. registro carrega seen_written=2",
              record.get("seen_written") == 2, str(record.get("seen_written")))
        check("F1c. sem seen_error (caderno saudavel)",
              record.get("seen_error") is None, str(record.get("seen_error")))
        rows = seen_rows(db)
        check("F1d. linhas no db do estagio", sorted(r[1] for r in rows)
              == sorted([j1.id, j2.id]), str(rows))
        check("F1e. registro segue tendo os campos F80 (frescor)",
              "manifest_generated_at" in record)

        # F2: estagio failed — writer fechado SEM criar arquivo (lazy)
        db2 = Path(tmp) / "seen2.db"

        def boom(**kw):
            raise RuntimeError("manifest down")

        with mock.patch.object(cli_mod, "collect_dataset_jobs",
                               side_effect=boom):
            jobs2, record2 = _run_dataset_stage("run-f2", 10.0, seen_db=db2)
        assert record2 is not None
        check("F2a. estagio failed -> jobs vazios", jobs2 == [])
        check("F2b. registro status=failed",
              record2.get("status") == "failed")
        check("F2c. seen_written=0 no failed",
              record2.get("seen_written") == 0)
        check("F2d. writer fechado sem criar arquivo (lazy)",
              not db2.exists())

        # F3: writer degradado -> forense no registro; estagio segue ok
        blocker = Path(tmp) / "blk.txt"
        blocker.write_text("x", encoding="utf-8")

        def fake_collect_broken(**kw):
            seen = kw.get("seen")
            if seen is not None:
                seen.write(j1.id)
                seen.write(j2.id)
            return [j1, j2], {"status": "ok", "rows_total": 2,
                              "rows_prefiltered": 2, "invalid_rows": 0,
                              "jobs": 2, "per_ats": {}, "skipped_budget": 0,
                              "failed_slices": 0, "bytes_downloaded": 10,
                              "duration": 0.1}

        with mock.patch.object(cli_mod, "collect_dataset_jobs",
                               side_effect=fake_collect_broken):
            jobs3, record3 = _run_dataset_stage(
                "run-f3", 10.0, seen_db=blocker / "s.db")
        assert record3 is not None
        check("F3a. estagio segue ok com caderno degradado",
              record3.get("status") == "ok" and len(jobs3) == 2)
        check("F3b. seen_error greppavel no registro",
              bool(record3.get("seen_error")), str(record3.get("seen_error")))
        check("F3c. seen_written=0 (degradou no 1o write)",
              record3.get("seen_written") == 0)

# ---------------------------------------------------------------------------
# G. Backup estendido (stem dataset_seen + retencao + refresh integrado)
# ---------------------------------------------------------------------------

def _make_seen_db(path: Path) -> bytes:
    """Caderno sintetico (2 linhas, 1 run) — devolve o conteudo bruto."""
    w = DatasetSeenWriter(path, "run-sintetico",
                          seen_at="2026-10-20T09:00:00+00:00")
    w.write("A GmbH|sf_dataset:aaa:1")
    w.write("B GmbH|sf_dataset:bbb:2")
    w.close()
    return path.read_bytes()


def test_backup_estendido() -> None:
    print("== G. Backup: stem dataset_seen + retencao + refresh ==")
    ts = "20261020T090000Z"
    check("G1a. backup_filename retrocompat (jobs-)",
          backup_filename(ts) == f"jobs-{ts}.db", backup_filename(ts))
    check("G1b. stem dataset_seen",
          backup_filename(ts, "dataset_seen") == f"dataset_seen-{ts}.db")

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        data.mkdir()
        jobs_bytes = rd_test_jobs_db(data / "jobs.db")
        seen_bytes = _make_seen_db(data / "dataset_seen.db")
        # G2: MESMO ts, bancos distintos -> artefatos DISTINTOS (sem
        # colisao: o os.replace do segundo nao alcancaria o primeiro).
        b_jobs = backup_jobs_db(data / "jobs.db", ts=ts)
        b_seen = backup_jobs_db(data / "dataset_seen.db", ts=ts)
        check("G2a. artefato jobs-<ts>.db", b_jobs.name == f"jobs-{ts}.db",
              b_jobs.name)
        check("G2b. artefato dataset_seen-<ts>.db",
              b_seen.name == f"dataset_seen-{ts}.db", b_seen.name)
        check("G2c. dois arquivos distintos no mesmo diretorio",
              b_jobs != b_seen and b_jobs.exists() and b_seen.exists())
        check("G3a. backup standalone (sem sidecars WAL)",
              not (data / "backups" / f"dataset_seen-{ts}.db-wal").exists()
              and not (data / "backups" / f"dataset_seen-{ts}.db-shm").exists())
        conn = sqlite3.connect(str(b_seen))
        try:
            qc = conn.execute("PRAGMA quick_check").fetchone()[0]
            n = conn.execute(
                f"SELECT COUNT(*) FROM {SEEN_TABLE}").fetchone()[0]
        finally:
            conn.close()
        check("G3b. backup integro (quick_check ok) e COMPLETO (2 linhas)",
              qc == "ok" and n == 2, f"qc={qc} n={n}")
        check("G3c. origens intocadas (bytes iguais)",
              (data / "jobs.db").read_bytes() == jobs_bytes
              and (data / "dataset_seen.db").read_bytes() == seen_bytes)

        check("G4a. _parse_backup_ts aceita jobs-", bool(
            _parse_backup_ts(f"jobs-{ts}.db")))
        check("G4b. _parse_backup_ts aceita dataset_seen-", bool(
            _parse_backup_ts(f"dataset_seen-{ts}.db")))
        check("G4c. stem desconhecido -> None (preservado)",
              _parse_backup_ts(f"outro-{ts}.db") is None)
        check("G4d. formato quebrado -> None",
              _parse_backup_ts("dataset_seen-naoehdata.db") is None)

        # G5: retencao remove jobs E dataset_seen velhos; preserva outros
        old = "20200101T000000Z"
        bdir = data / "backups"
        (bdir / f"jobs-{old}.db").write_bytes(b"x")
        (bdir / f"dataset_seen-{old}.db").write_bytes(b"x")
        (bdir / f"dataset_seen-29990101T000000Z.db").write_bytes(b"x")
        (bdir / f"estranho-{old}.db").write_bytes(b"x")
        removed = cleanup_backups(bdir, retention_days=14)
        removed_names = sorted(p.name for p in removed)
        check("G5a. retencao remove jobs- E dataset_seen- velhos",
              removed_names == [f"dataset_seen-{old}.db", f"jobs-{old}.db"],
              str(removed_names))
        check("G5b. futuro e desconhecido preservados",
              (bdir / f"dataset_seen-29990101T000000Z.db").exists()
              and (bdir / f"estranho-{old}.db").exists())
        check("G5c. backups novos preservados",
              b_jobs.exists() and b_seen.exists())


def rd_test_jobs_db(path: Path) -> bytes:
    """jobs.db sintetico no padrao do test_refresh."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, title TEXT NOT NULL)")
    conn.execute("INSERT INTO jobs (id, title) VALUES ('sf:1', 'Working Student')")
    conn.commit()
    conn.close()
    return path.read_bytes()


def test_refresh_integrado() -> None:
    print("== G6. Refresh integrado: caderno no backup diario ==")
    import subprocess
    with tempfile.TemporaryDirectory(prefix="t_f70rd_") as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        data_dir.mkdir()
        (data_dir / "collection_metrics.jsonl").write_text("", encoding="utf-8")
        rd_test_jobs_db(data_dir / "jobs.db")
        seen_bytes = _make_seen_db(data_dir / "dataset_seen.db")
        original_root = rd.repo_root

        def fake_run(*args, **kwargs) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args[0], 0)

        def fake_notify(config, message, *, dry_run) -> dict:
            return {"sent": True}

        rd.repo_root = lambda: root
        try:
            with mock.patch.object(rd, "run_collection", side_effect=fake_run), \
                 mock.patch.object(rd, "disk_usage_pct", return_value=50), \
                 mock.patch.object(rd, "notify_or_log", side_effect=fake_notify):
                rc = rd.main(["--config", str(root / ".env")])
        finally:
            rd.repo_root = original_root
        check("G6a. refresh exit 0", rc == 0, f"rc={rc}")
        jobs_bk = sorted((data_dir / "backups").glob("jobs-*.db"))
        seen_bk = sorted((data_dir / "backups").glob("dataset_seen-*.db"))
        check("G6b. backup do jobs.db criado (1)", len(jobs_bk) == 1,
              str(jobs_bk))
        check("G6c. backup do dataset_seen.db criado (1)", len(seen_bk) == 1,
              str(seen_bk))
        check("G6d. caderno de producao intacto (bytes iguais)",
              (data_dir / "dataset_seen.db").read_bytes() == seen_bytes)


# ---------------------------------------------------------------------------
# H. Registro dataset (forenses JSONL)
# ---------------------------------------------------------------------------

def test_registro_dataset() -> None:
    print("== H. Registro dataset: seen_written/seen_error ==")
    summary = {"status": "ok", "rows_total": 100, "rows_prefiltered": 24,
               "jobs": 23, "seen_written": 23,
               "seen_error": "OSError: disco cheio"}
    rec = _dataset_record("run-h", summary)
    check("H1a. seen_written carregado", rec.get("seen_written") == 23,
          str(rec.get("seen_written")))
    check("H1b. seen_error carregado",
          rec.get("seen_error") == "OSError: disco cheio",
          str(rec.get("seen_error")))
    rec_old = _dataset_record("run-h2", {"status": "ok", "rows_total": 10,
                                         "rows_prefiltered": 1})
    check("H2a. retrocompat: sem campos -> seen_written 0",
          rec_old.get("seen_written") == 0, str(rec_old.get("seen_written")))
    check("H2b. retrocompat: sem campos -> seen_error None",
          rec_old.get("seen_error") is None)
    blob = json.dumps(rec)
    check("H3. serializa em JSON (greppavel no JSONL)",
          "seen_written" in blob and "seen_error" in blob)


# ---------------------------------------------------------------------------
# I. Invariante append-only (lock de fonte — nenhuma mutacao existe)
# ---------------------------------------------------------------------------

def test_append_only_lock() -> None:
    print("== I. Append-only: fonte sem caminho de mutacao ==")
    src = Path(__file__).resolve().parent.parent / "src" / \
        "internship_finder" / "dataset_seen.py"
    text = src.read_text(encoding="utf-8")
    check("I1a. sem UPDATE de tabela no modulo",
          "UPDATE dataset_seen" not in text and "UPDATE " not in text, "")
    check("I1b. sem DELETE no modulo", "DELETE" not in text, "")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "s.db"
        w = DatasetSeenWriter(db, "r1", seen_at="2026-10-19T09:00:00+00:00")
        w.write("job-x")
        w.close()
        before = seen_rows(db)
        w2 = DatasetSeenWriter(db, "r1", seen_at="2026-10-21T09:00:00+00:00")
        w2.write("job-x")  # re-run: OR IGNORE
        w2.close()
        w3 = DatasetSeenWriter(db, "r2", seen_at="2026-10-21T09:00:00+00:00")
        w3.write("job-y")
        w3.close()
        after = seen_rows(db)
        check("I2a. linha antiga NUNCA reescrita (bytes identicos)",
              before == [r for r in after if r[0] == "r1"], str(after))
        check("I2b. append puro: 2 linhas no total", len(after) == 2,
              str(after))


# ---------------------------------------------------------------------------
# J. CI membership (auto-discovery F78)
# ---------------------------------------------------------------------------

def test_ci_membership() -> None:
    print("== J. CI: test_f70 na suite descoberta (auto-discovery F78) ==")
    import ci_discover_tests  # F78: suite = descoberta de scripts/test_*.py
    names = ci_discover_tests.discover_tests()
    check("J1. suite descoberta do CI inclui test_f70",
          "test_f70" in names, f"{len(names)} suites")


def main() -> int:
    test_writer_basico()
    print()
    test_idempotencia()
    print()
    test_best_effort()
    print()
    test_reader()
    print()
    test_integracao_dataset()
    print()
    test_cli_stage()
    print()
    test_backup_estendido()
    print()
    test_refresh_integrado()
    print()
    test_registro_dataset()
    print()
    test_append_only_lock()
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
