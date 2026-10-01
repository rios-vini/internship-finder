"""F1 — desligar componentes mortos (scripts/test_f1.py).

Auditoria F1 (01/10/2026) concluiu que 3 componentes consomem recurso sem
gerar valor. Esta suíte trava o NOVO comportamento (tudo OFF por default,
caminhos preservados sob demanda) e verifica os invariantes da fase:

GRUPO A — Enrichment LLM (gate de configuracao):
  A1. ``run_enrichment`` SEM ``INTERNSHIP_FINDER_ENRICHMENT=1`` (env OU
      .env) NUNCA dispara o subprocesso — mesmo com ``--enrichment`` e
      NVIDIA_API_KEY presentes (o cron de producao passa --enrichment e
      roda sem a env var: enrichment OFF).
  A2. Gate abre COM a env var (reativacao manual sob demanda).
  A3. Gate via ``.env`` (mesmo caminho da NVIDIA_API_KEY).
  A4. Gate de publicacao continua ANTERIOR ao gate F1 (exit 124/eligible 0
      -> pulado antes, log correto).
  A5. Teto ``--enrichment-max-secs``: subprocesso roda COM timeout;
      ``TimeoutExpired`` vira log de UMA linha e o refresh NUNCA derruba
      (defesa do flock — o run de 5h38 da janela NVIDIA degradada).
  A6. Default do teto = 1800s.

GRUPO B — Deadline hydration (flag ``INTERNSHIP_FINDER_DEADLINE_HYDRATION``):
  B1. Default OFF: adapter NAO hidrata ``application_deadline`` (auditoria
      231/231: valor SF = validade do feed g:expiration_date, collected+30d,
      nao prazo real de fechamento).
  B2. Flag ON: caminho completo preservado (parse, aware UTC, offset).
  B3. Flag ON: invalido -> None; ausente -> None (contrato P1.4 intacto).
  B4. Persistencia SQLite do campo preservada quando hidratado (schema nao
      mudou — o gate e apenas na populacao).

GRUPO C — Ranking sem campos mortos (criterio de pronto F1):
  C1. ``ranking.score_job``: score IDENTICO com e sem application_deadline
      (o campo morto nao influencia ranking).
  C2. ``filters.select_eligible``: eligibility IDENTICA com e sem o campo.
  C3. ``dedup.deduplicate``: chaves de dedup ignoram o campo (pre-existente;
      re-verificado).
  C4. Fonte de verdade por inspecao: nenhum modulo de ranking/filters/dedup
      referencia ``application_deadline`` (grep de contrato).

GRUPO D — Official-page (default OFF):
  D1. Parser do CLI: ``--official-page`` default False (o cron nao passa a
      flag; producao roda com o default).
  D2. ``run_filter_pipeline`` default ``official_page=False``: o estagio
      NAO roda e NENHUM registro ``type: official_page`` e gravado nas
      metricas.
  D3. ``--official-page`` explicito reativa o estagio (uso sob demanda) e
      grava o registro de metricas.

GRUPO E — Operacao (flock nunca preso):
  E1. refresh sem a env flag termina SEM subprocesso de enrichment pendente
      (ordem: mensagem -> enrichment; nada apos o gate pulado).
  E2. O runner standalone continua com lock flock proprio (SO) — o
      codigo preservado nao regrediu no contrato de concorrencia.

Uso:
    .venv/bin/python scripts/test_f1.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest.mock as mock
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

FAILURES: list[str] = []

ENRICH_FLAG = "INTERNSHIP_FINDER_ENRICHMENT"
DEADLINE_FLAG = "INTERNSHIP_FINDER_DEADLINE_HYDRATION"


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def _tenant_run_record(rid: str = "r1", total: int = 400, eligible: int = 50) -> dict:
    return {"type": "run", "run_id": rid, "timestamp": rid,
            "total_collected": total, "filtered": 60, "dedup_removed": 0,
            "eligible": eligible}


# ---------------------------------------------------------------------------
# A. Enrichment LLM — gate de configuracao + teto de tempo
# ---------------------------------------------------------------------------

_REAL_RUN = subprocess.run


def _make_spy(calls: dict, exit_code: int):
    real_run = _REAL_RUN

    def fake(command, *args, **kwargs):
        if any("enrichment_run.py" in str(c) for c in command):
            calls["subproc"].append(
                (command, kwargs.get("cwd"), kwargs.get("env"),
                 kwargs.get("timeout")))
            return subprocess.CompletedProcess(command, exit_code)
        return real_run(command, *args, **kwargs)

    return fake


def _run_refresh_with(root: Path, argv: list[str]) -> int:
    import refresh_daily as rd

    metrics = root / "data" / "collection_metrics.jsonl"
    metrics.parent.mkdir(parents=True, exist_ok=True)
    if not metrics.exists():
        metrics.write_text("", encoding="utf-8")

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess:
        with metrics.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_tenant_run_record()) + "\n")
        return subprocess.CompletedProcess(args[0], 0)

    original_root = rd.repo_root
    rd.repo_root = lambda: root
    try:
        with mock.patch.object(rd, "run_collection", side_effect=fake_run), \
             mock.patch.object(rd, "notify_or_log",
                               return_value={"sent": True}), \
             mock.patch.object(rd.subprocess, "run", side_effect=None):
            return rd.main(argv)
    finally:
        rd.repo_root = original_root


def test_a_enrichment_gate() -> None:
    print("== A: enrichment LLM — gate de configuração F1 ==")
    import refresh_daily as rd

    # A1: sem env flag (nem env, nem .env) -> subprocesso NUNCA roda,
    # mesmo com --enrichment + NVIDIA_API_KEY presentes.
    with tempfile.TemporaryDirectory(prefix="t_f1_a1_") as tmp:
        root = Path(tmp)
        calls: dict = {"subproc": []}
        saved_key = os.environ.pop("NVIDIA_API_KEY", None)
        saved_flag = os.environ.pop(ENRICH_FLAG, None)
        os.environ["NVIDIA_API_KEY"] = "fake-key-f1"
        rd.repo_root = lambda: root
        try:
            rc = _run_refresh_with_spy(root, calls, 0,
                                        ["--config", str(root / ".env"),
                                         "--enrichment"])
        finally:
            os.environ.pop("NVIDIA_API_KEY", None)
            if saved_key is not None:
                os.environ["NVIDIA_API_KEY"] = saved_key
            if saved_flag is not None:
                os.environ[ENRICH_FLAG] = saved_flag
        check("A1. --enrichment SEM env flag F1: subprocesso NAO roda "
              "(cron de producao)", rc == 0 and calls["subproc"] == [])

    # A2: COM a env flag -> subprocesso roda (reativacao sob demanda).
    with tempfile.TemporaryDirectory(prefix="t_f1_a2_") as tmp:
        root = Path(tmp)
        calls: dict = {"subproc": []}
        saved_key = os.environ.pop("NVIDIA_API_KEY", None)
        saved_flag = os.environ.pop(ENRICH_FLAG, None)
        os.environ["NVIDIA_API_KEY"] = "fake-key-f1"
        os.environ[ENRICH_FLAG] = "1"
        try:
            rc = _run_refresh_with_spy(root, calls, 0,
                                        ["--config", str(root / ".env"),
                                         "--enrichment"])
        finally:
            os.environ.pop(ENRICH_FLAG, None)
            if saved_flag is not None:
                os.environ[ENRICH_FLAG] = saved_flag
            os.environ.pop("NVIDIA_API_KEY", None)
            if saved_key is not None:
                os.environ["NVIDIA_API_KEY"] = saved_key
        check("A2. COM env flag F1=1: subprocesso roda", rc == 0 and len(calls["subproc"]) == 1)

    # A3: gate via .env (injecao a partir do config, sem environ).
    with tempfile.TemporaryDirectory(prefix="t_f1_a3_") as tmp:
        root = Path(tmp)
        (root / ".env").write_text(
            "NVIDIA_API_KEY=fake\n" + ENRICH_FLAG + "=1\n", encoding="utf-8")
        calls: dict = {"subproc": []}
        saved_key = os.environ.pop("NVIDIA_API_KEY", None)
        saved_flag = os.environ.pop(ENRICH_FLAG, None)
        try:
            rc = _run_refresh_with_spy(root, calls, 0,
                                        ["--config", str(root / ".env"),
                                         "--enrichment"])
        finally:
            os.environ.pop(ENRICH_FLAG, None)
            if saved_flag is not None:
                os.environ[ENRICH_FLAG] = saved_flag
            os.environ.pop("NVIDIA_API_KEY", None)
            if saved_key is not None:
                os.environ["NVIDIA_API_KEY"] = saved_key
        check("A3. gate F1 via .env: subprocesso roda", rc == 0 and len(calls["subproc"]) == 1)

    # A4: gate de publicacao ANTES do gate F1: exit 124 nunca roda
    # enrichment (mesmo com env flag ligada — refresh invalido).
    with tempfile.TemporaryDirectory(prefix="t_f1_a4_") as tmp:
        root = Path(tmp)
        metrics = root / "data" / "collection_metrics.jsonl"
        metrics.parent.mkdir(parents=True, exist_ok=True)
        metrics.write_text("", encoding="utf-8")
        calls: dict = {"subproc": []}
        import refresh_daily as rd
        original_root = rd.repo_root
        saved_key = os.environ.pop("NVIDIA_API_KEY", None)
        saved_flag = os.environ.pop(ENRICH_FLAG, None)
        os.environ["NVIDIA_API_KEY"] = "fake-key-f1"
        os.environ[ENRICH_FLAG] = "1"
        rd.repo_root = lambda: root
        try:
            with mock.patch.object(rd, "run_collection",
                                   return_value=subprocess.CompletedProcess([], 124)), \
                 mock.patch.object(rd, "notify_or_log",
                                   return_value={"sent": True}), \
                 mock.patch.object(rd.subprocess, "run",
                                   side_effect=_make_spy(calls, 0)):
                rc = rd.main(["--config", str(root / ".env"), "--enrichment"])
        finally:
            rd.repo_root = original_root
            os.environ.pop(ENRICH_FLAG, None)
            if saved_flag is not None:
                os.environ[ENRICH_FLAG] = saved_flag
            os.environ.pop("NVIDIA_API_KEY", None)
            if saved_key is not None:
                os.environ["NVIDIA_API_KEY"] = saved_key
        check("A4. exit 124 + env flag: gate de publicacao nega ANTES do F1",
              rc == 124 and calls["subproc"] == [])

    # A5: teto de tempo — TimeoutExpired vira log, refresh segue.
    with tempfile.TemporaryDirectory(prefix="t_f1_a5_") as tmp:
        root = Path(tmp)
        metrics = root / "data" / "collection_metrics.jsonl"
        metrics.parent.mkdir(parents=True, exist_ok=True)
        metrics.write_text("", encoding="utf-8")
        calls: dict = {"subproc": []}

        def fake_timeout(command, *args, **kwargs):
            if any("enrichment_run.py" in str(c) for c in command):
                calls["subproc"].append((command, kwargs.get("timeout")))
                raise subprocess.TimeoutExpired(command, kwargs.get("timeout") or 0)
            return real_run(command, *args, **kwargs)

        import refresh_daily as rd
        original_root = rd.repo_root
        saved_key = os.environ.pop("NVIDIA_API_KEY", None)
        saved_flag = os.environ.pop(ENRICH_FLAG, None)
        os.environ["NVIDIA_API_KEY"] = "fake-key-f1"
        os.environ[ENRICH_FLAG] = "1"
        rd.repo_root = lambda: root

        def fake_coll(*args, **kwargs) -> subprocess.CompletedProcess:
            with metrics.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(_tenant_run_record()) + "\n")
            return subprocess.CompletedProcess(args[0], 0)

        try:
            with mock.patch.object(rd, "run_collection", side_effect=fake_coll), \
                 mock.patch.object(rd, "notify_or_log",
                                   return_value={"sent": True}), \
                 mock.patch.object(rd.subprocess, "run", side_effect=fake_timeout):
                rc = rd.main(["--config", str(root / ".env"), "--enrichment"])
        finally:
            rd.repo_root = original_root
            os.environ.pop(ENRICH_FLAG, None)
            if saved_flag is not None:
                os.environ[ENRICH_FLAG] = saved_flag
            os.environ.pop("NVIDIA_API_KEY", None)
            if saved_key is not None:
                os.environ["NVIDIA_API_KEY"] = saved_key
        check("A5. TimeoutExpired: refresh sobrevive (exit da coleta preservado)",
              rc == 0 and len(calls["subproc"]) == 1)
        if calls["subproc"]:
            check("A5b. subprocesso executado COM timeout (teto flock)",
                  calls["subproc"][0][1] is not None)
        check("A6. default do teto = 1800s",
              rd.DEFAULT_ENRICHMENT_MAX_SECS == 1800)


def _run_refresh_with_spy(root: Path, calls: dict, exit_code: int,
                          argv: list[str]) -> int:
    import refresh_daily as rd

    metrics = root / "data" / "collection_metrics.jsonl"
    metrics.parent.mkdir(parents=True, exist_ok=True)
    if not metrics.exists():
        metrics.write_text("", encoding="utf-8")

    def fake_run(*args, **kwargs) -> subprocess.CompletedProcess:
        with metrics.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_tenant_run_record()) + "\n")
        return subprocess.CompletedProcess(args[0], 0)

    original_root = rd.repo_root
    rd.repo_root = lambda: root
    try:
        with mock.patch.object(rd, "run_collection", side_effect=fake_run), \
             mock.patch.object(rd, "notify_or_log",
                               return_value={"sent": True}), \
             mock.patch.object(rd.subprocess, "run",
                               side_effect=_make_spy(calls, exit_code)):
            return rd.main(argv)
    finally:
        rd.repo_root = original_root


# ---------------------------------------------------------------------------
# B. Deadline hydration — default OFF, caminho preservado
# ---------------------------------------------------------------------------

def test_b_deadline_hydration() -> None:
    print("== B: deadline hydration — flag INTERNSHIP_FINDER_DEADLINE_HYDRATION ==")
    from internship_finder.adapters.ats import (
        AtsJobAdapter,
        set_deadline_hydration_enabled,
    )
    from internship_finder.models.company import Company

    company = Company(name="Teste", ats="successfactors", slug="t",
                      url="https://careers.teste.example")
    adapter = AtsJobAdapter()
    item = {"title": "Praktikum", "url": "https://a/1",
            "external_id": "R1", "application_deadline": "2026-10-15"}

    saved = os.environ.pop(DEADLINE_FLAG, None)
    try:
        set_deadline_hydration_enabled(False)
        job_off = adapter.to_job(item, company)
        check("B1. default OFF: campo da fonte NAO hidratado",
              job_off.application_deadline is None)

        set_deadline_hydration_enabled(True)
        job_on = adapter.to_job(item, company)
        check("B2. flag ON: valor hidratado e preservado",
              job_on.application_deadline == datetime(2026, 10, 15))
        bad = adapter.to_job(dict(item, application_deadline="not-a-date"),
                             company)
        check("B3. flag ON: invalido -> None (contrato intacto)",
              bad.application_deadline is None)
        absent = adapter.to_job(
            {"title": "Praktikum", "url": "https://a/2", "external_id": "R2"},
            company)
        check("B3b. flag ON: ausente -> None", absent.application_deadline is None)
    finally:
        set_deadline_hydration_enabled(True)
        set_deadline_hydration_enabled(False)
        if saved is None:
            os.environ.pop(DEADLINE_FLAG, None)
        else:
            os.environ[DEADLINE_FLAG] = saved

    # B4: persistencia SQLite do campo preservada (schema intocado).
    from internship_finder.storage.sqlite_store import SqliteStore
    import sqlite3
    with tempfile.TemporaryDirectory(prefix="t_f1_b4_") as tmp:
        db = Path(tmp) / "jobs.db"
        set_deadline_hydration_enabled(True)
        try:
            job = adapter.to_job(item, company)
            with SqliteStore(db) as store:
                store.run([job])
            conn = sqlite3.connect(str(db))
            try:
                row = conn.execute(
                    "SELECT application_deadline FROM jobs WHERE id = ?",
                    (job.id,)).fetchone()
            finally:
                conn.close()
            check("B4. SQLite: campo persistido quando hidratado (schema intacto)",
                  row is not None and row[0] is not None)
        finally:
            if saved is None:
                os.environ.pop(DEADLINE_FLAG, None)
            else:
                os.environ[DEADLINE_FLAG] = saved


# ---------------------------------------------------------------------------
# C. Ranking sem campos mortos
# ---------------------------------------------------------------------------

_JOB_BASE = {
    "id": "F1|successfactors:test:1",
    "source": "successfactors:test",
    "title": "Praktikum im Einkauf (m/w/d)",
    "company": "F1 Co",
    "location": "Munich, DE",
    "country_iso": "de",
    "url": "https://a/1",
    "external_id": "R1",
    "employment_type": "PART_TIME",
    "internship": True,
    "posted_at": "2026-09-01T00:00:00Z",
    "collected_at": "2026-09-07T06:00:02Z",
    "description": "Supply chain, procurement, SAP. English required.",
}


def test_c_ranking_sem_deadline() -> None:
    print("== C: ranking/eligibilidade sem campos mortos ==")
    from internship_finder.dedup import deduplicate
    from internship_finder.filters import select_eligible
    from internship_finder.ranking import score_job

    with_deadline = dict(_JOB_BASE, application_deadline="2026-10-07T00:00:00Z")
    without = {k: v for k, v in _JOB_BASE.items() if k != "application_deadline"}

    s1 = score_job(with_deadline)
    s2 = score_job(without)
    check("C1. score_job: score IDENTICO com/sem application_deadline",
          s1.total == s2.total and s1.breakdown == s2.breakdown)

    sel1, _ = select_eligible([with_deadline], student=True, area=True, country="de")
    sel2, _ = select_eligible([without], student=True, area=True, country="de")
    check("C2. select_eligible: eligibility IDENTICA com/sem o campo",
          [j["id"] for j in sel1] == [j["id"] for j in sel2])

    # Duplicatas VERDADEIRAS (mesma identidade textual company+title+
    # location) com deadlines DIFERENTES: dedup colapsa mesmo assim — o
    # campo morto NAO distingue vagas nem salva duplicata (nao e chave).
    a = dict(_JOB_BASE, id="F1|a:1", url="https://a/1",
             application_deadline="2026-10-01T00:00:00Z")
    b = dict(_JOB_BASE, id="F1|a:2", url="https://a/2",
             application_deadline="2026-11-01T00:00:00Z")
    distinct = dict(_JOB_BASE, id="F1|a:3", url="https://a/3", external_id="R3",
                    title="Werkstudent IT (m/w/d)",
                    description="Python automation and data pipelines.")
    out, stats, removed = deduplicate([a, b, distinct])
    check("C3. dedup: deadlines diferentes NAO salvam duplicata verdadeira "
          "(campo nao e chave)", len(out) == 2 and len(removed) == 1)

    # C4: contrato por inspecao — nenhum modulo de ranking/filters/dedup
    # referencia o campo morto.
    src_root = ROOT / "src" / "internship_finder"
    offenders = []
    for mod in ("ranking.py", "filters.py", "dedup.py", "materials_ranking.py"):
        text = (src_root / mod).read_text(encoding="utf-8")
        if "application_deadline" in text:
            offenders.append(mod)
    check("C4. ranking/filters/dedup/materiais NAO referenciam application_deadline",
          offenders == [], f"offenders={offenders}")


# ---------------------------------------------------------------------------
# D. Official-page — default OFF
# ---------------------------------------------------------------------------

def test_d_official_page_default() -> None:
    print("== D: official-page — default OFF ==")
    from internship_finder.cli import run_filter_pipeline

    # D1: parser do CLI com default False.
    import internship_finder.cli as cli_mod
    import argparse
    parser = None
    # O parser e construido dentro de main(); verificamos via o default da
    # assinatura de run_filter_pipeline + o argparse do modulo.
    import inspect
    sig = inspect.signature(run_filter_pipeline)
    check("D1. run_filter_pipeline: official_page default False",
          sig.parameters["official_page"].default is False)
    src_text = Path(inspect.getfile(cli_mod)).read_text(encoding="utf-8")
    check("D1b. argparse --official-page default False",
          '"--official-page",\n        action=argparse.BooleanOptionalAction,\n        default=False,'
          in src_text)

    # D2: pipeline default NAO roda o estagio e NAO grava registro.
    from internship_finder.official_page import enrich_official_pages
    job = dict(_JOB_BASE, description=None)  # candidata (sem description)
    with tempfile.TemporaryDirectory(prefix="t_f1_d2_") as tmp:
        out = Path(tmp) / "eligible.json"
        metrics = Path(tmp) / "metrics.jsonl"
        with mock.patch.object(cli_mod, "enrich_official_pages",
                               side_effect=AssertionError("nao deveria rodar")):
            rc = run_filter_pipeline(
                [dict(job)], student=True, area=False, country="all",
                output=out, dedup=True, rank=True,
                metrics=metrics,
            )
        recs = [json.loads(l) for l in metrics.read_text().splitlines()
                if l.strip()] if metrics.exists() else []
        op = [r for r in recs if r.get("type") == "official_page"]
        check("D2. default: estagio NAO roda, sem registro official_page",
              rc == 0 and out.exists() and op == [])

    # D3: flag explicita reativa o estagio sob demanda.
    class NullTransport:
        def get(self, url, headers, timeout):
            return (200, "<html><body>" + "empty " * 50 + "</body></html>", url)

    with tempfile.TemporaryDirectory(prefix="t_f1_d3_") as tmp:
        out = Path(tmp) / "eligible.json"
        metrics = Path(tmp) / "metrics.jsonl"
        rc = run_filter_pipeline(
            [dict(job)], student=True, area=False, country="all",
            output=out, dedup=True, rank=True,
            official_page=True, official_page_transport=NullTransport(),
            metrics=metrics,
        )
        recs = [json.loads(l) for l in metrics.read_text().splitlines()
                if l.strip()]
        op = [r for r in recs if r.get("type") == "official_page"]
        check("D3. --official-page explicito: estagio reativado + registro",
              rc == 0 and len(op) == 1)


# ---------------------------------------------------------------------------
# E. Operacao — flock nunca preso pelo enrichment
# ---------------------------------------------------------------------------

def test_e_operacao() -> None:
    print("== E: operação — flock nunca preso pelo enrichment ==")
    import refresh_daily as rd

    # E1: sem env flag, o refresh termina normal e o subprocesso de
    # enrichment NUNCA foi criado (gate pulado antes).
    with tempfile.TemporaryDirectory(prefix="t_f1_e1_") as tmp:
        root = Path(tmp)
        calls: dict = {"subproc": []}
        saved_key = os.environ.pop("NVIDIA_API_KEY", None)
        saved_flag = os.environ.pop(ENRICH_FLAG, None)
        os.environ["NVIDIA_API_KEY"] = "fake-key-f1"
        try:
            rc = _run_refresh_with_spy(root, calls, 0,
                                        ["--config", str(root / ".env"),
                                         "--enrichment"])
        finally:
            os.environ.pop("NVIDIA_API_KEY", None)
            if saved_key is not None:
                os.environ["NVIDIA_API_KEY"] = saved_key
            if saved_flag is not None:
                os.environ[ENRICH_FLAG] = saved_flag
        check("E1. cron (sem env flag): refresh termina sem subprocesso de enrichment",
              rc == 0 and calls["subproc"] == [])

    # E2: runner standalone continua com lock flock do SO (contrato
    # de concorrencia preservado — codigo mantido sob demanda).
    runner_path = ROOT / "src" / "internship_finder" / "enrichment" / "runner.py"
    text = runner_path.read_text(encoding="utf-8")
    check("E2. runner: lock flock do SO preservado (acquire_lock)",
          "fcntl.flock" in text and LOCK_NAME_GUARD in text)


LOCK_NAME_GUARD = ".enrichment.lock"


def main() -> int:
    test_a_enrichment_gate()
    test_b_deadline_hydration()
    test_c_ranking_sem_deadline()
    test_d_official_page_default()
    test_e_operacao()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
