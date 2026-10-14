"""Ranking por perfil EU non-DE — F36 (terceiro perfil).

Classifica as MESMAS vagas elegíveis do pipeline por relevância para o
canal secundário declarado na F7 (DE primário; NL/BE/LU/FI backup). O
benchmark v2 (F27, docs/ranking_benchmark.md §6.4c) mediu que o estrato
não-DE NÃO se comporta como o DE sob os pesos atuais:

- tau +0,528 (não-DE) vs +0,785 (DE);
- ``location`` vale 0 em 204/205 não-DE (componente DE-explícita por
  design) + registry quase ausente fora da DE (0,09 vs 0,44) = handicap
  estrutural ~1,5 pts SEM relação com qualidade;
- não-DE = 26% do universo mas só 12% do top-100;
- 40% rotuladas "ruim" (marketing/BD/HR de startups EN) vs 20% no DE.

F36 (veredito do dono 13/10, ver docs/f36_non_de_profile.md): ranking
SEPARADO POR PERFIL — o mesmo padrão da Fase 4 (Materials Engineering).
Perfis business e materials permanecem INTOCADOS (invariante byte-idêntica
testada em scripts/test_f36.py).

Princípios (mesmos da Fase 4):

- **Não altera a elegibilidade**: opera SOMENTE sobre o conjunto já
  elegível (mesmas vagas, mesma dedup, mesmos filtros).
- **Score independente**: ``eu_score``/``eu_breakdown`` são campos NOVOS,
  adicionados SEM tocar ``score``/``score_breakdown`` (business) nem
  ``materials_score``/``materials_breakdown``. Os três rankings coexistem,
  cada um com ordem própria.
- **Determinístico, reproduzível, barato**: regex sobre o texto original
  (título + descrição) + arquivos versionados (watchlist F13). Sem LLM.
- **Função pura do job**: o score de uma vaga não depende de outras
  vagas do universo (recorrência de empresa foi rejeitada na calibração
  exatamente por quebrar essa pureza — o score mudaria só porque o
  universo ao redor mudou).

Composição do score (constantes de módulo):

    area      = MESMOS detectores/pesos do business (filters.area_score,
                título 2.0 / descrição 0.0 — a descrição continua entrando
                por skills+language)
    skills    = MESMOS do business (+0.75 por competência na descrição)
    language  = MESMO do business (EN +1.5; DE required −2.0 / preferred −0.5)
    type      = marcador forte de tipo no título (+1.0, reusa filters)
    location  = país-alvo do PROJETO (iso em countries.TARGET_COUNTRIES
                → +1.0; sem bônus Berlin — o sinal aqui é "país do plano
                de emigração", não "Alemanha em particular")
    interest  = watchlist F13 (+0.5) — a lista de interesse do dono
                REderivada para o estrato: o registry F3/F32 (110→127
                empresas DE) cobre 17% do não-DE; a watchlist F13
                (curadoria visa_friendly/nicho, editável pelo dono) cobre
                39%. Match casefold exato/substring (mesma regra F3).
    penalties = senior/manager/full_time — MESMOS detectores/pesos
    fn        = função NÃO-alvo no TÍTULO (marketing/HR/sales-BD) −2.5,
                GATED: só quando o título NÃO tem termo primário de área
                (híbridos "HR Analytics"/"Sales Analytics" são vagas de
                dados e ficam protegidos — mesmo espírito da regra do
                milestone 2 do ranking principal). Resposta direta ao
                achado v2: 40% do estrato "ruim" sobe pelo termo
                "Operations"/"Analyst" em títulos de marketing/BD/HR.

Calibração: grid offline no estrato não-DE rotulado do v2 (35 vagas, 432
pares comparáveis; ver docs/f36_non_de_profile.md §benchmark v3). w_fn
em {2.0, 2.5, 3.0} todos ≥ alvo (+0.10 sobre +0,528); escolhido 2.5
(centro do intervalo, não o pico — com n=35 o grid fino é frágil).
Validação 2-fold (paridade de id): holdout A→B +0,769 / B→A +0,523.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from internship_finder.countries import TARGET_COUNTRIES, infer_country_iso
from internship_finder.filters import (
    AREA_PRIMARY,
    STUDENT_TYPE_PATTERNS,
)
from internship_finder.ranking import (
    Score,
    _area_score,
    _language_score,
    _matches_any,
    _penalty_score,
    _skills_score,
)

# ---------------------------------------------------------------------------
# Pesos (constantes de módulo — ajuste fácil e documentado)
# ---------------------------------------------------------------------------

# area/skills/language/type/penalties: MESMOS pesos do business — reuso das
# funções privadas de ranking.py (o perfil é novo; os detectores não são).
WEIGHT_TYPE_TITLE = 1.0
# Localização: qualquer país-alvo do projeto (F7), não só a DE.
WEIGHT_TARGET_COUNTRY = 1.0
# Watchlist F13 como lista de interesse do estrato (registry rederivado).
# Menor que WEIGHT_REGISTRY_INTEREST (+1.0 no business): a watchlist é uma
# curadoria mais larga (visa_friendly + nicho) e a calibração no estrato
# não mostrou ganho ordinal acima de +0.5 (grid: watch 0.5 ≈ watch 0.0).
WEIGHT_WATCHLIST_INTEREST = 0.5
# Função não-alvo no título, sem termo primário de área (gate).
PENALTY_NON_TARGET_FUNCTION = -2.5

# ---------------------------------------------------------------------------
# Watchlist F13 (config/company_watchlist.json) — lazy singleton tolerante
# ---------------------------------------------------------------------------

# Arquivo versionado, editável pelo dono (F13). Ausente/corrompido/vazio →
# componente fica 0 para TODAS as vagas (nunca erro — o perfil não pode
# derrubar o refresh). Mesma filosofia de load_watchlist do radar F13.
_WATCHLIST_PATH = Path(__file__).resolve().parents[2] / "config" / "company_watchlist.json"
_watchlist_cache: frozenset[str] | None = None


def _watchlist_companies() -> frozenset[str]:
    """Nomes da watchlist (casefold), lazy; vazio em qualquer falha."""
    global _watchlist_cache
    if _watchlist_cache is None:
        try:
            data = json.loads(_WATCHLIST_PATH.read_text(encoding="utf-8"))
            names = [
                str(w).strip().casefold()
                for w in (data.get("companies") or [])
                if str(w).strip()
            ]
        except (OSError, ValueError, AttributeError):
            names = []
        _watchlist_cache = frozenset(names)
    return _watchlist_cache


def watchlist_interest(company: str | None) -> float:
    """Componente ``interest``: watchlist F13 com match casefold
    exato/substring (mesma regra do registry F3 — FN barato > FP caro)."""
    if not company:
        return 0.0
    folded = str(company).strip().casefold()
    if not folded:
        return 0.0
    for name in _watchlist_companies():
        if name and (name == folded or name in folded):
            return WEIGHT_WATCHLIST_INTEREST
    return 0.0


# ---------------------------------------------------------------------------
# Funções não-alvo no TÍTULO (padrão materials: categorias fechadas,
# lista curta e fixa, calibrada nos modos de falha DOCUMENTADOS do v2)
# ---------------------------------------------------------------------------

# Três categorias (marketing/HR/vendas-BD) = os "ruim" do estrato no v2:
# marketing/BD/HR de startups EN que passam pelos filtros multi-país.
# Cada lista é CURTA por design: penalidade de título precisa ser
# precisa; termo genérico demais criaria dano colateral (medido: 15/777
# títulos híbridos com área primária — protegidos pelo gate abaixo).
NON_TARGET_FUNCTION_PATTERNS: dict[str, list[str]] = {
    "marketing": [
        r"\bmarketing\b",
        r"\bbrand\b",
        r"\bcommunications\b",
        r"\bcontent\b",
        r"\btourism\b",
        r"\bevent management\b",
    ],
    "hr": [
        r"\bhr\b",
        r"\bhuman resources\b",
        r"\brecruit\w*",
        r"\btalent\b",
        r"\bpeople\b",
        r"\bemployee experience\b",
    ],
    "sales_bd": [
        r"\bsales\b",
        r"\bbusiness development\b",
        r"\baccount manager\b",
        r"\bclient services\b",
        r"\bcustomer (care|service|support)",
        r"\bkey account",
    ],
}
_FN_RE = [
    re.compile(p, re.IGNORECASE)
    for pats in NON_TARGET_FUNCTION_PATTERNS.values()
    for p in pats
]
# Gate: termo PRIMÁRIO de área no título protege a vaga (híbridos de dados).
_AREA_PRIMARY_RE = [re.compile(p, re.IGNORECASE) for p in AREA_PRIMARY]


def _fn_penalty_score(title: str) -> float:
    """Penalidade por função não-alvo no TÍTULO, com gate de área primária.

    O v2 mostrou os "ruim" do estrato subindo por "Operations"/"Analyst"
    em títulos de marketing/BD/HR (40% do estrato). A penalidade só vale
    quando o título NÃO carrega termo primário de área: "HR Analytics
    Intern" e "Sales Development and Analytics" são vagas de DADOS
    (15/777 casos medidos) e ficam protegidos — o sinal de dados vence a
    função organizacional, mesmo espírito do milestone 2 do principal
    (marcador forte vence senioridade).
    """
    if any(rx.search(title) for rx in _AREA_PRIMARY_RE):
        return 0.0
    if any(rx.search(title) for rx in _FN_RE):
        return PENALTY_NON_TARGET_FUNCTION
    return 0.0


# ---------------------------------------------------------------------------
# Location por país-alvo do projeto
# ---------------------------------------------------------------------------


def _location_score(d: dict[str, Any]) -> float:
    """País-alvo do projeto (countries.TARGET_COUNTRIES) → +1.0.

    Diferente do business (DE-explícito + Berlin), aqui o sinal é "a vaga
    está num país do plano F7" — todos os países-alvo valem o mesmo. O
    estrato não-DE deixa de carregar o handicap −1.0 estrutural medido
    no v2 (location=0 em 204/205).
    """
    location = d.get("location") or ""
    iso = infer_country_iso(location=location, country_iso=d.get("country_iso"))
    if iso in TARGET_COUNTRIES:
        return WEIGHT_TARGET_COUNTRY
    return 0.0


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------


def eu_score_job(job: dict[str, Any] | Any) -> Score:
    """Score de relevância para o canal EU non-DE (dict ou ``Job``).

    Função pura e determinística. Componentes NOVOS — nunca toca
    ``score``/``score_breakdown`` (business) nem ``materials_*``.
    """
    d = job.to_dict() if hasattr(job, "to_dict") else job
    title = str(d.get("title") or "")
    description = d.get("description") or ""
    text = f"{title} {description}"

    area = _area_score(title, description)
    skills = _skills_score(description)
    language = _language_score(text)
    type_bonus = (
        WEIGHT_TYPE_TITLE
        if _matches_any(STUDENT_TYPE_PATTERNS, title.lower())
        else 0.0
    )
    location = _location_score(d)
    interest = watchlist_interest(d.get("company"))
    penalties = _penalty_score(title.lower(), d.get("employment_type"))
    fn = _fn_penalty_score(title)

    breakdown = {
        "area": round(area, 2),
        "skills": round(skills, 2),
        "language": round(language, 2),
        "type": round(type_bonus, 2),
        "location": round(location, 2),
        "interest": round(interest, 2),
        "penalties": round(penalties, 2),
        "fn": round(fn, 2),
    }
    total = round(sum(breakdown.values()), 2)
    return Score(total=total, breakdown=breakdown)


def rank_eu_jobs(jobs: list[dict[str, Any]] | list[Any]) -> list[dict[str, Any]]:
    """Adiciona ``eu_score`` + ``eu_breakdown`` e ordena desc.

    Ranking INDEPENDENTE dos perfis business/materials: mesma entrada
    (vagas elegíveis), score próprio, posições próprias. Desempate
    determinístico (score desc -> título casefold -> empresa -> id —
    mesmo critério dos outros dois perfis). Retorna NOVA lista; a entrada
    não é mutada e os scores dos outros perfis não são alterados.
    """
    out: list[dict[str, Any]] = []
    for item in jobs:
        d = item.to_dict() if hasattr(item, "to_dict") else dict(item)
        score = eu_score_job(d)
        d["eu_score"] = score.total
        d["eu_breakdown"] = score.breakdown
        out.append(d)
    out.sort(
        key=lambda j: (
            -j["eu_score"],
            str(j.get("title") or "").casefold(),
            str(j.get("company") or "").casefold(),
            str(j.get("id") or ""),
        )
    )
    return out


def is_eu_stratum_job(job: dict[str, Any] | Any) -> bool:
    """A vaga pertence ao estrato não-DE (canal secundário F7)?

    Determinístico e tolerante: usa o MESMO ``infer_country_iso`` do
    pipeline (location + country_iso). Sem ISO resolvido (ex.: remoto
    sem país) NÃO é do estrato — a seção de display "Fora da Alemanha"
    só promete vagas fora da DE.
    """
    d = job.to_dict() if hasattr(job, "to_dict") else job
    iso = infer_country_iso(
        location=d.get("location"), country_iso=d.get("country_iso")
    )
    return iso is not None and iso != "de"


def rank_eu_stratum(
    jobs: list[dict[str, Any]] | list[Any],
) -> list[dict[str, Any]]:
    """Ranking do perfil EU SOBRE O ESTRATO não-DE (display).

    ``rank_eu_jobs`` pontua o universo inteiro (o score de qualquer vaga
    é computável — mesma filosofia dos perfis business/materials); esta
    função é o corte de EXIBIÇÃO da seção 🇪🇺: filtra o estrato
    (``is_eu_stratum_job``) e devolve o ranking próprio do subconjunto.
    Sem mutação da entrada; desempate idêntico ao ``rank_eu_jobs``.
    """
    stratum = [
        (item.to_dict() if hasattr(item, "to_dict") else dict(item))
        for item in jobs
        if is_eu_stratum_job(item)
    ]
    return rank_eu_jobs(stratum)
