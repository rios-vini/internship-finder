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
from datetime import UTC, date, datetime
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
    r"\bpraktikant",  # pega Praktikant/Praktikantin no inicio da palavra
    r"pflichtpraktikant",  # F133: compostos Pflichtpraktikant/Pflichtpraktikantin/Pflichtpraktikant*in
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
    # F141 — compostos alemães de Einkauf/Beschaffung (substring sem \b inicial
    # para casar Projekteinkauf, Energieeinkauf, Frachteinkauf, Rohstoffbeschaffung etc.)
    r"projekteinkauf",
    r"energieeinkauf",
    r"frachteinkauf",
    r"rohstoffbeschaffung",
    r"markeneinkauf",
    r"netzeinkauf",
    r"tiefbaueinkauf",
    r"materialfeldeinkauf",
    r"ersatzteileinkauf",
    r"importverzollung",
    r"globaleinkauf",
    r"strategisch\w*einkauf",
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
    # F141 — compostos alemães de Logistik (substring sem \b inicial para casar
    # Transportlogistik, Produktionslogistik, Intralogistik, Lagerlogistik etc.)
    r"transportlogistik",
    r"beschaffungslogistik",
    r"logistikmanagement",
    r"intralogistik",
    r"produktionslogistik",
    r"lagerlogistik",
    r"vertriebslogistik",
    r"retourenlogistik",
    r"einkaufslogistik",
    r"versorgungslogistik",
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

# ---------------------------------------------------------------------------
# F136 — Contexto não-alvo (HR/Recruiting/Talent/Personal/Marketing)
# ---------------------------------------------------------------------------
# Quando o título indica contexto de RH, recrutamento, talent acquisition,
# pessoal (DE) ou marketing, certos termos RELATED/WEAK que são falsos
# positivos léxicos de procurement/supply-chain devem ter peso ZERO:
# - "operations" em "HR Operations" / "People Operations" ≠ supply-chain ops
# - "sourcing" em "Talent Sourcing" / "Recruiting Sourcing" ≠ procurement sourcing
# - "reporting" em "HR Reporting" ≠ BI reporting
# - "support" em "Campaign Support" / "HR Support" ≠ tech support
# - "logist" em contexto saúde/cuidados (ex.: Zorgbedrijf = empresa de cuidados NL)
#   ≠ supply-chain logistics
# A detecção é por CONTEXTO (prefixo/contexto), não por palavra isolada.
#
# Termos que ZERAM quando contexto não-alvo detectado:
_ZERO_IN_HR_CONTEXT = {
    "related": {
        "operations",
        "operations excellence",
        "sourcing",
        "logist",
    },
    "weak": {
        "reporting",
        "support",
    },
}

# Termos que ZERAM quando contexto marketing detectado
_ZERO_IN_MARKETING_CONTEXT = {
    "related": {
        "operations",
        "operations excellence",
        "logist",
    },
    "weak": {
        "reporting",
        "support",
        "data",
        "sap",
        "erp",
    },
}

# Padrões para detectar contexto HR/Recruiting/Talent/Personal
_NON_TARGET_HR_CONTEXT_PATTERNS = [
    r"\bhr\b",
    r"\bhuman resources\b",
    r"\brecruit\w*",
    r"\btalent\s+(sourcing|acquisition|management|partner)\b",
    r"\bpeople\s+(operations|ops|partner|experience)\b",
    r"\bemployee experience\b",
    r"\bpersonal(entwicklung|wesen|abteilung|bereich)?\b",  # DE: Personal, Personalentwicklung, Personalwesen
    r"\bpessoal\b",  # PT: pessoal (RH)
    r"\brecursos humanos\b",  # PT: recursos humanos
]

# Padrões para detectar contexto Marketing
_NON_TARGET_MARKETING_CONTEXT_PATTERNS = [
    r"\bmarketing\b",
    r"\bbrand\b",
    r"\bcommunications\b",
    r"\bcontent\b",
    r"\btourism\b",
    r"\bevent management\b",
    r"\bproduktmarketing\b",  # DE: product marketing
    r"\bproduct marketing\b",
    r"\bcommunications\b",
    r"\bkommunikation\b",  # DE: communications
    r"\bcampaign\b",
    r"\bsocial media\b",
]

# Padrões para detectar contexto saúde/cuidados (para zerar "logist" em Zorgbedrijf etc.)
_NON_TARGET_HEALTHCARE_CONTEXT_PATTERNS = [
    # Cura do orquestrador (probe real 27/10): \bzorg\b não casa COMPOSTOS —
    # "Woonzorgcentrum/WZC" (a vaga real do Zorgbedrijf) passava mesmo com
    # description. Substring p/ compostos + sigla + "bewoners" (residentes).
    r"zorgbedrijf",  # NL: care company (substring — WoonZorgBedrijf etc.)
    r"zorgcentrum",  # NL: care center (woonzorgcentrum)
    r"verzorging",  # NL: care/nursing (verzorgingstehuis/-huis)
    r"ouderenhuis",
    r"\bwzc\b",  # NL: sigla woonzorgcentrum
    r"\bbewoners?\b",  # NL: residentes (transporte de residentes)
    r"\bzorg\b",  # NL: care
    r"\bzorgbedrijf\b",  # NL: care company (legacy — mantém)
    r"\bzorg\b",  # NL: care
    r"\bgezondheid\b",  # NL: health
    r"\bverpleging\b",  # NL: nursing
    r"\bpflege\b",  # DE: care/nursing
    r"\bbetreuung\b",  # DE: care/support
    r"\bcare\b",
    r"\bhealthcare\b",
    r"\bpatient\b",
    r"\bresident\b",
    r"\belderly\b",
    r"\bsenior\b(?=\s+(care|home|wohn))",  # senior care/home/wohn
]

_NON_TARGET_HR_CONTEXT_RES = [re.compile(p, re.IGNORECASE) for p in _NON_TARGET_HR_CONTEXT_PATTERNS]
_NON_TARGET_MARKETING_CONTEXT_RES = [re.compile(p, re.IGNORECASE) for p in _NON_TARGET_MARKETING_CONTEXT_PATTERNS]
_NON_TARGET_HEALTHCARE_CONTEXT_RES = [re.compile(p, re.IGNORECASE) for p in _NON_TARGET_HEALTHCARE_CONTEXT_PATTERNS]


