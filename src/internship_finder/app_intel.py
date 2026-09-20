"""Application Intelligence — Fase 6 (Candidate Fit + Application Intelligence).

Camada DETERMINISTICA e pura sobre os dados reais da vaga (titulo +
descricao + campos do Job). Nenhum valor e inventado: tudo que esta aqui
sai de evidencias no proprio anuncio ou de campos da fonte.

Conceitos SEPARADOS (enunciado da Fase 6) — nao confundir:

- **Relevancia** (score): quanto a vaga combina com o perfil (ranking.py).
- **Candidate Fit**: sinais objetivos de candidatura (tipo, pais, idioma,
  autorizacao, dados presentes).
- **Urgencia**: quanto tempo resta ate o deadline CONFIRMADO do empregador.
- **Work authorization**: autorizacao de trabalho, classificada SOMENTE por
  evidencias explicitas no anuncio.
- **Limite importante (medido no run 19/09, 476 eligible)**: os 295
  ``application_deadline`` existentes sao TODOS de tenants SuccessFactors e
  valem EXATAMENTE ``collected_at + 30 dias`` (295/295). Isso e a
  ``g:expiration_date`` do feed Google Merchant da plataforma — horizonte de
  validade do anuncio, NAO prazo de candidatura definido pelo empregador.
  Por isso este modulo trata esses valores como ``platform_sf`` (validade de
  feed) e os EXCLUI de urgencia/"vagas expirando"; nunca os apresenta como
  deadline. Se uma fonte externa com prazo real aparecer, ela cai em
  ``employer`` automaticamente (a regra e por fonte/ATS, nao por data).
- **Nunca inventar deadline**: ``first_seen + N dias`` ou qualquer outra
  derivacao NAO entra aqui (AGENTS.md + enunciado Fase 6).

Idioma (novo tratamento — Fase 6):

- **Ingles**: qualquer evidencia de ingles no titulo+descricao e sinal
  COMPATIVEL com o perfil (+1.5 no score, mantido do ranking) — o perfil do
  dono e em ingles; ausencia nao penaliza.
- **Alemao**: classificacao por intensidade da EXIGENCIA, usando o TEXTO do
  anuncio (nunca o idioma em que o anuncio foi escrito):
    required  -> penalidade forte (ranking: PENALTY_LANG_DE_REQUIRED)
    preferred -> penalidade menor   (ranking: PENALTY_LANG_DE_PREFERRED)
    plus      -> neutro (mencoes difusas: "alemao" citado sem exigencia)
    none      -> neutro (sem mencao)
  Regras de classificacao (validacao no conjunto real 19/09, 476 vagas):
  para CADA mencao a alemao (tokens), os qualificadores dentro de uma janela
  de +/-45 chars sao avaliados por PROXIMIDADE e o sinal mais forte vence:
  negacao explicita ("no German required") -> plus (sem barreira);
  verbo de exigencia (fliessend, verhandlungssicher, erforderlich,
  required/must/fluent/native, "in Wort und Schrift", nivel CEFR A1-C2,
  "deutschsprachiges Team/Umfeld") -> required;
  qualificador de intensidade diretamente ligado a lingua ("sehr gute
  Deutschkenntnisse", "very good German") -> required;
  "preferred/desirable/plus/von Vorteil/wunschenswert" ligado a mencao ->
  preferred; par "German and English" sem intensidade -> preferred;
  "basic/Grundkenntnisse" -> preferred;
  mencao nua ("deutschkenntnisse" sem qualificador) -> preferred;
  demais mencoes (ex.: "Deutschland", "Deutsche Bahn", "deutschsprachig"
  solto) -> plus.
  Detalhe de implementacao: "deutsch" SOLTO nunca e token ("Deutschland",
  "deutsche Gesellschaft", empresa "Deutsche Bahn" nao indicam idioma);
  "german" e word-bounded (nao pega "Germany"); "gutes Praktikum" nao
  qualifica lingua porque exige termo de lingua/kenntnisse logo apos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from internship_finder.filters import SENIORITY_PATTERNS, STUDENT_TYPE_PATTERNS

# ---------------------------------------------------------------------------
# Idioma — inglês (evidencia) e alemão (nivel de exigência)
# ---------------------------------------------------------------------------

LANG_EN_PATTERNS = [r"\benglish\b", r"\benglisch"]
_LANG_EN_RE = [re.compile(p, re.IGNORECASE) for p in LANG_EN_PATTERNS]


def english_evidence(text: str | None) -> bool:
    """Evidencia de ingles no titulo+descricao (perfil: sinal compativel)."""
    return bool(text) and any(rx.search(text) for rx in _LANG_EN_RE)


# Tokens de mencao a alemao COMO IDIOMA (word-bounded; "Deutschland" e
# "deutsche + nome proprio/empresa" nao sao tokens — nao indicam idioma).
GERMAN_TOKEN_PATTERNS: list[str] = [
    r"\bgerman\b",
    r"\bdeutsch\b",  # "Deutsch", "auf Deutsch", "Deutsch- und Englischkenntnisse"
    r"\bdeutschkenntnisse\b",
    r"\bdeutschsprachig\w*",
    # Par "deutscher und englischer (Sprache)..." — sempre mencao de idioma.
    r"\bdeutsch(er|e|en)?\b\s+(und|&|bzw\.?)?\s*(englisch(er|e|en)?|englische?)\b",
]
_GERMAN_TOKEN_RE = [re.compile(p, re.IGNORECASE) for p in GERMAN_TOKEN_PATTERNS]

# Qualificadores ancorados (pattern, kind). A JANELA e de +/-45 chars em
# volta do token; regras por ordem de prioridade (a primeira que casar na
# janela define a classe local) e o sinal MAIS FORTE agregado
# (required > preferred > plus) vence no final.
_GERMAN_QUALS: list[tuple[str, str]] = [
    # Negacao explicita -> sem barreira (plus); vence sempre ("no German
    # required", "Keine Deutschkenntnisse erforderlich").
    (
        r"\b(no|not|kein\w*|ohne)\b[\w\s,()-]{0,22}\b"
        r"(required|requirement|vorausgesetzt|erforderlich|n"
        r"ötig|noetig|notwendig|pflicht|needed|need)\b",
        "negated",
    ),
    # Verbo de exigencia na ORDEM DIRETA ("German required", "Deutschkenntnisse
    # vorausgesetzt"): o alemao e o SUJEITO da exigencia.
    (
        r"\b(german|deutsch\w*)\b[\w\s,()-]{0,35}\b"
        r"(required|essential|mandatory|must|fluent|fluency|native|pflicht|"
        r"erforderlich|vorausgesetzt|erwartet|zwingend|notwendig)\b",
        "verb_direct",
    ),
    # Frase explicita de comunicacao nas duas linguas.
    (r"in deutscher und englischer sprache|in english and german", "verb_explicit"),
    (r"\bin wort und schrift\b", "verb"),
    (r"\b(a1|a2|b1|b2|c1|c2)\b", "verb"),  # nivel CEFR explicito
    (
        r"\bdeutschsprachig\w*\s*(team|umfeld|arbeitsumfeld|abteilung|"
        r"environment|kunden|raum)\b",
        "verb",
    ),
    # Qualificador de intensidade DIRETAMENTE ligado a lingua/kenntnisse.
    (
        r"(sehr\s+)?(gute|guter|gutes|solide|solider|fundierte|fundierter|"
        r"exzellente|ausgezeichnete|umfassende|sicher(er|e)?|excellent|"
        r"very good|good|advanced|strong)\s+[\w\s,&()-]{0,26}\b"
        r"(deutsch\w*|\bgerman\b|kenntnisse\w*|sprachkenntnisse\w*|"
        r"sprachliche\w*|sprache\b|skills\b)\b",
        "qual",
    ),
    # Par com palavra de idioma logo depois: "Sprache/Language/Kenntnisse/
    # Skills" apos "Deutsch und Englisch" -> requisito das duas linguas.
    (
        r"\b(english|englisch\w*)\b[\w\s,()-]{0,15}\b(and|und|&)\b"
        r"[\w\s,()-]{0,15}\b(german|deutsch\w*)\b"
        r"[\w\s,()-]{0,25}\b(sprache\w*|language\w*|kenntnisse\w*|skills)\b|"
        r"\b(german|deutsch\w*)\b[\w\s,()-]{0,15}\b(and|und|&)\b"
        r"[\w\s,()-]{0,15}\b(english|englisch\w*)\b"
        r"[\w\s,()-]{0,25}\b(sprache\w*|language\w*|kenntnisse\w*|skills)\b",
        "pair_strong",
    ),
    # Verbo de exigencia na ORDEM INVERSA ("We require German") — so quando
    # NAO ha palavra branda na janela (senao "English required, German is a
    # plus" viraria required: a exigencia e do INGLES, nao do alemao).
    (
        r"\b(required|essential|mandatory|must|fluent|fluency|native|"
        r"fließend|fliessend|verhandlungssicher)\w*[\w\s,()-]{0,30}\b"
        r"(german|deutsch\w*)\b",
        "verb_rev",
    ),
    # "preferred/plus/von Vorteil" na janela -> preferido.
    (
        r"\b(plus|preferred|desirable|an asset|a plus|advantage|beneficial|"
        r"advantageous|nice to have|von vorteil|wünschenswert|wunschenswert|"
        r"bevorzugt|idealerweise|gerne gesehen|ein plus|good to have)\b",
        "soft",
    ),
    # Par "German and English" / "Englisch und Deutsch" sem intensidade.
    (
        r"\b(german|deutsch\w*)\b[\w\s,()-]{0,15}\b(and|und|&)\b"
        r"[\w\s,()-]{0,15}\b(english|englisch\w*)\b|"
        r"\b(english|englisch\w*)\b[\w\s,()-]{0,15}\b(and|und|&)\b"
        r"[\w\s,()-]{0,15}\b(german|deutsch\w*)\b",
        "pair",
    ),
    (r"\b(basic|grundkenntnisse|grundlegend)\w*", "basic"),
]
_GERMAN_QUALS_RE = [(re.compile(p, re.IGNORECASE), kind) for p, kind in _GERMAN_QUALS]

GERMAN_LEVELS = ("required", "preferred", "plus", "none")
_LEVEL_PRIO = {"required": 3, "preferred": 2, "plus": 1}

# Razao da classificacao (para explicabilidade na interface).
GERMAN_REASONS = (
    "verb", "qual", "soft", "pair", "basic", "negated", "bare",
)


@dataclass(frozen=True)
class GermanLevel:
    """Nivel de exigencia de alemao + razao (evidencia que venceu)."""

    level: str
    reason: str


def has_german_mention(text: str | None) -> bool:
    if not text:
        return False
    return any(rx.search(text) for rx in _GERMAN_TOKEN_RE)


def german_level(text: str | None) -> GermanLevel | None:
    """Nivel de exigencia de alemao no titulo+descricao; None = sem mencao.

    Deterministico e independente do idioma do anuncio: so sentencas com
    evidencias de requisito (ou negacao) mudam de ``plus``. Para cada token
    de mencao, a janela +-45 chars e avaliada; o primeiro qualificador que
    casar define a classe daquela mencao; o SINAL MAIS FORTE de todas as
    mencoes vence (required > preferred > plus).
    """
    if not text:
        return None
    tokens: list[re.Match] = []
    for rx in _GERMAN_TOKEN_RE:
        tokens.extend(rx.finditer(text))
    if not tokens:
        return None
    best_level = "plus"
    best_reason = "bare"
    _TIGHT_SOFT_RE = re.compile(
        r"\b(plus|preferred|desirable|an asset|a plus|von vorteil|"
        r"wünschenswert|wunschenswert|bevorzugt|idealerweise|nice to have|"
        r"good to have|gerne gesehen|ein plus|advantage|beneficial)\b",
        re.IGNORECASE,
    )
    for m in tokens:
        win = text[max(0, m.start() - 45): min(len(text), m.end() + 45)]
        local, reason = "plus", "bare"
        # Palavra branda GRUDADA a mencao (+-25 chars) qualifica a lingua em
        # si ("German is a plus. English required" -> preferido: a exigencia
        # forte e do ingles, nao do alemao).
        tight = _TIGHT_SOFT_RE.search(
            text[max(0, m.start() - 25): min(len(text), m.end() + 25)]
        )
        if tight:
            local, reason = "preferred", "soft"
        else:
            soft_in_win = any(
                rx.search(win) for rx, kind in _GERMAN_QUALS_RE if kind == "soft"
            )
            for qrx, kind in _GERMAN_QUALS_RE:
                if not qrx.search(win):
                    continue
                if kind == "negated":
                    local, reason = "plus", "negated"
                    break
                if kind == "verb_rev" and soft_in_win:
                    continue  # a exigencia provavelmente e do ingles
                if kind in ("verb", "verb_direct", "verb_explicit",
                            "pair_strong", "qual"):
                    local, reason = "required", kind
                    break
                if kind in ("soft", "pair", "basic"):
                    local, reason = "preferred", kind
        if _LEVEL_PRIO[local] > _LEVEL_PRIO[best_level]:
            best_level, best_reason = local, reason
    return GermanLevel(level=best_level, reason=best_reason)


# ---------------------------------------------------------------------------
# Work authorization — estados por EVOLUÇÃO EXPLÍCITA no anuncio
# ---------------------------------------------------------------------------

# Vocabulario que indica que o anuncio TOCA o tema (sen interromper: sem
# esse vocab, "not mentioned").
_WA_VOCAB = [
    r"\bvisa\w*", r"\b(work|working)?\s?permits?\w*", r"\bsponsor\w*",
    r"\brelocat\w*", r"\barbeitserlaubnis\w*", r"\baufenthaltserlaubnis\w*",
    r"\bvisum\w*", r"\bright to work\b", r"\bwork authorization\b",
    r"\bimmigration\b", r"\b(eu-?bürger|eu?\s?bürger)\w*",
    r"\b(eu|european)\s+(citizens?|nationals?|passports?)\b",
]
_WA_SUPPORT = [
    r"\bvisa\w*\s+sponsor\w*",
    r"\bsponsor\w*[\w\s,()-]{0,25}(visa\w*|work\s+permits?|arbeitserlaubnis\w*|visum\w*)",
    r"\b(visa\w*|work\s+permits?|arbeitserlaubnis\w*|visum\w*)[\w\s,()-]{0,25}"
    r"\b(support\w*|sponsor\w*|übernehm\w*|uebernehm\w*|assist\w*|help\w*)",
    r"\brelocat\w*[\w\s,()-]{0,20}(support|assistance|package|benefit|allowance)",
    r"\b(support|assistance|package)[\w\s,()-]{0,20}relocat\w*",
]
_WA_NO_SUPPORT = [
    r"\bno\s+(visa\w*\s+)?sponsor\w*",
    r"\b(not|cannot|can'?t|can not|does\s+not)\w*[\w\s,()-]{0,20}sponsor\w*",
    r"\bno\s+relocat\w*", r"\bkein\w*\s+sponsor\w*", r"\bsponsor\w*\s+not\b",
    r"\bunfortunately[\w\s,()-]{0,25}sponsor\w*",
]
_WA_EXISTING = [
    r"\b(must|need|require|requires?)\w*[\w\s,()-]{0,30}"
    r"\b(existing\s+)?(work\s+authorization|right\s+to\s+work|"
    r"(valid\s+)?(work|working)\s+permits?|arbeitserlaubnis\w*)\b",
    r"\b(work\s+authorization|right\s+to\s+work|arbeitserlaubnis\w*)"
    r"[\w\s,()-]{0,30}\b(required|must|need)\b",
    r"\b(valid|gültige|gueltige)\s+(arbeits-?\s*und\s*aufenthaltserlaubnis|"
    r"arbeitserlaubnis|work\s+(and\s+residence\s+)?permits?|"
    r"residence\s+permits?)\b",
    r"\b(eu-?bürger|european\s+(citizens?|nationals?)|eu\s+(citizens?|nationals?))"
    r"(?:\s*(only|required|are\s+eligible))?",
    r"\baufenthaltserlaubnis\w*",
    r"\bnon-?(eu|german)\s+(citizens?|nationals?)\s+need\b",
]
_WA_VOCAB_RE = [re.compile(p, re.IGNORECASE) for p in _WA_VOCAB]
_WA_SUPPORT_RE = [re.compile(p, re.IGNORECASE) for p in _WA_SUPPORT]
_WA_NO_SUPPORT_RE = [re.compile(p, re.IGNORECASE) for p in _WA_NO_SUPPORT]
_WA_EXISTING_RE = [re.compile(p, re.IGNORECASE) for p in _WA_EXISTING]

# Ordem de precedencia: negacao vence suporte ("no sponsorship" e aviso);
# suporte vence "existing" quando ambos aparecem (empresa suporta, mas ja
# pede autorizacao atual vale o aviso mais util ao candidato).
WORK_AUTH_STATES = (
    "support", "existing_required", "no_sponsorship", "unclear", "not_mentioned",
)


def work_authorization(text: str | None) -> dict[str, str]:
    """Estado de autorizacao de trabalho por EVIDENCIA no anuncio.

    Nunca inferida de empresa multinacional/localizacao: sem vocab -> 
    ``not_mentioned``; vocab sem classificacao -> ``unclear``.
    """
    text = text or ""
    if not any(rx.search(text) for rx in _WA_VOCAB_RE):
        return {"state": "not_mentioned", "detected": "no_vocab"}
    if any(rx.search(text) for rx in _WA_NO_SUPPORT_RE):
        return {"state": "no_sponsorship", "detected": "no_support"}
    if any(rx.search(text) for rx in _WA_SUPPORT_RE):
        return {"state": "support", "detected": "support"}
    if any(rx.search(text) for rx in _WA_EXISTING_RE):
        return {"state": "existing_required", "detected": "existing"}
    return {"state": "unclear", "detected": "vocab_unclassified"}


# ---------------------------------------------------------------------------
# Deadline / urgencia
# ---------------------------------------------------------------------------

# Precedencia de fontes (regra documentada no enunciado Fase 6 + PROJECT
# STATUS "application_deadline em tenants SuccessFactors"): tenants
# successfactors publicam SOMENTE g:expiration_date (feed = collected+30d).
SF_SOURCE_PREFIX = "successfactors:"

DEADLINE_KINDS = ("employer", "platform_sf", "none")

URGENCY_GREEN = 14   # > 14 dias
URGENCY_YELLOW = 7   # 7-14 dias
URGENCY_ORANGE = 3   # 3-6 dias
URGENCY_RED = 2      # <= 2 dias (ou vencida)


def _as_date(value: Any) -> date | None:
    """Data de um valor ISO/datetime/date; None se invalido (nunca inventa)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def deadline_kind(job: dict[str, Any] | Any) -> str:
    """Classe do ``application_deadline``: employer / platform_sf / none."""
    if not _as_date(_deadline_value(job)):
        return "none"
    source = str((job.to_dict() if hasattr(job, "to_dict") else job).get("source") or "")
    if source.startswith(SF_SOURCE_PREFIX):
        return "platform_sf"
    return "employer"


