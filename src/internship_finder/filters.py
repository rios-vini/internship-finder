"""Filtros de utilidade: tipo (estudante/estagio), area-alvo e pais.

Funcoes puras (sem dependencia de CLI/modelos) usadas tanto pelo adapter
(flag ``Job.internship``) quanto pelo CLI (vagas eligible).

Regras de negocio (dono):
- Tipo aceito: Internship, Intern, Working Student, Student Worker, Student
  Internship, Industrial Internship, Praktikum, Werkstudent, iXp, estagio e
  equivalentes internacionais (gyakornok, staz, stazh, becario...). Teses
  academicas entram como posicao estudantil (Abschlussarbeit,
  Bachelor-/Masterarbeit, Semester-/Studienarbeit, Bachelor's/Master's
  thesis — regra do dono, pos-auditoria 15/09).
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
  Dual Study, "Praktikum im Rahmen des Dualen Studiums"), Studium mit
  vertiefter Praxis (pos-auditoria 15/09), programas de graduacao com grau no
  titulo (Bachelor of Science/Arts/Engineering, Bachelor ... im Praxisverbund
  — pos-auditoria 15/09; Bachelorarbeit/Bachelor's thesis sao teses VALIDAS e
  nao casam o "bachelor of"), Ausbildung /
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
  Vocabulario de analise de dados CONTROLADO (pos-auditoria 15/09): "data
  science", "data analysis", "datenanalyse" e "business analyst" em RELATED
  — so os compostos; "data"/"analyst"/"analysis"/"business" soltos
  continuam de fora.
- Pais configuravel: ISO alpha-2, "europe", "remote" ou "all" (sem filtro).
  ``country_iso`` e a fonte primaria; fallback para ``country`` e, por fim,
  para codigo ISO de 2 letras presente na ``location`` (ex.: SAP usa
  "Walldorf, DE, 69190" sem campo de pais). A logica de pais vive em
  ``countries`` (P2 #12); ``filters`` re-exporta os simbolos para
  compatibilidade total com quem importa daqui.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# ---------------------------------------------------------------------------
# Tipo de vaga (estudante/estagio)
# ---------------------------------------------------------------------------

# Marcadores FORTES de vaga de estudante/estagio. Quando presentes no titulo,
# vencem as exclusoes de senioridade (ver ``is_student_role``). Cobre EN, DE,
# PT-BR, FR, ES, IT, HU, PL, RU, CZ, TR.
STUDENT_TYPE_PATTERNS = [
    r"\binterns?\b(?!\.)",  # F37: "intern." abreviação (internacional etc.) não é marcador
    r"\binternships?\b",
    r"\bworking student",  # "Working Student", "Working Students"
    r"\bstudent worker",
    r"\bstudent internship",
    r"\bindustrial internship",
    r"\bco[- ]?ops?\b",
    r"\bapprentices?\b",
    # F37: "placement" SOZINHO não é marcador (FP Amazon #88 "Inbound &
    # Inventory Placement Operations" — logística; MediaMarkt "advertising
    # placements"). Só os COMPOSTOS UK de placement-estágio (inclui
    # "Placement Analyst" — programa de banco tipo Citi Amsterdam, 6 meses,
    # contra-caso real do universo 13/10).
    r"\b(?:internship|industrial|sandwich|work)\s+placements?\b",
    r"\bplacements?\s+(?:student|year|scheme|position|program|programme|analyst)s?\b",
    r"\bplacement\s+(?:student|year|scheme|position|program|programme|analyst)s?\b",
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
    # Teses academicas (regra do dono, pos-auditoria 15/09): Abschlussarbeit,
    # Bachelor-/Masterarbeit (e com hifen), Semester-/Studienarbeit,
    # Bachelor's/Master's thesis (apostrofo ASCII ou tipografico). Tese e
    # SEMPRE posicao estudantil. So os COMPOSTOS explicitos — nunca
    # "Bachelor"/"Master"/"Studium"/"Student"/"Trainee" soltos (programas de
    # graduacao nao sao estagio; "Student" generico nao e marcador).
    r"\b(abschluss|bachelor|master|semester|studien)[- ]?arbeit\b",
    r"\bbachelor[’']s thesis\b",
    r"\bmaster[’']s thesis\b",
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
    # "Studium mit vertiefter Praxis" (SmVdP): programa de graduacao (inicio
    # 2027, DHBW/TH) — mesma classe do Duales Studium. Auditoria 15/09: 4/4
    # medidos eram graduacao e 2 vazavam para o eligible via marcador de tipo
    # na DESCRICAO (leakage) — a exclusao no TITULO vence a descricao rica
    # ("Praktikum"/"Bachelor"/"Student" na descricao nao ressuscitam a vaga).
    r"\bstudium mit vertiefter praxis\b",
    # Programas de graduacao (Bachelor of Science/Arts/Engineering e variantes;
    # "Bachelor Maschinenbau im Praxisverbund") NAO sao estagio: o TITULO
    # identifica um grau formal. A exclusao no TITULO vence marcador forte de
    # tipo vindo da DESCRICAO (leakage pos-auditoria 15/09: BASF "Bachelor of
    # Science ..." e SAP "Bachelor of Science (B.Sc.) ... (STAR)" passavam pelo
    # "duales studium"/"ausbildung" da descricao). So os COMPOSTOS do grau —
    # nunca "Bachelor" solto (Bachelorarbeit/Bachelor's thesis sao teses
    # VALIDAS; "Internship ... (Bachelor's degree)" e estagio com requisito,
    # sem o "of" -> nao excluido).
    r"\bbachelor of\b",
    r"\bpraxisverbund\b",
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
    # F37 (14/10): Aushilfe = vaga de apoio temporária (Nebenjob/Minijob),
    # não estágio universitário. FP GALERIA ×8 no 13/10: título "Aushilfe
    # (w/m/d)" com desc "studentische Aushilfen ... Werkstudenten" — o
    # marcador forte da DESC vazava; a exclusão de TÍTULO vence a desc
    # (mesmo mecanismo das regras Trainee/Duales Studium existentes).
    r"\baushilfe(n)?\b",
    # F37 (14/10): Schnupperpraktikum = estágio de orientação ESCOLAR
    # (pré-Azubi, aluno de ensino médio) — mesmo degrau do
    # Schuelerpraktikum acima. Caso medido 13/10: Champignon
    # "Schnupperpraktikum Kaufmann für Spedition und Logistik...".
    r"\bschnupper\w*",
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
    r"\bdata science\b",
    r"\bdata analysis\b",
    r"\bdatenanalyse\b",  # DE: data analysis
    r"\bbusiness analyst\b",
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
# Função NÃO-alvo no TÍTULO (F55 — casa canônica; antes vivia só no eu_ranking)
# ---------------------------------------------------------------------------
# Três categorias (marketing/HR/vendas-BD) = os "ruim" do estrato não-DE no
# benchmark v2 (F27/F36): marketing/BD/HR de startups EN. Cada lista é CURTA
# por design: penalidade de título precisa ser precisa; termo genérico demais
# criaria dano colateral. F55 (17/10, veredito v4): a regra migrou para cá
# porque a lente de função deixa de ser exclusiva do perfil EU — o business
# também penaliza, com a correção medida no v4: "HR Rewards Analytics"
# (rotulada RUIM pelo dono) passava pelo gate de área primária ("analytics")
# e ficava ACIMA de ótimas de supply chain (inversões gap-3 nos perfis
# business e EU). A categoria HR passa a ser checada ANTES do gate
# (``ungated_hr``): analytics NÃO protege RH. Híbridos de dados nas demais
# categorias ("Sales Analytics") continuam protegidos pelo gate.
PENALTY_NON_TARGET_FUNCTION = -2.5
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
_NON_TARGET_FN_RES = [
    re.compile(p, re.IGNORECASE)
    for pats in NON_TARGET_FUNCTION_PATTERNS.values()
    for p in pats
]
_NON_TARGET_HR_RES = [
    re.compile(p, re.IGNORECASE) for p in NON_TARGET_FUNCTION_PATTERNS["hr"]
]


def function_penalty_nontarget(title: str, *, ungated_hr: bool = False) -> float:
    """Penalidade por função não-alvo no TÍTULO.

    ``ungated_hr=False`` (comportamento F36/EU): o termo PRIMÁRIO de área no
    título protege a vaga (híbridos de dados — "HR Analytics" sob a regra
    antiga). ``ungated_hr=True`` (correção F55 medida no v4, aplicada ao
    business e ao EU): a categoria HR é checada ANTES do gate — "HR Rewards
    Analytics" é RH com template de dados, não vaga de dados; "Sales
    Analytics" e as demais categorias continuam protegidas pelo gate
    (mesmo espírito da regra do milestone 2: o sinal forte vence a função
    organizacional).
    """
    if ungated_hr and any(rx.search(title) for rx in _NON_TARGET_HR_RES):
        return PENALTY_NON_TARGET_FUNCTION
    if any(p.search(title) for p in _PATTERNS["primary"]):
        return 0.0
    if any(rx.search(title) for rx in _NON_TARGET_FN_RES):
        return PENALTY_NON_TARGET_FUNCTION
    return 0.0


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
# F18 — Aplicabilidade ao perfil do dono (hard exclude na camada eligible)
# ---------------------------------------------------------------------------
#
# Perfil (decisão do dono 07/10): aluno de GRADUAÇÃO (bachelor, Eng.
# Materiais UFSCar 2022–2027), brasileiro, alemão A1–A2, precisa de visto.
# Vagas INAPLICÁVEIS por definição:
#   - alemão EXIGIDO (german_level == required — classificador F18 corrigido);
#   - empresa exige autorização de trabalho PRÉVIA
#     (visa_policy == candidate_must_have_authorization; não-mencionadas e
#     unclear FICAM — unclear é a aposta do projeto);
#   - TESE (Abschlussarbeit/Thesis no título) — não é estágio;
#   - Werkstudent PURO (sem intern/praktikum no título) — exige matrícula em
#     universidade ALEMÃ; híbridos "Werkstudent ... Praktikum" FICAM;
#   - mestrado exigido (requires_master).
# A exclusão é na camada eligible (aqui, na cascata) — a coleta bruta
# (jobs.db/dataset) NÃO muda; remover o estágio reverte o comportamento.

# Motivos de exclusão, na ordem de atribuição first-match (contagem por
# motivo nunca soma mais de 1 por vaga). F37 (14/10): 6 novos motivos de
# hard-eligibility (decisão literal do dono — EXCLUSÃO, nunca score):
# EU-citizenship, NL-enrolment, PhD, duração >6m por título, FULL_TIME
# efetivo sem marcador de estágio. Tese estendida (Bachelorarbeit/
# Masterarbeit puros) continua no motivo thesis_title existente.
# F37.2 (15/10): 2 novos motivos (decisão do dono 15/10 "2a. A" = EXCLUIR,
# mesmo mecanismo da F37): erasmus_program (programa de mobilidade
# estudantil Erasmus+; perfil do dono = visto §16e candidatura direta) e
# spontaneous_pool (candidatura espontânea/pool, título-only).
# F61 (19/10): NENHUM motivo novo — ``visa_blocked`` ganha critério
# TEXTUAL (exigência de título de residência JÁ VÁLIDO dirigida a
# não-UE, MAHLE verbatim) além do critério de intel; o contador existente
# passa a contar os dois caminhos. Reversível: ``--no-applicability``
# desliga o estágio inteiro (comportamento pré-F18).
APPLICABILITY_EXCLUSION_REASONS = (
    "german_required",
    "visa_blocked",
    "thesis_title",
    "werkstudent_puro",
    "master_required",
    "eu_citizenship_required",
    "nl_enrolment_required",
    "phd_position",
    "duration_over_6m",
    "full_time_permanent",
    "erasmus_program",
    "spontaneous_pool",
    "job_type_non_internship",
    "experience_required",
)

# F37.3 (decisão do dono 15/10 ~23:45 UTC, literal: "german_required:
# exclusão total aprovada"): motivos cujo veredito é EXCLUSÃO TOTAL do
# eligible_jobs.json também quando revelados na re-avaliação PÓS-HIDRATAÇÃO
# (F20 topo exibido / F25 backlog) — o registro SAI do arquivo (com
# provenance na métrica diária), e NÃO apenas o flag F25
# ``hydration_inapplicable`` (que demove do topo mas mantém a vaga no JSON).
# A cascata ``select_eligible`` já remove TODO motivo (não só estes); este
# subconjunto é a decisão de QUEM também exclui fora da cascata — a decisão
# vive num lugar só: ampliar a exclusão = somar o motivo a esta tupla
# (1 linha). Nenhum segundo mecanismo, nenhum detector duplicado — o motivo
# vem de ``applicability_exclusion_reason``.
# F86 (20/10, decisão do dono "TODAS as 6 foram recusadas → exclusão
# automática"): as classes job_type_non_internship (HiWi/Werkstudent/
# Masterand/permanente — o detector "não-é-estágio-pra-graduando") e
# experience_required ("N years of professional experience", HYUNDAI
# MOBIS verbatim) também EXCLUEM o eligible_jobs.json na re-avaliação
# PÓS-HIDRATAÇÃO. O dono é graduando (formando 2027): essas classes são
# bloqueios DUROS de elegibilidade (insight do doc de recusas:
# elegibilidade > tuning), não preferência — mesmo tratamento F37.3 de
# ``german_required``. Ampliar = somar o motivo a esta tupla (1 linha).
APPLICABILITY_JSON_EXCLUSION_REASONS = (
    "german_required",
    "job_type_non_internship",
    "experience_required",
)


def is_json_exclusion_reason(reason: str | None) -> bool:
    """F37.3 — True quando o motivo de inaplicabilidade EXCLUI a vaga do
    eligible_jobs.json (mesma trilha de exclusão da cascata e da remoção
    F39), e não só a demove do topo (flag F25). ``None``/motivo não listado
    = False (design F25 intacto)."""
    return reason in APPLICABILITY_JSON_EXCLUSION_REASONS

# Tese por TÍTULO (case-insensitive). "Abschlussarbeit" cobre as teses DE
# sem grau no nome (Bachelorarbeit/Masterarbeit têm os compostos próprios,
# mas caem aqui também); "thesis" cobre EN (Bachelor's/Master's Thesis,
# Thesis Internship). Deliberadamente NÃO inclui "arbeit" solto nem
# "studienarbeit" sem "arbeit"... na real: "studienarbeit" TEM "arbeit",
# mas o pattern pede o composto explícito — sem FP.
_THESIS_TITLE_RE = re.compile(r"abschlussarbeit|thesis", re.IGNORECASE)

# Werkstudent PURO por título: menciona werkstudent/working student E NÃO
# menciona intern/internship/praktikant/praktikum (híbridos FICAM —
# "Werkstudent ... Praktikum" contém estágio e o dono se qualifica).
_WS_TITLE_RE = re.compile(r"werkstudent|working student", re.IGNORECASE)
_WS_HYBRID_RE = re.compile(r"intern|internship|praktikant|praktikum", re.IGNORECASE)


def is_thesis_title(title: str | None) -> bool:
    """Título é de tese acadêmica (Abschlussarbeit/Thesis)?"""
    return bool(_THESIS_TITLE_RE.search(title or ""))


def is_werkstudent_puro_title(title: str | None) -> bool:
    """Título é Werkstudent PURO (sem híbrido de estágio)?"""
    t = title or ""
    return bool(_WS_TITLE_RE.search(t)) and not bool(_WS_HYBRID_RE.search(t))


# ---------------------------------------------------------------------------
# F37 — Saneamento hard-eligibility (14/10): vagas que o dono NÃO PODE
# aplicar saem do eligible (EXCLUSÃO — decisão literal do dono; nunca
# rebaixamento de score). Detectores regex determinísticos sobre trechos
# LITERAIS confirmados na revisão do gabarito 14/10 (referência
# revisao-gabarito-2026-10-14.md). Cada constante nomeia o trecho real.
# ---------------------------------------------------------------------------

# (1) Cidadania EU exigida — o dono tem passaporte BR (visto §16e). Trechos
# literais medidos no universo 13/10 (19 vagas: teampicnic R6 + Kraft Heinz
# ×18). Word-boundary em todos; variantes ue/ü cobertas.
_EU_CITIZENSHIP_RES = [
    # teampicnic R6: "Staatsbürgerschaft eines EU-Mitgliedstaates"
    re.compile(
        r"staatsb(ü|ue)rgerschaft\s+eines\s+eu[- ]mitgliedstaates", re.IGNORECASE
    ),
    # Kraft Heinz R8: "EU working rights are required"
    re.compile(r"\beu\s+working\s+rights\b", re.IGNORECASE),
    # Kraft Heinz R8 (variante literal): "Either you have an EU Citizenship,
    # or you are studying in the Netherlands"
    re.compile(
        r"either\s+you\s+have\s+an\s+eu\s+citizenship,\s+"
        r"or\s+you\s+are\s+studying\s+in\s+the\s+netherlands",
        re.IGNORECASE,
    ),
]

# (2) Matrícula/residência NL obrigatória (sistema holandês HBO/WO) — o dono
# é matriculado na UFSCar (BR). Trechos literais medidos (22 vagas 13/10:
# Vanderlande ×5, Levio ×4, Frenckengroup ×3, Parfumado R12...).
_NL_ENROLMENT_RES = [
    # Vanderlande R31: "Mandatory enrolment to a Dutch Education System &
    # resident of The Netherlands"
    re.compile(
        r"mandatory\s+enrolment\s+to\s+a\s+dutch\s+education\s+system", re.IGNORECASE
    ),
    # Parfumado R12: "enrolled in an HBO/WO programme" (sistema NL; "HBO"
    # puro também aparece — word-boundary evita colisões)
    re.compile(r"\bhbo\b|\bhbo/wo\b", re.IGNORECASE),
]

# (3) PhD/doctoral — perfil é aluno de graduação (bachelor). Casos medidos:
# SAP "PhD Internship" (título), conxai "MS or PhD" (descrição). Só o
# requisito EXPLÍCITO de PhD atual (não mestrado — master_required existe).
_PHD_RES = [
    re.compile(r"\bphd\b", re.IGNORECASE),
    re.compile(r"\bdoctoral\b", re.IGNORECASE),
    re.compile(r"\bdoktorand", re.IGNORECASE),
]


def _res_fire(res: list[re.Pattern], text: str) -> bool:
    return any(rx.search(text) for rx in res)


def requires_eu_citizenship(title: str, description: str | None) -> bool:
    """A vaga exige cidadania UE / direitos de trabalho UE (F37)?"""
    return _res_fire(_EU_CITIZENSHIP_RES, f"{title} {description or ''}")


def requires_nl_enrolment(title: str, description: str | None) -> bool:
    """A vaga exige matrícula/residência no sistema NL (F37)?"""
    return _res_fire(_NL_ENROLMENT_RES, f"{title} {description or ''}")


def requires_phd(title: str, description: str | None) -> bool:
    """A vaga exige PhD/doctoral (F37)?"""
    return _res_fire(_PHD_RES, f"{title} {description or ''}")


# Tese por título — extensão F37: Bachelorarbeit/Masterarbeit (composição
# com hífen/espaço) são teses PUAS no título, e a vaga NÃO é estágio.
# Casos medidos 13/10: OTTOFUCHSKG "Bachelorarbeit Data Science" (FP #57),
# Fraunhofer ×2 "Bachelorarbeit/Semesterarbeit: ...". O regex existente
# (abschlussarbeit|thesis) não casa "bachelorarbeit" (o composto
# "bachelorarbeit" contém "arbeit" mas o pattern exige "abschluss"|"thesis").
# "Bachelorarbeit/Semesterarbeit" também não (mesma razão). Híbridos com
# estágio no título FICAM (ex.: "Praktikum ... Bachelorarbeit" seria estágio
# com tese — não medido no universo, mas a regra do título-puro preserva).
_THESIS_TITLE_F37_RE = re.compile(
    r"\b(bachelor|master)[- ]?arbeit\b", re.IGNORECASE
)


def is_thesis_title_strict(title: str | None) -> bool:
    """Título é tese PUra (F37)? Cobertura estendida: Bachelorarbeit/
    Masterarbeit (com hífen/espaço) além de Abschlussarbeit/Thesis."""
    t = title or ""
    return bool(_THESIS_TITLE_RE.search(t) or _THESIS_TITLE_F37_RE.search(t))


# Duração por título > 6 meses (teto §16e): a vaga É longa por definição
# do próprio título. Parser reusado da F29 (job_duration — mesma semântica
# min>6 = flag, 6 exatos e faixa com piso <=6 = ok). TÍTULO-ONLY: a
# descrição tem FPs de contexto medidos (14 casos >6m na desc, 5 deles
# "graduated in the last 12 months"/"Reststudiendauer mind. 12 Monate" —
# não são duração da vaga). Casos reais no título (13/10): ArcelorMittal
# "IT Procurement Internship - 12 months" (#38), Deutsche Börse "for up to
# 12 months".
_DURATION_OVER6M_MONTHS = 6


def duration_over_6m_title(title: str | None) -> bool:
    """Título cita duração da vaga acima do teto §16e de 6 meses (F37)?

    Usa o MESMO parser da F29 (``opportunity_intel.job_duration``) sobre o
    TÍTULO apenas: ``min > 6`` exclui (o piso da faixa já estoura o
    teto); ``min <= 6`` fica (faixa 6–12 começa dentro do teto — mesma
    semântica de ``duration_flag_text`` da F29, casos Edbz/Bosch 6–12).
    """
    if not title:
        return False
    from internship_finder.opportunity_intel import job_duration

    dur = job_duration({"title": title, "description": None})
    if not dur:
        return False
    return dur["min"] > _DURATION_OVER6M_MONTHS


# FULL_TIME efetivo (F37): employment_type == FULL_TIME sem NENHUM
# marcador de estágio no título NEM na descrição = vaga permanente
# (full-time job), não estágio. Caso medido 13/10: Amazon EU Sàrl
# "Business Analyst, EU Inbound & Inventory Placement Operations"
# (FP #88 — passava por "placement" logístico na desc). CONTRA-CASO
# travado: Praktikum legítimo marcado FULL_TIME (Bosch "Praktikum in der
# Logistik" et al., 268/272 do FULL_TIME) continua eligible — o marcador
# no título os preserva por construção.
_FULL_TIME_VALUES = {"full_time", "fulltime", "full-time", "full time"}


def is_full_time_permanent(job: dict) -> bool:
    """Vaga FULL_TIME efetiva SEM marcador de estágio (F37)?

    True quando ``employment_type`` normalizado é FULL_TIME e o texto
    (título+descrição) não traz nenhum marcador de tipo estudante. As
    vagas legítimas de estágio marcadas FULL_TIME carregam o marcador no
    título (Praktikum/Intern/...) — o detector só pega as permanentes
    de verdade.
    """
    et = str(job.get("employment_type") or "").strip().lower().replace("-", "_")
    if et not in _FULL_TIME_VALUES:
        return False
    if et in STUDENT_EMPLOYMENT_TYPES:  # intern/internship/co-op (defensivo)
        return False
    title = str(job.get("title") or "")
    description = job.get("description") or ""
    text = f"{title} {description}".lower()
    return not _has_any(STUDENT_TYPE_PATTERNS, text)


# F37.2 (15/10) — Erasmus+ = programa de mobilidade estudantil europeia. O
# dono tem visto §16e com candidatura DIRETA e não é estudante-UE em
# mobilidade: postings de programa Erasmus+ não são aplicáveis (decisão
# literal "2a. A" = EXCLUIR). Detecção por TÍTULO apenas — a menção na
# descrição NÃO mata (contra-casos medidos 13/10: Bosch Tienen "Internship
# Purchasing Project Management (M/PPE-WS10)" / "Internship Logistics" /
# "Internship in the fields Manufacturing and Production planning" citam
# Erasmus/partner na desc e são estágios legítimos).
# Casos medidos (universo 13/10): e-farm "Paid Erasmus+ International
# Internship in International Logistics" (#85) e "Baltic Markets – Paid
# Erasmus+ ... Digital Sales" etc. ×6; indiecampers "Spontaneous Application
# | Tourism & Operations Internship - Erasmus+" ×11; clear "Erasmus
# Internship - Partnership Development Intern" / "... Project Management
# Intern"; Tierklinik Ismaning "Erasmus plus-Programm als Praktikum für
# Student*innen und Absolvent*innen der Veterinärmedizin"; artscience-node
# "Only for Erasmus/Turing Internship: AI/IT, Graphic Designer...".
# Guard anti-nome-próprio (empresa/pessoa/universidade chamada Erasmus,
# zero casos no universo 13/10+14/10, defensivo): ocorrências de
# "Erasmus University/Universität/College/MC" não contam como programa.
_ERASMUS_PROGRAM_RE = re.compile(r"\berasmus\b", re.IGNORECASE)
_ERASMUS_NAME_RE = re.compile(
    r"\berasmus\s+(university|universit(ä|a|a)?t|college|mc)\b", re.IGNORECASE
)


def requires_erasmus_program(title: str | None, description: str | None = None) -> bool:
    """Título identifica a vaga como programa Erasmus+ (F37.2)?

    Título-only: remove as ocorrências de nome próprio (``Erasmus
    University Rotterdam`` etc.) e casa ``\\berasmus\\b`` no que sobra —
    "Erasmus Internship"/"Erasmus+ program"/"Erasmus plus-Programm" são
    programas de mobilidade; "Erasmus University" sozinho não é. A
    descrição é aceita por assinatura mas deliberadamente IGNORADA
    (contra-casos Bosch desc-erasmus medidos no universo).
    """
    if not title:
        return False
    cleaned = _ERASMUS_NAME_RE.sub(" ", title)
    return bool(_ERASMUS_PROGRAM_RE.search(cleaned))


# F37.2 (15/10) — candidatura espontânea / pool: posting que NÃO é uma vaga
# concreta, é um canal de "mande seu CV". TÍTULO-only (desc-only NUNCA mata
# — contra-casos medidos 13/10: NXP "become part of NXP's Young
# Professional Talent Pool" (perk), REWE "Aufnahme in das Bindungsprogramm
# 'future steps' mit exklusiven Events und Talentpool" (programa
# pós-candidatura), Atlas Copco "bewaard in onze talentpool voor
# toekomstige opportuniteiten" (desc NL), Edbz "Deine Bewerbung kannst Du
# daher als eine Art Initiativbewerbung verstehen" (vaga concreta), GRIFOLS
# "bewirb dich initiativ für ein Praktikum bei Haema" (instrução),
# Henkel/BASF/Bayer "...initiatives/Initiativen..." (FP do \binitiativ\w* —
# word-boundary fecha esta classe: "initiatives" NÃO casa).
# Casos medidos (títulos): "Spontaneous Application" (VW, Webasto, Allianz,
# Barco, Swisslife, NXP FR, indiecampers), "Candidature spontanée"
# (Liebherr FR, NXP), "Candidatura Espontânea/á" (VW ES/PT),
# "Initiativbewerbung(en)" (Fraunhofer ×40+, AIXTRON, Bosch JMP, caronsale,
# continental, Telekom, eathappy, Marquardt, Klinikum...),
# "Initiativstelle(n)" (Fraunhofer HHI, VW ZENDA, Klinikum EB),
# "Initiativ" puro (Witzenmann "Praktikant (m/w/d) (Initiativ)", datev
# "Initiativ für IT"), "Talent Pool" (ABB ×30), "Open Application"
# (noxmobility, jacklinks, paretosecurities), "Open Internship Application"
# (Enzazaden), "Speculative Application" (Fraunhofer ×15), "Unsolicited
# application" (Fraunhofer/Bosch ×50), "Initiative Application"
# (Fraunhofer, nxp "Student Internships - Initiative Application (m/f/d)",
# Knorr-Bremse, sungrow).
_SPONTANEOUS_POOL_RES = [
    re.compile(r"\bspontaneous\s+applications?\b", re.IGNORECASE),
    re.compile(r"\bcandidature\s+spontan(é|e)e?s?\b", re.IGNORECASE),
    re.compile(r"\bcandidatura\s+espont(â|á|a)ne[as]?\b", re.IGNORECASE),
    re.compile(r"\bspontan\w*bewerbung\w*\b", re.IGNORECASE),
    # DE — "Initiativbewerbung(en)", "Initiativstelle(n)", "Initiativ"
    # puro ("Praktikant (m/w/d) (Initiativ)", "Initiativ für IT").
    # \binitiativ\b sozinho NÃO casa "Initiativen"/"initiatives"/
    # "Initiative" (word-boundary) — o FP em massa medido no eligible
    # (124 estágios legítimos) fica vivo.
    re.compile(r"\binitiativ(bewerbung\w*|stelle\w*|stellen)?\b", re.IGNORECASE),
    # EN — pools nomeados: "Talent Pool", "Open (Internship) Application",
    # "Speculative Application", "Unsolicited Application", "Initiative
    # Application". "open application" no título é sempre canal; na
    # descrição é menção (não olhamos desc).
    re.compile(r"\btalent\s*pool\b", re.IGNORECASE),
    re.compile(r"\bopen\s+(internship\s+)?applications?\b", re.IGNORECASE),
    re.compile(r"\b(speculative|unsolicited|initiative)\s+applications?\b",
               re.IGNORECASE),
]


def is_spontaneous_pool_title(title: str | None) -> bool:
    """Título identifica o posting como candidatura espontânea/pool (F37.2)?

    Título-only: os padrões só casam nomes de CANAL ("Spontaneous
    Application", "Initiativbewerbung", "Talent Pool", "Open
    Application"...) no título. Vagas concretas que mencionam o canal na
    descrição ficam (contra-casos medidos acima).
    """
    if not title:
        return False
    return any(rx.search(title) for rx in _SPONTANEOUS_POOL_RES)


# requires_master — a vaga exige/é mestrado (título OU descrição).
#
# Título: tese/estudo de mestrado por definição (Masterarbeit, Master's
# Thesis, Master Thesis, Masterstudium, Masterstudent).
#
# Descrição: exigência do GRAU. Word-boundary + whitelist de falsos
# positivos ("master data", "masterclass", "master plan"...): o pattern
# nega cada FP conhecido com lookbehind/lookahead ANTES de casar o
# "master" genérico. "Bachelor's or Master's" NÃO é exigência de mestrado
# (perfil bachelor se qualifica). "Abschlussarbeit" isolado NÃO é sinal
# (pode ser tese de bachelor — a exclusão de tese é por TÍTULO).
_MASTER_TITLE_RE = re.compile(
    r"\bmaster(arbeit|'?s?\s?thesis|studium|student)\b", re.IGNORECASE
)

# FPs que NUNCA são grau de mestrado (verificados por teste). O lookbehind
# lista os prefixos compostos; "master's degree" etc. vêm do corpo central.
_MASTER_FP_PREFIX = (
    r"(?<!master\s)(?<!master-)"  # bloqueia o PRÓPRIO "master x" já casado
)
# Padrões legítimos de exigência (EN+DE). Cada alternativa exige contexto
# de GRAU/PROGRAMA/ESTUDO — nunca "master data/schedule/plan/class/key/
# bedroom/ceremonies/postmaster/webmaster/gamesmaster/quartermaster/
# masterful/masterpiece" (todos com word-boundary e verificados).
_MASTER_DEGREE_RES = [
    # grau explícito
    re.compile(
        r"\bmaster'?s?\s+(degree|diploma|abschluss|programme|program|"
        r"course)\b|\bmaster\s?abschluss\b|\bmasterabschluss\w*\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bm\.?sc\.?\b|\bm\.?eng\.?\b", re.IGNORECASE),
    # estado de aluno/estudo de mestrado
    re.compile(
        r"\b(studying towards|enrolled in|pursuing|currently enrolled in)\s+a?\s*"
        r"(master'?s?\s+(program|programme|degree|course|studies)?|"
        r"masterstudium)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bmaster'?s?\s+student\b|\bmasterstudent\w*\b|"
        r"\byou are a master'?s?\s+student\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcompleted master'?s?\b|\bmaster'?s?\s+(completed|degree)\b|"
        r"\bholds? a master'?s?\b|\bmaster'?s?\s+level\b",
        re.IGNORECASE,
    ),
]
# FP guard: termos que parecem master mas NÃO são grau. Casam ANTES dos
# legítimos e NEUTRALIZAM o trecho (função corta o texto nos FPs).
_MASTER_FP_RE = re.compile(
    r"\bmaster\s+(data|schedule|plan|key|bedroom|file|records?|management|"
    r"template|record|builder|sample|list|sheet|transaction|table|index|"
    r"node|page|view|query|report|dashboard|model|pipeline|server|"
    r"database|system|source|target|view|form|code|script|test|ticket|"
    r"order|invoice|vendor|customer|material|product|item|article|"
    r"number|id|data set|dataset| cleanse|governance|maintenance|"
    r"masterclass|master class)\b"
    r"|\b(masterclass|masterful|masterpiece|postmaster|webmaster|"
    r"gamesmaster|quartermaster|master of ceremonies|master key|"
    r"master bedroom|master data|master schedule|master plan)\b",
    re.IGNORECASE,
)


def requires_master(title: str | None, description: str | None) -> bool:
    """A vaga exige (ou é) mestrado? Função pura, case-insensitive, EN+DE.

    ``True`` SOMENTE quando há evidência de exigência/ser de mestrado:

    - Título com Masterarbeit / Master's Thesis / Master Thesis /
      Masterstudium / Masterstudent → True (tese/estudo de mestrado);
    - Descrição exigindo o grau ("Master's degree", "M.Sc.", "Master
      abschluss", "completed master", "master's program", "you are a
      Master student", "studying towards a Master", "Currently enrolled
      in a Master's program" — caso real SAP iXp 1444205833) → True;
    - "Bachelor's or Master's" / "(Bachelor/Master)" / "Bachelor; Master"
      → False (não é exigência de mestrado — bachelor se qualifica);
    - "Abschlussarbeit" isolado na descrição → False (ambíguo);
    - FPs ("master data", "master schedule", "masterclass", "master key",
      "master bedroom", "postmaster", "webmaster", "gamesmaster",
      "quartermaster", "masterful", "masterpiece", "Master of
      Ceremonies") → False (word-boundary + guard).
    """
    t = (title or "")
    if _MASTER_TITLE_RE.search(t):
        return True
    d = (description or "")
    if not d:
        return False
    # Título sem sinal: analisa a descrição removendo os trechos FP
    # (substitui por espaço para não colar palavras vizinhas).
    cleaned = _MASTER_FP_RE.sub(" ", d)
    # "Bachelor's or Master's"/"Bachelor or Master" não exige mestrado:
    # neutraliza o "Master" dessas construções ANTES dos padrões legítimos.
    cleaned = re.sub(
        r"\bbachelor'?s?\s*(or|/|;|,|und|and)?\s*master'?s?\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return any(rx.search(cleaned) for rx in _MASTER_DEGREE_RES)


# ---------------------------------------------------------------------------
# F61 — Visa §16e (19/10): exigência TEXTUAL de título de residência JÁ
# VÁLIDO dirigida a cidadãos não-UE. O dono emigra com visto §16e de
# PRIMEIRA ENTRADA (jan/2027) — não possui Aufenthaltstitel antes de
# emigrar; posting que o exige como pré-requisito é bloqueio (eliminação
# manual atestada no REGISTRO-AVALIACOES-VAGAS 10/2026: MAHLE Lead-Buying
# score 4.5, eliminada pelo dono com esse motivo).
#
# Medição pré-implementação (archive 20261018T090001Z, estágio de
# aplicabilidade = 3.121 vagas): o classificador WA de TEXTO
# (app_intel.work_authorization) JÁ devolve ``existing_required`` para a
# description MAHLE — o buraco era a CADEIA: ``visa_blocked`` era
# intel-only e a MAHLE é ``unclear`` na curadoria F9, então o sinal
# textual nunca era consultado. Este detector fecha o buraco pelo padrão
# ESPECÍFICO (endereçado-a-não-UE + qualificador de exigência), NÃO pelo
# estado genérico ``existing_required``: os patterns _WA_EXISTING incluem
# alternativas sem qualificador (``EU-Bürger`` bare casa o pattern [3])
# e ligar o estado inteiro à exclusão bloquearia vagas que apenas
# MENCIONAM o tema.
#
# A DIREÇÃO é o discriminador semântico (anti-FP medido): o padrão exige
# nicht-eu/non-eu ANTES do documento. VW Praktikum ("Ggf. Arbeits- und
# Aufenthaltserlaubnis inkl. Zusatzblatt für Nicht-EU-Bürgerinnen /
# -Bürger" — condicional ggf., ordem INVERTIDA) e STIHL ("wenn vorliegend
# ... deine gültige Arbeits- und Aufenthaltserlaubnis") NÃO casam. Guard
# de negação no span casado: "kein gültiger Aufenthaltstitel erforderlich"
# / "residence permit not required" não bloqueiam.
#
# Patrocínio OFERECIDO (contra-casos medidos no universo 18/10:
# the-exploration-company "including visa sponsorship where applicable",
# internations "support with your visa application", teampicnic "sponsor
# your Visa", MediaMarktSaturn "we'll assist you with the visa process")
# não tem a forma endereçada-a-não-UE + exigência → nunca bloqueia.
# ---------------------------------------------------------------------------
_NON_EU_PERMIT_RES = [
    # MAHLE DE verbatim — 12 registros no estágio 18/10: "Für
    # Nicht-EU-Bürger: gültiger Aufenthaltstitel erforderlich"
    re.compile(
        r"(für\s+)?nicht-eu[^\n]{0,40}aufenthaltstitel[^\n]{0,20}"
        r"(erforderlich|notwendig|vorausgesetzt)",
        re.IGNORECASE,
    ),
    # MAHLE EN verbatim — 16 registros: "For non-EU citizens: Valid
    # residence permit required"
    re.compile(
        r"(for\s+)?non-eu[^\n]{0,40}residence\s+permits?[^\n]{0,20}"
        r"(required|necessary|needed)",
        re.IGNORECASE,
    ),
    # Variantes estruturais equivalentes (0 ocorrências no universo 18/10;
    # mesma forma endereçada-a-não-UE + qualificador — sem generalização
    # além do evidenciado: o composto "Aufenthalts- und Arbeitserlaubnis"
    # NÃO é coberto por não existir na forma bloqueante no universo).
    re.compile(
        r"(for\s+)?non-eu[^\n]{0,40}(work|working)\s+permits?[^\n]{0,20}"
        r"(required|necessary|needed)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(für\s+)?nicht-eu[^\n]{0,40}aufenthaltserlaubnis[^\n]{0,20}"
        r"(erforderlich|notwendig|vorausgesetzt)",
        re.IGNORECASE,
    ),
]
# Negação DENTRO do span casado invalida a exigência (guard F61). ``\bno\b``
# não casa "non-EU" (em "non" não há boundary após "no").
_NON_EU_PERMIT_NEGATION_RE = re.compile(r"\b(kein\w*|not|no)\b", re.IGNORECASE)


def requires_existing_permit_for_non_eu(
    title: str | None, description: str | None
) -> bool:
    """F61 — o texto exige permit/título de residência JÁ VÁLIDO a não-UE?

    Pura, case-insensitive, DE+EN. ``True`` SOMENTE na forma
    endereçada-a-não-UE + documento + qualificador de exigência — a
    direção nicht-eu→documento é o discriminador (a ordem invertida
    documento→nicht-eu é checklist condicional e NÃO bloqueia) e negação
    no span casado ("kein ... erforderlich", "not required") também não.
    """
    text = f"{title or ''} {description or ''}"
    for rx in _NON_EU_PERMIT_RES:
        m = rx.search(text)
        if m and not _NON_EU_PERMIT_NEGATION_RE.search(m.group(0)):
            return True
    return False


# ---------------------------------------------------------------------------
# F86 — job_type + experiência (20/10): o detector "não-é-estágio-pra-
# graduando". Origem: RECUSAS-FEEDBACK-PIPELINE-2026-10.md, categoria TIPO
# (5 vagas) + EXPERIENCIA (1 vaga), todas recusadas pelo dono em 20/10 com
# veredito FALHA/PARCIAL — score ≠ elegibilidade; a correção é EXCLUSÃO
# F37.3-style (``job_type_non_internship`` + ``experience_required``),
# nunca peso. O dono é graduando (formando 2027): HiWi/Student assistant
# não é Pflichtpraktikum; Werkstudent exige matrícula em universidade
# ALEMÃ (Einschreibung); Masterand é tese de MESTRADO (perfil bachelor);
# permanente full-time não é estágio; experiência profissional prévia
# bloqueia o estagiário de primeira viagem.
#
# PASSO 0 (medido no corpus real 20/10, jobs.json 108.173 vagas brutas +
# eligible 704): hiwi no título 574 / desc-only 111; werkstudent título
# 9.941 / desc-only 80; Masterand/Bachelorand no título 25 (gap REAL —
# nada pegava: ``requires_master`` casa master(arbeit|thesis|studium|
# student), não "Masterand"); sinal full-time textual 2.309; padrão de
# experiência 2.322 no bruto — no ELIGIBLE o delta medido da cadeia nova
# é 10 (4 hiwi + 5 werkstudent + 1 tese) + 1 experience_required.
#
# GUARD DE TÍTULO (anti-FP, doutrina F37 dos híbridos — "Werkstudent ...
# Praktikum" FICA): título com marcador de estágio/Praktikum NUNCA é
# excluído pelo job_type, mesmo que o restante do texto mencione outras
# classes. Família praktikum por SUBSTRING (compostos medidos:
# "Jahrespraktikum", "Pflichtpraktikant", "Praktikanten") — mesma
# permissividade do _WS_HYBRID_RE da F37; família intern por WORD-
# BOUNDARY ("International"/"Internal" NÃO salvam — os 5 werkstudent
# puros que escapavam do puro por "Intern⊂International" são casos
# REAIS medidos no eligible: Marquardt Footprint Management, oediv/
# Oetker Controlling International, REWE International Tax, mllerservi).
# O caso-limite Impulsgrad "Werkstudent:in / Praktikant:in" (título
# duplo, desc vazia) FICA (decisão registrada no relatório F86: a
# presença de Praktikant no título salva — doutrina dos híbridos — e o
# dono se qualifica a Praktikum §16e; badge de ambiguidade no site).
# ---------------------------------------------------------------------------
# (a) guard de título — veja o bloco acima.
_JOB_TYPE_TITLE_GUARD_RE = re.compile(
    r"praktikum|praktika|praktikant|\binterns?\b|\binternships?\b|\bfreiwillig",
    re.IGNORECASE,
)
# (b) HiWi/Student assistant (DE+EN). Fraunhofer Hamburg "Studentische
# Hilfskraft Software Entwicklung..." (SF 1444227733) e Fraunhofer
# Kaiserslautern "STUDENT ASSISTANT (all genders) - DATA SPACE..." (SF
# 1446740233) verbatim; família AIXTRON "Studentische Aushilfe" pega pelo
# trecho desc-only de HiWi/Hilfskraft (medido).
_HIWI_RE = re.compile(
    r"\bhiwi\b|wissenschaftliche\s+hilfskraft|studentische\s+hilfskraft"
    r"|student\s+assistant",
    re.IGNORECASE,
)
# (c) Werkstudent — título (reuso do _WS_TITLE_RE da F37) e descrição com
# contexto DEFINIDOR ("als Werkstudent:in...", "as a working student...").
# Desc-solto NUNCA pega: "durch Praktika, Werkstudententätigkeiten oder
# eine erste Berufserfahrung" (boilerplate de background, BASF Junior
# Controller SF verbatim) não é a vaga ser Werkstudent.
_WS_DESC_RE = re.compile(
    r"\b(?:als|as\s+a?)\s+(?:werkstudent\w*|working\s+students?)\b",
    re.IGNORECASE,
)
# (d) Tese por PAPEL (Masterand/Bachelorand — gap medido: 25 títulos) e
# por DEFINIÇÃO na descrição ("im Rahmen einer Masterarbeit",
# "Master's Thesis:"). "Abschlussarbeit" solto na descrição NÃO pega
# (doutrina existente do requires_master: ambíguo — pode ser tese de
# bachelor e a exclusão de tese é por TÍTULO).
_TESE_ROLE_RE = re.compile(r"\b(?:master|bachelor)and\w*", re.IGNORECASE)
_TESE_DESC_RE = re.compile(
    r"im\s+rahmen\s+(?:einer|deiner|ihrer|der)\s+"
    r"(?:master|bachelor)['’´-]?\s?(?:arbeit|thesis)"
    r"|\bmasterarbeit\b|\bmaster[’'´]?s?\s+thesis\b",
    re.IGNORECASE,
)
# (e) Permanente textual: sinal de full-time/emprego fixo + remuneração
# ANUAL (medido BASF Junior Controller SF verbatim: "Bruttojahresgehalt
# (Vollzeit): 40.000 - 46.000 €"). A ausência de marcador estudantil usa
# a MESMA STUDENT_TYPE_PATTERNS do full_time_permanent da F37 (título+
# descrição) — um estágio legítimo carrega o marcador em algum lugar;
# boilerplate de empresa ("Wir bieten Praktika an...") bloqueia o motivo
# por design (falso-negativo consciente, documentado no relatório: o
# gêmeo SF do BASF JC fica, o gêmeo AA/desc-vazia sai).
_FULLTIME_TEXT_RE = re.compile(
    r"\bvollzeit\b|\bfestanstellung\b|bruttojahresgehalt|jahresgehalt"
    r"|jahresarbeitsentgelt|\bpermanent\s+(?:position|contract|role|employment)"
    r"|\d[\d.,]*\s*€\s*(?:pro|per)\s+(?:jahr|year)"
    r"|€\s*\d[\d.,]*\s*(?:pro|per)\s+(?:jahr|year)"
    r"|\d[\d.,]*\s*(?:eur|euros?)\s*(?:pro|per)\s+(?:jahr|year)"
    r"|\b\d[\d.,]{3,}\s*(?:pro|per)\s+(?:jahr|year)\b",
    re.IGNORECASE,
)


def job_type_of(title: str | None, description: str | None) -> str | None:
    """F86 — classe de tipo de vaga extraída de título+descrição.

    Retorna ``"hiwi"`` | ``"werkstudent"`` | ``"tese"`` | ``"permanente"``
    ou ``None`` (sem sinal OU título com marcador de estágio/Praktikum —
    o guard dos híbridos F37). Precedência hiwi > werkstudent > tese >
    permanente (permanente só por AUSÊNCIA de marcador + sinal full-time,
    então não colide com as demais). Pura, case-insensitive, DE+EN.
    """
    t = title or ""
    d = description or ""
    if _JOB_TYPE_TITLE_GUARD_RE.search(t):
        return None
    text = f"{t} {d}"
    if _HIWI_RE.search(text):
        return "hiwi"
    if _WS_TITLE_RE.search(t) or _WS_DESC_RE.search(d):
        return "werkstudent"
    if _TESE_ROLE_RE.search(text) or _TESE_DESC_RE.search(d):
        return "tese"
    if _FULLTIME_TEXT_RE.search(text) and not _has_any(
        STUDENT_TYPE_PATTERNS, text
    ):
        return "permanente"
    return None


# (f) Título duplo Werkstudent/Praktikant (caso Impulsgrad "Werkstudent:in
# / Praktikant:in Operations & Entrepreneurship (m/w/d)", desc vazia):
# FICA no eligible (o guard de título salva) e o site renderiza o badge de
# ambiguidade — o dono vê o porquê na triagem. O classificador do badge
# vive em ``app_intel.job_type_ambiguous_title`` (camada pura
# compartilhada com o render — o G1 da F51 veda o renderer de importar
# filters; mesma dicotomia do german_level F18/F37.3).


# (g) Experiência profissional prévia (HYUNDAI MOBIS verbatim: "Minimum
# of 1 year of relevant professional experience"). N ≥ 1 ANO. Quatro
# guards medidos no corpus:
#   1. NEGAÇÃO no span ("keine Erfahrung erforderlich" não tem número —
#      o \\d+ já protege; o guard cobre "not required" com número);
#   2. FAIXA COM PISO ZERO ("0–2 years of experience (entry-level)", SAP
#      Contracts & Bid Support verbatim — o dono SE QUALIFICA com 0 anos);
#   3. HISTÓRIA DA EMPRESA: a frase da match é sobre a EMPRESA ("building
#      on more than 180 years of experience", C&A verbatim; "With more
#      than 70 years of experience ... Coface has become"; "With 30 years
#      of experience in chemical trading ... has established") e não
#      sobre o CANDIDATO → não é requisito;
#   4. DE por composto ("N Jahre Berufserfahrung/Praxiserfahrung").
_EXP_RES = [
    re.compile(
        r"(\d+)\s*(?:jahr|year)s?\s*(?:of\s*)?(?:relevant\s*)?"
        r"(?:professional\s*)?(?:work\s*)?(?:experience|erfahrung)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d+)\s*jahre?s?\s+\w*erfahrung",
        re.IGNORECASE,
    ),
    # "N+ years" — o "+" é marcador de requisito (medido 20/10: 2.371 no
    # corpus bruto — AIXTRON "Minimum 5+ years of hands-on experience",
    # adidas "2 + years working with Global markets"; 2.459 com
    # experience/erfahrung em ≤80 chars; 0 FPs de duração-de-contrato no
    # eligible — a duração usa meses/"befristet", não "N+ years").
    re.compile(r"(\d+)\s*\+\s*(?:jahre?s?|years?)\b", re.IGNORECASE),
]
_EXP_NEGATION_RE = re.compile(r"\b(?:kein\w*|not|no)\b", re.IGNORECASE)
# Negação DEPOIS do span ("3 years of experience are not required",
# "sind nicht erforderlich") — só formas de exigência negada; o "not"
# solto ("Not only that...") NÃO nega (FP).
_EXP_POST_NEGATION_RE = re.compile(
    r"\bnot\s+(?:\w+\s+)?(?:required|necessary|needed)\b"
    r"|\b(?:is|are|sind|ist)\s+nicht\b"
    r"|\b(?:nicht|kein\w*)\s+(?:\w+\s+)?(?:erforderlich|notwendig)\b",
    re.IGNORECASE,
)
_EXP_ZERO_RANGE_RE = re.compile(
    r"\b0\s*[-–—]\s*\d+\s*(?:jahre?s?|years?)\b", re.IGNORECASE
)
_EXP_HISTORY_RE = re.compile(
    r"\bwe\b|\bour\b|\bwir\b|\bunser\w*|\bbuilding on\b"
    r"|\bhas\s+(?:become|established|built|grown)\b|\bfounded\b"
    r"|\bgegr(?:ü|ue)ndet\b",
    re.IGNORECASE,
)
_EXP_CANDIDATE_RE = re.compile(
    r"\byou\b|\byour\b|\bdu\b|\bdein\w*|\bprofil\b|\bprofile\b"
    r"|\bcandidates?\b|\bapplicants?\b|\bbewerber\w*",
    re.IGNORECASE,
)
_EXP_SENTENCE_SPLIT = ".!?·•¶\n"


def _sentence_at(text: str, pos: int) -> str:
    """Frase (span entre separadores) que contém ``pos`` — guard 3."""
    starts = [text.rfind(ch, 0, pos) + 1 for ch in _EXP_SENTENCE_SPLIT]
    s = max(starts) if starts else 0
    ends = [
        i
        for i in (text.find(ch, pos) for ch in _EXP_SENTENCE_SPLIT)
        if i != -1
    ]
    e = min(ends) if ends else len(text)
    return text[s:e]


def requires_experience(title: str | None, description: str | None) -> bool:
    """F86 — exige N ≥ 1 ano de experiência profissional prévia?

    Pura, case-insensitive, EN+DE, sobre título+descrição. Os guards de
    negação/faixa-zero/história-de-empresa estão no bloco ``_EXP_RES``.
    """
    text = f"{title or ''} {description or ''}"
    for rx in _EXP_RES:
        for m in rx.finditer(text):
            if int(m.group(1)) < 1:
                continue
            # Negação: no PRÓPRIO span ("no 3 years..." — raro) e DEPOIS
            # dele ("3 years of experience are not required" — janela de
            # 20 chars pós-span, só formas de exigência negada).
            if _EXP_NEGATION_RE.search(m.group(0)):
                continue
            if _EXP_POST_NEGATION_RE.search(text[m.end(): m.end() + 20]):
                continue
            if _EXP_ZERO_RANGE_RE.search(
                text[max(0, m.start() - 10): m.end()]
            ):
                continue
            sent = _sentence_at(text, m.start())
            if _EXP_HISTORY_RE.search(sent) and not _EXP_CANDIDATE_RE.search(
                sent
            ):
                continue
            return True
    return False


def applicability_exclusion_reason(
    job: dict, *, intel_map: dict[str, dict] | None = None
) -> str | None:
    """Motivo de inaplicabilidade da vaga ao perfil do dono; None = aplicável.

    Ordem de atribuição FIRST-MATCH (a mesma vaga nunca conta 2 motivos):
    ``german_required`` → ``visa_blocked`` → ``thesis_title`` →
    ``werkstudent_puro`` → ``master_required`` → ``eu_citizenship_required``
    → ``nl_enrolment_required`` → ``phd_position`` → ``duration_over_6m`` →
    ``full_time_permanent`` → ``job_type_non_internship`` →
    ``erasmus_program`` → ``spontaneous_pool`` → ``experience_required``.

    - ``german_required``: ``app_intel.german_level(título+descrição)`` ==
      ``required`` (classificador F18 — o dataset não carrega o nível; a
      exclusão chama a MESMA função pura do render/digest).
    - ``visa_blocked``: (F61) EXIGÊNCIA TEXTUAL de permit/título de
      residência JÁ VÁLIDO dirigida a não-UE
      (``requires_existing_permit_for_non_eu`` — MAHLE verbatim "Für
      Nicht-EU-Bürger: gültiger Aufenthaltstitel erforderlich"; o dono
      emigra com §16e de primeira entrada e não tem título antes de
      emigrar) OU Company Intelligence da empresa com ``visa_policy``
      == ``candidate_must_have_authorization`` (match exato via
      ``opportunity_intel``). Não-mentionadas e ``unclear`` FICAM no
      critério de INTEL (unclear é a aposta do projeto); o critério
      TEXTUAL independe de intel_map — por isso a re-avaliação
      pós-hidratação (F20/F25, chamada sem intel_map) também o aplica
      e ``flagged_visa_blocked`` do registro type:applicability passa
      a ser alcançável (antes: sempre 0).
    - ``thesis_title``: ``abschlussarbeit|thesis`` no título (F37:
      estendido a ``Bachelorarbeit``/``Masterarbeit`` puros via
      ``is_thesis_title_strict``).
    - ``werkstudent_puro``: título com ``werkstudent|working student`` SEM
      ``intern|internship|praktikant|praktikum`` (híbridos ficam).
    - ``job_type_non_internship`` (F86): ``job_type_of(título, descrição)``
      devolve classe — ``hiwi`` (HiWi/wissenschaftliche|studentische
      Hilfskraft/Student assistant — Fraunhofer HH 1444227733, Fraunhofer
      KL 1446740233), ``werkstudent`` (título ou desc definidora "als
      Werkstudent" — exige matrícula alemã), ``tese`` (Masterand/
      Bachelorand por papel — Bauerfeind AG — ou Masterarbeit/Master's
      Thesis definidora na desc) ou ``permanente`` (sinal full-time +
      remuneração anual SEM marcador estudantil — BASF Junior Controller).
      Título com marcador de estágio/Praktikum NUNCA exclui (doutrina F37
      dos híbridos; Impulsgrad "Werkstudent:in / Praktikant:in" FICA com
      badge de ambiguidade).
    - ``master_required``: ``requires_master(título, descrição)``.
    - ``eu_citizenship_required`` (F37): trecho literal exigindo
      cidadania UE / EU working rights (teampicnic R6, Kraft Heinz R8) —
      o dono tem passaporte BR.
    - ``nl_enrolment_required`` (F37): matrícula/residência obrigatória
      no sistema holandês (Vanderlande R31, Parfumado R12 HBO/WO).
    - ``phd_position`` (F37): PhD/doctoral exigido (SAP PhD Internship) —
      perfil é aluno de graduação.
    - ``duration_over_6m`` (F37): título cita duração da vaga acima do
      teto §16e de 6 meses (ArcelorMittal "12 months") — mesmo parser/
      semântica do badge F29, título-only.
    - ``full_time_permanent`` (F37): ``employment_type`` FULL_TIME sem
      NENHUM marcador de estágio no título/descrição (Amazon BA EU
      Inbound #88) — vaga permanente, não estágio.
    - ``erasmus_program`` (F37.2): título identifica programa Erasmus+/
      mobilidade estudantil (e-farm #85, indiecampers #98, clear, Tierklinik,
      artscience-node) — o dono aplica com visto §16e/candidatura direta,
      não é estudante-UE em mobilidade (decisão "2a. A"). Título-only;
      menção na descrição NÃO mata (Bosch Tienen ficam).
    - ``spontaneous_pool`` (F37.2): título identifica canal de candidatura
      espontânea/pool — "Spontaneous Application", "Initiativbewerbung",
      "Initiativstelle", "Initiativ", "Candidature spontanée",
      "Candidatura Espontânea", "Spontanbewerbung", "Talent Pool", "Open
      Application", "Speculative/Unsolicited/Initiative Application" — e o
      posting NÃO é uma vaga concreta (decisão "2a. A"). Título-only;
      menção na descrição NÃO mata (NXP/REWE/Edbz/GRIFOLS ficam).
    - ``experience_required`` (F86): ``requires_experience(título,
      descrição)`` — N ≥ 1 ano de experiência profissional prévia
      (HYUNDAI MOBIS absolventa 13423313 verbatim "Minimum of 1 year of
      relevant professional experience"). Guards: negação no span,
      faixa com piso zero ("0–2 years (entry-level)" FICA) e frase de
      história da empresa ("more than 180 years of experience" C&A NÃO é
      requisito).
    """
    from internship_finder.app_intel import german_level

    title = str(job.get("title") or "")
    description = job.get("description")
    text = f"{title} {description or ''}"

    gl = german_level(text)
    if gl is not None and gl.level == "required":
        return "german_required"

    # F61: exigência TEXTUAL de permit já válido dirigida a não-UE —
    # independe de intel_map (a re-avaliação pós-hidratação F20/F25 chama
    # esta função SEM intel_map; a MAHLE é ``unclear`` na curadoria F9 e o
    # texto é o único sinal dela).
    if requires_existing_permit_for_non_eu(title, description):
        return "visa_blocked"

    if intel_map:
        from internship_finder.opportunity_intel import (
            company_intel_for,
            visa_policy_state,
        )

        entry = company_intel_for(job, intel_map)
        if visa_policy_state(entry) == "candidate_must_have_authorization":
            return "visa_blocked"

    if is_thesis_title_strict(title):
        return "thesis_title"

    if is_werkstudent_puro_title(title):
        return "werkstudent_puro"

    if requires_master(title, description):
        return "master_required"

    if requires_eu_citizenship(title, description):
        return "eu_citizenship_required"

    if requires_nl_enrolment(title, description):
        return "nl_enrolment_required"

    if requires_phd(title, description):
        return "phd_position"

    if duration_over_6m_title(title):
        return "duration_over_6m"

    if is_full_time_permanent(job):
        return "full_time_permanent"

    # F86 (20/10): o detector "não-é-estágio-pra-graduando" — HiWi/
    # Student assistant, Werkstudent (matrícula alemã exigida), tese de
    # papel (Masterand/Bachelorand) e permanente textual (full-time +
    # remuneração anual, sem marcador estudantil). DEPOIS de
    # ``full_time_permanent``: o campo estruturado ``employment_type`` é
    # evidência mais forte que o sinal textual (a fixture F37 "ft" —
    # Associate Analyst FULL_TIME — mantém o motivo original). O guard de
    # título preserva os híbridos F37 ("Werkstudent ... Praktikum" FICA) —
    # decisão do dono: TODAS as 6 vagas do registro foram recusadas.
    if job_type_of(title, description):
        return "job_type_non_internship"

    # F37.2 (decisão do dono 15/10, "2a. A" = EXCLUIR): programas Erasmus+
    # ANTES de pool — first-match: indiecampers "Spontaneous Application |
    # ... - Erasmus+" conta como erasmus_program (programa de mobilidade é
    # o motivo mais específico da vaga).
    if requires_erasmus_program(title, description):
        return "erasmus_program"

    if is_spontaneous_pool_title(title):
        return "spontaneous_pool"

    # F86 (20/10): experiência profissional prévia exigida (HYUNDAI MOBIS
    # verbatim "Minimum of 1 year of relevant professional experience") —
    # bloqueio p/ estagiário de primeira viagem. ÚLTIMO na ordem
    # first-match (ortogonal às classes de tipo; guards de negação,
    # faixa-zero e história-de-empresa no detector).
    if requires_experience(title, description):
        return "experience_required"

    return None


def select_eligible(
    jobs: list[dict],
    *,
    student: bool = True,
    area: bool = True,
    country: str = "de",
    applicability: bool = True,
    intel_map: dict[str, dict] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Aplica os filtros de utilidade em cascata: tipo -> area -> pais.

    F18 — novo estágio final ``aplicabilidade`` (default ON): remove da
    saída eligible as vagas INAPLICÁVEIS ao perfil do dono (alemão exigido,
    empresa que exige autorização prévia, tese por título, Werkstudent
    puro por título, mestrado exigido). Contagem first-match por motivo em
    ``counts["aplicabilidade_excluidas_*"]``; ``counts["aplicabilidade"]``
    é o total mantido. ``applicability=False`` desliga (reversibilidade —
    comportamento idêntico ao pré-F18).

    ``intel_map`` (opcional) é o mapa de Company Intelligence
    (``opportunity_intel.load_company_intel``). Quando fornecido, o motivo
    ``visa_blocked`` exclui empresas com ``visa_policy`` ==
    ``candidate_must_have_authorization`` (não-mentionadas e unclear
    FICAM nesse critério). O ``visa_blocked`` também tem critério
    TEXTUAL (F61 — exigência de permit já válido dirigida a não-UE,
    ``requires_existing_permit_for_non_eu``) que independe de
    ``intel_map`` (a função é pura — nunca lê arquivos; o pipeline do
    CLI injeta o mapa).

    Retorna ``(selecionados, contagens)`` com o total acumulado a cada
    etapa: ``{"total", "tipo", "area", "pais", "aplicabilidade"}``
    (as contagens refletem o que cada etapa manteve). ``jobs`` sao dicts
    (o que o CLI le do JSON) — sem dependencia do modelo ``Job``. Filtro
    desligado mantem a contagem da etapa anterior (ex.: ``country="all"``
    -> ``pais == area``).
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
    if applicability:
        kept: list[dict] = []
        excluded: Counter[str] = Counter()
        for j in step:
            reason = applicability_exclusion_reason(j, intel_map=intel_map)
            if reason is None:
                kept.append(j)
            else:
                excluded[reason] += 1
        step = kept
        for reason in APPLICABILITY_EXCLUSION_REASONS:
            counts[f"aplicabilidade_excluidas_{reason}"] = int(excluded[reason])
    counts["aplicabilidade"] = len(step)
    return step, counts
