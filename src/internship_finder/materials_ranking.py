"""Ranking por perfil Materials Engineering — Fase 4 (segundo perfil).

Classifica as MESMAS vagas elegiveis do pipeline por relevancia para um
estudante de Engenharia de Materiais (Materials Science, Metallurgy, Polymer,
Composites, Ceramics, Metals, Surface Engineering, Corrosion, Failure
Analysis, Materials Testing, Laboratory, Manufacturing, Production, Process
Engineering, Quality/R&D com contexto tecnico).

Principios (Fase 4 — enunciado do dono):

- **Nao altera a elegibilidade**: opera SOMENTE sobre o conjunto ja elegivel
  (``data/eligible_jobs.json`` — mesmas vagas, mesma dedup, mesmos filtros).
- **Score independente**: ``materials_score``/``materials_breakdown`` sao
  campos NOVOS, adicionados SEM tocar ``score``/``score_breakdown`` do perfil
  principal (nunca ``final = business + materials``). Os dois rankings
  coexistem e cada um tem sua propria ordem.
- **Deterministico, reproduzivel, barato**: regex sobre o texto original da
  vaga (titulo + descricao), sem LLM/embeddings/externo.
- **Explicavel**: o breakdown usa somente componentes implementados
  (materiais / adjacente / contexto / tipo / local / penalidades).

Composicao do score (constantes de modulo)::

    materials = soma de termos do NUCLEO no TITULO (2.5 por termo unico)
                + 1.0 fixo se a DESCRICAO traz >= 1 termo do nucleo
    adjacent  = idem, termos ADJACENTES (1.25 por termo unico no titulo;
                + 0.5 fixo se a descricao tem >= 1 termo adjacente)
    context   = qualidade/P&D/lab/teste: 0.75 por termo unico no TITULO
                (+ 0.5 fixo na descricao) — GATED: so conta quando o TITULO
                ja tem >= 1 termo de nucleo OU adjacente (sem o gate,
                "Sales Development" ou "Quality Engineer" de qualquer setor
                viraria vaga de materiais)
    type      = marcador forte de tipo no titulo (reusa filters) +1.0
    location  = DE explicito +1.0 / Berlin +0.5 (mesmo conceito do principal)
    penalties = funcao NAO-materiais no TITULO: compras/SCM -1.5 (o perfil
                comercial OPOSTO); logistica/vendas/financas/RH/juridico/
                software/administrativo -1.0 (cada CATEGORIA conta uma vez;
                descricao NAO penaliza — boilerplate "MS Office" e areas
                organizacionais citando "Einkauf" derrubariam vagas tecnicas)

Calibracao (validada no conjunto real de 18/09, 476 eligible — Fase 4):
a descricao conta NO MAXIMO UMA VEZ por bloco porque templates genericos
(e.g. Fraunhofer/SAP) citam termos tecnicos em vagas de outras funcoes e
inflariam o score (medido: 10,5 pts so de descricao numa vaga). O TITULO e
a estrutura da vaga; a descricao apenas CORROBORA. Regra de ouro do
enunciado: uma vaga contendo apenas "student"/"engineering"/"manufacturing"/
"internship" NAO recebe relevancia alta; os termos do nucleo no TITULO pesam
muito mais. Termos de funcao de negocio (Einkauf, Procurement, Supply
Chain...) sao penalizados — o perfil e tecnico — mas jamais zeram uma vaga
com sinal real de materiais (o nucleo vence a penalidade).
"""

from __future__ import annotations

import re
from typing import Any

from internship_finder.filters import STUDENT_TYPE_PATTERNS
from internship_finder.ranking import Score

# ---------------------------------------------------------------------------
# Pesos (constantes de modulo — ajuste facil e documentado)
# ---------------------------------------------------------------------------

# NUCLEO de materiais: cada termo unico no TITULO; a descricao so corrobora
# (1.0 fixo, no maximo uma vez) — ver docstring (calibracao real 18/09).
WEIGHT_MATERIALS_TITLE = 2.5
WEIGHT_MATERIALS_DESC = 1.0
# ADJACENTES (manufacturing, process eng, battery...): mesmo padrao, menor.
WEIGHT_ADJACENT_TITLE = 1.25
WEIGHT_ADJACENT_DESC = 0.5
# CONTEXTO (qualidade/P&D/lab/teste) — condicional: so conta quando o TITULO
# ja tem >= 1 termo de nucleo OU adjacente (gate de contexto tecnico).
WEIGHT_CONTEXT_TITLE = 0.75
WEIGHT_CONTEXT_DESC = 0.5
# Marcador forte de tipo de vaga no TITULO (reusa STUDENT_TYPE_PATTERNS).
WEIGHT_TYPE_TITLE = 1.0
# Localizacao: DE explicito / Berlin (mesmo conceito do perfil principal).
WEIGHT_DE_EXPLICIT = 1.0
WEIGHT_DE_CAPITAL = 0.5
# Penalidades por funcao NAO-materiais. Compras/SCM e o PERFIL OPOSTO
# (negocio) e pesa mais; as demais funcoes sao menos antagonicas.
PENALTY_PROCUREMENT = -1.5
PENALTY_OTHER_FUNCTION = -1.0

