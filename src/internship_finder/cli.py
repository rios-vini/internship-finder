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
import os
import stat
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from internship_finder.collectors.ats_scraper import collect_company
from internship_finder.dataset_source import (
    DATASET_BUDGET_SECONDS,
    collect_dataset_jobs,
)
from internship_finder.direct_fetch import (
    DIRECT_FETCH_BUDGET_SECONDS,
    collect_direct_fetch,
)
from internship_finder.dedup import deduplicate
from internship_finder.mirror_dedup import KEY_MIRRORS_DE_EN, deduplicate_mirrors_de_en
from internship_finder.filters import parse_country_spec, select_eligible
from internship_finder.health import build_health_report
from internship_finder.hydration import hydrate_descriptions, print_hydration_report
from internship_finder.metrics import read_metrics, utcnow_iso, write_metrics
from internship_finder.official_page import (
    OFFICIAL_PAGE_LIMIT,
    enrich_official_pages,
    print_official_page_report,
)
from internship_finder.models.job import Job, normalize_job_dict
from internship_finder.opportunity_intel import (
    company_intel_for,
    load_company_intel,
    visa_friendly,
)
from internship_finder.ranking import rank_jobs
from internship_finder.registry import (
    CompanyRegistry,
    latest_run_tenants,
    registry_names,
    tenant_consistency_report,
)
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
    # F5 — sinal visa_friendly da EMPRESA (visa_policy curada ∈
    # {explicit_support, unclear}); aditivo no fim do contrato. NAO entra no
    # score (regra de independencia). ``extrasaction="ignore"`` mantem
    # compat para dicts sem o campo.
    "visa_friendly",
]


