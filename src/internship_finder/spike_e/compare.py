"""Comparacao deterministic × LLM (spec §11) — relations por campo.

Para cada campo A-F do record vs o valor deterministico (funcoes puras de
``app_intel``/``opportunity_intel``, executadas SOBRE A MESMA AMOSTRA — o
deterministic_value e computado NA SPIKE, nunca lido de tabela externa).

Relations (§11): ``agree`` | ``llm_adds_information`` | ``conflict`` |
``deterministic_missing`` | ``llm_missing``. Conflito NUNCA e resolvido
automaticamente — e exatamente o que a spike mede.

Mapeamentos det→spike (necessarios porque os enums diferem):

- WA det: support -> explicit_support-ish; existing_required ->
  existing_authorization_required; no_sponsorship -> explicit_no_support;
  unclear/not_mentioned -> unclear/not_mentioned (mesmo nome na spike).
- German det: required -> required; preferred -> preferred; plus -> None
  (mencao difusa, sem exigencia); None -> not_mentioned.
- English det: True -> "evidence" (binaria, SEM estado); False ->
  not_mentioned.
- Salary det: dict -> tem salario; None -> sem.
- Deadline det: kind employer/employer_textual -> tem data;
  platform_sf -> validade de feed (Nao e prazo; count como
  deterministic_missing para fins de informacao NOVA ao candidato, mas
  registrada como platform validity, nao deadline).
- Student det: internship=True para TODAS as eligible (filtro exige) —
  discriminacao por subtipo NAO existe no deterministico.

O mapeamento e registrado no baseline_deterministic.json e no relatorio
(nunca escondido): relations sobre valores mapeados, com o valor det
CRU tambem presente no artefato para auditoria.
"""

from __future__ import annotations

from typing import Any

# Relation enum (§11)
RELATIONS = (
    "agree", "llm_adds_information", "conflict",
    "deterministic_missing", "llm_missing",
)

# Estados WA considerados INFORMATIVOS (o resto e gap).
_WA_INFORMATIVE = {
    "explicit_support", "explicit_no_support",
    "candidate_must_have_authorization", "existing_authorization_required",
    "international_candidates_accepted", "student_authorization_compatible",
}


def deterministic_baseline(job: dict[str, Any]) -> dict[str, Any]:
    """Lado deterministico computado NA SPIKE (funcoes puras, read-only).

    Executado sobre os MESMOS jobs da amostra (§7 do metodo). Valores
    crus preservados para auditoria.
    """
    from internship_finder import app_intel, opportunity_intel
    title = str(job.get("title") or "")
    desc = str(job.get("description") or "")
    text = f"{title} {desc}"

    wa = app_intel.work_authorization(text)
    gl = app_intel.german_level(text)
    en = app_intel.english_evidence(text)
    sal = opportunity_intel.job_salary(job)
    dkind = app_intel.deadline_kind(job)
    ddate = app_intel.deadline_date(job)

    return {
        "wa_state_raw": wa["state"],           # enum det cru
        "wa_detected": wa.get("detected"),
        "german_raw": gl.level if gl else None,  # required/preferred/plus/None
        "english_raw": en,                       # bool
        "salary_raw": sal,                       # dict | None
        "deadline_kind_raw": dkind,              # employer/employer_textual/platform_sf/none
        "deadline_date_raw": ddate.isoformat() if ddate else None,
        "internship_flag": bool(job.get("internship")),
    }


def wa_relation(det_state: str, llm_state: str | None) -> str:
    """Relation WA (§11) sobre valores MAPEADOS para o vocabulario da spike."""
    if llm_state is None:
        return "llm_missing"
    det_map = {
        "support": "explicit_support",
        "existing_required": "existing_authorization_required",
        "no_sponsorship": "explicit_no_support",
        "unclear": "unclear",
        "not_mentioned": "not_mentioned",
    }
    det = det_map.get(det_state, det_state)
    det_informative = det in _WA_INFORMATIVE
    llm_informative = llm_state in _WA_INFORMATIVE
    if det == llm_state:
        return "agree"
    if det_informative and llm_informative:
        return "conflict"
    if not det_informative and llm_informative:
        return "llm_adds_information"
    if det_informative and not llm_informative:
        # det afirma algo util (ex.: existing_required) e LLM respondeu
        # not_mentioned/unclear: perda de informacao do lado LLM.
        return "llm_missing"
    # ambos gaps (unclear vs not_mentioned): tecnicamente "agree" na
    # ausencia de informacao util; registramos agree (nenhum lado informa).
    return "agree"


def lang_relation(det_raw: str | None, llm_state: str | None) -> str:
    """Relation German/English (§11)."""
    if llm_state is None:
        return "llm_missing"
    det_map = {"required": "required", "preferred": "preferred",
               "plus": "not_mentioned", None: "not_mentioned"}
    det = det_map.get(det_raw, "not_mentioned")
    if det == llm_state:
        return "agree"
    det_informative = det in ("required", "preferred", "not_required")
    llm_informative = llm_state in ("required", "preferred", "not_required")
    if det_informative and llm_informative:
        return "conflict"
    if not det_informative and llm_informative:
        return "llm_adds_information"
    return "llm_missing"