# ---------------------------------------------------------------------------
# Termos do NUCLEO de materiais (fortes; cada termo unico no titulo conta)
# ---------------------------------------------------------------------------
# Chave = rotulo do termo (auditoria); valor = regex. Regras de construcao:
# - NUNCA a palavra solta "material(s)": "Materialwirtschaft" e procurement
#   de materiais e "Materialfluss" e logistica — so COMPOSTOS e frases
#   explicitas de materiais.
# - Germanismos compostos entram por prefixo (werkstoff/kunststoff/...).
MATERIALS_TERMS: dict[str, str] = {
    # EN — frases explicitas de ciencias/engenharia de materiais.
    "materials engineering/science": (
        r"\bmaterials? (engineering|science|scientist|technology|technolog"
        r"ies?|mechanics|chemistry|chemist)\b"
    ),
    "materials testing/characterization": (
        r"\bmaterials? (testing|characterization|analysis|analytics)\b"
    ),
    # DE — compostos canonicos (nunca "material" solto).
    "materialwissenschaft": r"materialwissenschaft\w*",
    "materialtechnik": r"materialtechnik\w*",
    "materialkunde": r"materialkunde\w*",
    "materialprüfung": r"materialpr(ü|ue)fung\w*",
    "werkstoff": r"werkstoff\w*",  # Werkstoff, Werkstofftechnik, -prüfung
    # Metalurgia e metais.
    "metallurgy": r"metallurg\w*",
    "metals": r"\bmetals?\b",
    "steel": r"\bsteel\b",
    "aluminium": r"alumini\w*",  # aluminium / aluminum
    "alloys": r"alloy\w*",
    # Polimeros e plasticos.
    "polymers": r"polymer\w*",
    "plastics": r"\bplastics?\b",
    "kunststoff": r"kunststoff\w*",
    "injection molding": r"injection mold\w*",
    "spritzguss": r"spritzguss\w*",
    # Compositos e ceramicas.
    "composites": r"composite\w*",
    "ceramics": r"ceramic\w*",
    "keramik": r"keramik\w*",
    # Corrosao.
    "corrosion": r"corrosion\w*",
    "korrosion": r"korrosion\w*",
    # Engenharia de superficie / recobrimentos.
    "surface engineering": (
        r"surface (engineering|technology|treatment\w*|finishing|modification)"
    ),
    "oberflächentechnik": r"oberfl(ä|ae)chentechnik",
    "coatings": r"\bcoatings?\b",
    "beschichtung": r"beschichtung\w*",
    # Analise de falhas e ensaios nao destrutivos.
    "failure analysis": r"failure analysis",
    "schadensanalyse": r"schadensanalyse\w*",
    "ndt": r"\bndt\b|non[- ]destructive",
}
_MATERIALS_RE = {k: re.compile(v, re.IGNORECASE) for k, v in MATERIALS_TERMS.items()}

# ---------------------------------------------------------------------------
# Termos ADJACENTES (areas industriais diretamente relacionadas — peso menor)
# ---------------------------------------------------------------------------
ADJACENT_TERMS: dict[str, str] = {
    "manufacturing": r"\bmanufactur\w*|fertigung\w*",
    "production": r"\bproduction\b|produktion\w*",
    "process engineering": r"process engineer\w*",
    "prozesstechnik": r"prozesstechnik\w*",
    "verfahrenstechnik": r"verfahrenstechnik\w*",  # DE: process/chemical eng.
    "mechanical": r"\bmechanical\b|maschinen\w*",
    "industrial engineering": r"industrial engineering",
    "battery": r"batter\w*",  # battery/Batterie/Batteriezelle(-fertigung)
    "electrolysis": r"elektrolyse\w*|electrolyt\w*|electrolyz\w*",
    "fuel cell": r"fuel cell\b|brennstoffzelle\w*",
    "semiconductor": r"semiconductor\w*|halbleiter\w*",
    "chemistry": r"chem\w*",  # chemical/Chemie/"chemische Prozesse"
    "additive manufacturing": r"additive manufacturing|3[- ]?d print\w*",
    "anlagenbau": r"anlagenbau\w*",  # DE: plant/process engineering
    "laboratory": r"laborator\w*|\blabor\b|laborant\w*",
    "laser": r"laser\w*",
    "presswerk": r"presswerk\w*",  # DE: stamping plant (metal forming)
    "catalysts": r"katalysator\w*|catalyst\w*",
    "welding": r"\bweld\w*|schwei(ß|ss)\w*",
}
_ADJACENT_RE = {k: re.compile(v, re.IGNORECASE) for k, v in ADJACENT_TERMS.items()}

