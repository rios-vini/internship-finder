#!/usr/bin/env python3
"""Testes OFFLINE da spike Fase E (scripts/test_spike_e.py).

Os 15 grupos da spec §21, 100% offline: toda chamada LLM e injetada via
FakeTransport (estilo test_enrichment.py); fixtures sao SINTETICAS
(empresas "Testcompany"/"Testcorp" — nenhum dado real de vaga); zero
rede, zero API real, zero data/. A key e sempre fake.

Uso:

    .venv/bin/python scripts/test_spike_e.py

Grupos (spec §21):

 1. JSON valido (batch end-to-end com payload completo).
 2. JSON invalido (3 tentativas -> record de erro, sem crash).
 3. Campo fora do enum (rejeicao estrita, outros campos preservados).
 4. Ausencia de evidence em estado informativo.
 5. Response truncada (JSON picado -> parse_error -> record de erro).
 6. Timeout (ReadTimeout -> record de erro, batch continua).
 7. Conflito deterministic vs LLM (relation=conflict).
 8. not_mentioned (ausencia sem erro, sem evidence).
 9. unclear (com e sem evidence).
10. Sponsorship vs relocation (guarda).
11. Existing authorization vs sponsorship (guarda).
12. Required vs preferred (distincao preservada + conflict det×LLM).
13. Deadline sem data explicita (rejeitado; unclear com evidence aceito).
14. Salary incompleto (sem evidence rejeitado; parcial com evidence OK).
15. Uma falha nao interrompe o batch (3 jobs: erro, ok, ok).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import requests  # noqa: E402

from internship_finder.spike_e import input_builder, sample  # noqa: E402
from internship_finder.spike_e.compare import (  # noqa: E402
    lang_relation,
    wa_relation,
)
from internship_finder.spike_e.runner import run_batch  # noqa: E402
from internship_finder.spike_e.schema import (  # noqa: E402
    DeadlineField,
    LanguageField,
    SalaryField,
    StudentField,
    WAField,
    parse_llm_fields,
)

FAILURES: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    if cond:
        print(f"[OK] {name}")
    else:
        print(f"[FAIL] {name} {detail}")
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fakes / fixtures (SINTETICAS — nenhum nome/dado real de vaga)
# ---------------------------------------------------------------------------

FAKE_KEY = "fake-key-DO-NOT-LEAK-1234567890"


class FakeLLMTransport:
    """Transport falso: fila de respostas (status, body) p/ .post.

    Fila esgotada REPETE a ultima resposta; item Exception e levantado.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.last = responses[-1] if responses else None
        self.calls: list[dict] = []

    def post(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers,
                           "payload": payload})
        item = self.responses.pop(0) if self.responses else self.last
        if item is None:
            raise AssertionError("FakeLLMTransport sem resposta na fila")
        if isinstance(item, Exception):
            raise item
        status, body = item
        return status, body

    def get(self, url, headers, timeout):
        raise AssertionError("LLM transport nao deve fazer GET")


def llm_body(content: str, usage: dict | None = None) -> str:
    return json.dumps({
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": usage or {"prompt_tokens": 100, "completion_tokens": 50},
    })


def synth_job(jid: str = "Testcorp Alpha|test:tenant:1", **kw) -> dict:
    """Vaga SINTETICA completa (nenhum dado real)."""
    desc = kw.get("description") or (
        "We are hiring a working student for supply chain analytics. "
        "Fluent German required (C1). Salary: 1200-1400 EUR per month. "
        + "lorem ipsum dolor sit amet " * 200
    )
    return {
        "id": jid,
        "source": kw.get("source", "test:tenant"),
        "title": kw.get("title", "Working Student Data Analytics"),
        "company": kw.get("company", "Testcorp Alpha"),
        "location": "Berlin",
        "country_iso": "DE",
        "url": "https://jobs.example.test/job/1",
        "description": desc,
        "collected_at": "2026-09-28T09:00:00+00:00",
        "internship": True,
        "employment_type": "PART_TIME",
        "raw": {"department": "Supply Chain", "commitment": "Part-time",
                "employment_type": "PART_TIME"},
        **kw.get("extra", {}),
    }


