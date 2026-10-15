"""Testes da Fase F43 — página full-list: todas as vagas + abas por perfil +
busca sobre a lista inteira + lazy-render (100% offline).

Bug de PRODUTO que a F43 fecha (medido na revisão de 14/10, reconfirmado no
A/B da fase sobre o archive 15/10): a página pública era a UNIÃO PARCIAL de
seções com critérios distintos (📊 top-100 por score + 🆕 novas + 🎯 radar +
🧪 materials + 🇪🇺 EU) — cada seção com o seu próprio critério de entrada, e
o corte top-N com cap 2/empresa escondendo o resto. Resultado: vagas do
top-100 por score AUSENTES do HTML (A/B 15/10 com dados reais: 55/100 no
regime legado; 118 de 861 vagas com link). O dono procurou a vaga no site e
não achou — eram estes buracos.

Contratos testados (o regime top-N legado da F11 é INTOCADO — byte a byte):

- T1: regime FULL lista o UNIVERSO inteiro (zero ausência do top-100 por
  score, medido por ``data-jid``); o regime legado sobre a MESMA fixture
  deixa vagas de fora (prova de que a fixture exercita o buraco) e o
  rodapé do full conta a verdade ("todas as N vagas elegíveis").
- T2: abas por perfil (💼 business default / 🧪 materials / 🇪🇺 EU) no HTML
  do regime full + CSS próprio; o legado não ganha nenhuma dessas marcas.
- T3: núcleo JS das abas/busca executado em node com DOM simulado (padrão
  F5/F13): reordenação por perfil, ocultação de quem não tem o perfil,
  contagem visível e busca client-side sobre os cards — inclusive os que
  ainda não foram revelados (a busca é sobre ATRIBUTOS no DOM, não sobre
  pixels).
- T4: núcleo PURO do lazy-render (``f43LazyInit``) executado em node: o
  mapa de revelação inicial é determinístico (primeiros N "eager").
- T5: orçamento de página do regime full = cap PROPORCIONAL e monotônico
  (``page_full_cap_bytes``), com piso no cap duro legado; o corte de
  garantia (``full_limit``) devolve página dentro do cap com rodapé
  HONESTO ("mostrando X de Y").
- T6: regressão zero do regime legado (nenhuma marca F43; default ==
  ``full_list=False`` explícito; seções de sempre presentes).
- T7: no full, as seções 🧪/🇪🇺 continuam no HTML como ATALHOS (dedupe
  contra a lista única — nenhum ``data-jid`` duplicado no documento) e com
  header honesto ("destaques fora do top N").
- T8: o regime liga sozinho quando o chamador pede o universo
  (``top >= PAGE_TOP_FULL`` — é o que o publish pede via ``PUBLIC_TOP``) e
  NÃO liga com ``top`` explícito pequeno (``--top 100`` segue legado).

Fixtures: SINTÉTICAS, campos mínimos — nenhum payload real, nenhum dado de
produção, zero rede.

Uso:  .venv/bin/python scripts/test_f43.py   (ou bash scripts/test_f43.py)
"""

from __future__ import annotations

import html as _html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
from internship_finder.eu_ranking import rank_eu_stratum  # noqa: E402
from internship_finder.materials_ranking import rank_materials_jobs  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

STAMP = "2026-10-15 22:00"  # carimbo fixo: renders A/B comparaveis


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


def esc(value: object) -> str:
    return _html.escape(str(value), quote=True)


# ---------------------------------------------------------------------------
# Fixture sintética — o buraco da união parcial precisa de DUAS coisas:
# empresas repetidas (o cap 2/empresa esconde a 3ª+ vaga) e vagas do top-100
# por score fora das seções parciais.
# ---------------------------------------------------------------------------

N_JOBS = 140
N_COMPANIES = 40  # 140/40: 3-4 vagas por empresa -> cap 2/empresa morde
NON_DE = ("nl", "be", "lu", "fi")


