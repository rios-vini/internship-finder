"""F12 — Traducao SOB DEMANDA de descricoes DE->EN com cache persistente.

Ferramenta MANUAL do dono (VPS). O cron/refresh NUNCA chama LLM (contrato
F12): este script e o UNICO escritor do ``data/translation_cache.json``
e roda so quando o dono pede. Uso tipico::

    .venv/bin/python scripts/translate_description.py --top 5
    .venv/bin/python scripts/translate_description.py --job-id '<id>'
    .venv/bin/python scripts/translate_description.py --top 10 --force

Onde esta a traducao depois? O render ``scripts/minimal_page.py`` le o
cache (best-effort) na publicacao seguinte — o cron 09:00 UTC publica sozinho,
ou o dono publica na hora com ``scripts/publish_pages.py`` (sem --dry-run).
A pagina publica e ESTATICA (GitHub Pages, sem backend): nao existe botao
"traduza ja" — o fluxo honesto e traduzir aqui e esperar o render seguinte.

Seguranca (padrao do enrichment/llm.py): a key vem EXCLUSIVAMENTE de
``NVIDIA_API_KEY`` — env OU injetada do ``--config`` (.env padrao do repo,
mesmo mecanismo do refresh_daily). NUNCA impressa; erros passam por
``_sanitize``; o cache e o HTML nao carregam nenhum segredo (gate
``check_public_safe`` do publish segue dono da pagina).

Exit codes: 0 = concluido (traducoes novas + cache hits); 1 = erro de
setup (sem key, input ausente/invalido, selecao vazia); 2 = LLM falhou em
>=1 vaga (sucessos anteriores SAO gravados no cache — re-run drena o resto).

Offline por construcao nos testes: transport injetavel (FakeTransport,
padrao do test_enrichment); nenhum teste toca rede.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder import display_translate as dt  # noqa: E402
from internship_finder.enrichment.llm import get_api_key  # noqa: E402

EXIT_OK = 0
EXIT_SETUP = 1
EXIT_LLM_FAILED = 2


def repo_root() -> Path:
    """Raiz do repo (este script vive em ``<repo>/scripts/``)."""
    return Path(__file__).resolve().parents[1]


def _load_env_key(config_path: Path | None) -> str:
    """Key de ``NVIDIA_API_KEY``: env herda; senao injeta do arquivo config.

    Mesmo padrao do refresh_daily (env OU .env). O valor NUNCA e impresso.
    """
    key = get_api_key()
    if key:
        return key
    if config_path is None:
        return ""
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == "NVIDIA_API_KEY":
            return value.strip().strip('"').strip("'")
    return ""


def _load_jobs(input_path: Path) -> list[dict]:
    """Le o eligible_jobs.json (lista ranqueada). Erro claro se invalido."""
    import json

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(
            f"[setup] nao consegui ler {input_path}: {exc}"
        ) from None
    except ValueError as exc:
        raise SystemExit(
            f"[setup] {input_path} nao e JSON valido: {exc}"
        ) from None
    if not isinstance(data, list):
        raise SystemExit(
            f"[setup] formato inesperado em {input_path}: esperado lista"
        )
    return data


def _select_jobs(jobs: list[dict], *, job_ids: list[str] | None,
                 top_n: int | None) -> list[dict]:
    """Selecao deterministica: --job-id exatos; senao --top N por score."""
    if job_ids:
        wanted: dict[str, dict] = {}
        for job in jobs:
            jid = str(job.get("id") or "")
            if jid in job_ids and jid not in wanted:
                wanted[jid] = job
        return [wanted[j] for j in job_ids if j in wanted]
    ranked = sorted(
        jobs, key=lambda j: (float(j.get("score") or 0.0), str(j.get("id"))),
        reverse=True,
    )
    return ranked[: (top_n or 0)] if top_n else []


def main(argv: list[str] | None = None, *, transport=None,
         backoff: tuple[float, ...] | None = None,
         sleep=None) -> int:
    """CLI da traducao sob demanda (testes injetam transport/backoff/sleep)."""
    parser = argparse.ArgumentParser(
        description="F12: traduz descricoes DE->EN sob demanda e grava no "
                    "cache data/translation_cache.json (LLM GLM 5.3 flash; "
                    "key NVIDIA_API_KEY via env ou --config).",
    )
    parser.add_argument("--input", default=None, metavar="PATH",
                        help="eligible_jobs.json do run (default: "
                             "data/eligible_jobs.json do repo)")
    parser.add_argument("--cache", default=None, metavar="PATH",
                        help="caminho do cache (default: "
                             "data/translation_cache.json do repo)")
    parser.add_argument("--config", default=None, metavar="PATH",
                        help="arquivo .env com NVIDIA_API_KEY (default: "
                             ".env da raiz do repo; o shell env ganha sempre)")
    parser.add_argument("--job-id", action="append", default=None,
                        metavar="ID",
                        help="id canonico da vaga (repetivel)")
    parser.add_argument("--top", type=int, default=None, metavar="N",
                        help="traduz as N primeiras vagas por score")
    parser.add_argument("--force", action="store_true",
                        help="re-traduz mesmo com cache hit")
    args = parser.parse_args(argv)

    root = repo_root()
    input_path = Path(args.input) if args.input else root / "data" / "eligible_jobs.json"
    cache_path = Path(args.cache) if args.cache else root / "data" / dt.CACHE_FILE_NAME
    config_path = Path(args.config) if args.config else root / ".env"

    if not args.job_id and not args.top:
        parser.error("informe --job-id ID e/ou --top N (nada a fazer sem seleção)")

    # Tarefa 5 (fallback offline): sem key no env/config -> falha graciosa
    # com mensagem clara. Titulos por dicionario + glossario sao OFFLINE e
    # nao dependem desta ferramenta — seguem funcionando no render.
    key = _load_env_key(config_path)
    if not key:
        print(
            "[setup] NVIDIA_API_KEY ausente: defina na env ou no --config "
            f"({config_path}) e rode de novo. Nada foi gravado; a pagina "
            "continua com titulos EN (dicionario) + glossario, que sao "
            "offline. Este script nao roda sem key (nao ha fallback de "
            "traducao de DESCRICAO sem LLM)."
        )
        return EXIT_SETUP

    if not input_path.exists():
        print(f"[setup] {input_path} nao existe — rode a coleta antes.")
        return EXIT_SETUP
    jobs = _load_jobs(input_path)

    cache = dt.load_translation_cache(cache_path)
    if cache_path.exists() and not cache:
        print("[aviso] cache existente ilegivel/vazio — sera reescrito")

    selected = _select_jobs(jobs, job_ids=args.job_id, top_n=args.top)
    missing = [i for i in (args.job_id or []) if i not in
               {str(j.get("id")) for j in selected}]
    if missing:
        print(f"[setup] id(s) nao encontrado(s) no input: {', '.join(missing)}")
        return EXIT_SETUP
    if not selected:
        print("[setup] selecao vazia — nada a fazer.")
        return EXIT_SETUP

    todo: list[dict] = []
    hits = 0
    for job in selected:
        jid = str(job.get("id") or "")
        desc = " ".join(str(job.get("description") or "").split())
        if not desc:
            print(f"[skip] {jid}: sem descricao no snapshot (nada a traduzir)")
            continue
        if not args.force and jid in cache:
            print(f"[cache] {jid}: ja traduzida (use --force para refazer)")
            hits += 1
            continue
        todo.append(job)

    if not todo:
        print(f"nada a traduzir ({hits} cache hits) — cache: {cache_path}")
        return EXIT_OK

    print(f"traduzindo {len(todo)} descricao(oes) (cache: {cache_path})…")
    failures = 0
    for job in todo:
        jid = str(job.get("id") or "")
        desc = " ".join(str(job.get("description") or "").split())
        result, usage, latency, attempts, error, truncated = dt.translate_text(
            key, desc,
            transport=transport,
            backoff=backoff or dt.DEFAULT_BACKOFF_S,
            sleep=sleep or dt.time.sleep,
        )
        if error or result is None:
            failures += 1
            err = error or "empty_content"
            print(f"[erro] {jid}: {err} (tentativas: {attempts}) — "
                  "nao gravada; re-run re-tenta")
            continue
        cache[jid] = {"en": result, "ts": dt.time.time()}
        spent = ""
        if isinstance(usage, dict):
            spent = f" · tokens in/out: {usage.get('prompt_tokens')}/" \
                    f"{usage.get('completion_tokens')}"
        print(f"[ok] {jid} · {latency}s · {len(result)} chars EN"
              f"{' · AVISO: entrada cortada em 12k chars' if truncated else ''}"
              f"{spent}")

    if cache and (todo or hits):
        dt.save_translation_cache(cache_path, cache)

    if failures:
        print(f"concluido com {failures} falha(s) — sucessos estao no cache; "
              "re-run drena as falhas")
        return EXIT_LLM_FAILED
    print(
        f"pronto: {len(todo)} traducao(oes) gravadas em {cache_path} "
        "— aparecem no render seguinte (cron 09:00 UTC ou "
        "scripts/publish_pages.py manual)"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