# ---------------------------------------------------------------------------
# Termos de CONTEXTO (condicionais): so contam com contextoTECNICO no TITULO
# (>= 1 termo de nucleo OU adjacente). Implementa a regra do enunciado:
# "Quality Engineering / R&D quando houver forte relacao tecnica com
# materiais" — sem isso, "Quality Engineer" de qualquer setor (banco, SAP...)
# viraria vaga de materiais.
# ---------------------------------------------------------------------------
CONTEXT_TERMS: dict[str, str] = {
    "quality": r"\bqualit\w*",  # Quality/Qualität (qualidade tecnica)
    "rd": r"\br&d\b|research\w*|forsch\w*",  # P&D / research / Forschung
    "development": r"\bdevelopment\b|entwickl\w*",  # development/Entwicklung
    "testing": r"\btest\w*|versuch\w*|pr(ü|ue)f\w*",  # teste/Versuch/Prüfung
    "characterization": r"characteriz\w*",  # so isolada; composta ja e forte
}
_CONTEXT_RE = {k: re.compile(v, re.IGNORECASE) for k, v in CONTEXT_TERMS.items()}

# ---------------------------------------------------------------------------
# Penalidades (sinais de funcao NAO-materiais — negativos)
# ---------------------------------------------------------------------------
# Compras/SCM: o perfil comercial OPOSTO ao tecnico.
PROCUREMENT_PATTERNS = [
    r"\beinkauf\w*",
    r"\bpurchas\w*",
    r"\bprocurement\w*",
    r"\bsupplier\w*",
    r"\bsourcing\w*",
    r"\bbeschaffung\w*",
    r"\bsupply chain\b",
]
# Demais funcoes nao-materiais (peso menor).
OTHER_FUNCTION_PATTERNS = [
    # Logistica / transporte.
    r"\blogistik\w*", r"\blogistics\w*", r"\bwarehouse\w*", r"\blager\w*",
    r"\binventory\b", r"\btransport\w*",
    # Vendas / marketing / e-commerce.
    r"\bsales\b", r"\bmarketing\w*", r"\bvertrieb\w*", r"\bkey account\w*",
    r"\bcustomer\b", r"\bcommercial\w*", r"\be-?commerce\b", r"\bmarketplace",
    # Financas.
    r"\bfinanc\w*", r"\bcontrolling\b", r"\baccounting\b", r"\btreasury\b",
    r"\baudit\b", r"\btax\b", r"\bbudget\w*", r"\bcosting\w*",
    # RH / pessoas / recrutamento.
    r"\bhuman resources\b", r"\bpeople\b", r"\bhr\b", r"\brecruit\w*",
    r"\bpersonal\w*", r"\btalent\w*",
    # Juridico / compliance / risco.
    r"\blegal\b", r"\bcompliance\b", r"\brisk\b", r"\bgovernance\b",
    r"\bdatenschutz",
    # Software / TI.
    r"\bsoftware\w*", r"\bdeveloper\w*", r"\bprogramm\w*", r"\bdevops\b",
    r"\bfrontend\w*", r"\bbackend\w*", r"\bcloud\b", r"\bit\b",
    # Administrativo / escritorio.
    r"\badministration\w*", r"\bsekretariat\w*", r"\bverwaltung\w*",
    r"\boffice\b",
]
_PROCUREMENT_RE = [re.compile(p, re.IGNORECASE) for p in PROCUREMENT_PATTERNS]
_OTHER_FUNCTION_RE = [re.compile(p, re.IGNORECASE) for p in OTHER_FUNCTION_PATTERNS]


def _title_terms(terms: dict[str, re.Pattern], title: str) -> int:
    """Numero de TERMOS UNICOS que aparecem no TITULO."""
    return sum(1 for rx in terms.values() if rx.search(title))


def _has_desc_term(terms: dict[str, re.Pattern], description: str | None) -> bool:
    """A DESCRICAO traz >= 1 termo do bloco (corroboracao, no maximo uma vez)."""
    return any(rx.search(description or "") for rx in terms.values())


def _block_score(
    terms: dict[str, re.Pattern],
    title: str,
    description: str | None,
    *,
    weight_title: float,
    weight_desc: float,
) -> float:
    """Score de um bloco: termos unicos no titulo + 1 corroboracao da descricao."""
    return (
        weight_title * _title_terms(terms, title)
        + (weight_desc if _has_desc_term(terms, description) else 0.0)
    )


