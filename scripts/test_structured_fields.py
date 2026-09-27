"""Testes standalone — Fase B: campos estruturados do ``raw`` (ats-scrapers 0.3.0).

Cobre ``src/internship_finder/structured_fields.py`` (novo), o consumo em
``scripts/interface.py`` (botao "candidatar-se" + linhas de detalhe) e as
INVARIAntes da fase (spec §12 — dados mockados, zero rede):

1.  department ausente nao quebra o Job (None; render sem a linha).
2.  department presente e preservado (acessor devolve o valor do raw).
3.  employment_type enum e EVIDENCIA: nao substitui o filtro atual
    (is_student_role continua sendo a autoridade; relation so registra).
4.  conflito de employment type e detectado (Werkstudent + FULL_TIME ->
    'conflict'; INTERN + career event excluido -> 'conflict').
5.  is_remote e preservado como evidencia (True/False/None; False nao vira
    'on_site' declarado; conflito com sinal textual e metrica).
6.  apply_url NAO substitui job.url: segundo botao so aparece quando
    existe, passa _safe_url e DIFERE; job.url permanece no titulo/abrir.
7.  requisition_id nao altera dedup nesta fase (Job.id/external_id
    inalterados pelo consumo; deduplicate ignora o campo).
8.  global_id nao altera identidade (Job.id permanece <company>|<source>:
    <external_id>).
9.  campos desconhecidos continuam preservados no raw.
10. ausencia dos campos em ATS que nao os fornecem nao quebra o pipeline
    (job sem raw; job com raw vazio; render SQLite-like sem raw).
11. ranking permanece identico com o novo consumo (score/ordem mock A/B).
12. eligible permanece identico (select_eligible ignora os campos novos;
    mesmo conjunto com/sem raw estruturado).

Padrao dos demais scripts: [OK]/[FAIL] e termina com "TUDO OK" (exit 0) ou
"FALHAS:" (exit != 0).

Uso:  .venv/bin/python scripts/test_structured_fields.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import interface  # noqa: E402
from internship_finder import structured_fields as sf  # noqa: E402
from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.dedup import deduplicate  # noqa: E402
from internship_finder.filters import is_student_role, select_eligible  # noqa: E402
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.ranking import rank_jobs, score_job  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def base_job(**over) -> dict:
    """Vaga mock minima, no formato do snapshot (dict serializado)."""
    job = {
        "id": "ACME|smartrecruiters:acme:123",
        "source": "smartrecruiters:acme",
        "title": "Werkstudent Procurement (m/w/d)",
        "company": "ACME",
        "location": "München, DE",
        "country": "DE",
        "country_iso": "DE",
        "remote": None,
        "url": "https://jobs.smartrecruiters.com/acme/123",
        "description": "Support the purchasing team with analyses.",
        "internship": True,
        "posted_at": "2026-09-20T00:00:00+00:00",
        "collected_at": "2026-09-26T00:00:00+00:00",
        "external_id": "123",
        "employment_type": None,
        "raw": {},
    }
    job.update(over)
    return job


# ---------------------------------------------------------------------------
# 1-2. department: ausente nao quebra; presente e preservado
# ---------------------------------------------------------------------------

def test_department() -> None:
    print("== [1-2] department: ausente nao quebra; presente preservado ==")
    no_dep = base_job(raw=None)
    check("1. sem raw -> department() = None", sf.department(no_dep) is None)
    row = interface._row_html(1, copy.deepcopy(no_dep))
    check("1. render sem raw nao quebra e sem linha 'área:'",
          "área:" not in row)
    empty_raw = base_job(raw={})
    check("1. raw vazio -> None", sf.department(empty_raw) is None)
    ws_dep = base_job(raw={"department": "  Purchasing  "})
    check("2. department preservado com strip",
          sf.department(ws_dep) == "Purchasing")
    check("2. string so-whitespace -> None",
          sf.department(base_job(raw={"department": "   "})) is None)
    row = interface._row_html(1, copy.deepcopy(ws_dep))
    check("2. render exibe 'área: Purchasing' (escapada)",
          "área: Purchasing" in row)
    evil = base_job(raw={"department": "<script>x</script>"})
    row = interface._row_html(1, copy.deepcopy(evil))
    check("2. department e escapado no HTML",
          "<script>x</script>" not in row
          and "área: &lt;script&gt;x&lt;/script&gt;" in row)


# ---------------------------------------------------------------------------
# 3-4. employment_type: evidencia, nao filtro; conflitos detectados
# ---------------------------------------------------------------------------

def test_employment_type_evidence() -> None:
    print("== [3-4] employment_type: evidencia; conflitos detectados ==")
    # 3. enum JAMAIS substitui o filtro atual: Werkstudent segue student-role
    #    com enum FULL_TIME; a classificacao atual e a autoridade.
    ws_full = base_job(raw={"employment_type": "FULL_TIME"},
                       employment_type="FULL_TIME")
    check("3. enum FULL_TIME nao derruba is_student_role (Werkstudent)",
          is_student_role(ws_full["title"], ws_full["description"], "FULL_TIME"))
    check("3. relation registra o conflito (nao corrige)",
          sf.employment_type_relation(ws_full) == "conflict")
    # Filtro de eligible NAO usa o enum do raw: mesmo conjunto com/sem
    without = copy.deepcopy(ws_full); without["raw"] = None
    check("3. select_eligible ignora o enum do raw (mesmo resultado)",
          len(select_eligible([ws_full])[0]) == len(select_eligible([without])[0]) == 1)
    # 4. conflitos detectados
    check("4. Werkstudent + FULL_TIME -> conflict",
          sf.employment_type_relation(ws_full) == "conflict")
    # Caso real da auditoria: vaga de PROGRAMA/career-event marcada INTERN no
    # ATS mas EXCLUIDA pela classificacao atual (Management Trainee e
    # exclusao de programa no filtro — a autoridade da fase).
    intern_event = base_job(
        title="Management Trainee Program (m/w/d)",
        description="Join our graduate program events.",
        raw={"employment_type": "INTERN"},
        employment_type="INTERN",
    )
    check("4. programa excluido + enum INTERN -> conflict",
          not is_student_role(intern_event["title"], intern_event["description"], "INTERN")
          and sf.employment_type_relation(intern_event) == "conflict")
    intern_ok = base_job(title="Intern Procurement",
                         raw={"employment_type": "INTERN"},
                         employment_type="INTERN")
    check("4. Intern real + enum INTERN -> match",
          sf.employment_type_relation(intern_ok) == "match")
    check("4. sem enum -> missing",
          sf.employment_type_relation(base_job()) == "missing")
    check("4. label fora do enum (softgarden OTHER) -> missing",
          sf.employment_type_relation(
              base_job(raw={"employment_type": "OTHER"},
                       employment_type="OTHER")) == "missing")
    check("4. PART_TIME e compativel (regime tipico) -> match",
          sf.employment_type_relation(
              base_job(raw={"employment_type": "PART_TIME"},
                       employment_type="PART_TIME")) == "match")
    # Display: enum so aparece quando DIFERE do label canonico exibido
    row = interface._row_html(1, copy.deepcopy(ws_full))
    check("4. UI NAO exibe 'classificação ATS' quando enum == canonico",
          "classificação ATS" not in row)
    diverge = base_job(raw={"employment_type": "FULL_TIME"},
                       employment_type="PART_TIME")
    row = interface._row_html(1, copy.deepcopy(diverge))
    check("4. UI exibe 'classificação ATS' quando enum difere do canonico",
          "classificação ATS: FULL_TIME" in row)


# ---------------------------------------------------------------------------
# 5. is_remote: evidencia preservada; conflito com sinal textual
# ---------------------------------------------------------------------------

def test_is_remote() -> None:
    print("== [5] is_remote: preservado como evidencia ==")
    check("5. True/False preservados",
          sf.is_remote_flag(base_job(raw={"is_remote": True})) is True
          and sf.is_remote_flag(base_job(raw={"is_remote": False})) is False)
    check("5. sem raw -> None", sf.is_remote_flag(base_job(raw=None)) is None)
    check("5. valor nao-bool -> None",
          sf.is_remote_flag(base_job(raw={"is_remote": "yes"})) is None)
    # False NAO vira on_site: work_mode continua not_mentioned sem texto
    from internship_finder.opportunity_intel import work_mode
    check("5. is_remote=False nao fabrica on_site (work_mode mantem regra)",
          work_mode(base_job(raw={"is_remote": False})) == "not_mentioned")
    # conflito: ATS False x texto hybrid
    hybrid = base_job(
        description="Du arbeitest hybrid: 3 Tage remote.",
        raw={"is_remote": False},
    )
    check("5. conflito flag False x texto hybrid detectado",
          sf.remote_relation(hybrid) == "conflict")
    remote_true = base_job(raw={"is_remote": True})
    check("5. flag True sem sinal textual -> match",
          sf.remote_relation(remote_true) == "match")
    check("5. sem flag -> missing",
          sf.remote_relation(base_job()) == "missing")


# ---------------------------------------------------------------------------
# 6. apply_url: segundo botao, nunca substitui job.url
# ---------------------------------------------------------------------------

def test_apply_url() -> None:
    print("== [6] apply_url: segundo botao; job.url preservada ==")
    job = base_job(raw={"apply_url": "https://acme.com/apply/123"})
    check("6. apply_url lido do raw", sf.apply_url(job) is not None)
    row = interface._row_html(1, copy.deepcopy(job))
    check("6. botao candidatar-se renderizado ao lado do abrir",
          "candidatar-se&nbsp;↗" in row and "abrir&nbsp;↗" in row)
    check("6. job.url permanece no link do titulo",
          'href="https://jobs.smartrecruiters.com/acme/123"' in row)
    check("6. apply_url NUNCA substitui job.url no botao abrir",
          'href="https://acme.com/apply/123"' in row
          and row.count('class="open" href="https://jobs.smartrecruiters.com/acme/123"') == 1)
    # igual a job.url -> nao renderiza duplicado
    same = base_job(raw={"apply_url": "https://jobs.smartrecruiters.com/acme/123"})
    row = interface._row_html(1, copy.deepcopy(same))
    check("6. apply_url == job.url -> sem segundo botao",
          "candidatar-se" not in row)
    # scheme invalido -> nao vira href
    bad = base_job(raw={"apply_url": "javascript:alert(1)"})
    check("6. scheme invalido rejeitado", sf.apply_url(bad) is None)
    row = interface._row_html(1, copy.deepcopy(bad))
    check("6. scheme invalido nao renderiza botao", "candidatar-se" not in row)
    # sem apply_url -> nada muda
    row = interface._row_html(1, copy.deepcopy(base_job()))
    check("6. sem apply_url -> so o botao abrir", "candidatar-se" not in row)


# ---------------------------------------------------------------------------
# 7-8. requisition_id / global_id: fora de dedup/identidade nesta fase
# ---------------------------------------------------------------------------

def test_identity_untouched() -> None:
    print("== [7-8] requisition_id/global_id fora de dedup/identidade ==")
    company = Company(name="ACME", ats="smartrecruiters", slug="acme", query="ACME")
    item = {
        "title": "Werkstudent Procurement",
        "url": "https://jobs.smartrecruiters.com/acme/123",
        "external_id": "123",
        "requisition_id": "REF-999",
        "global_id": "smartrecruiters:123",
        "department": "Purchasing",
        "employment_type": "FULL_TIME",
    }
    job = AtsJobAdapter().to_job(dict(item), company)
    check("7. Job.id NAO usa requisition_id (P1.1: company|source:external_id)",
          job.id == "ACME|smartrecruiters:acme:123")
    check("7. external_id permanece o do ATS (123), nao o req_id",
          job.external_id == "123")
    check("7. req_id preservado apenas como evidencia no raw",
          job.raw.get("requisition_id") == "REF-999")
    # dedup deterministico: MESMO comportamento com/sem req_id no raw
    a = {"id": "A|s:x:1", "source": "s:x", "company": "A", "title": "T",
         "url": "https://a/1", "external_id": "1",
         "collected_at": "2026-09-26T00:00:00+00:00",
         "raw": {"requisition_id": "REF-1"}}
    b = {"id": "A|s:x:1", "source": "s:x", "company": "A", "title": "T",
         "url": "https://a/1", "external_id": "1",
         "collected_at": "2026-09-26T00:00:00+00:00",
         "raw": {"requisition_id": "REF-1"}}
    c = {"id": "B|s:y:9", "source": "s:y", "company": "B", "title": "T",
         "url": "https://b/9", "external_id": "9",
         "collected_at": "2026-09-26T00:00:00+00:00",
         "raw": {"requisition_id": "REF-1"}}  # mesmo req_id, vaga distinta
    out, _stats, _removed = deduplicate([a, b, c])
    check("7. dedup nesta fase: colapsa o duplicado real, mantem vaga distinta "
          "com mesmo req_id (sem cross-req dedup)",
          len(out) == 2
          and {j["id"] for j in out} == {"A|s:x:1", "B|s:y:9"})
    check("8. global_id NAO altera identidade (fica no raw)",
          job.raw.get("global_id") == "smartrecruiters:123"
          and job.id == "ACME|smartrecruiters:acme:123")
    check("8. acessor global_id le o raw", sf.global_id({"raw": {"global_id": "x:1"}}) == "x:1")


# ---------------------------------------------------------------------------
# 9-10. raw preserva desconhecidos; ausencia nao quebra pipeline
# ---------------------------------------------------------------------------

def test_raw_robustness() -> None:
    print("== [9-10] raw preserva desconhecidos; ausencia nao quebra ==")
    company = Company(name="ACME", ats="smartrecruiters", slug="acme", query="ACME")
    job = AtsJobAdapter().to_job({
        "title": "Werkstudent", "url": "https://a/1", "external_id": "1",
        "whatever_future_field": {"deep": [1, 2]}, "department": "X",
    }, company)
    check("9. campo desconhecido preservado no raw",
          job.raw.get("whatever_future_field") == {"deep": [1, 2]})
    # 10. pipeline tolera ausencia total
    for name, j in [
        ("sem raw", base_job(raw=None)),
        ("raw vazio", base_job(raw={})),
        ("raw sem nenhum campo conhecido", base_job(raw={"zzz": 1})),
    ]:
        ok = (sf.department(j) is None and sf.employment_type_enum(j) is None
              and sf.is_remote_flag(j) is None and sf.commitment_label(j) is None
              and sf.apply_url(j) is None and sf.requisition_id(j) is None
              and sf.global_id(j) is None
              and sf.employment_type_relation(j) == "missing"
              and sf.remote_relation(j) == "missing")
        check(f"10. acessores neutros em job {name}", ok)
        row = interface._row_html(1, copy.deepcopy(j))
        check(f"10. render ok em job {name}",
              "área:" not in row and "candidatar-se" not in row
              and "classificação ATS" not in row)
    # caminho SQLite-like: raw=None (coluna excluida do DB) nao quebra render
    check("10. job dict sem campo raw algum (KeyError-free)",
          sf.department({"title": "x"}) is None)


# ---------------------------------------------------------------------------
# 11-12. ranking/eligible identicos com o novo consumo
# ---------------------------------------------------------------------------

def test_ranking_eligible_unchanged() -> None:
    print("== [11-12] ranking e eligible identicos com novo consumo ==")
    plain = [base_job(title=f"Werkstudent Procurement {i}") for i in range(3)]
    enriched = [base_job(
        title=f"Werkstudent Procurement {i}",
        raw={"department": "Purchasing", "employment_type": "FULL_TIME",
             "is_remote": False, "apply_url": "https://a/apply",
             "requisition_id": f"REF-{i}", "global_id": f"smartrecruiters:{i}"},
    ) for i in range(3)]
    s_plain = [score_job(j) for j in plain]
    s_enriched = [score_job(j) for j in enriched]
    check("11. scores identicos com/sem campos estruturados",
          s_plain == s_enriched)
    check("11. ordem identica (rank_jobs deterministico)",
          [j["id"] for j in rank_jobs(plain)] == [j["id"] for j in rank_jobs(enriched)])
    e_plain = select_eligible(plain, country="all")
    e_enriched = select_eligible(enriched, country="all")
    check("12. eligible identico (mesmo conjunto/contagens)",
          len(e_plain[0]) == len(e_enriched[0]) == 3
          and e_plain[1] == e_enriched[1])
    # o render consome os campos sem mutar a vaga (read-only)
    j = copy.deepcopy(enriched[0])
    frozen = copy.deepcopy(j)
    interface._row_html(1, j)
    check("11. render nao muta o dict da vaga", j == frozen)


def main() -> int:
    test_department()
    test_employment_type_evidence()
    test_is_remote()
    test_apply_url()
    test_identity_untouched()
    test_raw_robustness()
    test_ranking_eligible_unchanged()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
