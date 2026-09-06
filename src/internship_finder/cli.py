"""CLI do internship-finder: coleta orientada a empresas + filtros de utilidade.

Dois modos:

- **Filtro (default):** le vagas coletadas (``--input``), aplica a cascata de
  filtros de utilidade, remove duplicatas, RANQUEIA por compatibilidade com o
  perfil (score + TOP 20; ``--no-rank`` desliga) e grava as ELIGIBLE em
  ``--output`` com ``score``/``score_breakdown``::

      internship-finder                                  # data/jobs.json -> data/eligible_jobs.json (ranqueado)
      internship-finder --country europe --no-area       # Europa, qualquer area
      internship-finder --all                            # copia tudo, sem filtros

- **Coleta:** com ``--companies``, coleta novas vagas (fluxo original, grava o
  bruto em ``--output``, default ``data/jobs.json``) e, em seguida, aplica a
  mesma cascata e grava o resultado em ``--filter-output``::

      internship-finder --companies "Bosch,SAP" --output data/jobs.json

- **Health:** com ``--health [PATH]``, consome o JSONL de metricas de execucao
  (default ``data/collection_metrics.jsonl``), imprime o relatorio de health por
  tenant/ATS (JSON indentado) no stdout e retorna 0. E o UNICO modo quando
  presente::

      internship-finder --health
      internship-finder --health data/collection_metrics.jsonl

Cascata de contagens (tudo ligado por padrao): total -> tipo estudante/estagio
-> area-alvo -> pais (``--country``, default ``de``). ``--all`` desliga os tres
filtros de uma vez. Exit code: 0 se algo foi gravado e a coleta nao teve
falha real; 1 se nada foi gravado/nenhuma vaga; 2 no modo coleta quando houve
falha real de coleta (timeout/erro/sem match), mesmo com vagas coletadas. As
metricas de execucao sao persistidas em JSONL (``--metrics``, default
``data/collection_metrics.jsonl`` no modo coleta). No modo health, arquivo
inexistente/ilegivel -> mensagem de erro no stderr e exit != 0.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

from internship_finder.collectors.ats_scraper import collect_company
from internship_finder.dedup import deduplicate
from internship_finder.filters import parse_country_spec, select_eligible
from internship_finder.health import build_health_report
from internship_finder.metrics import read_metrics, utcnow_iso, write_metrics
from internship_finder.models.job import Job, normalize_job_dict
from internship_finder.ranking import rank_jobs
from internship_finder.registry import CompanyRegistry, registry_names
from internship_finder.storage.sqlite_store import SqliteStore

log = logging.getLogger("internship_finder")

CSV_COLUMNS = [
    "id",
    "title",
    "company",
    "location",
    "country",
    "country_iso",
    "remote",
    "url",
    "source",
    "external_id",
    "employment_type",
    "internship",
    "posted_at",
    "application_deadline",
    "collected_at",
    "score",
]


def save_outputs(jobs: list[Job] | list[dict], output: Path) -> None:
    """Grava JSON e CSV (CSV derivado do nome do JSON). Aceita Job ou dict.

    Contrato (P3 #20/ACH-18, medido em 05/09): JSON = fonte completa (todos
    os campos do Job, inclusive ``description``/``raw``/``score_breakdown``);
    CSV = visao tabular com as colunas de CSV_COLUMNS (15 + ``remote`` desde
    06/09 — antes, ``remote`` ficava de fora em 38.038/38.038 linhas de
    jobs.csv e 224/224 de eligible_jobs.csv). ``description``/``raw``/
    ``score_breakdown`` ficam de fora do CSV de proposito (texto grande/
    aninhado; a fonte de verdade e o JSON).
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [j.to_dict() if hasattr(j, "to_dict") else j for j in jobs]
    with output.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    log.info("salvos: %s e %s", output, csv_path)


def print_cascade(counts: dict[str, int], country: str) -> None:
    """Imprime as contagens em cascata: total -> tipo -> area -> pais."""
    print("=== Cascata de filtros ===")
    print(f"  total            : {counts['total']}")
    print(f"  + tipo estudante : {counts['tipo']}")
    print(f"  + area-alvo      : {counts['area']}")
    print(f"  + pais           : {counts['pais']}   (--country {country})")


