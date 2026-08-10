"""Filtros de utilidade: tipo (estudante/estagio), area-alvo e pais.

Funcoes puras (sem dependencia de CLI/modelos) usadas tanto pelo adapter
(flag ``Job.internship``) quanto pelo CLI (vagas candidataveis).

Regras de negocio (dono):
- Tipo aceito: Internship, Intern, Working Student, Student Worker, Student
  Internship, Industrial Internship, Praktikum, Werkstudent, iXp, estagio e
  equivalentes internacionais (gyakornok, staz, stazh, becario...). Trainee e
  "Junior Managers Program" (Bosch) entram; graduate/absolvent NAO (perfil e
  de estudante atual, nao recem-formado).
- Excluir posicoes permanentes/senior (senior, director, head, manager...),
  MAS um marcador forte de tipo no TITULO vence a senioridade: ex.
  "Praktikum Assistenz im Management des Senior Vice Presidents" e estagio;
  "Junior Managers Program - Software & KI" e trainee. Tradeoff documentado:
  um titulo raro tipo "Internship Coordinator" (vaga full-time que coordena
  estagiarios) entraria como falso positivo — aceitavel no MVP.

- Area-alvo com heuristica de pontuacao (sem ML): titulo e mais forte que
  descricao; termo "relacionado" sozinho nao basta; "sap"/"erp"/"data"
  (fracos) so relevam combinados. Relevante se pontuacao >= AREA_MIN_SCORE.
- Pais configuravel: ISO alpha-2, "europe", "remote" ou "all" (sem filtro).
  ``country_iso`` e a fonte primaria; fallback para ``country`` e, por fim,
  para codigo ISO de 2 letras presente na ``location`` (ex.: SAP usa
  "Walldorf, DE, 69190" sem campo de pais).
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Tipo de vaga (estudante/estagio)
# ---------------------------------------------------------------------------

# Marcadores FORTES de vaga de estudante/estagio. Quando presentes no titulo,
# vencem as exclusoes de senioridade (ver ``is_student_role``). Cobre EN, DE,
# PT-BR, FR, ES, IT, HU, PL, RU, CZ, TR.
STUDENT_TYPE_PATTERNS = [
    r"\binterns?\b",
    r"\binternships?\b",
    r"\bworking student",  # "Working Student", "Working Students"
    r"\bstudent worker",
    r"\bstudent internship",
    r"\bindustrial internship",
    r"\bco[- ]?ops?\b",
    r"\btrainees?\b",
    r"\bapprentices?\b",
    r"\bplacements?\b",
    # Nota: graduate/absolvent NAO entram (perfil e de estudante atual, nao
    # recem-formado); "SAP Associate" (full-time para graduados) fica de fora.
    # DE: Werkstudent, Praktikum, iXp, duales Studium, HiWi.
    r"\bwerkstudent",  # sem fechamento: pega Werkstudentin/Werkstudenten
    r"\bstudentische hilfskraft",
    r"praktikum",  # pega Praktikum/Praktikumsplatz/Praktikumsthemen
    r"\bpraktikant",
    r"\bixp\b",
    r"\bduales studium",
    # BR: estagio/estagiario.
    r"\best[áa]gio\b",
    r"\bestagi[áa]ri[oa]s?\b",
    # FR: stagiaire.
    r"\bstagiaires?\b",
    # ES: practicas / becario.
    r"\bpr[áa]cticas?\b",
    r"\bbecari[oa]s?\b",
    # IT: tirocinio.
    r"\btirocinio\b",
    # HU: gyakornok / gyakornoki (intern).
    r"\bgyakornok",
    # PL: staz / stazysta (intern).
    r"\bsta[zż]",
    # RU: stazh (intern) — cobre стажер/стажёр/стажировка.
    r"стаж",
    # CZ: staz / praxe (internship).
    r"\bpráxe\b",
    # TR: stajyer (intern).
    r"\bstajyer",
    # Bosch: Junior Managers Program = trainee (entra por regra do dono).
    r"\bjunior managers program\b",
    r"\bjmp\b",
    r"\bmanagement trainee\b",
]

# Exclusoes de senioridade/posicao permanente. So valem quando NAO ha marcador
# forte de tipo no titulo (ver ``is_student_role``).
SENIORITY_PATTERNS = [
    r"\bsenior\b",
    r"\bsr\.?\b",
    r"\bprincipal\b",
    r"\bstaff\b",
    r"\bhead of\b",
    r"\bchief\b",
    r"\bdirector",
    r"\bexpert",
    r"\blead\b",
    r"\bvp\b",
]

MANAGER_PATTERN = re.compile(r"\bmanage", re.IGNORECASE)

# employment_type que por si so indica vaga de estudante. PART_TIME nao basta:
# ha clerk/posicoes permanentes part-time que nao sao vagas de estudante.
STUDENT_EMPLOYMENT_TYPES = {"intern", "internship", "trainee", "co-op"}


def _has_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def is_student_role(
    title: str,
    description: str | None = None,
    employment_type: str | None = None,
) -> bool:
    """Vaga e de estudante/estagio (heuristica, sem ML)?

    Marcador forte de tipo no TITULO => estudante (mesmo que o titulo tenha
    "senior"/"manager": "Praktikum ... Senior VP" e estagio; "Junior Managers
    Program" e trainee). Sem marcador no titulo, aceita-se marcador na
    descricao ou employment_type INTERN, mas ai exclusoes de senioridade no
    titulo valem ("Senior Manager" com descricao falando de estagio nao entra).
    """
    title_low = title.lower()
    type_in_title = _has_any(STUDENT_TYPE_PATTERNS, title_low)

    text = f"{title} {description or ''}".lower()
    type_anywhere = type_in_title or _has_any(STUDENT_TYPE_PATTERNS, text)
    et = (employment_type or "").strip().lower().replace("-", "_")
    if et in STUDENT_EMPLOYMENT_TYPES:
        type_anywhere = True

    if not type_anywhere:
        return False
    if type_in_title:
        return True
    # Tipo so veio da descricao/employment_type: senioridade no titulo derruba.
    if _has_any(SENIORITY_PATTERNS, title_low) or MANAGER_PATTERN.search(title_low):
        return False
    return True


# ---------------------------------------------------------------------------
# Area-alvo (Supply Chain, Procurement, BI, Analytics, Automacao...)
# ---------------------------------------------------------------------------

# Termos de area, em tres niveis. Pontuacao no TITULO / na DESCRICAO:
#   PRIMARY  -> 3 / 1      (as areas-alvo do dono)
#   RELATED  -> 2 / 0.5    (areas relacionadas do dono)
#   WEAK     -> 1 / 0.5    (sinais genericos: "data", "sap", "automation"...
#                           so relevam combinados com outro sinal)
AREA_PRIMARY = [
    r"\bsupply[ -]?chain\b",
    r"\bprocurement\b",
    r"\bpurchasing\b",
    r"\bpurchase\b",
    r"\beinkauf",  # DE: purchasing
    r"\bbeschaffung",  # DE: procurement/sourcing
    r"\bcompras\b",  # BR
    r"\bsuprimentos\b",  # BR
    r"\bbusiness intelligence\b",
    r"\bbi\b",  # "BI Developer"
    r"\bdata[ &]+analytics\b",
    r"\banalytics\b",
    r"\bprocess automation\b",
    r"\bprocess excellence\b",
    r"\brpa\b",
    r"\brobotic process automation\b",
]

AREA_RELATED = [
    r"\boperations\b",
    r"\boperations excellence\b",
    r"\bsupply chain planning\b",
    r"\blogist",
    r"\bsourcing\b",
    r"\bstrategic procurement\b",
    r"\bpurchasing operations\b",
    r"\bdigital operations\b",
    r"\bbusiness analytics\b",
    r"\bcontinuous improvement\b",
    r"\bprocess improvement\b",
    r"\bprozessoptimierung",  # DE: process improvement
    r"\bprocesos\b",  # ES/PT
]

AREA_WEAK = [
    r"\bdata\b",
    r"\breporting\b",
    r"\berp\b",
    r"\bsap\b",
    r"\bautomation\b",
    r"\bautomatisierung",  # DE
    r"\bdigital transformation\b",
    r"\banalyst\b",
    r"\bprozessmanagement",  # DE
    r"\bprocess management\b",
]

AREA_TITLE_WEIGHTS = {"primary": 3.0, "related": 2.0, "weak": 1.0}
AREA_DESC_WEIGHTS = {"primary": 1.0, "related": 0.5, "weak": 0.5}
AREA_MIN_SCORE = 1.5

_PATTERNS: dict[str, list[re.Pattern]] = {
    level: [re.compile(p, re.IGNORECASE) for p in pats]
    for level, pats in (
        ("primary", AREA_PRIMARY),
        ("related", AREA_RELATED),
        ("weak", AREA_WEAK),
    )
}


def area_score(title: str, description: str | None = None) -> float:
    """Pontuacao de aderencia a area-alvo (titulo pesa mais que descricao)."""
    score = 0.0
    for level, patterns in _PATTERNS.items():
        if any(p.search(title) for p in patterns):
            score += AREA_TITLE_WEIGHTS[level]
        if description and any(p.search(description) for p in patterns):
            score += AREA_DESC_WEIGHTS[level]
    return score


def matches_area(title: str, description: str | None = None) -> bool:
    """Vaga e relevante para as areas-alvo do dono? (heuristica, sem ML)."""
    return area_score(title, description) >= AREA_MIN_SCORE


# ---------------------------------------------------------------------------
# Pais / localizacao
# ---------------------------------------------------------------------------

# ISO 3166-1 alpha-2 (codigos validos para o fallback por ``location``).
# Minusculas: todas as comparacoes usam ``.lower()``.
COUNTRY_CODES = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ
    BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR
    CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU
    ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ
    LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
    MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF
    PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI
    SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR
    TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """.lower().split()
)

