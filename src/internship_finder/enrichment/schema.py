"""Schema do enrichment — contrato de dados da camada LLM (enrichment v1).

Cada record identifica a vaga (job_id), a origem (source/original_url/final_url)
e a extracao POR CAMPO com evidencia literal e confianca. Nada e inventado:
``true``/``false`` EXIGEM citacao <=200 chars do texto da pagina; ausencia de
informacao e ``not_mentioned`` (NUNCA ``false``); evidencia conflitante,
insuficiente ou CONDICIONAL e ``unclear``.

Taxonomia de work authorization CORRIGIDA — conceitos DISTINTOS, nunca
sinonimos (o spike 24/09 mediu 2 falsos positivos reais por sinonimia):

1. ``student_status_required`` — exige matricula universitaria
   (Immatrikulation/enrolled). NOTA: comprovar matricula NAO comprova
   autorizacao de trabalho, sponsorship nem residence permit — cada campo
   e avaliado INDEPENDENTEMENTE.
2. ``work_authorization_required`` — afirmacao generica de que alguma
   autorizacao de trabalho e necessaria, sem especificar qual.
3. ``existing_work_authorization_required`` — exige que o candidato JA
   POSSUA autorizacao valida (ex. "must already hold a valid work permit").
   Frase CONDICIONAL (ggf. / falls erforderlich / if applicable) NUNCA e
   ``true`` — e ``unclear`` com a evidencia.
4. ``work_permit_required`` — mencao explicita a Arbeitserlaubnis/work
   permit COMO REQUISITO (mesma regra do condicional).
5. ``residence_permit_required`` — mencao explicita a
   Aufenthaltserlaubnis/residence permit COMO REQUISITO (mesma regra).
6. ``visa_sponsorship`` — o empregador patrocina/cobre/assiste visto.
   Ausencia de promocao de visto NAO e ``false`` — e ``not_mentioned``.
7. ``international_candidates_explicitly_accepted`` — aceitacao EXPLICITA
   de candidatos internacionais na VAGA; frase generica de DEI da EMPRESA
   nao conta (FP real medido no spike: frase da Bayer).
8. ``eu_citizenship_required`` — cidadania UE explicitamente exigida.

``schema_version`` e constante 1: migracoes futuras leem esse campo para
saber como interpretar records antigos.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# ---------------------------------------------------------------------------
# Constantes do contrato
# ---------------------------------------------------------------------------

EXTRACTOR = "llm-glm-5.3-flash"
SCHEMA_VERSION = 1
EVIDENCE_MAX_CHARS = 200
CONTENT_LIMIT = 12000

# Marcadores CONDICIONAIS — guardas deterministicas pos-LLM (defense in
# depth: o prompt ensina a regra, o normalizador confere). "oder" fica SO no
# prompt: "Arbeitserlaubnis oder Aufenthaltstitel erforderlich" continua sendo
# requisito duro; o guarda usa apenas marcadores de alta precisao (medidos no
# spike: "sowie ggf. eine gueltige Arbeits- und Aufenthaltserlaubnis").
_CONDITIONAL_MARKERS: tuple[str, ...] = (
    "ggf.", "ggf ", "falls erforderlich", "falls notwendig", "falls gegeben",
    "if applicable", "if required", "if necessary", "where applicable",
    "where required", "sofern erforderlich", "nach moeglichkeit",
    "nach möglichkeit",
)

# Frases genericas de DEI da EMPRESA — nao sao aceitacao explicita de
# candidatos internacionais na VAGA (FP real do spike, frase da Bayer).
_DEI_MARKERS: tuple[str, ...] = (
    "ungeachtet", "regardless of", "equal opportunity", "aller menschen",
    "alle menschen", "all people", "all humans", "diversity",
)


# ---------------------------------------------------------------------------
# Enums de valor
# ---------------------------------------------------------------------------


class WAValue(StrEnum):
    """Valor por campo extraido: 4 estados, nunca sinonimos.

    ``not_mentioned`` = ausencia de informacao na pagina (NUNCA ``false``);
    ``unclear`` = evidencia conflitante, insuficiente ou CONDICIONAL.
    """

    TRUE = "true"
    FALSE = "false"
    NOT_MENTIONED = "not_mentioned"
    UNCLEAR = "unclear"


class PageStatus(StrEnum):
    """Resultado do fetch + classificacao da pagina (classify_page)."""

    OK = "ok"
    REDIRECTED = "redirected"
    NOT_FOUND = "not_found"
    EMPTY_CONTENT = "empty_content"
    JS_RENDERED = "js_rendered"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    FETCH_ERROR = "fetch_error"


class FieldConfidence(StrEnum):
    """Confianca por campo: alta/media quando embasada, baixa quando fraca."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