def _deadline_value(job: dict[str, Any] | Any) -> Any:
    d = job.to_dict() if hasattr(job, "to_dict") else job
    return d.get("application_deadline")


def deadline_date(job: dict[str, Any] | Any) -> date | None:
    """Data crua da fonte (mapeada, nunca derivada)."""
    return _as_date(_deadline_value(job))


def days_until(target: date | None, ref: date) -> int | None:
    """Dias entre ``ref`` (hoje do run) e o deadline; None sem deadline."""
    if target is None:
        return None
    return (target - ref).days


def urgency_color(days_left: int | None) -> str | None:
    """Cor de urgencia padrao do enunciado (so para deadline EMPLOYER).

    Faixas: verde > 14 dias; amarela 7-14; laranja 3-6; vermelha <= 2
    (inclui vencida/negativa).
    """
    if days_left is None:
        return None
    if days_left > URGENCY_GREEN:
        return "green"
    if days_left >= URGENCY_YELLOW:
        return "yellow"
    if days_left >= URGENCY_ORANGE:
        return "orange"
    return "red"  # <= 2 dias ou vencida


def snapshot_ref_date(jobs: list[dict[str, Any]]) -> date:
    """Data de referencia do snapshot = data do run (max(collected_at)).

    Usada para determinismo de urgencia (a pagina regenerada a cada run usa
    o run atual, nao "hoje" arbitrario). Nunca inventa deadline.
    """
    ref: str | None = None
    for j in jobs:
        ts = str((j.to_dict() if hasattr(j, "to_dict") else j).get("collected_at") or "")
        if ts and (ref is None or ts > ref):
            ref = ts
    if ref:
        parsed = _as_date(ref)
        if parsed:
            return parsed
    return date.today()


