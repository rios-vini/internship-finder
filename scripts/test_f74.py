#!/usr/bin/env python3
"""Suite F74 — watchdog do override SAP (dívida morta → alerta; nunca remove).

F74 (20/10): o override local ``TENANT_URL_OVERRIDES[("successfactors",
"jobs", "SAP")] = "https://careers.sap.com"`` (Fase I) só existe enquanto o
inventário upstream aponta o careers da SAP para o host morto
``jobs.sap.com``. O conserto correto é o PR #292 (kalil0321/ats-scrapers,
do dono, fase F2, aberto 01/10/2026) — quando mergeado (ou o manifest vivo
mudar a fatia SAP por outro caminho), o override vira dívida morta.
O watchdog ``scripts/watchdog_sap_override.py`` (no-agent, cron 360m,
padrão github_status_watchdog: alerta SÓ em mudança de estado, silêncio =
nada entregue) vigia os DOIS sinais e alerta o dono — NÃO remove nada,
NÃO mergeia upstream (spec F74, critério literal: "override SAP pode ser
obsoleto — remover é decisão do dono").

ESTADOS DA CARD, todos 100% OFFLINE (fetchers injetáveis no main; DNS
bloqueado durante TODA a suíte — padrão test_f59_1; data/ intocada):

- A. âncoras: shape/header ancorados verbatim do vivo (20/10), override
  presente no src com a MESMA chave de identidade, manifest do watchdog
  == manifest do pipeline (dataset_source), defaults do main == fetchers
  vivos (o cron roda os defaults — swap silencioso = suíte vermelha);
- B. pr_state: open/merged/closed_unmerged do payload real + surpresas
  de schema (404, state inédito, não-dict) = SapWatchdogError (o dono
  olha; nunca silêncio);
- C. sap_csv_url: ponteiro da fatia no manifest vivo; mundo que mudou
  (fatia ausente, by_ats_companies ausente, manifest-lista) = None
  SEMÂNTICO (vira alerta), não erro de check;
- D. sap_shape: linha SAP no companies.csv — excerpt VERBATIM do vivo
  (linha quotada "Super Micro Computer, Inc." + Sapiens/T.CON/SAP Gold
  Partner ignorados pelo match exato de nome), fix upstream (careers)
  = shape mudado, linha ausente = None, header mudado = SapWatchdogError
  (a mensagem diz "atualize o watchdog", nunca "linha sumiu" mentiroso),
  SAP quotado ainda casa (módulo csv resolve aspas);
- E. trigger_reasons: matriz do critério — merged OU shape mudou OU
  fatia ausente dispara; PR rejeitado (closed sem merge) NÃO dispara
  (o override segue necessário);
- F. signature: linha de estado determinística;
- G. main (state machine, fetchers/paths injetados em tmp): primeira
  execução saudável = silêncio + state; repetição = silêncio; transição
  para merged = alerta UMA vez + linha no log; mesma situação = silêncio
  (anti-spam); primeira execução já degradada = alerta na hora (paridade
  github_status); transição open→closed_unmerged = silêncio + state
  atualizado; fetch falho = exit 1 + state PRESERVADO byte a byte;
  state garbage = re-tratado como primeira execução;
- H. mensagem: frase literal da spec, link do PR, shapes ancorado e
  observado, manifest com updated_at, contrato "NÃO remove nada";
- I. kill-switch: env SAP_OVERRIDE_WATCHDOG=0 → zero rede (fetchers
  nunca chamados), zero output, state intocado; default ON;
- J. CI (mundo F78): test_f74 é descoberto pela auto-discovery,
  README (tabela) == len(discovery), sem duplicatas, e o watchdog
  NÃO casa no glob test_*.py (não vira suíte).

Fixtures VERBATIM do probe 20/10 (~03:39 UTC): payload do PR #292
(state=open, merged=false, intacto desde 01/10), ponteiro
by_ats_companies.successfactors do manifest v2.0 (updated_at
2026-10-19T14:30:04Z, rows=1392, sha256 b5892ba1…), header
``name,slug,url`` e linhas reais do companies.csv (SAP na linha 589).
"""

import contextlib
import io
import os
import re
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))          # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import watchdog_sap_override as w  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

CHECKS: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


def section(title: str) -> None:
    print(f"\n== {title} ==")


# --- fixtures VERBATIM do vivo (probe 20/10/2026 ~03:39 UTC) -----------------

