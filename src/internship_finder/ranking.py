"""Ranking/matching por perfil — funcoes puras, sem dependencia de CLI.

Ordena as vagas candidataveis por compatibilidade com o perfil do dono
(Supply Chain, Procurement, BI, Analytics, Automacao; competencias de dados;
ingles essencial; Alemanha). Heuristica deterministica, sem ML.

Componentes do score (``score_job`` -> ``Score.total`` + ``breakdown``):

- **registry** — F3: o registry de 101 empresas vira LISTA DE INTERESSE:
    ``+WEIGHT_REGISTRY_INTEREST`` quando a empresa da vaga bate com um nome
    canonico do registry (casefold exato OU substring — "Robert Bosch GmbH"
    contem "bosch"). NAO e filtro: vaga fora do registry entra no eligible
    normalmente, so sem o desempate. Todos os demais componentes abaixo
    seguem INALTERADOS para qualquer vaga (invariante F3 §7.1: o unico
    delta permitido no ranking e este componente novo, aditivo).
- **area** — reusa ``filters.area_score``, mas so a parte do TITULO
  (``AREA_TITLE_WEIGHT``). A area vinda da DESCRICAO e multiplicada por
  ``AREA_DESC_WEIGHT``, calibrado em **0.0** no conjunto real (13.482 brutas):
  os templates genericos de descricao (ex.: SAP) citam "data", "sap",
  "reporting", "automation" em vagas de Marketing/Comunicacao e inflavam a
  area dessas vagas acima de cargos com area clara no titulo (Praktikum
  Logistik, JMP Purchasing). O valor da descricao continua entrando pelas
  componentes **skills** e **language**. Se um dia as descricoes forem mais
  ricas, ajustar a constante.
  Fase 2 (pos-auditoria): frases de PRODUTO com termos de area no TITULO
  (``AREA_TITLE_PRODUCT_PATTERNS``, ex.: "SAP Analytics Cloud") sao
  mascaradas antes da deteccao — o termo pertence ao nome do produto, nao a
  funcao da vaga ("Working Student ... Communications / Media Production in
  SAP Analytics Cloud" nao e vaga de Analytics). Lista curta e fixa,
  calibrada no caso real da auditoria; a frase mais especifica vem primeiro
  (senao o "sap" fraco remanescente ainda pontuaria).
- **skills** — competencias do perfil na DESCRICAO (+WEIGHT_SKILL por termo;
  sem descricao, contribui 0).
- **language** — ingles (+WEIGHT_LANG_EN, essencial) quando ha evidencia no
  titulo+descricao; alemão pela EXIGENCIA DETECTADA NO TEXTO (Fase 6):
  ``app_intel.german_level`` classifica required (penalidade forte
  PENALTY_LANG_DE_REQUIRED) / preferred (PENALTY_LANG_DE_PREFERRED) / plus
  (neutro) / sem mencao (neutro). Nao ha mais bonus por o anuncio conter
  alemao: o idioma em que o anuncio foi escrito NAO e requisito. Muitas
  descricoes estao vazias: sem descricao, age-se com graca e o score vem so
  do titulo.
- **type** — marcador forte de tipo de vaga no TITULO (Praktikum, Werkstudent,
  Internship, iXp... — reusa ``filters.STUDENT_TYPE_PATTERNS``; Trainee/JMP
  NAO sao marcadores: os programas de ``filters.PROGRAM_EXCLUSION_PATTERNS``
  nao chegam ao ranking e nao ganham bonus de tipo):
  +WEIGHT_TYPE_TITLE.
- **location** — DE explicito (ISO alpha-2 via ``filters.infer_country_iso``)
  +WEIGHT_DE_EXPLICIT; Berlin (capital alema) +WEIGHT_DE_CAPITAL. Remoto fica
  neutro.
- **penalties** — ``senior/director/head/principal`` (PENALTY_SENIOR, forte) e
  ``manager`` (PENALTY_MANAGER, suave) SO quando nao ha marcador forte de tipo
  no titulo (regra do milestone 2: marcador forte vence senioridade —
  "Praktikum ... Senior VP" fica protegido; JMP/Trainee nao sao marcadores e
  nao recebem protecao de penalidade);
  ``employment_type == FULL_TIME`` (PENALTY_FULL_TIME, suave: varios
  Werkstudent/Praktikum vêm marcados FULL_TIME no conjunto — nao zera).

Pesos em constantes de modulo (ajuste facil). Desempate deterministico:
score desc, depois titulo (casefold), empresa, id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from internship_finder.app_intel import english_evidence, german_level
from internship_finder.filters import (
    MANAGER_PATTERN,
    SENIORITY_PATTERNS,
    STUDENT_TYPE_PATTERNS,
    area_score,
    infer_country_iso,
)
from internship_finder.registry import CompanyRegistry

# ---------------------------------------------------------------------------
# Pesos (constantes de modulo — ajuste facil)
# ---------------------------------------------------------------------------

WEIGHT_AREA_TITLE = 2.0  # area do TITULO (filters.area_score, so titulo)
# F5 (03/10): experimento offline nos 29 pares benchmark-x-snapshot atual
# (benchmarks/ranking_benchmark_v1.json x eligible 478; ver relatorio F5
# §experimento): W in {0.25, 0.5, 1.0} — tau +0.712 -> +0.732 (so W=1.0),
# gap elite-bad +6.26 -> +7.10 (as duas classes sobem JUNTAS — o sinal nao
# discrimina), drift top-10 = 1 permuta boa<->boa, inversoes elite-bad 3->2.
# Evidencia FRACA a favor de W>0 num N=29 dominado por vagas do proprio
# perfil (dados/supply) — o FP original da calibracao (Marketing citando
# "data" no template) NAO esta na amostra (churn). Mantem 0.0: calibracao
# original em 13.482 brutas > experimento em 29; honestidade > completude.
WEIGHT_AREA_DESC = 0.0  # area da DESCRICAO (mantido: 0 — experimento F5 nao autoriza mudanca)
WEIGHT_SKILL = 0.75  # por competencia do perfil na descricao
WEIGHT_LANG_EN = 1.5  # ingles essencial (qualquer evidencia no titulo/descricao)
PENALTY_LANG_DE_REQUIRED = -2.0  # "German required", "fließende Deutschkenntnisse"...
PENALTY_LANG_DE_PREFERRED = -0.5  # "German preferred", "von Vorteil", par sem nivel
WEIGHT_TYPE_TITLE = 1.0  # marcador forte de tipo no TITULO
WEIGHT_DE_EXPLICIT = 1.0  # DE explicito (ISO) na vaga
WEIGHT_DE_CAPITAL = 0.5  # Berlin (capital alema)
PENALTY_SENIOR = -3.0  # senior/director/head/principal (forte)
PENALTY_MANAGER = -1.0  # "manager" suave (protegido por marcador forte de tipo)
PENALTY_FULL_TIME = -0.5  # suave: Werkstudent/Praktikum marcados FULL_TIME

# F3 — registry como LISTA DE INTERESSE (componente novo no Score.breakdown).
# O registry deixa de ser filtro de existencia: vaga de empresa FORA do
# registry entra no eligible normalmente e so perde o desempate. Match:
# ``Job.company`` casefold == nome canonico do registry OU nome do registry
# e SUBSTRING do company do job (casefold) - o dataset traz nomes legais
# ("Robert Bosch GmbH" vs registry "Bosch", "MAHLE International GmbH" vs
# "Mahle"). Substring casefold: FN barato > FP caro (um "Bosch" matcheia
# "Robert Bosch GmbH"; FP tipo "Bosch" dentro de outro nome e raro e
# benigno). NAO e filtro: todos os jobs entram, so com -1.0 relativo.
WEIGHT_REGISTRY_INTEREST = 1.0

# Frases de PRODUTO que contem termos de area ("Analytics" em "SAP Analytics
# Cloud"). O termo e do NOME DO PRODUTO, nao da funcao da vaga: nao deve
# pontuar como area do TITULO (Fase 2, pos-auditoria). Lista curta e fixa,
# calibrada no caso real (a unica vaga do conjunto com "analytics cloud" no
# titulo era uma vaga de Communications/Media). A frase MAIS ESPECIFICA vem
# PRIMEIRO: se "analytics cloud" rodasse antes, sobraria "sap" fraco no
# titulo e a area ainda ganharia +2.0. Novos produtos: adicionar a frase
# completa na ordem (especifica -> generica).
AREA_TITLE_PRODUCT_PATTERNS = [
    r"\bsap analytics cloud\b",
    r"\banalytics cloud\b",
]
_AREA_TITLE_PRODUCT_RE = [
    re.compile(p, re.IGNORECASE) for p in AREA_TITLE_PRODUCT_PATTERNS
]

# ---------------------------------------------------------------------------
# Competencias do perfil (positivo; na descricao)
# ---------------------------------------------------------------------------

# Termos exatos da especificacao do dono. Cada termo detectado soma
# WEIGHT_SKILL (uma vez por vaga, nao por ocorrencia — deterministico).
SKILL_PATTERNS: dict[str, str] = {
    "inventory management": r"\binventory management\b",
    "supplier relationships/management": r"\bsupplier (relationships?|management)\b",
    "process automation": r"\bprocess automation\b",
    "system integration": r"\bsystems? integration\b",
    "python": r"\bpython\b",
    "apis": r"\bapis?\b",
    "cloud": r"\bcloud\b",
    "data/reporting": r"\breporting\b",
    "continuous improvement": r"\bcontinuous improvement\b",
}
_SKILL_RE = {name: re.compile(p, re.IGNORECASE) for name, p in SKILL_PATTERNS.items()}

# ---------------------------------------------------------------------------
# Idioma (positivo; detectado no titulo+descricao)
# ---------------------------------------------------------------------------

# EN: evidencia de ingles (titulo+descricao) — FORTE e word-bounded
# (mesma lista exportada por app_intel; apenas re-exportada aqui).
LANG_EN_PATTERNS = [r"\benglish\b", r"\benglisch"]
_LANG_EN_RE = [re.compile(p, re.IGNORECASE) for p in LANG_EN_PATTERNS]


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Score:
    """Score total + breakdown por componente (para impressao/auditoria)."""

    total: float
    breakdown: dict[str, float]


# -----------------------------------------------------------------------
# Registry como lista de interesse (F3) — lazy singleton
# -----------------------------------------------------------------------

# Nomes canonicos do registry (casefold), computados UMA vez por processo
# a partir de ``CompanyRegistry().entries`` (nomes canonicos de coleta —
# a MESMA fonte de verdade da coleta; sem segunda lista).
_registry_names_cache: list[str] | None = None


def _registry_name_set() -> list[str]:
    """Nomes canonicos do registry, casefold (lazy singleton)."""
    global _registry_names_cache
    if _registry_names_cache is None:
        _registry_names_cache = [
            e.name.strip().casefold()
            for e in CompanyRegistry().entries
            if e.name and e.name.strip()
        ]
    return _registry_names_cache


def registry_interest(company: str | None) -> float:
    """Componente ``registry`` do score: ``WEIGHT_REGISTRY_INTEREST`` quando a
    empresa da vaga e do registry (lista de interesse), ``0.0`` caso contrario.

    Match: company casefold == nome canonico OU nome canonico SUBSTRING do
    company (casefold) — cobre os nomes legais do dataset ("Robert Bosch
    GmbH" vs registry "Bosch"). FN barato > FP caro (decisao F3 §4.2). NAO e
    filtro de elegibilidade — e um peso aditivo e deterministico.
    """
    if not company:
        return 0.0
    folded = str(company).strip().casefold()
    if not folded:
        return 0.0
    for name in _registry_name_set():
        if name and (name == folded or name in folded):
            return WEIGHT_REGISTRY_INTEREST
    return 0.0


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _mask_product_phrases(text: str) -> str:
    """Remove frases de produto (ex.: 'SAP Analytics Cloud') do texto.

    Fase 2 (pos-auditoria): termos de area dentro do NOME DO PRODUTO nao sao
    termos de area da funcao — nao devem pontuar. Ordem dos padroes importa
    (mais especifico primeiro: mascarar "SAP Analytics Cloud" inteiro antes
    de "Analytics Cloud", senao sobraria o "sap" fraco pontuando).
    """
    for pattern in _AREA_TITLE_PRODUCT_RE:
        text = pattern.sub(" ", text)
    return text


def _area_score(title: str, description: str | None) -> float:
    """Area: titulo com peso forte, descricao com peso fraco/zero.

    Reusa ``filters.area_score`` (mesmas listas de termos): a parte do titulo
    (``area_score(title, None)``) e a da descricao (diferenca ao incluir a
    descricao) entram com pesos independentes. Frases de produto
    (``AREA_TITLE_PRODUCT_PATTERNS``) sao mascaradas no TITULO antes da
    deteccao de area (ver ``_mask_product_phrases``).
    """
    title_area = area_score(_mask_product_phrases(title), None)
    desc_area = max(0.0, area_score(title, description) - area_score(title, None))
    return WEIGHT_AREA_TITLE * title_area + WEIGHT_AREA_DESC * desc_area


def _skills_score(description: str | None) -> float:
    """Competencias do perfil na descricao (+WEIGHT_SKILL por termo)."""
    if not description:
        return 0.0
    return sum(
        WEIGHT_SKILL for pattern in _SKILL_RE.values() if pattern.search(description)
    )


def _language_score(text: str) -> float:
    """Ingles (+WEIGHT_LANG_EN na evidencia) e alemao pela EXIGENCIA (Fase 6).

    ``app_intel.german_level`` classifica required/preferred/plus/none a
    partir do TEXTO (verbos de exigencia, qualificadores de intensidade,
    "von Vorteil"/preferred, negacao explicita). O idioma do anuncio nunca
    e requisito; mencao difusa (plus) fica NEUTRA.
    """
    score = 0.0
    if english_evidence(text):
        score += WEIGHT_LANG_EN
    de = german_level(text)
    if de is not None:
        if de.level == "required":
            score += PENALTY_LANG_DE_REQUIRED
        elif de.level == "preferred":
            score += PENALTY_LANG_DE_PREFERRED
    return score


def _location_score(d: dict[str, Any]) -> float:
    """DE explicito (ISO alpha-2) + Berlin. Remoto fica neutro (0)."""
    location = d.get("location") or ""
    iso = infer_country_iso(location=location, country_iso=d.get("country_iso"))
    score = 0.0
    if iso == "de":
        score += WEIGHT_DE_EXPLICIT
    if "berlin" in location.lower():
        score += WEIGHT_DE_CAPITAL
    return score


def _penalty_score(title_low: str, employment_type: str | None) -> float:
    """Penalidades de senioridade/manager/FULL_TIME.

    Senioridade e "manager" so valem quando NAO ha marcador forte de tipo no
    titulo (regra do milestone 2, mesma de ``filters.is_student_role``:
    "Praktikum ... Senior VP" e estagio e fica protegido). JMP/Trainee NAO
    sao marcadores: "Junior Managers Program" recebe a penalidade de manager
    como qualquer cargo sem marcador. FULL_TIME e suave e aplica sempre (-0.5
    — muitos Werkstudent/Praktikum vêm marcados FULL_TIME e nao podem zerar).
    """
    strong_type_in_title = _matches_any(STUDENT_TYPE_PATTERNS, title_low)
    penalty = 0.0
    if not strong_type_in_title:
        if _matches_any(SENIORITY_PATTERNS, title_low):
            penalty += PENALTY_SENIOR
        if MANAGER_PATTERN.search(title_low):
            penalty += PENALTY_MANAGER
    if (employment_type or "").strip().lower().replace("-", "_") == "full_time":
        penalty += PENALTY_FULL_TIME
    return penalty


def score_job(job: dict[str, Any] | Any) -> Score:
    """Score de compatibilidade de uma vaga (dict ou ``Job``) com o perfil.

    Funcao pura e deterministica: mesmos dados -> mesmo score. Aceita dict
    (o que o CLI le do JSON) ou modelo ``Job``.
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
    penalties = _penalty_score(title.lower(), d.get("employment_type"))
    registry = registry_interest(d.get("company"))

    breakdown = {
        "area": round(area, 2),
        "skills": round(skills, 2),
        "language": round(language, 2),
        "type": round(type_bonus, 2),
        "location": round(location, 2),
        "penalties": round(penalties, 2),
        "registry": round(registry, 2),
    }
    total = round(sum(breakdown.values()), 2)
    return Score(total=total, breakdown=breakdown)


def rank_jobs(jobs: list[dict[str, Any]] | list[Any]) -> list[dict[str, Any]]:
    """Adiciona ``score`` + ``score_breakdown`` e ordena desc (deterministico).

    Desempate: score desc -> titulo (casefold) -> empresa -> id. Retorna uma
    NOVA lista de dicts (nao muta a entrada).
    """
    out: list[dict[str, Any]] = []
    for item in jobs:
        d = item.to_dict() if hasattr(item, "to_dict") else dict(item)
        score = score_job(d)
        d["score"] = score.total
        d["score_breakdown"] = score.breakdown
        out.append(d)
    out.sort(
        key=lambda j: (
            -j["score"],
            str(j.get("title") or "").casefold(),
            str(j.get("company") or "").casefold(),
            str(j.get("id") or ""),
        )
    )
    return out
