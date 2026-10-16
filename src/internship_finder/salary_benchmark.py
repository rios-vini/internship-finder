"""Benchmark salarial curado (F29) — ESTIMATIVA DE MERCADO, nunca dado.

Arquivo versionado ``config/salary_benchmark.json`` (padrão employer_quality:
``_meta`` com fonte/checked + entradas por categoria). O loader é TOLERANTE:
arquivo ausente/corrompido/formato inesperado -> ``{}`` (sem badge, sem erro).

REGRA INVIOLÁVEL (orquestrador, F29): a estimativa de mercado JAMAIS funde
com o salário detectado no anúncio (``opportunity_intel.job_salary``). São
campos SEPARADOS — a estimativa é SEMPRE rotulada "estimativa de mercado" e
só é oferecida quando o anúncio NÃO cita salário (``job_salary`` ausente).
Camada INFORMATIVA de display: nada disto entra em score/eligibility/
filters/ranking.

Categorias (valores de partida da pesquisa de 12/10, fontes abaixo):

- ``pflichtpraktikum``: Ø ~1.021 EUR/mês (praktikum.info);
- ``freiwilliges_praktikum``: Ø ~1.507 EUR/mês (praktikum.info);
- ``werkstudent``: 14–17 EUR/h (kununu Ø ~2.400 EUR/mês FTE; Indeed Bayern
  Ø 17,46 EUR/h);
- Mindestlohn 2026: 13,90 EUR/h (meinpraktikum.de/absolventa.de).
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = [
    "DEFAULT_SALARY_BENCHMARK_PATH",
    "SALARY_ESTIMATE_LABEL",
    "SALARY_CATEGORY_PRACTIKUM",
    "load_salary_benchmark",
    "estimate_for_category",
    "salary_category_of",
    "salary_estimate_line",
    "salary_estimate_short",
    "salary_estimate_for_job",
    "market_salary_estimate",
]

DEFAULT_SALARY_BENCHMARK_PATH = Path("config/salary_benchmark.json")

# Rótulo LITERAL da estimativa (F29 item 5: SEMPRE rotulada, nunca dado).
SALARY_ESTIMATE_LABEL = "estimativa de mercado"

# Categorias canônicas do benchmark (chaves do arquivo curado).
SALARY_CATEGORY_PRACTIKUM = "praktikum"
SALARY_CATEGORY_WERKSTUDENT = "werkstudent"


def load_salary_benchmark(path: str | Path | None = None) -> dict[str, dict]:
    """Lê o benchmark curado; ``{}`` em qualquer falha (nunca levanta).

    Padrão ``load_employer_quality``: arquivo ausente/JSON quebrado/lista
    vazia -> mapa vazio = SEM estimativa em qualquer superfície (o sinal
    simplesmente não aparece; o build nunca quebra por causa dele).
    """
    if path is None:
        path = DEFAULT_SALARY_BENCHMARK_PATH
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = raw.get("categories") if isinstance(raw, dict) else raw
        if not isinstance(entries, dict):
            return {}
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for key, entry in entries.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        out[key] = entry
    return out


def estimate_for_category(benchmark: dict[str, dict] | None,
                          category: str) -> dict | None:
    """Entrada de estimativa da categoria; ``None`` quando não mapeada.

    Valida a estrutura mínima (``text`` presente) — entrada corrompida =
    sem estimativa (silêncio gracioso, mesma regra dos mapas curados).
    """
    if not benchmark or not category:
        return None
    entry = benchmark.get(category)
    if not isinstance(entry, dict) or not entry.get("text"):
        return None
    return entry


def salary_category_of(job: dict) -> str | None:
    """Categoria derivável do TÍTULO (F29 item 5); ``None`` = não derivável.

    Determinístico, casefold, offline — MESMA família de regra do
    ``is_werkstudent_title`` da F13 (título, não employment_type: medição
    F13 mostrou 0 ocorrências úteis nesse campo). Ordem de precedência:

    1. Pflichtpraktikum (marcador explícito) > praktikum genérico — a
       estimativa de Pflicht é a mais honesta quando o anúncio declara;
    2. Werkstudent (working student) — categoria própria (€/h).
    """
    title = str(job.get("title") or "").casefold()
    if not title.strip():
        return None
    if "pflichtpraktikum" in title:
        return "pflichtpraktikum"
    if "praktikum" in title or "praktikant" in title or "internship" in title \
            or "intern" in title:
        return SALARY_CATEGORY_PRACTIKUM
    if "werkstudent" in title or "working student" in title:
        return SALARY_CATEGORY_WERKSTUDENT
    return None


def salary_estimate_line(entry: dict) -> str:
    """Linha de display da estimativa: ``estimativa de mercado: ~X (fonte, MM/AAAA)``.

    O rótulo é LITERAL e INICIA a linha — a estimativa nunca aparece sem a
    palavra "estimativa" antes do valor (regra F29: nunca apresentada como
    dado). A data é a do ``checked`` da própria entrada curada.
    """
    source = str(entry.get("source_name") or "fonte de mercado").strip()
    checked = str(entry.get("checked") or "").strip()
    date_part = ""
    if len(checked) >= 7:
        date_part = f", {checked[:7].replace('-', '/')}"
    return f"{SALARY_ESTIMATE_LABEL}: ~{entry.get('text')}{date_part} ({source})"


def salary_estimate_short(entry: dict) -> str:
    """F51 — estimativa compacta do CARD: ``≈<texto>*``.

    A honestidade da F29 continua: o ``*`` remete à legenda única, que
    reproduz o rótulo LITERAL ``estimativa de mercado`` (a palavra
    "estimativa" segue presente na página — dentro da legenda, no
    bloco explicando o ``*``), a fonte e a data ``checked``. Pura.
    """
    return f"≈{entry.get('text')}*"


def market_salary_estimate(job: dict,
                           benchmark: dict[str, dict] | None) -> dict | None:
    """Estimativa de mercado para a vaga quando o anúncio NÃO cita salário.

    Contrato da F29 item 5 (REGRA INVIOLÁVEL):

    - ``opportunity_intel.job_salary`` PRESENTE -> ``None`` (mostra-se SÓ o
      detectado — nunca ambos, nunca fundidos);
    - ausente E categoria derivável do título E entrada no benchmark ->
      ``{"category", "entry"}``;
    - ausente e categoria não derivável -> ``None`` (sem estimativa — nunca
      chutar categoria pela descrição).
    """
    try:
        from internship_finder import opportunity_intel
        if opportunity_intel.job_salary(job) is not None:
            return None
    except Exception:  # noqa: BLE001 — best-effort, nunca derruba display
        return None
    category = salary_category_of(job)
    if category is None:
        return None
    entry = estimate_for_category(benchmark, category)
    if entry is None:
        return None
    return {"category": category, "entry": entry}


def salary_estimate_for_job(job: dict,
                            benchmark: dict[str, dict] | None,
                            *, compact: bool = False) -> str:
    """Linha pronta para o card/página; ``''`` quando não se aplica.

    Pura e offline; encapsula o contrato completo (detectado presente = ''
    — o chamador mostra apenas o salário detectado). F51:
    ``compact=True`` devolve a forma curta ``≈€1.507/mês*`` (o ``*``
    aponta para a legenda única); ``compact=False`` mantém a linha
    rotulada completa da F29 (digest e superfícies fora do card).
    """
    est = market_salary_estimate(job, benchmark)
    if est is None:
        return ""
    if compact:
        return salary_estimate_short(est["entry"])
    return salary_estimate_line(est["entry"])
