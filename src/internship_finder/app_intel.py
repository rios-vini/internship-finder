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

import html as _html
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from internship_finder.filters import SENIORITY_PATTERNS, STUDENT_TYPE_PATTERNS

# ---------------------------------------------------------------------------
# Normalização de texto para os DETECTORES (item 5, auditoria pós-Fases 1–8)
# ---------------------------------------------------------------------------

# Tags HTML encontradas em descrições reais (34/390 no run 22/09; teampicnic
# usa <p>/<li>/<strong>/<h2>, softgarden <br> etc.). Entidades (&, &nbsp;)
# aparecem em 189/390. O ZWSP (\u200b) aparece no texto do STIHL.
_TAG_RE = re.compile(r"<[^>]+>")
_ZWSP = "\u200b"


def normalize_text(text: str | None) -> str:
    """Texto normalizado para os DETECTORES textuais desta camada.

    Três passos (item 5 da auditoria): ``html.unescape`` (entidades como
    ``&``/``&nbsp;``), remoção de tags HTML e normalização básica de
    whitespace (colapso de Runs + trim; ``&nbsp;``/ZWSP viram espaço).

    Delimitação crítica: alimenta SOMENTE os detectores de intel
    pós-eligibilidade (``german_level``/``work_authorization``/
    ``english_evidence``/``has_german_mention``/``job_salary`` e o extrator
    de deadline textual). NUNCA é aplicada em ``filters``/ranking-eligibilidade
    e NUNCA destrói o ``Job.description`` original — a normalização é local a
    cada chamada de detector.
    """
    if not text:
        return text or ""
    out = _html.unescape(str(text))
    out = _TAG_RE.sub(" ", out)
    out = out.replace(_ZWSP, " ")
    return " ".join(out.split())


# ---------------------------------------------------------------------------
# Idioma — inglês (evidência) e alemão (nível de exigência)
# ---------------------------------------------------------------------------

LANG_EN_PATTERNS = [r"\benglish\b", r"\benglisch"]
_LANG_EN_RE = [re.compile(p, re.IGNORECASE) for p in LANG_EN_PATTERNS]


def english_evidence(text: str | None) -> bool:
    """Evidência de inglês no título+descrição (perfil: sinal compatível)."""
    text = normalize_text(text)
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
    text = normalize_text(text)
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
    text = normalize_text(text)
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
                if kind == "verb_rev":
                    # "fließend in Deutsch"/"fluency in German" — verbo de
                    # exigencia na ordem inversa, SEM palavra branda na
                    # janela: e requisito do alemao (o fall-through anterior
                    # deixava esses casos em plus/bare — FN medido no run
                    # 22/09: STIHL "Fließend in Deutsch & Englisch").
                    local, reason = "required", kind
                    break
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