def _detect_non_target_context(title: str) -> dict[str, bool]:
    """Detecta se o título está em contexto não-alvo (HR/recruiting/marketing/saúde).
    
    Retorna dict com flags: hr, marketing, healthcare.
    """
    title_low = title.lower()
    return {
        "hr": any(rx.search(title_low) for rx in _NON_TARGET_HR_CONTEXT_RES),
        "marketing": any(rx.search(title_low) for rx in _NON_TARGET_MARKETING_CONTEXT_RES),
        "healthcare": any(rx.search(title_low) for rx in _NON_TARGET_HEALTHCARE_CONTEXT_RES),
    }


def _should_zero_term(level: str, term: str, context: dict[str, bool]) -> bool:
    """Verifica se um termo deve ter peso zero dado o contexto detectado."""
    if context.get("hr"):
        if level in _ZERO_IN_HR_CONTEXT and term in _ZERO_IN_HR_CONTEXT[level]:
            return True
    if context.get("marketing"):
        if level in _ZERO_IN_MARKETING_CONTEXT and term in _ZERO_IN_MARKETING_CONTEXT[level]:
            return True
    if context.get("healthcare"):
        # Healthcare context zera "logist" em RELATED
        if level == "related" and term == "logist":
            return True
    return False


def _extract_base_term(pattern: str, level: str) -> str:
    """Extrai termo base do pattern para lookup nas tabelas de zero."""
    # Remove \b, \w*, etc. para obter termo chave
    # Patterns conhecidos que precisam de zero:
    if "operations" in pattern:
        return "operations" if "excellence" not in pattern else "operations excellence"
    if "sourcing" in pattern:
        return "sourcing"
    if "logist" in pattern:
        return "logist"
    if "reporting" in pattern:
        return "reporting"
    if "support" in pattern:
        return "support"
    if pattern == r"\bdata\b":
        return "data"
    if pattern == r"\bsap\b":
        return "sap"
    if pattern == r"\berp\b":
        return "erp"
    # Default: retorna o pattern limpo
    return pattern.strip(r"\b")


def area_score(title: str, description: str | None = None) -> float:
    """Pontuacao de aderencia a area-alvo (titulo pesa mais que descricao).
    
    F136: quando contexto não-alvo (HR/recruiting/marketing/saúde) é detectado
    no título, certos termos RELATED/WEAK que são falsos positivos léxicos
    de procurement/supply-chain têm peso ZERO.
    """
    context = _detect_non_target_context(title)
    score = 0.0
    for level, patterns in _PATTERNS.items():
        # Título
        for p in patterns:
            if p.search(title):
                # Extrair o termo base do pattern para checar se deve zerar
                term = _extract_base_term(p.pattern, level)
                if not _should_zero_term(level, term, context):
                    score += AREA_TITLE_WEIGHTS[level]
                    break  # Só conta uma vez por nível no título
        # Descrição
        if description:
            for p in patterns:
                if p.search(description):
                    term = _extract_base_term(p.pattern, level)
                    if not _should_zero_term(level, term, context):
                        score += AREA_DESC_WEIGHTS[level]
                        break
    return score


def matches_area(title: str, description: str | None = None) -> bool:
    """Vaga adere as areas-alvo do dono? (heuristica, sem ML).
    
    F136: aplica detecção de contexto não-alvo e penalidade de função não-alvo
    para evitar que vagas de HR/recruiting/marketing passem pelo filtro de área.
    """
    # Primeiro calcula score com contexto-aware
    score = area_score(title, description)
    
    # Aplica penalidade de função não-alvo (HR/marketing/sales_bd) no filtro
    # ungated_hr=True: HR é checado ANTES do gate de termo primário
    penalty = function_penalty_nontarget(title, ungated_hr=True)
    score += penalty
    
    return score >= AREA_MIN_SCORE


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
# F106 (23/10): 1 motivo novo na cadeia — ``de_enrolment_required``
# (matrícula em universidade ALEMÃ, irmã da classe NL; detector
# ``requires_de_enrolment`` com âncoras "an/in einer deutschen",
# "einer deutschen Hochschule/Universität", "Hochschule/Universität in
# Deutschland", EN "(at|in) a German university"/"university based in
# Germany"/"at a university in Germany"). Passo 0 medido: os 2 hits do
# eligible (Continental REF99687I, novemcore) eram requisitos reais →
# EXCLUSÃO (não flag), mesma trilha F37.3 da classe NL; contra-casos
# Bosch SPO (matrícula genérica), Duale Hochschule (DUAL) e "based in
# Germany" de residência não casam.
# F137 (27/10) — Threshold de idade de postagem para elegibilidade (hard exclude).
# Default 12 meses: AXA "Praktikum Datenanalyse" postada 24/10/2024 (~24 meses)
# e lotes Consultport (~18 meses, 20/10 e 25/10) chegavam como NOVAS e eram
# eliminadas manualmente. O corte 12m pega esses casos (24m, 18m, 13m+)
# sem afetar vagas recentes (≤11m) nem vagas sem posted_at (neutro, nunca mata).
STALE_POSTING_THRESHOLD_MONTHS = 12