def print_examples(jobs: list[dict] | list[Job], limit: int = 15) -> None:
    """Exemplos da lista final (titulo, empresa, local, URL)."""
    for j in jobs[:limit]:
        d = j.to_dict() if hasattr(j, "to_dict") else j
        print(f"  - {d['title']} | {d['company']} | {d.get('location') or '-'} | {d['url']}")
    if len(jobs) > limit:
        print(f"  ... +{len(jobs) - limit} vagas (lista completa no JSON/CSV)")


def print_dedup_report(dedup_stats: dict[str, int]) -> None:
    """Linha do relatorio de dedup: quantas removidas e por qual chave."""
    total = sum(dedup_stats.values())
    if not total:
        return
    print(
        f"dedup: removidas {total} "
        f"({dedup_stats.get('external_id', 0)} por external_id, "
        f"{dedup_stats.get('url', 0)} por URL, "
        f"{dedup_stats.get('company+title+location', 0)} por company+title+location)"
    )


def print_ranking(jobs: list[dict], top: int = 20) -> None:
    """TOP N ranqueados com score e breakdown curto (area/skills/lang/tipo/loc/pen)."""
    n = min(top, len(jobs))
    print(f"\n=== TOP {n} (ranking por perfil) ===")
    for i, j in enumerate(jobs[:n], 1):
        b = j.get("score_breakdown") or {}
        parts = " ".join(f"{k} {v:+.1f}" for k, v in b.items())
        print(
            f"  {i:>2}. {j['score']:6.2f} | {j['title'][:60]} | "
            f"{j.get('company')} | {parts}"
        )
    if len(jobs) > n:
        print(f"  ... +{len(jobs) - n} vagas (score completo no JSON/CSV)")


def run_filter_pipeline(
    jobs: list[Job] | list[dict],
    *,
    student: bool,
    area: bool,
    country: str,
    output: Path,
    dedup: bool = True,
    rank: bool = True,
    metrics: Path | None = None,
    run_id: str | None = None,
) -> int:
    """Aplica a cascata, remove duplicatas, ranqueia por perfil, imprime e grava.

    A deduplicacao roda sobre o conjunto ja filtrado (a saida eligible nao
    tem duplicatas); ``dedup=False`` (--no-dedup) a desliga. O ranking
    (``rank=True``, default) adiciona ``score`` + ``score_breakdown`` a cada
    vaga, ordena desc (melhores primeiro) e imprime o TOP 20; ``rank=False``
    (--no-rank) mantem a ordem original e imprime exemplos como antes.

    Se ``metrics`` for fornecido, grava um registro de resumo do run
    (``type: run``) em JSONL com ``total_collected``/``filtered``/
    ``dedup_removed``/``eligible`` (o total coletado e o ``len(jobs)`` de
    entrada; ``filtered`` e o final da cascata; ``dedup_removed`` so conta
    quando ``dedup=True``).
    """
    # Normaliza as strings de entrada (mesma regra dos validators do Job)
    # antes da cascata. O caminho filtro opera sobre dicts, sem reconstruir
    # ``Job``: dicts crus passam por ``normalize_job_dict``; instancias de
    # ``Job`` ja passaram pelos validators (idempotente, inofensivo).
    normalized = [
        j.to_dict() if hasattr(j, "to_dict") else normalize_job_dict(j) for j in jobs
    ]
    selected, counts = select_eligible(
        normalized,
        student=student,
        area=area,
        country=country,
    )
    print_cascade(counts, country)
    if dedup:
        selected, dedup_stats, _ = deduplicate(selected)
        print_dedup_report(dedup_stats)
    if rank:
        selected = rank_jobs(selected)
    print(f"\n=== {len(selected)} vagas eligible{', ranqueadas por perfil' if rank else ''} ===")
    if rank:
        print_ranking(selected)
    else:
        print_examples(selected)
    save_outputs(selected, output)

    if metrics is not None:
        write_metrics(
            metrics,
            [
                {
                    "type": "run",
                    "run_id": run_id or utcnow_iso(),
                    "timestamp": utcnow_iso(),
                    "total_collected": len(jobs),
                    "filtered": counts["pais"],
                    "dedup_removed": sum(dedup_stats.values()) if dedup else 0,
                    "eligible": len(selected),
                }
            ],
        )
    return 0 if selected else 1


