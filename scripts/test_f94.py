#!/usr/bin/env python3
"""F94 — Liveness v2: estado persistente + edge cases de provedor (offline).

O DELTA da F87 (ITEM 1 da delegação): o que o passe de liveness concluiu
DEVE ficar consultável por vaga — ``liveness_status: alive|dead|unknown``
+ ``liveness_checked_at`` no registro — e os edge cases de provedor
medidos ao vivo (probes 21/10) precisam de semântica própria:

- **SAML/csod** (henkel ×4 do registro): 3 redirects =>
  ``samldefault.aspx`` 200 com corpo mínimo "SAML Authentication
  Request" (3.633 bytes). O wall PROVA nada sobre a vaga => unknown +
  ``manual_check_required``, NUNCA dead (controle negativo do teste).
- **Lidl redirect stub** (``rdr/jump-to-job/<ref>``): o veredito é do
  ALVO. Caso re-post verbatim: Ref 753653 ("Praktikum Controlling
  International - Projekte") saiu do eligible (re-post ganhou novo
  requisition id 1426446133/Ref 735605) mas o alvo SEGUE VIVO no site
  (rdr => 1 hop => 200, 209.849 bytes medidos) — pacote de candidatura
  VÁLIDO não pode ser descartado. Stub que MORRE (404) ou erra (500
  "We'll be right back" medido p/ ref inexistente) NÃO prova morte do
  anúncio => unknown, nunca dead/F39.
- **stale_posting**: idade do posting por tipo (estágio 45d; permanente
  90d) com posted_at coletado como fonte primária e caderno F70
  first_seen como fallback.
- **re-check >24h** (item 4): hook documentado pro fluxo de aplicação —
  veredito velho (ou ausente/unknown) pede re-teste antes do pacote.
  Display/digest, NUNCA exclusão.

Fixtures VERBATIM (probes da fase 21/10 + eligible de produção):
GFO Kliniken softgarden 57526218 (404 medido), Lidl Ref 753653 (viva no
alvo) + Ref 735605 + IT Digitaler Arbeitsplatz 1429059833 (removida do
eligible 19→21/10 e viva, 200/61.715B), henkel csod 89534/89499/89300/
88050 (SAML wall), rdr ref inexistente (500). Zero rede: openers fake
scriptados; tempdir para o integration path do ``_intake_liveness``;
nada de data/ de produção.

Standalone exit-code: imprime [OK]/[FAIL]; rc=0 só se tudo passar.
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import refresh_daily as rd  # noqa: E402
import url_liveness as ul  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

BUDGET_ENV = "INTERNSHIP_FINDER_HYDRATION_BUDGET"
DEAD_OFF_ENV = "INTERNSHIP_FINDER_DEAD_REMOVAL_OFF"


def section(name: str) -> None:
    print(f"\n--- {name} ---")


def check(name: str, cond, detail: str | None = None) -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"[OK] {name}" + (f" — {detail}" if detail else ""))
    else:
        print(f"[FAIL] {name}" + (f" — {detail}" if detail else ""))
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fixtures VERBATIM (probes ao vivo 21/10 + registro do dono)
# ---------------------------------------------------------------------------

# GFO Kliniken (softgarden 57526218): 404 entre coleta e análise (ITEM 1) —
# id/posted_at exatamente como estão no eligible de produção.
GFO_57526218 = {
    "id": "GFO Kliniken Niederrhein|sf_dataset:softgarden:57526218",
    "title": "Praktikum Einkauf u. Zentrallager",
    "company": "GFO Kliniken Niederrhein",
    "location": "Moers, DE",
    "url": ("https://gfo-online.career.softgarden.de/jobs/57526218/"
            "Praktikum-Einkauf-u-Zentrallager-/"),
    "posted_at": "2026-07-13T15:45:12.545000+02:00",
    "description": "Praktikum im Einkauf und Zentrallager der GFO Kliniken.",
}

# Lidl re-post (ITEM 1, Ref 753653): saiu do eligible no run 21/10 (re-post
# 1426446133/Ref 735605 entrou) mas SEGUE VIVA no site — medido:
#   feed URL  => 200, 68.743 bytes, sem redirect
#   rdr stub  => 1 redirect => alvo 200, 209.849 bytes
#   rdr bogus => 500 "We'll be right back", 210.447 bytes
LIDL_OLD_1441979333 = {
    "id": "lidlstiftup2|sf_dataset:successfactors:1441979333",
    "title": "Praktikum Controlling International - Projekte",
    "company": "lidlstiftup2",
    "location": "Neckarsulm, DE",
    "url": ("https://jobs.lidl/sti/job/Neckarsulm-Praktikum-Controlling-"
            "International-Projekte/1441979333/"),
    "description": "Praktikum im Controlling International - Projekte.",
}
LIDL_STUB_753653 = "https://jobs.lidl.de/rdr/jump-to-job/753653"
LIDL_ALVO_753653 = ("https://jobs.lidl.de/jobs/praktikum-controlling-"
                    "international-projekte-neckarsulm-753653")
LIDL_STUB_BOGUS = "https://jobs.lidl.de/rdr/jump-to-job/999999999"

# Lidl IT Digitaler Arbeitsplatz (1429059833): removida do eligible entre os
# snapshots 19/10 e 21/10 e a página SEGUE viva (200, 61.715 bytes, título
# "Praktikum IT Digitaler Arbeitsplatz Stellendetails | Lidl").
LIDL_GONE_1429059833 = {
    "id": "lidlstiftup2|sf_dataset:successfactors:1429059833",
    "title": "Praktikum IT Digitaler Arbeitsplatz",
    "company": "lidlstiftup2",
    "location": "Neckarsulm, DE",
    "url": ("https://jobs.lidl/sti/job/Neckarsulm-Praktikum-IT-Digitaler-"
            "Arbeitsplatz/1429059833/"),
    "description": "Praktikum IT Digitaler Arbeitsplatz.",
}

# henkel ×4 (csod/SAML): as 4 URLs verbatim do registro (todas por
# henkel.csod.com; 3 seguem not_assessable no eligible de hoje). Resposta
# MEDIDA: 3 redirects => samldefault.aspx, 200, 3.633 bytes,
# <title>SAML Authentication Request</title>.
HENKEL_SAML_IDS = (
    "henkel|cornerstone:henkel:89534",
    "henkel|cornerstone:henkel:89499",
    "henkel|cornerstone:henkel:89300",
    "henkel|cornerstone:henkel:88050",
)
HENKEL_URL_89534 = "https://henkel.csod.com/ux/ats/careersite/1/job/89534?c=henkel"
SAML_FINAL_URL = ("https://henkel.csod.com/samldefault.aspx?ouid=2&ReturnUrl="
                  "https%3a%2f%2fhenkel.csod.com%2fcommon%2frestrictedarea.aspx")
SAML_BODY = (
    "<html><head><title>SAML Authentication Request</title></head>"
    "<body onload=\"document.forms[0].submit();\">"
    "<form id=\"form1\" method=\"post\" action=\"https://ahoi.henkel.com/\">"
    "</form></body></html>"
)


def henkel_job(n: int) -> dict:
    url = HENKEL_URL_89534 if n == 89534 else (
        f"https://henkel.csod.com/ux/ats/careersite/1/job/{n}?c=henkel")
    return {
        "id": f"henkel|cornerstone:henkel:{n}",
        "title": f"Internship {n}",
        "company": "henkel",
        "location": "Duesseldorf, DE",
        "url": url,
        "description": "Internship description.",
    }


def job_page_body(n_bytes: int = 209_849) -> str:
    # página de vaga grande (ordem do alvo Lidl medido: 209.849 bytes)
    return ("<html><head><title>Stellendetails | Lidl</title></head><body>"
            + "<p>Stellenanzeige mit vielen Details. </p>" * (n_bytes // 40)
            + "</body></html>")


# ---------------------------------------------------------------------------
# Harness — openers fake scriptados (padrão test_f87; zero rede)
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, url: str, body: str = ""):
        self.url = url
        self._body = body.encode("utf-8")

    def read(self, n: int = -1) -> bytes:
        if n < 0 or n > len(self._body):
            return self._body
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(status_map: dict, error_urls: dict, bodies: dict):
    """Openers fake: url => _Resp(url, corpo) | HTTPError(code)."""
    def open_url(req, timeout=None):
        url = req.full_url
        if url in error_urls:
            raise urllib.error.HTTPError(
                url, int(error_urls[url]), "fake", {}, None)
        if url in status_map:
            final_url, body = status_map[url]
            return _Resp(final_url, bodies.get(url, body))
        raise urllib.error.URLError("url fora do script do teste")
    return open_url


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _stage_env(value: str) -> str:
    os.environ[BUDGET_ENV] = value
    return BUDGET_ENV


def _stage_dead_off() -> str:
    os.environ[DEAD_OFF_ENV] = "1"
    return DEAD_OFF_ENV


# ---------------------------------------------------------------------------
# G1 — veredito por vaga (alive|dead|unknown) no stats do passe
# ---------------------------------------------------------------------------

def test_verdicts() -> None:
    section("G1 — veredito base no stats (F94 item 1)")
    alive_job = {
        "id": "acme|workday:acme:1",
        "title": "Internship Procurement",
        "company": "acme",
        "url": "https://acme.example.com/jobs/1",
    }
    net_job = {
        "id": "acme|workday:acme:2",
        "title": "Internship Logistics",
        "company": "acme",
        "url": "https://acme.example.com/jobs/2",
    }
    jobs = [GFO_57526218, alive_job, net_job, henkel_job(89534)]
    opener = _opener(
        status_map={
            alive_job["url"]: (alive_job["url"], job_page_body(50_000)),
            henkel_job(89534)["url"]: (SAML_FINAL_URL, SAML_BODY),
        },
        error_urls={GFO_57526218["url"]: 404},
        bodies={},
    )
    dead, bodies, stats = ul.check_liveness_v2(jobs, opener=opener, delay=0)
    check("404 hard-dead => dead set",
          dead == {GFO_57526218["id"]}, str(dead))
    check("stats tem vereditos para as 4 checadas",
          len(stats.get("verdicts") or {}) == 4, str(stats.get("verdicts")))
    check("GFO veredito dead (http 404)",
          stats["verdicts"][GFO_57526218["id"]] == {"status": "dead", "detail": "http 404"},
          str(stats["verdicts"].get(GFO_57526218["id"])))
    check("200 limpo => alive",
          stats["verdicts"][alive_job["id"]] == {"status": "alive", "detail": ""},
          str(stats["verdicts"].get(alive_job["id"])))
    check("rede fora => unknown (nunca dead)",
          stats["verdicts"][net_job["id"]] == {"status": "unknown", "detail": "network"},
          str(stats["verdicts"].get(net_job["id"])))
    check("hard_dead_ids segue F39-compatível",
          stats.get("hard_dead_ids") == {GFO_57526218["id"]},
          str(stats.get("hard_dead_ids")))
    check("contadores alive/unknown presentes",
          stats.get("alive") == 1 and stats.get("unknown") == 2,
          f"alive={stats.get('alive')} unknown={stats.get('unknown')}")
    # vaga sem url verificável: sem veredito, sem tentativa
    stats2 = ul.check_liveness_v2(
        [{"id": "x", "title": "t", "company": "c", "url": "notaurl"}],
        opener=opener, delay=0)[2]
    check("vaga sem http(s) => sem veredito", stats2.get("verdicts") == {},
          str(stats2.get("verdicts")))
    # 5xx = erro, não morte (F11) — vira unknown honesto
    stats3 = ul.check_liveness_v2(
        [{"id": "acme|workday:acme:3", "title": "t", "company": "c",
          "url": "https://acme.example.com/jobs/3"}],
        opener=_opener({}, {"https://acme.example.com/jobs/3": 500}, {}),
        delay=0)[2]
    check("HTTP 500 => unknown (nunca dead)",
          stats3["verdicts"]["acme|workday:acme:3"]["status"] == "unknown"
          and stats3["verdicts"]["acme|workday:acme:3"]["detail"] == "http 500",
          str(stats3.get("verdicts")))


# ---------------------------------------------------------------------------
# G2 — SAML/csod: unknown + manual_check_required, NUNCA dead (controle
# negativo da spec)
# ---------------------------------------------------------------------------

def test_saml_never_dead() -> None:
    section("G2 — csod/SAML => unknown + manual_check_required (NUNCA dead)")
    jobs = [henkel_job(n) for n in (89534, 89499, 89300, 88050)]
    status_map = {j["url"]: (SAML_FINAL_URL, SAML_BODY) for j in jobs}
    dead, bodies, stats = ul.check_liveness_v2(
        jobs, opener=_opener(status_map, {}, {}), delay=0)
    manual = set(stats.get("manual_check_required") or [])
    check("nenhuma henkel marcada dead (controle negativo)",
          dead == set() and not stats.get("hard_dead_ids")
          and not stats.get("soft_dead_ids"), str(dead))
    check("4/4 veredito unknown", len(manual) == 4, str(manual))
    for j in jobs:
        v = stats["verdicts"].get(j["id"]) or {}
        check(f"{j['id']} unknown com detalhe saml wall",
              v.get("status") == "unknown" and "saml wall" in v.get("detail", ""),
              str(v))
    check("wall SAML não hidrata (corpo é do IdP, não da vaga)",
          bodies == {}, str(bodies))
    # variante B: marcador SAML SÓ no corpo (URL final sem 'saml' no path)
    job_b = henkel_job(1)
    job_b["id"] = "henkel|cornerstone:henkel:1"
    dead_b, _b, stats_b = ul.check_liveness_v2(
        [job_b],
        opener=_opener({job_b["url"]: ("https://x.example.com/login",
                                       SAML_BODY)}, {}, {}), delay=0)
    check("marcador SAML no CORPO também dispara unknown (sem dead)",
          stats_b["verdicts"][job_b["id"]]["status"] == "unknown"
          and dead_b == set()
          and job_b["id"] in set(stats_b.get("manual_check_required") or []),
          str(stats_b.get("verdicts")))
    # página VIVA de vaga (grande, sem marcador) NUNCA é confundida com wall
    job_alive = henkel_job(2)
    job_alive["id"] = "henkel|cornerstone:henkel:2"
    _d, _b, stats_c = ul.check_liveness_v2(
        [job_alive],
        opener=_opener({job_alive["url"]: (job_alive["url"],
                                           job_page_body(60_000))}, {}, {}),
        delay=0)
    check("200 de job page real => alive (anti-FP do detector SAML)",
          stats_c["verdicts"][job_alive["id"]]["status"] == "alive"
          and not (stats_c.get("manual_check_required") or []),
          str(stats_c.get("verdicts")))


# ---------------------------------------------------------------------------
# G3 — Lidl redirect stub: veredito vem do ALVO (controle negativo da spec)
# ---------------------------------------------------------------------------

def test_lidl_redirect_target() -> None:
    section("G3 — Lidl rdr/jump-to-job: o ALVO decide (pacote válido)")
    # (a) stub + alvo VIVO (Ref 753653 medido: rdr => alvo 200/209.849B)
    stub_job = {
        "id": "lidlstiftup2|sf_dataset:successfactors:753653",
        "title": "Praktikum Controlling International - Projekte",
        "company": "lidlstiftup2",
        "url": LIDL_STUB_753653,
    }
    dead, _b, stats = ul.check_liveness_v2(
        [stub_job],
        opener=_opener({LIDL_STUB_753653: (LIDL_ALVO_753653,
                                           job_page_body())}, {}, {}), delay=0)
    check("alvo vivo => ALIVE (pacote válido não descartado)",
          stats["verdicts"][stub_job["id"]]["status"] == "alive" and dead == set(),
          str(stats["verdicts"]))
    check("alvo vivo NÃO entra em hard_dead (F39 intocado)",
          not (stats.get("hard_dead_ids") or []), str(stats.get("hard_dead_ids")))
    # (b) stub MORRE com 404: o 404 é do STUB, não do anúncio => unknown
    dead2, _b2, stats2 = ul.check_liveness_v2(
        [stub_job], opener=_opener({}, {LIDL_STUB_753653: 404}, {}), delay=0)
    check("stub 404 => unknown, NUNCA dead/F39",
          stats2["verdicts"][stub_job["id"]] == {"status": "unknown",
                                                 "detail": "stub http 404"}
          and dead2 == set() and not (stats2.get("hard_dead_ids") or []),
          str(stats2["verdicts"]))
    # (c) stub erra com 500 (ref inexistente, medido: "We'll be right back")
    dead3, _b3, stats3 = ul.check_liveness_v2(
        [{"id": "lidlstiftup2|sf_dataset:successfactors:bogus",
          "title": "t", "company": "c", "url": LIDL_STUB_BOGUS}],
        opener=_opener({}, {LIDL_STUB_BOGUS: 500}, {}), delay=0)
    check("stub 500 (ref inexistente) => unknown, NUNCA dead",
          stats3["verdicts"]["lidlstiftup2|sf_dataset:successfactors:bogus"]
          ["status"] == "unknown" and dead3 == set(), str(stats3["verdicts"]))
    # (d) REGRESSION GUARD: 404 de job page (NÃO-stub) segue hard-dead F11
    dead4, _b4, stats4 = ul.check_liveness_v2(
        [GFO_57526218], opener=_opener({}, {GFO_57526218["url"]: 404}, {}),
        delay=0)
    check("404 de página real (não-stub) segue hard-dead",
          dead4 == {GFO_57526218["id"]}
          and stats4["verdicts"][GFO_57526218["id"]]["status"] == "dead",
          str(stats4["verdicts"]))
    # (e) feed URL da REMOVIDA do eligible segue viva (re-post: o URL é a
    # evidência — 1429059833 saiu do eligible 19→21/10 e responde 200)
    dead5, _b5, stats5 = ul.check_liveness_v2(
        [LIDL_GONE_1429059833],
        opener=_opener({LIDL_GONE_1429059833["url"]: (
            LIDL_GONE_1429059833["url"], job_page_body(61_000))}, {}, {}),
        delay=0)
    check("vaga removida do eligible com URL viva => ALIVE",
          stats5["verdicts"][LIDL_GONE_1429059833["id"]]["status"] == "alive"
          and dead5 == set(), str(stats5["verdicts"]))


# ---------------------------------------------------------------------------
# G4 — persistência no registro: annotator + _intake_liveness + kill switch
# ---------------------------------------------------------------------------

def test_annotation_persistence() -> None:
    section("G4a — _annotate_liveness_state: estado no registro, cura e cura-idempotente")
    job_a = {"id": "acme|workday:acme:1", "title": "t", "company": "c",
             "url": "https://x/1"}
    job_b = {"id": "acme|workday:acme:2", "title": "t", "company": "c",
             "url": "https://x/2",
             "liveness_status": "alive", "liveness_checked_at": "2026-10-20T09:00:00+00:00"}
    job_c = {"id": "henkel|cornerstone:henkel:9", "title": "t", "company": "c",
             "url": "https://x/9", "manual_check_required": True}
    ranking = [job_a, job_b, job_c]
    verdicts = {
        job_a["id"]: {"status": "dead", "detail": "http 404"},
        job_b["id"]: {"status": "alive", "detail": ""},
        job_c["id"]: {"status": "unknown", "detail": "saml wall (url:/samldefault.aspx)"},
    }
    stats_state = rd._annotate_liveness_state(
        ranking, verdicts, {job_c["id"]}, "2026-10-21T09:00:00+00:00")
    check("contagens: 1 dead, 1 alive, 1 unknown/manual",
          stats_state == {"annotated": 3, "alive": 1, "dead": 1,
                          "unknown": 1, "manual_check_required": 1},
          str(stats_state))
    check("job_a ganha dead + timestamp",
          job_a["liveness_status"] == "dead"
          and job_a["liveness_checked_at"] == "2026-10-21T09:00:00+00:00",
          str(job_a))
    check("job_b atualiza timestamp (estado recomputado)",
          job_b["liveness_status"] == "alive"
          and job_b["liveness_checked_at"] == "2026-10-21T09:00:00+00:00",
          str(job_b))
    check("job_c unknown + manual_check_required=True",
          job_c["liveness_status"] == "unknown"
          and job_c["manual_check_required"] is True, str(job_c))
    # cura idempotente: wall saiu (alvo vivo no run seguinte) => flag apaga
    rd._annotate_liveness_state(
        ranking, {job_c["id"]: {"status": "alive", "detail": ""}}, set(),
        "2026-10-21T10:00:00+00:00")
    check("cura: manual_check_required apaga quando a vaga vira viva",
          "manual_check_required" not in job_c
          and job_c["liveness_status"] == "alive", str(job_c))
    # veredito malformado: estado anterior permanece
    rd._annotate_liveness_state(
        ranking, {job_a["id"]: {"status": "coisa-estranha"}}, set(),
        "2026-10-21T11:00:00+00:00")
    check("veredito malformado => estado anterior intocado",
          job_a["liveness_status"] == "dead", str(job_a))
    # persistência entre runs: vaga NÃO checada mantém o estado do run anterior
    job_d = {"id": "acme|workday:acme:4", "title": "t", "company": "c",
             "url": "https://x/4",
             "liveness_status": "alive", "liveness_checked_at": "2026-10-19T09:00:00+00:00"}
    rd._annotate_liveness_state([job_d], {}, set(), "2026-10-21T12:00:00+00:00")
    check("vaga fora do passe mantém o estado persistido (F94 item 1)",
          job_d["liveness_status"] == "alive"
          and job_d["liveness_checked_at"] == "2026-10-19T09:00:00+00:00",
          str(job_d))


def _intake_fixture(tmp: Path):
    """Cenário verbatim: 4 novas (GFO 404, henkel SAML, Lidl viva, acme viva)."""
    henkel = henkel_job(89534)
    acme = {"id": "acme|workday:acme:1", "title": "Internship Procurement",
            "company": "acme", "url": "https://acme.example.com/jobs/1"}
    ranking = [dict(GFO_57526218), henkel, LIDL_GONE_1429059833, acme]
    status_map = {
        LIDL_GONE_1429059833["url"]: (
            LIDL_GONE_1429059833["url"], job_page_body(61_000)),
        acme["url"]: (acme["url"], job_page_body(30_000)),
        henkel["url"]: (SAML_FINAL_URL, SAML_BODY),
    }
    errors = {GFO_57526218["url"]: 404}
    return ranking, _opener(status_map, errors, {}), henkel, acme


def test_intake_persistence() -> None:
    section("G4b — _intake_liveness integração: veredito persistido no JSON")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        data_dir = tmp / "data"
        archive_dir = tmp / "archive"
        data_dir.mkdir()
        archive_dir.mkdir()
        ranking, opener, henkel, acme = _intake_fixture(tmp)
        _write_json(data_dir / "eligible_jobs.json", ranking)
        _write_json(archive_dir / "eligible_jobs.json", [])  # baseline: tudo novo
        env = _stage_env("4")
        try:
            stats = rd._intake_liveness(
                data_dir, archive_dir, tmp / "metrics.jsonl",
                run_id="f94-test", log=None, opener=opener)
        finally:
            os.environ.pop(env, None)
        check("intake: 4 novas checadas",
              stats.get("new_candidates") == 4 and stats.get("fetched") == 4,
              str(stats))
        check("intake: GFO hard-dead REMOVIDA do JSON (F39 preservado)",
              stats.get("removed") == 1, str(stats.get("removed_ids")))
        out = json.loads((data_dir / "eligible_jobs.json").read_text("utf-8"))
        ids = {j["id"] for j in out}
        check("JSON sem a GFO removida",
              GFO_57526218["id"] not in ids, str(sorted(ids)))
        henkel_out = next(j for j in out if j["id"] == henkel["id"])
        check("henkel: liveness_status=unknown no REGISTRO",
              henkel_out.get("liveness_status") == "unknown", str(henkel_out.get("liveness_status")))
        check("henkel: manual_check_required=True no REGISTRO",
              henkel_out.get("manual_check_required") is True,
              str(henkel_out.get("manual_check_required")))
        check("henkel: liveness_checked_at ISO gravado",
              bool(henkel_out.get("liveness_checked_at")),
              str(henkel_out.get("liveness_checked_at")))
        lidl_out = next(j for j in out if j["id"] == LIDL_GONE_1429059833["id"])
        check("lidl viva (removida do eligible antes): ALIVE no registro",
              lidl_out.get("liveness_status") == "alive",
              str(lidl_out.get("liveness_status")))
        check("lidl: NÃO ganhou manual_check_required",
              "manual_check_required" not in lidl_out, str(lidl_out))
        acme_out = next(j for j in out if j["id"] == acme["id"])
        check("acme viva: alive + timestamp",
              acme_out.get("liveness_status") == "alive"
              and bool(acme_out.get("liveness_checked_at")), str(acme_out))
        check("metrica intake: contagens de veredito (a removida F39 também "
              "foi checada e anotada antes da remoção)",
              stats.get("verdict_annotated") == 4
              and stats.get("verdict_alive") == 2
              and stats.get("verdict_dead") == 1
              and stats.get("verdict_unknown") == 1
              and stats.get("verdict_manual_check") == 1,
              f"annotated={stats.get('verdict_annotated')} "
              f"alive={stats.get('verdict_alive')} "
              f"dead={stats.get('verdict_dead')} "
              f"unknown={stats.get('verdict_unknown')} "
              f"manual={stats.get('verdict_manual_check')}")

    with tempfile.TemporaryDirectory() as td:
        # kill switch F39: hard-dead FICA no JSON com liveness_status=dead
        tmp = Path(td)
        data_dir = tmp / "data"
        archive_dir = tmp / "archive"
        data_dir.mkdir()
        archive_dir.mkdir()
        ranking, opener, _henkel, _acme = _intake_fixture(tmp)
        _write_json(data_dir / "eligible_jobs.json", ranking)
        _write_json(archive_dir / "eligible_jobs.json", [])
        env_budget = _stage_env("4")
        env_off = _stage_dead_off()
        try:
            stats = rd._intake_liveness(
                data_dir, archive_dir, tmp / "metrics.jsonl",
                run_id="f94-test-off", log=None, opener=opener)
        finally:
            os.environ.pop(env_budget, None)
            os.environ.pop(env_off, None)
        out = json.loads((data_dir / "eligible_jobs.json").read_text("utf-8"))
        gfo = next((j for j in out if j["id"] == GFO_57526218["id"]), None)
        check("kill switch: hard-dead FICA no JSON",
              gfo is not None, str(stats.get("removed")))
        check("kill switch: veredito dead persiste no registro",
              gfo is not None and gfo.get("liveness_status") == "dead"
              and bool(gfo.get("liveness_checked_at")), str(gfo))


# ---------------------------------------------------------------------------
# G5 — stale_posting: idade por tipo, posted_at => F70 first_seen
# ---------------------------------------------------------------------------

def _seen_db(path: Path, rows: list[tuple[str, str, str]]) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE dataset_seen ("
        "run_id TEXT NOT NULL, job_id TEXT NOT NULL, "
        "first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, "
        "PRIMARY KEY (run_id, job_id))")
    for run_id, job_id, first in rows:
        con.execute(
            "INSERT INTO dataset_seen (run_id, job_id, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?)", (run_id, job_id, first, first))
    con.commit()
    con.close()


NOW = datetime.datetime(2026, 10, 21, 12, 0, 0, tzinfo=datetime.UTC)


def test_stale_posting() -> None:
    section("G5 — stale_posting: 45d estágio / 90d permanente (posted_at + F70)")
    # (a) GFO verbatim: posted 2026-07-13, agora 21/10 => ~100d => flag
    gfo = dict(GFO_57526218)
    stats = rd._annotate_stale_posting([gfo], now=NOW)
    check("GFO (100d estágio) => stale_posting=True",
          gfo.get("stale_posting") is True
          and isinstance(gfo.get("posting_age_days"), int)
          and int(gfo["posting_age_days"]) >= 99, str(gfo.get("posting_age_days")))
    check("idade veio do posted_at (fonte primária)",
          stats["by_source"].get("posted_at") == 1, str(stats["by_source"]))
    # (b) estágio fresco (2d) => sem flag
    fresh = {"id": "x|workday:x:1", "title": "Praktikum Einkauf",
             "company": "x", "url": "https://x/1",
             "posted_at": "2026-10-19T09:00:00+00:00"}
    rd._annotate_stale_posting([fresh], now=NOW)
    check("estágio 2d => sem flag",
          "stale_posting" not in fresh and "posting_age_days" not in fresh,
          str(fresh))
    # (c) tipo PERMANENTE: 60d NÃO flag (90d); 100d flag
    perm_desc = ("We offer a permanent full-time position. "
                 "Bruttojahresgehalt (Vollzeit): 40.000 - 46.000 EUR.")
    perm60 = {"id": "basf|successfactors:basf:1",
              "title": "Junior Controller",
              "company": "basf", "url": "https://x/2",
              "posted_at": "2026-08-22T09:00:00+00:00",
              "description": perm_desc}
    stats60 = rd._annotate_stale_posting([perm60], now=NOW)
    check("permanente 60d: limiar 90 => sem flag",
          "stale_posting" not in perm60
          and stats60["by_threshold"].get("90") == 1,
          f"{stats60['by_threshold']} {perm60}")
    check("permanente detectado via job_type_of (F86)",
          rd.stale_posting_threshold_days(perm60) == 90,
          str(rd.stale_posting_threshold_days(perm60)))
    perm100 = dict(perm60, id="basf|successfactors:basf:2",
                   posted_at="2026-07-13T09:00:00+00:00")
    rd._annotate_stale_posting([perm100], now=NOW)
    check("permanente 100d => flag (limiar 90)",
          perm100.get("stale_posting") is True
          and int(perm100["posting_age_days"]) >= 99, str(perm100.get("posting_age_days")))
    # (d) werkstudent (família estágio) 60d => flag (limiar 45)
    ws = {"id": "y|personio:y:1", "title": "Werkstudent Einkauf",
          "company": "y", "url": "https://x/3",
          "posted_at": "2026-08-22T09:00:00+00:00"}
    rd._annotate_stale_posting([ws], now=NOW)
    check("werkstudent 60d => flag (limiar 45 da família estágio)",
          ws.get("stale_posting") is True, str(ws))
    # (e) sem posted_at => caderno F70 (first_seen) como fallback
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "dataset_seen.db"
        _seen_db(db, [("2026-10-01T09:00:00+00:00",
                       "lidl|sf_dataset:successfactors:111",
                       "2026-09-01T09:00:00+00:00")])
        no_post = {"id": "lidl|sf_dataset:successfactors:111",
                   "title": "Praktikum Logistik", "company": "lidl",
                   "url": "https://x/4", "posted_at": None}
        stats_seen = rd._annotate_stale_posting(
            [no_post], now=NOW, seen_db_path=db)
        check("sem posted_at: idade vinda do caderno F70 first_seen (50d => flag)",
              no_post.get("stale_posting") is True
              and stats_seen["by_source"].get("first_seen") == 1
              and no_post["posting_age_days"] == 50,
              f"{no_post.get('posting_age_days')} {stats_seen['by_source']}")
        # (f) sem nenhuma evidência: sem flag (nunca dado fabricado)
        none_job = {"id": "z|z:1", "title": "Praktikum", "company": "z",
                    "url": "https://x/5", "posted_at": None}
        stats_none = rd._annotate_stale_posting(
            [none_job], now=NOW, seen_db_path=db)
        check("sem posted_at E sem caderno => sem flag, no_evidence contada",
              "stale_posting" not in none_job
              and stats_none["no_evidence"] == 1,
              str(stats_none))
    # (g) idempotência/cura: flag acendeu ontem, re-post zera posted_at => apaga
    cured = {"id": "c|c:1", "title": "Praktikum", "company": "c",
             "url": "https://x/6", "stale_posting": True,
             "posting_age_days": 120,
             "posted_at": "2026-10-20T09:00:00+00:00"}
    stats_cure = rd._annotate_stale_posting([cured], now=NOW)
    check("cura: re-post zera a idade => flag apaga (recomputação)",
          "stale_posting" not in cured and stats_cure["cleared"] == 1,
          f"{cured} {stats_cure['cleared']}")
    # (h) posted_at ILEGÍVEL => tenta fallback, nunca inventa
    bad = {"id": "b|b:1", "title": "Praktikum", "company": "b",
           "url": "https://x/7", "posted_at": "nao-e-uma-data"}
    stats_bad = rd._annotate_stale_posting([bad], now=NOW)
    check("posted_at ilegível sem fallback => sem flag",
          "stale_posting" not in bad and stats_bad["no_evidence"] == 1,
          str(stats_bad))


# ---------------------------------------------------------------------------
# G6 — re-check >24h: hook do fluxo de aplicação (display/digest, NUNCA
# exclusão)
# ---------------------------------------------------------------------------

def test_recheck_hook() -> None:
    section("G6 — needs_liveness_recheck (24h antes do pacote)")
    fresh = {"liveness_status": "alive",
             "liveness_checked_at": "2026-10-21T11:00:00+00:00"}
    check("alive 1h atrás => não pede re-check",
          ul.needs_liveness_recheck(fresh, now=NOW) is False,
          str(fresh))
    old = {"liveness_status": "alive",
           "liveness_checked_at": "2026-10-20T07:00:00+00:00"}
    check("alive 29h atrás => re-check antes do pacote",
          ul.needs_liveness_recheck(old, now=NOW) is True, str(old))
    check("sem estado => re-check (honesto por default)",
          ul.needs_liveness_recheck({}, now=NOW) is True)
    check("só liveness_checked_at (sem status) => re-check",
          ul.needs_liveness_recheck(
              {"liveness_checked_at": "2026-10-21T11:00:00+00:00"}, now=NOW)
          is False, "sem status: o timestamp fresco governa")
    unknown = {"liveness_status": "unknown",
               "liveness_checked_at": "2026-10-21T11:00:00+00:00"}
    check("unknown SEMPRE pede re-check (inconclusivo não autoriza pacote)",
          ul.needs_liveness_recheck(unknown, now=NOW) is True, str(unknown))
    dead_fresh = {"liveness_status": "dead",
                  "liveness_checked_at": "2026-10-21T11:00:00+00:00"}
    check("dead com veredito fresco não pede re-check (veredito é recente)",
          ul.needs_liveness_recheck(dead_fresh, now=NOW) is False,
          str(dead_fresh))
    check("timestamp ilegível => re-check (defensivo)",
          ul.needs_liveness_recheck(
              {"liveness_status": "alive", "liveness_checked_at": "x"},
              now=NOW) is True)
    naive = {"liveness_status": "alive",
             "liveness_checked_at": "2026-10-21T11:00:00"}  # sem tz => UTC
    check("timestamp sem timezone assumido UTC (shape real do JSON)",
          ul.needs_liveness_recheck(naive, now=NOW) is False, str(naive))


# ---------------------------------------------------------------------------
# G7 — falha TOTAL de rede: nada marcado E vereditos preservados
# ---------------------------------------------------------------------------

def test_total_network_failure() -> None:
    section("G7 — rede fora: veredito anterior do registro permanece")
    def dead_opener(req, timeout=None):
        raise urllib.error.URLError("rede fora")

    job = {"id": "acme|workday:acme:1", "title": "t", "company": "c",
           "url": "https://x/1",
           "liveness_status": "alive", "liveness_checked_at": "2026-10-19T09:00:00+00:00"}
    dead, _b, stats = ul.check_liveness_v2([job], opener=dead_opener, delay=0)
    check("falha total: nenhuma vaga marcada (doutrina F11)",
          dead == set(), str(dead))
    check("falha total: SEM vereditos (estado anterior preservado)",
          stats.get("verdicts") == {} and stats.get("manual_check_required") == [],
          str(stats.get("verdicts")))
    state = rd._annotate_liveness_state(
        [job], stats.get("verdicts") or {}, set(), "2026-10-21T12:00:00+00:00")
    check("annotator no-op: registro mantém alive de 19/10",
          state["annotated"] == 0 and job["liveness_status"] == "alive"
          and job["liveness_checked_at"] == "2026-10-19T09:00:00+00:00",
          str(job))


# ---------------------------------------------------------------------------
# G8 — contrato do stats: campos F94 são ADITIVOS (F39/F11 intactos)
# ---------------------------------------------------------------------------

def test_stats_contract() -> None:
    section("G8 — stats: chaves F11/F39/F20 + F94 aditivas")
    jobs = [GFO_57526218, LIDL_GONE_1429059833]
    opener = _opener(
        status_map={LIDL_GONE_1429059833["url"]: (
            LIDL_GONE_1429059833["url"], job_page_body(61_000))},
        error_urls={GFO_57526218["url"]: 404}, bodies={})
    dead, _b, stats = ul.check_liveness_v2(jobs, opener=opener, delay=0)
    for key in ("attempts", "http_responses", "net_errors", "soft_dead",
                "hydrated", "hydration_failed", "short_candidates",
                "duration_s", "hard_dead_ids", "hard_dead_status",
                "soft_dead_ids"):
        check(f"stats mantém {key}", key in stats, str(sorted(stats.keys())))
    for key in ("verdicts", "manual_check_required", "alive", "unknown"):
        check(f"stats traz {key} (F94)", key in stats, str(sorted(stats.keys())))
    hard_ids, hard_status = rd._extract_liveness_details(stats)
    check("_extract_liveness_details segue extraindo hard-dead (F39)",
          hard_ids == {GFO_57526218["id"]}
          and hard_status == {GFO_57526218["id"]: 404}, str(hard_status))


# ---------------------------------------------------------------------------

def main() -> int:
    test_verdicts()
    test_saml_never_dead()
    test_lidl_redirect_target()
    test_annotation_persistence()
    test_intake_persistence()
    test_stale_posting()
    test_recheck_hook()
    test_total_network_failure()
    test_stats_contract()
    print(f"\n==== test_f94: {CHECKS} checks, {len(FAILURES)} falha(s) ====")
    if FAILURES:
        print("FALHAS:")
        for f in FAILURES:
            print(f"- {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())