APPLICABILITY_EXCLUSION_REASONS = (
    "german_required",
    "native_language",
    "visa_blocked",
    "thesis_title",
    "werkstudent_puro",
    "master_required",
    "eu_citizenship_required",
    "nl_enrolment_required",
    # F106 (23/10): matrícula em universidade ALEMÃ — irmã da classe NL,
    # motivo PRÓPRIO (a legenda NL carrega 🇳🇱; a DE é 🇩🇪). Passo 0
    # medido: os 2 hits do eligible eram requisitos reais (Continental
    # REF99687I, novemcore) → EXCLUSÃO na cascata, mesma trilha F37.3.
    "de_enrolment_required",
    # F111 (24/10): matrícula em universidade/HBO da UE — irmã das classes
    # NL/DE acima (mesma cadeia F37.3, motivo próprio: a legenda NL é 🇳🇱,
    # a DE é 🇩🇪 e a EU é 🇪🇺). Passo 0 medido: 10/10 spans reais
    # (Bosch Mechelen ×7, Fraunhofer ×2, gospooky ×1) → EXCLUSÃO na
    # cascata (não flag). Contra-casos: "based in EU", "work within the
    # EU", "sales within the EU", "remote within the EU", "EU-based
    # university" cooperativa, "studying in the EU" solto — 0 FP.
    "eu_enrolment_required",
    "phd_position",
    "duration_over_6m",
    "duration_conflict",
    "full_time_permanent",
    "erasmus_program",
    "spontaneous_pool",
    "job_type_non_internship",
    "experience_required",
    "recent_graduate",
    # F137 (27/10): posted_at > 12 meses → stale_posting (hard exclude).
    # Mesmo threshold da constante acima; casos medidos: AXA 24m, Consultport 18m.
    # posted_at ausente/inválida NÃO desclassifica (neutro — mesma semântica
    # do dedup: ausente = "infinito" para frescor, aqui = nunca mata).
    "stale_posting",
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
    # F99 (22/10): classes duras de elegibilidade novas — mesmo padrão F86
    # (elegibilidade > tuning): o motivo SAI do eligible_jobs.json também
    # quando revelado na re-avaliação pós-hidratação.
    "native_language",
    "duration_conflict",
    "recent_graduate",
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
    # F99 (22/10) — AWS ESC 10571716 verbatim: "Candidate must be a national
    # of an EU member state and residing in the EU". Nacionalidade UE exigida
    # é a MESMA classe semântica do motivo (o dono tem passaporte BR).
    re.compile(r"\bnationals?\s+of\s+an?\s+eu\b", re.IGNORECASE),
    re.compile(r"\bcitizens?\s+of\s+an?\s+eu\s+member\s+state\b", re.IGNORECASE),
    # variante curta "EU nationals" — guard lookbehind evita o FP "non-EU
    # nationals" (o hífen é word boundary; sem o guard casaria).
    re.compile(r"(?<!non-)(?<!non )\beu\s+nationals?\b", re.IGNORECASE),
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
    # F99 (22/10) — Avery Dennison 744000155457544 verbatim: "You must be
    # currently enrolled at a Dutch university for the entire duration of
    # your internship". Matrícula em universidade HOLANDESA exigida = mesma
    # classe (o dono é matriculado na UFSCar/BR; a generalização
    # multi-país fica para fase futura com motivo próprio).
    re.compile(
        r"\benrol{1,2}ed\s+(at|in)\s+a\s+"
        r"(dutch|netherlands)\s+"
        r"(university|universiteit|hogeschool|college|research\s+university)\b",
        re.IGNORECASE,
    ),
    # F99 — YETI JR102248 verbatim (título): "Business Operations Internship
    # for AUAS Students" + desc "...at the Amsterdam University of Applied
    # Sciences". AUAS = Amsterdam University of Applied Sciences — público
    # por INSTITUIÇÃO específica NL. Contexto exigido ("at/for AUAS") para
    # a sigla; o nome por extenso é inambíguo.
    re.compile(r"\b(at|for)\s+(the\s+)?auas\b", re.IGNORECASE),
    re.compile(r"\bauas\s+students?\b", re.IGNORECASE),
    re.compile(r"\bamsterdam\s+university\s+of\s+applied\s+sciences\b", re.IGNORECASE),
]

# (2b) Matrícula em universidade ALEMÃ obrigatória (F106, 23/10) — irmã da
# classe NL acima: o dono é matriculado na UFSCar (BR), então exigir
# matrícula em Hochschule/Universität alemã é bloqueio duro da mesma
# família. Casos medidos (23/10): Continental REF99687I "Studium der
# Chemie, ... an einer deutschen Hochschule"; novemcore 14171261
# "Laufendes Bachelor- oder Master-Studium an einer deutschen Hochschule
# oder Universität"; InterNations 744000145780559 "enrolled at a German
# university"; DHL 384551 "university based in Germany" (registro 22/10 —
# fora do dataset vivo). Corpus inteiro (jobs.json 23/10, 118.785
# vagas): 98 spans "an/in einer deutschen" + 1 "Semester einer deutschen
# Hochschule" + 7 "Hochschule/Universität in Deutschland" + 27
# "(at|in) a German university" + 4 "at a university in Germany" —
# TODOS requisitos de matrícula, 0 falso positivo.
# ÂNCORAS OBRIGATÓRIAS (padrão solto "deutsche Hochschule" é proibido):
# "Immatrikulation an einer Hochschule" GENÉRICA (Bosch Pflichtpraktikum
# gem. SPO; 478 spans) NÃO é matrícula local — estudante internacional
# satisfaz; "Duale Hochschule" (BASF/KPMG/SAP DHBW) é classe DUAL
# (job_type F86) e não menciona "an/in einer deutschen"; "based in
# Germany" SOLTO é residência/localização (BASF "team based in Germany",
# Tesla "Role is based in Germany", Bayer "You are based in Germany" —
# outra classe, fora de escopo); "Studium an spannenden Projekten"
# (KPMG) não tem "einer deutschen"; "aus einer deutschen
# Erfolgsgeschichte" (Würth) não tem palavra de instituição nem
# preposição an/in.
_DE_ENROLMENT_RES = [
    # Continental REF99687I / novemcore / Fraunhofer ×N / join_com ×N /
    # eures ×N / Carrier / Essity / TU Berlin: "Studium ... an einer
    # deutschen Hochschule", "Gültige Immatrikulation an einer deutschen
    # Hochschule oder Universität", "in einer deutschen Hochschule
    # immatrikuliert" (SYNLAB), "in einer Deutschen Hochschule
    # eingeschrieben" (Believe, maiúscula irregular coberta pelo
    # IGNORECASE). GUARD EMPÍRICO (medido no corpus 23/10): em 95/95
    # spans, a palavra após "(an|in) einer deutschen" é INSTITUIÇÃO
    # (hochschule ×67, universität ×22, compostos "hochschule/
    # universität" ×2, typos "universitit"/"hochschuke",
    # fachhochschule ×1) — o padrão exige a palavra de instituição, o
    # que veda FPs do tipo "in einer deutschen Stadt"/"an einer
    # deutschen Firma" (superfície real em anúncios futuros).
    re.compile(
        r"\b(?:an|in)\s+einer\s+deutschen?\s+"
        r"(?:hochsch|universit|fachhochsch)",
        re.IGNORECASE,
    ),
    # inserção PONTUADA entre artigo-adjetivo e instituição (a única
    # forma medida com algo no meio): "an einer deutschen/europäischen
    # Hochschule oder Universität" (Fraunhofer — alemã OU europeia, o
    # dono não tem nenhuma) e "an einer deutschen (Fach-) Hochschule
    # oder Universität" (TUM Klinikum).
    re.compile(
        r"\b(?:an|in)\s+einer\s+deutschen?\s*[/((-]\s*"
        r"[\w\s/()-]{0,28}?(?:hochsch|universit|fachhochsch)",
        re.IGNORECASE,
    ),
    # egc-fmde: "mindestens im 3. Semester einer deutschen Hochschule
    # eingeschrieben" — SEM preposição an/in antes; a palavra de
    # instituição logo depois é o guard (não casa "aus einer deutschen
    # Erfolgsgeschichte", Würth — o único span não-instituição do
    # corpus inteiro).
    re.compile(
        r"\beiner\s+deutschen?\s+(?:hochsch|universit|fachhochsch)",
        re.IGNORECASE,
    ),
    # Fraunhofer ×2 / tanzstudio-gregor ×2 / sobi: "Gültige
    # Immatrikulation an einer Hochschule oder Universität in
    # Deutschland", "Eingeschrieben an Hochschule oder Universität in
    # Deutschland", "...staatlich anerkannten Hochschule in
    # Deutschland". A alternância cobre o 2º termo do par
    # "Hochschule/ Universität in Deutschland" (com espaço após a barra,
    # grafia real da fixture).
    re.compile(
        r"\b(?:hochschule|universit\w*|fachhochsch\w*)\s+in\s+deutschland\b",
        re.IGNORECASE,
    ),
    # InterNations ×3 / Aptiv ×2 / Lonza / clariness / Allianz ×2 / TE
    # Connectivity / Nordex ×2 / Hermès / akirolabs / Deutsche Börse /
    # Fraunhofer EN ×6 / qwist: "enrolled at a German university",
    # "enrolled in a German university", "Valid enrollment at a German
    # university or college", "Ongoing studies at a German university",
    # "registered student at a German university" (Hermès). O par
    # "at/in a German university" é a âncora — 27/27 spans medidos são
    # requisitos de matrícula, 0 menção cooperativa ("with a German
    # university" = 0 spans no corpus).
    re.compile(
        r"\b(?:at|in)\s+a\s+german\s+(?:university|college|hochschule)\b",
        re.IGNORECASE,
    ),
    # DHL 384551 (registro 22/10, fora do dataset vivo): "university
    # based in Germany" — a UNIVERSIDADE é que fica na Alemanha.
    re.compile(r"\buniversity\s+based\s+in\s+germany\b", re.IGNORECASE),
    # Deutsche Börse Sustainability / lano / zentioio: "Ongoing Bachelor
    # or Master's studies ... at a university in Germany", "pursuing a
    # degree ... at a university in Germany", "Currently enrolled at a
    # university in Germany (Werkstudent status required)".
    re.compile(r"\bat\s+a\s+university\s+in\s+germany\b", re.IGNORECASE),
]