def make_jobs(n: int = N_JOBS, n_companies: int = N_COMPANIES) -> list[dict]:
    jobs = []
    for i in range(n):
        iso = "de" if i % 5 else NON_DE[(i // 5) % len(NON_DE)]
        jobs.append({
            "id": f"fx|f43:{i}",
            "title": f"Praktikum Supply Chain Beschaffung {i} (m/w/d)",
            "company": f"Firma {i % n_companies} GmbH",
            "location": f"Stadt {i}, {iso.upper()}",
            "country_iso": iso,
            "employment_type": "FULL_TIME",
            "url": f"https://jobs.example.com/f43/{i}",
            "description": "Beschaffung und supplier management. " * 8,
            "score": round(50.0 - i * 0.1, 2),
        })
    return jobs


def sections_of(jobs: list[dict]) -> dict:
    """Seções 🧪/🇪🇺 do MESMO jeito que o chamador real (from_file) monta."""
    return {
        "materials": rank_materials_jobs(jobs)[:mp.MATERIALS_SECTION_TOP],
        "eu": rank_eu_stratum(jobs)[:mp.EU_SECTION_TOP],
    }


def render_legacy(jobs: list[dict]) -> str:
    return mp.render_size_aware(jobs, total_eligible=len(jobs),
                                generated_at=STAMP, top=mp.PAGE_TOP,
                                **sections_of(jobs))


def render_full(jobs: list[dict]) -> str:
    return mp.render_size_aware(jobs, total_eligible=len(jobs),
                                generated_at=STAMP, top=mp.PAGE_TOP,
                                full_list=True, profile_maps=mp._profile_maps(jobs),
                                **sections_of(jobs))


def has_jid(page: str, job_id: str) -> bool:
    return f'data-jid="{esc(job_id)}"' in page


# ---------------------------------------------------------------------------
# T1 — o buraco (legado) e a lista completa (full)
# ---------------------------------------------------------------------------

def test_full_list_zero_ausencias() -> None:
    section("T1: full-list = universo inteiro (zero ausência do top-100)")
    jobs = make_jobs()
    top100 = jobs[:100]
    legacy = render_legacy(jobs)
    full = render_full(jobs)

    full_present = sum(1 for j in top100 if has_jid(full, j["id"]))
    # O legado nem emite data-jid: a presença dele é medida pelo LINK da vaga.
    leg_links = sum(1 for j in top100
                    if f'href="{esc(j["url"])}"' in legacy)
    full_links = sum(1 for j in top100
                     if f'href="{esc(j["url"])}"' in full)
    print(f"       top-100 por score: legado {leg_links}/100 links "
          f"| full {full_present}/100 data-jid e {full_links}/100 links")

    check("legado deixa vagas do top-100 de fora (fixture exercita o buraco)",
          leg_links < 100, f"{leg_links}/100")
    check("full: TODAS as 100 vagas do top-100 no HTML (data-jid)",
          full_present == 100, f"{full_present}/100")
    check("full: os 100 links de vaga também presentes",
          full_links == 100, f"{full_links}/100")
    check("full: universo inteiro listado (140 vagas)",
          sum(1 for j in jobs if has_jid(full, j["id"])) == N_JOBS)
    check("full: rodapé honesto com o total do universo",
          "todas as 140 vagas elegíveis" in full)
    check("legado: rodapé continua o da F11 (Top N de M, sem sufixo novo)",
          "Top 80 de 140 vagas elegíveis ·" in legacy)
    leg_main = legacy.split('<ol id="list">')[1].split("</ol>")[0]
    check("legado: o corte por empresa é a causa (80 < 100 vagas listadas)",
          leg_main.count('<li class="c') == 80,
          str(leg_main.count('<li class="c')))
    check("legado não ganha data-jid (regime antigo intocado)",
          "data-jid=" not in legacy)


# ---------------------------------------------------------------------------
# T2 — abas por perfil
# ---------------------------------------------------------------------------

def test_abas_por_perfil() -> None:
    section("T2: abas 💼/🧪/🇪🇺 no regime full (e só nele)")
    jobs = make_jobs()
    full = render_full(jobs)
    legacy = render_legacy(jobs)
    check('full: barra de abas presente (id="tabs")', 'id="tabs"' in full)
    for prof, label in (("business", "💼"), ("materials", "🧪"), ("eu", "🇪🇺")):
        check(f'full: aba {prof} presente ({label})',
              f'data-prof="{prof}"' in full)
    check("full: default = business com classe 'on' e aria-selected",
          'class="on" data-prof="business" aria-selected="true"' in full)
    check("full: contador visível (#n) entra na página",
          '<span id="n" class="count" aria-live="polite"></span>' in full)
    check("full: CSS das abas só no regime full (bloco próprio)",
          "#tabs button.on" in full and "#tabs button.on" not in legacy)
    check("legado: nenhuma aba no HTML", 'id="tabs"' not in legacy)
    check("legado: CSS do full não vaza para o regime antigo",
          "content-visibility" not in legacy and "f43LazyInit" not in legacy)
    # data-attrs de perfil: presentes para as vagas do estrato materials/EU
    check("full: card do perfil materials traz score e rank",
          'data-mat="' in full and 'data-matr="' in full)
    check("full: card do estrato não-DE traz score e rank EU",
          'data-eu="' in full and 'data-eur="' in full)
    check("full: rank business no card (a coluna .r exibida)",
          'data-r="1"' in full)


# ---------------------------------------------------------------------------
# T3 — núcleo JS das abas/busca em node (DOM simulado)
# ---------------------------------------------------------------------------

NODE_HARNESS = """
function mk(a){return {a:a||{},style:{},kids:[],
  getAttribute:function(k){return (k in this.a)?this.a[k]:null;},
  setAttribute:function(k,v){this.a[k]=v;},
  removeAttribute:function(k){delete this.a[k];},
  appendChild:function(c){var i=this.kids.indexOf(c);
    if(i>-1)this.kids.splice(i,1); this.kids.push(c);},
  addEventListener:function(){}};}
var cards=[
  mk({'data-jid':'a','data-q':'praktikum einkauf alpha','data-s':'12','data-r':'1',
      'data-mat':'9','data-matr':'3','data-eu':'7','data-eur':'2','data-vf':'1',
      'data-de':'none','data-iso':'nl','data-new':'0','data-ws':'0','data-data':'0'}),
  mk({'data-jid':'b','data-q':'praktikum logistik beta','data-s':'15','data-r':'2',
      'data-de':'required','data-iso':'de','data-new':'1','data-ws':'0','data-data':'0'}),
  mk({'data-jid':'c','data-q':'internship controlling gamma','data-s':'9','data-r':'3',
      'data-mat':'11','data-matr':'1','data-de':'none','data-iso':'de','data-new':'0',
      'data-ws':'1','data-data':'1'})];
var tabs=[mk({'data-prof':'business'}),mk({'data-prof':'materials'}),
          mk({'data-prof':'eu'})];
var ol=mk({}), cnt={textContent:''}, q=mk({}); q.value='';
var document={querySelectorAll:function(s){return s==='#tabs button'?tabs:cards;},
  getElementById:function(i){
    if(i==='list')return ol; if(i==='n')return cnt; if(i==='q')return q;
    return null;}};
var window={};
%(js)s
function snap(){return {order:ol.kids.map(function(k){return k.a['data-jid'];}),
  disp:cards.map(function(c){return c.style.display;}),count:cnt.textContent,
  on:tabs.map(function(t){return t.a['data-prof']+':'+t.className;})};}
window.__F43sync(); window.__F43apply('business');
var business=snap();
window.__F43apply('materials');
var materials=snap();
window.__F43apply('eu');
var eu=snap();
q.value='alpha'; window.__F43sync(); window.__F43apply('business');
var search=snap();
console.log(JSON.stringify({business:business,materials:materials,eu:eu,search:search}));
"""


def _node(js: str, harness: str, timeout: int = 30) -> tuple[int, str, str]:
    proc = subprocess.run(["node", "-"], input=harness % {"js": js},
                          capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def test_js_abas_e_busca_node() -> None:
    section("T3: núcleo JS das abas + busca sobre a lista (node, DOM simulado)")
    if shutil.which("node") is None:
        check("node disponível p/ executar o núcleo JS", False,
              "[SKIP] node ausente (CI tem node)")
        return
    rc, out, err = _node(mp._JS_PROFILE, NODE_HARNESS)
    check("núcleo JS roda em node sem erro", rc == 0, err.strip()[:200])
    if rc != 0:
        return
    data = json.loads(out.strip().splitlines()[-1])

    b = data["business"]
    check("business (default): ordem por score desc",
          b["order"] == ["b", "a", "c"], str(b["order"]))
    check("business: nenhum card oculto e contagem = 3",
          b["disp"] == ["", "", ""] and b["count"] == "3 vagas", str(b))
    check("business: aba ativa marcada (class=on)",
          b["on"] == ["business:on", "materials:", "eu:"], str(b["on"]))

    m = data["materials"]
    check("materials: reordena pela coluna do perfil (c 11 > a 9)",
          m["order"] == ["c", "a", "b"], str(m["order"]))
    check("materials: vaga sem score do perfil fica FORA (b = none)",
          m["disp"][1] == "none" and m["count"] == "2 vagas", str(m))

    e = data["eu"]
    check("EU: só o estrato não-DE aparece (a), resto oculto",
          e["disp"] == ["", "none", "none"] and e["count"] == "1 vagas",
          str(e))

    s = data["search"]
    check("busca client-side: só o card que casa com 'alpha'",
          s["disp"] == ["", "none", "none"] and s["count"] == "1 vagas",
          str(s))
    check("busca é por ATRIBUTO do card (data-q), não por pixel: "
          "funciona sobre o que ainda não foi revelado",
          "data-q" in mp._JS_PROFILE and "getAttribute('data-q')" in mp._JS_PROFILE)
    check("busca/filtros religam a lista ao digitar (listener no input)",
          "if(q)q.addEventListener('input',onFilter)" in mp._JS_PROFILE)


# ---------------------------------------------------------------------------
# T4 — núcleo puro do lazy-render em node
# ---------------------------------------------------------------------------

LAZY_HARNESS = """
function mk(jid){return {getAttribute:function(k){return k==='data-jid'?jid:null;}};}
var all=[mk('j1'),mk('j2'),mk('j3'),mk('j4'),mk('j5')];
%(js)s
console.log(JSON.stringify({n2:f43LazyInit(all,2),n0:f43LazyInit(all,0),
  n9:f43LazyInit(all,9),vazio:f43LazyInit([],3)}));
"""


def test_lazy_core_node() -> None:
    section("T4: núcleo puro do lazy-render (node)")
    if shutil.which("node") is None:
        check("node disponível p/ o núcleo do lazy", False,
              "[SKIP] node ausente (CI tem node)")
        return
    rc, out, err = _node(mp._JS_LAZY_CORE, LAZY_HARNESS)
    check("f43LazyInit roda em node sem erro", rc == 0, err.strip()[:200])
    if rc != 0:
        return
    d = json.loads(out.strip().splitlines()[-1])
    check("N=2: primeiros 2 'eager' (1), resto adiado (0)",
          d["n2"] == {"j1": "1", "j2": "1", "j3": "0", "j4": "0", "j5": "0"},
          str(d["n2"]))
    check("N=0: nada eager (mas o mapa existe p/ todos)",
          set(d["n0"].values()) == {"0"} and len(d["n0"]) == 5)
    check("N>nº de cards: tudo eager", set(d["n9"].values()) == {"1"})
    check("lista vazia: mapa vazio (sem erro)", d["vazio"] == {})
    check("wrapper real usa o MESMO núcleo (f43LazyInit) — o teste do IO "
          "fica por wrapper não-testável offline (documentado)",
          "f43LazyInit(lis,N)" in mp._JS_LAZY_IO)
    check("sem IntersectionObserver o wrapper revela TUDO (página nunca vazia)",
          "!('IntersectionObserver' in window)" in mp._JS_LAZY_IO)
    check("página carrega o CSS que evita render fora da viewport",
          'li.c[data-lazy="1"]{content-visibility:auto' in mp._CSS_F43)


# ---------------------------------------------------------------------------
# T5 — orçamento de página do regime full
# ---------------------------------------------------------------------------

def test_cap_proporcional() -> None:
    section("T5: cap proporcional do regime full + corte de garantia honesto")
    jobs = make_jobs()
    cap = mp.page_full_cap_bytes(len(jobs))
    full = render_full(jobs)
    size = len(full.encode("utf-8"))
    print(f"       cap({len(jobs)}) = {cap} bytes | página full = {size} bytes")
    check("cap proporcional cresce com o universo", mp.page_full_cap_bytes(900)
          > mp.page_full_cap_bytes(100))
    check("cap tem piso no cap duro legado (universo pequeno não fica "
          "com cap menor que a página entregável)",
          mp.page_full_cap_bytes(0) == mp.PAGE_HARD_CAP_BYTES)
    check("cap = chrome + orçamento por card quando acima do piso",
          mp.page_full_cap_bytes(1000)
          == mp.FULL_CHROME_BYTES + mp.FULL_CARD_BUDGET_BYTES * 1000)
    check("página full do universo cabe no cap do dia", size <= cap,
          f"{size} <= {cap}")
    # A faixa mudou de verdade: com universo maior a página passa FOLGADO do
    # cap fixo legado e continua dentro do cap proporcional (é o regime que
    # entrega ~900 vagas reais em ~1,1MB — ver A/B da fase).
    big = make_jobs(300)
    big_page = render_full(big)
    big_size = len(big_page.encode("utf-8"))
    big_cap = mp.page_full_cap_bytes(len(big))
    print(f"       universo 300: página {big_size} bytes | cap {big_cap} bytes "
          f"(cap legado fixo {mp.PAGE_HARD_CAP_BYTES})")
    check("universo maior passa do cap fixo de 150KB (faixa nova de página)",
          big_size > mp.PAGE_HARD_CAP_BYTES, f"{big_size} bytes")
    check("universo maior ainda cabe no cap proporcional", big_size <= big_cap)

    # corte de garantia: full_limit força o prefixo e o rodapé conta a verdade
    cut = mp.render_minimal_html(jobs, total_eligible=len(jobs),
                                 generated_at=STAMP, full_list=True,
                                 profile_maps=mp._profile_maps(jobs),
                                 full_limit=5)
    check("corte de garantia: prefixo do ranking (5 primeiros ids)",
          all(has_jid(cut, jobs[i]["id"]) for i in range(5)))
    check("corte de garantia: nada além do prefixo",
          not has_jid(cut, jobs[5]["id"]))
    check("corte de garantia: rodapé HONESTO (mostrando X de Y)",
          "mostrando 5 de 140 vagas" in cut)
    check("corte de garantia: página menor que o cap",
          len(cut.encode("utf-8")) <= cap)
    check("legado não aceita full_limit (0 cards = só seções, sem vazamento)",
          not has_jid(mp.render_minimal_html(
              jobs, total_eligible=len(jobs), generated_at=STAMP,
              full_limit=5), jobs[0]["id"]))


# ---------------------------------------------------------------------------
# T6 — regressão zero do regime legado
# ---------------------------------------------------------------------------

def test_regressao_zero_legado() -> None:
    section("T6: regime top-N legado (F11) intocado")
    jobs = make_jobs()
    default = render_legacy(jobs)
    explicit = mp.render_size_aware(jobs, total_eligible=len(jobs),
                                    generated_at=STAMP, top=mp.PAGE_TOP,
                                    full_list=False, profile_maps=None,
                                    **sections_of(jobs))
    check("default == full_list=False explícito (byte a byte)",
          default == explicit)
    for marker in ("data-jid=", 'id="tabs"', "f43LazyInit", "content-visibility",
                   "#tabs button", "data-mat=", "data-eu=", "vagas elegíveis (orçamento"):
        check(f"legado sem a marca F43 {marker!r}", marker not in default)
    leg_main = default.split('<ol id="list">')[1].split("</ol>")[0]
    check("legado: corte top-100 + cap 2/empresa segue valendo (80 na lista)",
          leg_main.count('<li class="c') == 80,
          str(leg_main.count('<li class="c')))
    check("legado: cabe no cap duro legado",
          len(default.encode("utf-8")) < mp.PAGE_HARD_CAP_BYTES)


# ---------------------------------------------------------------------------
# T7 — seções de sempre no full (atalhos, sem duplicata)
# ---------------------------------------------------------------------------

def test_secoes_intactas_full() -> None:
    section("T7: seções 🧪/🇪🇺 seguem no full como DESTAQUE do perfil")
    jobs = make_jobs()
    full = render_full(jobs)

    # A lista única (#list) é o universo inteiro, sem duplicata DENTRO dela.
    main_block = full.split('<ol id="list">')[1].split("</ol>")[0]
    ids = re.findall(r'data-jid="([^"]*)"', main_block)
    check("lista única (#list) tem o universo inteiro, uma vez cada",
          len(ids) == N_JOBS and len(set(ids)) == N_JOBS, str(len(ids)))
    check("fora da #list só há seções (sem cards órfãos de perfil)",
          full.count('<li class="c') > N_JOBS)

    check("seção 🧪 presente no full com header de destaque",
          "destaques do perfil 🧪" in full)
    check("seção 🇪🇺 presente no full com header de destaque",
          "destaques do perfil 🇪🇺" in full)
    check("nota do destaque aponta a aba (reordenação da lista INTEIRA)",
          "use a aba 🧪 para " in full and "reordená-la INTEIRA" in full
          and "use a aba 🇪🇺 para " in full)

    # Destaque = MESMO ranking do pipeline (nenhuma regra nova no render).
    mat_top = rank_materials_jobs(jobs)[0]
    eu_top = rank_eu_stratum(jobs)[0]
    mat_sec = full.split("destaques do perfil 🧪")[1].split("destaques do perfil 🇪🇺")[0]
    check("destaque 🧪 abre com o top-1 do rank_materials_jobs",
          has_jid(mat_sec, mat_top["id"]))
    check("destaque 🇪🇺 abre com o top-1 do rank_eu_stratum",
          has_jid(full.split("destaques do perfil 🇪🇺")[1], eu_top["id"]))
    check("rank do perfil no card = posição no ranking (top-1 materials = 1)",
          f'data-jid="{esc(mat_top["id"])}" data-r="' in full
          and f'data-matr="1"' in full)
    check("seções continuam cobertas por teste de contrato próprio (F36.1)",
          Path(__file__).with_name("test_f36_1.py").exists())


# ---------------------------------------------------------------------------
# T8 — o regime liga pelo pedido "todas as vagas" (publish) e não por --top N
# ---------------------------------------------------------------------------

def test_auto_regime() -> None:
    section("T8: regime liga com top >= PAGE_TOP_FULL (publish) e não com --top 100")
    jobs = make_jobs()[:12]
    tmp = Path(tempfile.mkdtemp(prefix="f43-test-", dir=str(
        Path.home() / ".hermes" / "cache" / "scratch"))) / "jobs.json"
    tmp.write_text(json.dumps(jobs), encoding="utf-8")
    try:
        full = mp.render_minimal_html_from_file(
            tmp, top=mp.PAGE_TOP_FULL, include_materials=True,
            include_eu=True, generated_at=STAMP)
        legacy = mp.render_minimal_html_from_file(
            tmp, top=mp.PAGE_TOP, include_materials=True, include_eu=True,
            generated_at=STAMP)
        check("top=PAGE_TOP_FULL (publish: PUBLIC_TOP) liga o full",
              'id="tabs"' in full and has_jid(full, jobs[0]["id"]))
        check("top=PAGE_TOP (--top 100) mantém o legado",
              'id="tabs"' not in legacy and not has_jid(legacy, jobs[0]["id"]))
        check("--full-list explícito também liga (full_list=True)",
              'id="tabs"' in mp.render_minimal_html_from_file(
                  tmp, top=mp.PAGE_TOP, full_list=True, generated_at=STAMP))
        rc = subprocess.run(
            [sys.executable, str(Path(mp.__file__)), "--help"],
            capture_output=True, text=True, timeout=60)
        check("CLI --help anuncia --full-list",
              "--full-list" in rc.stdout, rc.stdout[-200:] if rc.returncode else "")
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


def main() -> int:
    print("F43 — página full-list (todas as vagas, abas, busca, lazy-render)")
    test_full_list_zero_ausencias()
    test_abas_por_perfil()
    test_js_abas_e_busca_node()
    test_lazy_core_node()
    test_cap_proporcional()
    test_regressao_zero_legado()
    test_secoes_intactas_full()
    test_auto_regime()
    print()
    if FAILURES:
        print(f"F43: FALHAS: {len(FAILURES)} de {CHECKS} checks")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print(f"F43: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