def synth_entry(n: int = 1, job: dict | None = None) -> dict:
    """Entrada no shape do sample.build_sample para o run_batch."""
    job = job or synth_job(jid=f"Testcorp Alpha|test:tenant:{n}")
    return {
        "job_id": job["id"], "company": job["company"],
        "source": job["source"], "url": job["url"],
        "bucket": "e_control", "selection_reason": "test",
        "job": job,
    }


VALID_PAYLOAD = {
    "work_authorization": {
        "state": "candidate_must_have_authorization",
        "evidence": "Applicants must be authorized to work in Germany.",
        "source": "description", "confidence": "high",
    },
    "german": {
        "state": "required",
        "evidence": "Fluent German required (C1).",
        "source": "description", "confidence": "high",
    },
    "english": {
        "state": "not_mentioned", "evidence": None, "source": None,
        "confidence": None,
    },
    "deadline": {"date": None, "kind": None, "evidence": None,
                 "source": None, "confidence": None},
    "salary": {
        "min": 1200.0, "max": 1400.0, "currency": "EUR", "period": "month",
        "evidence": "Salary: 1200-1400 EUR per month",
        "source": "description", "confidence": "high",
    },
    "student": {
        "state": "working_student",
        "evidence": "Working Student Data Analytics",
        "source": "structured_fields", "confidence": "high",
    },
}


def run_fake_batch(transport, entries, records_path: Path):
    """run_batch com transport falso, backoff 0 e log coletor."""
    logs: list[str] = []
    summary = run_batch(
        FAKE_KEY, entries, records_path,
        transport=transport, backoff=(0, 0), sleep=lambda s: None,
        log=logs.append, skip_done=False,
    )
    rows = [json.loads(line) for line in
            records_path.read_text(encoding="utf-8").splitlines() if line]
    return summary, rows, logs


# ---------------------------------------------------------------------------
# Grupos §21
# ---------------------------------------------------------------------------

def group_01_valid_json() -> None:
    print("== Grupo 1: JSON valido ==")
    with tempfile.TemporaryDirectory() as td:
        rp = Path(td) / "records.jsonl"
        summary, rows, _ = run_fake_batch(
            FakeLLMTransport([(200, llm_body(json.dumps(VALID_PAYLOAD)))]),
            [synth_entry(1)], rp)
        check("1.1 batch 1 job ok", summary["n_ok"] == 1
              and summary["n_error"] == 0)
        check("1.2 record com 6 campos extraidos",
              rows and all(rows[0].get(f) is not None for f in
                           ("work_authorization", "german", "english",
                            "deadline", "salary", "student")))
        check("1.3 field_errors vazio", rows[0]["field_errors"] == {})
        check("1.4 usage registrado",
              rows[0]["usage"]["prompt_tokens"] == 100)
        # input montado: cap 12k + normalizacao de HTML
        job = synth_job()
        job["description"] = "<p>" + job["description"] + "</p>"
        llm_input, truncated, _ = input_builder.build_input(job)
        check("1.5 input cap 12k", len(llm_input) <= 12000)
        check("1.6 HTML removido do input", "<p>" not in llm_input)
        job2 = synth_job()
        job2["description"] = "x" * 20000
        _, trunc2, _ = input_builder.build_input(job2)
        check("1.7 truncagem registrada", trunc2 is True)


def group_02_invalid_json() -> None:
    print("== Grupo 2: JSON invalido ==")
    with tempfile.TemporaryDirectory() as td:
        rp = Path(td) / "records.jsonl"
        summary, rows, _ = run_fake_batch(
            FakeLLMTransport([(200, "isto nao e json")]),
            [synth_entry(1)], rp)
        check("2.1 erro apos 3 tentativas", summary["n_error"] == 1
              and rows[0]["attempts"] == 3)
        check("2.2 record de erro preservado",
              rows[0]["error"] is not None
              and rows[0]["error"].startswith("parse_error"))
        check("2.3 campos de extracao ausentes (nunca fallback)",
              rows[0]["work_authorization"] is None)