RecordConfidence = Literal["high", "medium", "low"]

LanguageLevel = Literal[
    "none", "conversational", "fluent", "business", "native",
    "not_mentioned", "unclear",
]
WorkModeValue = Literal["on_site", "hybrid", "remote", "not_mentioned", "unclear"]
SalaryPeriod = Literal["hour", "month", "year"]


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------


def hash_content(text: str) -> str:
    """SHA-256 do texto normalizado (identidade de conteudo para cache)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _evidence_ok(value: str | None) -> str | None:
    """Normalizacao minima: strip; vazio vira None (nao e citacao)."""
    if value is None:
        return None
    value = value.strip()
    return value or None


# ---------------------------------------------------------------------------
# Shapes por campo (value | evidence | confidence)
# ---------------------------------------------------------------------------


class _EvBase(BaseModel):
    """Base com validacao comum de evidence (contrato <=200 chars)."""

    evidence: str | None = None

    @field_validator("evidence")
    @classmethod
    def _ev_len(cls, v: str | None) -> str | None:
        v = _evidence_ok(v)
        if v is not None and len(v) > EVIDENCE_MAX_CHARS:
            raise ValueError(
                f"evidence acima de {EVIDENCE_MAX_CHARS} chars "
                f"(got {len(v)}); o normalizador trunca antes de construir"
            )
        return v


class ExtractedField(_EvBase):
    """Campo WAValue: true/false EXIGEM evidence + confidence.

    ``not_mentioned``/``unclear`` levam evidence quando existir citacao.
    """

    value: WAValue
    confidence: FieldConfidence | None = None

    @model_validator(mode="after")
    def _require_evidence_for_true_false(self) -> "ExtractedField":
        if self.value in (WAValue.TRUE, WAValue.FALSE):
            if not self.evidence:
                raise ValueError(
                    "valor true/false exige evidence (citacao literal da pagina)"
                )
            if self.confidence is None:
                raise ValueError("valor true/false exige confidence por campo")
        return self


class WorkModeField(_EvBase):
    """Modalidade como declarada na pagina ("on-site" normaliza p/ on_site)."""

    value: WorkModeValue
    confidence: FieldConfidence | None = None


class LanguageRequirementField(_EvBase):
    """Nivel de idioma COMO DECLARADO; idioma do anuncio NAO e requisito."""

    level: LanguageLevel
    confidence: FieldConfidence | None = None


class SalaryField(_EvBase):
    """Salario literal da pagina; nunca convertido/estimado."""

    value: str | None = None
    period: SalaryPeriod | None = None
    currency: str | None = None
    confidence: FieldConfidence | None = None


class LocationField(_EvBase):
    """Local declarado NA PAGINA (nao o do feed)."""

    value: str | None = None
    confidence: FieldConfidence | None = None


class DeadlineField(_EvBase):
    """Prazo EXPLICITAMENTE declarado; nunca inferido de posted_at."""

    date: _dt.date | None = None
    confidence: FieldConfidence | None = None


class PageIsJobPostingField(_EvBase):
    """"O texto e de fato o anuncio desta vaga (ancora company+title)."""

    value: bool = False
    confidence: FieldConfidence | None = None


