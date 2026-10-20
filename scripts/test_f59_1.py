#!/usr/bin/env python3
''''true; V="$(dirname "$0")/../.venv/bin/python"; [ -x "$V" ] || V=python3; exec "$V" -- "$0" "$@" # '''
"""Suite F59.1 — vendor self-removível do parser BambooHR (PR #300).

Poliglota de 1 linha (bash: ``exec`` re-invoca sob python3; python: string
no-op) — ``bash scripts/test_f59_1.py`` e ``python scripts/test_f59_1.py``
rodam a mesma suíte; o CI usa ``python scripts/$t.py`` (contrato ci.yml).

F59.1 (19/10): o widget BambooHR (embed2.php) serve JSON PURO desde ~08/10
(probe F59/F59.1: HTTP 200, 623 bytes; as MESMAS 2 vagas Remote dentro de
``departments[].positions[]``); o parser HTML do pacote upstream 0.3.0
(marcador ``bhrPositionID_``) acha 0 vagas = ``empty`` silencioso. Por
decisão do dono ("aplicar a solução no meu projeto... ao invés de deixar
defasado esperando semanas"), o parser do PR #300 (kalil0321/ats-scrapers,
fork rios-vini/ats-scrapers head 85c270a) é VENDADO em
``upstream_patches/bamboohr.py`` — com AUTO-DETECÇÃO que torna o patch
self-removível (convergência sem divergência com o upstream).

ESTADOS DA CARD (4 + extras), todos 100% OFFLINE:

(a) pacote SEM fix + fixture JSON → o patch parseia as 2 vagas, campos
    id/name/location/department/url IGUAIS ao caminho HTML (fixture HTML
    gêmeo parseado pelo parser INSTALADO);
(b) SIMULACRO de pacote COM fix → o bypass é no-op: a factory devolve a
    PRÓPRIA classe sondada (o pacote é quem manda), nunca o vendored;
(c) fixture HTML → caminho byte-idêntico nos DOIS estados (patch ativo e
    bypass) — a branch JSON não perturba tenants HTML;
(d) ASSERT DE REMOÇÃO: se o pacote INSTALADO passar NATIVAMENTE no
    fixture (upstream mergeu + release + upgrade), a suíte FALHA
    amigavelmente apontando o checklist de remoção — a remoção da camada
    deixa de ser opcional. HOJE (0.3.0) o canário confirma o estado
    "sem fix" e a suíte segue.

Extras: kill switch env INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR
(default ON; 0 = histórico), passthrough de ATS != bamboohr, ponto de uso
no coletador (hidratação segue get_scraper direto — detail API intocada
pelo PR #300), prova de offline (socket bloqueado), paridade verbatim do
parser vendored (success=false / positions ilegíveis / blank state /
dedup / URL derivada) e ci.yml (união RELATIVA por presença).

ZERO REDE: o fixture é a resposta VERBATIM de bcg.bamboohr.com capturada
no probe 19/10 (623 bytes, md5 ef2200a8b60e145fdf23f0a66103ce3f —
constante FIXTURE_JSON_BCG); TODO fetch é o stub _FixtureFetcher (a
suíte bloqueia resolução de DNS e prova que nada escapa).
"""

import json
import os
import re
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ats_scrapers.exceptions import ScraperError  # noqa: E402

from internship_finder.upstream_patches import bamboohr as up  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COLLECTOR_SRC = (
    ROOT / "src" / "internship_finder" / "collectors" / "ats_scraper.py"
).read_text(encoding="utf-8")
HYDRATION_SRC = (ROOT / "src" / "internship_finder" / "hydration.py").read_text(
    encoding="utf-8"
)
REGISTRY_SRC = (ROOT / "src" / "internship_finder" / "registry.py").read_text(
    encoding="utf-8"
)
HEALTH_SRC = (ROOT / "src" / "internship_finder" / "health.py").read_text(
    encoding="utf-8"
)
VENDORED_SRC = (
    ROOT / "src" / "internship_finder" / "upstream_patches" / "bamboohr.py"
).read_text(encoding="utf-8")