# "Europa" para o dono: UE/EEE + CH + UK + Balcas (paises onde estagio/estudo
# em alemao e viavel ou comum no contexto). RU/BY ficam de fora. Minusculas,
# como COUNTRY_CODES.
EUROPE_COUNTRIES = frozenset(
    """
    AD AL AT BA BE BG BY CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LI LT
    LU LV MC MD ME MK MT NL NO PL PT RO RS SE SI SK SM UA UK VA
    """.lower().split()
)


def infer_country_iso(
    location: str | None = None,
    country: str | None = None,
    country_iso: str | None = None,
) -> str | None:
    """ISO alpha-2 do pais da vaga, com fallbacks.

    1. ``country_iso`` / ``country`` (normalizados).
    2. Ultimo codigo de 2 letras valido em ``location`` (ex.: SAP grava
       "Walldorf, DE, 69190" sem campo de pais; estados US como "GA"/"PA"
       nao sao codigos ISO e sao ignorados).
    """
    for value in (country_iso, country):
        if value:
            code = str(value).strip().lower()
            if code in COUNTRY_CODES:
                return code
    if location:
        matches = re.findall(r"(?:^|[\s,]+)([A-Za-z]{2})(?=$|[\s,.;:])", location)
        for token in reversed(matches):
            code = token.lower()
            if code in COUNTRY_CODES:
                return code
    return None


