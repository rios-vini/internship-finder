"""Publicacao do ranking em GitHub Pages (Fase 1).

Fluxo diario (chamado pelo ``scripts/refresh_daily.py`` apos a coleta):

    ranking gerado (data/eligible_jobs.json, snapshot do run)
      -> reusa scripts/interface.py (MESMO HTML do uso local, nada de
         frontend novo) para renderizar a pagina
      -> verifica que nenhum segredo/caminho privado vazou (Parte D)
      -> escreve ``index.html`` atomicamente no clone de deploy
      -> commit + push na branch ``gh-pages``
      -> GitHub Pages serve a URL estavel.

Garantias (Parte C): o ranking publicado e sempre um dataset VALIDO E COMPLETO
— a decisao e a funcao unica ``publication_allowed`` (ver docstring): publica
com vagas elegiveis > 0 em runs ok (exit 0) OU parciais com falhas perifericas
de fontes individuais (exit 2); dataset vazio, run truncado (exit 124) ou exit
inesperado nunca publicam (a pagina anterior permanece). A geracao acontece em
diretorio temporario e o artefato so entra no clone via ``os.replace`` (mesmo
filesystem); o push contem apenas ``index.html``. Nenhum ranking, peso ou
filtro e alterado — isto publica o snapshot exatamente como o run o gerou.

O clone de deploy vive FORA do repo (default ``~/internship-finder-ghpages``,
por isso ele nunca e contaminado por outras branches nem vaza nos commits do
projeto). ``jobs.db``, logs, ``data/`` e artefatos internos nunca sao
publicados.

Manual (Parte F):

    .venv/bin/python scripts/publish_pages.py --dry-run            # gera + verifica, sem push
    .venv/bin/python scripts/publish_pages.py                      # publica o ranking atual
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

PAGES_BRANCH = "gh-pages"
INDEX_NAME = "index.html"

# "Todas as vagas" para a publicacao: o default do interface.py (--top 25) e o
# topo rapido do uso local; a pagina publica mostra o ranking completo.
PUBLIC_TOP = 100000

# Parte D — padroes que NUNCA podem aparecer no artefato publicado. O proprio
# HTML do template nao contem nenhum destes; se um aparecer, o push e
# bloqueado e o run reporta o problema (melhor falso positivo do que vazar).
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ghp_[0-9A-Za-z]{20,}"), "token GitHub (ghp_)"),
    (re.compile(r"gho_[0-9A-Za-z]{20,}"), "token GitHub (gho_)"),
    (re.compile(r"github_pat_[0-9A-Za-z_]{20,}"), "token GitHub (github_pat_)"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"), "token Slack"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "chave AWS (AKIA)"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "chave Google"),
    (re.compile(r"\bsk-[0-9A-Za-z]{20,}\b"), "secret 'sk-'"),
    (re.compile(r"(?i)TELEGRAM_BOT_TOKEN"), "variavel TELEGRAM_BOT_TOKEN"),
    (re.compile(r"(?i)TELEGRAM_CHAT_ID"), "variavel TELEGRAM_CHAT_ID"),
    (re.compile(r"(?i)git-credentials"), "referencia a ~/.git-credentials"),
]

# Exit codes operacionais do refresh que representam um dataset PUBLICAVEL
# (ver ``publication_allowed``). 0 = coleta ok; 2 = parcial com falhas
# perifericas de fontes individuais mas dataset valido salvo (o CLI grava os
# outputs SEMPRE que ha vagas — ver cli.py); qualquer outro (1 = dataset
# vazio, 124 = run truncado/estourado) NAO publica.
_PUBLISHABLE_EXIT_CODES = frozenset({0, 2})


def publication_allowed(exit_code: int, eligible: int) -> bool:
    """Decisao UNICA de publicacao parcial segura (auditoria 23/09).

    Um run pode alimentar Pages/digest/sync quando o dataset produzido e
    valido e nao-vazio — ``eligible > 0`` — e o run terminou em um estado
    cujo dataset e confiavel (exit 0 = ok; exit 2 = parcial com falhas
    perifericas de fontes individuais: Lidl timeout, K+N NXDOMAIN etc.; o
    CLI salva jobs.json/eligible_jobs.json SEMPRE que ha vagas e a escrita e
    atomica, entao o ranking existe e esta integro).

    Bloqueiam (dataset vazio/nao confiavel): exit 1 (nenhuma vaga), exit 124
    (run TRUNCADO pelo teto — o dataset pode estar pela metade) e qualquer
    exit desconhecido. ``eligible <= 0`` bloqueia sempre.

    O exit code OPERACIONAL do refresh NAO muda (P1.3): esta funcao so
    decide AUTORIZACAO de publicar; o cron/monitoramento continuam lendo o
    exit real da coleta. Este predicado e a UNICA regra — Pages
    (``publish_ranking``), digest e sync do ``refresh_daily`` a consultam;
    nenhum componente tem regra propria.
    """
    return (
        eligible > 0
        and exit_code in _PUBLISHABLE_EXIT_CODES
    )


# Fragmentos de caminhos privados/artefatos internos (slash no final distingue
# caminho real de palavras comuns como "home office").
_PRIVATE_FRAGMENTS = [
    "/home/ubuntu",
    "/root/",
    "/Users/",
    "/tmp/if_",
    ".env",
    "jobs.db",
]


def check_public_safe(text: str) -> list[str]:
    """Problemas encontrados no artefato (lista vazia = seguro para publicar).

    Verifica (a) padroes de secret/credencial conhecidos e (b) fragmentos de
    caminhos privados da VPS / artefatos internos. Nao e ofuscacao nem
    criptografia: e um gate que bloqueia o push se o conteudo estiver fora do
    esperado — o HTML e gerado por template fixo + dados de vagas, entao o
    conjunto de falsos positivos possiveis e pequeno e audivel.
    """
    problems: list[str] = []
    for pat, label in _SECRET_PATTERNS:
        if pat.search(text):
            problems.append(f"padrao de secret: {label}")
    for frag in _PRIVATE_FRAGMENTS:
        pos = text.find(frag)
        if pos != -1:
            ctx = text[max(0, pos - 40):pos + len(frag) + 40]
            problems.append(f"fragmento privado {frag!r} (ctx: {ctx!r})")
    return problems


def _log(log, msg: str, *args) -> None:
    """Loga via logging.Logger pedido; sem logger, usa print (modo manual)."""
    if log is not None:
        log.info(msg, *args)
    else:
        print(msg % args if args else msg)


def _git(deploy_dir: Path, *args: str, log=None) -> str:
    """Roda ``git`` em ``deploy_dir``; erro = RuntimeError com saida do git."""
    proc = subprocess.run(
        ["git", *args], cwd=deploy_dir, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} falhou (exit {proc.returncode}): "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout.strip()


def ensure_deploy_clone(
    deploy_dir: Path, origin_url: str, *, root: Path, log=None,
) -> None:
    """Prepara o clone de deploy da branch ``gh-pages`` (bootstrap ou sync).

    Bootstrap (primeiro deploy, branch remota inexistente): ``git init`` local
    com a branch ``gh-pages`` e o origin do repo. Runs seguintes: sincroniza
    com a remota (fetch + reset --hard) — o unico escritor desta branch e este
    fluxo, entao reset e seguro e garante que o commit parte do ultimo estado
    publicado mesmo se o push anterior falhou no meio do caminho.
    """
    _log(log, "pages: deploy_dir=%s origin=%s", deploy_dir, origin_url)
    if not (deploy_dir / ".git").exists():
        deploy_dir.mkdir(parents=True, exist_ok=True)
        _git(deploy_dir, "init", "-b", PAGES_BRANCH)
        _git(deploy_dir, "remote", "add", "origin", origin_url)
        # Identity do commit: herda a do repo de trabalho (imita o autor real).
        for key in ("user.name", "user.email"):
            val = _git(root, "config", "--get", key)
            if val:
                _git(deploy_dir, "config", key, val)
    remote_heads = _git(
        deploy_dir, "ls-remote", "--heads", "origin", f"refs/heads/{PAGES_BRANCH}",
    )
    if remote_heads:
        _git(deploy_dir, "fetch", "-q", "origin", PAGES_BRANCH)
        _git(deploy_dir, "reset", "--hard", f"origin/{PAGES_BRANCH}")
        _git(deploy_dir, "checkout", "-B", PAGES_BRANCH, f"origin/{PAGES_BRANCH}")
    else:
        _git(deploy_dir, "checkout", "-B", PAGES_BRANCH)


def render_ranking_html(
    root: Path, output_path: Path, *, top: int = PUBLIC_TOP, timeout: float = 300.0,
) -> str:
    """Gera o HTML do ranking reusando ``scripts/interface.py`` (mesmo mecanismo).

    O ``--input`` e o caminho RELATIVO ``data/eligible_jobs.json`` (com cwd na
    raiz do repo), de proposito: o rotulo exibido na pagina ("data/
    eligible_jobs.json (N vagas ranqueadas)") nao expoe caminho absoluto da
    VPS. Retorna o texto gerado; o arquivo temporario de saida e removido.
    """
    script = root / "scripts" / "interface.py"
    if not script.exists():
        raise RuntimeError(f"scripts/interface.py nao encontrado em {root}")
    cmd = [
        sys.executable, str(script),
        "--input", "data/eligible_jobs.json",
        "--top", str(top),
        "--output", str(output_path),
    ]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    try:
        proc = subprocess.run(
            cmd, cwd=root, capture_output=True, text=True, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"geracao do HTML estourou o tempo ({timeout:.0f}s)") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"interface.py falhou (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    text = output_path.read_text(encoding="utf-8")
    output_path.unlink(missing_ok=True)
    return text


def publish_html(html: str, deploy_dir: Path, *, run_id: str, log=None) -> bool:
    """Publica ``index.html`` no clone de deploy; ``False`` = nada mudou.

    Sequencia: gate de seguranca (Parte D) -> escrita atomica (temp no MESMO
    diretorio + ``os.replace``, nunca parcial) -> commit + push da branch
    ``gh-pages``. Se o conteudo e identico ao publicado, nao ha commit nem
    push (evita ruido no historico da branch).
    """
    problems = check_public_safe(html)
    if problems:
        raise RuntimeError(
            "conteudo inseguro para publicacao: " + "; ".join(problems)
        )
    final = deploy_dir / INDEX_NAME
    tmp = deploy_dir / f".{INDEX_NAME}.{os.getpid()}.tmp"
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, final)  # atomico: o index.html nunca fica pela metade
    status = _git(deploy_dir, "status", "--porcelain", "--", INDEX_NAME)
    if not status:
        _log(log, "pages: index.html identico ao publicado; nada a fazer")
        return False
    _git(deploy_dir, "add", "--", INDEX_NAME)
    safe_run = re.sub(r"[^A-Za-z0-9._:-]", "-", str(run_id)) or "unknown"
    _git(deploy_dir, "commit", "-m", f"deploy(run {safe_run}): atualiza ranking publico")
    _git(deploy_dir, "push", "-q", "origin", f"HEAD:{PAGES_BRANCH}")
    _log(log, "pages: deploy publicado (commit %s)",
         _git(deploy_dir, "rev-parse", "--short", "HEAD"))
    return True


def publish_ranking(
    root: Path,
    deploy_dir: Path,
    *,
    exit_code: int,
    eligible: int,
    run_id: str,
    top: int = PUBLIC_TOP,
    log=None,
) -> bool:
    """Publica o ranking do run em GitHub Pages.

    Gate (funcao UNICA ``publication_allowed``, auditoria 23/09): publica com
    vagas elegiveis > 0 e dataset confiavel — exit 0 (ok) OU exit 2 (parcial
    com falhas perifericas de fontes individuais). Dataset vazio (exit 1),
    run truncado (exit 124) ou exit inesperado nao publicam nada — a pagina
    anterior permanece. O HTML e gerado em diretorio temporario e so entra no
    clone apos a verificacao de seguranca.
    """
    if not publication_allowed(exit_code, eligible):
        _log(log, "pages: publicacao pulada (exit=%d eligible=%d — dataset "
                  "vazio/truncado)", exit_code, eligible)
        return False
    origin_url = _git(root, "config", "--get", "remote.origin.url")
    ensure_deploy_clone(deploy_dir, origin_url, root=root, log=log)
    with tempfile.TemporaryDirectory(prefix="if_pages_") as td:
        html = render_ranking_html(root, Path(td) / INDEX_NAME, top=top)
        return publish_html(html, deploy_dir, run_id=run_id, log=log)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publica o ranking atual em GitHub Pages (branch gh-pages).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=str(Path.cwd()), metavar="PATH",
                        help="raiz do repo internship-finder (default: cwd)")
    parser.add_argument("--pages-dir", default=None, metavar="PATH",
                        help="clone de deploy da branch gh-pages "
                             f"(default: ~/internship-finder-ghpages)")
    parser.add_argument("--top", type=int, default=PUBLIC_TOP,
                        help=f"maximo de vagas na pagina (default: {PUBLIC_TOP} = todas)")
    parser.add_argument("--exit-code", type=int, default=0,
                        help="exit code do run de coleta (default: 0). Gate "
                             "publication_allowed: 0/2 autorizam, 1/124 "
                             "bloqueiam (com --eligible > 0).")
    parser.add_argument("--eligible", type=int, default=1,
                        help="vagas elegiveis do run (default: 1). "
                             "eligible <= 0 bloqueia a publicacao.")
    parser.add_argument("--run-id", default=None,
                        help="rotulo do run no commit (default: timestamp atual)")
    parser.add_argument("--dry-run", action="store_true",
                        help="gera o HTML e verifica seguranca, SEM push nem escrita no clone")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    deploy_dir = Path(args.pages_dir or Path.home() / "internship-finder-ghpages").resolve()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if args.dry_run:
        problems: list[str] = []
        with tempfile.TemporaryDirectory(prefix="if_pages_dry_") as td:
            out = Path(td) / INDEX_NAME
            html = render_ranking_html(root, out, top=args.top)
            problems = check_public_safe(html)
            if problems:
                print("CONTEUDO INSEGURO — publicacao bloqueada:")
                for p in problems:
                    print(f"  - {p}")
                return 2
            dry = Path("/tmp/interface_pages_dryrun.html")
            dry.write_text(html, encoding="utf-8")
            print(f"dry-run OK: ranking renderizado e verificado — {len(html)} bytes")
            print(f"(artefato de inspecao: {dry}; NADA foi publicado.)")
        if problems:
            return 2
        return 0

    ok = publish_ranking(
        root, deploy_dir, exit_code=args.exit_code, eligible=args.eligible,
        run_id=run_id, top=args.top,
    )
    print(f"publicacao {'concluida' if ok else 'nao necessaria/pulada'} em {deploy_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())