def _parse_duration(duration: str | None) -> float | None:
    """Converte a duracao formatada do summary (ex.: ``0.4s``) em float (segundos).

    Devolve ``None`` quando ``duration`` e ``None``/vazio ou nao pode ser
    interpretado como numero — a metrica deve ser nativamente numerica no JSONL.
    """
    if duration is None:
        return None
    text = str(duration).strip().lower()
    if text.endswith("s"):
        text = text[:-1]
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _split_summary_error(item: tuple) -> tuple[str, str | None, str]:
    """Desempacota uma entrada de ``summary``[``timeout``|``failed``].

    O formato novo e ``(source, code, err)``; o antigo ``(source, err)`` ainda
    pode surgir de testes/mocks. Devolve sempre ``(source, code, err)`` com
    ``code=None`` quando a entrada antiga nao traz codigo.
    """
    if len(item) >= 3:
        source, code, err = item[0], item[1], item[2]
    else:
        source, err = item[0], item[1]
        code = None
    return source, code, err


def _tenant_record(
    run_id: str,
    company: str,
    source: str,
    status: str,
    collected: int,
    duration: str | None = None,
    error: str | None = None,
    *,
    error_code: str | None = None,
) -> dict:
    """Registro de metricas de um tenant (linha ``type: tenant`` do JSONL).

    ``source`` e ``ats:slug`` (ex.: ``successfactors:jobs``) — o ATS e o
    prefixo ate o primeiro ``:``. ``duration`` chega como string formatada
    do summary (ex.: ``0.4s``) e e convertida em float (segundos) antes da
    persistencia; ``error`` carrega a mensagem de timeout/erro; ``error_code``
    (kwarg opcional) o codigo estruturado (ex.: ``TIMEOUT``) quando houver —
    ``null`` em estados ok/empty/skipped ou quando o registro nao tem codigo.
    """
    ats = source.split(":", 1)[0] if source else ""
    return {
        "type": "tenant",
        "run_id": run_id,
        "timestamp": utcnow_iso(),
        "company": company,
        "source": source,
        "ats": ats,
        "status": status,
        "collected": collected,
        "error": error,
        "error_code": error_code,
        "duration": _parse_duration(duration),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Coleta vagas por empresa e/ou filtra vagas candidataveis "
        "(estudante/estagio + area-alvo + pais)."
    )
    parser.add_argument(
        "--companies",
        help='Nomes separados por virgula, ex.: "Bosch,SAP" (modo coleta; sem ele, '
        "filtra --input)",
    )
    parser.add_argument(
        "--registry",
        action="store_true",
        help="Modo coleta orientado a registry: usa as empresas ENABLED do "
        "CompanyRegistry (fonte de verdade em codigo) como lista de coleta. "
        "Com --companies, restringe a esse subconjunto, na ordem informada.",
    )
    parser.add_argument(
        "--input",
        default="data/jobs.json",
        help="JSON bruto de entrada (modo filtro; default: data/jobs.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="modo filtro: saida eligible (default: data/eligible_jobs.json); "
        "modo coleta: saida bruta (default: data/jobs.json)",
    )
    parser.add_argument(
        "--filter-output",
        default="data/eligible_jobs.json",
        help="modo coleta: saida eligible (default: data/eligible_jobs.json)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="Timeout por scraper (s) — modo coleta (deve ser > 0; valor "
        "invalido -> erro claro, exit 2)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximo de vagas por tenant (0 = sem limite; aplicado APOS a "
        "coleta, por tenant) — modo coleta (negativo -> erro claro, exit 2)",
    )
    parser.add_argument(
        "--include-descriptions",
        action="store_true",
        help="Busca descricao por vaga (mais lento em ATS que exigem chamada por vaga)",
    )
    parser.add_argument(
        "--student",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Filtra tipo estudante/estagio (default: ligado; --no-student desliga)",
    )
    parser.add_argument(
        "--area",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Filtra areas-alvo do dono (Supply Chain, Procurement, BI, Analytics, "
        "Automacao; default: ligado; --no-area desliga)",
    )
    parser.add_argument(
        "--country",
        "--countries",
        dest="country",
        default="de",
        help="Pais/localizacao: ISO alpha-2 (ex.: 'de,at,ch'), 'europe', 'remote' "
        "ou 'all' (default: de; valor invalido -> erro)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Desliga os tres filtros (tipo, area, pais): copia o conjunto inteiro",
    )
    parser.add_argument(
        "--dedup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Remove duplicatas da saida (default: ligado; --no-dedup desliga)",
    )
    parser.add_argument(
        "--rank",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Rankeia as vagas por compatibilidade com o perfil (score + TOP 20; "
        "default: ligado; --no-rank desliga e mantem a ordem original)",
    )
    parser.add_argument(
        "--metrics",
        default=None,
        help="Caminho do JSONL de metricas da execucao (default no modo coleta: "
        "data/collection_metrics.jsonl)",
    )
    parser.add_argument(
        "--sqlite",
        default=None,
        metavar="PATH",
        help="Modo coleta: persiste o historico de cada vaga (first_seen/"
        "last_seen/active/archived) no banco sqlite3 em PATH (default: desligado). "
        "Sem a flag, o comportamento e identico ao atual.",
    )
    parser.add_argument(
        "--health",
        nargs="?",
        const="data/collection_metrics.jsonl",
        default=None,
        metavar="PATH",
        help="Modo health (unico quando presente): le o JSONL de metricas de "
        "execucao (default: data/collection_metrics.jsonl), imprime o relatorio "
        "por tenant/ATS em JSON no stdout e retorna 0. Arquivo inexistente/"
        "ilegivel -> erro no stderr e exit != 0.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.health is not None:
        health_path = Path(args.health)
        if not health_path.exists():
            print(f"ERRO: arquivo de metricas nao encontrado: {health_path} "
                  "(colete antes com --companies)", file=sys.stderr)
            return 1
        try:
            records = read_metrics(health_path)
        except Exception as exc:  # noqa: BLE001 - sem traceback feio para o usuario
            print(f"ERRO: nao foi possivel ler {health_path}: {exc}", file=sys.stderr)
            return 1
        report = build_health_report(records)
        # P3 lote 1: expoe o estado por empresa (CompanyRegistry.company_status,
        # read-only e defensivo) na chave "companies" — fecha o gap doc x codigo
        # (o README ja documenta essa exposicao no relatorio do --health).
        report["companies"] = CompanyRegistry().company_status(health_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.all:
        args.student = False
        args.area = False
        args.country = "all"

    # P2 #15 (ACH-11): valida a spec de pais cedo (antes de input/coleta).
    # Antes, valor invalido virava 0 vagas silencioso (frozenset que nunca
    # casa) ou token nao-ISO era ignorado; agora e erro claro com exit 2.
    # Especs validas seguem o MESMO parse de select_eligible — resultado
    # do filtro inalterado.
    try:
        parse_country_spec(args.country)
    except ValueError as exc:
        parser.error(str(exc))

    # P3 #20 (ACH-14): valida flags de coleta cedo. Antes, --timeout <= 0 e
    # --limit negativo eram aceitos silenciosamente com comportamento
    # indefinido (deadline do subprocesso virava so a margem / slice ``[:-k]``
    # sutil da lista). Agora: erro claro (exit 2), antes de input/coleta,
    # como a validacao de --country (P2 #15). Valores validos inalterados;
    # refresh_daily.py usa --timeout 60 (ok).
    if args.timeout <= 0:
        parser.error("--timeout deve ser > 0 (segundos por scraper)")
    if args.limit < 0:
        parser.error("--limit deve ser >= 0 (0 = sem limite)")

    if args.companies or args.registry:
        names = [n.strip() for n in args.companies.split(",") if n.strip()] if args.companies else []
        if args.registry:
            # Modo orientado a registry: a lista vem do CompanyRegistry. Sem
            # --companies, são TODAS as ENABLED; com --companies, o subconjunto
            # na ordem informada. API total: --companies "A,B" segue idêntico.
            registry = CompanyRegistry()
            names = registry_names(registry, names or None)
            if not names:
                parser.error("--registry sem nenhuma empresa habilitada no registry")
        if not names:
            parser.error("--companies vazio")

        run_id = utcnow_iso()
        metrics_path = Path(args.metrics or "data/collection_metrics.jsonl")
        all_jobs: list[Job] = []
        summaries: list[tuple[str, dict]] = []
        for name in names:
            jobs, summary = collect_company(
                name,
                timeout=args.timeout,
                include_descriptions=args.include_descriptions,
                limit=args.limit,
            )
            summaries.append((name, summary))
            all_jobs.extend(jobs)
            print(f"Found {len(jobs)} jobs for {name}")
            for j in jobs[:15]:
                print(f"  - {j}")
            if len(jobs) > 15:
                print(f"  ... +{len(jobs) - 15} vagas (lista completa no JSON/CSV)")

        total = len(all_jobs)
        print(f"\n=== TOTAL: {total} vagas ===")
        # Falhas reais de coleta (timeout/erro/nao encontrada) tornam a coleta
        # parcialmente degradada; EMPTY (tenant respondeu com 0 vagas) e
        # legitimo e nao conta como falha. Acumula para o exit code.
        had_failure = False
        tenant_records: list[dict] = []
        for name, summary in summaries:
            for source, n, dt in summary["ok"]:
                print(f"  OK   {source}: {n} vagas ({dt})")
                tenant_records.append(_tenant_record(run_id, name, source, "ok", n, dt))
            for source, dt in summary.get("empty", []):
                print(f"  EMPTY {source}: 0 vagas ({dt})")
                tenant_records.append(_tenant_record(run_id, name, source, "empty", 0, dt))
            for item in summary.get("timeout", []):
                source, code, err = _split_summary_error(item)
                print(f"  TIMEOUT {source}: {err}")
                had_failure = True
                tenant_records.append(_tenant_record(
                    run_id, name, source, "timeout", 0, None, err, error_code=code))
            for item in summary["failed"]:
                source, code, err = _split_summary_error(item)
                print(f"  FAIL {source}: {err}")
                had_failure = True
                tenant_records.append(_tenant_record(
                    run_id, name, source, "error", 0, None, err, error_code=code))
            for source in summary["skipped"]:
                print(f"  SKIP {source}: sem scraper no pacote")
                tenant_records.append(_tenant_record(run_id, name, source, "skipped", 0, None))
            if summary["not_found"]:
                print(f"  NONE {name}: sem match exato na base")
                had_failure = True
                tenant_records.append(_tenant_record(run_id, name, "", "not_found", 0, None, "sem match exato"))

        if not total:
            write_metrics(metrics_path, tenant_records)
            log.error("nenhuma vaga coletada; verifique as empresas e o pacote ats-scrapers")
            return 1
        # Salva e processa SEMPRE (nao descarta o que foi coletado), mas uma
        # coleta com falhas reais sinaliza degradacao no exit code (>=2), para
        # a automacao detectar; exit 1 ja e reservado para "nenhuma vaga".
        raw_output = Path(args.output or "data/jobs.json")
        save_outputs(all_jobs, raw_output)
        # Persistencia SQLite (opcional, P1 #5): roda no processo pai apos o
        # merge dos jobs vindos dos subprocessos (escritor unico). Sem --sqlite,
        # nada muda — comportamento identico ao atual. Uma falha de escrita
        # nunca derruba a coleta: qualquer erro (caminho inacessivel, disco
        # cheio, etc.) e logado e o run segue.
        if args.sqlite:
            sqlite_path = Path(args.sqlite)
            try:
                sqlite_path.parent.mkdir(parents=True, exist_ok=True)
                with SqliteStore(sqlite_path) as store:
                    stats = store.run(all_jobs)
                print(
                    f"\n=== SQLite {sqlite_path}: {len(all_jobs)} vagas no run "
                    f"({stats['inserted']} novas, {stats['reactivated']} "
                    f"reativadas) ==="
                )
            except Exception as exc:  # noqa: BLE001 - a coleta nunca cai por sqlite
                log.error("sqlite falhou e foi ignorado (%s): %s", sqlite_path, exc)
        # Tenant records primeiro; o run record (resumo) e escrito dentro do
        # ``run_filter_pipeline``, ao final do processamento.
        write_metrics(metrics_path, tenant_records)
        pipeline_rc = run_filter_pipeline(
            all_jobs,
            student=args.student,
            area=args.area,
            country=args.country,
            output=Path(args.filter_output),
            dedup=args.dedup,
            rank=args.rank,
            metrics=metrics_path,
            run_id=run_id,
        )
        if had_failure:
            log.warning("coleta parcial com falhas (timeout/erro/sem match); "
                        "resultado pode estar incompleto")
            return 2
        return pipeline_rc

    # Modo filtro (default): le vagas ja coletadas e filtra.
    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"--input nao encontrado: {input_path} (colete antes com --companies)")
    with input_path.open(encoding="utf-8") as fh:
        jobs = json.load(fh)
    output = Path(args.output or "data/eligible_jobs.json")
    return run_filter_pipeline(
        jobs,
        student=args.student,
        area=args.area,
        country=args.country,
        output=output,
        dedup=args.dedup,
        rank=args.rank,
    )


if __name__ == "__main__":
    raise SystemExit(main())
