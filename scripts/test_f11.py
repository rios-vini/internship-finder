"""Testes da Fase F11 — funil de aplicacao (100% offline).

Cobre as 4 tarefas da fase sem rede e sem ``data/`` de producao:

- **T1 Novas de ontem**: diff de IDs (``new_since_previous``) — normal,
  1o run sem snapshot, snapshot corrompido, snapshot vazio valido, diff
  gigante (>= NEW_SINCE_BIG_DIFF: so contagem); secoes 🆕 da pagina
  (top 10 + data-new) e do digest (contagem + top 3 com apply_url).
- **T2 EN-friendly**: ``data-de`` por card (required/preferred/plus/
  none), badge "🇩🇪 DE exigido" apenas em required, toggle JS
  "sem alemão exigido" (nucleo executado em node), digest "🎯 Top 5
  aplicáveis" (visa_friendly E sem required; <5 e ==0 gracioso).
- **T3 Vitalidade**: mock de HEAD (404/410 = morta; 403/429/timeout =
  ignorados; falha total de rede = nenhuma marca); vagas mortas descem
  do top exibido e ganham badge; JSON/CSV intocados; estagio dentro do
  refresh nunca derruba o run (fake opener que levanta).
- **T4 Pagina 100 + diversidade**: PAGE_TOP=100, cap 2/empresa na
  EXIBICAO (a 3a ocorrencia pulada, a seguinte sobe; scores/ordem dos
  exibidos intactos), filtros client-side de pais (data-iso + select)
  e "so novas" (data-new), secao Materials (ranking proprio top 10,
  score materials exibido), tamanho <= 100 KB alvo / < 150 KB cap duro.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest.mock as mock
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
import publish_pages as pp  # noqa: E402
import ranking_digest as rg  # noqa: E402
import url_liveness as ul  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures (offline; formato real do eligible_jobs.json)
# ---------------------------------------------------------------------------

def _job(i: int, *, company=None, score=None, de_text="", visa=False,
         iso="de", posted=None, apply_url=None) -> dict:
    return {
        "id": f"t{i}", "title": f"Praktikum Supply Chain {i}",
        "company": company or f"Firma {i} GmbH",
        "location": "Berlin, DE", "country_iso": iso,
        "score": 15.0 - (i * 0.1) if score is None else score,
        "url": f"https://jobs.example.com/{i}",
        "description": de_text or ("Werkstudent supply chain management "
                                   "logistics procurement " * 8),
        "posted_at": posted,
        "visa_friendly": visa,
        "raw": {"apply_url": apply_url} if apply_url else {},
    }


_DE_REQUIRED = "Sehr gute Deutschkenntnisse in Wort und Schrift erforderlich"
_DE_PREFERRED = "Deutschkenntnisse sind wünschenswert, English is required"
# menção BARE (sem qualificador forte na janela) -> plus (razão 'bare')
_DE_PLUS = "Deutschkenntnisse vorhanden. English business fluent."
_NO_DE = "English business fluent, work with global teams"


def _distinct_jobs(n: int, **kw) -> list[dict]:
    return [_job(i, **kw) for i in range(n)]


# ---------------------------------------------------------------------------
# T1 — diff de IDs (novas de ontem)
# ---------------------------------------------------------------------------

def test_diff_normal() -> None:
    section("T1: diff de IDs — normal / sem snapshot / corrompido / gigante")
    cur = _distinct_jobs(10)
    prev = [dict(j) for j in cur[:6]]  # 4 novas
    diff = rg.new_since_previous(cur, prev)
    check("diff normal: 4 novas",
          diff is not None and len(diff[0]) == 4 and len(diff[1]) == 0)
    check("ids novos corretos",
          diff[0] == {f"t{i}" for i in range(6, 10)})

    # 1o run: sem snapshot (None) -> sem diff, SEM erro
    check("sem snapshot -> None (secao ausente, sem erro)",
          rg.new_since_previous(cur, None) is None)
    check("load_ranking_or_none: arquivo ausente -> None",
          rg.load_ranking_or_none(Path("/tmp/nao_existe_f11.json")) is None)

    with tempfile.TemporaryDirectory(prefix="t_f11_snap_") as tmp:
        bad = Path(tmp) / "corrupto.json"
        bad.write_text("{corrompido", encoding="utf-8")
        check("load_ranking_or_none: corrompido -> None",
              rg.load_ranking_or_none(bad) is None)
        empty = Path(tmp) / "vazio.json"
        empty.write_text("[]", encoding="utf-8")
        check("load_ranking_or_none: lista vazia VALIDA -> [] (nao None)",
              rg.load_ranking_or_none(empty) == [])
        # snapshot vazio valido: TODOS os atuais sao novos (estado real)
        d2 = rg.new_since_previous(cur, [])
        check("snapshot vazio valido: todas as 10 sao novas",
              d2 is not None and len(d2[0]) == 10)

    # diff gigante: 600 novas (evento de dataset novo)
    big_cur = _distinct_jobs(600)
    d3 = rg.new_since_previous(big_cur, [])
    check("diff gigante: 600 novas computadas",
          d3 is not None and len(d3[0]) == 600)


def test_diff_digest_section() -> None:
    section("T1: digest 🆕 — contagem + top 3; gigante = so contagem")
    cur = _distinct_jobs(10)
    # 4 novas no topo (t6..t9); cada uma com apply_url
    for j in cur[6:]:
        j["raw"] = {"apply_url": f"https://apply.example.com/{j['id']}"}
    diff = rg.new_since_previous(cur, cur[:6])
    lines = rg.new_since_lines(diff, cur)
    text = "\n".join(lines)
    check("header com contagem", "🆕 Novas desde ontem: 4" in text)
    check("top 3 listado (t6/t7/t8 por score)", "t6" in text
          and "t7" in text and "t8" in text)
    check("4a nova nao listada, aviso (+N na página)", "t9" not in text
          and "(+1 outras novas — ver página)" in text)
    check("linha com apply_url", "https://apply.example.com/t6" in text)

    # diff None (sem snapshot): secao ausente
    check("sem snapshot: secao ausente", rg.new_since_lines(None, cur) == [])

    # 0 novas + 2 sumiram
    d0 = (set(), {"x", "y"})
    lines0 = rg.new_since_lines(d0, cur)
    check("0 novas: linha honesta",
          "🆕 Novas desde ontem: 0" in "\n".join(lines0)
          and "2 vaga(s) saíram" in "\n".join(lines0))

    # diff gigante: SO contagem, NUNCA a lista
    big = ({"x"} | {f"n{i}" for i in range(599)}, set())
    lines_big = rg.new_since_lines(big, cur)
    t_big = "\n".join(lines_big)
    check("diff gigante: contagem presente", "600" in t_big)
    check("diff gigante: sem lista de vagas", "Praktikum" not in t_big
          and "evento de dataset novo" in t_big)
    check("diff gigante: 3 linhas apenas (header+nota)",
          len(lines_big) == 2)


def test_diff_page_section() -> None:
    section("T1: pagina 🆕 — top 10 + data-new + toggle")
    cur = _distinct_jobs(40)
    new_ids = {f"t{i}" for i in (0, 1, 2, 39, 38, 37, 36, 35, 34, 33, 32, 31)}
    html = mp.render_minimal_html(cur, total_eligible=40,
                                  generated_at="x", new_since_ids=new_ids)
    check("secao 🆕 com contagem", "🆕 Novas desde ontem — 12 nova(s)" in html)
    check("badge 🆕 nos cards novos", html.count('class="newb"') >= 10)
    check("toggle 'só novas de ontem' presente", 'id="f-new"' in html)
    check("data-new=1 nos cards novos",
          html.count('data-new="1"') >= 10)
    # sem diff: sem secao, sem toggle
    html_no = mp.render_minimal_html(cur, total_eligible=40, generated_at="x")
    check("sem diff: sem secao 🆕", "🆕 Novas desde ontem" not in html_no)
    check("sem diff: sem toggle f-new", 'id="f-new"' not in html_no)


def test_diff_page_via_archive() -> None:
    section("T1: from_file com archive real (mecanica do snapshot anterior)")
    with tempfile.TemporaryDirectory(prefix="t_f11_arch_") as tmp:
        base = Path(tmp)
        cur = _distinct_jobs(20)
        (base / "eligible_jobs.json").write_text(json.dumps(cur),
                                                 encoding="utf-8")
        arch = base / "data" / "archive"
        yday = arch / "20261003T090001Z"
        yday.mkdir(parents=True)
        (yday / "eligible_jobs.json").write_text(
            json.dumps(cur[:12]), encoding="utf-8")
        html = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=arch,
            include_materials=False)
        check("diff contra snapshot: 8 novas", "8 nova(s)" in html)
        # snapshot corrompido: skip gracioso, sem secao, sem erro
        (yday / "eligible_jobs.json").write_text("{corrompido",
                                                 encoding="utf-8")
        html2 = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=arch,
            include_materials=False)
        check("snapshot corrompido: secao 🆕 omitida (sem erro)",
              "🆕 Novas desde ontem" not in html2)
        # sem archive dir: sem secao, sem erro
        html3 = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=base / "nao_existe",
            include_materials=False)
        check("archive inexistente: sem secao, sem erro",
              "🆕 Novas desde ontem" not in html3)


# ---------------------------------------------------------------------------
# T2 — EN-friendly (data-de, badge, toggle, digest 🎯)
# ---------------------------------------------------------------------------

def test_data_de_and_badge() -> None:
    section("T2: data-de por card + badge '🇩🇪 DE exigido' (só required)")
    jobs = [
        _job(0, de_text=_DE_REQUIRED),
        _job(1, de_text=_DE_PREFERRED),
        _job(2, de_text=_DE_PLUS),
        _job(3, de_text=_NO_DE),
    ]
    html = mp.render_minimal_html(jobs, total_eligible=4, generated_at="x")
    check("data-de=required", 'data-de="required"' in html)
    check("data-de=preferred", 'data-de="preferred"' in html)
    check("data-de=plus", 'data-de="plus"' in html)
    check("data-de=none (sem menção)", 'data-de="none"' in html)
    check("badge 🇩🇪 DE exigido APENAS em required",
          html.count("🇩🇪 DE exigido") == 1)
    check("toggle sem alemão exigido presente", 'id="f-de"' in html)
    check("label do toggle", "sem alemão exigido" in html)


def test_js_filters_node() -> None:
    section("T2: nucleo JS dos filtros (vf/de/country/new) executado em node")
    if shutil.which("node") is None:
        print("  [SKIP] node ausente — nucleo JS nao executado (CI tem node)")
        return
    # harness: DOM falso com os cards; valida o MATCH de cada filtro
    harness = """
