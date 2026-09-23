"""Testes da publicacao do ranking em GitHub Pages (Fase 1).

Cobre ``scripts/publish_pages.py``: gate de seguranca (Parte D), escrita
atomica, commit/push condicional (nada a fazer quando o conteudo nao muda),
renderizacao real via ``scripts/interface.py`` (offline, fixture em tempdir)
e o gate do fluxo — predicado UNICO ``publication_allowed`` (auditoria
23/09): publica com ``eligible > 0`` em runs ok (exit 0) OU parciais com
falhas perifericas (exit 2); dataset vazio (exit 1) e run truncado (exit
124) bloqueiam. Os comandos git sao mockados (``_git``) — nenhuma
rede/secret envolvida.

Sem ``data/`` do repo: fixtures em tempdir (bloco real usa SKIP padrao do
projeto quando o snapshot nao existe — aqui ele nunca e necessario).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ (importa o alvo)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import publish_pages as pp  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _clean_html() -> str:
    """HTML parecido com o do interface.py: so conteudo de vagas + template."""
    return (
        "<!doctype html><html><body><h1>Internship Finder — vagas em destaque</h1>"
        "<p>data/eligible_jobs.json (2 vagas ranqueadas) · gerado em 2026-09-18T10:00:00Z</p>"
        '<a href="https://jobs.example.com/1">Praktikum Logistik</a>'
        "<p>STIHL · Waiblingen · de · Supply Chain Management</p>"
        "</body></html>"
    )


def test_check_public_safe() -> None:
    print("== Parte D: gate de seguranca do conteudo publicado ==")
    check("HTML normal de vagas e seguro ([] problemas)",
          pp.check_public_safe(_clean_html()) == [])
    token = "ghp_0123456789abcdef0123456789abcdef0123"
    probs = pp.check_public_safe(_clean_html() + token)
    check("token GitHub (ghp_) detectado",
          any("token GitHub" in p for p in probs))
    probs = pp.check_public_safe(_clean_html() + "github_pat_0123456789abcdef0123456789abcdef0123456789")
    check("token GitHub (github_pat_) detectado",
          any("github_pat_" in p for p in probs))
    probs = pp.check_public_safe(_clean_html() + "TELEGRAM_BOT_TOKEN")
    check("variavel TELEGRAM_BOT_TOKEN detectada",
          any("TELEGRAM_BOT_TOKEN" in p for p in probs))
    probs = pp.check_public_safe(_clean_html() + "rodou em /home/ubuntu/internship-finder")
    check("caminho privado /home/ubuntu detectado",
          any("/home/ubuntu" in p for p in probs))
    probs = pp.check_public_safe(_clean_html() + "backup em data/jobs.db")
    check("artefato interno jobs.db detectado",
          any("jobs.db" in p for p in probs))
    probs = pp.check_public_safe(_clean_html() + "rodei .env na raiz")
    check("arquivo .env detectado",
          any(".env" in p for p in probs))


def test_publish_html_git() -> None:
    print("== publicacao: escrita atomica + commit/push condicional ==")
    with tempfile.TemporaryDirectory(prefix="t_pp_git_") as tmp:
        deploy_dir = Path(tmp)
        html = _clean_html()

        calls: list[tuple] = []
        # Simula o git real: 'status' reflete a diferenca entre o index.html atual
        # e o ultimo commit (estado "publicado"); 'commit' grava o estado novo.
        state: dict = {"published": None}

        def fake_git(deploy_dir, *args, log=None):
            calls.append(args)
            if args[0] == "status":
                if not (deploy_dir / "index.html").exists():
                    return ""
                current = (deploy_dir / "index.html").read_text(encoding="utf-8")
                return "" if current == state["published"] else " M index.html"
            if args[0] == "commit":
                state["published"] = (deploy_dir / "index.html").read_text(encoding="utf-8")
                return "abc1234"
            if args[0] == "rev-parse":
                return "abc1234"
            return ""

        with mock.patch.object(pp, "_git", side_effect=fake_git):
            changed = pp.publish_html(html, deploy_dir, run_id="2026-09-18T10:00:00+00:00")
        check("primeira publicacao reporta que mudou", changed is True)
        final = deploy_dir / "index.html"
        check("index.html escrito com o conteudo exato", final.read_text(encoding="utf-8") == html)
        check("nenhum arquivo temporario residual",
              not list(deploy_dir.glob(".index.html.*.tmp")))
        commits = [c for c in calls if c[0] == "commit"]
        check("commit realizado", len(commits) == 1)
        if commits:
            msg = commits[0][2]
            check("mensagem do commit carrega o run_id sanitizado",
                  "deploy(run 2026-09-18T10:00:00-00:00): atualiza ranking publico" == msg)
        pushes = [c for c in calls if c[0] == "push"]
        check("push para a branch gh-pages", len(pushes) == 1
              and pushes[0][-1] == f"HEAD:{pp.PAGES_BRANCH}")

        calls.clear()
        with mock.patch.object(pp, "_git", side_effect=fake_git):
            changed2 = pp.publish_html(html, deploy_dir, run_id="r2")
        check("conteudo identico -> nada publicado (False)", changed2 is False)
        check("sem commit nem push quando nada mudou",
              not any(c[0] in ("commit", "push") for c in calls))

        # Seguranca: conteudo com token bloqueia ANTES de escrever qualquer coisa.
        bad_dir = Path(tmp) / "bad"
        bad_dir.mkdir()
        leaked = html + "ghp_0123456789abcdef0123456789abcdef0123"
        raised = False
        try:
            with mock.patch.object(pp, "_git", side_effect=fake_git):
                pp.publish_html(leaked, bad_dir, run_id="r3")
        except RuntimeError as exc:
            raised = "inseguro" in str(exc)
        check("conteudo inseguro bloqueado com RuntimeError", raised)
        check("nada escrito no deploy quando o gate falha",
              not (bad_dir / "index.html").exists()
              and not list(bad_dir.glob(".index.html.*.tmp")))


def _make_repo_fixture(tmp_root: Path) -> Path:
    """Raiz fake de repo: src/ (pacote real copiado) + scripts/interface.py +
    data/eligible_jobs.json (2 vagas sinteticas). Offline."""
    root = Path(__file__).resolve().parent.parent
    (tmp_root / "scripts").mkdir(parents=True)
    shutil.copy2(root / "scripts" / "interface.py", tmp_root / "scripts" / "interface.py")
    shutil.copytree(
        root / "src" / "internship_finder",
        tmp_root / "src" / "internship_finder",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    data_dir = tmp_root / "data"
    data_dir.mkdir()
    jobs = [
        {
            "title": "Praktikum Data Analytics / Data Science",
            "company": "STIHL", "url": "https://jobs.example.com/1",
            "score": 17.5, "location": "Waiblingen", "country_iso": "de",
            "description": "Supply Chain Analytics", "first_seen": "2026-09-16",
            "employment_type": "Internship",
        },
        {
            "title": "Werkstudent SCM Beschaffung",
            "company": "Bosch", "url": "https://jobs.example.com/2",
            "score": 14.0, "location": "Stuttgart", "country_iso": "de",
            "description": "Einkauf Logistik", "first_seen": "2026-09-16",
            "employment_type": "Working Student",
        },
    ]
    (data_dir / "eligible_jobs.json").write_text(
        json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp_root


def test_render_ranking_html() -> None:
    print("== renderizacao real via scripts/interface.py (offline) ==")
    with tempfile.TemporaryDirectory(prefix="t_pp_render_") as tmp:
        fake_root = _make_repo_fixture(Path(tmp))
        out = Path(tmp) / "out" / "index.html"
        out.parent.mkdir()
        html = pp.render_ranking_html(fake_root, out, top=10)
        check("HTML gerado e nao-vazio", len(html) > 500)
        check("contem as vagas do snapshot",
              "Praktikum Data Analytics / Data Science" in html
              and "Werkstudent SCM Beschaffung" in html)
        check("links das vagas no HTML",
              'href="https://jobs.example.com/1"' in html
              and 'href="https://jobs.example.com/2"' in html)
        check("rotulo da fonte e RELATIVO (nao expoe caminho da VPS)",
              "data/eligible_jobs.json" in html
              and str(fake_root) not in html
              and "/home/" not in html)
        check("arquivo temporario de saida removido", not out.exists())
        check("gate de seguranca aprova o HTML gerado",
              pp.check_public_safe(html) == [])


def test_publish_ranking_gates() -> None:
    print("== gates do fluxo: predicado UNICO publication_allowed (23/09) ==")
    with tempfile.TemporaryDirectory(prefix="t_pp_gates_") as tmp:
        root = Path(tmp)
        deploy = Path(tmp) / "pages"

        with mock.patch.object(pp, "ensure_deploy_clone") as ensure, \
             mock.patch.object(pp, "render_ranking_html") as render, \
             mock.patch.object(pp, "publish_html") as publish, \
             mock.patch.object(pp, "_git", return_value="https://github.com/x/y.git") as gitm:
            render.return_value = "<html>ranking</html>"
            publish.return_value = True
            # dataset vazio (exit 1 = zero vagas): bloqueado
            r1 = pp.publish_ranking(root, deploy, exit_code=1, eligible=5, run_id="r")
            check("exit 1 (dataset vazio) -> nada publicado", r1 is False
                  and not ensure.called and not render.called and not publish.called)
            r2 = pp.publish_ranking(root, deploy, exit_code=0, eligible=0, run_id="r")
            check("eligible == 0 -> nada publicado", r2 is False
                  and not ensure.called and not render.called and not publish.called)
            # run truncado (exit 124): dataset pode estar pela metade
            r2b = pp.publish_ranking(root, deploy, exit_code=124, eligible=5, run_id="r")
            check("exit 124 (truncado) -> nada publicado", r2b is False
                  and not ensure.called and not render.called and not publish.called)
            # run PARCIAL com falhas perifericas (exit 2) + vagas validas:
            # publica (auditoria 23/09 — antes exit != 0 bloqueava tudo)
            r2c = pp.publish_ranking(root, deploy, exit_code=2, eligible=5, run_id="r-parc")
            check("exit 2 (parcial) + eligible > 0 -> publica",
                  r2c is True and ensure.called and render.called and publish.called)
            r3 = pp.publish_ranking(root, deploy, exit_code=0, eligible=5, run_id="r9")
            check("exit 0 + eligible > 0 -> fluxo completo",
                  r3 is True and ensure.called and render.called and publish.called)
            check("origin descoberto no repo de trabalho",
                  gitm.call_args.args[:2] == (root, "config"))
            check("HTML renderizado e o publicado (mesmo objeto)",
                  publish.call_args.args[0] == "<html>ranking</html>")
            check("run_id chega ao commit como passado",
                  publish.call_args.kwargs["run_id"] == "r9")


def main() -> None:
    test_check_public_safe()
    test_publish_html_git()
    test_render_ranking_html()
    test_publish_ranking_gates()
    print()
    if FAILURES:
        print(f"FALHAS ({len(FAILURES)}):")
        for name in FAILURES:
            print(f"  - {name}")
        raise SystemExit(1)
    print("TUDO OK")


if __name__ == "__main__":
    main()