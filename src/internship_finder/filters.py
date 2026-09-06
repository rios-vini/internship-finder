"""Filtros de utilidade: tipo (estudante/estagio), area-alvo e pais.

Funcoes puras (sem dependencia de CLI/modelos) usadas tanto pelo adapter
(flag ``Job.internship``) quanto pelo CLI (vagas eligible).

Regras de negocio (dono):
- Tipo aceito: Internship, Intern, Working Student, Student Worker, Student
  Internship, Industrial Internship, Praktikum, Werkstudent, iXp, estagio e
  equivalentes internacionais (gyakornok, staz, stazh, becario...).
  Graduate/absolvent NAO (perfil e de estudante atual, nao recem-formado).
- Programas de trainee EXCLUIDOS (regra do dono, pos-auditoria): Graduate
  Trainee, Management Trainee, Junior Managers Program e JMP. A exclusao do
  programa vence inclusive ``employment_type`` "trainee". "Trainee" generico
  deixou de ser marcador forte: sem outro marcador, a vaga nao passa.
  "Internship Trainee" / contexto estudantil continua aceito (o termo
  "internship"/"intern" ja cobre — sem regra extra).
- Tipos NAO compativeis com estagio/working student universitario EXCLUIDOS
  (regra do dono, Fase 1 das correcoes pos-auditoria): Duales Studium (e
  equivalentes: Dualer Student/Student:in, Dualer Master, Duale Hochschule,
  Dual Study, "Praktikum im Rahmen des Dualen Studiums"), Ausbildung /
  Berufsausbildung (aprendizagem profissional) e o equivalente EN
  Apprentice/Apprenticeship (P3 lote 1), Schul-/Schuelerpraktikum e
  estagios escolares ("Praktikum fuer Schueler:innen",
  Berufsorientierungspraktikum) e servico voluntario (FSJ/BFD). A exclusao do
  tipo vence QUALQUER marcador forte de tipo no titulo (ex.: "Industriepraktikum
  ... Dual Study Kooperation" e dual, nao estagio). Regra de TITULO apenas,
  generica (nenhum ATS especifico), checada ANTES da aceitacao por tipo (mesmo
  mecanismo da regra Trainee/JMP). PRESERVADOS: Internship/Intern, Praktikum
  (inclusive Pflichtpraktikum/Hochschulpraktikum — o \b inicial dos patterns de
  Schulpraktikum evita a composicao), Werkstudent, Working Student.
- Excluir posicoes permanentes/senior (senior, director, head, manager...),
  MAS um marcador forte de tipo no TITULO vence a senioridade: ex.
  "Praktikum Assistenz im Management des Senior Vice Presidents" e estagio.
  Tradeoff documentado: um titulo raro tipo "Internship Coordinator" (vaga
  full-time que coordena estagiarios) entraria como falso positivo —
  aceitavel no MVP.

- Area-alvo com heuristica de pontuacao (sem ML): titulo e mais forte que
  descricao; termo "relacionado" sozinho nao basta; "sap"/"erp"/"data"
  (fracos) so relevam combinados. Relevante se pontuacao >= AREA_MIN_SCORE.
- Pais configuravel: ISO alpha-2, "europe", "remote" ou "all" (sem filtro).
  ``country_iso`` e a fonte primaria; fallback para ``country`` e, por fim,
  para codigo ISO de 2 letras presente na ``location`` (ex.: SAP usa
  "Walldorf, DE, 69190" sem campo de pais). A logica de pais vive em
  ``countries`` (P2 #12); ``filters`` re-exporta os simbolos para
  compatibilidade total com quem importa daqui.
"""

from __future__ import annotations

import re
from typing import Any

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
    r"\bapprentices?\b",
    r"\bplacements?\b",
    # Nota: graduate/absolvent NAO entram (perfil e de estudante atual, nao
    # recem-formado); "SAP Associate" (full-time para graduados) fica de fora.
    # Trainee generico NAO e marcador (regra do dono pos-auditoria); os
    # programas Graduate/Management Trainee, Junior Managers Program e JMP
    # sao EXCLUIDOS em PROGRAM_EXCLUSION_PATTERNS.
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
]