def group_03_out_of_enum() -> None:
    print("== Grupo 3: campo fora do enum ==")
    bad = dict(VALID_PAYLOAD)
    bad["work_authorization"] = {
        "state": "probably_supports", "evidence": "x",
        "source": "description", "confidence": "high",
    }
    fields, errors = parse_llm_fields(bad)
    check("3.1 campo invalido rejeitado", fields.get("work_authorization")
          is None and "work_authorization" in errors)
    check("3.2 outros campos preservados",
          fields.get("german") is not None
          and fields.get("salary") is not None)


def group_04_missing_evidence() -> None:
    print("== Grupo 4: ausencia de evidence ==")
    bad = dict(VALID_PAYLOAD)
    bad["german"] = {"state": "required", "evidence": None,
                     "source": None, "confidence": "high"}
    fields, errors = parse_llm_fields(bad)
    check("4.1 estado informativo sem evidence rejeitado",
          fields.get("german") is None and "german" in errors)
    bad2 = dict(VALID_PAYLOAD)
    bad2["work_authorization"] = {
        "state": "explicit_support", "evidence": None,
        "source": None, "confidence": "high"}
    fields2, errors2 = parse_llm_fields(bad2)
    check("4.2 explicit_support sem evidence rejeitado",
          fields2.get("work_authorization") is None)


def group_05_truncated_response() -> None:
    print("== Grupo 5: response truncada ==")
    cut = json.dumps(VALID_PAYLOAD)[:60]  # JSON picado no meio
    with tempfile.TemporaryDirectory() as td:
        rp = Path(td) / "records.jsonl"
        summary, rows, _ = run_fake_batch(
            FakeLLMTransport([(200, llm_body(cut))]), [synth_entry(1)], rp)
        check("5.1 JSON picado -> record de erro",
              summary["n_error"] == 1
              and rows[0]["error"].startswith("parse_error"))
        check("5.2 sem resultado parcial usado",
              rows[0]["work_authorization"] is None)


def group_06_timeout() -> None:
    print("== Grupo 6: timeout ==")
    with tempfile.TemporaryDirectory() as td:
        rp = Path(td) / "records.jsonl"
        summary, rows, _ = run_fake_batch(
            FakeLLMTransport([requests.ReadTimeout("timed out")]),
            [synth_entry(1)], rp)
        check("6.1 ReadTimeout -> record de erro",
              summary["n_error"] == 1
              and "request_error:ReadTimeout" in str(rows[0]["error"]))
        check("6.2 batch nao crashou (summary completo)",
              summary["n_ok"] == 0 and summary["aborted"] is False)


def group_07_conflict() -> None:
    print("== Grupo 7: conflito deterministic vs LLM ==")
    check("7.1 det existing_required x LLM explicit_support -> conflict",
          wa_relation("existing_required", "explicit_support") == "conflict")
    check("7.2 det support x LLM explicit_no_support -> conflict",
          wa_relation("support", "explicit_no_support") == "conflict")
    check("7.3 det unclear x LLM informative -> llm_adds_information",
          wa_relation("unclear", "candidate_must_have_authorization")
          == "llm_adds_information")
    check("7.4 det not_mentioned x LLM not_mentioned -> agree",
          wa_relation("not_mentioned", "not_mentioned") == "agree")


def group_08_not_mentioned() -> None:
    print("== Grupo 8: not_mentioned ==")
    payload = {f: {"state": "not_mentioned", "evidence": None,
                   "source": None, "confidence": None}
               for f in ("work_authorization", "german", "english",
                         "student")}
    payload["deadline"] = {"date": None, "kind": None, "evidence": None,
                           "source": None, "confidence": None}
    payload["salary"] = {"min": None, "max": None, "currency": None,
                         "period": None, "evidence": None, "source": None,
                         "confidence": None}
    fields, errors = parse_llm_fields(payload)
    check("8.1 ausencia global sem erros", errors == {})
    check("8.2 todos os campos not_mentioned validos",
          all(fields.get(f) is not None for f in payload))