class UsageInfo(BaseModel):
    """Tokens in/out quando o endpoint devolver (tolerante a chaves)."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


class EnrichmentRecord(BaseModel):
    """Registro de enrichment: identidade + origem + processamento + campos.

    Records de NAO-extracao (fetch falhou / pagina inutil / LLM falhou)
    carregam os campos de extracao como ``None`` + ``extracted_at=None``:
    ausencia de valor NUNCA e preenchida com not_mentioned (conflito de
    semanticas). ``confidence`` do record e computada por
    :func:`compute_record_confidence` (regra deterministica da spec).
    """

    model_config = ConfigDict(protected_namespaces=())

    # identidade / origem
    job_id: str
    company: str
    title: str
    source: str
    original_url: str
    final_url: str | None = None
    fetched_at: str
    http_status: int | None = None
    page_status: PageStatus

    # conteudo / processamento
    content_hash: str | None = None
    extractor: Literal["llm-glm-5.3-flash"] = EXTRACTOR
    model: str | None = None
    extracted_at: str | None = None
    confidence: RecordConfidence | None = None
    error: str | None = None
    attempts: int = 0
    latency_s: float | None = None
    usage: UsageInfo | None = None
    content_truncated: bool = False

    # extracao (cada campo no shape value/evidence/confidence)
    student_status_required: ExtractedField | None = None
    work_authorization_required: ExtractedField | None = None
    existing_work_authorization_required: ExtractedField | None = None
    work_permit_required: ExtractedField | None = None
    residence_permit_required: ExtractedField | None = None
    visa_sponsorship: ExtractedField | None = None
    international_candidates_explicitly_accepted: ExtractedField | None = None
    eu_citizenship_required: ExtractedField | None = None
    internship_compatible: ExtractedField | None = None
    salary: SalaryField | None = None
    work_mode: WorkModeField | None = None
    location: LocationField | None = None
    german_requirement: LanguageRequirementField | None = None
    english_requirement: LanguageRequirementField | None = None
    employer_deadline: DeadlineField | None = None
    page_is_job_posting: PageIsJobPostingField | None = None

    schema_version: Literal[1] = SCHEMA_VERSION

    @field_validator("job_id")
    @classmethod
    def _job_id_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("job_id obrigatorio (identidade do record)")
        return v


# Campos WA (valor WAValue) — usados pela confianca record-level e pelas
# guardas de normalizacao.
WA_FIELD_NAMES: tuple[str, ...] = (
    "student_status_required",
    "work_authorization_required",
    "existing_work_authorization_required",
    "work_permit_required",
    "residence_permit_required",
    "visa_sponsorship",
    "international_candidates_explicitly_accepted",
    "eu_citizenship_required",
    "internship_compatible",
)

# Campos cujo true pode ser rebaixado pela guarda condicional (exigencias e
# sponsorship; international tem guarda propria de DEI).
_CONDITIONAL_GUARD_FIELDS: frozenset[str] = frozenset({
    "student_status_required",
    "work_authorization_required",
    "existing_work_authorization_required",
    "work_permit_required",
    "residence_permit_required",
    "visa_sponsorship",
    "eu_citizenship_required",
})


def _is_conditional(evidence: str | None) -> bool:
    """Evidencia traz marcador condicional (ggf. / if applicable / ...)."""
    if not evidence:
        return False
    low = " " + evidence.casefold() + " "
    return any(m in low for m in _CONDITIONAL_MARKERS)


def _is_dei_generic(evidence: str | None) -> bool:
    """Evidencia e frase generica de DEI da empresa (FP medido no spike)."""
    if not evidence:
        return False
    low = evidence.casefold()
    return any(m in low for m in _DEI_MARKERS)


# ---------------------------------------------------------------------------
# Normalizacao do JSON da LLM -> models do schema
# ---------------------------------------------------------------------------


def _norm_value(raw) -> WAValue:
    """Valor WAValue: ausente -> not_mentioned; desconhecido -> unclear."""
    if raw is None:
        return WAValue.NOT_MENTIONED
    s = str(raw).strip().casefold()
    mapping = {
        "true": WAValue.TRUE,
        "false": WAValue.FALSE,
        "not_mentioned": WAValue.NOT_MENTIONED,
        "unclear": WAValue.UNCLEAR,
    }
    return mapping.get(s, WAValue.UNCLEAR)


def _norm_confidence(raw, *, value: WAValue) -> FieldConfidence | None:
    if isinstance(raw, str):
        s = raw.strip().casefold()
        if s in ("high", "medium", "low"):
            return FieldConfidence(s)  # type: ignore[arg-type]
    # default: true/false sem confidence da LLM -> medium (ha evidencia);
    # not_mentioned/unclear sem confidence -> None.
    if value in (WAValue.TRUE, WAValue.FALSE):
        return FieldConfidence.MEDIUM
    return None


def _norm_evidence(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    ev = raw.strip()
    if not ev:
        return None
    return ev[:EVIDENCE_MAX_CHARS]


def _norm_wa_field(name: str, spec) -> ExtractedField:
    if not isinstance(spec, dict):
        spec = {}
    value = _norm_value(spec.get("value"))
    evidence = _norm_evidence(spec.get("evidence"))
    confidence = _norm_confidence(spec.get("confidence"), value=value)

    # Guardas deterministas pos-LLM (o prompt ja ensina; aqui confere).
    if value is WAValue.TRUE and name in _CONDITIONAL_GUARD_FIELDS:
        if _is_conditional(evidence):
            # condicional -> unclear com a evidencia (nunca true)
            value = WAValue.UNCLEAR
    if value is WAValue.TRUE and name == "international_candidates_explicitly_accepted":
        if _is_dei_generic(evidence):
            # DEI generico da empresa -> not_mentioned (nunca true)
            value = WAValue.NOT_MENTIONED
    if value in (WAValue.TRUE, WAValue.FALSE) and evidence is None:
        # true/false SEM evidencia viola o contrato (citacao literal) ->
        # rebaixa p/ unclear; o schema continua exigindo evidence em
        # true/false construidos diretamente (defesa do contrato).
        value = WAValue.UNCLEAR

    return ExtractedField(value=value, evidence=evidence, confidence=confidence)


_PERIOD_ALIASES: dict[str, str] = {
    "hour": "hour", "hourly": "hour", "stunde": "hour", "pro stunde": "hour",
    "month": "month", "monthly": "month", "monat": "month", "monatlich": "month",
    "year": "year", "yearly": "year", "jahr": "year", "jaehrlich": "year",
}
_CURRENCY_ALIASES: dict[str, str] = {
    "eur": "EUR", "euro": "EUR", "€": "EUR",
    "usd": "USD", "$": "USD",
    "gbp": "GBP", "£": "GBP",
    "chf": "CHF",
}
_LEVEL_ALIASES: dict[str, str] = {
    "business fluent": "business", "verhandlungssicher": "business",
    "verhandlungssichere": "business", "verhandlungssicher in": "business",
    "fluent": "fluent", "fliessend": "fluent", "fließend": "fluent",
    "sehr gut": "fluent", "sehr gute": "fluent", "proficient": "fluent",
    "native": "native", "native speaker": "native", "muttersprachlich": "native",
    "conversational": "conversational", "konversationssicher": "conversational",
    "none": "none", "no": "none", "keine": "none", "kein": "none",
}
_WORK_MODE_ALIASES: dict[str, str] = {
    "on_site": "on_site", "on-site": "on_site", "onsite": "on_site",
    "vor ort": "on_site",
    "hybrid": "hybrid",
    "remote": "remote",
    "not_mentioned": "not_mentioned", "unclear": "unclear",
}


def _norm_salary(spec) -> SalaryField:
    if not isinstance(spec, dict):
        spec = {}
    raw_value = spec.get("value")
    value = str(raw_value).strip() if isinstance(raw_value, (str, int, float)) else None
    if value == "":
        value = None
    evidence = _norm_evidence(spec.get("evidence"))
    # valor sem evidencia = nao verificado na pagina -> descarta (AGENTS.md:
    # distinguish explicitly sourced fields from inferred fields)
    if value is not None and evidence is None:
        value = None
    period = None
    if isinstance(spec.get("period"), str):
        period = _PERIOD_ALIASES.get(spec["period"].strip().casefold())
    currency = None
    if isinstance(spec.get("currency"), str):
        currency = _CURRENCY_ALIASES.get(
            spec["currency"].strip().casefold(), spec["currency"].strip()
        )
    confidence = _norm_confidence(spec.get("confidence"), value=WAValue.TRUE)
    if value is None:
        confidence = None
    return SalaryField(
        value=value, period=period, currency=currency,
        evidence=evidence, confidence=confidence,
    )


def _norm_work_mode(spec) -> WorkModeField:
    if not isinstance(spec, dict):
        spec = {}
    raw = spec.get("value")
    value: WorkModeValue = "not_mentioned"  # type: ignore[assignment]
    if isinstance(raw, str):
        value = _WORK_MODE_ALIASES.get(raw.strip().casefold(), "unclear")  # type: ignore[assignment]
    return WorkModeField(
        value=value,
        evidence=_norm_evidence(spec.get("evidence")),
        confidence=_norm_confidence(spec.get("confidence"), value=WAValue.TRUE),
    )


def _norm_level(raw) -> LanguageLevel:
    """Nivel COMO DECLARADO: enum exato > alias exato > alias por substring.

    Aliases cobrem variantes alemas comprovadas da spec ("verhandlungssicher"
    -> business, "sehr gute" -> fluent); substring confere a frase inteira
    ("sehr gute Deutschkenntnisse"). Desconhecido -> unclear (nunca adivinhado).
    """
    if not isinstance(raw, str):
        return "not_mentioned"
    s = raw.strip().casefold()
    if s in ("none", "conversational", "fluent", "business", "native",
             "not_mentioned", "unclear"):
        return s  # type: ignore[return-value]
    if s in _LEVEL_ALIASES:
        return _LEVEL_ALIASES[s]  # type: ignore[return-value]
    for alias, level in sorted(
        _LEVEL_ALIASES.items(), key=lambda kv: -len(kv[0])
    ):
        if alias in s:
            return level  # type: ignore[return-value]
    return "unclear"


def _norm_language(spec) -> LanguageRequirementField:
    if not isinstance(spec, dict):
        spec = {}
    return LanguageRequirementField(
        level=_norm_level(spec.get("level")),
        evidence=_norm_evidence(spec.get("evidence")),
        confidence=_norm_confidence(spec.get("confidence"), value=WAValue.TRUE),
    )


def _norm_location(spec) -> LocationField:
    if not isinstance(spec, dict):
        spec = {}
    raw = spec.get("value")
    value = str(raw).strip() if isinstance(raw, str) else None
    if value == "":
        value = None
    confidence = _norm_confidence(spec.get("confidence"), value=WAValue.TRUE)
    if value is None:
        confidence = None
    return LocationField(
        value=value, evidence=_norm_evidence(spec.get("evidence")),
        confidence=confidence,
    )


def _norm_deadline(spec) -> DeadlineField:
    if not isinstance(spec, dict):
        spec = {}
    raw = spec.get("date")
    date = None
    evidence = _norm_evidence(spec.get("evidence"))
    if isinstance(raw, str) and raw.strip() and evidence is not None:
        try:
            date = _dt.date.fromisoformat(raw.strip())
        except ValueError:
            date = None  # data invalida -> sem prazo (nunca inventado)
    confidence = _norm_confidence(spec.get("confidence"), value=WAValue.TRUE)
    if date is None:
        confidence = None
    return DeadlineField(date=date, evidence=evidence, confidence=confidence)


def _norm_page_is_job_posting(spec) -> PageIsJobPostingField:
    if not isinstance(spec, dict):
        spec = {}
    value = spec.get("value")
    # ausencia -> False (pagina nao confirmada como anuncio -> confianca low)
    is_posting = bool(value) if isinstance(value, bool) else False
    confidence = _norm_confidence(spec.get("confidence"), value=WAValue.TRUE)
    return PageIsJobPostingField(
        value=is_posting,
        evidence=_norm_evidence(spec.get("evidence")),
        confidence=confidence if is_posting else None,
    )


def fields_from_llm(parsed: dict) -> dict:
    """Normaliza o JSON cru da LLM para os models do schema.

    Tolerante por design (o JSON pode vir picado/incompleto em janela
    degradada — medido no spike): chave ausente -> ``not_mentioned``/None,
    valor fora do enum -> ``unclear``. Cada campo e normalizado
    INDEPENDENTEMENTE — nenhum valor e propagado entre campos (a evidencia
    de Immatrikulation nao preenche sponsorship/authorization/residence).
    Guardas deterministicas rebaixam os 2 falsos positivos reais do spike:
    condicional (ggf./if applicable) e frase DEI generica da empresa.
    """
    parsed = parsed if isinstance(parsed, dict) else {}
    fields: dict = {}
    for name in WA_FIELD_NAMES:
        fields[name] = _norm_wa_field(name, parsed.get(name))
    fields["salary"] = _norm_salary(parsed.get("salary"))
    fields["work_mode"] = _norm_work_mode(parsed.get("work_mode"))
    fields["location"] = _norm_location(parsed.get("location"))
    fields["german_requirement"] = _norm_language(parsed.get("german_requirement"))
    fields["english_requirement"] = _norm_language(parsed.get("english_requirement"))
    fields["employer_deadline"] = _norm_deadline(parsed.get("employer_deadline"))
    fields["page_is_job_posting"] = _norm_page_is_job_posting(
        parsed.get("page_is_job_posting"))
    return fields


# ---------------------------------------------------------------------------
# Construtores e confianca record-level
# ---------------------------------------------------------------------------


def build_record(
    job: dict,
    *,
    fetched_at: str,
    page_status: PageStatus | str,
    final_url: str | None = None,
    http_status: int | None = None,
    content_hash: str | None = None,
    error: str | None = None,
    fields: dict | None = None,
    content_truncated: bool = False,
    model: str | None = None,
    extracted_at: str | None = None,
    attempts: int = 0,
    latency_s: float | None = None,
    usage: dict | None = None,
) -> EnrichmentRecord:
    """Constroi EnrichmentRecord completo (sucesso OU nao-extracao).

    ``fields`` (saida de :func:`fields_from_llm`) presente = extracao
    ocorrida -> ``extracted_at`` e obrigatorio e a confianca record-level e
    computada. Sem ``fields`` = record de nao-extracao (fetch falhou, pagina
    inutil ou LLM falhou) — campos ficam ``None``, nunca not_mentioned.
    """
    if fields is not None and extracted_at is None:
        raise ValueError("extracao com fields exige extracted_at")
    page_status = PageStatus(page_status)
    usage_model = None
    if isinstance(usage, dict):
        usage_model = UsageInfo(
            prompt_tokens=usage.get("prompt_tokens", usage.get("input_tokens")),
            completion_tokens=usage.get(
                "completion_tokens", usage.get("output_tokens")),
        )
    kwargs: dict = dict(
        job_id=str(job.get("id") or ""),
        company=str(job.get("company") or ""),
        title=str(job.get("title") or ""),
        source=str(job.get("source") or ""),
        original_url=str(job.get("url") or ""),
        final_url=final_url,
        fetched_at=fetched_at,
        http_status=http_status,
        page_status=page_status,
        content_hash=content_hash,
        model=model,
        extracted_at=extracted_at,
        error=(error[:200] if isinstance(error, str) else None),
        attempts=attempts,
        latency_s=latency_s,
        usage=usage_model,
        content_truncated=content_truncated,
    )
    if fields:
        kwargs.update(fields)
    record = EnrichmentRecord(**kwargs)
    if fields is not None:
        record.confidence = compute_record_confidence(record)
    return record


def compute_record_confidence(record: EnrichmentRecord) -> RecordConfidence | None:
    """Confianca record-level deterministica (spec da fase):

    - ``None``  = nao extraido (falha);
    - ``low``   = page_is_job_posting=false OU campo true/false sem evidencia;
    - ``medium``= extracao completa com evidencias E truncamento do texto;
    - ``high``  = extracao completa, todo true/false com evidencia,
      page_is_job_posting=true, sem truncamento.

    O branch "true/false sem evidencia" e defensivo: o schema EXIGE evidencia
    em true/false e o normalizador rebaixa o caso LLM para unclear — mas a
    formula da spec e conferida aqui de qualquer forma.
    """
    if record.extracted_at is None:
        return None
    pip = record.page_is_job_posting.value if record.page_is_job_posting else False
    if pip is not True:
        return "low"
    for name in WA_FIELD_NAMES:
        field = getattr(record, name)
        if field is None:
            continue
        if field.value in (WAValue.TRUE, WAValue.FALSE) and not field.evidence:
            return "low"
    if record.content_truncated:
        return "medium"
    return "high"


def is_success_record(record: dict | EnrichmentRecord) -> bool:
    """Record com extracao valida (extracted_at presente) — base do cache
    e da preservacao de records no upsert."""
    if isinstance(record, EnrichmentRecord):
        return record.extracted_at is not None
    return record.get("extracted_at") is not None