# Programas de trainee/graduado EXCLUIDOS (regra do dono, pos-auditoria).
# Quando o TITULO traz o nome do programa, a vaga NAO e eligible — mesmo que
# ``employment_type`` seja "trainee": a exclusao do programa vence o
# STUDENT_EMPLOYMENT_TYPES. "Internship Trainee" nao bate aqui (sem regra
# extra: o termo "internship"/"intern" ja e marcador forte).
PROGRAM_EXCLUSION_PATTERNS = [
    r"\bgraduate trainee\b",
    r"\bmanagement trainee\b",
    r"\bjunior managers program\b",
    r"\bjmp\b",
]

# Tipos NAO compativeis com estagio/working student universitario EXCLUIDOS
# (regra do dono, Fase 1 das correcoes pos-auditoria pos-expansao). Padroes
# EXPLICITOS (nunca palavra solta generica — ex.: nao ha pattern de "praktikum"
# nem de "studium" sozinhos; "Schuelerpraktikum" e pego pela palavra composta e
# o \b inicial evita excluir "Hochschulpraktikum", que e estagio universitario
# VALIDO). Checados no TITULO, ANTES da aceitacao por tipo (como a regra
# Trainee/JMP): a exclusao vence qualquer marcador forte de tipo.
TYPE_EXCLUSION_PATTERNS = [
    # Duales Studium e equivalentes: programas de graduacao com estudo+trabalho
    # (inicio 2027, DHBW etc.), NAO estagio universitario. Cobre "Duales
    # Studium", "Dualen Studiums" (genitivo: "Praktikum im Rahmen des Dualen
    # Studiums"), "Duale Studien", "Dualer Studiengang", "Dual Study/Studies/
    # Study programme", "Ausbildungsintegriertes Duales Studium".
    r"\bdual\w* stud\w*\b",
    # "Dualer Student", "Dual Student", "Duale:r Student:in" (dois-pontos
    # genero-inclusivo), "Duale/r Bachelor/Master Student/in".
    r"\bdual\w*[:/]*\w* student",
    # "Duale Hochschule (BW Heidenheim...)" — estudar na DH, nao estagio.
    r"\bdual\w* hochschule",
    # "Dualer Master (M.Eng.)" — mestrado dual, nao estagio.
    r"\bdual\w* master",
    # Ausbildung / Berufsausbildung: aprendizagem profissional (Azubi), nao
    # estagio universitario. "Ausbildung zum/als ...", "Ausbildungsplatz",
    # "Berufsausbildung", "Schwerpunkt kaufmaennische Berufsausbildung".
    r"\b(berufs)?ausbildungs?",
    # EN equivalente (P3 lote 1): Apprentice/Apprenticeship (Azubi). O mesmo
    # perfil dos 'Ausbildung ...' DE (aprendizagem profissional, nao estagio
    # universitario). Como as regras DE, a exclusao vence QUALQUER marcador
    # forte de tipo no titulo — inclusive o proprio ``\bapprentices?\b`` de
    # STUDENT_TYPE_PATTERNS (a exclusao roda ANTES da aceitacao por tipo).
    # ``\bapprentice`` cobre Apprentice/Apprentices; ``\bapprenticeships?``
    # cobre a forma nominal (Apprenticeship/Apprenticeships).
    r"\bapprentice",
    r"\bapprenticeships?",
    # Estagios ESCOLARES (aluno do ensino medio, nao universidade):
    # "Schuelerpraktikum", "Schuelerpraktikant", "Schulpraktikum" (o \b inicial
    # NAO casa "Hochschulpraktikum" — estagio universitario valido),
    # "Praktikum fuer Schueler:innen" (tambem em composicao: "Herbstpraktikum
    # fuer Schueler:innen", "Betriebspraktikum fuer Schueler:innen" — sem \b
    # inicial: o "fuer Schueler" ja e inequivoco),
    # "Berufsorientierungspraktikum".
    r"\bsch(ü|ue)lerpraktikum",
    r"\bsch(ü|ue)lerpraktikant",
    r"\bschulpraktikum",
    r"\bschulpraktikant",
    r"praktikum f(ü|ue)r sch(ü|ue)ler",
    r"\bberufsorientierungspraktikum",
    # Servico voluntario (ano sabatico pos-escola, nao estagio): FSJ, BFD,
    # Freiwilliges Soziales/Oekologisches Jahr, Bundesfreiwilligendienst.
    r"\bfsj\b",
    r"\bbfd\b",
    r"\bfreiwilliges (soziales|(ö|oe)kologisches) jahr\b",
    r"\bbundesfreiwilligendienst",
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
# ``trainee`` FORA (P3 lote 1): trainee generico nao e marcador forte (regra do
# dono pos-auditoria) — um titulo so com et "trainee" nao passa; os programas
# Graduate/Management Trainee/JMP continuam excluidos por
# PROGRAM_EXCLUSION_PATTERNS.
STUDENT_EMPLOYMENT_TYPES = {"intern", "internship", "co-op"}


def _has_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def is_student_role(
    title: str,
    description: str | None = None,
    employment_type: str | None = None,
) -> bool:
    """Vaga e de estudante/estagio (heuristica, sem ML)?

    Programa/tipo excluido no TITULO (Graduate Trainee, Management Trainee,
    Junior Managers Program, JMP; Duales Studium, Ausbildung, Schul-/
    Schuelerpraktikum e equivalentes) => False ANTES de qualquer aceitacao —
    inclusive ``employment_type`` "trainee". "Trainee" generico deixou de
    ser marcador forte. Marcador forte de tipo no TITULO => estudante (mesmo
    que o titulo tenha "senior"/"manager": "Praktikum ... Senior VP" e
    estagio). Sem marcador no titulo, aceita-se marcador na descricao ou
    employment_type INTERN, mas ai exclusoes de senioridade no titulo valem
    ("Senior Manager" com descricao falando de estagio nao entra).
    """
    title_low = title.lower()
    if _has_any(PROGRAM_EXCLUSION_PATTERNS, title_low) or _has_any(
        TYPE_EXCLUSION_PATTERNS, title_low
    ):
        return False
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
    """Vaga adere as areas-alvo do dono? (heuristica, sem ML)."""
    return area_score(title, description) >= AREA_MIN_SCORE


# ---------------------------------------------------------------------------
# Pais / localizacao (re-export de ``countries`` — ver P2 #12)
# ---------------------------------------------------------------------------

from internship_finder.countries import (
    COUNTRY_CODES,
    infer_country_iso,
    is_remote,
    parse_country_spec,
    matches_country,
)



# ---------------------------------------------------------------------------
# Cascata de filtros (uso do CLI)
# ---------------------------------------------------------------------------


def select_eligible(
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
        # Fase 2 (Phenom/DHL): o filtro de pais re-infere o ISO via
        # ``infer_country_iso`` (ex.: Phenom nao expoe country_iso, mas a
        # location termina com o NOME do pais). Alem de filtrar, GRAVA de
        # volta o ISO canonico nos dicts selecionados (``country_iso`` e
        # ``country``) — a saida eligible carrega o pais (DHL volta a ter
        # 'de'), sem mudar a regra do filtro (mesmo predicado de sempre).
        enriched: list[dict[str, Any]] = []
        for j in step:
            if matches_country(
                j.get("country_iso"), j.get("location"), j.get("remote"), spec
            ):
                iso = infer_country_iso(
                    location=j.get("location"), country_iso=j.get("country_iso")
                )
                enriched.append({**j, "country_iso": iso, "country": iso})
        step = enriched
    counts["pais"] = len(step)
    return step, counts
