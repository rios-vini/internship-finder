"""Coleta orientada a empresas: find_company (match exato) -> scraper -> Job.

O ``fetch`` de cada scraper roda em um subprocesso com teto de tempo
(``timeout`` + margem): um tenant que trava ou erra e registrado e nao
derruba o resto do pipeline. O contexto de multiprocessing e o default do
SO (fork no Linux, spawn no Windows).
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import time
from queue import Empty as _Empty

from internship_finder.adapters.ats import AtsJobAdapter
from internship_finder.collectors.company import CompanyCollector
from internship_finder.collectors.phenom_tenants import build_phenom_company, get_phenom_tenant
from internship_finder.collectors.us_centric_tenants import build_us_centric_company, get_us_centric_tenant
from internship_finder.errors import (
    FETCH_STAGE,
    NORMALIZE_STAGE,
    TIMEOUT,
    UNKNOWN,
    CollectionError,
    classify_exception,
)
from internship_finder.geocoding import flush_cache
from internship_finder.models.company import Company
from internship_finder.models.job import Job
from internship_finder.upstream_patches.bamboohr import get_patched_scraper
from internship_finder.collectors.personio_tenants import (  # noqa: E402
    build_personio_company,
    get_personio_tenant,
)

log = logging.getLogger(__name__)

# Scrapers cujo "slug" e na verdade a URL completa de careers (o slug da
# base, ex.: "jobs" p/ SAP/ZF no successfactors, nao e usavel sozinho).
URL_SLUG_ATS = {"successfactors", "workday", "taleo", "icims", "phenom", "avature", "oracle"}

# Override da URL de careers por EMPRESA (Fase I — SAP source recovery).
#
# Contexto: o site publico de carreiras da SAP foi reconstruido (Next.js) e
# o host historico ``jobs.sap.com`` deixou de expor o feed RSS legacy em
# ``/sitemal.xml`` (404 desde 22/09/2026 -> FETCH_ERROR diário no cron). O
# portal RMK legacy continua VIVO em ``careers.sap.com`` com o MESMO feed
# (mesmo schema g:*, mesmo formato de id, descriptions completas; 913 itens
# em 29/09). A URL stale vem do inventario de companies hospedado upstream
# (ats-companies/successfactors.csv), nao do scraper: o SuccessFactors 0.3.0
# coleta o feed novo sem nenhuma alteracao.
#
# Este mapa e a MENOR mudanca arquiteturalmente correta: corrige o HOST do
# feed no ponto exato onde a URL entra no fluxo (``scraper_slug``), por
# empresa — nunca por tenant (``successfactors:jobs`` e compartilhado por 16
# empresas no registry; um override de tenant redirecionaria ZF/Kaufland/
# Schaeffler/... para o site da SAP). Chave: (ats, slug) + nome EXATO da
# empresa resolvida (``Company.name`` da base), o mesmo criterio de
# identidade da coleta. ``Company.source`` (ats:slug), ``Job.id``
# (<company>|<source>:<external_id>) e todo o restante do pipeline seguem
# IDENTICOS — so o host do feed muda.
#
# Remocao: quando o upstream atualizar a URL no manifest/CSV de companies,
# remover a entrada (e o teste correspondente) — o mapa e auto-contido e a
# ausencia de override restaura o comportamento puro do inventario.
TENANT_URL_OVERRIDES: dict[tuple[str, str, str], str] = {
    # SAP: jobs.sap.com (board Next.js novo, sem feed) -> careers.sap.com
    # (RMK legacy, feed sitemal.xml vivo e completo). Verificada em
    # 29/09/2026: 913 itens, identidade/overlap historico 825/913.
    ("successfactors", "jobs", "SAP"): "https://careers.sap.com",
    # Lidl: OVERRIDE REMOVIDO (F132, 26/10/2026).
    # O feed legacy career5.successfactors.eu?company=lidlstiftuP2 migrou de conteúdo
    # e agora serve o board US do Lidl (88 vagas US, zero DE).
    # O feed original jobs.lidl/sitemal.xml está vivo (108 MB, ~46s download,
    # ~98s total com parsing) e retorna 21.776 vagas (15.397 DE).
    # Requer timeout dedicado de 100s (ver TENANT_TIMEOUT_OVERRIDES).
    # Removido para restaurar o fluxo padrão do inventário (jobs.lidl/sitemal.xml).
}


def scraper_slug(company: Company) -> str:
    """Slug efetivo a passar ao construtor do scraper."""
    override = TENANT_URL_OVERRIDES.get(
        (company.ats, company.slug, (company.name or "").strip())
    )
    if override:
        return override
    if company.ats in URL_SLUG_ATS and company.url:
        return company.url
    return company.slug


# F58 (18/10/2026): override de MIGRACAO de ATS por empresa. O inventario
# upstream (ats-companies, manifest atualizado ~14:30 UTC) e a fonte canonica
# de tenants, mas nao acompanha migracoes de plataforma em tempo real:
# enquanto a linha antiga nao sai do manifest, a coleta pelo nome resolve o
# tenant MORTO, o scraper antigo segue o redirect para o site novo, parseia
# 0 vagas e o health ve ``empty`` — quebra SILENCIOSA (F49 secao 2.5: 19+
# runs "empty" com a empresa viva e contratando). Este mapa reescreve o
# tenant RESOLVIDO para a plataforma nova no ponto exato onde a resolucao
# entra no fluxo (``collect_company``, logo apos ``find_company``), pela
# MESMA chave de identidade do ``TENANT_URL_OVERRIDES`` (Fase I): (ats,
# slug) + nome EXATO da empresa resolvida (``Company.name`` da base). O
# valor e o (ats, slug) novos — para ATS de URL-como-slug (URL_SLUG_ATS) o
# slug e a URL completa de careers, usada direto pelo scraper e pelo
# ``Company.source`` (``ats:slug``). ``Company.url`` e setado junto: o
# ``scraper_slug`` e a hidratacao leem a URL de la.
#
# Remocao: quando o upstream atualizar a linha no manifest/CSV (a linha
# avature sair e/ou a phenom entrar), remover a entrada (e o teste
# correspondente) — o mapa e auto-contido e a ausencia de override restaura
# o comportamento puro do inventario. Ate la, o registry declara o tenant
# NOVO como referencia (consistencia registry x runtime verde) e a coleta
# usa este override.
TENANT_ATS_OVERRIDES: dict[tuple[str, str, str], tuple[str, str]] = {
    # Siemens Healthineers: Avature -> Phenom (~fim 09/2026). Probe F49
    # 18/10: jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs
    # responde 302 -> careers.siemens-healthineers.com/global/en
    # (plataforma Phenom: cdn.phenompeople.com, csrfToken + POST /widgets).
    # Validado AO VIVO 18/10 (F58) com o caminho EXATO do pipeline
    # (PhenomScraper, defaults locale en_us/country us): 823 vagas em ~3s
    # (111 na Alemanha; 39 student-pattern+DE — Werkstudent Erlangen/
    # Forchheim/Rudolstadt). Manifest upstream verificado ao vivo 18/10:
    # find_company("Siemens Healthineers") ainda resolve SO a linha avature.
    (
        "avature",
        "https://jobs.siemens-healthineers.com/en_US/searchjobs/SearchJobs",
        "Siemens Healthineers",
    ): ("phenom", "https://careers.siemens-healthineers.com"),
    # AkzoNobel: SuccessFactors -> Phenom (~29/09/2026). Achado F72
    # (auditoria viva 20/10): careers.akzonobel.com/sitemal.xml responde
    # HTTP 500 PERSISTENTE (RetryExhausted apos 3 tentativas; 500
    # re-medido a ~1h10 de distancia e por GET direto — CloudFront,
    # 23 bytes) com o portal VIVO: raiz 303 -> /gb/en HTTP 200 com
    # assinatura Phenom (data-ph-id). Serie do JSONL de metricas: 28 runs
    # ok (~270 vagas/dia, 08-28/09) -> 22 runs FETCH_ERROR collected=0
    # (29/09-20/10) — coleta cega com a empresa viva, mesmo padrao F58.
    # Validado AO VIVO 20/10 com o caminho EXATO do pipeline
    # (PhenomScraper, defaults locale en_us/country us): 225 vagas em ~2s;
    # 5 student-pattern no board global (1 DE: "Praktikum /
    # Studententatigkeit", Koln DEU, jobId 28874); identidade
    # company == careers.akzonobel.com (P1.1). Manifest upstream
    # verificado ao vivo 20/10: find_company("AkzoNobel") ainda resolve SO
    # a linha successfactors com slug "careers" + url
    # careers.akzonobel.com (o DESAMBIGUADOR e a URL; o slug "careers" e
    # COMPARTILHADO com Swiss Re — o nome EXATO na chave do override e o
    # que protege o outro tenant do mesmo slug) — remover este override
    # quando o upstream atualizar a linha. Evidencias e serie completa:
    # relatorio F72 (~/.hermes/handoff/f72-auditoria-127/).
    (
        "successfactors",
        "careers",
        "AkzoNobel",
    ): ("phenom", "https://careers.akzonobel.com"),
}


# F116 (24/10/2026): exclusão de tenants CRÔNICOS mortos/homônimos que o
# manifest upstream insiste em resolver, gerando FETCH_ERROR recorrente a
# cada run (39/38 runs desde ~10/09). Estas empresas JÁ TÊM tenants de
# referência VIVOS no registry (phenom:nan p/ Kuehne+Nagel; successfactors:sma
# p/ SMA) — a exclusão é cirúrgica no tenant problemático, NÃO na empresa.
# Chave: (ats, slug, company_name) — mesma identidade do TENANT_ATS_OVERRIDES.
# Remoção: quando o upstream remover a linha morta do manifest, remover a
# entrada daqui — o mapa é auto-contido e a ausência restaura o comportamento
# puro do inventário.
TENANT_EXCLUDES: set[tuple[str, str, str]] = {
    # Kuehne+Nagel: cornerstone:kuehne-nagel (kuehne-nagel.csod.com NXDOMAIN
    # desde ~10/09; careersite extinto, K+N migrou p/ phenom jobs.kuehne-nagel.com).
    # Registry já declara phenom:nan como referência (1.064–1.115 vagas/dia,
    # 32/32 runs ok — medição F49 §2.1, 17/10/2026).
    ("cornerstone", "kuehne-nagel", "Kuehne+Nagel"),
    # SMA: oracle:fa-exow-saasfaprod1/cx_1 (fa-exow-saasfaprod1.oraclecloud.com
    # NXDOMAIN; homônimo confirmado 17/09 = academia marítima em Sharjah/UAE,
    # 7 vagas faculty Marine Engineering/Maritime Business. Oracle scraper
    # exige URL completa (oracle ∉ URL_SLUG_ATS) → FETCH_ERROR crônico).
    # Registry já declara successfactors:sma como referência (sma.jobs vivo).
    ("oracle", "fa-exow-saasfaprod1/cx_1", "SMA"),
}


def resolve_tenant_migration(company: Company) -> Company:
    """Reescreve o tenant de uma empresa cujo ATS migrou (F58).

    A reescrita acontece ANTES de qualquer consumo (``has_scraper`` /
    ``scraper_slug`` / adaptador / metricas): todo o downstream ve o tenant
    novo, com ``source``/``id`` honestos da plataforma real — nada do tenant
    morto permanece no fluxo. Empresas fora do mapa seguem 100% o
    comportamento puro do inventario (a ausencia de entrada e a inercia).
    """
    key = (company.ats, company.slug, (company.name or "").strip())
    override = TENANT_ATS_OVERRIDES.get(key)
    if not override:
        return company
    ats, slug = override
    return company.model_copy(update={"ats": ats, "slug": slug, "url": slug})

# Margem (segundos) somada ao ``timeout`` do scraper antes de declarar o
# subprocesso travado (ACH-07). Parametrizavel via ``fetch_with_timeout(...,
# margin=...)`` — os testes usam uma margem pequena para timeout rapido sem
# alterar o comportamento de producao (default 25).
TIMEOUT_MARGIN = 25.0

# F132 (26/10/2026): override de TIMEOUT por tenant.
# Alguns feeds (ex.: Lidl sitemal.xml = 108 MB) precisam de mais tempo que
# o teto global do cron (60s + 25s margem = 85s). Este mapa permite um
# timeout dedicado por tenant (mesma chave de identidade: (ats, slug, name)).
# O valor substitui o ``timeout`` passado ao ``fetch_with_timeout`` ANTES de
# somar a margem. Remocao: quando o feed emagrecer ou o teto global subir,
# remover a entrada — a ausencia restaura o comportamento global.
TENANT_TIMEOUT_OVERRIDES: dict[tuple[str, str, str], float] = {
    # Lidl: jobs.lidl/sitemal.xml = 108 MB, ~46s download + ~52s parsing = ~98s total.
    # O timeout global de 60s (85s com margem) nao basta. 100s = 125s com margem.
    # Medido AO VIVO 26/10/2026: 21.776 vagas (15.397 DE) em 97.4s.
    ("successfactors", "lidlstiftuP2", "LIDL"): 100.0,
}

# Tempo (segundos) de cada estagio do encerramento forçado: ``terminate()``
# (SIGTERM) tem uma janela de grace para chamar a cleanup normal; se o
# processo ignorar/sobreviver, ``kill()`` (SIGKILL) e o fallback final.
TERMINATE_GRACE = 5.0
KILL_GRACE = 2.0


def fetch_worker(
    company: Company, timeout: float, include_descriptions: bool, queue: mp.Queue
) -> None:
    """Roda o scraper e devolve as vagas normalizadas (dicts) pela queue.

    A normalizacao usa a ``Company`` real (source/slug corretos) e acontece
    uma unica vez — a re-adaptacao apos a queue duplicaria prefixos no ``id``.

    O payload de erro na queue e ESTRUTURADO (sem texto livre): a tupla
    ``("-error", code, detail)``, com ``code``/``detail`` vindos de
    ``classify_exception`` por estagio (fetch vs normalize).
    """
    try:
        try:
            # F59.1: ponto de uso do patch BambooHR auto-removível — o
            # factory decide (auto-detect contra o fixture BCG) entre o
            # pacote puro e o parser vendored; para TODO outro ATS é
            # ``get_scraper`` puro (inércia). Hidratação (get_description,
            # detail API) segue ``get_scraper`` direto — o PR #300 não
            # toca esse caminho.
            scraper = get_patched_scraper(
                company.ats,
                scraper_slug(company),
                timeout=timeout,
                include_descriptions=include_descriptions,
            )
            jobs = scraper.fetch()
        except Exception as exc:  # noqa: BLE001 - falha do estagio de fetch
            code, detail = classify_exception(exc, stage=FETCH_STAGE)
            queue.put(("-error", code, detail))
            return
        try:
            adapter = AtsJobAdapter()
            result = [adapter.to_job(j, company).to_dict() for j in jobs]
            # Persiste o cache de geocoding (resultados/respostas) que este
            # subprocesso possa ter gravado durante a adaptacao. O cache e
            # file-based, entao o write propaga para os demais processos.
            flush_cache()
        except Exception as exc:  # noqa: BLE001 - falha do estagio de adaptacao
            code, detail = classify_exception(exc, stage=NORMALIZE_STAGE)
            queue.put(("-error", code, detail))
            return
        queue.put(("ok", result))
    except Exception as exc:  # noqa: BLE001 - nem a classificacao pode derrubar
        queue.put(("-error", UNKNOWN, f"{type(exc).__name__}: {exc}"))


def _shutdown(proc: mp.Process, queue: mp.Queue) -> None:
    """Encerra ``proc`` e a queue de forma completa, em QUALQUER desfecho.

    Fluxo (ACH-07): ``terminate()`` (SIGTERM) -> ``join(grace)`` -> se ainda
    vivo, ``kill()`` (SIGKILL) -> ``join(2)``. A queue e drenada
    (``get_nowait`` ate ``Empty``) e depois fechada com ``close()`` +
    ``join_thread()``, sem deixar item residual nem thread de feeder viva.
    """
    proc.terminate()
    proc.join(timeout=TERMINATE_GRACE)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=KILL_GRACE)
    try:
        while True:
            queue.get_nowait()
    except _Empty:
        pass
    queue.close()
    queue.join_thread()


def _wait_worker(proc: mp.Process, queue: mp.Queue, deadline: float) -> tuple[str, object | None]:
    """Espera o primeiro item da queue, monitorando a morte do worker.

    Retorna ``(outcome, item)``:
      - ``("ok", ("ok", result))``          — item entregue/consumido;
      - ``("ok", ("-error", code, detail))``— item de erro estruturado;
      - ``("timeout", None)``               — queue vazia ate o ``deadline``;
      - ``("dead", None)``                  — worker morreu sem mensagem
        (``exitcode != 0``) detectado ANTES do deadline via ``is_alive``.
    A espera usa ``queue.get(timeout=0.2)`` como poller leve (barato, acorda a
    cada 200ms) e checa o exitcode para nao gastar a margem inteira quando o
    subprocesso ja caiu (os._exit/segfault/kill; o ``except`` nao captura).
    """
    while True:
        if not proc.is_alive():
            exitcode = proc.exitcode
            if exitcode is not None and exitcode != 0 and queue.empty():
                # Morreu sem deixar item na queue -> nao ha o que ler.
                return "dead", None
            # exitcode == 0 (terminou normal) ou ha item residual do feeder:
            # segue e tenta ler; so declara morte quando a queue esta vazia.
        try:
            item = queue.get(timeout=0.2)
            return "ok", item
        except _Empty:
            if time.monotonic() >= deadline:
                return "timeout", None


def fetch_with_timeout(
    company: Company,
    timeout: float,
    include_descriptions: bool,
    margin: float = TIMEOUT_MARGIN,
) -> list[dict]:
    """fetch() do scraper com teto de tempo; trava/erro nao derruba o fluxo.

    O ciclo de vida do subprocesso (ACH-07) distingue 4 desfechos de forma
    observavel (mensagens claras no ``detail``/log), SEM adicionar status:

    - **timeout** — a queue ficou vazia ate o ``deadline`` (``timeout`` +
      margem): ``CollectionError(TIMEOUT, ...)``.
    - **worker morto** — o subprocesso morreu sem mandar mensagem
      (``os._exit``/segfault/kill; o ``except`` do worker nao captura): detectado
      VIA ``exitcode``/``is_alive`` ANTES do deadline e reportado como
      ``CollectionError(UNKNOWN, \"worker morreu (exitcode N) sem mensagem\")`` —
      distinto de timeout, sem gastar a margem inteira.
    - **erro do worker** — payload estruturado ``("-error", code, detail)``:
      ``CollectionError(code, detail)`` do P1 #7.
    - **sucesso** — ``("ok", result)``: payload devolvido.

    Em TODOS os caminhos o processo e encerrado (terminate -> join -> kill ->
    join) e a queue drenada/fechada — sem orfaos.

    ``margin`` (opcional) parametriza a margem de timeout; default ``25``
    (``TIMEOUT_MARGIN``), inalterado em producao.
    """
    ctx = mp.get_context()
    queue = ctx.Queue()
    proc = ctx.Process(
        target=fetch_worker,
        args=(company, timeout, include_descriptions, queue),
    )
    proc.start()
    tag = f"{company.ats}/{company.slug}"
    deadline = time.monotonic() + timeout + margin
    try:
        outcome, item = _wait_worker(proc, queue, deadline)
        if outcome == "dead":
            raise CollectionError(
                UNKNOWN,
                f"worker {tag} morreu (exitcode {proc.exitcode}) sem mensagem",
            ) from None
        if outcome == "timeout":
            raise CollectionError(
                TIMEOUT,
                f"scraper {tag} nao respondeu em {timeout + margin:.0f}s (timeout)",
            ) from None
        status, payload = item[0], item[1]
        if status == "-error":
            code, detail = item[1], item[2]
            raise CollectionError(code, detail) from None
    finally:
        _shutdown(proc, queue)
    return payload


def collect_company(
    name: str,
    timeout: float = 45.0,
    include_descriptions: bool = False,
    limit: int = 0,
) -> tuple[list[Job], dict]:
    """Coleta as vagas de ``name`` (match exato na base do ats-scrapers).

    Retorna ``(jobs, summary)``; ``summary`` distingue o estado de cada
    tenant, para que "0 vagas" (EMPTY) nao seja confundido com erro:
    - ``ok``      [(source, n, tempo)]     — SUCCESS (>=1 vaga coletada)
    - ``empty``   [(source, tempo)]        — EMPTY (tenant respondeu, 0 vagas)
    - ``timeout`` [(source, code, erro)]   — TIMEOUT (nao respondeu no prazo)
    - ``failed``  [(source, code, erro)]   — ERROR (excecao de coleta)
    - ``skipped`` [source]                 — sem scraper registrado
    - ``not_found`` (bool)                 — empresa sem match exato na base

    ``code`` e o codigo estruturado de ``errors`` (ex.: ``TIMEOUT``,
    ``CONNECTION_ERROR``) e ``erro`` o detalhe legivel (``str(exc)``); os dois
    juntos (e nao texto livre sozinho) propagam da queue ate o registro JSONL.

    Erros/timeouts sao registrados e o fluxo segue para as proximas
    empresas/tenants (nenhuma excecao e engolida silenciosamente).
    """
    collector = CompanyCollector()
    companies = collector.find_company(name)
    
    # Check for known Phenom tenants with local config overrides
    phenom_config = get_phenom_tenant(name)
    if phenom_config:
        # Build correct Phenom company with locale/country
        phenom_company = build_phenom_company(phenom_config, name)
        # For Viega: replace any database entries (incorrectly listed as SuccessFactors)
        # For Hugo Boss/Mars: add to the list (database entries work but use defaults)
        if name.casefold() == "viega".casefold():
            # Viega is incorrectly in DB as SuccessFactors; use only Phenom
            companies = [phenom_company]
        else:
            # Hugo Boss, Mars: add Phenom config with correct locale/country
            # The database entries use default locale/country; our config is more accurate
            companies = [phenom_company] + [c for c in companies if c.ats != "phenom"]

    # Check for US-centric tenants (may be missing from database or need explicit config)
    us_config = get_us_centric_tenant(name)
    if us_config:
        us_company = build_us_centric_company(us_config, name)
        # Replace any database entries with our verified config
        # (database may have wrong ATS or missing entries)
        companies = [us_company] + [c for c in companies if c.ats != us_config.ats or c.url != us_config.url]

    # F139: Personio tenants com config local verificada (company canonica —
    # o host (ex.: hairoboticseurope.jobs.personio.com) NUNCA vira company)
    personio_config = get_personio_tenant(name)
    if personio_config:
        personio_company = build_personio_company(personio_config, name)
        companies = [personio_company] + [
            c for c in companies if c.ats != "personio" or c.slug != personio_config.slug
        ]

    summary: dict = {
        "ok": [],
        "empty": [],
        "timeout": [],
        "failed": [],
        "skipped": [],
        "not_found": False,
        # Identidade efetiva da empresa por tenant (P1.2): usado pelo lifecycle
        # do SQLite para escopar o archive em unidades EMPTY (sem jobs para
        # derivar ``job.company``). Para OK, o ``job.company`` dos jobs e a
        # mesma identidade (P1.1: empresa + tenant ATS).
        "companies": {},
    }
    if not companies:
        log.warning("[%s] nao encontrada na base (match exato)", name)
        summary["not_found"] = True
        return [], summary

    jobs: list[Job] = []
    for company in companies:
        # F58: ATS migrado (manifest upstream ainda traz a linha morta) —
        # reescreve o tenant resolvido para a plataforma validada ANTES de
        # qualquer consumo; empresas fora do mapa seguem o inventario puro.
        company = resolve_tenant_migration(company)
        # F116: exclusão cirúrgica de tenants crônicos mortos/homônimos
        # (mesma chave de identidade do TENANT_ATS_OVERRIDES/TENANT_EXCLUDES).
        exclude_key = (company.ats, company.slug, (company.name or "").strip())
        if exclude_key in TENANT_EXCLUDES:
            log.info(
                "[%s] %s excluído por F116 (tenant crônico morto/homônimo — "
                "registry já tem referência viva); pulando coleta",
                name,
                company.source,
            )
            summary["skipped"].append(company.source)
            summary["companies"][company.source] = company.name or company.query
            continue
        if not collector.has_scraper(company):
            log.warning("[%s] %s sem scraper registrado; pulando", name, company.source)
            summary["skipped"].append(company.source)
            summary["companies"][company.source] = company.name or company.query
            continue
        # F132: timeout dedicado por tenant (ex.: Lidl sitemal.xml 108 MB).
        tenant_key = (company.ats, company.slug, (company.name or "").strip())
        effective_timeout = TENANT_TIMEOUT_OVERRIDES.get(tenant_key, timeout)
        if effective_timeout != timeout:
            log.info(
                "[%s] %s: usando timeout dedicado %.0fs (global %.0fs)",
                name,
                company.source,
                effective_timeout,
                timeout,
            )
        t0 = time.time()
        try:
            # Fase A (D4): Softgarden e a excecao explicita — o feed de vagas
            # ja embute a description completa sem custo adicional de
            # requests (a auditoria do ecossistema 0.3.0 mediu isso ao vivo);
            # sem o flag ela e descartada na origem. Todos os demais ATS
            # seguem o flag global (nunca bulk desnecessario).
            tenant_include_descriptions = (
                include_descriptions or company.ats == "softgarden"
            )
            raw_jobs = fetch_with_timeout(company, effective_timeout, tenant_include_descriptions)
            if limit and len(raw_jobs) > limit:
                raw_jobs = raw_jobs[:limit]
            # Os dicts ja saem normalizados (single-pass no subprocesso).
            converted = [Job(**d) for d in raw_jobs]
            dt = time.time() - t0
            if converted:
                jobs.extend(converted)
                summary["ok"].append((company.source, len(converted), f"{dt:.1f}s"))
                # Identidade efetiva da empresa observada nos jobs (P1.1).
                summary["companies"][company.source] = converted[0].company
                log.info("[%s] %s: %d vagas em %.1fs", name, company.source, len(converted), dt)
            else:
                summary["empty"].append((company.source, f"{dt:.1f}s"))
                summary["companies"][company.source] = company.name or company.query
                log.info("[%s] %s: 0 vagas (EMPTY) em %.1fs", name, company.source, dt)
        except CollectionError as exc:
            code = exc.code if exc.code else UNKNOWN
            if code == TIMEOUT:
                summary["timeout"].append((company.source, code, exc.detail))
                log.error("[%s] %s timeout: %s", name, company.source, exc)
            else:
                summary["failed"].append((company.source, code, exc.detail))
                log.error("[%s] %s falhou: %s", name, company.source, exc)
        except TimeoutError as exc:  # noqa: BLE001 - builtin str do mock/pista
            code, detail = classify_exception(exc)
            summary["timeout"].append((company.source, code, detail))
            log.error("[%s] %s timeout: %s", name, company.source, exc)
        except Exception as exc:  # noqa: BLE001 - segue para as proximas
            code, detail = classify_exception(exc)
            summary["failed"].append((company.source, code, detail))
            log.error("[%s] %s falhou: %s", name, company.source, exc)
    return jobs, summary