def _write_atomic(output: Path, write: Callable[[TextIO], None]) -> None:
    """Grava ``output`` com substituicao atomica, delegando a serializacao.

    ``write(fh)`` recebe o handle de texto (UTF-8) do arquivo temporario e
    deve escrever TODO o conteudo. A mecanica e a mesma para JSON e CSV:

    1. arquivo temporario no MESMO diretorio do destino (mesmo filesystem ->
       ``os.replace`` atomico, sem risco de EXDEV);
    2. escreve tudo no temporario;
    3. fecha (a saida do ``with``);
    4. substitui o final com ``os.replace``.

    Garantia: o arquivo final nunca fica truncado/parcial — em qualquer falha
    de escrita ou substituicao ele continua sendo o arquivo valido anterior;
    em sucesso, vira o novo completo de uma vez (quem ler nunca ve uma versao
    pela metade). Em falha, o temporario e removido.

    Sem ``fsync`` de proposito: a garantia que o projeto exige e contra
    escrita parcial (crash de processo, erro de I/O, disco cheio durante a
    geracao), nao durabilidade contra queda de energia — os dados sao
    regenerados a cada run e o ``rotate`` do refresh ja preserva o snapshot
    anterior no archive. ``mkstemp`` cria com 0600; o modo do arquivo final
    reproduz o comportamento do ``open("w")`` atual (preserva o modo do
    arquivo existente na substituicao; 0666 & umask para arquivo novo).
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    tmp_path = Path(tmp_name)
    try:
        if output.exists():
            os.chmod(tmp_path, stat.S_IMODE(output.stat().st_mode))
        else:
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(tmp_path, 0o666 & ~umask)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            write(fh)
        os.replace(tmp_path, output)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError as unlink_exc:
            log.warning("temporario de %s nao removido apos falha: %s",
                        output, unlink_exc)
        raise


def _write_json_atomic(rows: list[dict], output: Path) -> None:
    """Grava ``rows`` como JSON em ``output`` com substituicao atomica.

    Encapsula o formato JSON sobre ``_write_atomic`` (tempfile no mesmo
    diretorio + ``os.replace``). Ver ``_write_atomic`` para as garantias.
    """
    _write_atomic(
        output,
        lambda fh: json.dump(rows, fh, ensure_ascii=False, indent=2),
    )


def _dump_csv(fh: TextIO, rows: list[dict]) -> None:
    """Escreve ``rows`` como CSV tabular no handle ``fh`` (formato fixo).

    Contrato ACH-18: apenas as colunas de ``CSV_COLUMNS`` (``description``/
    ``raw``/``score_breakdown`` ficam de fora de proposito — texto grande/
    aninhado; a fonte de verdade e o JSON). ``extrasaction="ignore"`` mantem
    o comportamento atual para dicts com campos fora do contrato.
    """
    writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


def _apply_visa_friendly(jobs: list[dict]) -> int:
    """F5: adiciona ``visa_friendly: bool`` a cada vaga (sinal de EMPRESA).

    Deriva do arquivo CURADO ``company_intel/company_intelligence.json``
    (mesma fonte do bloco Opportunity Intelligence da interface): empresa
    com ``visa_policy_state`` ∈ {explicit_support, unclear} => True. Best
    effort e aditivo — arquivo ausente/invalido deixa as vagas SEM o
    campo (o CSV escreve vazio; a interface trata ausente como False);
    nunca derruba o run, nunca altera score/ordem/eligibilidade.

    Retorna o numero de vagas com visa_friendly=True (para log/metricas).
    """
    intel_map = load_company_intel()
    if not intel_map:
        return 0
    n = 0
    for job in jobs:
        entry = company_intel_for(job, intel_map)
        job["visa_friendly"] = visa_friendly(entry)
        if job["visa_friendly"]:
            n += 1
    return n


def save_outputs(jobs: list[Job] | list[dict], output: Path) -> None:
    """Grava JSON e CSV (CSV derivado do nome do JSON). Aceita Job ou dict.

    Contrato (P3 #20/ACH-18, medido em 05/09): JSON = fonte completa (todos
    os campos do Job, inclusive ``description``/``raw``/``score_breakdown``);
    CSV = visao tabular com as colunas de CSV_COLUMNS (15 + ``remote`` desde
    06/09 — antes, ``remote`` ficava de fora em 38.038/38.038 linhas de
    jobs.csv e 224/224 de eligible_jobs.csv). ``description``/``raw``/
    ``score_breakdown`` ficam de fora do CSV de proposito (texto grande/
    aninhado; a fonte de verdade e o JSON).

    Ambos JSON e CSV sao escritos com substituicao ATOMICA (``_write_atomic``:
    tempfile no mesmo diretorio + ``os.replace``) — se a geracao falhar no
    meio, o arquivo final existente permanece valido e inalterado (nunca
    truncado), e o temporario e removido.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = [j.to_dict() if hasattr(j, "to_dict") else j for j in jobs]
    _write_json_atomic(rows, output)
    csv_path = output.with_suffix(".csv")
    _write_atomic(csv_path, lambda fh: _dump_csv(fh, rows))
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
    """Linha do relatorio de dedup: quantas removidas e por qual chave.

    Inclui o sub-estagio de mirrors DE/EN (Fase C) — as remocoes dele
    somam no total junto com as chaves classicas.
    """
    total = sum(dedup_stats.values())
    if not total:
        return
    print(
        f"dedup: removidas {total} "
        f"({dedup_stats.get('external_id', 0)} por external_id, "
        f"{dedup_stats.get('url', 0)} por URL, "
        f"{dedup_stats.get('company+title+location', 0)} por company+title+location, "
        f"{dedup_stats.get(KEY_MIRRORS_DE_EN, 0)} por mirrors DE/EN (requisition_id))"
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
    hydrate: bool = True,
    mirror_dedup: bool = True,
    official_page: bool = False,
    official_page_limit: int | None = None,
    official_page_transport: Any | None = None,
    metrics: Path | None = None,
    run_id: str | None = None,
) -> int:
    """Aplica a cascata, remove duplicatas, ranqueia por perfil, imprime e grava.

    A deduplicacao roda sobre o conjunto ja filtrado (a saida eligible nao
    tem duplicatas); ``dedup=False`` (--no-dedup) a desliga. O ranking
    (``rank=True``, default) adiciona ``score`` + ``score_breakdown`` a cada
    vaga, ordena desc (melhores primeiro) e imprime o TOP 20; ``rank=False``
    (--no-rank) mantem a ordem original e imprime exemplos como antes.

    Hidratacao seletiva (Fase A, ``hydrate=True`` default): entre dedup e
    rank, vagas elegiveis SEM description ganham a description completa via
    ``ats-scrapers`` (detail por vaga, best-effort — falha nao derruba o run
    nem muda exit codes; ``--no-hydrate-descriptions`` desliga). Elegibilidade
    congela ANTES (a cascata le description); o ranking e os enriquecimentos
    downstream (app_intel sobre eligible_jobs.json) passam a ver o texto.

    Official-page enrichment (Fase D, ``official_page=False`` default desde
    F1 01/10): quando ligado (``--official-page``), apos a hidratacao e
    ANTES do ranking, vagas candidatas (description ausente/teaser OU sem
    deadline OU sem salary) ganham evidencia estruturada da pagina oficial
    (JSON-LD JobPosting) em ``job["official_page"]`` — UM GET por vaga,
    best-effort, sem LLM/browser; ``--no-official-page`` desliga;
    ``--official-page-limit N`` controla o tamanho do lote (default 150,
    cortado por prioridade). Motivo do OFF (auditoria F1): cookie-wall e
    paginas JS-rendered tornam o estagio sem retorno — o codigo permanece
    preservado para uso sob demanda. Falha por vaga nunca derruba o run nem
    muda exit codes.

    Se ``metrics`` for fornecido, grava um registro de resumo do run
    (``type: run``) em JSONL com ``total_collected``/``filtered``/
    ``dedup_removed``/``eligible`` (o total coletado e o ``len(jobs)`` de
    entrada; ``filtered`` e o final da cascata; ``dedup_removed`` so conta
    quando ``dedup=True``) e, quando a hidratacao roda, um registro
    ``type: hydration`` com as estatisticas da fase (cobertura antes/depois,
    sucesso/falha/skip por ATS, duracao) e, quando o official-page roda, um
    registro ``type: official_page`` com as estatisticas da fase.
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
    dedup_stats: dict[str, int] = {}
    if dedup:
        selected, dedup_stats, _ = deduplicate(selected)
    if dedup and mirror_dedup:
        # Fase C: sub-estagio de mirrors DE/EN (requisition_id + titulo
        # normalizado como guardrail linguistico). Roda DENTRO do estagio
        # de dedup, imediatamente apos a cascata classica e ANTES da
        # hidratacao — os mirrors saem do conjunto elegivel antes do
        # detail-fetch (economiza fetch de vagas que seriam removidas).
        # Como SUB-estagio, herda o gate do estagio pai: ``--no-dedup``
        # desliga TODA remocao (semantica preservada); ``--no-mirror-dedup``
        # desliga apenas este sub-estagio (reversibilidade da Fase C).
        # As remocoes somam em ``dedup_stats`` (total do relatorio e do
        # JSONL ``type: run`` em ``dedup_removed``) — o relatorio imprime
        # UMA vez, apos ambos os sub-estagios.
        selected, mirror_stats, _ = deduplicate_mirrors_de_en(selected)
        if mirror_stats:
            dedup_stats[KEY_MIRRORS_DE_EN] = (
                dedup_stats.get(KEY_MIRRORS_DE_EN, 0) + mirror_stats[KEY_MIRRORS_DE_EN]
            )
    if dedup:
        print_dedup_report(dedup_stats)
    if hydrate:
        # Fase A: hidratacao seletiva das descriptions AUSENTES, pos-dedup e
        # pre-ranking. Best-effort: qualquer falha por vaga e registrada e o
        # pipeline segue (exit codes inalterados). O try externo cobre uma
        # falha estrutural da hidratacao inteira (ex.: import/bug) — nesse
        # caso o pipeline atual segue com as descriptions que existem.
        try:
            selected, hydration_stats = hydrate_descriptions(selected)
            print_hydration_report(hydration_stats)
        except Exception as exc:  # noqa: BLE001 - hidratacao nunca e fatal
            log.warning("hidratacao de descriptions falhou (%s); pipeline segue", exc)
            hydration_stats = None
    else:
        hydration_stats = None
    if official_page:
        # Fase D: enriquecimento deterministico pela pagina oficial (JSON-LD
        # JobPosting) — APOS a hidratacao (teasers phenom seguem candidatos)
        # e ANTES do ranking (description melhorada e vista pelo score).
        # Mesma disciplina best-effort da Fase A: falha por vaga e contada,
        # try externo cobre falha estrutural, exit codes inalterados.
        try:
            selected, official_page_stats = enrich_official_pages(
                selected,
                limit=official_page_limit,
                transport=official_page_transport,
            )
            print_official_page_report(official_page_stats)
        except Exception as exc:  # noqa: BLE001 - enrichment nunca e fatal
            log.warning("official-page enrichment falhou (%s); pipeline segue", exc)
            official_page_stats = None
    else:
        official_page_stats = None
    if rank:
        selected = rank_jobs(selected)
    # F5 — sinal visa_friendly (empresa): apos o ranking (aditivo; nunca
    # altera score/ordem), antes de gravar JSON/CSV. Best-effort.
    visa_friendly_count = _apply_visa_friendly(selected)
    if visa_friendly_count:
        print(
            f"=== visa_friendly: {visa_friendly_count} vagas de empresas com "
            "política/programa de visto (visa_policy ∈ {explicit_support, unclear}) ==="
        )
    print(f"\n=== {len(selected)} vagas eligible{', ranqueadas por perfil' if rank else ''} ===")
    if rank:
        print_ranking(selected)
    else:
        print_examples(selected)
    save_outputs(selected, output)

    if metrics is not None:
        records = [
            {
                "type": "run",
                "run_id": run_id or utcnow_iso(),
                "timestamp": utcnow_iso(),
                "total_collected": len(jobs),
                "filtered": counts["pais"],
                "dedup_removed": sum(dedup_stats.values()) if dedup else 0,
                "eligible": len(selected),
            }
        ]
        if hydration_stats is not None:
            records.append(
                {
                    "type": "hydration",
                    "run_id": run_id or utcnow_iso(),
                    "timestamp": utcnow_iso(),
                    **hydration_stats,
                }
            )
        if official_page_stats is not None:
            records.append(
                {
                    "type": "official_page",
                    "run_id": run_id or utcnow_iso(),
                    "timestamp": utcnow_iso(),
                    **official_page_stats,
                }
            )
        write_metrics(metrics, records)
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


def _unit_identity(job: Job | dict) -> tuple[str | None, str | None]:
    """Identidade (company, source) de um job para o lifecycle (P1.2).

    Aceita ``Job`` (producao, retorno de ``collect_company``) ou dict (mocks
    legados de teste). Devolve ``(None, None)`` quando a identidade nao pode
    ser derivada — o CLI entao nao cria unidade (conservador: nao arquiva).
    """
    if isinstance(job, Job):
        return job.company, job.source
    company = job.get("company") if isinstance(job, dict) else None
    source = job.get("source") if isinstance(job, dict) else None
    return company or None, source or None


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


def _dataset_record(run_id: str, summary: dict) -> dict:
    """Registro de metricas do estagio dataset (linha ``type: dataset``).

    Campos (spec F3 §4.1 item 5): run_id/timestamp/type=dataset/
    source=sf_dataset/status/rows por fatia (``per_ats`` com rows+kept)/
    total_prefiltered/bytes/duration — mais as contagens de
    invalid_rows/skipped_budget/failed_slices e jobs criados. O registro e
    gravado mesmo quando o estagio falha (``status: failed``): a falha do
    dataset e DADO (o run segue com so os jobs do registry; o exit code nao
    muda — invariante F3 §4.1 item 6).
    """
    return {
        "type": "dataset",
        "run_id": run_id,
        "timestamp": utcnow_iso(),
        "source": "sf_dataset",
        "status": summary.get("status"),
        "rows_total": summary.get("rows_total", 0),
        "total_prefiltered": summary.get("rows_prefiltered", 0),
        "invalid_rows": summary.get("invalid_rows", 0),
        "jobs": summary.get("jobs", 0),
        "per_ats": summary.get("per_ats", {}),
        "skipped_budget": summary.get("skipped_budget", 0),
        "failed_slices": summary.get("failed_slices", 0),
        "bytes_downloaded": summary.get("bytes_downloaded", 0),
        "duration": summary.get("duration"),
        "error": summary.get("error"),
    }


def _country_isos_for_stages(spec_result: frozenset[str] | str | None) -> tuple[str, ...]:
    """F7: ISOs-alvo derivados do ``--country`` do CLI (fonte unica).

    O ``--country`` e a UNICA fonte de verdade do escopo de pais do run:
    os estagios de coleta (prefilter do dataset, locationCodes do EURES)
    seguem o MESMO escopo do filtro final. ``frozenset`` -> ISOs na ordem
    canonica de TARGET_COUNTRIES primeiro (DE primeiro); ``"remote"`` ->
    escopo de coleta default DE (o filtro remoto e pos-coleta, o dataset
    nao tem faceta de remote no prefilter — documentado); ``None`` (all) ->
    todos os ISOs validos.
    """
    from internship_finder import countries as countries_mod

    if spec_result is None:  # --country all: coleta tudo (corte e do filtro)
        return tuple(sorted(countries_mod.COUNTRY_CODES))
    if isinstance(spec_result, str):  # "remote": coleta default DE
        return ("de",)
    ordered = [c for c in countries_mod.TARGET_COUNTRIES
               if c in spec_result]
    ordered += sorted(c for c in spec_result if c not in ordered)
    return tuple(ordered) if ordered else ("de",)


def _run_dataset_stage(
    run_id: str,
    budget_secs: float,
    country_isos: Any = ("de",),
) -> tuple[list[Job], dict | None]:
    """Estagio dataset (F3): best-effort TOTAL — nunca levanta para o run.

    Devolve ``(jobs, registro)``; em falha estrutural (manifest/rede), os
    jobs sao vazios e o registro carrega ``status: failed`` para o JSONL —
    o CLI loga e segue so com os jobs do registry (exit code inalterado).
    """
    try:
        jobs, summary = collect_dataset_jobs(
            budget_seconds=budget_secs, country_isos=country_isos
        )
    except Exception as exc:  # noqa: BLE001 - dataset nunca derruba o run
        log.error("estagio dataset falhou (%s); run segue com registry only", exc)
        return [], _dataset_record(run_id, {
            "status": "failed", "error": f"{type(exc).__name__}: {exc}",
            "rows_total": 0, "rows_prefiltered": 0, "invalid_rows": 0,
            "jobs": 0, "per_ats": {}, "skipped_budget": 0,
            "failed_slices": 0, "bytes_downloaded": 0, "duration": 0.0,
        })
    record = _dataset_record(run_id, summary)
    if summary.get("status") == "failed":
        log.error("estagio dataset terminou failed (ver registro dataset no JSONL)")
    else:
        log.info(
            "estagio dataset: %d jobs (%d rows prefilteradas de %d; %d bytes; "
            "%.1fs)", summary.get("jobs", 0), summary.get("rows_prefiltered", 0),
            summary.get("rows_total", 0), summary.get("bytes_downloaded", 0),
            summary.get("duration") or 0.0,
        )
    return jobs, record


def _direct_fetch_record(run_id: str, summary: dict) -> dict:
    """Registro de metricas do estagio direct_fetch (linha ``type: direct_fetch``).

    Um registro por run com o status GERAL (ok/partial/failed — cada fonte
    tem seu proprio sub-status em ``ba``/``eures``) e as contagens por fonte
    (rows vistas, jobs criados, paginas, details ok/falha, cap truncado).
    Gravado MESMO em falha (degradacao graciosa e DADO: o run segue; exit
    code NAO muda — mesma regra do estagio dataset da F3).
    """
    return {
        "type": "direct_fetch",
        "run_id": run_id,
        "timestamp": utcnow_iso(),
        "source": summary.get("source", "direct_fetch"),
        "status": summary.get("status"),
        "jobs": summary.get("jobs", 0),
        "ba": summary.get("ba", {}),
        "eures": summary.get("eures", {}),
        "duration": summary.get("duration"),
        "skipped_budget": summary.get("skipped_budget", False),
    }


def _run_direct_fetch_stage(
    run_id: str,
    budget_secs: float,
    max_jobs: int | None,
    eures_location_codes: Any = None,
) -> tuple[list[Job], dict | None]:
    """Estagio direct_fetch (F4): best-effort TOTAL — nunca levanta o run.

    Falha de UMA fonte = ``status: partial`` (a outra segue); falha de
    AMBAS = ``status: failed`` — em qualquer caso o run continua com os
    jobs do registry + dataset e o exit code NAO muda.
    """
    try:
        jobs, summary = collect_direct_fetch(
            budget_seconds=budget_secs, max_jobs=max_jobs,
            eures_location_codes=eures_location_codes,
        )
    except Exception as exc:  # noqa: BLE001 - direct_fetch nunca derruba o run
        log.error("estagio direct_fetch falhou (%s); run segue sem fetch direto", exc)
        return [], _direct_fetch_record(run_id, {
            "source": "direct_fetch", "status": "failed", "jobs": 0,
            "ba": {"source": "direct:bundesagentur", "status": "failed",
                   "jobs": 0, "rows_seen": 0, "pages": 0,
                   "error": f"{type(exc).__name__}: {exc}"},
            "eures": {"source": "direct:eures", "status": "failed",
                      "jobs": 0, "rows_seen": 0, "pages": 0},
            "duration": 0.0, "skipped_budget": False,
        })
    record = _direct_fetch_record(run_id, summary)
    status = summary.get("status")
    if status in ("failed", "partial"):
        log.warning("estagio direct_fetch terminou %s (ver registro direct_fetch no JSONL)", status)
    else:
        log.info(
            "estagio direct_fetch: %d jobs (ba %d, eures %d; %.1fs)",
            summary.get("jobs", 0),
            (summary.get("ba") or {}).get("jobs", 0),
            (summary.get("eures") or {}).get("jobs", 0),
            summary.get("duration") or 0.0,
        )
    return jobs, record


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
        "--hydrate-descriptions",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Hidrata description AUSENTE das vagas ELEGIVEIS via detail-fetch do "
        "ats-scrapers (pos-dedup, pre-ranking, best-effort; default: ligado; "
        "--no-hydrate-descriptions desliga). Diferente de --include-descriptions, "
        "que busca descricao por vaga durante a COLETA inteira (bulk, mais lento).",
    )
    parser.add_argument(
        "--official-page",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enriquecimento pela pagina oficial (Fase D): UM GET por vaga "
        "candidata (description ausente/teaser OU sem deadline OU sem salary), "
        "extrai JSON-LD JobPosting como evidencia estruturada em "
        "job['official_page'] (pos-hidratacao, pre-ranking, best-effort; "
        "default: DESLIGADO desde F1 01/10 — cookie-wall/JS-render torna o "
        "estagio sem retorno; --official-page liga sob demanda). Sem LLM/browser.",
    )
    parser.add_argument(
        "--official-page-limit",
        type=int,
        default=None,
        help="Limite de vagas por execucao do official-page enrichment "
        "(default: 150, cortado por prioridade: sem description > teaser > "
        "sem deadline > sem salary; 0 = sem limite). Primeiro run controlado "
        "da fase (spec): custo medido ~1.4s/GET.",
    )
    parser.add_argument(
        "--dataset",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="F3: coleta TAMBEM do dataset hospedado do ats-scrapers "
        "(manifest publico, prefilter DE+estagio em streaming; ~21,6k rows "
        "de 63 fatias) e concatena com os jobs do registry no MESMO funil "
        "filtros->dedup->ranking. Default: LIGADO no modo --registry "
        "(inversao arquitetural: dataset e fonte primaria, registry e lista "
        "de interesse no ranking), DESLIGADO no --companies explícito; "
        "--no-dataset reverte ao comportamento anterior. Falha do dataset "
        "NUNCA derruba o run (best-effort: log + registro dataset com "
        "status failed; exit code segue o da coleta do registry).",
    )
    parser.add_argument(
        "--dataset-budget-secs",
        type=float,
        default=DATASET_BUDGET_SECONDS,
        help=f"Teto total do estagio dataset em segundos, checado ENTRE "
        f"fatias (default {DATASET_BUDGET_SECONDS:.0f}); estourado, as "
        f"fatias restantes viram skipped_budget e o run segue.",
    )
    parser.add_argument(
        "--direct-fetch",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="F4: coleta TAMBEM uma amostra diaria DIRETA das APIs publicas "
        "BA (angebotsart=34 PRAKTIKUM_TRAINEE) e EURES (keywords "
        "Praktikum, EVERYWHERE) com filtro de estagio nativo, cap de "
        "jobs por fonte e paginacao sequencial (rate limit "
        "conservador). Default: LIGADO no modo --registry, DESLIGADO "
        "no --companies explicito; --no-direct-fetch desliga. Falha de "
        "fonte NUNCA derruba o run (degradacao graciosa: registro "
        "type: direct_fetch com status failed/partial).",
    )
    parser.add_argument(
        "--direct-fetch-max-jobs",
        type=int,
        default=None,
        metavar="N",
        help="Limite de jobs POR FONTE (BA, EURES) por run do estagio "
        "direct_fetch (default 200). O cap e a medida principal de rate "
        "limit: 1 fetch/dia por fonte, paginacao sequencial, timeout "
        "curto por request.",
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
        "--mirror-dedup",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Sub-estagio de dedup (Fase C): remove mirrors DE/EN — mesma vaga "
        "publicada nos dois idiomas no mesmo tenant com o mesmo "
        "requisition_id (chave: req_id + marcador de tipo DE/EN do titulo + "
        "guardrails de country/employment_type). Default: ligado; "
        "--no-mirror-dedup desliga (reversivel). Sub-estagio do --dedup: "
        "--no-dedup desliga toda remocao.",
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
        registry = CompanyRegistry()
        report["companies"] = registry.company_status(health_path)
        # P2: consistencia Registry x runtime — tenant declarado no registry x
        # tenants efetivamente resolvidos no run mais recente do JSONL, por
        # empresa (configuracao x resultado real). Divergencia (declarado X,
        # runtime so Y) aparece como status "drift"; None declarado e resolucao
        # dinamica valida ("dynamic"); sem dados -> "no_data". Reusa o fluxo de
        # health (mesmos records) — sem sistema paralelo.
        report["registry_consistency"] = tenant_consistency_report(
            registry.entries, latest_run_tenants(records)
        )
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

    # F7: ISOs-alvo dos ESTAGIOS de coleta derivados do --country (mesma
    # fonte de verdade do filtro final). Ex.: "de,lu,nl,fi,be" -> prefilter
    # do dataset e locationCodes do EURES nos 5 paises; "de" -> comportamento
    # identico a F3/F4 (retrocompat).
    stage_country_isos = _country_isos_for_stages(
        parse_country_spec(args.country)
    )

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
        # F3: default do estagio dataset — LIGADO no modo --registry (a
        # inversao arquitetural e o pedido; o refresh de producao roda
        # --registry), DESLIGADO no --companies explícito (uso pontual
        # continua com o comportamento anterior). --no-dataset reverte.
        dataset_enabled = (
            args.dataset if args.dataset is not None else bool(args.registry)
        )
        # Registro do estagio dataset (gravado no JSONL junto com os
        # tenant records, antes do run record) — None quando desligado.
        dataset_record: dict | None = None
        dataset_jobs: list[Job] = []
        # F4: mesmo default do dataset — LIGADO no --registry (amostra
        # fresca diaria das 2 maiores fontes de estagio da Europa, com
        # filtro nativo), DESLIGADO no --companies explícito.
        direct_fetch_enabled = (
            args.direct_fetch if args.direct_fetch is not None else bool(args.registry)
        )
        direct_fetch_record: dict | None = None
        direct_fetch_jobs: list[Job] = []
        # Unidades de coleta confiavel (P1.2): (company, source, jobs) de
        # tenants que terminaram em OK/EMPTY. Tenants que falharam
        # (timeout/error/not_found/skipped) NAO entram — a ausencia deles no
        # run nunca arquiva as vagas da unidade (ausencia observada !=
        # ausencia por falha de coleta). Preenchida no loop e consumida pelo
        # bloco --sqlite.
        collection_units: list[tuple[str, str, list[Job]]] = []
        for name in names:
            jobs, summary = collect_company(
                name,
                timeout=args.timeout,
                include_descriptions=args.include_descriptions,
                limit=args.limit,
            )
            summaries.append((name, summary))
            all_jobs.extend(jobs)
            # Identifica as unidades bem-sucedidas desta empresa. A company
            # efetiva vem dos jobs (para OK) ou do mapeamento do summary (para
            # EMPTY); o escopo (company, source) e a identidade P1.1 do Job.
            companies = summary.get("companies", {})
            ok_sources = {src for src, *_ in summary["ok"]}
            empty_sources = {src for src, *_ in summary.get("empty", [])}
            by_unit: dict[tuple[str, str], list[Job]] = {}
            for j in jobs:
                company_id, source = _unit_identity(j)
                if company_id and source:
                    by_unit.setdefault((company_id, source), []).append(j)
            for (company_id, source), unit_jobs in by_unit.items():
                if source in ok_sources:
                    collection_units.append((company_id, source, unit_jobs))
            # EMPTY: coleta valida com 0 vagas -> arquiva a unidade inteira.
            for source in empty_sources:
                collection_units.append(
                    (companies.get(source) or name, source, [])
                )
            print(f"Found {len(jobs)} jobs for {name}")
            for j in jobs[:15]:
                print(f"  - {j}")
            if len(jobs) > 15:
                print(f"  ... +{len(jobs) - 15} vagas (lista completa no JSON/CSV)")

        total = len(all_jobs)
        # F3: estagio dataset APOS a coleta do registry (mesma ordem da
        # concatenacao). Best-effort: falha nao derruba o run nem muda exit
        # codes — vira registro ``type: dataset`` com status failed e o run
        # segue so com os jobs do registry.
        if dataset_enabled:
            dataset_jobs, dataset_record = _run_dataset_stage(
                run_id, args.dataset_budget_secs,
                country_isos=stage_country_isos,
            )
            all_jobs = all_jobs + dataset_jobs
            total = len(all_jobs)
            rec = dataset_record or {}
            if dataset_jobs:
                print(
                    f"\n=== DATASET sf_dataset: +{len(dataset_jobs)} jobs "
                    f"({rec.get('total_prefiltered')} rows "
                    f"prefilteradas, {rec.get('bytes_downloaded')} "
                    f"bytes, {rec.get('duration')}s) ==="
                )
        # F4: estagio direct_fetch APOS o dataset (mesma concatenacao).
        # Best-effort: falha de fonte nunca derruba o run nem muda exit
        # codes — vira registro ``type: direct_fetch`` com status
        # failed/partial e o run segue com o que houver.
        if direct_fetch_enabled:
            direct_fetch_jobs, direct_fetch_record = _run_direct_fetch_stage(
                run_id,
                DIRECT_FETCH_BUDGET_SECONDS,
                args.direct_fetch_max_jobs,
                eures_location_codes=stage_country_isos,
            )
            all_jobs = all_jobs + direct_fetch_jobs
            total = len(all_jobs)
            if direct_fetch_jobs:
                rec = direct_fetch_record or {}
                print(
                    f"\n=== DIRECT FETCH F4: +{len(direct_fetch_jobs)} jobs "
                    f"(ba {rec.get('ba', {}).get('jobs', 0)}, "
                    f"eures {rec.get('eures', {}).get('jobs', 0)}, "
                    f"{rec.get('duration')}s) ==="
                )
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
            records = list(tenant_records)
            if dataset_record is not None:
                records.append(dataset_record)
            if direct_fetch_record is not None:
                records.append(direct_fetch_record)
            write_metrics(metrics_path, records)
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
        # P1.2: o lifecycle e atualizado POR UNIDADE de coleta confiavel
        # (company, source). Unidades com timeout/erro/not_found nao entram em
        # ``collection_units`` e, portanto, nao tem nenhuma vaga arquivada —
        # ausencia observada != ausencia causada por falha de coleta.
        if args.sqlite:
            sqlite_path = Path(args.sqlite)
            try:
                sqlite_path.parent.mkdir(parents=True, exist_ok=True)
                with SqliteStore(sqlite_path) as store:
                    stats = store.run_units(collection_units)
                print(
                    f"\n=== SQLite {sqlite_path}: {len(all_jobs)} vagas no run "
                    f"({stats['inserted']} novas, {stats['reactivated']} "
                    f"reativadas) ==="
                )
            except Exception as exc:  # noqa: BLE001 - a coleta nunca cai por sqlite
                log.error("sqlite falhou e foi ignorado (%s): %s", sqlite_path, exc)
        # Tenant records primeiro; o run record (resumo) e escrito dentro do
        # ``run_filter_pipeline``, ao final do processamento. O registro do
        # estagio dataset (F3) e gravado AQUI (mesma posicao dos tenant
        # records): a ordem no JSONL e tenant -> dataset -> run.
        records = list(tenant_records)
        if dataset_record is not None:
            records.append(dataset_record)
        if direct_fetch_record is not None:
            records.append(direct_fetch_record)
        write_metrics(metrics_path, records)
        pipeline_rc = run_filter_pipeline(
            all_jobs,
            student=args.student,
            area=args.area,
            country=args.country,
            output=Path(args.filter_output),
            dedup=args.dedup,
            mirror_dedup=args.mirror_dedup,
            rank=args.rank,
            hydrate=args.hydrate_descriptions,
            official_page=args.official_page,
            official_page_limit=(
                args.official_page_limit
                if args.official_page_limit is not None
                else OFFICIAL_PAGE_LIMIT
            ),
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
        mirror_dedup=args.mirror_dedup,
        rank=args.rank,
        hydrate=args.hydrate_descriptions,
        official_page=args.official_page,
        official_page_limit=(
            args.official_page_limit
            if args.official_page_limit is not None
            else OFFICIAL_PAGE_LIMIT
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
