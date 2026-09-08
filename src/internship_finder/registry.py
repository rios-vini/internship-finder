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

    @property
    def source(self) -> str:
        """Identificador composto de tenant quando disponível (``ats:slug``)."""
        return self.tenant or ""


# --- Seed: as 65 empresas operacionais (12 da validação inicial + 27 da
# --- expansão E2 + 26 da expansão internacional P3 #23: 9 DE + 17 NL/CH/AT).
# --- Nomes canônicos = consulta real do ``--companies``
# --- (README.md + docs/empresas_verificacao.md + docs/relatorio_expansao.md).
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
    # --- 9 da expansão internacional P3 #23 (2026-09-08) — Lote A (DE) ---
    # Validadas com scripts/verify_companies.py --fetch (match exato + scraper
    # + fetch real OK >0 vagas); tenant copiado da saída (sem invenção).
    RegistryEntry(name="Allianz", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Adidas", ats="moka", tenant="moka:adidas/140456"),
    RegistryEntry(name="Puma", ats="workday", tenant="workday:puma/jobs_at_puma"),
    RegistryEntry(name="Hella", ats="cornerstone", tenant="cornerstone:hella"),
    RegistryEntry(name="Fraunhofer", ats="successfactors", tenant="successfactors:fraunhofer"),
    RegistryEntry(name="Merck", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Boehringer Ingelheim", ats="successfactors", tenant="successfactors:BoehringerPRD"),
    RegistryEntry(name="HelloFresh", ats="greenhouse", tenant="greenhouse:hellofresh"),
    RegistryEntry(name="Otto", ats="jazzhr", tenant="jazzhr:otto"),
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