def parse_ref_date(value: str | date | datetime | None) -> date:
    """Converte ``--ref-date`` (YYYY-MM-DD), datetime ou date; None = hoje."""
    if value is None:
        return datetime.now().date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


# ---------------------------------------------------------------------------
# Candidate fit — sinais objetivos de candidatura (nunca inventa)
# ---------------------------------------------------------------------------


def candidate_fit(job: dict[str, Any] | Any) -> list[dict]:
    """Sinais objetivos de candidatura a partir dos DADOS REAIS da vaga.

    Cada sinal: ``{"key", "kind", "label_hint"}`` onde kind e:
    ``ok`` (verde), ``warn`` (problema objetivo), ``info`` (neutro/info).
    O texto PT-BR final e montado pela camada ptbr (glossario Fase 5).
    """
    d = job.to_dict() if hasattr(job, "to_dict") else job
    title = str(d.get("title") or "")
    text = f"{title} {d.get('description') or ''}"
    employment_type = str(d.get("employment_type") or "").strip()

    student_type = bool(
        re.search(r"|".join(STUDENT_TYPE_PATTERNS), title, re.IGNORECASE)
    ) or bool(re.search(r"werkstudent|working student|student(ische|er)?",
                        title, re.IGNORECASE))
    sign: list[dict] = [
        {
            "key": "germany",
            "kind": "ok" if str(d.get("country_iso") or "").casefold() == "de" else "info",
        },
        {
            "key": "student_type",
            "kind": "ok" if student_type else "info",
            "detail": employment_type or None,
        },
        {
            "key": "english",
            "kind": "ok" if english_evidence(text) else "info",
        },
        {
            "key": "location_known",
            "kind": "ok" if (d.get("location") or "").strip() else "warn",
        },
        {
            "key": "description_known",
            "kind": "ok" if (d.get("description") or "").strip() else "info",
        },
    ]
    de = german_level(text)
    if de is not None and de.level != "none":
        sign.append({
            "key": "german",
            "kind": "warn" if de.level == "required" else "info",
            "detail": de.level,
        })
    wa = work_authorization(text)["state"]
    if wa in ("existing_required", "no_sponsorship", "unclear"):
        sign.append({"key": "work_auth", "kind": "warn", "detail": wa})
    elif wa == "support":
        sign.append({"key": "work_auth", "kind": "ok", "detail": wa})
    else:
        sign.append({"key": "work_auth", "kind": "info", "detail": wa})
    return sign