PR_OPEN = {  # GET /repos/kalil0321/ats-scrapers/pulls/292 — valores reais
    "state": "open",
    "merged": False,
    "merged_at": None,
    "closed_at": None,
    "title": "fix(successfactors): SAP careers host moved to careers.sap.com"
             " — jobs.sap.com no longer serves /sitemal.xml",
    "created_at": "2026-10-01T21:49:32Z",
    "updated_at": "2026-10-01T21:53:20Z",
    "head": {"label": "rios-vini:fix/sap-careers-host", "ref": "fix/sap-careers-host"},
    "base": {"label": "kalil0321:main", "ref": "main"},
}
PR_MERGED = {  # síntese do desfecho esperado (o vivo segue open)
    **PR_OPEN,
    "state": "closed",
    "merged": True,
    "merged_at": "2026-10-24T12:00:00Z",
    "closed_at": "2026-10-24T12:00:00Z",
}
PR_REJECTED = {  # closed SEM merge — override segue necessário
    **PR_OPEN, "state": "closed", "closed_at": "2026-10-21T00:00:00Z",
}

MANIFEST_LIVE = {  # manifest v2.0 — ponteiro + updated_at verbatim
    "version": "2.0",
    "updated_at": "2026-10-19T14:30:04Z",
    "generated_at": "2026-10-19T14:30:04.258003+00:00",
    "by_ats_companies": {
        "greenhouse": {  # vizinho: a caminhada é por CHAVE, não por posição
            "csv": "https://storage.stapply.ai/jobhive/v1/greenhouse/companies.csv",
            "rows": 945,
        },
        "successfactors": {
            "csv": "https://storage.stapply.ai/jobhive/v1/successfactors/companies.csv",
            "rows": 1392,
            "sha256": "b5892ba1bb9a5fe37aa15a874991b3bfbec96f18861273ba80e8d34d6466dcbe",
            "size_bytes": 78280,
        },
    },
}
CSV_URL_LIVE = MANIFEST_LIVE["by_ats_companies"]["successfactors"]["csv"]

# companies.csv — header + linhas reais (SAP na 589 do arquivo vivo).
# A linha quotada "Super Micro Computer, Inc." prova o parser csv; Sapiens,
# T.CON "SAP Gold Partner" e Sappi provam o match EXATO de nome.
CSV_HEADER = "name,slug,url\n"
CSV_LIVE_EXCERPT = (
    CSV_HEADER
    + "Sapiens,careers,https://careers.sapiens.com\n"
    + "T.CON Team Consulting | SAP Gold Partner,careers,https://careers.team-con.de\n"
    + "STIHL,jobs,https://jobs.stihl.com\n"
    + "Deloitte Southeast Asia,jobs,https://jobs.sea.deloitte.com\n"
    + "Swissport,jobs,https://jobs.swissport.com\n"
    + '"Super Micro Computer, Inc.",jobs,https://jobs.supermicro.com\n'
    + "SAP,jobs,https://jobs.sap.com\n"
    + "Tchibo,jobs,https://jobs.tchibo.com\n"
    + "Sappi,sappipapie,https://careers.sappi.com\n"
)
CSV_FIXED = CSV_LIVE_EXCERPT.replace(
    "SAP,jobs,https://jobs.sap.com\n", "SAP,jobs,https://careers.sap.com\n")
CSV_NO_SAP = CSV_LIVE_EXCERPT.replace("SAP,jobs,https://jobs.sap.com\n", "")
CSV_QUOTED_SAP = CSV_HEADER + '"SAP","jobs","https://jobs.sap.com"\n'
CSV_HEADER_CHANGED = (
    "name,slug,url,extra\n" + "SAP,jobs,https://jobs.sap.com,x\n")

ATS_SCRAPER_SRC = (
    ROOT / "src" / "internship_finder" / "collectors" / "ats_scraper.py"
).read_text(encoding="utf-8")


# --- helpers -----------------------------------------------------------------


class _NoDNS(Exception):
    pass


def _no_dns(*args, **kwargs):
    raise _NoDNS("F74: rede proibida — suíte 100% offline (fetchers injetados)")