def group_09_unclear() -> None:
    print("== Grupo 9: unclear ==")
    payload = {
        "work_authorization": {
            "state": "unclear",
            "evidence": "visa sponsorship may be available case by case",
            "source": "description", "confidence": "medium",
        },
        "german": {"state": "unclear", "evidence": None, "source": None,
                   "confidence": None},
    }
    fields, errors = parse_llm_fields(payload)
    check("9.1 unclear COM evidence valido",
          fields.get("work_authorization") is not None and errors == {})
    check("9.2 unclear SEM evidence valido",
          fields.get("german") is not None)


def group_10_sponsorship_vs_relocation() -> None:
    print("== Grupo 10: sponsorship vs relocation ==")
    f, e = parse_llm_fields({"work_authorization": {
        "state": "explicit_support",
        "evidence": "We support your relocation to Berlin",
        "source": "description", "confidence": "high"}})
    check("10.1 relocation-only nao e explicit_support",
          f.get("work_authorization") is None
          and "work_authorization" in e)
    f2, e2 = parse_llm_fields({"work_authorization": {
        "state": "explicit_support",
        "evidence": "We sponsor work visas for this role",
        "source": "description", "confidence": "high"}})
    check("10.2 sponsorship real e explicit_support",
          f2.get("work_authorization") is not None and e2 == {})


def group_11_existing_vs_sponsorship() -> None:
    print("== Grupo 11: existing authorization vs sponsorship ==")
    f, e = parse_llm_fields({"work_authorization": {
        "state": "explicit_support",
        "evidence": "Candidates must already hold a valid work permit",
        "source": "description", "confidence": "high"}})
    check("11.1 already-hold nao e explicit_support",
          f.get("work_authorization") is None)
    f2, e2 = parse_llm_fields({"work_authorization": {
        "state": "existing_authorization_required",
        "evidence": "Candidates must already hold a valid work permit",
        "source": "description", "confidence": "high"}})
    check("11.2 already-hold E existing_authorization_required",
          f2.get("work_authorization") is not None and e2 == {})


def group_12_required_vs_preferred() -> None:
    print("== Grupo 12: required vs preferred ==")
    r = LanguageField(state="required",
                      evidence="German required", source="description",
                      confidence="high")
    p = LanguageField(state="preferred",
                      evidence="German is a plus", source="description",
                      confidence="high")
    check("12.1 estados distintos preservados",
          r.state != p.state)
    check("12.2 det required x LLM preferred -> conflict",
          lang_relation("required", "preferred") == "conflict")
    check("12.3 det required x LLM required -> agree",
          lang_relation("required", "required") == "agree")
    check("12.4 det None x LLM preferred -> llm_adds_information",
          lang_relation(None, "preferred") == "llm_adds_information")


def group_13_deadline_no_explicit_date() -> None:
    print("== Grupo 13: deadline sem data explicita ==")
    f, e = parse_llm_fields({"deadline": {
        "date": None, "kind": "employer_textual",
        "evidence": "apply as soon as possible",
        "source": "description", "confidence": "medium"}})
    check("13.1 kind employer_textual sem data rejeitado",
          f.get("deadline") is None and "deadline" in e)
    f2, e2 = parse_llm_fields({"deadline": {
        "date": None, "kind": "unclear",
        "evidence": "apply as soon as possible",
        "source": "description", "confidence": "low"}})
    check("13.2 kind unclear com evidence (sem data) valido",
          f2.get("deadline") is not None and e2 == {})
    f3, e3 = parse_llm_fields({"deadline": {
        "date": "2026-10-23", "kind": "employer_textual",
        "evidence": "Bewerbungsfrist: 23.10.2026",
        "source": "description", "confidence": "high"}})
    check("13.3 deadline textual com data valida",
          f3.get("deadline") is not None
          and f3["deadline"].date.isoformat() == "2026-10-23")