# ---------------------------------------------------------------------------
# Problemas possiveis (SO objetivos) e quality flags
# ---------------------------------------------------------------------------


def possible_problems(job: dict[str, Any] | Any, ref: date) -> list[dict]:
    """Problemas objetivos de candidatura; apenas com evidencia no anuncio.

    Retorna ``[{"key", "detail", "severity"}]`` — nunca opiniao sobre
    empresa/vaga; o texto PT-BR e responsabilidade da camada ptbr.
    """
    d = job.to_dict() if hasattr(job, "to_dict") else job
    title = str(d.get("title") or "")
    text = f"{title} {d.get('description') or ''}"
    problems: list[dict] = []

    de = german_level(text)
    if de is not None and de.level == "required":
        problems.append({"key": "german_required", "detail": de.reason,
                         "severity": "hard"})
    elif de is not None and de.level == "preferred":
        problems.append({"key": "german_preferred", "detail": de.reason,
                         "severity": "soft"})

    wa = work_authorization(text)["state"]
    if wa == "existing_required":
        problems.append({"key": "wa_existing", "detail": "", "severity": "hard"})
    elif wa == "no_sponsorship":
        problems.append({"key": "wa_no_sponsorship", "detail": "", "severity": "hard"})
    elif wa == "unclear":
        problems.append({"key": "wa_unclear", "detail": "", "severity": "soft"})

    kind = deadline_kind(d)
    dl = deadline_date(d)
    if kind == "employer" and dl is not None:
        days = days_until(dl, ref)
        problems.append({
            "key": "deadline",
            "detail": f"{dl.isoformat()}|{days}",
            "severity": "hard" if (days is not None and days <= URGENCY_RED) else "soft",
        })
    elif kind == "platform_sf" and dl is not None:
        days = days_until(dl, ref)
        if days is not None and days < 0:
            problems.append({
                "key": "sf_validity_passed",
                "detail": f"{dl.isoformat()}|{days}",
                "severity": "hard",
            })

    has_student_type = bool(
        re.search(r"|".join(STUDENT_TYPE_PATTERNS), title, re.IGNORECASE)
    )
    if not has_student_type and any(
        re.search(p, title, re.IGNORECASE) for p in SENIORITY_PATTERNS
    ):
        problems.append({"key": "senior_title", "detail": "", "severity": "hard"})

    return problems