def _type_score(title: str) -> float:
    """Marcador forte de tipo de vaga no titulo (mesma regra do principal)."""
    return (
        WEIGHT_TYPE_TITLE
        if any(re.search(p, title, re.IGNORECASE) for p in STUDENT_TYPE_PATTERNS)
        else 0.0
    )


def _location_score(d: dict[str, Any]) -> float:
    """DE explicito (ISO) + Berlin. Remoto fica neutro (mesmo conceito)."""
    from internship_finder.countries import infer_country_iso

    location = d.get("location") or ""
    iso = infer_country_iso(location=location, country_iso=d.get("country_iso"))
    score = 0.0
    if iso == "de":
        score += WEIGHT_DE_EXPLICIT
    if "berlin" in location.lower():
        score += WEIGHT_DE_CAPITAL
    return score


def _penalty_score(title: str) -> float:
    """Penalidades por funcao NAO-materiais — SOMENTE no TITULO.

    Compras/SCM (o nucleo do perfil comercial) pesam mais; as demais funcoes
    pesam menos. Cada CATEGORIA conta uma vez (nunca por termo — senao
    "Einkauf und Lieferantennetzwerk" penalizaria dobrado). A FUNCAO de uma
    vaga esta no titulo: a descricao traz ruido de boilerplate (requisitos
    "MS Office", areas da organizacao citando "Einkauf") que penalizaria
    vagas tecnicas reais — medido no conjunto 18/09 (vaga de desenvolvimento
    de celula de bateria penalizada por mencao da area organizacional).
    """
    penalty = 0.0
    if any(rx.search(title) for rx in _PROCUREMENT_RE):
        penalty += PENALTY_PROCUREMENT
    if any(rx.search(title) for rx in _OTHER_FUNCTION_RE):
        penalty += PENALTY_OTHER_FUNCTION
    return penalty


def materials_score_job(job: dict[str, Any] | Any) -> Score:
    """Score de relevancia para Materials Engineering (dict ou ``Job``).

    Funcao pura e deterministica. Componentes NOVOS — nunca toca
    ``score``/``score_breakdown`` (perfil principal permanece intacto).
    """
    d = job.to_dict() if hasattr(job, "to_dict") else job
    title = str(d.get("title") or "")
    description = d.get("description") or ""

    # Gate de contexto tecnico: o TITULO precisa ter >= 1 termo de nucleo ou
    # adjacente — senao "Qualität"/"R&D"/"development" soltos nao pontuam.
    technical = (
        _title_terms(_MATERIALS_RE, title) > 0
        or _title_terms(_ADJACENT_RE, title) > 0
    )

    materials = _block_score(
        _MATERIALS_RE, title, description,
        weight_title=WEIGHT_MATERIALS_TITLE, weight_desc=WEIGHT_MATERIALS_DESC,
    )
    adjacent = _block_score(
        _ADJACENT_RE, title, description,
        weight_title=WEIGHT_ADJACENT_TITLE, weight_desc=WEIGHT_ADJACENT_DESC,
    )
    context = (
        _block_score(
            _CONTEXT_RE, title, description,
            weight_title=WEIGHT_CONTEXT_TITLE, weight_desc=WEIGHT_CONTEXT_DESC,
        )
        if technical else 0.0
    )
    type_bonus = _type_score(title)
    location = _location_score(d)
    penalties = _penalty_score(title)

    breakdown = {
        "materials": round(materials, 2),
        "adjacent": round(adjacent, 2),
        "context": round(context, 2),
        "type": round(type_bonus, 2),
        "location": round(location, 2),
        "penalties": round(penalties, 2),
    }
    total = round(sum(breakdown.values()), 2)
    return Score(total=total, breakdown=breakdown)


def rank_materials_jobs(jobs: list[dict[str, Any]] | list[Any]) -> list[dict[str, Any]]:
    """Adiciona ``materials_score`` + ``materials_breakdown`` e ordena desc.

    Ranking INDEPENDENTE do perfil principal: mesma entrada (as vagas
    elegiveis), composicao propria de score, posicoes proprias. Desempate
    deterministico (score desc -> titulo -> empresa -> id — mesmo criterio do
    principal). Retorna NOVA lista; a entrada nao e mutada e o ``score`` do
    principal nao e alterado.
    """
    out: list[dict[str, Any]] = []
    for item in jobs:
        d = item.to_dict() if hasattr(item, "to_dict") else dict(item)
        score = materials_score_job(d)
        d["materials_score"] = score.total
        d["materials_breakdown"] = score.breakdown
        out.append(d)
    out.sort(
        key=lambda j: (
            -j["materials_score"],
            str(j.get("title") or "").casefold(),
            str(j.get("company") or "").casefold(),
            str(j.get("id") or ""),
        )
    )
    return out