def group_14_incomplete_salary() -> None:
    print("== Grupo 14: salary incompleto ==")
    f, e = parse_llm_fields({"salary": {
        "min": 1200.0, "max": None, "currency": "EUR", "period": None,
        "evidence": None, "source": None, "confidence": "high"}})
    check("14.1 valor sem evidence rejeitado",
          f.get("salary") is None and "salary" in e)
    f2, e2 = parse_llm_fields({"salary": {
        "min": 1200.0, "max": None, "currency": "EUR", "period": "month",
        "evidence": "Salary: 1200 EUR per month",
        "source": "description", "confidence": "high"}})
    check("14.2 parcial (so min) com evidence valido",
          f2.get("salary") is not None and e2 == {}
          and f2["salary"].min == 1200.0 and f2["salary"].max is None)
    f3, e3 = parse_llm_fields({"salary": {
        "min": None, "max": None, "currency": None, "period": None,
        "evidence": None, "source": None, "confidence": None}})
    check("14.3 salary vazio (sem salario) valido",
          f3.get("salary") is not None and e3 == {})


def group_15_failure_does_not_stop_batch() -> None:
    print("== Grupo 15: uma falha nao interrompe o batch ==")
    with tempfile.TemporaryDirectory() as td:
        rp = Path(td) / "records.jsonl"
        # O cliente faz 3 tentativas por job: o job 1 precisa "falhar as
        # 3" (500 repetido), os jobs 2-3 respondem ok de primeira.
        # FakeLLMTransport repete o ULTIMO item quando a fila esvazia.
        transport = FakeLLMTransport([
            (500, "server exploded"),
            (500, "server exploded"),
            (500, "server exploded"),
            (200, llm_body(json.dumps(VALID_PAYLOAD))),
            (200, llm_body(json.dumps(VALID_PAYLOAD))),
        ])
        summary, rows, logs = run_fake_batch(
            transport,
            [synth_entry(1), synth_entry(2), synth_entry(3)],
            rp)
        check("15.1 batch completou 3 jobs", summary["n_target"] == 3
              and len(rows) == 3)
        check("15.2 falha isolada (1 erro, 2 ok)",
              summary["n_error"] == 1 and summary["n_ok"] == 2)
        check("15.3 jobs pos-erro tem extracao valida",
              rows[2]["work_authorization"] is not None
              and rows[2]["work_authorization"]["state"]
              == "candidate_must_have_authorization")


def group_extra_sample_and_evidence() -> None:
    """Sanidade extra (nao faz parte dos 15): amostra deterministica e
    verificacao de evidence no input (usados pelo manual review)."""
    print("== Extra: amostra deterministica + evidence_in_input ==")
    jobs = []
    for i in range(40):
        jobs.append(synth_job(jid=f"Testcorp {i}|test:tenant:{i}",
                              description="short" * 10))
    s = sample.build_sample(jobs)
    s2 = sample.build_sample(jobs)
    check("X.1 amostra reprodutivel",
          [e["job_id"] for e in s] == [e["job_id"] for e in s2])
    check("X.2 composicao documentada",
          sample.sample_composition(s)
          == sample.sample_composition(s2))
    check("X.3 evidence_in_input tolerante (case/espaco)",
          input_builder.evidence_in_input(
              "Fluent  German REQUIRED.", "text with fluent german required.")
          is True)
    check("X.4 evidence ausente no input detectada",
          input_builder.evidence_in_input(
              "not in the text at all", "some other text") is False)
    # student not_mentioned (correcao do enum §7-F + §9)
    f, e = parse_llm_fields({"student": {
        "state": "not_mentioned", "evidence": None, "source": None,
        "confidence": None}})
    check("X.5 student not_mentioned valido (ausencia nao e erro)",
          f.get("student") is not None and e == {})


def main() -> int:
    group_01_valid_json()
    group_02_invalid_json()
    group_03_out_of_enum()
    group_04_missing_evidence()
    group_05_truncated_response()
    group_06_timeout()
    group_07_conflict()
    group_08_not_mentioned()
    group_09_unclear()
    group_10_sponsorship_vs_relocation()
    group_11_existing_vs_sponsorship()
    group_12_required_vs_preferred()
    group_13_deadline_no_explicit_date()
    group_14_incomplete_salary()
    group_15_failure_does_not_stop_batch()
    group_extra_sample_and_evidence()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        print("FALHAS")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