def quality_flags(job: dict[str, Any] | Any, ref: date) -> list[dict]:
    """Flags de QUALIDADE dos dados (objetivas); nao julga a empresa."""
    d = job.to_dict() if hasattr(job, "to_dict") else job
    title = str(d.get("title") or "")
    desc = str(d.get("description") or "").strip()
    text = f"{title} {desc}"
    flags: list[dict] = []

    kind = deadline_kind(d)
    if kind == "none":
        flags.append({"key": "no_deadline", "detail": "", "severity": "info"})
    elif kind == "platform_sf":
        flags.append({"key": "platform_validity", "detail": "", "severity": "info"})

    if not (d.get("location") or "").strip():
        flags.append({"key": "no_location", "detail": "", "severity": "info"})
    if len(desc) < 200:
        flags.append({"key": "short_description", "detail": str(len(desc)),
                      "severity": "info"})
    if not english_evidence(text) and not has_german_mention(text):
        flags.append({"key": "no_language", "detail": "", "severity": "info"})

    posted = _as_date(d.get("posted_at"))
    if posted is not None:
        age = (ref - posted).days
        if age > 60:
            flags.append({"key": "old_posting", "detail": str(age),
                          "severity": "info"})
    return flags


# ---------------------------------------------------------------------------
# Application readiness (so a partir dos sinais objetivos acima)
# ---------------------------------------------------------------------------

READINESS_READY = "ready"
READINESS_VERIFY = "verify"


def application_readiness(problems: list[dict]) -> str:
    """'ready' = ZERO problemas objetivos; qualquer sinal -> 'verify'."""
    return READINESS_READY if not problems else READINESS_VERIFY