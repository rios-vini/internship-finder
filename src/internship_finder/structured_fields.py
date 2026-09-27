"""Campos estruturados do ``raw`` (Fase B) — leitura pura, zero estado.

O ``ats-scrapers 0.3.0`` preserva no ``raw`` de cada ``Job`` varios campos
ESTRUTURADOS que o pipeline nao consumia: ``department``,
``employment_type`` (enum normalizado), ``is_remote``, ``commitment``,
``apply_url``, ``requisition_id``, ``global_id``. Este modulo os expoe de
forma segura, seguindo o PRECEDENTE de ``opportunity_intel`` (``job_salary``
le ``raw.salary_*``; ``work_mode`` le ``raw.is_remote``): funcoes puras,
deterministicas, read-only sobre dicts de vaga — nada de rede, nada de
estado, nada de escrita.

PRINCIPIOS DA FASE (spec do dono):

- O ``raw`` continua sendo a FONTE estruturada do ATS; NENHUM campo e
  promovido ao modelo canonico ``Job`` (spec §7: so promove com necessidade
  concreta de consumo recorrente — display le direto do ``raw``).
- ``employment_type`` do ATS e EVIDENCIA COMPLEMENTAR: JAMAIS substitui o
  filtro atual (``filters.is_student_role``). A auditoria mostrou os dois
  lados do problema: SmartRecruiters marca vagas ``INTERN`` que sao eventos
  de carreira; e Bosch/recruitee marcam ``Praktikum``/``Werkstudent`` como
  ``FULL_TIME``/``CONTRACT`` (o enum descreve o REGIME do contrato, nao a
  natureza da vaga). Conflitos sao REGISTRADOS
  (``employment_type_relation``), nunca corrigidos.
- ``is_remote=False`` NAO e "on-site declarado": o upstream infere o flag
  de forma estreita e ``None`` significa "nao sabemos" (docstring do
  modelo: a heuristica de titulo "only ever returns True (never False)").
  ``False`` e evidencia complementar; conflito com o sinal textual e
  metrica (``remote_relation``), nao decisao.
- ``apply_url`` nunca substitui ``job.url``: e um SEGUNDO link de
  candidatura quando existe, passa na validacao de scheme da UI (P2.3,
  http/https) e so e util quando DIFERE de ``job.url``.
- ``requisition_id`` e ``global_id`` NAO participam de dedup/identidade
  nesta fase (identidade tenant-scoped do projeto permanece — P1.1). Sao
  medidos como evidencia para uma decisao futura de Fase C/D.

Toda string vazia/so-whitespace vira ``None`` (mesma regra ``_strip`` do
modelo). Todo job sem ``raw`` (dict) devolve valores neutros — o caminho
SQLite da interface (``raw`` propositalmente excluido do DB) e vagas de
ATS que nao fornecem o campo nao quebram (spec §12.10).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from internship_finder.app_intel import normalize_text
from internship_finder.filters import STUDENT_TYPE_PATTERNS, is_student_role
from internship_finder.opportunity_intel import _WORK_MODE_RE

# Enum normalizado do ats-scrapers 0.3.0 (models.EmploymentType).
EMPLOYMENT_TYPE_ENUMS = frozenset(
    {"FULL_TIME", "PART_TIME", "CONTRACT", "INTERN", "TEMPORARY"}
)


# ---------------------------------------------------------------------------
# Leitura bruta
# ---------------------------------------------------------------------------

def _raw(job: dict) -> dict:
    """``job["raw"]`` quando e dict; {} caso contrario (nunca quebra)."""
    raw = job.get("raw")
    return raw if isinstance(raw, dict) else {}


def _str(raw: dict, key: str) -> str | None:
    """Valor string do raw: strip; vazio/whitespace -> None (regra _strip)."""
    value = raw.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------------------
# Campos estruturados (acessores puros)
# ---------------------------------------------------------------------------

def department(job: dict) -> str | None:
    """``raw.department`` — agrupamento organizacional do ATS, se houver.

    Semantica por ATS e heterogenea (auditoria 26/09): SmartRecruiters
    traca area real (Supply Chain, Purchasing); greenhouse publica a
    propria taxonomia da empresa (Students, Graduate Programs);
    successfactors mistura BU, local e layout de formulario
    ("ATS_WCMS_WEBFORM", "Studierende"). E evidencia de display, nunca
    regra — nao entra em score nem elegibilidade nesta fase.
    """
    return _str(_raw(job), "department")


def employment_type_enum(job: dict) -> str | None:
    """``raw.employment_type`` — enum normalizado do ats-scrapers.

    ``FULL_TIME``/``PART_TIME``/``CONTRACT``/``INTERN``/``TEMPORARY`` (ou
    label livre quando o ATS nao normaliza). E EVIDENCIA: nao substitui
    ``filters.is_student_role`` nem o filtro de eligible. Conflito com a
    classificacao atual e metrica (ver ``employment_type_relation``),
    nunca correcao automatica.
    """
    return _str(_raw(job), "employment_type")


def is_remote_flag(job: dict) -> bool | None:
    """``raw.is_remote`` — flag estruturado de modalidade, quando existe.

    ``True`` afirma remote (``opportunity_intel.work_mode`` ja o consome
    como sinal — precedente da Fase 7). ``False`` e evidencia COMPLEMENTAR
    fraca: o upstream publica ``False`` quando o ATS nao expoe o flag e a
    inferencia de titulo nao achou marcador — nao e "on-site declarado".
    ``None`` = sem valor. Nada aqui altera filtro/ranking.
    """
    value = _raw(job).get("is_remote")
    return value if isinstance(value, bool) else None


def commitment_label(job: dict) -> str | None:
    """``raw.commitment`` — label livre do ATS (Workable type, Lever
    commitment, Bundesagentur arbeitszeit, CDI/CDD...).

    DESCOBERTA DA FASE B (por que nao vai para a UI): para os ATS que o
    preenchem no dataset, ``commitment`` e a ORIGEM do label canonico
    ``Job.employment_type`` — a cadeia de fallback do adapter termina em
    ``commitment``. Softgarden ``commitment=OTHER`` == ``employment_type``
    ``OTHER``; workday ``Full time`` == ``FULL_TIME`` (normalizado a
    montante). Exibir ambos seria DUPLICACAO do mesmo dado por dois
    caminhos. A unica divergencia observada e personio (``commitment``
    ``Full-time`` vs enum ``INTERN`` — o enum e mais especifico), e a
    solucão e usar o enum no display complementar, nao o label. O campo
    permanece preservado no ``raw`` como evidencia.
    """
    return _str(_raw(job), "commitment")


def apply_url(job: dict) -> str | None:
    """``raw.apply_url`` — URL DIRETA de candidatura, quando utilizavel.

    Regra da fase (spec §5): ``job.url`` continua sendo a URL da vaga/
    origem (link do titulo + botao "abrir"); ``apply_url`` e um SEGUNDO
    botao "candidatar-se", so quando existe, tem scheme http/https (mesma
    regra P2.3 do ``interface._safe_url``) e DIFERE de ``job.url`` — a
    comparacao de diferenca fica na UI, que ja tem ``job.url`` em maos.
    Nunca substitui silenciosamente uma pela outra.
    """
    url = _str(_raw(job), "apply_url")
    if url is None:
        return None
    try:
        scheme = urlsplit(url).scheme
    except ValueError:
        return None
    return url if scheme.casefold() in ("http", "https") else None


def requisition_id(job: dict) -> str | None:
    """``raw.requisition_id`` — identificador interno do empregador.

    Docstring upstream: "Same role mirrored on two different ATSes shares
    the same requisition_id — strong cross-ATS dedup signal". NESTA FASE
    e apenas MEDIDO (unicos, duplicados por tenant, mirrors) — NAO entra
    em dedup, nao altera ``Job.id``/``external_id``/eligible. Ver
    ``scripts/structured_fields_coverage.py`` (analise completa) — o
    resultado alimenta a decisao de uma futura Fase C/D.
    """
    return _str(_raw(job), "requisition_id")


def global_id(job: dict) -> str | None:
    """``raw.global_id`` — ``{ats_type}:{ats_id}`` do upstream.

    NAO substitui a identidade tenant-scoped do projeto (``Job.id`` =
    ``<company>|<source>:<external_id>``, P1.1); e evidencia futura,
    medida apenas: cobertura, unicidade, colisoes, relacao com o id atual.
    """
    return _str(_raw(job), "global_id")


# ---------------------------------------------------------------------------
# Métricas de conflito (evidência estruturada × classificação atual)
# ---------------------------------------------------------------------------

def employment_type_relation(job: dict) -> str:
    """Relacao enum do ATS × classificacao ATUAL: ``match``/``conflict``/``missing``.

    Compara o enum estruturado com a AUTORIDADE da fase —
    ``filters.is_student_role`` com os MESMOS inputs do filtro de eligible
    (titulo, descricao, employment_type canonico) — para medir a
    confiabilidade do campo antes de qualquer regra futura (spec §2/§10):

    - ``missing``: sem enum no ``raw``, OU label fora do enum normalizado
      do ats-scrapers (ex.: softgarden ``OTHER`` — sem semantica de
      classificacao, nao afirma nem nega student-role).
    - ``match``: enum ``INTERN`` + classificacao atual student-role; enum
      ``INTERN`` fora do eligible nao ocorre no dataset (9/9 elegiveis
      com INTERN sao student-role). ``PART_TIME`` e sempre compativel — e
      o regime tipico de Werkstudent/working student e nao afirma nada
      sobre a natureza da vaga (um clerk part-time tambem e PART_TIME).
    - ``conflict``: enum ``INTERN`` mas classificacao atual diz nao-student
      (o caso SmartRecruiters career-event); OU enum
      ``FULL_TIME``/``CONTRACT``/``TEMPORARY`` mas classificacao atual diz
      student-role — o caso dominante no dataset (Bosch ``Praktikum`` =
      FULL_TIME, recruitee ``Werkstudent`` = CONTRACT): o enum descreve o
      REGIME do contrato, nao a natureza da vaga.

    Conflito e REGISTRO, nunca correcao: a classificacao atual e a
    autoridade e o enum nao a substitui (spec §2).
    """
    enum = _str(_raw(job), "employment_type")
    if enum is None:
        return "missing"
    enum_norm = enum.upper().replace("-", "_").replace(" ", "_")
    if enum_norm not in EMPLOYMENT_TYPE_ENUMS:
        return "missing"
    title = str(job.get("title") or "")
    # Classificacao ATUAL: os MESMOS inputs que o filtro de eligible usa.
    current = is_student_role(title, job.get("description"), enum)
    if enum_norm == "INTERN":
        return "match" if current else "conflict"
    if enum_norm == "PART_TIME":
        return "match"
    # FULL_TIME / CONTRACT / TEMPORARY
    return "conflict" if current else "match"


def remote_relation(job: dict) -> str:
    """Relacao ``is_remote`` estruturado × sinal textual: ``match``/``conflict``/``missing``.

    Mede a confiabilidade do flag comparando-o ao detector TEXTUAL puro
    (as mesmas regex de ``opportunity_intel._WORK_MODE_RE`` sobre
    titulo+descricao, SEM consumir o flag — isolando o sinal textual).
    Nao escolhe vencedor (spec §3):

    - ``missing``: sem flag estruturado (``is_remote`` ausente/nao-bool).
    - ``match``: ``True`` + sinal textual remote/hybrid/ausente; ``False``
      + sinal textual on_site/ausente (``not_mentioned`` textual nao e
      conflito: ``False`` so significa "sem marcador de remote").
    - ``conflict``: ``True`` × on_site textual; ``False`` × remote/hybrid
      textual (caso real do dataset: ashby Statista "Working Student
      Procurement" — ATS ``False``, descricao "hybrid").
    """
    flag = is_remote_flag(job)
    if flag is None:
        return "missing"
    textual = "not_mentioned"
    text = " ".join(
        normalize_text(x) for x in (job.get("title"), job.get("description")) if x
    )
    if text:
        if _WORK_MODE_RE["hybrid"].search(text):
            textual = "hybrid"
        elif _WORK_MODE_RE["remote"].search(text):
            textual = "remote"
        elif _WORK_MODE_RE["on_site"].search(text):
            textual = "on_site"
    if flag is True:
        return "conflict" if textual == "on_site" else "match"
    return "conflict" if textual in ("remote", "hybrid") else "match"