def english_relation(det_raw: bool, llm_state: str | None) -> str:
    """Relation English: det e BINARIA (evidencia), LLM tem estado."""
    if llm_state is None:
        return "llm_missing"
    det_map = {True: "required", False: "not_mentioned"}
    det = det_map.get(det_raw, "not_mentioned")
    if det == llm_state:
        return "agree"
    llm_informative = llm_state in ("required", "preferred", "not_required")
    det_informative = det_raw is True
    if det_informative and llm_informative:
        return "conflict"
    if not det_informative and llm_informative:
        return "llm_adds_information"
    return "llm_missing"


def salary_relation(det_raw: dict | None, llm_field) -> str:
    """Relation Salary: det tem salario (dict) ou nao (None)."""
    if llm_field is None:
        return "llm_missing"
    has_llm_value = (getattr(llm_field, "min", None) is not None
                     or getattr(llm_field, "max", None) is not None)
    det_has = det_raw is not None and any(
        det_raw.get(k) is not None for k in ("min", "max"))
    if det_has and has_llm_value:
        return "agree"  # ambos acharam salario (conflito de VALOR e
        # registrado na tabela cruzada com valores lado a lado)
    if det_has and not has_llm_value:
        return "llm_missing"
    if not det_has and has_llm_value:
        return "llm_adds_information"
    return "agree"  # ambos sem


def deadline_relation(det_kind: str, det_date: str | None, llm_field) -> str:
    """Relation Deadline.

    det informativo = employer/employer_textual (prazo real). platform_sf
    NAO e prazo (validade de feed) — para o CANDIDATO e como se nao
    houvesse; LLM achando prazo textual onde det nao viu e
    llm_adds_information mesmo com platform_sf presente.
    """
    if llm_field is None:
        return "llm_missing"
    llm_date = getattr(llm_field, "date", None)
    det_informative = det_kind in ("employer", "employer_textual")
    if llm_date is not None and det_informative:
        return "agree"
    if llm_date is not None and not det_informative:
        return "llm_adds_information"
    if llm_date is None and det_informative:
        return "llm_missing"
    # llm sem data e det sem prazo: agreement na ausencia
    return "agree"


def student_relation(llm_field) -> str:
    """Relation Student: o det NAO discrimina subtipo (internship=True
    para todas as eligible por construcao) — conceito ausente no lado
    deterministico. Resposta LLM informativa = ``deterministic_missing``
    (det sem campo comparavel); unclear/not_mentioned -> agree-na-
    ausencia; campo ausente -> llm_missing."""
    if llm_field is None:
        return "llm_missing"
    state = getattr(llm_field, "state", None)
    if state in (None, "not_mentioned", "unclear"):
        return "agree"
    return "deterministic_missing"


def compare_record(baseline: dict[str, Any], record) -> dict[str, Any]:
    """Todas as relations de um record contra o baseline deterministico."""
    wa = getattr(record, "work_authorization", None)
    german = getattr(record, "german", None)
    english = getattr(record, "english", None)
    salary = getattr(record, "salary", None)
    deadline = getattr(record, "deadline", None)
    student = getattr(record, "student", None)
    return {
        "job_id": record.job_id,
        "bucket": record.bucket,
        "work_authorization": {
            "deterministic": baseline["wa_state_raw"],
            "llm": wa.state if wa else None,
            "relation": wa_relation(baseline["wa_state_raw"],
                                    wa.state if wa else None),
        },
        "german": {
            "deterministic": baseline["german_raw"],
            "llm": german.state if german else None,
            "relation": lang_relation(baseline["german_raw"],
                                      german.state if german else None),
        },
        "english": {
            "deterministic": baseline["english_raw"],
            "llm": english.state if english else None,
            "relation": english_relation(baseline["english_raw"],
                                         english.state if english else None),
        },
        "deadline": {
            "deterministic": f"{baseline['deadline_kind_raw']}"
                             f"{'@' + baseline['deadline_date_raw'] if baseline['deadline_date_raw'] else ''}",
            "llm": (f"{deadline.kind}@{deadline.date.isoformat()}"
                    if deadline and deadline.date else
                    (deadline.kind if deadline else None)),
            "relation": deadline_relation(baseline["deadline_kind_raw"],
                                          baseline["deadline_date_raw"],
                                          deadline),
        },
        "salary": {
            "deterministic": (
                f"{baseline['salary_raw'].get('min')}-"
                f"{baseline['salary_raw'].get('max')} "
                f"{baseline['salary_raw'].get('currency', '') or ''}"
                if baseline["salary_raw"] else None),
            "llm": (f"{salary.min}-{salary.max} {salary.currency or ''}"
                    if salary and (salary.min is not None
                                   or salary.max is not None) else None),
            "relation": salary_relation(baseline["salary_raw"], salary),
        },
        "student": {
            "deterministic": "internship=True (todas eligible; sem subtipo)",
            "llm": student.state if student else None,
            "relation": student_relation(student),
        },
    }
