"""Schema da Fase E — record da spike (pydantic, enums EXATOS da spec §7).

Diferencas deliberadas vs enrichment v1 (``enrichment/schema.py``):

- Input: TEXTO JA COLETADO (description hidratada/feed + bloco
  ``official_page`` como contexto marcado §12 + JSON-LD), NAO fetch+HTML
  de pagina oficial.
- Enums NOVOS da spec §7 (WA com 8 estados; German/English com estado
  required/preferred/not_required/not_mentioned/unclear; deadline com
  kind employer_textual/official_page_structured/unclear; student com 6
  estados; salary min/max/currency/period/evidence).
- Validacao ESTRITA (spec §10): valor fora do enum -> campo rejeitado
  com erro registrado (record marcado ``field_errors``), NUNCA fallback
  heuristico. A normalizacao tolerante do v1 (alias/substring) NAO se
  aplica aqui — mapear "sehr gut"->fluent seria heuristica.
- Evidence-first (spec §8): estado informativo EXIGE evidence curta
  (<=200 chars, citacao literal do input); ``confidence`` em
  high/medium/low (spec §9). Ausencia de evidencia = ``not_mentioned``
  (nunca ``low``).

``source`` de cada campo: onde a evidencia foi encontrada no input
montado — ``description`` (texto de extracao), ``structured_fields``,
``official_page_context`` ou ``jsonld``. Marcadores condicionais/DEI
(mesmos tuples do v1) sao guardas pos-LLM defense-in-depth.
"""

from __future__ import annotations

import datetime as _dt
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = 1
EVIDENCE_MAX_CHARS = 200
CONTENT_LIMIT = 12000

# Marcadores condicionais e frases DEI genericas — MESMOS tuples comprovados
# do enrichment v1 (llm.py/schema.py do v1). Reuso explicito (decisao 5 do
# orquestrador): guardas deterministicas pos-LLM, defense in depth.
_CONDITIONAL_MARKERS: tuple[str, ...] = (
    "ggf.", "ggf ", "falls erforderlich", "falls notwendig", "falls gegeben",
    "if applicable", "if required", "if necessary", "where applicable",
    "where required", "sofern erforderlich", "nach moeglichkeit",
    "nach möglichkeit",
)
_DEI_MARKERS: tuple[str, ...] = (
    "ungeachtet", "regardless of", "equal opportunity", "aller menschen",
    "alle menschen", "all people", "all humans", "diversity",
)

# Campo de onde a evidencia veio (input montado da spike).
EVIDENCE_SOURCE = Literal[
    "description", "structured_fields", "official_page_context", "jsonld",
]
CONFIDENCE = Literal["high", "medium", "low"]


class WAState(StrEnum):
    """WA da spike (spec §7-A): 8 estados, nunca sinonimos."""

    EXPLICIT_SUPPORT = "explicit_support"
    EXPLICIT_NO_SUPPORT = "explicit_no_support"
    CANDIDATE_MUST_HAVE_AUTHORIZATION = "candidate_must_have_authorization"
    EXISTING_AUTHORIZATION_REQUIRED = "existing_authorization_required"
    INTERNATIONAL_CANDIDATES_ACCEPTED = "international_candidates_accepted"
    STUDENT_AUTHORIZATION_COMPATIBLE = "student_authorization_compatible"
    UNCLEAR = "unclear"
    NOT_MENTIONED = "not_mentioned"


class LangState(StrEnum):
    """Idioma (spec §7-B/C): required/preferred/not_required/not_mentioned/unclear."""

    REQUIRED = "required"
    PREFERRED = "preferred"
    NOT_REQUIRED = "not_required"
    NOT_MENTIONED = "not_mentioned"
    UNCLEAR = "unclear"


class DeadlineKind(StrEnum):
    """Deadline (spec §7-D)."""

    EMPLOYER_TEXTUAL = "employer_textual"
    OFFICIAL_PAGE_STRUCTURED = "official_page_structured"
    UNCLEAR = "unclear"


