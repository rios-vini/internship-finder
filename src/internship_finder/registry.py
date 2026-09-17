"""Registry operacional de empresas da coleta (fonte de verdade).

Substitui a lista de empresas que hoje vive copiada no README/docs e era colada
manualmente no ``--companies``. Cada entrada traz o **nome canônico de coleta**
(a consulta usada no ``--companies`` / ``collect_company``) e, quando o tenant
da base é conhecido, o ATS/tenant de referência. ``enabled`` habilita/desabilita
a empresa sem editar texto corrido.

O ``status``/``última coleta`` por empresa NÃO é duplicado aqui: é derivado do
JSONL de métricas existente (``data/collection_metrics.jsonl``), que já registra
o estado por tenant com o nome da empresa. O registry apenas materializa o
agregado por empresa de forma read-only e defensiva (registro malformado nunca
derruba). Assim o estado operacional tem uma única fonte (o JSONL) e o registry
expõe a **configuração** (quais empresas, habilitadas, tenant de referência).

A **consistência** entre o tenant declarado no registry e o tenant que o
runtime de fato resolve/coleta é verificável por ``tenant_consistency_report``
(configuração x resultado real, classificação por empresa — ver docstring da
função) e exposta pelo ``--health`` (chave ``registry_consistency``).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class RegistryEntry(BaseModel):
    """Uma empresa operacional da coleta (configuração, não resultado)."""

    name: str  # nome canônico de coleta (consulta do --companies)
    ats: str | None = None  # ATS de referência quando conhecido (ex.: "successfactors")
    tenant: str | None = None  # tenant de referência na base (ex.: "successfactors:jobs")
    enabled: bool = True  # false desabilita a empresa sem removê-la do registry


# --- Seed: 96 empresas operacionais (12 da validação inicial + 27 da
# --- expansão E2 + 25 da expansão internacional P3 #23: 8 DE + 17 NL/CH/AT
# --- + 17 da expansão de cobertura 15/09/2026 + 6 da auditoria 16/09/2026
# --- + 9 da auditoria próxima fronteira 17/09/2026).
# --- Nomes canônicos = consulta real do ``--companies``
# --- (README.md + docs/empresas_verificacao.md + docs/relatorio_expansao.md +
# --- docs da auditoria de cobertura 15/09 + auditoria próxima onda 16/09).
# --- Tenant/ATS de referência preenchidos a partir dos docs quando conhecidos;
# --- ``None`` deixa "a base decide" (find_company resolve o tenant em runtime).
SEED = [
    # --- 12 da validação inicial (2026-08-10) ---
    RegistryEntry(name="Bosch", ats="smartrecruiters", tenant="smartrecruiters:BoschGroup"),
    RegistryEntry(name="SAP", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Continental", ats="smartrecruiters", tenant="smartrecruiters:continental"),
    RegistryEntry(name="ZF", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Bayer", ats="eightfold", tenant="eightfold:bayer"),
    RegistryEntry(name="BASF", ats="successfactors", tenant="successfactors:basf"),
    RegistryEntry(name="Henkel", ats="cornerstone", tenant="cornerstone:henkel"),
    RegistryEntry(name="Infineon", ats="eightfold", tenant="eightfold:infineon"),
    RegistryEntry(name="Zalando", ats="workday", tenant="workday:zalando/zalandositewd"),
    RegistryEntry(name="Delivery Hero", ats="smartrecruiters", tenant="smartrecruiters:deliveryhero"),
    RegistryEntry(name="Covestro", ats="workday", tenant="workday:covestro/cov_external"),
    RegistryEntry(name="Evonik", ats="workday", tenant="workday:evonik/external_careers"),
    # --- 27 da expansão E2 (2026-08-12) ---
    RegistryEntry(name="DHL", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Hellmann", ats="workday", tenant="workday:hellmann/hellmannexternaljobs"),
    RegistryEntry(name="Lidl", ats="successfactors", tenant="successfactors:lidlstiftuP2"),
    RegistryEntry(name="Kaufland", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="VWAGLPPROD10", ats="successfactors", tenant="successfactors:VWAGLPPROD10"),
    RegistryEntry(name="Schaeffler", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Mahle", ats="successfactors", tenant="successfactors:mahleinter"),
    RegistryEntry(name="Trumpf", ats="workday"),
    RegistryEntry(name="SICK AG", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Voith", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="knorrbremsP2", ats="successfactors", tenant="successfactors:knorrbremsP2"),
    RegistryEntry(name="brosefahrz", ats="successfactors", tenant="successfactors:brosefahrz"),
    RegistryEntry(name="Phoenix Contact", ats="greenhouse", tenant="greenhouse:phoenixcontact"),
    RegistryEntry(name="KraussMaffei", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="kronesag", ats="successfactors", tenant="successfactors:kronesag"),
    RegistryEntry(name="bbraunprd", ats="successfactors", tenant="successfactors:bbraunprd"),
    RegistryEntry(name="Sartorius", ats="workday", tenant="workday:sartorius/sartoriuscareers"),
    RegistryEntry(name="freseniusglobal", ats="workday", tenant="workday:freseniusglobal/fse"),
    RegistryEntry(name="Deutsche Telekom", ats="eightfold", tenant="eightfold:telekom-growthhub"),
    RegistryEntry(name="Celonis", ats="greenhouse", tenant="greenhouse:celonis"),
    RegistryEntry(name="DATEV", ats="workday"),
    RegistryEntry(name="Statista", ats="ashby", tenant="ashby:statista"),
    RegistryEntry(name="Scout24", ats="greenhouse", tenant="greenhouse:scout24"),
    RegistryEntry(name="Siemens Healthineers", ats="avature"),
    RegistryEntry(name="Zeiss Group", ats="workday", tenant="workday:zeissgroup/external"),
    RegistryEntry(name="draegerP", ats="successfactors", tenant="successfactors:draegerP"),
    RegistryEntry(name="Uniper", ats="successfactors", tenant="successfactors:jobs"),
    # --- 8 da expansão internacional P3 #23 (2026-09-08) — Lote A (DE) ---
    # Validadas com scripts/verify_companies.py --fetch (match exato + scraper
    # + fetch real OK >0 vagas); tenant copiado da saída (sem invenção).
    # Otto (jazzhr:otto) REMOVIDA em 15/09: falso positivo — otto.applytojob.com
    # não é o Otto Group (auditoria de cobertura; ver seção J.8).
    RegistryEntry(name="Allianz", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Adidas", ats="moka", tenant="moka:adidas/140456"),
    RegistryEntry(name="Puma", ats="workday", tenant="workday:puma/jobs_at_puma"),
    RegistryEntry(name="Hella", ats="cornerstone", tenant="cornerstone:hella"),
    RegistryEntry(name="Fraunhofer", ats="successfactors", tenant="successfactors:fraunhofer"),
    RegistryEntry(name="Merck", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Boehringer Ingelheim", ats="successfactors", tenant="successfactors:BoehringerPRD"),
    RegistryEntry(name="HelloFresh", ats="greenhouse", tenant="greenhouse:hellofresh"),
    # --- 17 da expansão internacional P3 #23 (2026-09-08) — Lote B (NL/CH/AT) ---
    RegistryEntry(name="Philips", ats="workday", tenant="workday:philips/jobs-and-careers"),
    RegistryEntry(name="ING", ats="workday", tenant="workday:ing/icsnldgen"),
    RegistryEntry(name="Heineken", ats="successfactors", tenant="successfactors:C0000032666P"),
    RegistryEntry(name="Adyen", ats="greenhouse", tenant="greenhouse:adyen"),
    RegistryEntry(name="Nestlé", ats="successfactors", tenant="successfactors:jobdetails"),
    RegistryEntry(name="Novartis", ats="workday", tenant="workday:novartis/novartis_careers"),
    RegistryEntry(name="ABB", ats="workday", tenant="workday:abb/External_Career_Page"),
    RegistryEntry(name="Red Bull", ats="smartrecruiters", tenant="smartrecruiters:RedBull"),
    RegistryEntry(name="Roche", ats="workday", tenant="workday:roche/roche-ext"),
    RegistryEntry(name="Swiss Re", ats="successfactors", tenant="successfactors:careers"),
    RegistryEntry(name="Schindler", ats="successfactors", tenant="successfactors:job"),
    RegistryEntry(name="Shell", ats="workday", tenant="workday:shell/shellcareers"),
    RegistryEntry(name="Unilever", ats="workday", tenant="workday:unilever/unilever_experienced_professionals"),
    RegistryEntry(name="AkzoNobel", ats="successfactors", tenant="successfactors:careers"),
    RegistryEntry(name="Rabobank", ats="workday", tenant="workday:rabobank/jobs"),
    RegistryEntry(name="NXP", ats="workday", tenant="workday:nxp/careers"),
    RegistryEntry(name="OMV", ats="successfactors", tenant="successfactors:omvagPRD"),
    # --- 17 da expansão de cobertura (2026-09-15, auditoria de cobertura) ---
    # Validadas AO VIVO em 15/09 com scripts/verify_companies.py --fetch (match
    # exato + scraper + fetch real); tenant copiado da RESOLUÇÃO REAL do runtime
    # (find_company), não do nome amigável — o tenant declarado precisa existir
    # no conjunto resolvido para o relatório de consistência não apontar drift.
    # Nomes canônicos = consulta de coleta (slug quando o nome natural não
    # resolve exato: BAUHAUS->bahagag, MediaMarkt->mediasatur, About You->
    # aboutyougmbh).
    RegistryEntry(name="Liebherr", ats="successfactors", tenant="successfactors:LiMySLive"),
    RegistryEntry(name="STIHL", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Simon-Kucher", ats="cornerstone", tenant="cornerstone:simon-kucher"),
    RegistryEntry(name="bahagag", ats="successfactors", tenant="successfactors:bahagag"),
    RegistryEntry(name="BCG", ats="bamboohr", tenant="bamboohr:bcg"),
    RegistryEntry(name="mediasatur", ats="successfactors", tenant="successfactors:mediasatur"),
    RegistryEntry(name="Tchibo", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="HORNBACH", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="aboutyougmbh", ats="smartrecruiters", tenant="smartrecruiters:aboutyougmbh"),
    RegistryEntry(name="Hager Group", ats="successfactors", tenant="successfactors:HagerGroup"),
    RegistryEntry(name="Lanxess", ats="successfactors", tenant="successfactors:lanxessP"),
    RegistryEntry(name="Linde", ats="cornerstone", tenant="cornerstone:linde"),
    RegistryEntry(name="Sonepar", ats="successfactors", tenant="successfactors:career"),
    RegistryEntry(name="Flix", ats="greenhouse", tenant="greenhouse:flix"),
    RegistryEntry(name="Kuehne+Nagel", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Vattenfall", ats="smartrecruiters", tenant="smartrecruiters:Vattenfall"),
    RegistryEntry(name="4flow", ats="workday", tenant="workday:4flow/4flow"),
    # --- 6 da auditoria de cobertura 16/09/2026 (próxima onda) ---
    # Identidades validadas AO VIVO em 16/09 (fetch real read-only; ver
    # /home/ubuntu/auditoria_proxima_onda_2026-09-16.md). BMW AG, Jobs Festo,
    # Wacker e Webasto Jobportal COMPARTILHAM successfactors:jobs mas têm URLs
    # de manifest distintas (jobs.bmwgroup.com / jobs.festo.com /
    # jobs.wacker.com / jobs.webasto.com) — o coletor desambigua por URL
    # (URL_SLUG_ATS), nunca pelo slug genérico "jobs" (padrão
    # STIHL/Tchibo/HORNBACH 15/09; regra da auditoria 16/09).
    # Nome canônico = nome EXATO do manifest quando ele não resolve pelo nome
    # natural (Jobs Festo, Webasto Jobportal, Wacker) — nunca deduzir a
    # empresa pelo slug compartilhado. SMA resolve também o tenant oracle
    # `fa-exow-saasfaprod1/cx_1` (slug incompleto p/ o oracle; identidade não
    # confirmada — NÃO é esta entrada): FETCH_ERROR recorrente esperado por
    # run, unidade falha nunca entra no SQLite/lifecycle (P1.2).
    RegistryEntry(name="BMW AG", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="SMA", ats="successfactors", tenant="successfactors:sma"),
    RegistryEntry(name="Jobs Festo", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Wacker", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Webasto Jobportal", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Roland Berger", ats="smartrecruiters", tenant="smartrecruiters:rolandberger"),
    # --- 9 da auditoria próxima fronteira (2026-09-17, READ-ONLY; relatório
    # --- /home/ubuntu/auditoria_proxima_fronteira_2026-09-17.md) ---
    # Validadas AO VIVO em 17/09 com fetch real read-only (manifest 80.390
    # empresas; funil oficial student/área/pais): todas com eligible DE>0
    # medido. Nome canônico = nome EXATO do manifest quando o nome natural
    # resolve falso positivo ou zero (regra da auditoria 16/09): "audibene /
    # hear.com" desambigua das 4 entradas audibene (join/personio/teamtailor
    # também existem) e "cbs Corporate Business Solutions GmbH" evita o FP
    # workable:cbs-9 (name "CBS"). O match EXATO do CompanyCollector
    # short-circuita o fallback token, então homônimas com name diferente não
    # entram na coleta (Picnic→só greenhouse:teampicnic, não "Picnic
    # Delivery"; Engelhart→só greenhouse, não join.com "Engelhart & Dirr";
    # Holzland Becker→só recruitee, não softgarden "Manfred Scherf
    # Holzfachhandel"). Tenants copiados da RESOLUÇÃO REAL do runtime.
    RegistryEntry(name="Picnic", ats="greenhouse", tenant="greenhouse:teampicnic"),
    RegistryEntry(name="AIXTRON SE", ats="softgarden", tenant="softgarden:aixtron"),
    RegistryEntry(name="CarOnSale", ats="greenhouse", tenant="greenhouse:caronsale"),
    RegistryEntry(name="cbs Corporate Business Solutions GmbH", ats="recruitee", tenant="recruitee:cbsconsulting"),
    RegistryEntry(name="CURRENTA GRUPPE", ats="recruitee", tenant="recruitee:currentagruppe"),
    RegistryEntry(name="Engelhart", ats="greenhouse", tenant="greenhouse:engelhart"),
    RegistryEntry(name="Holzland Becker", ats="recruitee", tenant="recruitee:holzlandbecker"),
    RegistryEntry(name="Miebach Consulting GmbH", ats="recruitee", tenant="recruitee:miebachconsulting"),
    RegistryEntry(name="audibene / hear.com", ats="greenhouse", tenant="greenhouse:audibenehearcom"),
]


def _status_sort_key(rec: dict) -> tuple:
    """Chave de ordenacao: run_id (string ordenavel) primeiro; fallback timestamp.

    Espelha ``health._sort_key`` (P3 lote 1): registros com ``run_id`` string
    ordenam antes dos que so tem ``timestamp``; sem ambos, mantem a ordem de
    chegada (sort estavel). ``run_id``/``timestamp`` nao-string ou vazios sao
    tratados como ausentes — o status nunca derruba por tipo inesperado.
    """
    run_id = rec.get("run_id")
    if isinstance(run_id, str) and run_id.strip():
        return (0, run_id)
    ts = rec.get("timestamp")
    if isinstance(ts, str) and ts.strip():
        return (1, ts)
    return (2, "")


class CompanyRegistry:
    """Fonte de verdade das empresas operacionais da coleta.

    Carrega o seed em código (sem persistência em ``data/`` durante a tarefa).
    ``company_status`` agrega o estado por empresa a partir do JSONL de métricas
    existente (LEITURA defensiva; nunca escreve e nunca derruba).
    """

    def __init__(self, entries: list[RegistryEntry] | None = None) -> None:
        self._entries: dict[str, RegistryEntry] = {}
        for e in entries if entries is not None else SEED:
            self._entries[e.name] = e

    @property
    def entries(self) -> list[RegistryEntry]:
        """Entradas ordenadas por nome (determinístico)."""
        return [self._entries[n] for n in sorted(self._entries)]

    def get(self, name: str) -> RegistryEntry | None:
        return self._entries.get(name)

    def enabled(self, names: list[str] | None = None) -> list[RegistryEntry]:
        """Entradas habilitadas; ``names`` opcional restringe o subconjunto.

        Ordem de ``names`` preservada quando fornecido (importante para a ordem
        de coleta do CLI); sem ele, ordem alfabética do seed. Uma entrada
        desabilitada nunca entra no resultado.
        """
        if names is None:
            return [e for e in self.entries if e.enabled]
        result = []
        for n in names:
            e = self._entries.get(n)
            if e is not None and e.enabled:
                result.append(e)
        return result

    def company_status(self, metrics: Path | str) -> dict[str, dict]:
        """Estado por empresa derivado do JSONL de métricas (read-only).

        Para cada empresa do registry, agrega os registros ``type: tenant`` que
        carregam aquele ``company``: último ``status``, última data e total de
        vagas da última coleta. O "último" registro é o mais recente por
        ``(run_id, timestamp)`` (P3 lote 1, espelho de ``health._sort_key``) —
        NÃO a última linha do arquivo: JSONL pode chegar fora de ordem.
        Registros malformados são ignorados sem derrubar.
        Empresas sem nenhum registro aparecem com ``status=None``.
        """
        if not Path(metrics).exists():
            return {e.name: {"status": None, "last_run": None, "last_collected": None}
                    for e in self.entries}
        company_rows: dict[str, list[dict]] = {e.name: [] for e in self.entries}
        for line in Path(metrics).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or rec.get("type") != "tenant":
                continue
            company = rec.get("company")
            if company not in company_rows:
                continue
            company_rows[company].append(rec)

        status: dict[str, dict] = {}
        for name, rows in company_rows.items():
            if not rows:
                status[name] = {"status": None, "last_run": None, "last_collected": None}
                continue
            # run mais recente por (run_id, timestamp) — nao por posicao no
            # arquivo (linhas podem vir fora de ordem; P3 lote 1).
            last = sorted(rows, key=_status_sort_key)[-1]
            status[name] = {
                "status": last.get("status"),
                "last_run": last.get("timestamp"),
                "last_collected": last.get("collected"),
            }
        return status


def registry_names(registry: CompanyRegistry, names: list[str] | None = None) -> list[str]:
    """Nomes de coleta a partir do registry (lista de ``str`` para o CLI).

    Sem ``names`` devolve TODAS as habilitadas (ordem alfabética); com ``names``
    devolve a interseção na ordem informada.
    """
    return [e.name for e in registry.enabled(names)]


# --- Consistencia Registry x runtime (P2: tenant declarado x tenant real) ---

# Status da classificacao por empresa (chaves do relatorio de consistencia):
#  - "consistent"  — tenant declarado == unica resolucao do runtime (normal);
#  - "drift"       — tenant DECLARADO (nao-None) ausente das resolucoes do
#    runtime: o registry diz X e o runtime resolve/coleta so Y — divergencia;
#  - "multi"       — declarado presente entre N>1 resolucoes: o registry nao
#    declara ser exaustivo, so referencia; coleta extra e informativa, nao e
#    erro;
#  - "dynamic"     — declarado ``None`` e o runtime resolveu: resolucao
#    dinamica deliberada (a base decide), NAO e drift;
#  - "not_found"   — o runtime nao resolveu nenhum tenant para a empresa
#    (sem match exato na base);
#  - "no_data"     — nenhuma informacao de runtime para a empresa (ex.: ainda
#    nao coletada no run de referencia).
TENANT_CONSISTENT = "consistent"
TENANT_DRIFT = "drift"
TENANT_DYNAMIC = "dynamic"
TENANT_MULTI = "multi"
TENANT_NOT_FOUND = "not_found"
TENANT_NO_DATA = "no_data"


def tenant_consistency_status(
    declared_tenant: str | None,
    runtime_sources: list[str],
) -> str:
    """Classifica o tenant declarado no registry contra os tenants resolvidos.

    Regra central: so existe DRIFT quando o registry declara um tenant
    explicito e o runtime resolve ALGO diferente — listas vazias sao
    ``not_found`` (sem resolucao nao ha o que comparar; o erro original de
    coleta continua visivel no JSONL via status ``not_found``, nao e mascarado)
    e ``None`` declarado e sempre ``dynamic`` (resolveu) ou ``not_found``
    (nao resolveu) — nunca drift. Tenants compartilhados entre empresas nao
    afetam a classificacao: ela consome so a resolucao DA empresa.
    """
    sources = [s for s in (runtime_sources or [])
               if isinstance(s, str) and s.strip()]
    if not sources:
        return TENANT_NOT_FOUND
    if declared_tenant is None:
        return TENANT_DYNAMIC
    if declared_tenant not in sources:
        return TENANT_DRIFT
    return TENANT_MULTI if len(sources) > 1 else TENANT_CONSISTENT


def tenant_consistency_report(
    entries: list[RegistryEntry],
    runtime_tenants: dict[str, list[str]],
) -> list[dict]:
    """Relatorio de consistencia Registry x runtime, por empresa.

    ``runtime_tenants`` mapeia o nome canonico da empresa -> tenants
    (``ats:slug``) resolvidos pelo runtime no ponto de referencia (ex.: os
    registros ``type: tenant`` do run mais recente do JSONL de metricas via
    ``latest_run_tenants``, ou a resolucao viva de ``find_company``).

    Empresa AUSENTE do dict = ``no_data`` (sem informacao de runtime); presente
    com lista vazia = ``not_found`` (resolvida e nao encontrada).

    A identidade da comparacao e POR EMPRESA (nome canonico do registry),
    nunca ``source`` isolado como identidade global: o MESMO tenant pode ser
    compartilhado por varias empresas (ex.: ``successfactors:jobs`` cobre
    SAP/ZF/Kaufland/...; ``phenom:nan`` cobre DHL/Allianz/Merck/...) e a
    classificacao de uma empresa nunca depende do que outra coletou.

    Devolve uma linha por entrada (ordem do registry, deterministica), com
    ``company``, ``ats``, ``registry_tenant``, ``runtime_tenants`` (ordenado)
    e ``status`` — JSON-serializavel.
    """
    report: list[dict] = []
    for e in entries:
        sources = runtime_tenants.get(e.name)
        if sources is None:
            status = TENANT_NO_DATA
        else:
            status = tenant_consistency_status(e.tenant, sources)
        report.append(
            {
                "company": e.name,
                "ats": e.ats,
                "registry_tenant": e.tenant,
                "runtime_tenants": sorted(
                    s for s in (sources or []) if isinstance(s, str) and s.strip()
                ),
                "status": status,
            }
        )
    return report


def latest_run_tenants(records: list[dict]) -> dict[str, list[str]]:
    """Tenants resolvidos pelo runtime no run MAIS RECENTE dos ``records``.

    Consome os registros ``type: tenant`` do JSONL de metricas: agrupa por
    ``company`` os ``source`` (``ats:slug``) do run com o ``run_id`` maior
    (ISO 8601 ordena cronologicamente). Registrar de ``not_found`` (sem
    ``source``) marca a empresa com lista vazia — distinto de empresa sem
    nenhum registro (ausente do dict). Malformados sao ignorados, nunca
    derrubam (mesmo espirito do health). Deduplica sources por empresa.
    """
    latest: str | None = None
    for r in records:
        if not isinstance(r, dict) or r.get("type") != "tenant":
            continue
        rid = r.get("run_id")
        if isinstance(rid, str) and rid and (latest is None or rid > latest):
            latest = rid
    if latest is None:
        return {}
    out: dict[str, list[str]] = {}
    for r in records:
        if not isinstance(r, dict) or r.get("type") != "tenant":
            continue
        if r.get("run_id") != latest:
            continue
        company = r.get("company")
        if not (isinstance(company, str) and company):
            continue
        source = r.get("source")
        if isinstance(source, str) and source.strip():
            sources = out.setdefault(company, [])
            if source not in sources:
                sources.append(source)
        elif r.get("status") == "not_found":
            # Convencao do CLI: ``not_found`` grava a empresa SEM tenant
            # (``source`` vazio) — marca a empresa com lista vazia, para o
            # relatorio distinguir de "sem dados". Registro sem source e sem
            # status ``not_found`` e malformado/legado: ignorado (o health
            # tambem o ignora).
            out.setdefault(company, [])
    return out