# (2c) Matrícula em universidade da UE obrigatória (F111, 24/10) — irmã
# das classes NL (F37) e DE (F106) acima: o dono é matriculado na UFSCar
# (BR), então exigir matrícula em universidade/HBO de estado-membro da UE
# é bloqueio duro da mesma família. Casos medidos (24/10, corpus inteiro
# jobs.json 118.785 vagas): 7 spans Bosch Mechelen "University/College
# must be located in a member state of the EU" + 2 spans Fraunhofer
# "Enrolled student in Germany or within the EU" + 1 span gospooky
# "Enrolled at a HBO/university within the EU" = 10/10 spans REAIS,
# 0 FP → EXCLUSÃO na cascata F37.3 (não flag).
# ÂNCORAS OBRIGATÓRIAS (padrão solto "within the EU" / "in the EU" é
# proibido — guarda residência/trabalho/mercado sem enrolled+instituição):
# - "based in EU" / "work within the EU" / "sales within the EU" /
#   "remote within the EU" — residência/trabalho/mercado, sem enrolled
#   + instituição → fora de escopo (medidos 0 FP no corpus).
# - "EU-based university" SOLTO sem "enrolled" — menção cooperativa
#   ("in cooperation with an EU-based university"), não matrícula.
# - "studying in the EU" sem instituição explícita — padrão não medido
#   no corpus, defensivo.
# O detector exige a PALAVRA DE INSTITUIÇÃO (university/college/hbo/
# universität/hochschule) + verbo de matrícula/localização (enrolled/
# located/enrolled at) + âncora UE (EU / European Union / member state
# of the EU / within the EU) — a combinação das 3 âncoras é o guard.
_EU_ENROLMENT_RES = [
    # Bosch Mechelen ×7 verbatim: "your University/College must be
    # located in a member state of the EU" / "University/College must
    # be located in a member state of the EU". Âncora: instituição
    # (University/College) + located + EU member state.
    re.compile(
        r"\b(?:university|college)\b.{0,40}?"
        r"\b(?:must\s+be\s+)?located\b.{0,40}?"
        r"\b(?:member\s+state\s+of\s+the\s+eu|eu\b|european\s+union)\b",
        re.IGNORECASE,
    ),
    # Fraunhofer ×2 verbatim: "Enrolled student in Germany or within
    # the EU". Âncora: enrolled + student + within the EU. A palavra
    # "student" serve como proxy de instituição (contexto de matrícula).
    re.compile(
        r"\benrolled\b.{0,30}?"
        r"\b(?:student|at\s+a\s+(?:hbo|university|college))\b.{0,30}?"
        r"\bwithin\s+the\s+eu\b",
        re.IGNORECASE,
    ),
    # gospooky verbatim: "Enrolled at a HBO/university within the EU".
    # Âncora: enrolled at + HBO/university + within the EU.
    re.compile(
        r"\benrolled\s+at\s+a\s+\b(?:hbo|university|college)\b.{0,30}?"
        r"\bwithin\s+the\s+eu\b",
        re.IGNORECASE,
    ),
    # Variante genérica defensiva: "enrolled at ... university ... EU"
    # / "enrolled in ... university ... EU" / "located at ... university
    # ... EU" — exige as 3 âncoras (instituição + enrolled/located + EU)
    # para evitar FPs de residência/trabalho. Janela de 60 chars entre
    # âncoras medida no corpus (maior span real = 48 chars Bosch).
    re.compile(
        r"\b(?:enrolled|located)\b.{0,60}?"
        r"\b(?:university|college|hbo|hochschule|universit\w*)\b.{0,60}?"
        r"\b(?:eu\b|european\s+union|member\s+state\s+of\s+the\s+eu|within\s+the\s+eu)\b",
        re.IGNORECASE,
    ),
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


def requires_de_enrolment(title: str, description: str | None) -> bool:
    """A vaga exige matrícula em universidade ALEMÃ (F106)?"""
    return _res_fire(_DE_ENROLMENT_RES, f"{title} {description or ''}")


def requires_eu_enrolment(title: str, description: str | None) -> bool:
    """A vaga exige matrícula em universidade/HBO da UE (F111)?"""
    return _res_fire(_EU_ENROLMENT_RES, f"{title} {description or ''}")


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
        r"\bmaster'?s?\s+students?\b|\bmasterstudent\w*\b|"
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
    # F99 (22/10): apóstrofo tipográfico (U+2019/U+2018) é a MESMA grafia de
    # mestrado — 187/704 vagas do archive 20261021T090001Z carregam U+2019.
    # A cadeia normaliza antes; aqui de novo (idempotente) para chamadores
    # diretos da função pura.
    d = d.translate(_APOSTROPHE_FIX)
    # Título sem sinal: analisa a descrição removendo os trechos FP
    # (substitui por espaço para não colar palavras vizinhas).
    cleaned = _MASTER_FP_RE.sub(" ", d)
    # "Bachelor's or Master's"/"Bachelor's final year or Master's"/
    # "undergraduate or master's" não exige mestrado: o grau de BACHELOR/
    # undergraduate é aceito — neutraliza o "Master" dessas construções
    # ANTES dos padrões legítimos. F99 estende a janela do "or" (30 chars
    # sem pontuação) além do adjacente: Resmed "Bachelor's final year or
    # Master's programme" aceita o graduando do dono; Tencent "undergraduate
    # or master's degree student" idem.
    cleaned = re.sub(
        r"\bbachelor'?s?\s*(or|/|;|,|und|and)?\s*master'?s?\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(bachelor|undergraduate)'?s?[^.;:]{0,30}\b(or|/|;|,|und|and)\b"
        r"[^.;:]{0,10}master'?s?\b",
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


# ---------------------------------------------------------------------------
# F99 — Requisitos duros de elegibilidade (22/10): 6 classes de requisito que
# escaparam de TODA a triagem e chegaram ao documento de estratégia como vagas
# "aplicáveis" quando NÃO são (verificação independente do Brainstorm_Visto
# 21/10, erratas E1/E4/E5/E6/E8). Três classes são NOVAS (detectores abaixo);
# três são EXTENSÕES de motivos existentes (eu_citizenship_required,
# nl_enrolment_required, master_required — ver _EU_CITIZENSHIP_RES,
# _NL_ENROLMENT_RES e requires_master). Severidade espelhada da F85:
# requisito DURO exclui; "advantage/preferred/ideally" NÃO exclui.
# ---------------------------------------------------------------------------

# Apóstrofo tipográfico → ASCII: "Master’s" (U+2019) é a mesma grafia de
# "Master's". ROOT CAUSE medido das 3 fixtures de mestrado da F99 (ISS DACH
# JR_10438, AGFA 454965801, Oliver Wyman R_364450) e de 187/704 vagas do
# archive 20261021T090001Z (26,5% do corpus). Idempotente.
_APOSTROPHE_FIX = str.maketrans({"\u2019": "'", "\u2018": "'"})


def normalize_apostrophes(text: str | None) -> str:
    """F99 — normaliza apóstrofos tipográficos (U+2019/U+2018 → ASCII)."""
    return (text or "").translate(_APOSTROPHE_FIX)


# --- (F99-a) native_language — exigência de língua em nível NATIVO ---
# ISS STOXX JR_10434 verbatim (a vaga de MAIOR score do dataset 21/10):
# "A minimum one of the following languages to a native standard: Russian,
# Polish, German, Turkish, Danish, Swedish, Norwegian." O dono é nativo
# PT-BR — nenhuma dessas línguas é nativa dele. O german_level (F18/F85)
# vê alemão no texto e classifica ``plus`` — o contexto "one of the
# following languages" derrota o classificador de nível, por isso a classe
# é um detector PRÓPRIO.
_NATIVE_LANGUAGE_RES = [
    re.compile(r"to\s+a\s+native\s+standard", re.IGNORECASE),
    re.compile(
        r"\bnative\s+(speaker|level|proficiency|standard|command)s?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bmother\s+tongue\b", re.IGNORECASE),
    re.compile(
        r"\bnative\s+(german|english|french|dutch|danish|swedish|norwegian|"
        r"russian|polish|turkish|spanish|italian|czech|hungarian|romanian|"
        r"bulgarian|greek|portuguese)\b",
        re.IGNORECASE,
    ),
]
# Severidade F85: menção nativa com marcador SOFT perto do match NÃO exclui
# (Kraft Heinz "Ideally native Dutch speaker or at least, advanced Dutch"
# — "ideally" é preferência, não requisito).
_NATIVE_SOFT_NEAR_RE = re.compile(
    r"\b(advantage|preferred|preference|plus|desirable|nice to have|bonus|"
    r"welcome|ideally)\b",
    re.IGNORECASE,
)
_NATIVE_LANGUAGE_NAMES_RE = re.compile(
    r"\b(german|english|french|dutch|danish|swedish|norwegian|russian|polish|"
    r"turkish|spanish|italian|czech|hungarian|romanian|bulgarian|greek|"
    r"portuguese)\b",
    re.IGNORECASE,
)
_F99_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")


def _f99_sentences(text: str) -> list[str]:
    return [s for s in _F99_SENT_SPLIT.split(text) if s]


def requires_native_language(title: str | None, description: str | None) -> bool:
    """F99 — exige língua em nível NATIVO (dono é nativo PT-BR)?

    Requisito DURO de natividade exclui; marcador soft ("ideally",
    "advantage", "preferred", "plus") no raio de ±80 chars do match NÃO
    exclui (severidade F85). Se as únicas línguas nativas citadas na
    sentença forem português, o dono qualifica (nativo) — não exclui.
    """
    text = f"{normalize_apostrophes(title)} {normalize_apostrophes(description)}"
    for sent in _f99_sentences(text):
        for rx in _NATIVE_LANGUAGE_RES:
            m = rx.search(sent)
            if not m:
                continue
            if _NATIVE_SOFT_NEAR_RE.search(
                sent[max(0, m.start() - 80): m.end() + 80]
            ):
                continue
            langs = _NATIVE_LANGUAGE_NAMES_RE.findall(sent)
            if langs and all(l.lower() == "portuguese" for l in langs):
                continue
            return True
    return False


# --- (F99-b) recent_graduate — vaga destinada a RECENT-GRADUATES ---
# auto1 744000154701234 verbatim: "You are recent graduate from University,
# preferably in Business, Economics, Finance, or in another relevant
# [field]". O dono é ALUNO MATRICULADO (§16e exige matrícula ativa durante
# o estágio obrigatório) — posting que define o candidato como
# recém-formado não é aplicável. GUARD (counter-cases F99): alternativa de
# MATRÍCULA na mesma janela anula o sinal — DB Controlling LU 1445042933
# ("You are enrolled ... or have graduated ... for no more than 6 months"),
# Wellington R94939 ("Current enrolment in, or recent completion of"),
# Nestlé 1441411733 ("obtained or are currently pursuing a degree"), JDE
# 744000150326658 ("mandatory part of your studies").
_RECENT_GRADUATE_RES = [
    re.compile(r"\byou\s+are\s+(a\s+)?recent\s+graduate\b", re.IGNORECASE),
    re.compile(r"\bfor\s+recent\s+graduates?\b", re.IGNORECASE),
    re.compile(r"\brecent\s+graduates?\s+(are|is)\b", re.IGNORECASE),
    re.compile(r"\bopen\s+to\s+recent\s+graduates?\b", re.IGNORECASE),
    re.compile(r"\byou\s+have\s+recently\s+graduated\b", re.IGNORECASE),
    re.compile(r"\brecently\s+graduated\s+from\b", re.IGNORECASE),
    re.compile(r"\brecent\s+graduates?\s+(from|in)\b", re.IGNORECASE),
]
# Alternativa de matrícula na janela ±60 chars do match (a alternativa
# aparece ANTES — "student or recent graduate" / "Currently studying in, or
# recently graduated from" — ou DEPOIS — "recent graduate or nearing the
# end of your studies"). Janela, não sentença: descrições sem pontuação
# geram sentenças-gigantes e o guard por sentença engole a fixture auto1.
_ENROLLED_ALTERNATIVE_RE = re.compile(
    r"\b(students?|studying|enrolled|enrolment|enrollment|undergraduate|"
    r"pursuing|completing|nearing|final[-\s]year)\b",
    re.IGNORECASE,
)


def targets_recent_graduates(title: str | None, description: str | None) -> bool:
    """F99 — a vaga define o candidato como recém-formado (dono é matriculado)?

    OR-semantics com matrícula na mesma janela (±60 chars) NÃO exclui
    (counter-cases DB Controlling/Wellington/Nestlé/JDE — matriculado
    qualifica).
    """
    text = f"{normalize_apostrophes(title)} {normalize_apostrophes(description)}"
    for sent in _f99_sentences(text):
        for rx in _RECENT_GRADUATE_RES:
            m = rx.search(sent)
            if not m:
                continue
            lo = max(0, m.start() - 60)
            hi = min(len(sent), m.end() + 60)
            if _ENROLLED_ALTERNATIVE_RE.search(sent[lo:hi]):
                continue
            return True
    return False


# ---------------------------------------------------------------------------
# F137 (27/10) — Posting stale: posted_at > 12 meses (hard exclude).
# ---------------------------------------------------------------------------
# Threshold parametrizado: STALE_POSTING_THRESHOLD_MONTHS = 12 (default).
# Casos medidos: AXA "Praktikum Datenanalyse" 24/10/2024 (~24 meses),
# lotes Consultport 20/10 e 25/10 (~18 meses) — chegavam como NOVAS e
# eram eliminadas manualmente. posted_at ausente/inválida NÃO desclassifica
# (neutro — mesma semântica do dedup: ausente = "infinito" para frescor,
# aqui = nunca mata).
# O detector recebe o job dict completo para acessar posted_at.


def is_stale_posting(job: dict) -> bool:
    """F137 — vaga tem posted_at > 12 meses (threshold parametrizado)?

    True SOMENTE quando posted_at existe, é válida e a idade em meses
    (dias / 30.44) excede STALE_POSTING_THRESHOLD_MONTHS.

    posted_at ausente/inválida -> False (neutro, nunca mata).
    Isso segue a mesma semântica do dedup (ausente = "infinito" para frescor),
    mas aqui "infinito" = NÃO desclassifica — a vaga pode ser re-postada
    (caso Lidl) e a data antiga não deve ser motivo de exclusão.
    """
    posted = str(job.get("posted_at") or "").strip()
    if not posted:
        return False  # ausente = neutro
    try:
        ts = datetime.fromisoformat(posted)
    except ValueError:
        return False  # inválida = neutro
    # Normaliza para date (ignora time-of-day e timezone):
    # Se tem tzinfo, converte para UTC antes de extrair date;
    # se naive, assume UTC (consistente com collected_at do pipeline).
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC)
    posted_date = ts.date()
    ref_date = date.today()
    age_days = (ref_date - posted_date).days
    if age_days < 0:
        return False  # futuro (clock skew) -> não mata
    age_months = age_days / 30.44
    return age_months > STALE_POSTING_THRESHOLD_MONTHS


# --- (F99-c) duration_conflict — duração > 6 meses citada na DESCRIÇÃO ---
# Delivery Hero 744000155973854 verbatim (página viva, confirmada 22/10;
# a descrição do DATASET não carrega a frase — gap de captura upstream,
# documentado no relatório da fase): "This is a 1 Year full time Internship
# and will require full time work authorization." — 12 meses ≠ estágio
# obrigatório de ≤6 meses (§16e). O motivo existente duration_over_6m é
# TÍTULO-only (F37: 14 FPs medidos na descrição — "graduated in the last
# 12 months", "Reststudiendauer mind. 12 Monate"); este detector exige o
# token de duração ADJACENTE ao marcador de estágio na MESMA frase, com
# PISO da faixa > 6 (semântica F29/F37: faixa 6–12 começa dentro do teto
# — Edbz "6 – 12 Monate Praktikum" FICA) e guard de frase-de-data
# ("within 12 months" = prazo de elegibilidade, Kinaxis — não duração).
# A parte "full time work authorization" é trabalho da F95 (work_auth) —
# NÃO duplicada aqui.
_F99_INTERNSHIP_MARKER_RE = re.compile(
    r"\b(internship|intern\b|praktikum|praktikant|placement)\b", re.IGNORECASE
)
_F99_DURATION_TOKEN_RE = re.compile(
    r"\b(\d{1,2})(?:\s*(?:[-\u2013\u2014]|to)\s*(\d{1,2}))?\s*[-\s]?\s*"
    r"(years?|months?|monate[rs]?)\b"
    r"|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"\s*[-\s]?\s*(years?|months?|monate[rs]?)\b",
    re.IGNORECASE,
)
_F99_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_F99_DURATION_AFTER_MARKER_RE = re.compile(
    r"\b(?:is|lasts?|runs?|of|will\s+(?:be|last|run)|would\s+(?:be|last|run)|"
    r"duration\s+of)\s+(?:at\s+least\s+|around\s+|approximately\s+)?",
    re.IGNORECASE,
)
_F99_DATE_PHRASE_RE = re.compile(
    r"\b(within|less\s+than|in\s+less\s+than|deadline|by)\s*$", re.IGNORECASE
)
# conectores temporais ENTRE a duracao e o marker = a duracao nao e da vaga
# ("at least 2 years before the internship" = experiencia previa)
_F99_TEMPORAL_CONNECTOR_RE = re.compile(
    r"\b(before|prior\s+to|after|following|then|next)\b", re.IGNORECASE
)
# ruído ENTRE a duração e o marker (conjunção/verbo) = construções de outra
# informação ("graduated in the last 12 months and are looking for an
# internship" — FP medido F37) — a duração da vaga é ADJACENTE ao marker
# ("1 Year full time Internship", "12-month internship").
_F99_INTERMEDIATE_NOISE_RE = re.compile(
    r"\b(and|or|but|however|while|when|if)\b|[,;]", re.IGNORECASE
)
_F99_MARKER_LOOKAHEAD = 30  # " full time " (11) + "Internship" (10) = 21
_F99_MONTHS_CAP = 6  # teto §16e (mesma semântica do F37/F29)


def _f99_duration_months(m: "re.Match") -> "tuple[int, int]":
    """(piso, teto) em meses do token de duração casado."""
    g = m.groups()
    if g[0] is not None:
        lo = int(g[0])
        hi = int(g[1]) if g[1] else lo
        unit = g[2]
    else:
        lo = _F99_WORD_NUM[g[3].lower()]
        hi = lo
        unit = g[4]
    if hi < lo:
        lo, hi = hi, lo
    mult = 12 if unit.lower().startswith(("year", "jahr")) else 1
    return lo * mult, hi * mult


def duration_conflict_description(title: str | None, description: str | None) -> bool:
    """F99 — duração da VAGA > 6 meses citada na descrição (teto §16e)?

    Token de duração (número + ano/mês, dígitos ou palavras) ADJACENTE ao
    marcador de estágio na mesma frase: (a) duração até 20 chars ANTES do
    marcador ("This is a 1 Year full time Internship", "During this
    12-month internship") ou (b) marcador + verbo de duração + duração
    ("an internship of at least 12 months"). PISO da faixa > 6 exclui;
    faixa com piso ≤ 6 fica ("6 to 12 months"). Frase-de-data ("within 12
    months") e duração de estudo/formatura não são duração da vaga.
    """
    text = f"{normalize_apostrophes(title)} {normalize_apostrophes(description)}"
    for sent in _f99_sentences(text):
        for m in _F99_DURATION_TOKEN_RE.finditer(sent):
            lo, _hi = _f99_duration_months(m)
            if lo <= _F99_MONTHS_CAP:
                continue
            if _F99_DATE_PHRASE_RE.search(sent[: m.start()]):
                continue
            # (a) duração imediatamente antes do marcador de estágio
            post = sent[m.end(): m.end() + _F99_MARKER_LOOKAHEAD]
            if _F99_TEMPORAL_CONNECTOR_RE.search(post):
                continue
            mk = _F99_INTERNSHIP_MARKER_RE.search(post)
            if mk and not _F99_INTERMEDIATE_NOISE_RE.search(post[: mk.start()]):
                return True
            # (b) marcador seguido de verbo de duração e desta duração
            mk = _F99_INTERNSHIP_MARKER_RE.search(sent)
            if mk and mk.end() <= m.start():
                between = sent[mk.end(): m.start()]
                if (
                    len(between) <= 40
                    and _F99_DURATION_AFTER_MARKER_RE.search(between)
                ):
                    return True
    return False


def applicability_exclusion_reason(
    job: dict, *, intel_map: dict[str, dict] | None = None
) -> str | None:
    """Motivo de inaplicabilidade da vaga ao perfil do dono; None = aplicável.

    Ordem de atribuição FIRST-MATCH (a mesma vaga nunca conta 2 motivos):
    ``german_required`` → ``native_language`` → ``visa_blocked`` →
    ``thesis_title`` → ``werkstudent_puro`` → ``master_required`` →
    ``eu_citizenship_required`` → ``nl_enrolment_required`` →
    ``de_enrolment_required`` →
    ``phd_position`` → ``duration_over_6m`` → ``duration_conflict`` →
    ``full_time_permanent`` → ``job_type_non_internship`` →
    ``erasmus_program`` → ``spontaneous_pool`` → ``experience_required`` →
    ``recent_graduate``.

    - ``german_required``: ``app_intel.german_level(título+descrição)`` ==
      ``required`` (classificador F18 — o dataset não carrega o nível; a
      exclusão chama a MESMA função pura do render/digest).
    - ``native_language`` (F99): exigência de língua em nível NATIVO
      (``requires_native_language`` — ISS STOXX JR_10434 verbatim "a
      minimum one of the following languages to a native standard:
      Russian, Polish, German, Turkish, Danish, Swedish, Norwegian"; o
      dono é nativo PT-BR). O german_level vê alemão e classifica
      ``plus`` — o contexto de lista derrota o classificador de nível.
      Severidade F85: "ideally native"/"native ... would be an
      advantage" NÃO exclui.
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
    - ``de_enrolment_required`` (F106): matrícula obrigatória em
      universidade ALEMÃ (``requires_de_enrolment`` — Continental
      REF99687I verbatim "Studium der Chemie, ... an einer deutschen
      Hochschule"; novemcore "Laufendes Bachelor- oder Master-Studium an
      einer deutschen Hochschule oder Universität"; InterNations
      "enrolled at a German university"; DHL 384551 "university based in
      Germany"). Irmã da classe NL (o dono é matriculado na UFSCar/BR);
      motivo PRÓPRIO porque a legenda NL carrega 🇳🇱. Âncoras
      OBRIGATÓRIAS — "Immatrikulation an einer Hochschule" GENÉRICA
      (Bosch Pflichtpraktikum gem. SPO, 478 spans) NÃO é matrícula
      local (estudante internacional satisfaz), "Duale Hochschule" é
      classe DUAL (job_type F86) e "based in Germany" sem "university"
      é residência/localização do CANDIDATO (BASF/Tesla/Bayer — outra
      classe). Exclusão na cascata (mesma trilha NL); NÃO entra em
      ``APPLICABILITY_JSON_EXCLUSION_REASONS`` (padrão nl_enrolment).
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
    - ``recent_graduate`` (F99): ``targets_recent_graduates(título,
      descrição)`` — a vaga define o candidato como RECENT-GRADUATE
      (auto1 744000154701234 verbatim "You are recent graduate from
      University") e o dono é ALUNO MATRICULADO (§16e exige matrícula
      ativa). OR-semantics com matrícula na mesma janela (±100 chars)
      NÃO exclui (DB Controlling "enrolled ... or have graduated",
      Wellington "current enrolment in, or recent completion of",
      Nestlé "obtained or are currently pursuing", JDE "mandatory part
      of your studies").
    - ``duration_conflict`` (F99): ``duration_conflict_description`` —
      duração da VAGA > 6 meses citada na DESCRIÇÃO (teto §16e;
      Delivery Hero 744000155973854 verbatim "This is a 1 Year full
      time Internship"). Token de duração ADJACENTE ao marcador de
      estágio na mesma frase; faixa com piso ≤ 6 fica ("6 to 12
      months", Edbz "6 – 12 Monate Praktikum"); frase-de-data ("within
      12 months", Kinaxis) não é duração. Complemento da duração
      TÍTULO-only do F37 (``duration_over_6m``) — os 14 FPs medidos na
      descrição ficam fora pela adjacência.
    ``master_required``/``eu_citizenship_required``/
    ``nl_enrolment_required`` ganham EXTENSÕES F99 (mesmos motivos,
    frases novas): apóstrofo tipográfico normalizado na cadeia (U+2019 —
    root cause das fixtures ISS DACH JR_10438/AGFA/Oliver Wyman;
    "Master's students" pluralizado; neutralizador "Bachelor's final
    year or Master's"/"undergraduate or master's"), nacionalidade UE
    ("national of an EU member state", AWS ESC 10571716; "EU nationals"
    com guard non-) e matrícula NL ("enrolled at a Dutch university",
    Avery Dennison 744000155457544; AUAS/Amsterdam University of Applied
    Sciences, YETI JR102248).
    F106 (23/10): a classe de matrícula local ganha o irmão ALEMÃO
    ``de_enrolment_required`` (detector próprio ``requires_de_enrolment``,
    âncoras "an/in einer deutschen"/"einer deutschen
    Hochschule/Universität"/"in Deutschland"/"(at|in) a German
    university"/"university based in Germany"/"at a university in
    Germany") — o grep pré-fase provou que o detector F99 era CEGO à
    classe DE: Continental REF99687I e novemcore estavam no eligible
    com "an einer deutschen Hochschule" no texto.
    """
    from internship_finder.app_intel import german_level

    title = str(job.get("title") or "")
    description = job.get("description")
    # F99 (22/10): apóstrofo tipográfico (U+2019/U+2018) é a MESMA grafia de
    # grau/nível — 187/704 vagas do archive 20261021T090001Z (26,5%). A
    # normalização UMA vez na cadeia cobre TODOS os detectores (root cause
    # das 3 fixtures de mestrado que escapavam: requires_master era ASCII).
    title = normalize_apostrophes(title)
    if isinstance(description, str):
        description = normalize_apostrophes(description)
    text = f"{title} {description or ''}"

    gl = german_level(text)
    if gl is not None and gl.level == "required":
        return "german_required"

    # F99 (22/10): exigência de língua em nível NATIVO (ISS STOXX JR_10434,
    # a vaga de maior score do dataset — "to a native standard: Russian,
    # Polish, German, Turkish..."). O german_level vê alemão e classifica
    # ``plus``; o contexto "one of the following languages" exige detector
    # próprio. Severidade F85: soft ("ideally"/"advantage") NÃO exclui.
    if requires_native_language(title, description):
        return "native_language"

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

    # F106 (23/10): matrícula em universidade ALEMÃ — irmã da classe NL
    # acima (mesma cadeia F37.3, motivo próprio: a legenda NL é 🇳🇱 e a
    # DE é 🇩🇪). Posições adjacentes preservam o first-match dos motivos
    # anteriores; nenhum caso medido de overlap NL×DE no corpus.
    if requires_de_enrolment(title, description):
        return "de_enrolment_required"

    # F111 (24/10): matrícula em universidade/HBO da UE — irmã das classes
    # NL/DE acima (mesma cadeia F37.3, motivo próprio: a legenda NL é 🇳🇱,
    # a DE é 🇩🇪 e a EU é 🇪🇺). Posições adjacentes preservam o first-match;
    # overlap NL×DE×EU zero medido no corpus (detector EU não casa padrões
    # NL/DE e vice-versa); first-match NL > DE > EU.
    if requires_eu_enrolment(title, description):
        return "eu_enrolment_required"

    if requires_phd(title, description):
        return "phd_position"

    if duration_over_6m_title(title):
        return "duration_over_6m"

    # F99 (22/10): duração da VAGA > 6 meses citada na DESCRIÇÃO (teto §16e)
    # — Delivery Hero 744000155973854 "This is a 1 Year full time
    # Internship". Token de duração ADJACENTE ao marcador de estágio na
    # mesma frase; faixa com piso ≤ 6 fica; frase-de-data ("within 12
    # months") não é duração. A parte "full time work authorization" é
    # trabalho da F95 (work_auth) — não duplicada aqui.
    if duration_conflict_description(title, description):
        return "duration_conflict"

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

    # F99 (22/10): vaga destinada a RECENT-GRADUATES (auto1 744000154701234
    # verbatim "You are recent graduate from University") — o dono é ALUNO
    # MATRICULADO (§16e exige matrícula ativa). OR-semantics com matrícula
    # na mesma janela NÃO exclui (counter-cases DB Controlling/Wellington/
    # Nestlé/JDE). ÚLTIMO na ordem first-match (família perfil do candidato,
    # junto com experience_required).
    if targets_recent_graduates(title, description):
        return "recent_graduate"

    # F137 (27/10): posted_at > 12 meses → stale_posting (hard exclude).
    # Threshold parametrizado (STALE_POSTING_THRESHOLD_MONTHS = 12 default).
    # Casos medidos: AXA "Praktikum Datenanalyse" 24/10/2024 (~24 meses),
    # lotes Consultport 20/10 e 25/10 (~18 meses) — chegavam como NOVAS e
    # eram eliminadas manualmente. posted_at ausente/inválida NÃO desclassifica
    # (neutro — mesma semântica do dedup: ausente = "infinito" para frescor,
    # aqui = nunca mata).
    if is_stale_posting(job):
        return "stale_posting"

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