class StudentKind(StrEnum):
    """Student compatibility (spec §7-F + §9).

    Os 6 valores da spec §7-F (student_role/internship/working_student/
    mandatory_internship/voluntary_internship/unclear) + ``not_mentioned``
    — estado global de ausencia (spec §9: "Quando nao houver evidencia:
    not_mentioned"; §8: toda conclusao factual exige evidence, ausencia
    nao e erro). Sem ele, toda vaga sem evidencia viraria field_error,
    violando o principio de ausencia.
    """

    STUDENT_ROLE = "student_role"
    INTERNSHIP = "internship"
    WORKING_STUDENT = "working_student"
    MANDATORY_INTERNSHIP = "mandatory_internship"
    VOLUNTARY_INTERNSHIP = "voluntary_internship"
    UNCLEAR = "unclear"
    NOT_MENTIONED = "not_mentioned"


def _evidence_ok(value: str | None) -> str | None:
    """Strip; vazio -> None (ausencia de citacao)."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def is_conditional(evidence: str | None) -> bool:
    """Evidencia traz marcador condicional (ggf. / if applicable / ...)."""
    if not evidence:
        return False
    low = " " + evidence.casefold() + " "
    return any(m in low for m in _CONDITIONAL_MARKERS)


def is_dei_generic(evidence: str | None) -> bool:
    """Evidencia e frase generica de DEI da empresa (FP medido no v1)."""
    if not evidence:
        return False
    low = evidence.casefold()
    return any(m in low for m in _DEI_MARKERS)


# ---------------------------------------------------------------------------
# Guardas deterministicas pos-LLM (defense in depth, spec §7-A): as tres
# confusoes EXPLICITAMENTE nomeadas pela spec. Padrao comprovado do
# enrichment v1; alta precisao — rebaixam so o caso de falso positivo.
# ---------------------------------------------------------------------------
import re as _re

# Tema de visto/autorizacao presente na evidencia (vocabulario do
# detector app_intel + passport/cidadania — EU-Buerger/valid EU passport
# sao requisitos de autorizacao): sem tema, evidencia nao suporta
# estado WA forte.
_WA_THEME_TOKENS_RE = _re.compile(
    r"visa|visum|sponsor|permit|erlaubnis|aufenthalt|"
    r"work authorization|right to work|immigration|"
    r"passport|citizenship|citizen|bürger|buerg",
    _re.IGNORECASE,
)
# Evidencia que so fala de RELOCACAO (mudanca de cidade) — §7-A:
# "relocation support" NUNCA e sponsorship.
_RELOCATION_ONLY_RE = _re.compile(
    r"relocat|umzug|moving to|relocation package|umzugs",
    _re.IGNORECASE,
)
# Evidencia de autorizacao JA EXISTENTE — §7-A: "must already hold a
# valid work permit" e REQUISITO, nao sponsorship.
_ALREADY_HOLD_RE = _re.compile(
    r"already (hold|possess|have|own)|must already|bereits vorhanden|"
    r"vorhandene[rnms]?\s+arbeitserlaubnis",
    _re.IGNORECASE,
)
# "International ENVIRONMENT" (descritivo) ≠ "international candidates
# ACCEPTED" (permissivo) — §7-A: ambiente internacional nao prova
# aceitacao sem vocabulario de aceitacao na evidencia.
_INTL_ENV_ONLY_RE = _re.compile(
    r"international\w*\s+(environment|team|company|workplace|setting|"
    r"kontext|umfeld)|internationales?\s+(team|umfeld)",
    _re.IGNORECASE,
)
_ACCEPT_VOCAB_RE = _re.compile(
    r"welcome|accepted|accept|applicants|candidates|bewerber|"
    r"kandidat|invite|encouraged",
    _re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Shapes por campo (state/evidence/source/confidence)
# ---------------------------------------------------------------------------


class _EvBase(BaseModel):
    """Evidence <=200 chars (citacao curta, spec §8)."""

    model_config = ConfigDict(protected_namespaces=())

    evidence: str | None = None
    source: EVIDENCE_SOURCE | None = None
    confidence: CONFIDENCE | None = None

    @field_validator("evidence")
    @classmethod
    def _ev_len(cls, v: str | None) -> str | None:
        v = _evidence_ok(v)
        if v is not None and len(v) > EVIDENCE_MAX_CHARS:
            raise ValueError(
                f"evidence acima de {EVIDENCE_MAX_CHARS} chars (got {len(v)})")
        return v


class _FieldBase(_EvBase):
    """Base comum dos campos state: evidence-first (spec §8)."""

    @model_validator(mode="after")
    def _evidence_required_for_informative_states(self):
        # not_mentioned/unclear podem (mas nao precisam) ter evidence;
        # TODO estado informativo exige citacao literal.
        if not hasattr(self, "state"):
            return self
        state = getattr(self, "state")
        if state not in ("not_mentioned", "unclear") and not self.evidence:
            raise ValueError(
                f"estado '{state}' exige evidence (citacao literal do input)")
        if self.evidence and not self.source:
            raise ValueError("evidence exige source (onde foi encontrada)")
        return self


class WAField(_FieldBase):
    """A. Work authorization (8 estados)."""

    state: WAState

    @model_validator(mode="after")
    def _guards(self) -> "WAField":
        # Defense in depth (padrao v1 + confusoes nomeadas na spec §7-A).
        # Guardas REJEITAM o campo (field_error) — a spike MEDE o
        # comportamento do LLM cru; corrigir silenciosamente esconderia
        # exatamente os FPs que o manual review precisa ver.
        if self.state is WAState.EXPLICIT_SUPPORT and is_conditional(self.evidence):
            raise ValueError("evidencia condicional nao permite explicit_support")
        if self.state is WAState.INTERNATIONAL_CANDIDATES_ACCEPTED:
            if is_dei_generic(self.evidence):
                raise ValueError(
                    "frase DEI generica nao permite international_accepted")
            if (self.evidence and _INTL_ENV_ONLY_RE.search(self.evidence)
                    and not _ACCEPT_VOCAB_RE.search(self.evidence)):
                raise ValueError(
                    "evidencia de ambiente internacional sem vocabulario de "
                    "aceitacao nao permite international_accepted")
        # Tema de visto/autorizacao ausente da evidencia -> estado forte
        # WA e insustentavel (a citacao nao fala do tema).
        if self.state in (
            WAState.EXPLICIT_SUPPORT, WAState.EXPLICIT_NO_SUPPORT,
            WAState.EXISTING_AUTHORIZATION_REQUIRED,
        ) and self.evidence and not _WA_THEME_TOKENS_RE.search(self.evidence):
            raise ValueError(
                "evidencia sem tema de visto/autorizacao nao suporta estado "
                "WA forte")
        # Relocation-only como suporte de visto (§7-A: con fusao nomeada).
        if (self.state is WAState.EXPLICIT_SUPPORT and self.evidence
                and _RELOCATION_ONLY_RE.search(self.evidence)
                and not _WA_THEME_TOKENS_RE.search(self.evidence)):
            raise ValueError(
                "evidencia de relocation nao permite explicit_support")
        # Existing-authorization como suporte (§7-A: con fusao nomeada).
        if (self.state is WAState.EXPLICIT_SUPPORT and self.evidence
                and _ALREADY_HOLD_RE.search(self.evidence)):
            raise ValueError(
                "evidencia de autorizacao ja existente nao permite "
                "explicit_support")
        return self


class LanguageField(_FieldBase):
    """B/C. German / English."""

    state: LangState


class DeadlineField(_FieldBase):
    """D. Deadline — so com evidencia textual clara (spec §7-D)."""

    date: _dt.date | None = None
    kind: DeadlineKind | None = None

    @model_validator(mode="after")
    def _kind_rules(self) -> "DeadlineField":
        # kind informativo (employer_textual/official_page_structured)
        # EXIGE date + evidence; kind=unclear aceita evidence sem date;
        # tudo ausente = campo sem deadline (ausencia nao e erro, §9).
        if self.kind in (DeadlineKind.EMPLOYER_TEXTUAL,
                         DeadlineKind.OFFICIAL_PAGE_STRUCTURED):
            if self.date is None:
                raise ValueError(
                    f"kind '{self.kind}' exige date (deadline declarado)")
            if not self.evidence:
                raise ValueError("deadline com date exige evidence")
        if self.date is not None and self.kind is None:
            raise ValueError("deadline com date exige kind")
        if self.kind is DeadlineKind.UNCLEAR and self.date is not None:
            raise ValueError("kind unclear nao aceita date")
        if self.kind is DeadlineKind.UNCLEAR and not self.evidence:
            raise ValueError("deadline sem date exige evidence (unclear)")
        return self


class SalaryField(_FieldBase):
    """E. Salary — somente explicitamente informado (nunca inferido)."""

    min: float | None = None
    max: float | None = None
    currency: str | None = None
    period: Literal["hour", "month", "year"] | None = None

    @model_validator(mode="after")
    def _salary_rules(self) -> "SalaryField":
        has_value = self.min is not None or self.max is not None
        if has_value and not self.evidence:
            raise ValueError("salary com valor exige evidence")
        if has_value and self.evidence and self.source is None:
            raise ValueError("salary com valor exige source")
        if not has_value and self.evidence and not self.confidence:
            # evidence sem valor = mencao de salario sem numero -> registro,
            # mas o estado "sem salario" fica explicito no record (salary=None).
            pass
        return self


class StudentField(_FieldBase):
    """F. Student compatibility (subtipo + evidencia)."""

    state: StudentKind


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


class UsageInfo(BaseModel):
    """Tokens in/out por job (usage da resposta)."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class SpikeERecord(BaseModel):
    """Record da spike Fase E (identidade + input + extracao + meta).

    ``field_errors``: campos rejeitados na validacao estrita (§10) —
    ``{"campo": "erro pydantic curto"}``. Record com field_errors continua
    valido (os outros campos sao usados); o campo rejeitado conta como
    ``llm_invalid`` na analise, nunca como informacao.
    """

    model_config = ConfigDict(protected_namespaces=())

    schema_version: Literal[1] = SCHEMA_VERSION

    # identidade (spec §5: preservar id/company/source/url original)
    job_id: str
    company: str
    title: str
    source: str
    original_url: str

    # amostra (§5) — bucket + motivo da selecao
    bucket: str
    selection_reason: str

    # input (§6) — o TEXTO exato enviado ao LLM fica no record para
    # reprodutibilidade do manual review (§17: "a revisao usa o MESMO
    # texto enviado ao LLM").
    llm_input: str
    input_truncated: bool = False

    # meta da execucao (§15)
    model: str
    extracted_at: str
    attempts: int = 0
    latency_s: float | None = None
    usage: UsageInfo | None = None
    error: str | None = None

    # extracoes A–F (None = campo ausente na resposta / rejeitado)
    work_authorization: WAField | None = None
    german: LanguageField | None = None
    english: LanguageField | None = None
    deadline: DeadlineField | None = None
    salary: SalaryField | None = None
    student: StudentField | None = None

    field_errors: dict[str, str] = {}

    @field_validator("job_id")
    @classmethod
    def _job_id_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("job_id obrigatorio")
        return v