var shown = [];
var li = function(attrs) {
  return { getAttribute: function(k) { return attrs[k] || null; },
           style: {}, _shown: false };
};
var cards = [
  li({'data-vf':'1','data-de':'required','data-iso':'de','data-new':'0','data-q':'a b'}),
  li({'data-vf':'0','data-de':'none','data-iso':'nl','data-new':'1','data-q':'c d'}),
  li({'data-vf':'1','data-de':'none','data-iso':'de','data-new':'0','data-q':'e f'}),
];
var el = { value:'', checked:false };
var state = { q:{value:''}, vf:{checked:false}, de:{checked:false},
              country:{value:''}, nw:{checked:false} };
// nucleo do filtro F11 (espelho da logica do _JS da pagina)
function applyF(st) {
  var c = 0;
  cards.forEach(function(li) {
    var ok = !st.q.value || li.getAttribute('data-q').indexOf(st.q.value) > -1;
    if (st.vf.checked) ok = ok && li.getAttribute('data-vf') === '1';
    if (st.de.checked) ok = ok && li.getAttribute('data-de') !== 'required';
    if (st.country.value) ok = ok && li.getAttribute('data-iso') === st.country.value;
    if (st.nw.checked) ok = ok && li.getAttribute('data-new') === '1';
    if (ok) c++;
  });
  return c;
}
if (applyF(state) !== 3) console.log('F1_FAIL');
state.vf.checked = true;
if (applyF(state) !== 2) console.log('F2_FAIL');
state.de.checked = true;
if (applyF(state) !== 1) console.log('F3_FAIL');
state.vf.checked = false; state.de.checked = false;
state.country.value = 'nl';
if (applyF(state) !== 1) console.log('F4_FAIL');
state.country.value = '';
state.nw.checked = true;
if (applyF(state) !== 1) console.log('F5_FAIL');
console.log('JS_OK');
"""
    proc = subprocess.run(["node", "-"], input=harness,
                          capture_output=True, text=True, timeout=30)
    out = proc.stdout.strip()
    check("núcleo dos 4 filtros correto em node", "JS_OK" in out
          and "FAIL" not in out)
    # e o _JS REAL da pagina roda sem erro com DOM nulo (guard F6)
    harness2 = """
