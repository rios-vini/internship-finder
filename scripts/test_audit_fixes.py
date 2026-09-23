"""Testes das correcoes da auditoria pos-Fases 1-8 (scripts/test_audit_fixes.py).

Cobre os 4 pontos corrigidos em 23/09 (item por item, com as fixtures
obrigatorias da spec do dono):

1. **Gate de publicacao parcial segura** — predicado UNICO
   ``publish_pages.publication_allowed``, usado por ``publish_ranking`` E
   pelo gate de digest/sync do ``refresh_daily``: exit 2 (parcial com falhas
   perifericas) + ``eligible > 0`` publica/digere/sincroniza; dataset vazio
   (exit 1 / eligible 0) e run truncado (exit 124) bloqueiam; exit code
   OPERACIONAL preservado (P1.3 intocado).
2. **Isolamento estrutural de testes** — nenhum teste/validacao escreve no
   ``data/`` de producao: sentinel byte-identical antes/depois de rodar a
   validacao a partir de um cwd COM ``data/``, e funcionamento a partir de
   cwd diferente.
3. **Atribuicao de erro por (source, company)** — SAP falha em
   ``successfactors:jobs`` compartilhado com BMW: a sumarizacao e a mensagem
   apontam SAP, nunca BMW.
4. **Alerta de regressao historica** — ``health._detect_regression``:
   empresa com historico ok que passa a falhar alerta (com company/source/
   error_code); sem historico ok nao alerta; dois companies no mesmo source
   alertam SO o que regrediu; repeticao do estado nao gera duplicata.

Standalone e OFFLINE (tempfile, mocks, sem rede, sem ``data/`` real).

Uso:  .venv/bin/python scripts/test_audit_fixes.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import publish_pages as pp  # noqa: E402
import refresh_daily as rd  # noqa: E402
from internship_finder.health import (  # noqa: E402
    MIN_OK_HISTORY_FOR_REGRESSION,
    build_health_report,
)

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _tenant(rid: str, source: str, status: str, collected: int, *,
            company: str = "Acme", error_code: str | None = None) -> dict:
    """Registro tenant minimo (mesmo schema do cli._tenant_record)."""
    return {
        "type": "tenant", "run_id": rid, "timestamp": rid,
        "company": company, "source": source,
        "ats": source.split(":", 1)[0], "status": status,
        "collected": collected,
        "error": None if status not in ("timeout", "error") else "boom",
        "error_code": error_code, "duration": 1.5,
    }


def _run_record(rid: str, total: int, eligible: int, dedup: int = 0) -> dict:
    return {
        "type": "run", "run_id": rid, "timestamp": rid,
        "total_collected": total, "filtered": 60, "dedup_removed": dedup,
        "eligible": eligible,
    }


# ---------------------------------------------------------------------------
# 1. Gate de publicacao parcial segura (predicado UNICO)
# ---------------------------------------------------------------------------

def test_publication_allowed_predicado() -> None:
    print("== item 1: predicado publication_allowed (A-E) ==")
    # A) eligible > 0 + falha parcial conhecida/periferica (exit 2) -> publica
    check("A. exit 2 + eligible 391 -> autorizado",
          pp.publication_allowed(2, 391) is True)
    check("A. exit 0 + eligible 1 -> autorizado (minimo)",
          pp.publication_allowed(0, 1) is True)
    # B) eligible == 0 -> bloqueia (qualquer exit)
    check("B. exit 0 + eligible 0 -> bloqueado",
          pp.publication_allowed(0, 0) is False)
    check("B. exit 2 + eligible 0 -> bloqueado",
          pp.publication_allowed(2, 0) is False)
    check("B. eligible negativo -> bloqueado",
          pp.publication_allowed(0, -5) is False)
    # C) falha critica de integridade/output: exit 1 (zero vagas = sem
    # output) e exit 124 (run truncado pelo teto = dataset pela metade).
    check("C. exit 1 (dataset vazio) -> bloqueado",
          pp.publication_allowed(1, 50) is False)
    check("C. exit 124 (run truncado) -> bloqueado",
          pp.publication_allowed(124, 300) is False)
    check("C. exit inesperado (3) -> bloqueado",
          pp.publication_allowed(3, 300) is False)
    # D) refresh totalmente OK -> publica normalmente
    check("D. exit 0 + eligible 391 -> autorizado",
          pp.publication_allowed(0, 391) is True)


def test_gate_publicacao_por_partes() -> None:
    print("== item 1: publish_ranking respeita o mesmo predicado ==")
    with tempfile.TemporaryDirectory(prefix="t_gate_pp_") as tmp:
        root = Path(tmp)
        deploy = Path(tmp) / "pages"
        with mock.patch.object(pp, "ensure_deploy_clone") as ensure, \
             mock.patch.object(pp, "render_ranking_html") as render, \
             mock.patch.object(pp, "publish_html") as publish, \
             mock.patch.object(pp, "_git", return_value="https://x/y.git"):
            render.return_value = "<html>ranking</html>"
            publish.return_value = True
            # exit 2 + eligible > 0: AGORA publica (antes: bloqueado)
            r = pp.publish_ranking(root, deploy, exit_code=2, eligible=391,
                                   run_id="r-parcial")
            check("exit 2 + eligible 391 -> fluxo de publicacao executado",
                  r is True and ensure.called and render.called
                  and publish.called)
            render.reset_mock(); ensure.reset_mock(); publish.reset_mock()
            # exit 1 + eligible > 0: continua bloqueado
            r = pp.publish_ranking(root, deploy, exit_code=1, eligible=391,
                                   run_id="r-vazio")
            check("exit 1 + eligible 391 -> nada publicado",
                  r is False and not ensure.called and not render.called
                  and not publish.called)
            render.reset_mock(); ensure.reset_mock(); publish.reset_mock()
            # exit 124 (truncado): bloqueado
            r = pp.publish_ranking(root, deploy, exit_code=124, eligible=391,
                                   run_id="r-truncado")
            check("exit 124 + eligible 391 -> nada publicado (run truncado)",
                  r is False and not ensure.called and not render.called
                  and not publish.called)


def test_gate_digest_sync_integrado() -> None:
    """A) digest/sync rodam em run PARCIAL com vagas validas; C) nao rodam
    em run truncado (exit 124); E) exit code OPERACIONAL preservado."""
    print("== item 1: gate UNICO alimenta digest/sync no refresh ==")
    for code, expect_digest, label in ((2, True, "parcial publica digest"),
                                       (124, False, "truncado SEM digest")):
        with tempfile.TemporaryDirectory(prefix="t_gate_rd_") as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            data_dir.mkdir()
            metrics = data_dir / "collection_metrics.jsonl"
            metrics.write_text("", encoding="utf-8")
            prev = [{"id": "old-1", "title": "Antiga", "company": "Acme",
                     "location": "Berlin", "score": 9.0,
                     "url": "https://ex.com/old-1"}]
            new = [{"id": "fresh-1", "title": "Nova", "company": "SAP",
                    "location": "Walldorf", "score": 12.0,
                    "url": "https://ex.com/fresh-1"}]
            (data_dir / "eligible_jobs.json").write_text(
                json.dumps(prev, ensure_ascii=False), encoding="utf-8")

            def fake_run(*args, **kwargs) -> subprocess.CompletedProcess:
                # Simula o CLI real: grava o ranking novo E o registro do run
                # no JSONL de metricas durante a coleta (o refresh lerah os
                # registros NOVOS para o summary — run_id/eligible).
                (data_dir / "eligible_jobs.json").write_text(
                    json.dumps(new, ensure_ascii=False), encoding="utf-8")
                with metrics.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(
                        _run_record("r1", 391, 1)) + "\n")
                return subprocess.CompletedProcess(args[0], code)

            calls: dict = {"notify": [], "sync": []}
            original_root = rd.repo_root
            original_sync = rd._sync_personal_ranking

            def fake_notify(config, message, *, dry_run) -> dict:
                calls["notify"].append(message)
                return {"sent": True}

            def fake_sync(root_arg, data_arg) -> None:
                calls["sync"].append((root_arg, data_arg))

            rd.repo_root = lambda: root
            rd._sync_personal_ranking = fake_sync
            try:
                with mock.patch.object(rd, "run_collection",
                                       side_effect=fake_run), \
                     mock.patch.object(rd, "notify_or_log",
                                       side_effect=fake_notify):
                    rc = rd.main(["--config", str(root / ".env"),
                                  "--always-notify"])
            finally:
                rd.repo_root = original_root
                rd._sync_personal_ranking = original_sync

            # E) exit code operacional preservado mesmo com digest permitido
            check(f"E. exit {code}: main retorna {code} (P1.3 intocado)",
                  rc == code, f"rc={rc}")
            msg = calls["notify"][0] if calls["notify"] else ""
            if expect_digest:
                check("A. exit 2: digest montado (Top 5 na mensagem)",
                      "🏆 Top 5" in msg and "🔗 Ranking completo" in msg)
                check("A. exit 2: sync-ranking pessoal executado",
                      len(calls["sync"]) == 1)
                check("A. exit 2: parcialidade VISIVEL na mensagem",
                      "Coleta parcial" in msg)
            else:
                check("C. exit 124: SEM digest (ranking truncado)",
                      "🏆 Top 5" not in msg
                      and "🔗 Ranking completo" not in msg)
                check("C. exit 124: sync-ranking pessoal NAO executado",
                      calls["sync"] == [])


def test_exit_code_operacional_preservado() -> None:
    """E) mesmo com publicacao parcial permitida, o exit do processo e o da
    coleta — o gate muda SO a autorizacao de publicar, nunca o exit code."""
    print("== item 1: exit code operacional (harness subprocesso) ==")
    scripts = Path(__file__).resolve().parent
    src = scripts.parent / "src"
    harness = (
        "import subprocess, sys, tempfile\n"
        "from pathlib import Path\n"
        f"sys.path.insert(0, {str(scripts)!r})\n"
        f"sys.path.insert(0, {str(src)!r})\n"
        "import refresh_daily as rd\n"
        "root = Path(tempfile.mkdtemp(prefix='t_exitfix_'))\n"
        "(root / 'data').mkdir()\n"
        "(root / 'data' / 'collection_metrics.jsonl').write_text('', encoding='utf-8')\n"
        "rd.repo_root = lambda: root\n"
        "def fake_run(*a, **k):\n"
        "    return subprocess.CompletedProcess(a[0], 2)\n"
        "def fake_notify(config, message, *, dry_run):\n"
        '    return {"sent": True}\n'
        "rd.run_collection = fake_run\n"
        "rd.notify_or_log = fake_notify\n"
        "raise SystemExit(rd.main(['--config', str(root / '.env')]))\n"
    )
    proc = subprocess.run([sys.executable, "-c", harness],
                          capture_output=True, text=True, timeout=60)
    check("E. processo com coleta exit 2 termina exit 2 (gate nao mascara)",
          proc.returncode == 2, f"rc={proc.returncode}")
    check("E. sem traceback no stderr", "Traceback" not in proc.stderr)


# ---------------------------------------------------------------------------
# 2. Testes/validacoes NUNCA escrevem em data/ de producao (estrutural)
# ---------------------------------------------------------------------------

def test_suite_nao_contamina_data_sentinel() -> None:
    """Rodar a validacao do repo (test_hardening, o ex-contaminador) a
    partir de um cwd COM data/ presente NAO altera nenhum JSONL de producao:
    sentinel byte-identical antes/depois. Roda em um clone temporario com
    data/collection_metrics.jsonl sentinel — nunca no data/ real."""
    print("== item 2: suite nao escreve no data/ de producao (sentinel) ==")
    scripts_dir = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="t_isol_") as tmp:
        root = Path(tmp)
        # pseudo-repo: scripts/ reais (so o ex-contaminador basta) + src real
        (root / "scripts").mkdir()
        (root / "data").mkdir()
        import shutil
        for name in ("test_hardening.py",):
            shutil.copy2(scripts_dir / name, root / "scripts" / name)
        shutil.copytree(
            scripts_dir.parent / "src", root / "src",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        # sentinel de producao: bytes conhecidos; a suite nao pode tocar
        sentinel = root / "data" / "collection_metrics.jsonl"
        sentinel_bytes = (b'{"type": "tenant", "company": "REAL", '
                          b'"source": "successfactors:jobs", '
                          b'"status": "ok", "collected": 10}\n')
        sentinel.write_bytes(sentinel_bytes)
        data_before = sorted(
            (str(p.relative_to(root)), p.stat().st_mtime_ns, p.stat().st_size)
            for p in (root / "data").rglob("*") if p.is_file()
        )

        # roda o ex-contaminador COM O CWD NO ROOT COM data/ — exatamente o
        # cenario que escreveu "Acme" no data/ de producao em 19-21/09
        env = {**os.environ, "PYTHONPATH": str(root / "src"),
               "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / "test_hardening.py")],
            cwd=str(root), capture_output=True, text=True, env=env,
            timeout=300,
        )
        check("test_hardening exit 0 no pseudo-repo com data/",
              proc.returncode == 0,
              f"rc={proc.returncode} stderr={proc.stderr[-200:]}")
        check("sentinel byte-identical (nenhum registro novo)",
              sentinel.read_bytes() == sentinel_bytes)
        data_after = sorted(
            (str(p.relative_to(root)), p.stat().st_mtime_ns, p.stat().st_size)
            for p in (root / "data").rglob("*") if p.is_file()
        )
        check("data/ intocado (nenhum arquivo criado/alterado)",
              data_before == data_after,
              f"diff={set(data_after) ^ set(data_before)}")
        # e funciona a partir de cwd DIFERENTE (comportamento independente)
        proc2 = subprocess.run(
            [sys.executable, str(root / "scripts" / "test_hardening.py")],
            cwd=str(Path(tmp)), capture_output=True, text=True, env=env,
            timeout=300,
        )
        check("test_hardening exit 0 de cwd diferente",
              proc2.returncode == 0)
        check("sentinel intocado apos run de cwd diferente",
              sentinel.read_bytes() == sentinel_bytes)
        # nenhuma linha "Acme"/mock no JSONL: o metrics da suite viveu em tmp
        check("nenhum registro mock no JSONL de producao",
              b"Acme" not in sentinel.read_bytes())


def test_collect_mode_sem_metrics_explcito_eh_o_unico_caminho() -> None:
    """Defesa em profundidade: grepa os cli.main de MODO COLETA do repo e
    exige --metrics explicito em TODOS (o default relativo ao cwd e o vetor
    da contaminacao — agora nenhum teste usa o default)."""
    print("== item 2: todo cli.main collect-mode tem --metrics explicito ==")
    scripts_dir = Path(__file__).resolve().parent
    offenders: list[str] = []
    for script in sorted(scripts_dir.glob("test_*.py")):
        text = script.read_text(encoding="utf-8")
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "cli.main([" not in line:
                continue
            # junta a chamada inteira (multi-linha) ate fechar o bracket
            call = line
            j = i
            while call.count("[") > call.count("]") and j + 1 < len(lines):
                j += 1
                call += lines[j]
            if '"--companies"' not in call and '"--registry"' not in call:
                continue  # modo filtro/health: nao grava metrics
            if '"--metrics"' not in call:
                offenders.append(f"{script.name}:{i + 1}")
    check("0 cli.main collect-mode sem --metrics no repo",
          offenders == [], f"ofensores={offenders}")


# ---------------------------------------------------------------------------
# 3. Atribuicao de erro por (source, company) — SAP x BMW
# ---------------------------------------------------------------------------

def test_atribuicao_sap_bmw_tenant_compartilhado() -> None:
    """Caso REAL da producao (runs 22-23/09): SAP error FETCH_ERROR + BMW ok
    no MESMO source successfactors:jobs. A mensagem aponta SAP, nao BMW."""
    print("== item 3: SAP falha, BMW ok — mensagem aponta SAP ==")
    records = [
        _tenant("2026-09-23T06:00:00+00:00", "successfactors:jobs", "ok", 830,
                company="BMW AG"),
        _tenant("2026-09-23T06:00:00+00:00", "successfactors:jobs", "error", 0,
                company="SAP", error_code="FETCH_ERROR"),
        _run_record("2026-09-23T06:00:00+00:00", 391, 391),
    ]
    summary = rd.summarize_run(records)
    # sumarizacao: a falha carrega a company QUE FALHOU
    check("summary error tem 1 falha com company SAP",
          len(summary["error"]) == 1
          and summary["error"][0][:2] == ("successfactors:jobs", "SAP"),
          f"error={summary['error']!r}")
    check("falha carrega error_code FETCH_ERROR",
          summary["error"][0][2] == "FETCH_ERROR")
    # source_names segue existindo (primeiro company) mas NAO decide mais
    # a atribuicao do erro
    check("source_names preservado (compat)",
          summary["source_names"].get("successfactors:jobs") == "BMW AG")

    message = rd.build_message(summary, [], exit_code=2)
    check("mensagem nao e None (run parcial)", message is not None)
    check("mensagem aponta SAP (empresa que falhou)",
          "SAP (successfactors:jobs)" in (message or ""),
          f"msg={message!r}")
    check("erro atribuido a SAP aparece como falha (FETCH_ERROR traduzido)",
          "SAP (successfactors:jobs) — erro ao buscar vagas" in (message or ""))
    check("BMW NAO aparece como fonte do erro",
          "BMW AG (successfactors:jobs) — erro" not in (message or ""))
    check("source compartilhado permanece correto na mensagem",
          "successfactors:jobs" in (message or ""))
    check("parcialidade visivel (1 de 2 fontes falharam)",
          "Coleta parcial: 1 de 2 fontes falharam" in (message or ""))


def test_atribuicao_dois_problemas_mesmo_source() -> None:
    """Dois companies falhando no MESMO source: dois problemas distintos,
    cada um com o nome certo (identidade (source, company))."""
    print("== item 3: dois companies falham no mesmo source ==")
    records = [
        _tenant("r1", "successfactors:jobs", "error", 0,
                company="SAP", error_code="FETCH_ERROR"),
        _tenant("r1", "successfactors:jobs", "timeout", 0,
                company="ZF", error_code="TIMEOUT"),
        _run_record("r1", 100, 10),
    ]
    summary = rd.summarize_run(records)
    message = rd.build_message(summary, [], exit_code=2)
    check("SAP e ZF listados separadamente",
          "SAP (successfactors:jobs)" in (message or "")
          and "ZF (successfactors:jobs)" in (message or ""))
    check("2 problemas (nao dedup por source)",
          (message or "").count("• SAP") == 1
          and (message or "").count("• ZF") == 1)


def test_alertas_health_atribuem_company() -> None:
    """Alertas do health (que ja tem company desde P3 #37) agora RENDERIZAM
    com o company correto — regressao de drop num tenant compartilhado."""
    print("== item 3: alerta de drop com company correto na mensagem ==")
    rows = [
        _tenant("2026-09-01T01:00:00Z", "phenom:nan", "ok", 8000,
                company="Alpha"),
        _tenant("2026-09-01T02:00:00Z", "phenom:nan", "ok", 8200,
                company="Alpha"),
        _tenant("2026-09-01T03:00:00Z", "phenom:nan", "ok", 8100,
                company="Alpha"),
        _tenant("2026-09-01T04:00:00Z", "phenom:nan", "ok", 8050,
                company="Alpha"),
        _tenant("2026-09-01T05:00:00Z", "phenom:nan", "ok", 200,
                company="Alpha"),
    ]
    report = build_health_report(rows)
    drops = [a for a in report["alerts"] if a["type"] == "drop"]
    check("drop detectado na serie Alpha", len(drops) == 1)
    summary = rd.summarize_run([_run_record("r1", 100, 10)])
    message = rd.build_message(summary, report["alerts"], exit_code=0)
    check("mensagem renderiza o company do alerta (Alpha)",
          "Alpha (phenom:nan) — queda brusca" in (message or ""),
          f"msg={message!r}")


# ---------------------------------------------------------------------------
# 4. Alerta de regressao historica (empresa ok -> error)
# ---------------------------------------------------------------------------

def _regressions(records: list[dict]) -> list[dict]:
    return [a for a in build_health_report(records)["alerts"]
            if a["type"] == "regression"]


def test_regressao_historica_detectada() -> None:
    """B) empresa com historico ok + error atual -> alerta."""
    print("== item 4 B: historico ok + error -> alerta ==")
    rows = [
        _tenant("2026-09-20T06:00:00+00:00", "successfactors:jobs", "ok", 474,
                company="SAP"),
        _tenant("2026-09-21T06:00:00+00:00", "successfactors:jobs", "ok", 480,
                company="SAP"),
        _tenant("2026-09-22T06:00:00+00:00", "successfactors:jobs", "ok", 474,
                company="SAP"),
        _tenant("2026-09-23T06:00:00+00:00", "successfactors:jobs", "error", 0,
                company="SAP", error_code="FETCH_ERROR"),
    ]
    reg = _regressions(rows)
    check("B. alerta de regressao gerado", len(reg) == 1, f"reg={reg!r}")
    if reg:
        a = reg[0]
        check("B. alerta com company exato (SAP)", a["company"] == "SAP")
        check("B. alerta com source do tenant",
              a["source"] == "successfactors:jobs")
        check("B. alerta com error_code quando disponivel",
              a["error_code"] == "FETCH_ERROR")
        check("B. alerta com ok_history", a["ok_history"] == 3)


def test_regressao_sem_historico_nao_alerta() -> None:
    """A) empresa sem historico + error -> SEM alerta de regressao (nunca
    funcionou; estado persistente e do recurring_error)."""
    print("== item 4 A: sem historico + error -> sem alerta ==")
    rows = [
        _tenant("2026-09-22T06:00:00+00:00", "successfactors:jobs", "error", 0,
                company="Nova", error_code="FETCH_ERROR"),
        _tenant("2026-09-23T06:00:00+00:00", "successfactors:jobs", "error", 0,
                company="Nova", error_code="FETCH_ERROR"),
    ]
    check("A. sem historico ok -> sem alerta de regressao",
          _regressions(rows) == [])
    # historico CURTO (2 ok) tambem nao: gate conservador
    rows_short = [
        _tenant("2026-09-22T06:00:00+00:00", "sf:x", "ok", 10, company="Curta"),
        _tenant("2026-09-22T07:00:00+00:00", "sf:x", "ok", 10, company="Curta"),
        _tenant("2026-09-23T06:00:00+00:00", "sf:x", "error", 0,
                company="Curta"),
    ]
    check("A. historico curto (2 ok < gate) -> sem alerta",
          _regressions(rows_short) == []
          and MIN_OK_HISTORY_FOR_REGRESSION == 3)
    # empty NAO e falha: empresa ok que responde 0 segue sem regressao
    rows_empty = [
        _tenant("2026-09-20T06:00:00+00:00", "sf:y", "ok", 10, company="Empty"),
        _tenant("2026-09-21T06:00:00+00:00", "sf:y", "ok", 10, company="Empty"),
        _tenant("2026-09-22T06:00:00+00:00", "sf:y", "ok", 10, company="Empty"),
        _tenant("2026-09-23T06:00:00+00:00", "sf:y", "empty", 0,
                company="Empty"),
    ]
    check("A. run mais recente empty -> sem regressao (nao e falha)",
          _regressions(rows_empty) == [])


def test_regressao_tenant_compartilhado_so_a_serie_errada() -> None:
    """C) dois companies no MESMO source: A (historico ok) falha, B segue ok
    -> alerta SOMENTE na serie de A."""
    print("== item 4 C: tenant compartilhado alerta so quem regrediu ==")
    rows = [
        # serie (successfactors:jobs, SAP): 3 ok e depois error
        _tenant("2026-09-20T06:00:00+00:00", "successfactors:jobs", "ok", 474,
                company="SAP"),
        _tenant("2026-09-21T06:00:00+00:00", "successfactors:jobs", "ok", 480,
                company="SAP"),
        _tenant("2026-09-22T06:00:00+00:00", "successfactors:jobs", "ok", 474,
                company="SAP"),
        _tenant("2026-09-23T06:00:00+00:00", "successfactors:jobs", "error", 0,
                company="SAP", error_code="FETCH_ERROR"),
        # serie (successfactors:jobs, BMW AG): segue ok
        _tenant("2026-09-22T06:00:00+00:00", "successfactors:jobs", "ok", 830,
                company="BMW AG"),
        _tenant("2026-09-23T06:00:00+00:00", "successfactors:jobs", "ok", 828,
                company="BMW AG"),
    ]
    reg = _regressions(rows)
    check("C. exatamente 1 alerta de regressao (serie SAP)", len(reg) == 1,
          f"reg={reg!r}")
    check("C. alerta aponta SAP (a serie que falhou)",
          bool(reg) and reg[0]["company"] == "SAP")
    check("C. BMW AG nao aparece em nenhum alerta de regressao",
          all(a.get("company") != "BMW AG" for a in reg))


def test_regressao_estado_persistente_sem_spam() -> None:
    """D) repeticao do mesmo estado: 1 alerta de regressao por relatorio,
    nao 1 por run do historico; coexistencia com recurring_error e
    intencional (transicao vs persistencia), sem duplicata do MESMO tipo."""
    print("== item 4 D: estado persistente nao gera spam ==")
    base_ok = [
        _tenant(f"2026-09-1{i}T06:00:00+00:00", "sf:jobs", "ok", 100,
                company="SAP")
        for i in (7, 8, 9)
    ]
    one_fail = base_ok + [
        _tenant("2026-09-20T06:00:00+00:00", "sf:jobs", "error", 0,
                company="SAP", error_code="FETCH_ERROR"),
    ]
    reg1 = _regressions(one_fail)
    check("D. 1a falha: exatamente 1 alerta de regressao", len(reg1) == 1)

    two_fails = one_fail + [
        _tenant("2026-09-21T06:00:00+00:00", "sf:jobs", "error", 0,
                company="SAP", error_code="FETCH_ERROR"),
    ]
    report = build_health_report(two_fails)
    reg2 = _regressions(two_fails)
    recurring = [a for a in report["alerts"]
                 if a["type"] == "recurring_error"]
    check("D. 2a falha: regressao continua 1 (nao acumula por run)",
          len(reg2) == 1, f"reg={reg2!r}")
    check("D. 2a falha: recurring_error assume o estado persistente",
          len(recurring) == 1 and recurring[0]["company"] == "SAP")
    check("D. interacao documentada: 1 regression + 1 recurring (tipos distintos)",
          len([a for a in report["alerts"]
               if a["type"] in ("regression", "recurring_error")]) == 2)

    five_fails = two_fails + [
        _tenant(f"2026-09-2{i}T06:00:00+00:00", "sf:jobs", "error", 0,
                company="SAP", error_code="FETCH_ERROR")
        for i in (2, 3, 4)
    ]
    reg5 = _regressions(five_fails)
    check("D. 5a falha: regressao AINDA 1 (sem spam)",
          len(reg5) == 1, f"reg={reg5!r}")


def test_regressao_timeout_e_mensagem() -> None:
    """timeout tambem e regressao; e a mensagem renderiza o alerta novo com
    a atribuicao correta (item 3 + 4 juntos). Serie que falhou no run E tem
    alerta de regressao: a linha de falha ganha o contexto historico (dedup
    — nenhum problema listado 2x). Serie sem falha no run atual: linha
    propria 'estava funcionando e falhou'."""
    print("== item 4: timeout conta + mensagem renderiza o alerta ==")
    rows = [
        _tenant("2026-09-20T06:00:00+00:00", "sf:lidlx", "ok", 300,
                company="Lidl"),
        _tenant("2026-09-21T06:00:00+00:00", "sf:lidlx", "ok", 290,
                company="Lidl"),
        _tenant("2026-09-22T06:00:00+00:00", "sf:lidlx", "ok", 310,
                company="Lidl"),
        _tenant("2026-09-23T06:00:00+00:00", "sf:lidlx", "timeout", 0,
                company="Lidl", error_code="TIMEOUT"),
    ]
    reg = _regressions(rows)
    check("timeout apos historico ok -> alerta de regressao",
          len(reg) == 1 and reg[0]["last_status"] == "timeout")

    # caso 1: a serie falhou NO RUN ATUAL -> contexto historico anotado na
    # linha de falha (1 linha, sem duplicata do alerta)
    summary = rd.summarize_run([
        _run_record("r1", 391, 391),
        _tenant("2026-09-23T06:00:00+00:00", "sf:lidlx", "timeout", 0,
                company="Lidl", error_code="TIMEOUT"),
    ])
    message = rd.build_message(summary, reg, exit_code=2)
    check("falha do run com contexto de regressao (empresa + historico)",
          "Lidl (sf:lidlx) — sem resposta a tempo (timeout)"
          " · antes funcionava (3 runs ok e agora falhou)" in (message or ""),
          f"msg={message!r}")
    check("alerta de regressao sem linha duplicada",
          (message or "").count("Lidl (sf:lidlx)") == 1)

    # caso 2: serie SEM falha no resumo do run (ex.: dados de run anterior)
    # -> linha propria com o tipo do erro
    summary2 = rd.summarize_run([_run_record("r1", 391, 391)])
    message2 = rd.build_message(summary2, reg, exit_code=0)
    check("regressao sem falha no run -> linha propria",
          "Lidl (sf:lidlx) — estava funcionando e falhou "
          "(sem resposta a tempo (timeout))" in (message2 or ""),
          f"msg={message2!r}")


def main() -> int:
    test_publication_allowed_predicado()
    test_gate_publicacao_por_partes()
    test_gate_digest_sync_integrado()
    test_exit_code_operacional_preservado()
    test_suite_nao_contamina_data_sentinel()
    test_collect_mode_sem_metrics_explcito_eh_o_unico_caminho()
    test_atribuicao_sap_bmw_tenant_compartilhado()
    test_atribuicao_dois_problemas_mesmo_source()
    test_alertas_health_atribuem_company()
    test_regressao_historica_detectada()
    test_regressao_sem_historico_nao_alerta()
    test_regressao_tenant_compartilhado_so_a_serie_errada()
    test_regressao_estado_persistente_sem_spam()
    test_regressao_timeout_e_mensagem()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