# Vocabulario que indica que o anuncio TOCA o tema (sem interromper: sem
# esse vocab, "not mentioned"). Relocation NÃO faz parte do tema (item 10
# da auditoria): mudança de cidade ≠ autorização de trabalho/imigração —
# "We support your relocation" não diz NADA sobre visto.
_WA_VOCAB = [
    r"\bvisa\w*", r"\b(work|working)?\s?permits?\w*", r"\bsponsor\w*",
    r"\barbeitserlaubnis\w*", r"\baufenthaltserlaubnis\w*",
    r"\barbeitsgenehmigung\w*", r"\baufenthaltstitel\w*",
    r"\bvisum\w*", r"\bright to work\b", r"\bwork authorization\b",
    r"\bimmigration\b", r"\b(eu-?bürger|eu?\s?bürger)\w*",
    r"\b(eu|european)\s+(citizens?|nationals?|passports?)\b",
]
# Tema + classificadores (item 10 da auditoria). O gabarito de suporte é
# BIDIRECIONAL: verbo de suporte logo ANTES (~30 chars) ou DEPOIS (~25
# chars) do tema. Temas são os do _WA_VOCAB (visa, work permit,
# arbeitserlaubnis, aufenthaltserlaubnis, arbeitsgenehmigung,
# aufenthaltstitel, visum, residence permit, work authorization, right to
# work, immigration) — relocation NÃO é tema.
_WA_THEME = (
    r"(?:\bvisa\w*|\bwork(?:ing)?\s?permits?\w*|arbeitserlaubnis\w*|"
    r"arbeitsgenehmigung\w*|aufenthaltserlaubnis\w*|aufenthaltstitel\w*|"
    r"\bvisum\w*|residence\s+permits?\w*|work\s+authorization|"
    r"right\s+to\s+work|immigration)"
)
# Verbos/nominais de suporte material ao PROCESSO de visto/autorização
# (custeio, papelada, acompanhamento). "help" só conta com TEMA na janela
# ("help identify opportunities" sem tema não é suporte de visto).
_WA_VERB = (
    r"(?:\bsupport\w*|\bassist\w*|\bhelp\w*|\bunterstütz\w*|\bunterstuetz\w*|"
    r"\bhilfe\w*|\bübernehm\w*|\buebernehm\w*|\bübernahme\b|\buebernahme\b|"
    r"\bbegleit\w*|\bbehilflich\b)"
)
# Janela: verbo ANTES do tema (~30) ou DEPOIS (~25) — dois sentidos.
_WA_SUPPORT = [
    # Ordem direta: "visa sponsorship", "sponsoring visas", "support with
    # the visa process" (verbo DEPOIS do tema, tema antes).
    r"\bvisa\w*\s+sponsor\w*",
    r"\bsponsor\w*[\w\s,()-]{0,25}(visa\w*|work\s+permits?|arbeitserlaubnis\w*|arbeitsgenehmigung\w*|aufenthaltserlaubnis\w*|visum\w*|residence\s+permits?)",
    # Tema ... depois verbo de suporte ("We support you with the visa
    # process" -> "visa process"; "Assistance with visa application
    # provided" -> assist antes, tema depois).
    rf"{_WA_THEME}[\w\s,()/-]{{0,25}}{_WA_VERB}",
    # Verbo ... depois tema ("Wir unterstützen bei der Beantragung eines
    # Visums"; "Support with residence permit application").
    rf"{_WA_VERB}[\w\s,()/-]{{0,30}}{_WA_THEME}",
    # Custeio explícito (suporte material): "Übernahme der Visakosten",
    # "visa costs covered/paid by us", "Visakosten übernehmen wir".
    r"(?:übernahme|uebernahme|coverage|covering)\s+(?:der\s+)?visa\w*(?:gebühren|kosten|gebuehren|costs?|fees?)",
    r"\bvisa\w*\s*(?:gebühren|kosten|gebuehren|costs?|fees?)\s+[\w\s,()-]{0,20}(covered|paid|übernommen|uebernommen|übernehmen|uebernehmen|by\s+us|wir)",
]
# Negação de suporte (precedência MÁXIMA — aviso útil ao candidato).
# Expandida no item 10: além de "sponsor", nega o vocab de suporte
# ("no visa support", "we do not provide visa assistance", "keine
# Unterstützung bei Visa", "ohne Übernahme der Visakosten").
_WA_NO_SUPPORT = [
    r"\bno\s+(visa\w*\s+)?sponsor\w*",
    r"\b(not|cannot|can'?t|can not|does\s+not)\w*[\w\s,()-]{0,20}sponsor\w*",
    r"\bno\s+relocat\w*", r"\bkein\w*\s+sponsor\w*", r"\bsponsor\w*\s+not\b",
    r"\bunfortunately[\w\s,()-]{0,25}sponsor\w*",
    # Negação do suporte genérico (EN): "no visa support", "we do not
    # provide visa assistance", "cannot help with visa/work permit".
    r"\bno\s+(visa\w*|work\s+permits?|work\s+authorization|residence\s+permits?)\s+(support|assistance|sponsor\w*|help)\b",
    r"\b(not|cannot|can'?t|can not|do\s+not|does\s+not|don'?t|doesn'?t)\w*"
    r"[\w\s,()-]{0,20}(provide|offer|give|help)\w*"
    r"[\w\s,()-]{0,20}(visa\w*|work\s+permits?|arbeitserlaubnis\w*|residence\s+permits?)",
    r"\bcannot\s+help\s+with\s+(the\s+)?(visa|work\s+permit|work\s+authorization|residence\s+permit)",
    # Negação do suporte genérico (DE): "keine Unterstützung bei Visa",
    # "keine Übernahme der Visakosten", "ohne Übernahme der Visa(kosten)".
    r"\bkein\w*\s+(unterstützung|hilfe)\w*[\w\s,()-]{0,25}(visa\w*|visum\w*|arbeitserlaubnis\w*|arbeitsgenehmigung\w*|aufenthalt\w*|erlaubnis\w*)",
    r"\b(ohne|kein\w*|keine)\s+übernahme\s+(?:der\s+)?visa\w*",
    # Negação de custeio EN/DE: "visa costs not covered", "Visakosten
    # werden nicht übernommen".
    r"\bvisa\w*\s*(?:gebühren|kosten|gebuehren|costs?|fees?)[\w\s,()-]{0,15}\bnot\b"
    r"[\w\s,()-]{0,15}(covered|paid|included|übernommen|uebernommen)",
    r"\bvisa\w*\s*(?:gebühren|kosten|gebuehren)[\w\s,()-]{0,15}\bnicht\b"
    r"[\w\s,()-]{0,15}(übernommen|uebernommen|übernehmen|getragen|erstattet)",
]
# Requisito de autorização JÁ EXISTENTE do candidato (aviso de barreira).
_WA_EXISTING = [
    r"\b(must|need|require|requires?)\w*[\w\s,()-]{0,30}"
    r"\b(existing\s+)?(work\s+authorization|right\s+to\s+work|"
    r"(valid\s+)?(work|working)\s+permits?|arbeitserlaubnis\w*|arbeitsgenehmigung\w*|aufenthaltstitel\w*)\b",
    r"\b(work\s+authorization|right\s+to\s+work|arbeitserlaubnis\w*|arbeitsgenehmigung\w*|aufenthaltstitel\w*)"
    r"[\w\s,()-]{0,30}\b(required|must|need|erforderlich|vorausgesetzt)\b",
    r"\b(valid|gültige|gueltige|gültiger|gueltiger)\s+(arbeits-?\s*(und|/&|und,)?\s*aufenthaltserlaubnis|"
    r"arbeits-?\s*und\s*aufenthaltserlaubnis|arbeitserlaubnis\w*|arbeitsgenehmigung\w*|"
    r"work\s+(and\s+residence\s+)?permits?|residence\s+permits?|aufenthaltstitel\w*)\b",
    r"\b(eu-?bürger|european\s+(citizens?|nationals?)|eu\s+(citizens?|nationals?))"
    r"(?:\s*(only|required|are\s+eligible))?",
    r"\baufenthaltserlaubnis\w*",
    r"\bnon-?(eu|german)\s+(citizens?|nationals?|bürgerinnen?)\s+(need|benötigen|brauchen|erforderlich|required)?\b",
    # "must already have", "already holds/possesses" + tema na sequência
    # (EN, ordem direta e inversa: "Candidates already possessing a work
    # permit" e "must already hold a valid visa").
    r"\b(must|need|have|should|candidates?|applicants?)\b[\w\s,()-]{0,15}\balready\b"
    r"[\w\s,()-]{0,25}\b(hold\w*|possess\w*|have)\w*[\w\s,()-]{0,20}"
    r"(valid\s+)?(work\s+permits?|visa\w*|arbeitserlaubnis\w*|aufenthaltstitel\w*|residence\s+permits?)",
    # DE: "vorhandene Arbeitserlaubnis/Aufenthaltstitel", "bereits
    # vorhanden", "bereits vorhanden" + tema.
    r"\bvorhandene[rnms]?\s+(arbeitserlaubnis\w*|aufenthaltstitel\w*|arbeitsgenehmigung\w*|aufenthaltserlaubnis\w*)",
    r"\b(arbeitserlaubnis\w*|aufenthaltstitel\w*|arbeitsgenehmigung\w*|aufenthaltserlaubnis\w*)"
    r"[\w\s,()-]{0,20}\bbereits\s+(vorhanden|vorliegen\w*|besitzen)\b",
    # Passaporte/cidadania EU como requisito: "valid EU passport
    # required", "EU passport required".
    r"\bvalid\s+eu\s+passport\s+(required|necessary|needed)\b"
    r"|\beu\s+passport\s+(required|necessary|needed)\b",
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
    text = normalize_text(text or "")
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

DEADLINE_KINDS = ("employer", "employer_textual", "platform_sf", "none")

# ---------------------------------------------------------------------------
# Deadline textual ESTRITO (item 8, auditoria pós-Fases 1–8)
# ---------------------------------------------------------------------------

# Prazo de candidatura EXPLICITAMENTE declarado no texto do anúncio.
# Padrão alemão comprovado no dataset (run 23/09, 6 ocorrências Fraunhofer):
# "Bewerbungsfrist: 15.10.2026". A data é OBRIGATÓRIA e imediatamente após
# o marcador (tolerância: dois pontos/hífen opcional e espaços). Negações
# ("keine Bewerbungsfrist", 4 ocorrências bahagag) NÃO casam: exigimos o
# separador de dois-pontos OU hífen seguido de data; "keine" antes do
# marcador não tem data adjacente e o match exige a data logo após.
# Variações de capitalização/espacamento suportadas (IGNORECASE + \s*).
_EMPLOYER_DEADLINE_RE = re.compile(
    r"\bbewerbungsfrist\s*[:\-]?\s*(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4})\b",
    re.IGNORECASE,
)
# Marcadores equivalentes inequívocos (mesma semântica de prazo de
# candidatura, evidência no dataset/enunciado): "Bewerbungsschluss".
_EMPLOYER_DEADLINE_LABELS = ("bewerbungsfrist", "bewerbungsschluss")
_EMPLOYER_DEADLINE_ALT_RE = re.compile(
    r"\bbewerbungsschluss\s*[:\-]?\s*(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4})\b",
    re.IGNORECASE,
)


def textual_deadline(text: str | None) -> date | None:
    """Prazo de candidatura DECLARADO NO TEXTO do anúncio; None sem evidência.

    Extração ALTAMENTE conservadora (item 8): apenas o marcador explícito
    ``Bewerbungsfrist``/``Bewerbungsschluss`` seguido IMEDIATAMENTE de data
    DD.MM.YYYY válida. Nada de NLP, frases ambíguas, posted_at+N dias,
    expiration_date de plataforma ou data de publicação. Datas passadas ou
    futuras são preservadas com o significado intacto (o consumidor decide
    urgência; a extração não altera o significado).
    """
    if not text:
        return None
    text = normalize_text(text)
    for rx in (_EMPLOYER_DEADLINE_RE, _EMPLOYER_DEADLINE_ALT_RE):
        m = rx.search(text)
        if not m:
            continue
        try:
            return date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        except ValueError:
            continue  # data inválida (ex.: 32.13.2026) -> sem deadline
    return None

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
    """Classe do ``application_deadline``: employer / employer_textual /
    platform_sf / none.

    Precedência (mais forte primeiro):

    1. Campo estruturado em fonte NÃO-SuccessFactors -> ``employer``
       (prazo real do empregador exposto pelo ATS; regra Fase 6).
    2. Prazo DECLARADO NO TEXTO do anúncio (``Bewerbungsfrist:
       DD.MM.YYYY`` — extrator estrito do item 8) -> ``employer_textual``.
    3. Campo estruturado em tenant SuccessFactors -> ``platform_sf``
       (validade de feed g:expiration_date = collected+30d, NUNCA prazo).
    4. Nenhum -> ``none``.
    """
    structural = _as_date(_deadline_value(job))
    source = str((job.to_dict() if hasattr(job, "to_dict") else job).get("source") or "")
    textual = textual_deadline(
        f"{_title_of(job)} {_description_of(job)}"
    )
    if structural is not None and not source.startswith(SF_SOURCE_PREFIX):
        return "employer"
    if textual is not None:
        return "employer_textual"
    if structural is not None:
        return "platform_sf"
    return "none"


def _title_of(job: dict[str, Any] | Any) -> str:
    d = job.to_dict() if hasattr(job, "to_dict") else job
    return str(d.get("title") or "")


def _description_of(job: dict[str, Any] | Any) -> str:
    d = job.to_dict() if hasattr(job, "to_dict") else job
    return str(d.get("description") or "")


def _deadline_value(job: dict[str, Any] | Any) -> Any:
    d = job.to_dict() if hasattr(job, "to_dict") else job
    return d.get("application_deadline")


def deadline_date(job: dict[str, Any] | Any) -> date | None:
    """Data do deadline CLASSIFICADO (mapeada, nunca derivada).

    Para ``employer``/``platform_sf`` é o valor estrutural da fonte; para
    ``employer_textual`` é a data extraída do texto (item 8). Sem deadline
    -> ``None`` (nunca inventa).
    """
    if deadline_kind(job) == "employer_textual":
        return textual_deadline(
            f"{_title_of(job)} {_description_of(job)}"
        )
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
    if kind in ("employer", "employer_textual") and dl is not None:
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
    elif kind == "employer_textual":
        flags.append({"key": "deadline_textual", "detail": "", "severity": "info"})

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