# ---------------------------------------------------------------------------
# Normalizacao estrita do JSON da LLM -> SpikeERecord fields (spec §10)
# ---------------------------------------------------------------------------

_FIELDS_A_F = (
    "work_authorization", "german", "english", "deadline",
    "salary", "student",
)


def _build_field(name: str, spec, model_cls):
    """Valida ESTRITO um campo do JSON cru; fora do enum -> erro registrado.

    Retorna (field | None, error | None). NUNCA fallback heuristico: valor
    desconhecido e rejeitado com a mensagem pydantic curta, campo vira None
    no record e entra em ``field_errors`` (§10: "rejeitar aquele campo,
    registrar erro").
    """
    if not isinstance(spec, dict):
        return None, "missing_or_not_dict"
    try:
        return model_cls(**spec), None
    except ValidationError as exc:
        try:
            first = str(exc.errors()[0].get("msg", exc))
        except Exception:
            first = str(exc)
        return None, str(first)[:160]
    except Exception as exc:
        return None, str(exc)[:160]


def parse_llm_fields(parsed: dict) -> tuple[dict, dict[str, str]]:
    """JSON cru da LLM -> campos validados + erros por campo.

    Chave ausente no JSON -> campo None (SEM erro: a LLM pode nao ter
    retornado o bloco). Valor presente e invalido -> None + erro em
    ``field_errors``. Nenhum valor e propagado entre campos.
    """
    parsed = parsed if isinstance(parsed, dict) else {}
    models = {
        "work_authorization": WAField,
        "german": LanguageField,
        "english": LanguageField,
        "deadline": DeadlineField,
        "salary": SalaryField,
        "student": StudentField,
    }
    fields: dict = {}
    errors: dict[str, str] = {}
    for name, model_cls in models.items():
        if name not in parsed:
            continue  # campo ausente na resposta -> None, sem erro
        field, err = _build_field(name, parsed.get(name), model_cls)
        if err:
            errors[name] = err
        elif field is not None:
            fields[name] = field
    return fields, errors