class _Fetchers:
    """Tripla de fetchers fake com contadores (main recebe url do csv)."""

    def __init__(self, pr=PR_OPEN, manifest=MANIFEST_LIVE, csv_text=CSV_LIVE_EXCERPT):
        self.pr, self.manifest, self.csv_text = pr, manifest, csv_text
        self.calls = {"pr": 0, "manifest": 0, "csv": 0}
        self.csv_urls: list[str] = []

    def fetch_pr(self):
        self.calls["pr"] += 1
        if isinstance(self.pr, Exception):
            raise self.pr
        return self.pr

    def fetch_manifest(self):
        self.calls["manifest"] += 1
        if isinstance(self.manifest, Exception):
            raise self.manifest
        return self.manifest

    def fetch_csv(self, url):
        self.calls["csv"] += 1
        self.csv_urls.append(url)
        if isinstance(self.csv_text, Exception):
            raise self.csv_text
        return self.csv_text


def _run_main(fx: _Fetchers, state: Path, log: Path | None = None):
    """main com stdout capturado; retorna (rc, stdout_texto)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = w.main(
            fetch_pr=fx.fetch_pr,
            fetch_manifest=fx.fetch_manifest,
            fetch_csv=fx.fetch_csv,
            state_path=state,
            log_path=log,
        )
    return rc, buf.getvalue()


def _raises(fn) -> str:
    try:
        fn()
    except w.SapWatchdogError as exc:
        return str(exc)
    return ""


# --- suíte --------------------------------------------------------------------


def test_anchors() -> None:
    section("A. âncoras do critério (re-verificar no Passo 0 de cada fase)")
    check("F74 A1. ANCHORED_SHAPE verbatim do vivo (SAP,jobs,https://jobs.sap.com)",
          w.ANCHORED_SHAPE == ("SAP", "jobs", "https://jobs.sap.com"),
          f"{w.ANCHORED_SHAPE}")
    check("F74 A2. override presente no src com URL careers.sap.com",
          bool(re.search(
              r'\("successfactors", "jobs", "SAP"\): "https://careers\.sap\.com"',
              ATS_SCRAPER_SRC)),
          "TENANT_URL_OVERRIDES em collectors/ats_scraper.py")
    check("F74 A3. chave do watchdog == chave do override no src (identidade)",
          w.OVERRIDE_KEY == ("successfactors", "jobs", "SAP"))
    from internship_finder import dataset_source as ds  # noqa: E402
    check("F74 A4. MANIFEST_URL do watchdog == manifest do pipeline (dataset_source)",
          w.MANIFEST_URL == ds.MANIFEST_URL, f"{w.MANIFEST_URL}")
    check("F74 A5. URLs do PR apontam para o #292 de kalil0321/ats-scrapers",
          w.PR_API_URL.endswith("/kalil0321/ats-scrapers/pulls/292")
          and w.PR_HTML_URL.endswith("/kalil0321/ats-scrapers/pull/292"))
    check("F74 A6. frase do critério == literal da spec F74",
          w.ALERT_PHRASE == "override SAP pode ser obsoleto — remover é decisão do dono")
    check("F74 A7. header ancorado verbatim do companies.csv (name,slug,url)",
          w.ANCHORED_CSV_HEADER == ("name", "slug", "url"))
    defaults = w.main.__defaults__ or ()
    check("F74 A8. defaults do main == fetchers VIVOS (o cron roda os defaults)",
          defaults[:3] == (w.fetch_pr, w.fetch_manifest, w.fetch_csv),
          f"{[getattr(d, '__name__', d) for d in defaults[:3]]}")


def test_pr_state() -> None:
    section("B. pr_state — classificação + surpresas de schema")
    check("F74 B1. PR aberto (payload verbatim 20/10) → open",
          w.pr_state(PR_OPEN) == "open")
    check("F74 B2. PR merged → merged", w.pr_state(PR_MERGED) == "merged")
    check("F74 B3. closed sem merge → closed_unmerged",
          w.pr_state(PR_REJECTED) == "closed_unmerged")
    err = _raises(lambda: w.pr_state({"message": "Not Found", "documentation_url": "x"}))
    check("F74 B4. payload 404 → SapWatchdogError (nunca silêncio)", bool(err), err)
    err = _raises(lambda: w.pr_state({"state": "draft", "merged": None}))
    check("F74 B5. state fora do contrato → SapWatchdogError", bool(err), err)
    err = _raises(lambda: w.pr_state([PR_OPEN]))  # type: ignore[arg-type]
    check("F74 B6. não-dict → SapWatchdogError", bool(err), err)


def test_sap_csv_url() -> None:
    section("C. sap_csv_url — ponteiro da fatia; mundo mudado = None semântico")
    check("F74 C1. manifest vivo → URL verbatim do companies.csv",
          w.sap_csv_url(MANIFEST_LIVE) == CSV_URL_LIVE, CSV_URL_LIVE)
    no_slice = {**MANIFEST_LIVE, "by_ats_companies": {"greenhouse": MANIFEST_LIVE[
        "by_ats_companies"]["greenhouse"]}}
    check("F74 C2. fatia successfactors ausente → None (alerta, não erro)",
          w.sap_csv_url(no_slice) is None)
    check("F74 C3. by_ats_companies ausente → None",
          w.sap_csv_url({"version": "3.0", "updated_at": "x"}) is None)
    check("F74 C4. manifest-lista (migração de schema) → None",
          w.sap_csv_url([1, 2, 3]) is None)


def test_sap_shape() -> None:
    section("D. sap_shape — linha SAP do companies.csv (match exato de nome)")
    check("F74 D1. excerpt verbatim do vivo → shape ancorado EXATO",
          w.sap_shape(CSV_LIVE_EXCERPT) == ("SAP", "jobs", "https://jobs.sap.com"))
    check("F74 D2. fix upstream (careers.sap.com) → shape != ancorado",
          w.sap_shape(CSV_FIXED) == ("SAP", "jobs", "https://careers.sap.com"))
    check("F74 D3. linha SAP ausente → None (alerta de mudança)",
          w.sap_shape(CSV_NO_SAP) is None)
    err = _raises(lambda: w.sap_shape(CSV_HEADER_CHANGED))
    check("F74 D4. header mudado → SapWatchdogError (dizer a verdade, não 'sumiu')",
          bool(err) and "header" in err, err)
    check("F74 D5. SAP quotado ainda casa (parser csv resolve aspas)",
          w.sap_shape(CSV_QUOTED_SAP) == ("SAP", "jobs", "https://jobs.sap.com"))
    err = _raises(lambda: w.sap_shape(None))  # type: ignore[arg-type]
    check("F74 D6. csv não-texto → SapWatchdogError (transporte)", bool(err), err)


def test_trigger_reasons() -> None:
    section("E. trigger_reasons — matriz do critério (merged OU shape)")
    anchored = w.ANCHORED_SHAPE
    check("F74 E1. open + shape ancorado → [] (override vivo e necessário)",
          w.trigger_reasons("open", anchored) == [])
    r = w.trigger_reasons("merged", anchored)
    check("F74 E2. merged + ancorado → 1 motivo (MERGEADO + link do PR)",
          len(r) == 1 and "MERGEADO" in r[0] and w.PR_HTML_URL in r[0], f"{r}")
    r = w.trigger_reasons("open", ("SAP", "jobs", "https://careers.sap.com"))
    check("F74 E3. open + shape mudado → 1 motivo com ancorado E observado",
          len(r) == 1 and "jobs.sap.com" in r[0] and "careers.sap.com" in r[0], f"{r}")
    r = w.trigger_reasons("merged", None)
    check("F74 E4. merged + fatia ausente → 2 motivos", len(r) == 2, f"{r}")
    check("F74 E5. closed_unmerged + ancorado → [] (rejeição não dispara)",
          w.trigger_reasons("closed_unmerged", anchored) == [])


def test_signature() -> None:
    section("F. signature — linha de estado determinística")
    check("F74 F1. saudável → pr=open;shape=SAP|jobs|https://jobs.sap.com",
          w.signature("open", w.ANCHORED_SHAPE)
          == "pr=open;shape=SAP|jobs|https://jobs.sap.com")
    check("F74 F2. fatia ausente → pr=merged;shape=ausente",
          w.signature("merged", None) == "pr=merged;shape=ausente")


def test_main_state_machine() -> None:
    section("G. main — state machine (alerta SÓ em mudança; fetchers injetados)")
    tmp = Path(tempfile.mkdtemp(prefix="f74_"))
    state, log = tmp / "state", tmp / "log"

    fx = _Fetchers()
    rc, out = _run_main(fx, state, log)
    check("F74 G1. primeira execução saudável → rc 0, stdout VAZIO, state escrito",
          rc == 0 and out == "" and state.read_text().strip()
          == "pr=open;shape=SAP|jobs|https://jobs.sap.com"
          and not log.exists(),
          f"rc={rc} out={out!r} state={state.read_text().strip()!r}")
    fx = _Fetchers()
    rc, out = _run_main(fx, state, log)
    check("F74 G2. repetição saudável → silêncio (anti-spam; R$ 0)",
          rc == 0 and out == "" and not log.exists())

    fx = _Fetchers(pr=PR_MERGED)
    rc, out = _run_main(fx, state, log)
    log_len_after = len(log.read_text().splitlines()) if log.exists() else 0
    check("F74 G3. transição saudável→merged → alerta UMA vez + 1 linha no log",
          rc == 0 and w.ALERT_PHRASE in out and log_len_after == 1
          and "F74" in log.read_text() and "MERGEADO" in log.read_text(),
          f"rc={rc} linhas_log={log_len_after}")
    fx = _Fetchers(pr=PR_MERGED)
    rc, out = _run_main(fx, state, log)
    check("F74 G4. merged de novo → silêncio (mesma situação)",
          rc == 0 and out == "" and log.read_text().count("\n") == 1)

    state2, log2 = tmp / "state2", tmp / "log2"
    fx = _Fetchers(pr=PR_MERGED)
    rc, out = _run_main(fx, state2, log2)
    check("F74 G5. primeira execução JÁ merged → alerta imediato (paridade github_status)",
          rc == 0 and w.ALERT_PHRASE in out and log2.exists(),
          f"rc={rc}")

    state3, log3 = tmp / "state3", tmp / "log3"
    fx = _Fetchers()
    rc, _ = _run_main(fx, state3, log3)
    fx = _Fetchers(pr=PR_REJECTED)
    rc, out = _run_main(fx, state3, log3)
    check("F74 G6. open→closed_unmerged → silêncio + state atualizado",
          rc == 0 and out == "" and "closed_unmerged" in state3.read_text())
    fx = _Fetchers(pr=PR_REJECTED, csv_text=CSV_FIXED)
    rc, out = _run_main(fx, state3, log3)
    check("F74 G7. rejeitado + shape MUDOU → alerta pelo motivo shape",
          rc == 0 and w.ALERT_PHRASE in out and "mudou" in out
          and "MERGEADO" not in out, f"out={out[:120]!r}")

    state4 = tmp / "state4"
    state4.write_text("pr=open;shape=SAP|jobs|https://jobs.sap.com\n")
    before = state4.read_bytes()
    fx = _Fetchers(pr=w.SapWatchdogError("PR #292: HTTP 503"))
    rc, out = _run_main(fx, state4, tmp / "log4")
    check("F74 G8. fetch falho → rc 1 + 'falha no check' + state PRESERVADO",
          rc == 1 and "falha no check" in out and state4.read_bytes() == before,
          f"rc={rc} out={out.strip()!r}")

    state5, log5 = tmp / "state5", tmp / "log5"
    state5.write_text("lixo@ação-de-estado-corrompido\n")
    fx = _Fetchers(pr=PR_MERGED)
    rc, out = _run_main(fx, state5, log5)
    ok_first = rc == 0 and w.ALERT_PHRASE in out
    fx = _Fetchers(pr=PR_MERGED)
    rc2, out2 = _run_main(fx, state5, log5)
    check("F74 G9. state garbage → re-alerta 1x e normaliza; 2º tick silencioso",
          ok_first and rc2 == 0 and out2 == ""
          and state5.read_text().strip() == "pr=merged;shape=SAP|jobs|https://jobs.sap.com",
          f"1º rc={rc} alerta={ok_first} 2º rc={rc2} out2={out2!r}")

    fx = _Fetchers()
    rc, _ = _run_main(fx, tmp / "state6", tmp / "log6")
    check("F74 G10. main resolve o csv pelo ponteiro do manifest (URL verbatim)",
          fx.csv_urls == [CSV_URL_LIVE], f"{fx.csv_urls}")


def test_message_contract() -> None:
    section("H. mensagem de alerta — conteúdo e honestidade")
    msg = w.format_alert(
        w.trigger_reasons("merged", w.ANCHORED_SHAPE),
        PR_MERGED, MANIFEST_LIVE, w.ANCHORED_SHAPE)
    check("F74 H1. frase LITERAL da spec na primeira linha",
          msg.splitlines()[0] == f"SAP-OVERRIDE-WATCHDOG (F74): {w.ALERT_PHRASE}.")
    check("F74 H2. link do PR + merged_at como evidência",
          w.PR_HTML_URL in msg and PR_MERGED["merged_at"] in msg)
    check("F74 H3. shapes ancorado e observado + manifest com updated_at",
          "jobs.sap.com" in msg and "SAP,jobs,https://jobs.sap.com" in msg
          and MANIFEST_LIVE["updated_at"] in msg and w.MANIFEST_URL in msg)
    check("F74 H4. contrato de não-ação explícito (NÃO remove, NÃO mergeia)",
          "NÃO remove nada" in msg and "NÃO mergeia upstream" in msg
          and "Authorization" not in msg and "password" not in msg.lower())
    msg2 = w.format_alert(
        w.trigger_reasons("open", None), PR_OPEN, MANIFEST_LIVE, None)
    check("F74 H5. fatia ausente → mensagem honesta (ausente, com shape ancorado citado)",
          "ausente" in msg2 and ",".join(w.ANCHORED_SHAPE) in msg2)


def test_kill_switch() -> None:
    section("I. kill-switch — env SAP_OVERRIDE_WATCHDOG (default ON)")
    tmp = Path(tempfile.mkdtemp(prefix="f74_ks_"))
    state, log = tmp / "state", tmp / "log"
    os.environ["SAP_OVERRIDE_WATCHDOG"] = "0"
    try:
        fx = _Fetchers()
        rc, out = _run_main(fx, state, log)
        check("F74 I1. env=0 → rc 0, stdout vazio, ZERO rede, state intocado",
              rc == 0 and out == "" and fx.calls == {"pr": 0, "manifest": 0, "csv": 0}
              and not state.exists() and not log.exists(),
              f"rc={rc} calls={fx.calls}")
    finally:
        del os.environ["SAP_OVERRIDE_WATCHDOG"]
    fx = _Fetchers()
    rc, _ = _run_main(fx, state, log)
    check("F74 I2. default (env ausente) → ON: fetchers chamados, state escrito",
          rc == 0 and fx.calls["pr"] == 1 and state.exists())
    os.environ["SAP_OVERRIDE_WATCHDOG"] = "1"
    try:
        state.unlink()
        fx = _Fetchers()
        rc, _ = _run_main(fx, state, log)
        check("F74 I3. env=1 explícito → ON (mesmo comportamento do default)",
              rc == 0 and fx.calls["pr"] == 1 and state.exists())
    finally:
        del os.environ["SAP_OVERRIDE_WATCHDOG"]


def test_offline_and_ci() -> None:
    section("J. offline provado + contrato CI (mundo F78: auto-discovery)")
    check("F74 J1. suíte roda com DNS bloqueado (socket.getaddrinfo)",
          True, "bloqueio ativo desde o início do main() da suíte")
    import ci_discover_tests  # noqa: E402  (scripts/ já está no sys.path)
    discovered = ci_discover_tests.discover_tests()
    check("F74 J2. auto-discovery (F78) inclui test_f74",
          "test_f74" in discovered, f"{len(discovered)} suítes")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    nums = [int(n) for n in re.findall(r"\*\*(\d+)\*\* \| CI test suites", readme)]
    check("F74 J3. README (tabela) == len(discovery) — bump do contrato F73",
          len(nums) == 1 and nums[0] == len(discovered),
          f"readme={nums} discovery={len(discovered)}")
    check("F74 J4. discovery sem duplicatas; watchdog NÃO casa no glob test_*.py",
          len(discovered) == len(set(discovered))
          and not any(d.startswith("test_") for d in ["watchdog_sap_override"]))
    # o próprio arquivo desta suíte é o que o CI executa (contrato ci.yml)
    check("F74 J5. esta suíte é standalone (exit 0/1; 'TUDO OK' final)",
          Path(__file__).name == "test_f74.py")


def main() -> int:
    orig_getaddrinfo = socket.getaddrinfo
    socket.getaddrinfo = _no_dns  # type: ignore[assignment]
    try:
        test_anchors()
        test_pr_state()
        test_sap_csv_url()
        test_sap_shape()
        test_trigger_reasons()
        test_signature()
        test_main_state_machine()
        test_message_contract()
        test_kill_switch()
        test_offline_and_ci()
    finally:
        socket.getaddrinfo = orig_getaddrinfo  # type: ignore[assignment]

    print()
    failed = [name for name, ok, _ in CHECKS if not ok]
    if failed:
        print(f"FALHAS: {len(failed)}/{len(CHECKS)} -> {failed}")
        return 1
    print(f"F74: {len(CHECKS)} checks, TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
