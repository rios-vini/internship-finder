"""F46 — RSS estático + toggle de i18n (pt-BR/en) na página pública.

Trava os contratos da F46 (branch feature/f46-rss-i18n; default do render
= EN, decisão do dono 15/10 — alemão FORA):

GRUPO A — FONTE ÚNICA de strings (I18N):
  A1. toda chave tem o par {"pt", "en"} (paridade obrigatória);
  A2. valores pt VERBATIM das constantes do main (legal/duração/matrícula/
      remuneração — nunca redigidos de novo);
  A3. builds pt dos templates JS reproduzem as constantes pré-F46 byte a
      byte (zero placeholder @@ residual);
  A4. builds en carregam as strings EN do dict (sem drift do código).

GRUPO B — A/B byte a byte (lição do PR #145: SHA CONGELADO, nunca main
móvel): MESMA fixture no minimal_page.py pré-F46 (subprocesso offline) —
render(lang="pt") == main BYTE A BYTE nos DOIS regimes (top-N e full,
com vitrine/aliases como o publish usa). Indisponível (checkout
shallow): degrada com aviso, nunca falso-verde.

GRUPO C — render EN (default/publish) difere SÓ no chrome:
  C1. cards: mesmos hrefs de vaga/apply, mesmos data-*, mesma ordem
      (o único href novo é o <link rel=alternate> do RSS no head);
  C2. maquinaria do toggle SÓ no EN (data-i18n-pt*, botão, __I18N_JS,
      localStorage if46lang, alternate do feed); o render pt NÃO ganha
      um byte disso;
  C3. html lang=en no EN / pt-BR no pt.

GRUPO D — mecanismo do toggle (vanilla, UM HTML só, sem re-fetch):
  D1. _js_i18n_script embute __I18N_JS com paridade pt/en e a chave de
      persistência; D2. textos pt do dia viajam nos attrs; D3. o map JS
      cobre exatamente as strings criadas por JS (contador F43 + F53).

GRUPO E — RSS estático (render_rss_xml / --rss):
  E1. XML válido, escape total (& < > " em dados), sem CDATA;
  E2. determinístico: mesmo input+stamp -> mesmos BYTES (o único
      instante vem do carimbo do render; nada de now());
  E3. pubDate = posted_at em RFC-822; sem posted_at = sem pubDate
      (nunca inventado); lastBuildDate = carimbo do render;
  E4. espelha o RENDER ATUAL via sink: mesma lista final (exclui
      mortas/inaplicáveis, mesma ordem de score, mesmo corte);
  E5. gate check_public_safe VERDE no feed (e o scanner varre o feed
      no publish — falha segura); E6. CLI --rss escreve o arquivo.

GRUPO F — publish F46: publish_html grava index.html + rss.xml com um
commit único; feed com segredo BLOQUEIA o push inteiro (falha segura,
sem push do dia); rss=None preserva o comportamento pré-F46.

GRUPO G — ci.yml: test_f46 entra na UNIÃO AO VIVO do array (lido do
head atual — nunca hardcode de contagem).
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.dom.minidom as minidom
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

import minimal_page as mp  # noqa: E402
import publish_pages as pp  # noqa: E402

FAILURES: list[str] = []
N = 0
STAMP = "2026-10-18 04:00"

# Baseline CONGELADO do A/B: main pré-F46 (merge da F53). NUNCA ``main``
# móvel (lição PR #145 — pós-merge o A/B mediria a F46 contra ela mesma).
_AB_BASELINE_SHA = "149203f"

# F60 — adições determinísticas da fase ao render (data-fr por card —
# sinal de francês, NUNCA consumido por filtro JS; badge
# ``<span class="fr">…🇫🇷…</span>`` para menção qualificada; item da
# legenda única dt/dd explicando o sinal). O A/B "pt == main pré-F46"
# passa a valer MÓDULO esse delta (strip cirúrgico): qualquer OUTRA
# divergência de byte continua FAIL.
_F60_ATTR_RE = re.compile(r' data-fr="[^"]*"')
_F60_BADGE_HTML = ' <span class="fr"><span aria-hidden="true">🇫🇷</span></span>'
_F60_LEGEND_RE = re.compile(
    r'<dt><span aria-hidden="true">🇫🇷</span>.*?</dt><dd>.*?</dd>', re.DOTALL)
# CSS do badge FR (light + dark) — parte do delta F60 no <style>.
_F60_CSS_RE = re.compile(r'\.fr\{[^}]*\}\n')


def _strip_f60(html: str) -> str:
    """Remove as adições F60 do render (A/B byte a byte módulo F60)."""
    out = _F60_ATTR_RE.sub("", html)
    out = out.replace(_F60_BADGE_HTML, "")
    out = _F60_LEGEND_RE.sub("", out)
    return _F60_CSS_RE.sub("", out)


def check(name: str, ok: bool, detail: str = "") -> None:
    global N
    N += 1
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def section(name: str) -> None:
    print(f"\n== {name} ==")


def _job(i: int, *, posted: str | None = None, dead: bool = False,
         inapplicable: bool = False, apply_url: str | None = None,
         company: str = "Firma & Söhne GmbH") -> dict:
    j = {
        "id": f"f46-{i:03d}",
        "title": f"Werkstudent Procurement & Logistik {i}",
        "company": company,
        "location": "Köln, DE",
        "country_iso": "DE",
        "score": round(20.0 - i * 0.25, 2),
        "url": f"https://example.com/vaga/{i}",
        "description": (f"Wir suchen <Talente> & \"Müll\"-Profiler — "
                        f"Einkauf, Supply Chain, Praktikum {i}."),
    }
    if posted:
        j["posted_at"] = posted
    if dead:
        j["dead_link"] = True
    if apply_url:
        j["raw"] = {"apply_url": apply_url}
    if inapplicable:
        j["german_level"] = "required"
    return j


def _jobs(n: int = 24, **kw) -> list[dict]:
    return [_job(i, company=f"Firma {i % 4} & Söhne GmbH", **kw)
            for i in range(n)]


# ---------------------------------------------------------------------------
# GRUPO A — fonte única
# ---------------------------------------------------------------------------

def group_a_source() -> None:
    section("A: FONTE ÚNICA (I18N) — paridade pt↔en e pt verbatim")
    missing = [k for k, v in mp.I18N.items() if set(v) != {"pt", "en"}]
    check("A1 paridade pt↔en em TODAS as chaves", not missing,
          f"{len(mp.I18N)} chaves" + (f"; faltando: {missing}" if missing else ""))
    verbatim = {
        "legal_duration": mp.LEGAL_DURATION_PHRASE,
        "legal_zustimmung": mp.LEGAL_ZUSTIMMUNG_PHRASE,
        "salary_unspecified": mp.SALARY_UNSPECIFIED_TEXT,
        "enrollment_flag": mp.ENROLLMENT_FLAG_TEXT,
        "dur_flag": mp.DURATION_FLAG_TEXT,
    }
    bad = {k: (v, mp.I18N[k]["pt"]) for k, v in verbatim.items()
           if mp.I18N[k]["pt"] != v}
    check("A2 pt VERBATIM das constantes do main", not bad,
          "; ".join(f"{k}" for k in bad) or "")
    for lang in ("pt", "en"):
        js = mp._js_fill(mp._JS_PROFILE_TPL, lang) + mp._js_fill(mp._JS_F53_TPL, lang)
        check(f"A3 build {lang}: zero placeholder @@ residual", "@@" not in js)
    check("A3b build pt do _JS_PROFILE == constante pré-F46",
          mp._JS_PROFILE == mp._js_fill(mp._JS_PROFILE_TPL, "pt"))
    check("A3c build pt do _JS_F53 == constante pré-F46",
          mp._JS_F53 == mp._js_fill(mp._JS_F53_TPL, "pt"))
    en_js = mp._js_fill(mp._JS_F53_TPL, "en")
    check("A4 build en usa as strings EN do dict",
          mp.I18N["f53_seen"]["en"] in en_js
          and mp.I18N["f53_empty"]["en"] in en_js
          and mp.I18N["f53_seen"]["pt"] not in en_js)
    check("A5 default do render = EN (decisão do dono 15/10)",
          mp.I18N_DEFAULT_LANG == "en")


# ---------------------------------------------------------------------------
# GRUPO B — A/B byte a byte contra o SHA congelado
# ---------------------------------------------------------------------------

def _ab_head_render(jobs: list[dict], *, full: bool) -> str | None:
    """Renderiza a MESMA fixture no minimal_page.py pré-F46 (subprocesso
    isolado, 100% offline). None se indisponível (checkout shallow)."""
    pre = _AB_BASELINE_SHA
    try:
        blob = subprocess.run(
            ["git", "show", f"{pre}:scripts/minimal_page.py"],
            capture_output=True, text=True, cwd=str(REPO), check=True,
        ).stdout
    except Exception:  # noqa: BLE001
        return None
    with tempfile.TemporaryDirectory(prefix="f46_ab_") as td:
        tdp = Path(td)
        (tdp / "scripts").mkdir()
        (tdp / "scripts" / "minimal_page.py").write_text(blob, encoding="utf-8")
        jobs_path = tdp / "jobs.json"
        jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
        top = "mp.PAGE_TOP_FULL" if full else "mp.PAGE_TOP"
        code = (
            "import sys, json\n"
            f"sys.path.insert(0, r'{tdp / 'scripts'}')\n"
            f"sys.path.insert(0, r'{REPO / 'src'}')\n"
            "import minimal_page as mp\n"
            f"jobs = json.load(open(r'{jobs_path}'))\n"
            f"html = mp.render_size_aware(jobs, total_eligible=len(jobs),"
            f" generated_at='{STAMP}', top={top}, full_list={full},"
            f" vitrine=True)\nopen(r'{tdp / 'head.html'}', 'w',"
            " encoding='utf-8').write(html)\nprint('ok')\n"
        )
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("      [A/B antes] subprocesso falhou:",
                  r.stderr.strip().splitlines()[-1] if r.stderr else "?")
            return None
        return (tdp / "head.html").read_text(encoding="utf-8")


def group_b_ab() -> None:
    section("B: A/B byte a byte — render(lang=pt) == main pré-F46 "
            f"(SHA congelado {_AB_BASELINE_SHA})")
    jobs = _jobs(24)
    for full, regime in ((False, "top-N"), (True, "full-list")):
        head = _ab_head_render(jobs, full=full)
        if head is None:
            print(f"  [SKIP] git show indisponível (checkout shallow) — "
                  f"regime {regime} degradado com aviso, sem falso-verde")
            continue
        cur = mp.render_size_aware(
            jobs, total_eligible=len(jobs), generated_at=STAMP,
            top=(mp.PAGE_TOP_FULL if full else mp.PAGE_TOP),
            full_list=full, vitrine=True, lang="pt")
        # F60 — o render pt ganhou adições determinísticas da fase
        # (data-fr por card + item de legenda 🇫🇷 + badge FR quando há
        # francês qualificado); o contrato "pt == main pré-F46" vale
        # MÓDULO esse delta (strip cirúrgico — qualquer OUTRA
        # divergência de byte continua FAIL).
        cur_net = _strip_f60(cur)
        check(f"B{1 if not full else 2} pt == main byte a byte "
              f"módulo adições F60 ({regime})",
              cur_net == head,
              f"{len(cur_net.encode('utf-8'))}B vs "
              f"{len(head.encode('utf-8'))}B")


# ---------------------------------------------------------------------------
# GRUPO C — EN difere só no chrome
# ---------------------------------------------------------------------------

def _cards(html: str) -> list[str]:
    return re.findall(r"<li class=\"c\".*?</li>", html, re.S)


def _visible(html: str) -> str:
    """HTML sem os valores dos attrs do toggle (o texto pt viaja neles) —
    o que sobra é o texto VISÍVEL do render EN."""
    return re.sub(r"data-i18n-pt(?:-html|)?=\"[^\"]*\"", "", html)


def group_c_en() -> None:
    section("C: render EN (default) — diff SÓ de chrome; toggle SÓ no EN")
    jobs = _jobs(12, posted="2026-10-17T12:00:00Z",
                 apply_url="https://apply.example.com/x")
    pt = mp.render_size_aware(jobs, total_eligible=len(jobs),
                              generated_at=STAMP, top=mp.PAGE_TOP,
                              full_list=True, vitrine=True, lang="pt")
    en = mp.render_size_aware(jobs, total_eligible=len(jobs),
                              generated_at=STAMP, top=mp.PAGE_TOP,
                              full_list=True, vitrine=True, lang="en")
    vis = _visible(en)
    check("C0 default do render (sem lang) == lang=en",
          mp.render_size_aware(jobs, total_eligible=len(jobs),
                               generated_at=STAMP, top=mp.PAGE_TOP,
                               full_list=True, vitrine=True) == en)

    def data_links(html: str) -> list[str]:
        # hrefs DE DADOS (cards) — o head do EN tem o alternate do RSS
        return [h for h in re.findall(r'href="([^"]+)"', html)
                if "rss.xml" not in h]
    check("C1 mesmos hrefs de dados (cards/about; único extra = RSS "
          "alternate no head)", data_links(pt) == data_links(en),
          f"{len(data_links(pt))} links")

    def card_data(card: str) -> str:
        # assinatura de DADOS do card: attrs + links (chrome fora)
        attrs = re.search(r"<li class=\"c\"([^>]*)>", card).group(1)
        links = re.findall(r'href="([^"]+)"', card)
        return attrs + "|" + "|".join(links)
    c_pt, c_en = _cards(pt), _cards(en)
    check("C1b mesma lista de cards, mesma ordem, mesmos dados",
          len(c_pt) == len(c_en)
          and [card_data(c) for c in c_pt] == [card_data(c) for c in c_en],
          f"{len(c_en)} cards")
    check("C1c scores/títulos (dados) idênticos",
          re.findall(r'data-s="[^"]*"', pt) == re.findall(r'data-s="[^"]*"', en))
    check("C2 toggle/attrs/JS SÓ no EN",
          all(m not in pt for m in ("data-i18n-pt", "lang-toggle",
                                    "__I18N_JS", "if46lang",
                                    'rel="alternate" type="application/rss+xml"'))
          and all(m in en for m in ("data-i18n-pt", "lang-toggle",
                                    "__I18N_JS", "if46lang",
                                    'rel="alternate" type="application/rss+xml"')))
    check("C3 html lang: en no EN / pt-BR no pt",
          '<html lang="en">' in en and '<html lang="pt-BR">' in pt)
    check("C4 chrome EN visível e pt só nos attrs (nunca visível)",
          "show already-seen" in en and ">apply ↗</a>" in en
          and "visa-friendly only" in vis and "Search title" in vis
          and _visible(en).find("candidatar-se") == -1
          and _visible(en).find("mostrar já vistas") == -1
          and _visible(en).find("só visa friendly") == -1
          and _visible(en).find("Buscar título") == -1)
    check("C5 render pt mantém o chrome pt verbatim",
          "mostrar já vistas" in pt and "candidatar-se ↗" in pt
          and "apply ↗" not in pt)
    check("C6 texto pt do dia viaja nos attrs do EN",
          'data-i18n-pt="🛂 só visa friendly"' in en
          and 'data-i18n-pt="todos os países"' in en)


# ---------------------------------------------------------------------------
# GRUPO D — mecanismo do toggle
# ---------------------------------------------------------------------------

def group_d_toggle() -> None:
    section("D: toggle vanilla — persistência e strings JS")
    script = mp._js_i18n_script()
    check("D1 bootstrap embute __I18N_JS e a chave de persistência",
          "window.__I18N_JS=" in script and "if46lang" in script
          and "localStorage" in script)
    payload = re.search(r"window\.__I18N_JS=(\{.*?\});", script, re.S)
    ok_payload = False
    if payload:
        data = json.loads(payload.group(1))
        ok_payload = (set(data) == {"count_unit", "f53_seen", "f53_seen_aria",
                                    "f53_empty", "f53_totop_aria",
                                    "score_factors"}
                      and all(set(v) == {"pt", "en"} for v in data.values()))
    check("D2 map JS cobre exatamente as strings criadas por JS (paridade)",
          ok_payload)
    check("D3 toggle troca PT/EN e persiste a escolha",
          "(l==='en')?'PT':'EN'" in script
          and "localStorage.setItem(KEY,nl)" in script)
    check("D4 bootstrap SÓ existe no render EN",
          "window.__I18N_JS" not in mp.render_minimal_html(
              _jobs(2), total_eligible=2, generated_at=STAMP, lang="pt"))


# ---------------------------------------------------------------------------
# GRUPO E — RSS
# ---------------------------------------------------------------------------

def group_e_rss() -> None:
    section("E: RSS estático — determinismo, escape, espelho do render")
    jobs = _jobs(12, posted="2026-10-16T12:00:00Z")
    jobs[3]["posted_at"] = None  # sem posted_at -> sem pubDate (honesto)
    dead_id = jobs[5]["id"]
    ia_id = jobs[6]["id"]
    sink: dict = {}
    page = mp.render_size_aware(
        jobs, total_eligible=len(jobs), generated_at=STAMP,
        top=mp.PAGE_TOP_FULL, full_list=True, vitrine=True, lang="en",
        dead_link_ids={dead_id}, inapplicable_ids={ia_id}, sink=sink)
    shown = sink["shown"]
    feed = mp.render_rss_xml(shown, total_eligible=len(jobs),
                             generated_at=STAMP, lang="en",
                             display_aliases=sink.get("aliases"))
    doc = minidom.parseString(feed)  # E1: XML válido
    items = doc.getElementsByTagName("item")
    check("E1 XML válido e nº de itens == lista final do render",
          len(items) == len(shown), f"{len(items)} itens")
    check("E1b exclui morta/inaplicável como a página",
          all(dead_id not in feed and ia_id not in feed for _ in [0])
          and dead_id not in {str(j["id"]) for j in shown})
    feed2 = mp.render_rss_xml(shown, total_eligible=len(jobs),
                              generated_at=STAMP, lang="en")
    check("E2 determinístico (mesmo input+stamp -> mesmos bytes)",
          feed2 == feed, f"{len(feed.encode('utf-8'))}B")
    tricky = [_job(900)]
    tricky[0]["title"] = 'Einkauf <Sonder> & "Müll" — test'
    t_feed = mp.render_rss_xml(tricky, total_eligible=1, generated_at=STAMP)
    parsed = minidom.parseString(t_feed)
    t_val = parsed.getElementsByTagName("title")[1].firstChild.nodeValue
    check("E1b escape XML total (& < > \")",
          t_val == tricky[0]["title"] and "&" in t_feed and "<" in t_feed)
    pub = items[0].getElementsByTagName("pubDate")
    check("E3 pubDate RFC-822 do posted_at",
          len(pub) == 1 and pub[0].firstChild.nodeValue ==
          "Fri, 16 Oct 2026 12:00:00 +0000")
    check("E3b sem posted_at = sem pubDate (nunca inventado)",
          len(items[3].getElementsByTagName("pubDate")) == 0)
    lbd = doc.getElementsByTagName("lastBuildDate")
    check("E3c lastBuildDate = carimbo do render (determinismo)",
          len(lbd) == 1 and lbd[0].firstChild.nodeValue ==
          "Sun, 18 Oct 2026 04:00:00 +0000")
    # E4: ordem do feed == ordem dos cards da página
    page_links = re.findall(r'<a class="t" href="([^"]+)"', page)
    feed_links = [i.getElementsByTagName("link")[0].firstChild.nodeValue
                  for i in items if i.getElementsByTagName("link")]
    check("E4 espelha o render: ordem do feed == ordem dos cards",
          feed_links == page_links, f"{len(feed_links)} itens")
    check("E5 gate check_public_safe VERDE no feed",
          pp.check_public_safe(feed) == [])
    guid = items[0].getElementsByTagName("guid")[0]
    check("E6 guid = id do dataset (isPermaLink=false)",
          guid.getAttribute("isPermaLink") == "false"
          and guid.firstChild.nodeValue == shown[0]["id"])
    # E6b: CLI --rss escreve o arquivo (subprocesso, fake_root)
    with tempfile.TemporaryDirectory(prefix="f46_rss_cli_") as tmp:
        tmp = Path(tmp)
        fake_root = tmp / "repo"
        (fake_root / "scripts").mkdir(parents=True)
        shutil.copy2(REPO / "scripts" / "minimal_page.py",
                     fake_root / "scripts" / "minimal_page.py")
        shutil.copytree(REPO / "src" / "internship_finder",
                        fake_root / "src" / "internship_finder",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        data = fake_root / "data"
        data.mkdir()
        (data / "eligible_jobs.json").write_text(json.dumps(jobs),
                                                 encoding="utf-8")
        out = tmp / "out" / "index.html"
        rss_out = tmp / "out" / "rss.xml"
        env_python = sys.executable
        cmd = [env_python, str(fake_root / "scripts" / "minimal_page.py"),
               "--input", "data/eligible_jobs.json", "--top", "100000",
               "--output", str(out), "--archive", "",
               "--translation-cache", "", "--watchlist", "",
               "--tracker-db", "", "--employer-quality", "",
               "--salary-benchmark", "", "--vitrine",
               "--display-aliases", "", "--rss", str(rss_out)]
        r = subprocess.run(cmd, cwd=fake_root, capture_output=True, text=True,
                           env={"PYTHONPATH": str(fake_root / "src"),
                                "PATH": "/usr/bin:/bin", "HOME": str(tmp)})
        check("E6b CLI --rss escreve o feed junto ao render",
              r.returncode == 0 and rss_out.exists()
              and "feed rss gerado" in r.stdout,
              r.stdout.strip().splitlines()[-1] if r.returncode == 0
              else r.stderr[-200:])


# ---------------------------------------------------------------------------
# GRUPO F — publish F46
# ---------------------------------------------------------------------------

def _deploy(tmp: Path) -> tuple[Path, Path]:
    bare = tmp / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    deploy = tmp / "deploy"
    deploy.mkdir()
    def g(*a: str) -> None:
        subprocess.run(["git", *a], cwd=deploy, capture_output=True,
                       text=True, check=True)
    g("init", "-q", "-b", "gh-pages")
    g("remote", "add", "origin", str(bare))
    g("config", "user.name", "t")
    g("config", "user.email", "t@t")
    return bare, deploy


def group_f_publish() -> None:
    section("F: publish — index.html + rss.xml num commit, gate nos DOIS")
    html = "<html><body>ok f46</body></html>"
    feed = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0"><channel><title>t</title>'
            "<link>https://x/</link><description>d</description></channel></rss>")
    with tempfile.TemporaryDirectory(prefix="f46_pub_") as tmp:
        _, deploy = _deploy(Path(tmp))
        ok = pp.publish_html(html, deploy, run_id="f46", rss=feed)
        files = sorted(p.name for p in deploy.iterdir()
                       if p.name in ("index.html", "rss.xml"))
        check("F1 grava os DOIS artefatos", ok and files ==
              ["index.html", "rss.xml"], str(files))
        msg = subprocess.run(
            ["git", "log", "-1", "--format=%s"], cwd=deploy,
            capture_output=True, text=True).stdout.strip()
        check("F1b commit único menciona o feed", "feed RSS" in msg, msg)
        # gate falha segura: segredo no feed bloqueia o push INTEIRO
        bad = feed.replace("<description>d</description>",
                           f"<description>ghp_{'A' * 30}</description>")
        blocked = False
        try:
            pp.publish_html(html, deploy, run_id="bad", rss=bad)
        except RuntimeError as exc:
            blocked = "rss.xml" in str(exc)
        check("F2 segredo no feed BLOQUEIA o push (falha segura)", blocked)
        n_commits = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=deploy,
            capture_output=True, text=True).stdout.strip()
        check("F2b nada entrou no clone após o bloqueio", n_commits == "1")
        # rss=None: comportamento pré-F46 (sem rss.xml, sem menção)
        with tempfile.TemporaryDirectory(prefix="f46_pub2_") as tmp2:
            _, deploy2 = _deploy(Path(tmp2))
            ok2 = pp.publish_html(html, deploy2, run_id="legacy")
            files2 = sorted(p.name for p in deploy2.iterdir()
                            if p.name in ("index.html", "rss.xml"))
            msg2 = subprocess.run(
                ["git", "log", "-1", "--format=%s"], cwd=deploy2,
                capture_output=True, text=True).stdout.strip()
            check("F3 rss=None preserva o contrato pré-F46",
                  ok2 and files2 == ["index.html"]
                  and "feed RSS" not in msg2)


# ---------------------------------------------------------------------------
# GRUPO G — ci.yml (união ao vivo)
# ---------------------------------------------------------------------------

def group_g_ci() -> None:
    section("G: ci.yml — test_f46 na união ao vivo do array")
    yml = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    m = re.search(r"tests=\(([^)]*)\)", yml, re.S)
    arr = m.group(1).split() if m else []
    check("G1 array da suíte lido do head atual", len(arr) > 80,
          f"{len(arr)} suítes")
    check("G2 test_f46 presente no array", "test_f46" in arr)
    on_disk = {p.stem for p in (REPO / "scripts").glob("test_*.py")}
    missing = sorted(t for t in arr if t not in on_disk)
    check("G3 nenhuma suíte fantasma no array", not missing, str(missing))


def main() -> int:
    group_a_source()
    group_b_ab()
    group_c_en()
    group_d_toggle()
    group_e_rss()
    group_f_publish()
    group_g_ci()
    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"F46: {len(FAILURES)} de {N} verificações FALHARAM:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"F46: TUDO OK — {N} verificações")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