def is_remote(location: str | None, remote: bool | None) -> bool:
    """Vaga remota? (campo ``remote`` ou "remote"/"home office" na localizacao)."""
    if remote:
        return True
    loc = (location or "").lower()
    return "remote" in loc or "home office" in loc or "homeoffice" in loc


def parse_country_spec(spec: str) -> frozenset[str] | str | None:
    """Normaliza ``--country`` para uma especificacao de filtro.

    - "all"/"world"/"any" -> None (sem filtro de pais)
    - "remote"            -> "remote" (vaga remota)
    - "europe"            -> conjunto EUROPE_COUNTRIES
    - lista ISO ("de,at,ch") -> conjunto de codigos
    """
    s = (spec or "").strip().lower()
    if not s or s in {"all", "world", "any"}:
        return None
    if s == "remote":
        return "remote"
    if s == "europe":
        return EUROPE_COUNTRIES
    codes = {c.strip() for c in s.split(",") if c.strip()}
    return frozenset(codes)


def matches_country(
    country_iso: str | None,
    location: str | None,
    remote: bool | None,
    spec: frozenset[str] | str | None,
) -> bool:
    """Vaga atende a especificacao de pais/localizacao? (spec = parse_country_spec)"""
    if spec is None:
        return True
    if isinstance(spec, str):  # "remote"
        return is_remote(location, remote)
    iso = infer_country_iso(location=location, country_iso=country_iso)
    return iso is not None and iso in spec


# ---------------------------------------------------------------------------
# Cascata de filtros (uso do CLI)
# ---------------------------------------------------------------------------


def select_relevant(
    jobs: list[dict],
    *,
    student: bool = True,
    area: bool = True,
    country: str = "de",
) -> tuple[list[dict], dict[str, int]]:
    """Aplica os filtros de utilidade em cascata: tipo -> area -> pais.

    Retorna ``(selecionados, contagens)`` com o total acumulado a cada etapa:
    ``{"total", "tipo", "area", "pais"}`` (as contagens refletem o que cada
    etapa manteve). ``jobs`` sao dicts (o que o CLI le do JSON) — sem
    dependencia do modelo ``Job``. Filtro desligado mantem a contagem da etapa
    anterior (ex.: ``country="all"`` -> ``pais == area``).
    """
    spec = parse_country_spec(country)
    counts: dict[str, int] = {"total": len(jobs)}
    step = list(jobs)
    if student:
        step = [
            j
            for j in step
            if is_student_role(
                j.get("title", ""), j.get("description"), j.get("employment_type")
            )
        ]
    counts["tipo"] = len(step)
    if area:
        step = [
            j
            for j in step
            if matches_area(j.get("title", ""), j.get("description"))
        ]
    counts["area"] = len(step)
    if spec is not None:
        step = [
            j
            for j in step
            if matches_country(j.get("country_iso"), j.get("location"), j.get("remote"), spec)
        ]
    counts["pais"] = len(step)
    return step, counts