CHECKS: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures — o gêmeo HTML das MESMAS 2 vagas do fixture JSON (estrutura do
# widget documentada no upstream; parseado pelo parser INSTALADO = o
# comportamento de produção pré-08/10, o contrato de saída do PR #300).
# ---------------------------------------------------------------------------
HTML_TWIN = """<li id="bhrDepartmentID_19228" class="BambooHR-ATS-Department-Item">
  <div id="department_19228" class="BambooHR-ATS-Department-Header">
    Architecture & Service Excellence
  </div>
  <ul class="BambooHR-ATS-Jobs-List">
    <li id="bhrPositionID_81" class="BambooHR-ATS-Jobs-Item">
      <a href="//bcg.bamboohr.com/careers/81">Atlassian Platform & ITSM Engineer</a>
      <span class="BambooHR-ATS-Location">Remote</span>
    </li>
  </ul>
</li>
<li id="bhrDepartmentID_18727" class="BambooHR-ATS-Department-Item">
  <div id="department_18727" class="BambooHR-ATS-Department-Header">
    EIDS
  </div>
  <ul class="BambooHR-ATS-Jobs-List">
    <li id="bhrPositionID_80" class="BambooHR-ATS-Jobs-Item">
      <a href="//bcg.bamboohr.com/careers/80">Release Train Engineer (RTE) - DHMS</a>
      <span class="BambooHR-ATS-Location">Remote</span>
    </li>
  </ul>
</li>"""

# Evidência F59/F59.1 — as 2 vagas Remote reais (id, título, local, depto, URL).
EXPECTED = [
    ("81", "Atlassian Platform & ITSM Engineer", "Remote",
     "Architecture & Service Excellence", "https://bcg.bamboohr.com/careers/81"),
    ("80", "Release Train Engineer (RTE) - DHMS", "Remote",
     "EIDS", "https://bcg.bamboohr.com/careers/80"),
]

WIDGET_URL = "https://bcg.bamboohr.com/jobs/embed2.php"


def _stubbed(cls: type, body: str):
    """Instancia ``cls`` com o fetcher stubado (offline) — mesmo gancho do
    auto-detect (``_probe_cls``), o afetch REAL roda por cima do stub."""
    return up._probe_cls(cls, body)("bcg", timeout=2.0, include_descriptions=False)


def _rows(scraper) -> list[dict]:
    """fetch() real → model_dump SEM ``fetched_at`` (carimbo de relógio é o
    único campo não-determinístico entre duas execuções do MESMO parser;
    os bytes de identidade/parse são comparados por inteiro)."""
    return [j.model_dump(exclude={"fetched_at"}) for j in scraper.fetch()]


# ---------------------------------------------------------------------------
# T1 — canário de remoção (estado (d) da card)
# ---------------------------------------------------------------------------
def t1_removal_canary() -> None:
    section("T1: (d) canário de remoção — pacote com fix = suíte FALHA")
    if up.upstream_has_json_fix():
        check(
            "(d) pacote INSTALADO parseia o fixture BCG NATIVAMENTE — "
            "REMOÇÃO DA CAMADA VENDORED EXIGIDA (falha amigável, by design)",
            False,
            "upstream tem o fix: (1) apagar upstream_patches/bamboohr.py e "
            "__init__.py; (2) collectors/ats_scraper.py: get_patched_scraper "
            "-> get_scraper (import incluído); (3) converter esta suíte em "
            "assert DIRETO do pacote (canário (d) deixa de existir); "
            "(4) atualizar comentários F59/F59.1 em registry.py/health.py; "
            "(5) mover a âncora _AB_BASELINE_SHA do test_f53. Checklist "
            "completo no topo de upstream_patches/bamboohr.py; PR #300.",
        )
    else:
        check(
            "(d) pacote instalado AINDA sem o fix — camada vendored "
            "necessária; suíte segue (estado atual: parser HTML 0.3.0)",
            True,
        )


# ---------------------------------------------------------------------------
# T2 — fixture VERBATIM (contrato do auto-detect)
# ---------------------------------------------------------------------------
def t2_fixture_lock() -> None:
    section("T2: fixture verbatim — 623 bytes, as 2 vagas da evidência F59")
    raw = up.FIXTURE_JSON_BCG
    check("fixture tem exatamente 623 bytes (probe 19/10)", len(raw.encode()) == 623,
          f"{len(raw.encode())} bytes")
    payload = json.loads(raw)
    check("fixture é JSON válido com success=true", payload.get("success") is True)
    positions = [
        (str(d.get("label")), p)
        for d in payload.get("departments", [])
        for p in d.get("positions", [])
    ]
    check("fixture carrega exatamente 2 positions", len(positions) == 2,
          f"{len(positions)}")
    got = sorted(
        (str(p["id"]), p["name"], p.get("location"), dept,
         p["url"].replace("\\/", "/"))
        for dept, p in positions
    )
    check("fixture = evidência F59 campo a campo (ids 81/80, Remote, URLs)",
          got == sorted(EXPECTED), f"got={got}")


# ---------------------------------------------------------------------------
# T3 — auto-detect COMPORTAMENTAL no estado atual (pacote sem fix)
# ---------------------------------------------------------------------------
def t3_probe_behavior() -> None:
    section("T3: auto-detect comportamental — afetch do pacote vs fixture")
    installed = up._installed_cls()
    check("classe sondada vem do PACOTE (ats_scrapers.*), via registro público",
          installed.__module__.startswith("ats_scrapers"),
          installed.__module__ + "." + installed.__name__)
    probe = _stubbed(installed, up.FIXTURE_JSON_BCG)
    jobs = probe.fetch()
    check("pacote 0.3.0: afetch REAL roda no fixture e acha 0 vagas "
          "(comportamental, não estrutural)", jobs == [])
    calls = getattr(probe, "_last_probe_fetcher").calls
    check("probe buscou a URL do widget (caminho de produção exercitado)",
          calls == [WIDGET_URL], f"calls={calls}")
    check("upstream_has_json_fix() = False no pacote sem fix",
          up.upstream_has_json_fix() is False)
    check("PatchedBambooHRScraper SUBCLASSE a classe do pacote instalado "
          "(herda HTML/detail/get_description; só o afetch muda)",
          issubclass(up.PatchedBambooHRScraper, installed))


# ---------------------------------------------------------------------------
# T4 — estado (a): pacote sem fix → patch parseia as 2 vagas == caminho HTML
# ---------------------------------------------------------------------------
def t4_patch_parses_fixture() -> None:
    section("T4: (a) patch parseia o fixture JSON — campos iguais ao HTML")
    rows_json = _rows(_stubbed(up.PatchedBambooHRScraper, up.FIXTURE_JSON_BCG))
    check("(a) patch parseia as 2 vagas do fixture", len(rows_json) == 2,
          f"{len(rows_json)} vagas")
    got = sorted(
        (r["ats_id"], r["title"], r.get("location"), r.get("department"),
         str(r["url"]))
        for r in rows_json
    )
    check("(a) campos id/name/location/department/url = evidência F59",
          got == sorted(EXPECTED), f"got={got}")
    check("(a) company/slug e ats_type = bamboohr (identidade do tenant)",
          all(r["company"] == "bcg" and r["ats_type"] == "bamboohr"
              for r in rows_json))
    # O CONTRATO do PR #300: MESMA saída do caminho HTML — o parser
    # INSTALADO (0.3.0, comportamento de produção pré-08/10) sobre o
    # gêmeo HTML tem que devolver exatamente as mesmas rows.
    rows_html = _rows(_stubbed(up._installed_cls(), HTML_TWIN))
    check("(a) caminho HTML (parser INSTALADO, fixture gêmeo) também acha "
          "as 2 vagas", len(rows_html) == 2, f"{len(rows_html)} vagas")
    check("(a) JSON (patch) == HTML (instalado) — model_dump sem fetched_at "
          "byte a byte", rows_json == rows_html)


# ---------------------------------------------------------------------------
# T5 — estado (b): simulacro de pacote COM fix → bypass é no-op
# ---------------------------------------------------------------------------
def t5_simulacrum_bypass() -> None:
    section("T5: (b) simulacro COM fix — o pacote é quem manda")
    installed = up._installed_cls()

    class _FixedUpstream(installed):
        """Simulacro do futuro: o 'pacote instalado' COM o fix do PR #300
        (afetch com a branch JSON + _parse_widget_json, mesma lógica que
        o vendored — classe DISTINTA para provar quem manda)."""

        afetch = up.PatchedBambooHRScraper.afetch
        _parse_widget_json = up.PatchedBambooHRScraper._parse_widget_json

    check("(b) probe detecta o fix no simulacro (True)",
          up.upstream_has_json_fix(_FixedUpstream) is True)
    scr = up.get_patched_scraper(
        "bamboohr", "bcg", probe_cls=_FixedUpstream,
        timeout=2.0, include_descriptions=False,
    )
    check("(b) bypass: a factory devolve a PRÓPRIA classe sondada "
          "(pacote manda)", type(scr) is _FixedUpstream, type(scr).__name__)
    check("(b) bypass: NÃO é instância do patch vendored",
          not isinstance(scr, up.PatchedBambooHRScraper))
    check("(b) bypass: continua sendo BambooHR do pacote (subclasse real)",
          isinstance(scr, installed))
    rows = _rows(_stubbed(_FixedUpstream, up.FIXTURE_JSON_BCG))
    check("(b) o simulacro parseia o fixture SOZINHO (bypass funcional: o "
          "comportamento vem do pacote, não do vendored)", len(rows) == 2)

# ---------------------------------------------------------------------------
# T6 — estado (c): fixture HTML → caminho byte-idêntico nos DOIS estados
# ---------------------------------------------------------------------------
def t6_html_identical() -> None:
    section("T6: (c) HTML byte-idêntico nos 2 estados (branch JSON inerte)")
    rows_patched = _rows(_stubbed(up.PatchedBambooHRScraper, HTML_TWIN))
    rows_installed = _rows(_stubbed(up._installed_cls(), HTML_TWIN))
    check("(c) HTML: patch ativo == bypass (instalado), model_dump sem "
          "fetched_at byte a byte", rows_patched == rows_installed)
    check("(c) HTML: as 2 vagas em ambos os estados",
          len(rows_patched) == 2 and len(rows_installed) == 2)
    # Guarda HTML do afetch vendored (herdada, verbatim do PR): marcador
    # bhrPositionID_ presente sem parse → erro alto, NÃO empty silencioso.
    bad_html = (
        '<li id="bhrDepartmentID_1" class="BambooHR-ATS-Department-Item">'
        '<div id="department_1" class="BambooHR-ATS-Department-Header">X'
        '</div><ul class="BambooHR-ATS-Jobs-List">'
        '<li id="bhrPositionID_99" class="BambooHR-ATS-Jobs-Item">'
        "sem link nenhum aqui</li></ul></li>"
    )
    raised = None
    try:
        _rows(_stubbed(up.PatchedBambooHRScraper, bad_html))
    except Exception as exc:  # noqa: BLE001 - a guarda DEVE levantar
        raised = exc
    check("(c) guarda HTML intacta no afetch vendored (marcador sem parse "
          "→ ScraperError, não empty silencioso)",
          isinstance(raised, ScraperError))


# ---------------------------------------------------------------------------
# T7 — kill switch (default ON; 0 = comportamento histórico)
# ---------------------------------------------------------------------------
def t7_kill_switch() -> None:
    section("T7: kill switch INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR")
    old = os.environ.get(up.PATCH_ENV)
    try:
        def _factory_with(value: str | None):
            if value is None:
                os.environ.pop(up.PATCH_ENV, None)
            else:
                os.environ[up.PATCH_ENV] = value
            return up.get_patched_scraper(
                "bamboohr", "bcg", timeout=2.0, include_descriptions=False
            )

        check("default (env ausente): patch ATIVO (PatchedBambooHRScraper)",
              isinstance(_factory_with(None), up.PatchedBambooHRScraper))
        check("=0: comportamento histórico (classe do pacote, mesmo sem fix)",
              type(_factory_with("0")) is up._installed_cls())
        check("=false: idem (falsy set)", type(_factory_with("false")) is up._installed_cls())
        check("=off: idem", type(_factory_with("off")) is up._installed_cls())
        check("=1: patch ATIVO explícito",
              isinstance(_factory_with("1"), up.PatchedBambooHRScraper))
    finally:
        if old is None:
            os.environ.pop(up.PATCH_ENV, None)
        else:
            os.environ[up.PATCH_ENV] = old
    check("nome da flag = INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR",
          up.PATCH_ENV == "INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR")


# ---------------------------------------------------------------------------
# T8 — passthrough: ATS != bamboohr segue get_scraper puro (inércia)
# ---------------------------------------------------------------------------
def t8_passthrough() -> None:
    section("T8: passthrough — nenhum outro ATS é tocado pela camada")
    gh = up.get_patched_scraper(
        "greenhouse", "acme", timeout=2.0, include_descriptions=False
    )
    check("greenhouse: classe do pacote ats_scrapers (não o vendored)",
          type(gh).__module__.startswith("ats_scrapers")
          and not isinstance(gh, up.PatchedBambooHRScraper),
          type(gh).__module__ + "." + type(gh).__name__)


# ---------------------------------------------------------------------------
# T9 — ponto de uso e documentação (contratos de fonte)
# ---------------------------------------------------------------------------
def t9_point_of_use() -> None:
    section("T9: ponto de uso (coletador) + docs registry/health")
    check("fetch_worker usa o factory (nenhum get_scraper direto no "
          "coletador)", "get_patched_scraper(" in COLLECTOR_SRC
          and "get_scraper(" not in COLLECTOR_SRC)
    check("hidratação segue get_scraper DIRETO (detail API — camada "
          "intocada pelo PR #300)",
          "from ats_scrapers.scrapers import get_scraper" in HYDRATION_SRC)
    check("registry.py (entry BCG) documenta a camada vendored + kill switch",
          "upstream_patches/bamboohr.py" in REGISTRY_SRC
          and "INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR" in REGISTRY_SRC)
    check("health.py documenta: zero_return cessa no 1º cron pós-merge "
          "deste repo", "upstream_patches/bamboohr.py" in HEALTH_SRC
          and "1o cron pos-merge" in HEALTH_SRC)
    check("camada vendored sem marcadores de conflito",
          "<<<<<<<" not in VENDORED_SRC)
    check("camada vendored carrega o checklist de remoção + link do PR #300",
          "CHECKLIST DE REMOÇÃO" in VENDORED_SRC and "PR #300" in VENDORED_SRC)


# ---------------------------------------------------------------------------
# T10 — offline com DNS bloqueado (nenhuma rede na suíte)
# ---------------------------------------------------------------------------
def t10_offline() -> None:
    section("T10: prova de offline — DNS bloqueado, tudo funciona")

    def _no_dns(*args, **kwargs):  # noqa: ANN001, ANN002
        raise AssertionError("rede aberta na suíte F59.1 (esperada offline)")

    # Bloquear socket.socket derrubaria também o socketpair do event loop
    # do asyncio (IPC local legítima). O bloqueio honesto é o DNS: nenhum
    # fetch HTTP sai sem getaddrinfo — o stub é a única fonte de corpo.
    orig = socket.getaddrinfo
    socket.getaddrinfo = _no_dns  # type: ignore[assignment]
    try:
        has_fix = up.upstream_has_json_fix()
        rows = _rows(_stubbed(up.PatchedBambooHRScraper, up.FIXTURE_JSON_BCG))
    finally:
        socket.getaddrinfo = orig  # type: ignore[assignment]
    check("probe + parse funcionam com DNS bloqueado (100% offline)",
          has_fix is False and len(rows) == 2)


# ---------------------------------------------------------------------------
# T11 — paridade verbatim do parser vendored (guardas do PR #300)
# ---------------------------------------------------------------------------
def t11_parser_parity() -> None:
    section("T11: paridade do parser vendored (verbatim PR #300)")

    def _afetch_rows(body: str) -> list[dict]:
        return _rows(_stubbed(up.PatchedBambooHRScraper, body))

    raised = None
    try:
        _afetch_rows(json.dumps({"success": False, "departments": []}))
    except Exception as exc:  # noqa: BLE001
        raised = exc
    check("success=false → ScraperError (falha explícita não se disfarça "
          "de vazio)", isinstance(raised, ScraperError)
          and "success=false" in str(raised))

    raised = None
    try:
        _afetch_rows(json.dumps({"success": True, "departments": [
            {"label": "X", "positions": [{"id": 7}]}]}))
    except Exception as exc:  # noqa: BLE001
        raised = exc
    check("positions listadas e nenhuma parseável → ScraperError (espelho "
          "da guarda HTML)", isinstance(raised, ScraperError))

    check("blank state (departments=[]) → [] genuíno (não é erro)",
          _afetch_rows(json.dumps({"success": True, "departments": []})) == [])

    rows = _afetch_rows(json.dumps({"success": True, "departments": [
        {"label": "A", "positions": [{"id": "5", "name": "Job",
                                      "location": "Remote"}]},
        {"label": "B", "positions": [{"id": 5, "name": "Job",
                                      "location": "Remote"}]}]}))
    check("dedup cross-department (mesmo id) → 1 row, fica a 1ª ocorrência",
          len(rows) == 1 and rows[0]["department"] == "A")

    rows = _afetch_rows(json.dumps({"success": True, "departments": [
        {"label": "D", "positions": [{"id": 42, "name": "T",
                                      "url": "/careers/42",
                                      "location": "Remote"}]}]}))
    check("URL relativa → share URL derivada do id (slug+id do tenant)",
          len(rows) == 1 and str(rows[0]["url"])
          == "https://bcg.bamboohr.com/careers/42")

    rows = _afetch_rows(json.dumps({"success": True, "departments": [
        {"label": "D", "positions": [{"id": 43, "name": "T",
                                      "location": "   "}]}]}))
    check("location em branco → None (não vira string vazia)",
          len(rows) == 1 and rows[0]["location"] is None)

    check("JSON malformado que começa com '{' → decode falha → cai no "
          "parser HTML → [] SEM exceção (guarda de decode)",
          _afetch_rows('{"broken') == [])


# ---------------------------------------------------------------------------
# T12 — ci.yml: união RELATIVA (presença no array)
# ---------------------------------------------------------------------------
def t12_ci_union() -> None:
    section("T12: CI — test_f59_1 na suíte descoberta (relativa, F78)")
    import ci_discover_tests
    arr = ci_discover_tests.discover_tests()
    check("test_f59_1 presente na suíte descoberta do CI (por presença)",
          "test_f59_1" in arr, f"{len(arr)} suítes")
    check("suíte descoberta viva e relativa (>= 80 suítes; contagens nunca hardcoded)",
          len(arr) >= 80, f"{len(arr)}")


def main() -> int:
    t1_removal_canary()
    t2_fixture_lock()
    t3_probe_behavior()
    t4_patch_parses_fixture()
    t5_simulacrum_bypass()
    t6_html_identical()
    t7_kill_switch()
    t8_passthrough()
    t9_point_of_use()
    t10_offline()
    t11_parser_parity()
    t12_ci_union()
    fails = [c for c in CHECKS if not c[1]]
    print(f"\nF59.1: {len(CHECKS) - len(fails)} OK, {len(fails)} FAIL")
    for name, _, detail in fails:
        print(f"  FAIL: {name} {detail}")
    print("TUDO OK" if not fails else "HÁ FALHAS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
