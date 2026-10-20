#!/usr/bin/env python3
"""F87 — flag "não-avaliável" + liveness no 1º sighting (offline).

Princípio: NÃO gastar a análise do dono em coisa que não presta.

Metade (a) — **flag ``not_assessable``** (display + digest, NUNCA
exclusão): acende quando a descrição que chegou ao eligible não dá base
de julgamento — vazia (0 chars úteis), abaixo do limiar medido no Passo 0
(600 chars; corpus 20/10: mediana 2.490, p25 1.469, henkel 89534 = 584 de
SAML wall) ou com padrão textual de login-wall/placeholder. O flag é
SINAL (⚠️ no card + linha no digest), não filtro. A hidratação (F20/F65)
CURA: texto >= limiar sem wall => a anotação idempotente apaga o campo.

Metade (b) — **liveness no 1º sighting**: candidatas NOVAS (primeira
aparição do ID contra o snapshot arquivado — MESMO diff do digest) ganham
1 fetch barato do ``url_liveness`` ANTES da janela de análise:
404/410 => mecanismo F39 (remoção do JSON); 200-falso textual (Festo
"Diese Stelle wurde leider bereits besetzt") => morta para display (🔗 +
desce do top, FICA no JSON — semântica F20/F39); timeout/rede NUNCA
prova morte. Budget: MESMO knob diário do F65
(``INTERNSHIP_FINDER_HYDRATION_BUDGET``; default 0 = OFF, regra 9), com
o gasto do intake abatido do F65 no mesmo run.

Fixtures VERBATIM (as 7 do registro, RECUSAS-FEEDBACK-PIPELINE-2026-10):
descrições reais de 584/1.561 chars (henkel cornerstone), ids reais de
Amazon Koblenz (absolventa 13423224, desc 0 chars no dataset vivo),
TYTAN e Impulsgrad (sf_dataset:bundesagentur, 0 chars), corpo Festo
200-falso e Simvia 404. Zero rede: openers fake scriptados; tempdir para
o integration path do ``_intake_liveness``; nada de data/ de produção.

Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import minimal_page as mp  # noqa: E402
import ranking_digest as rdi  # noqa: E402
import refresh_daily as rd  # noqa: E402
import url_liveness as ul  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

BUDGET_ENV = "INTERNSHIP_FINDER_HYDRATION_BUDGET"
DEAD_OFF_ENV = "INTERNSHIP_FINDER_DEAD_REMOVAL_OFF"


def section(name: str) -> None:
    print(f"\n--- {name} ---")


def check(name: str, cond) -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"[OK] {name}")
    else:
        print(f"[FAIL] {name}")
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fixtures VERBATIM (dataset vivo 20/10 + registro do dono)
# ---------------------------------------------------------------------------

# henkel 89534 — "Internship Data & Stakeholder Operations" — 584 chars de
# SAML wall (sem idioma/início/duração): o caso-âncora do limiar 600.
HENKEL_89534_DESC = (
    "About this Position What you´ll do Become part of a team that bridges busine"
    "ss operations, data, and digital solutions within Henkel Adhesive Technologi"
    "es Transform business questions into insights, recommendations, and tangible"
    " improvements in data and software Work directly with stakeholders across Sa"
    "les, Finance, and Operations to solve real business challenges Gain hands-on"
    " experience in performance management, operational excellence, process optim"
    "ization, and business enablement Contribute to projects that improve the way"
    " teams plan, report, collaborate, and make decisions"
)
assert len(HENKEL_89534_DESC) == 584

# henkel 89499 — "Internship Master Data Project" — 1.561 chars, MESMA wall
# (fragmento tasks-only atrás da autenticação). Fora do limiar 600 POR
# CONTRATO das regras medidas (doc no relatório: cabe ao enrichment F81).
HENKEL_89499_DESC = (
    "About this Position As a Customer Data CRM Master Data Intern, you will supp"
    "ort different projects in executing key initiatives related to CRM master da"
    "ta migration and customer data transformation projects. You will play a crit"
    "ical role in ensuring data quality, consistency, and governance during the m"
    "igration process and contribute to enhancing customer data structures and ow"
    "nership frameworks. What you´ll do Become a team member of the Global Adhesi"
    "ves Sales Excellence team responsible for driving business activities, tools"
    ", and processes to support the best execution of the sales strategy and shap"
    "ing our ideal salesforce Assist the implementation of data governance framew"
    "orks, policies, standards, and procedures Support data cleansing and migrati"
    "on activities for CRM migration - data mapping, cleansing, transformation, r"
    "econciliation and validation to ensure accuracy and consistency Facilitate w"
    "ith change management activities towards vast user community for the ongoing"
    " projects and initiatives Conduct analyses to support data-driven decision-m"
    "aking for customer segmentation or CRM optimization Prepare and maintain doc"
    "umentation, user guides, communication content and training materials to sup"
    "port data management processes Assist with reporting, KPIs, and dashboards t"
    "o track data quality and governance progress Support and contribute to maint"
    "aining and improving customer master data quality, ensuring accuracy, comple"
    "teness, and consistency across systems through data validation and enrichmen"
    "t activities using defined business rules"
)
assert len(HENKEL_89499_DESC) == 1561

HENKEL_89534 = {
    "id": "henkel|cornerstone:henkel:89534",
    "title": "Internship Data & Stakeholder Operations",
    "company": "henkel",
    "description": HENKEL_89534_DESC,
    "score": 9.0,
}
HENKEL_89499 = {
    "id": "henkel|cornerstone:henkel:89499",
    "title": "Internship Master Data Project",
    "company": "henkel",
    "description": HENKEL_89499_DESC,
    "score": 8.5,
}
AMAZON_KOBLENZ = {
    "id": "Amazon Koblenz GmbH - C44|absolventa:13423224",
    "title": "Logistik Start 2027 (m/w/d)",
    "company": "Amazon Koblenz GmbH - C44",
    "description": "",
    "score": 8.0,
}
TYTAN = {
    "id": "TYTAN Technologies GmbH|sf_dataset:bundesagentur:10001-1003615923-S",
    "title": "HR Systems & Analytics Intern (m/f/d)",
    "company": "TYTAN Technologies GmbH",
    "description": "",
    "score": 7.0,
}
IMPULSGRAD = {
    "id": "Impulsgrad GmbH|sf_dataset:bundesagentur:10001-1003575313-S",
    "title": "Werkstudent:in / Praktikant:in Operations & Entrepreneurship",
    "company": "Impulsgrad GmbH",
    "description": "",
    "score": 6.0,
}
FESTO = {
    "id": "Jobs Festo|sf_dataset:successfactors:1260918301",
    "title": "Praktikum in der Logistik",
    "company": "Jobs Festo",
    "url": "https://jobs.festo.com/job/St-Ingbert/1260918301",
    "score": 7.5,
}
SIMVIA = {
    "id": "Simvia|sf_dataset:recruitee:2100111",
    "title": "Revenue Operations Internship",
    "company": "Simvia",
    "url": "https://simvia.recruitee.com/o/revenue-operations-internship",
    "score": 7.2,
}
FESTO_BESETZT_BODY = (
    b"<html><head><title>Stelle besetzt</title></head><body>"
    b"<p>Diese Stelle wurde leider bereits besetzt.</p>"
    b"<p>Schauen Sie sich gerne unsere anderen offenen Stellen an.</p>"
    b"</body></html>"
)
# Counter-case — desc curta LEGÍTIMA (frase completa; caso real do corpus:
# Oliver Wyman phenom, 316 chars). Acende ``desc_curta`` e NADA mais.
OW_LEGIT_SHORT_DESC = (
    "Oliver Wyman - Data & Analytics Consulting - Intern (m/w/d). You will "
    "support client teams in building quantitative models and dashboards. "
    "Ideal for students with a quantitative background and proficiency in "
    "Python or R."
)
LONG_COMPLETE_DESC = "Descrição completa com requisitos, idioma, início e duração. " * 60


class _Resp:
    """Fake de resposta HTTP com corpo e URL final (padrão test_f39)."""

    def __init__(self, body: bytes = b"", url: str | None = None):
        self._body = body
        self.url = url

    def read(self, n: int = -1) -> bytes:
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(status_map: dict, error_urls: set, bodies: dict):
    """GET fake: status por URL (>=400 => HTTPError), error_urls = rede fora."""
    def open(req, timeout=None):
        url = req.full_url
        if url in error_urls:
            raise TimeoutError("simulated timeout")
        status = status_map.get(url, 200)
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "err", {}, None)
        return _Resp(bodies.get(url, b"<html><title>Job page</title></html>"),
                     url)
    return open


# ---------------------------------------------------------------------------
# A — detector puro: flag acende (fixtures verbatim) e a ordem de diagnóstico
# ---------------------------------------------------------------------------

def test_detector() -> None:
    section("A: detector assessability_reason — fixtures verbatim")
    check("henkel 89534 (584 chars SAML wall) => desc_curta",
          rd.assessability_reason(HENKEL_89534) == "desc_curta")
    check("Amazon Koblenz (absolventa 13423224, desc 0) => desc_vazia",
          rd.assessability_reason(AMAZON_KOBLENZ) == "desc_vazia")
    check("TYTAN (bundesagentur, desc 0) => desc_vazia",
          rd.assessability_reason(TYTAN) == "desc_vazia")
    check("Impulsgrad (bundesagentur, desc 0) => desc_vazia",
          rd.assessability_reason(IMPULSGRAD) == "desc_vazia")
    placeholder = dict(HENKEL_89499,
                       id="henkel|cornerstone:henkel:89300",
                       description="About this Position Please add a text "
                                   "and explain the position " + "x" * 1700)
    check("henkel 89300 (placeholder do template) => login_wall",
          rd.assessability_reason(placeholder) == "login_wall")
    check("wall vence curta (desc 200 com 'saml') => login_wall",
          rd.assessability_reason({"description": "saml redirect " + "x" * 200})
          == "login_wall")
    check("limiar: 599 chars => desc_curta",
          rd.assessability_reason({"description": "x" * 599}) == "desc_curta")
    check("limiar: 600 chars => avaliável (None)",
          rd.assessability_reason({"description": "x" * 600}) is None)
    check("counter-case: desc curta LEGÍTIMA acende desc_curta (sinal)",
          rd.assessability_reason({"description": OW_LEGIT_SHORT_DESC})
          == "desc_curta")
    check("counter-case: desc completa longa => None",
          rd.assessability_reason({"description": LONG_COMPLETE_DESC}) is None)
    check("descrição ausente (campo fora do dict) => desc_vazia",
          rd.assessability_reason({"id": "a|b:1"}) == "desc_vazia")
    # Padrões FP-nus do Passo 0 NÃO acendem wall: "design in…"/"InDesign"
    # contêm "sign in" como substring — fora do detector (16 FPs medidos).
    # Desc curta com os FPs => desc_curta (limiar), NUNCA login_wall.
    fp = {"id": "x|y:1",
          "description": "system design interview and InDesign work. "
                         "We build dashboards."}
    reason_fp = rd.assessability_reason(fp)
    check('FP "design in/InDesign" NÃO acende login_wall (fica no limiar)',
          reason_fp == "desc_curta" and reason_fp != "login_wall")


# ---------------------------------------------------------------------------
# B — anotação idempotente: acende, CURA pela hidratação, NUNCA exclui
# ---------------------------------------------------------------------------

def test_annotation() -> None:
    section("B: _annotate_assessability — acende, cura, nunca exclui")
    ranking = [dict(HENKEL_89534), dict(AMAZON_KOBLENZ),
               {"id": "a|b:1", "title": "Ok", "score": 5.0,
                "description": LONG_COMPLETE_DESC}]
    st = rd._annotate_assessability(ranking)
    check("flag acende: henkel desc_curta",
          ranking[0].get(rd.NOT_ASSESSABLE_FLAG) == "desc_curta")
    check("flag acende: Amazon desc_vazia",
          ranking[1].get(rd.NOT_ASSESSABLE_FLAG) == "desc_vazia")
    check("desc completa NÃO é flaggada",
          rd.NOT_ASSESSABLE_FLAG not in ranking[2])
    check("contadores: 2 novas, população por motivo {curta:1, vazia:1}",
          st["flagged"] == 2 and st["by_reason"] == {"desc_curta": 1,
                                                     "desc_vazia": 1})
    check("anti-exclusão: 3 vagas seguem no ranking, ordem intacta",
          len(ranking) == 3 and ranking[0]["id"] == HENKEL_89534["id"])
    check("anti-exclusão: score/emprego intatos",
          ranking[0]["score"] == 9.0 and ranking[1]["score"] == 8.0)
    # Idempotência: 2ª passada => flagged 0 (já marcadas), população igual.
    st2 = rd._annotate_assessability(ranking)
    check("idempotente: 2ª passada flagged=0",
          st2["flagged"] == 0 and st2["by_reason"] == st["by_reason"])
    # CURA pela hidratação: F20/F65 trouxe texto >= limiar => campo some.
    ranking[0]["description"] = LONG_COMPLETE_DESC  # hidratada
    st3 = rd._annotate_assessability(ranking)
    check("hidratação CURA: campo some da henkel",
          rd.NOT_ASSESSABLE_FLAG not in ranking[0])
    check("cura contada: cleared=1 com id",
          st3["cleared"] == 1
          and st3["cleared_ids"] == [HENKEL_89534["id"]])
    # Cura não abre exceção para wall: hidratação que trouxe texto MAS o
    # padrão de wall persiste => flag permanece (login_wall).
    ranking[1]["description"] = "Please add a text " + "y" * 700
    st4 = rd._annotate_assessability(ranking)
    check("wall persistente NÃO é curada (login_wall mantido)",
          ranking[1].get(rd.NOT_ASSESSABLE_FLAG) == "login_wall"
          and st4["by_reason"].get("login_wall") == 1)


# ---------------------------------------------------------------------------
# C — 200-falso textual (Festo): morta; FP-guard do corpo grande
# ---------------------------------------------------------------------------

def test_fake200() -> None:
    section("C: 200-falso textual — Festo besetzt (corpo curto) e FP-guard")
    opener = _opener({}, set(), {FESTO["url"]: FESTO_BESETZT_BODY})
    dead, _bodies, stats = ul.check_liveness_v2(
        [dict(FESTO)], opener=opener, want_bodies=False)
    check("Festo 200-falso => morta (soft-dead)",
          dead == {FESTO["id"]} and FESTO["id"] in stats["soft_dead_ids"])
    check("200-falso NÃO é hard-dead (remoção do JSON é exclusiva do 404/410)",
          FESTO["id"] not in stats["hard_dead_ids"])
    # FP-guard: marcador citado no MEIO de um corpo grande e vivo => vivo.
    big_body = (b"<html><head><title>Praktikum Logistik</title></head><body>"
                + b"x" * 8000
                + b"<p>position filled feedback welcome</p></body></html>")
    opener_big = _opener({}, set(), {FESTO["url"]: big_body})
    dead2, _, stats2 = ul.check_liveness_v2(
        [dict(FESTO)], opener=opener_big, want_bodies=False)
    check("mesmo marcador em corpo GRANDE => vivo (gate do corpo curto)",
          dead2 == set() and stats2["soft_dead"] == 0)
    # Marcador existente F20 segue valendo (sem gate — contrato F20).
    db_body = b"<html><body>Sorry, this position has been filled.</body></html>"
    opener_f20 = _opener({}, set(), {FESTO["url"]: db_body})
    dead3, _, _ = ul.check_liveness_v2(
        [dict(FESTO)], opener=opener_f20, want_bodies=False)
    check("marcador F20 clássico segue morto (sem regressão F20)",
          dead3 == {FESTO["id"]})


# ---------------------------------------------------------------------------
# D — liveness no 1º sighting: integração _intake_liveness (tempdir)
# ---------------------------------------------------------------------------

def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _stage_env(value: str):
    class _Ctx:
        def __enter__(self):
            self._old = os.environ.get(BUDGET_ENV)
            os.environ[BUDGET_ENV] = value
            return self

        def __exit__(self, *a):
            if self._old is None:
                os.environ.pop(BUDGET_ENV, None)
            else:
                os.environ[BUDGET_ENV] = self._old
    return _Ctx()


def _stage_dead_off():
    class _Ctx:
        def __enter__(self):
            os.environ[DEAD_OFF_ENV] = "1"
            return self

        def __exit__(self, *a):
            os.environ.pop(DEAD_OFF_ENV, None)
    return _Ctx()


def test_intake_liveness() -> None:
    section("D: _intake_liveness — Festo 200-falso, Simvia 404, timeout")
    with tempfile.TemporaryDirectory(prefix="f87_intake_") as tmp:
        data_dir = Path(tmp) / "data"
        archive_dir = Path(tmp) / "archive"
        data_dir.mkdir()
        archive_dir.mkdir()
        old_job = {"id": "velha|x:1", "title": "Velha", "url": "https://v/1",
                   "description": LONG_COMPLETE_DESC, "score": 1.0}
        timeout_job = {"id": "lenta|y:2", "title": "Lenta",
                       "url": "https://lenta.example/2",
                       "description": LONG_COMPLETE_DESC, "score": 2.0}
        ranking = [dict(FESTO), dict(SIMVIA), dict(timeout_job), dict(old_job)]
        _write_json(data_dir / "eligible_jobs.json", ranking)
        _write_json(archive_dir / "eligible_jobs.json", [dict(old_job)])
        metrics = data_dir / "collection_metrics.jsonl"
        metrics.write_text("", encoding="utf-8")
        opener = _opener(
            {FESTO["url"]: 200, SIMVIA["url"]: 404},
            error_urls={timeout_job["url"]},
            bodies={FESTO["url"]: FESTO_BESETZT_BODY},
        )
        before = (data_dir / "eligible_jobs.json").read_bytes()
        with _stage_env("10"):
            rec = rd._intake_liveness(
                data_dir, archive_dir, metrics, run_id="r87",
                opener=opener)
        check("3 candidatas novas detectadas (diff vs snapshot)",
              rec["new_candidates"] == 3)
        check("budget 10 => 3 fetches (1 por nova)",
              rec["fetched"] == 3)
        check("mortas: Festo (soft) + Simvia (hard); timeout NÃO é morte",
              rec["dead"] == 2 and rec["hard_dead"] == 1
              and rec["soft_dead"] == 1 and rec["net_errors"] == 1)
        check("timeout => viva (nada de falso-positivo)",
              timeout_job["id"] not in set(rec["dead_ids"]))
        check("mecanismo F39: Simvia 404 REMOVIDA do JSON",
              rec["removed"] == 1
              and rec["removed_ids"] == [SIMVIA["id"]])
        persisted = json.loads(
            (data_dir / "eligible_jobs.json").read_text(encoding="utf-8"))
        check("JSON reescrito sem o hard-dead; soft-dead Festo FICA (F20)",
              SIMVIA["id"] not in {j["id"] for j in persisted}
              and FESTO["id"] in {j["id"] for j in persisted})
        check("record carrega dead_ids para o chamador (display/digest)",
              set(rec["dead_ids"]) == {FESTO["id"], SIMVIA["id"]})
        check("metrica intake_liveness gravada (type + provenance)",
              "intake_liveness" in metrics.read_text(encoding="utf-8")
              and rec["type"] == "intake_liveness"
              and rec["removed_entries"][0]["status"] == 404)
        check("JSON original só mudou pela remoção F39 (resto intacto)",
              json.loads(before.decode("utf-8")) != persisted
              and len(json.loads(before.decode("utf-8")))
              - len(persisted) == 1)


def test_intake_contracts() -> None:
    section("E: _intake_liveness — contrato budget/baseline/kill switch")
    with tempfile.TemporaryDirectory(prefix="f87_ct_") as tmp:
        data_dir = Path(tmp) / "data"
        archive_dir = Path(tmp) / "archive"
        data_dir.mkdir()
        archive_dir.mkdir()
        ranking = [dict(HENKEL_89534), dict(AMAZON_KOBLENZ),
                   dict(SIMVIA),
                   {"id": "velha|x:1", "url": "https://v/1",
                    "description": LONG_COMPLETE_DESC, "score": 1.0}]
        _write_json(data_dir / "eligible_jobs.json", ranking)
        _write_json(archive_dir / "eligible_jobs.json",
                    [ranking[3]])  # só a velha é conhecida
        metrics = data_dir / "collection_metrics.jsonl"
        metrics.write_text("", encoding="utf-8")

        # (1) budget 0 (default) = OFF: zero fetch, JSON byte-identical.
        env_backup = os.environ.pop(BUDGET_ENV, None)
        try:
            before = (data_dir / "eligible_jobs.json").read_bytes()
            rec = rd._intake_liveness(data_dir, archive_dir, metrics,
                                      opener=_opener({}, set(), {}))
            check("budget 0 => OFF (regra 9)",
                  rec == {"budget": 0, "status": "off"})
            check("OFF: JSON byte-identical",
                  (data_dir / "eligible_jobs.json").read_bytes() == before)
        finally:
            if env_backup is not None:
                os.environ[BUDGET_ENV] = env_backup

        # (2) sem baseline (archive vazio): nada checado, diff começa depois.
        (archive_dir / "eligible_jobs.json").unlink()
        with _stage_env("10"):
            rec2 = rd._intake_liveness(data_dir, archive_dir, metrics,
                                       opener=_opener({}, set(), {}))
        check("sem snapshot anterior => no_baseline, 0 fetch",
              rec2["status"] == "no_baseline" and rec2["fetched"] == 0)
        # Recria o baseline para os próximos contratos.
        _write_json(archive_dir / "eligible_jobs.json", [ranking[3]])

        # (3) budget recorta: 3 novas, budget 1 => 1 fetch.
        with _stage_env("1"):
            rec3 = rd._intake_liveness(data_dir, archive_dir, metrics,
                                       opener=_opener({}, set(), {}))
        check("budget 1 com 3 novas => fetched 1 (recorte do teto)",
              rec3["new_candidates"] == 3 and rec3["fetched"] == 1)

        # (4) kill switch da F39 vale no intake: dead mas SEM remoção.
        with _stage_env("10"):
            with _stage_dead_off():
                rec4 = rd._intake_liveness(
                    data_dir, archive_dir, metrics,
                    opener=_opener({SIMVIA["url"]: 404}, set(), {}))
        check("kill switch F39: Simvia morta mas NÃO removida do JSON",
              SIMVIA["id"] in set(rec4["dead_ids"])
              and rec4["removed"] == 0
              and SIMVIA["id"] in {
                  j["id"] for j in json.loads(
                      (data_dir / "eligible_jobs.json")
                      .read_text(encoding="utf-8"))})


def test_shared_budget() -> None:
    section("F: poço compartilhado — intake abate do F65 no mesmo run")
    with tempfile.TemporaryDirectory(prefix="f87_budget_") as tmp:
        data_dir = Path(tmp)
        metrics = data_dir / "collection_metrics.jsonl"
        metrics.write_text("", encoding="utf-8")
        # budget_override=None => comportamento F65 exato (lê o knob).
        with _stage_env("7"):
            rec = rd._run_extended_hydration(
                data_dir, metrics, budget_override=None,
                opener=_opener({}, set(), {}))
        check("override None => knob direto (F65 exato)",
              rec["budget"] == 7)
        # budget_override=0 => OFF mesmo com env alta (intake comeu tudo).
        with _stage_env("7"):
            rec2 = rd._run_extended_hydration(
                data_dir, metrics, budget_override=0,
                opener=_opener({}, set(), {}))
        check("override 0 => OFF (poço esgotado pelo intake)",
              rec2["budget"] == 0 and rec2["status"] == "off")
        # override negativo não vira fetch negativo.
        with _stage_env("7"):
            rec3 = rd._run_extended_hydration(
                data_dir, metrics, budget_override=-3,
                opener=_opener({}, set(), {}))
        check("override negativo => clamp 0", rec3["budget"] == 0)


# ---------------------------------------------------------------------------
# G — linha ⚠️ do digest: formato, população, zero-byte sem flag
# ---------------------------------------------------------------------------

def test_digest_lines() -> None:
    section("G: digest — linha ⚠️ das não-avaliáveis")
    cur = [dict(HENKEL_89534), dict(AMAZON_KOBLENZ),
           {"id": "a|b:1", "title": "Ok Completa", "company": "C",
            "score": 5.0, "description": LONG_COMPLETE_DESC}]
    rd._annotate_assessability(cur)
    lines = rdi.assessability_lines(cur)
    check("linha única com contagem no corte",
          len(lines) == 1 and "2 no Top 30" in lines[0])
    check("quebra por motivo (1 curta, 1 vazia)",
          "1 curta, 1 vazia" in lines[0])
    check("exemplos com título curto",
          "Internship Data & Stakeholder Operations" in lines[0]
          and "Logistik Start 2027" in lines[0])
    # Excluídas das superfícies não contam (mesma semântica dos Top 5).
    lines2 = rdi.assessability_lines(
        cur, {AMAZON_KOBLENZ["id"]})
    check("excluded_ids saem da contagem", "1 no Top 30" in lines2[0])
    # Sem flaggada no corte => lista VAZIA (zero bytes — regressão zero).
    clean = [{"id": "a|b:1", "title": "Ok", "company": "C", "score": 9.0,
              "description": LONG_COMPLETE_DESC}]
    check("sem flaggada => [] (nenhum byte no digest)",
          rdi.assessability_lines(clean) == [])
    check("fixtures sem o campo (corpus antigo) => []",
          rdi.assessability_lines(
              [{"id": "x|y:1", "title": "T", "company": "C", "score": 1.0,
                "description": "curta"}]) == [])
    check("top recorta a população (top=1)",
          rdi.assessability_lines(cur, top=1)[0].startswith(
              "⚠️ Desc indisponível: 1 no Top 1"))
    # Integração digest_sections: campo presente => linha entre score e 🆕.
    with tempfile.TemporaryDirectory(prefix="f87_dig_") as tmp:
        cpath = Path(tmp) / "eligible_jobs.json"
        _write_json(cpath, cur)
        out = rdi.digest_sections(cpath, Path(tmp) / "nao-existe.json",
                                  pages_url="https://pages.example")
        na_idx = [i for i, l in enumerate(out) if l.startswith("⚠️ Desc indisponível")]
        check("digest_sections inclui a linha ⚠️", len(na_idx) == 1)
        clean_path = Path(tmp) / "clean.json"
        _write_json(clean_path, clean)
        out2 = rdi.digest_sections(clean_path, Path(tmp) / "nao-existe.json",
                                   pages_url="https://pages.example")
        check("digest sem flaggada = sem a linha (regressão zero)",
              not any(l.startswith("⚠️ Desc indisponível") for l in out2))


# ---------------------------------------------------------------------------
# H — badge ⚠️ no card: pt/en/ausente (byte-safe por campo)
# ---------------------------------------------------------------------------

def test_badge() -> None:
    section("H: card — badge ⚠️ desc indisponível (field-driven)")
    flagged = dict(HENKEL_89534)
    flagged[rd.NOT_ASSESSABLE_FLAG] = "desc_curta"
    base_kwargs = dict(visa=False, salary="", snippet="", apply_href=None,
                       job_href=None, de_level="none", age="1d")
    html_pt = mp._card(1, flagged, lang="pt",
                       na_flag=mp.not_assessable_flag_text(flagged),
                       **base_kwargs)
    check("badge pt: ⚠️ + 'desc indisponível' no card",
          "⚠️" in html_pt and "desc indisponível" in html_pt)
    html_en = mp._card(
        1, flagged, lang="en",
        na_flag=mp.not_assessable_flag_text(flagged, "en"),
        na_flag_pt=mp.not_assessable_flag_text(flagged, "pt"),
        **base_kwargs)
    check("badge EN + attr do toggle com o texto pt do dia",
          "description unavailable" in html_en
          and 'data-i18n-pt="desc indisponível"' in html_en)
    unflagged = {"id": "a|b:1", "title": "T", "company": "C",
                 "description": LONG_COMPLETE_DESC}
    html_no = mp._card(1, unflagged, lang="pt", **base_kwargs)
    check("sem campo => NENHUM byte do badge (A/B de SHA congelado intacto)",
          "desc indisponível" not in html_no
          and "description unavailable" not in html_no)
    check("helper: sem campo => '' (texto vazio)",
          mp.not_assessable_flag_text(unflagged) == "")
    check("I18N paridade pt/en da chave na_flag",
          mp.I18N["na_flag"]["pt"] == mp.NA_FLAG_TEXT
          and bool(mp.I18N["na_flag"]["en"]))
    # Fluxo _cards_section real: a fixture flaggada ganha o badge, a limpa não.
    with tempfile.TemporaryDirectory(prefix="f87_card_") as tmp:
        flagged_full = dict(flagged, url="https://x/1")
        clean_full = dict(unflagged, url="https://x/2",
                          title="Ok Completa")
        html = mp.render_minimal_html(
            [flagged_full, clean_full],
            total_eligible=2, generated_at="2026-10-20 12:00 UTC")
        check("render real: card flaggado com ⚠️, card limpo sem",
              html.count("desc indisponível") == 1
              and html.index("desc indisponível") < html.index("Ok Completa"))


def main() -> int:
    test_detector()
    test_annotation()
    test_fake200()
    test_intake_liveness()
    test_intake_contracts()
    test_shared_budget()
    test_digest_lines()
    test_badge()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print(f"TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