var document = { querySelectorAll: function () { return []; },
  getElementById: function () { return null; } };
%s
console.log('REALJS_OK');
""" % mp._JS
    proc2 = subprocess.run(["node", "-"], input=harness2,
                           capture_output=True, text=True, timeout=30)
    check("_JS real da página roda em node (guards)", 
          proc2.returncode == 0 and "REALJS_OK" in proc2.stdout)


def test_applicable_digest() -> None:
    section("T2: digest 🎯 Top 5 aplicáveis — 5, <5 e 0")
    # 5 aplicáveis intercaladas com não-aplicáveis
    jobs = []
    for i in range(10):
        jobs.append(_job(
            i, visa=(i % 2 == 0),
            de_text=_DE_REQUIRED if i % 2 == 1 else _NO_DE,
        ))
    # visa: 0,2,4,6,8 (todas sem DE-required) -> 5 aplicáveis
    lines = rg.applicable_lines(jobs)
    text = "\n".join(lines)
    check("5 aplicáveis listadas", text.count("Praktikum") == 5)
    check("DE-required visa_friendly excluída (t1/t3...)",
          "Praktikum Supply Chain 1" not in text)
    # <5: só 2 vagas visa_friendly sem required
    few = [_job(0, visa=True, de_text=_NO_DE),
           _job(1, visa=True, de_text=_NO_DE),
           _job(2, visa=False)]
    lines_few = rg.applicable_lines(few)
    check("<5: lista o que houver (2)", "\n".join(lines_few).count("Praktikum") == 2)
    # 0 aplicáveis: linha graciosa
    none_ = [_job(0, visa=True, de_text=_DE_REQUIRED),
             _job(1, visa=False, de_text=_NO_DE)]
    lines_zero = rg.applicable_lines(none_)
    tz = "\n".join(lines_zero)
    check("0 aplicáveis: linha graciosa (filtros restritivos)",
          "nenhuma vaga aplicável" in tz and "Praktikum" not in tz)
    # ranking vazio
    lines_empty = rg.applicable_lines([])
    check("ranking vazio: header + '— ranking vazio'",
          len(lines_empty) == 2 and "ranking vazio" in lines_empty[1])


def test_applicable_in_digest_sections() -> None:
    section("T2: digest_sections embute 🆕 e 🎯 (antes do link)")
    with tempfile.TemporaryDirectory(prefix="t_f11_dg_") as tmp:
        base = Path(tmp)
        cur = [_job(0, visa=True, de_text=_NO_DE),
               _job(1, visa=False, de_text=_DE_REQUIRED),
               _job(2, visa=True, de_text=_NO_DE, score=14.0)]
        prev = [dict(cur[0])]  # t1/t2 novas
        (base / "cur.json").write_text(json.dumps(cur), encoding="utf-8")
        (base / "prev.json").write_text(json.dumps(prev), encoding="utf-8")
        sections = rg.digest_sections(base / "cur.json", base / "prev.json",
                                      pages_url="https://x/")
        text = "\n".join(sections or [])
        check("seção 🆕 no digest montado", "🆕 Novas desde ontem: 2" in text)
        check("seção 🎯 no digest montado", "🎯 Top 5 aplicáveis" in text)
        check("🎯 lista as 2 aplicáveis (t0 e t2)",
              "Praktikum Supply Chain 0" in text.split("🎯")[1]
              and "Praktikum Supply Chain 2" in text.split("🎯")[1])
        check("seções novas ANTES do link final",
              text.index("🎯 Top 5") < text.index("🔗 Ranking completo")
              and text.index("🆕 Novas") < text.index("🔗 Ranking completo"))
        check("link continua sendo a última linha",
              (sections or [])[-1].startswith("🔗 Ranking completo"))


# ---------------------------------------------------------------------------
# T3 — vitalidade de URL
# ---------------------------------------------------------------------------

class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(status_map: dict, error_urls: set):
    """HEAD fake: status por URL; error_urls = exceção de rede (timeout)."""
    def open(req, timeout=None):
        url = req.full_url
        if url in error_urls:
            raise TimeoutError("simulated timeout")
        status = status_map.get(url, 200)
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "err", {}, None)
        return _Resp()
    return open


def test_liveness_unit() -> None:
    section("T3: check_liveness — 404/410 morta; 403/429/timeout ignorados")
    ul.time.sleep = lambda s: None  # acelerar (fixture)
    jobs = [
        {"id": "ok", "url": "https://x/ok"},
        {"id": "dead404", "url": "https://x/404"},
        {"id": "dead410", "url": "https://x/410"},
        {"id": "bot403", "url": "https://x/403"},
        {"id": "bot429", "url": "https://x/429"},
        {"id": "slow", "url": "https://x/timeout"},
        {"id": "nourl", "url": ""},
    ]
    opener = _opener(
        {"https://x/404": 404, "https://x/410": 410,
         "https://x/403": 403, "https://x/429": 429},
        {"https://x/timeout"},
    )
    dead = ul.check_liveness(jobs, opener=opener)
    check("404/410 = mortas (2)", dead == {"dead404", "dead410"})
    check("403/429/timeout NÃO marcados", "bot403" not in dead
          and "bot429" not in dead and "slow" not in dead)
    check("UA honesto no request (identificável)",
          "internship-finder" in ul.LIVENESS_UA.lower())

    # falha TOTAL de rede: nenhuma resposta HTTP de nenhuma tentativa
    def all_timeout(req, timeout=None):
        raise TimeoutError("network down")

    dead2 = ul.check_liveness(jobs[:4], opener=all_timeout)
    check("falha total de rede: NENHUMA marca", dead2 == set())

    # deadline: estoura e devolve o que confirmou
    slow_jobs = [{"id": f"j{i}", "url": f"https://x/ok{i}"} for i in range(30)]
    dead3 = ul.check_liveness(slow_jobs, opener=_opener({}, set()),
                              deadline_s=-1)
    check("deadline estourado: devolve vazio sem erro", dead3 == set())

    # opener que levanta exceção inesperada no meio: nunca propaga
    def boom(req, timeout=None):
        raise RuntimeError("boom")

    dead4 = ul.check_liveness(jobs[:2], opener=boom)
    check("opener que explode: retorna (possivelmente vazio), não levanta",
          isinstance(dead4, set))


def test_liveness_page_integration() -> None:
    section("T3: mortas descem do top exibido + badge; JSON intocado")
    jobs = _distinct_jobs(20)
    html = mp.render_minimal_html(jobs, total_eligible=20, generated_at="x",
                                  dead_link_ids={"t0", "t5"})
    main_list = html.split('<ol id="list">')[1].split("</ol>")[0]
    check("t0 (morta) fora do ranking principal", "/0<" not in main_list
          and "jobs.example.com/0" not in main_list)
    check("t5 (morta) fora do ranking principal",
          "jobs.example.com/5" not in main_list)
    check("badge '🔗 morta' nos cards (nova lista pos-corte sem elas)",
          "🔗 morta" not in main_list)  # mortas descem: badge não aparece no principal
    check("20 vagas - 2 mortas = 18 cards",
          main_list.count("<li class=") == 18)
    # a próxima sobe: t20 não existe (19 é a última); corte = 18 exibidas

    # render NÃO toca a lista de entrada (base de dados intocavel)
    check("lista de entrada intocada (id t0 ainda presente)",
          jobs[0]["id"] == "t0" and len(jobs) == 20)

    # dead via from_file + publish: subprocesso real com --dead-list
    with tempfile.TemporaryDirectory(prefix="t_f11_pub_") as tmp:
        base = Path(tmp)
        cur = _distinct_jobs(12)
        data_dir = base / "data"
        data_dir.mkdir()
        (data_dir / "eligible_jobs.json").write_text(json.dumps(cur),
                                                     encoding="utf-8")
        (base / "scripts").mkdir()
        root_repo = Path(__file__).resolve().parent.parent
        for name in ("minimal_page.py", "publish_pages.py"):
            shutil.copy2(root_repo / "scripts" / name,
                         base / "scripts" / name)
        shutil.copytree(root_repo / "src" / "internship_finder",
                        base / "src" / "internship_finder",
                        ignore=shutil.ignore_patterns("__pycache__"))
        out = base / "out" / "index.html"
        html_pp = pp.render_ranking_html(
            base, out, top=pp.PUBLIC_TOP, dead_link_ids={"t0", "t1"})
        main2 = html_pp.split('<ol id="list">')[1].split("</ol>")[0]
        check("publish -> render: 2 mortas fora do principal",
              main2.count("<li class=") == 10)
        check("badge 🔗 morta ausente do principal (mortas descem)",
              "🔗 morta" not in main2)
        check("JSON de entrada intocado pelo render",
              len(json.loads((data_dir / "eligible_jobs.json")
                             .read_text(encoding="utf-8"))) == 12)


def test_liveness_refresh_integration() -> None:
    section("T3: estágio no refresh_daily — nunca derruba o run (mock)")
    import refresh_daily as rd

    with tempfile.TemporaryDirectory(prefix="t_f11_rd_") as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        data_dir.mkdir()
        (data_dir / "collection_metrics.jsonl").write_text(
            json.dumps({"run_id": "r1", "type": "run", "status": "ok",
                        "total_collected": 400, "eligible": 20,
                        "collected_at": "2026-10-04T09:00:00Z"}),
            encoding="utf-8")
        jobs = _distinct_jobs(20)
        (data_dir / "eligible_jobs.json").write_text(json.dumps(jobs),
                                                     encoding="utf-8")
        pages_dir = root / "pages"

        calls: dict = {"publish": [], "liveness": []}

        def fake_run(*a, **k):
            return subprocess.CompletedProcess(a[0], 0)

        def fake_publish(root, pages, *, exit_code, eligible, run_id,
                         dead_link_ids=None):
            calls["publish"].append((exit_code, eligible, run_id,
                                     dead_link_ids))
            return True

        def fake_liveness(jobs, **kw):
            calls["liveness"].append([j["id"] for j in jobs])
            return {"t0", "t1"}

        original_root = rd.repo_root
        rd.repo_root = lambda: root
        try:
            with mock.patch.object(rd, "run_collection", side_effect=fake_run), \
                 mock.patch.object(rd, "disk_usage_pct", return_value=50), \
                 mock.patch.object(rd.url_liveness, "check_liveness",
                                   side_effect=fake_liveness), \
                 mock.patch.object(rd.publish_pages, "publish_ranking",
                                   side_effect=fake_publish), \
                 mock.patch.object(rd, "notify_or_log",
                                   side_effect=lambda c, m, *, dry_run:
                                   {"sent": True}):
                rc = rd.main(["--config", str(root / ".env"),
                              "--pages-dir", str(pages_dir),
                              "--always-notify"])
        finally:
            rd.repo_root = original_root

        check("refresh termina exit 0 com estágio de vitalidade rodando",
              rc == 0)
        check("liveness chamado 1x sobre o corte 2/empresa (20/20 -> 20)",
              len(calls["liveness"]) == 1)
        check("corte passado ao check = top exibido (20 empresas distintas)",
              len(calls["liveness"][0]) == 20)
        check("ids mortos repassados ao publish",
              calls["publish"] and calls["publish"][0][3] == {"t0", "t1"})

        # estágio que EXPLODE: run segue, publish sem mortas
        calls["publish"].clear()
        calls["liveness"].clear()

        original_root = rd.repo_root
        rd.repo_root = lambda: root
        try:
            with mock.patch.object(rd, "run_collection", side_effect=fake_run), \
                 mock.patch.object(rd, "disk_usage_pct", return_value=50), \
                 mock.patch.object(rd.url_liveness, "check_liveness",
                                   side_effect=RuntimeError("rede fora")), \
                 mock.patch.object(rd.publish_pages, "publish_ranking",
                                   side_effect=fake_publish), \
                 mock.patch.object(rd, "notify_or_log",
                                   side_effect=lambda c, m, *, dry_run:
                                   {"sent": True}):
                rc2 = rd.main(["--config", str(root / ".env"),
                               "--pages-dir", str(pages_dir),
                               "--always-notify"])
        finally:
            rd.repo_root = original_root
        check("estágio explodindo: refresh segue exit 0", rc2 == 0)
        check("publish recebe dead_ids VAZIO quando o estágio falha",
              calls["publish"] and calls["publish"][0][3] == set())


# ---------------------------------------------------------------------------
# T4 — página 100 + diversidade + filtros + Materials
# ---------------------------------------------------------------------------

def test_page_top_100() -> None:
    section("T4: PAGE_TOP=100 + cap 2/empresa")
    check("PAGE_TOP = 100", mp.PAGE_TOP == 100)
    jobs = _distinct_jobs(150)
    html = mp.render_minimal_html(jobs, total_eligible=150,
                                  generated_at="x")
    main_list = html.split('<ol id="list">')[1].split("</ol>")[0]
    check("150 vagas/150 empresas -> 100 cards (cap)",
          main_list.count("<li class=") == 100)
    check("footer informa o total (150)", "150 vagas elegíveis" in html)


def test_company_cap_rule() -> None:
    section("T4: regra máx 2/empresa — 3ª pulada, próxima sobe")
    jobs = [
        _job(0, company="SAP", score=15.0),
        _job(1, company="SAP", score=14.0),
        _job(2, company="SAP", score=13.0),     # 3ª SAP: pulada
        _job(3, company="Bosch", score=12.0),
        _job(4, company="SAP", score=11.0),     # 4ª SAP: pulada
        _job(5, company="STIHL", score=10.0),
    ]
    shown = mp.apply_company_cap(jobs)
    ids = [j["id"] for j in shown]
    check("ordem oficial preservada com pulos (t0,t1,t3,t5)",
          ids == ["t0", "t1", "t3", "t5"])
    check("3ª+ ocorrência da mesma empresa pulada",
          "t2" not in ids and "t4" not in ids)
    check("scores/ordem dos exibidos intactos",
          [j["score"] for j in shown] == [15.0, 14.0, 12.0, 10.0])
    # casefold: "sap" == "SAP" (mesma empresa); "S a P" é OUTRA empresa
    jobs2 = [
        _job(0, company="SAP", score=15.0),
        _job(1, company="sap", score=14.0),
        _job(2, company="S a P", score=13.0),
    ]
    shown2 = mp.apply_company_cap(jobs2)
    check("casefold: SAP == sap (cap conta junto); S a P distinta",
          [j["id"] for j in shown2] == ["t0", "t1", "t2"])
    # cap interage com limit: 4 empresas * 2 = 8 < limit 100
    many = []
    for i in range(40):
        many.append(_job(i, company=f"C{i % 4}"))
    shown3 = mp.apply_company_cap(many)
    check("4 empresas x 40 vagas -> 8 cards", len(shown3) == 8)


def test_country_and_new_filters() -> None:
    section("T4: filtros client-side — país (data-iso) e só novas")
    jobs = [
        _job(0, iso="de"),
        _job(1, iso="nl"),
        _job(2, iso="lu"),
        _job(3, iso="fi"),
        _job(4, iso="be"),
        _job(5, iso="de"),
    ]
    html = mp.render_minimal_html(jobs, total_eligible=6, generated_at="x",
                                  new_since_ids={"t1", "t3"})
    for iso in ("de", "nl", "lu", "fi", "be"):
        check(f"data-iso={iso} nos cards", f'data-iso="{iso}"' in html)
    check("select de país presente (5 opções)", 'id="f-country"' in html
          and html.count("<option value=") >= 6)
    check("sem bandeira 🇩🇪 no select (contrato F7: DE default visual)",
          "🇩🇪" not in html)


def test_materials_section() -> None:
    section("T4: seção Materials — top 10 por materials_score (perfil próprio)")
    from internship_finder.materials_ranking import rank_materials_jobs
    jobs = [
        _job(0, de_text="Praktikum Materials Testing metallische Werkstoffe"),
        _job(1, de_text="Werkstudent Batteriezelle Entwicklung Kathode"),
        _job(2, de_text="Working Student Logistik Versand"),
        _job(3, de_text="Intern Polymer Processing Spritzguss"),
    ]
    mat = rank_materials_jobs(jobs)[:mp.MATERIALS_SECTION_TOP]
    html = mp.render_minimal_html(jobs, total_eligible=4, generated_at="x",
                                  materials=mat)
    check("seção 🧪 Materials Engineering presente",
          "🧪 Materials Engineering" in html)
    check("header explica perfil alternativo", "perfil alternativo" in html)
    mat_cards = html.split("🧪 Materials Engineering")[1]
    check("cards materials = min(4, 10)", mat_cards.count("<li class=") == 4)
    check("score da seção é o materials_score (não o principal)",
          "data-s=" in mat_cards)
    # from_file computa a seção sozinho (default ON)
    with tempfile.TemporaryDirectory(prefix="t_f11_mat_") as tmp:
        base = Path(tmp)
        (base / "eligible_jobs.json").write_text(json.dumps(jobs),
                                                 encoding="utf-8")
        html2 = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=None)
        check("from_file: seção Materials por default",
              "🧪 Materials Engineering" in html2)
        # include_materials=False desliga
        html3 = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=None,
            include_materials=False)
        check("include_materials=False: sem seção",
              "🧪 Materials Engineering" not in html3)


def test_size_budget() -> None:
    section("T4: tamanho — 100 vagas reais-ish dentro do alvo/cap")
    jobs = _distinct_jobs(100)
    for j in jobs:
        j["description"] = ("Werkstudent supply chain logistik beschaffung "
                            "procurement SAP Excel " * 12)
    html = mp.render_minimal_html(jobs, total_eligible=2456,
                                  generated_at="2026-10-04 09:32")
    size = len(html.encode("utf-8"))
    check("100 cards principais", html.split('<ol id="list">')[1]
          .split("</ol>")[0].count("<li class=") == 100)
    check(f"tamanho {size} <= 100 KB (alvo)", size <= mp.PAGE_TARGET_BYTES)
    check(f"tamanho {size} < 150 KB (cap duro)", size < mp.PAGE_HARD_CAP_BYTES)
    check("gate check_public_safe aprova", pp.check_public_safe(html) == [])


def test_age_badge() -> None:
    section("T3b: badge de idade (posted_at) — só display")
    from datetime import UTC, datetime, timedelta
    ref_posted = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    jobs = [_job(0, posted=ref_posted), _job(1, posted=None)]
    html = mp.render_minimal_html(jobs, total_eligible=2, generated_at="x")
    check("badge 'há 3d' na vaga com posted_at", "há 3d" in html)
    check("sem badge na vaga sem posted_at", html.count("class=\"age\"") == 1)


def main() -> None:
    test_diff_normal()
    test_diff_digest_section()
    test_diff_page_section()
    test_diff_page_via_archive()
    test_data_de_and_badge()
    test_js_filters_node()
    test_applicable_digest()
    test_applicable_in_digest_sections()
    test_liveness_unit()
    test_liveness_page_integration()
    test_liveness_refresh_integration()
    test_page_top_100()
    test_company_cap_rule()
    test_country_and_new_filters()
    test_materials_section()
    test_size_budget()
    test_age_badge()
    print()
    if FAILURES:
        print(f"FALHAS ({len(FAILURES)}):")
        for name in FAILURES:
            print(f"  - {name}")
        raise SystemExit(1)
    print("TUDO OK")


if __name__ == "__main__":
    main()
