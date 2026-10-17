"""F51 — Card compacto + legenda única (details/summary) na página pública.

Trava os contratos da F51 (branch feature/f51-card-legenda):

GRUPO A — Legenda única (item 1):
  A1. <details class="legend"> presente, FECHADO por padrão, ZERO JS;
  A2. conteúdo: badges (🛂/🇩🇪/🚫/⭐/🏆/🆕/✅/🔗), *, glossário DE→EN,
      nota §16e LITERAL, explicação do score;
  A3. legenda nos DOIS regimes (top-N e full-list);
  A4. rótulo "estimativa de mercado" segue na página (F29 honesta);
  A5. frases jurídicas §16e LITERAIS;
  A6. posição: depois da barra/abas, antes da lista;
  A7. rodapé sem duplicar glossário/§16e (custo único).

GRUPO B — Salário compacto (item 2):
  B1. real: "€2.280/mês" (milhar alemão, período PT);
  B2. faixa: "€1.200–€1.400/mês";
  B3. estimado: "≈€1.507/mês*" (* -> legenda);
  B4. sem salário/estimativa: "remuneração não citada";
  B5. nunca ambos (raiz do elif, contrato F29).

GRUPO C — Idade em UM formato (item 3):
  C1. 3d/76d/2176d (nenhum formato legacy);
  C2. posted hoje -> "<1d";
  C3. >45d destaca pela CLASSE age-stale, não por texto.

GRUPO D — Badges compactos + aria-hidden (itens 4/5/7):
  D1. "🇩🇪" (sem "DE exigido"), "🔗" (sem "morta"), "🚫" (sem
      "inaplicável"), "⭐ N,N" (sem "· Kununu"), "🏆 GPTW" (sem ano);
  D2. emojis decorativos com aria-hidden="true";
  D3. ordem FIXA 🛂→🇩🇪/🚫→⭐/🏆→🆕→⏳/⚠️→✅→🔗;
  D4. linha EN (classe .en, F12) intacta;
  D5. zero title= por badge.

GRUPO E — CTA único (item 8):
  E1. apply_url == url -> SEM botão (título já é o link);
  E2. apply_url != url -> "candidatar-se";
  E3. sem apply_url -> "abrir vaga".

GRUPO F — Regimes + orçamento (itens 9/10):
  F1. formatos compactos nos 2 regimes;
  F2. top-N < 150KB (cap duro) e <= 100KB (alvo);
  F3. full-list <= cap proporcional;
  F4. A/B fixture congelada: pós-F51 MENOR que pré-F51 (main).

GRUPO G — Zero impacto no pipeline:
  G1. renderer não importa score/filters/ranking; data/ intocado.
"""

import json
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

import minimal_page as mp  # noqa: E402
from internship_finder import salary_benchmark as sb  # noqa: E402
from internship_finder import employer_quality as eq  # noqa: E402

FAILURES: list[str] = []
N = 0

REF = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
STAMP = "2026-10-16 12:00"
BM = sb.load_salary_benchmark(REPO / "config" / "salary_benchmark.json")
QM = eq.load_employer_quality(REPO / "config" / "employer_quality.json")

# Baseline CONGELADO do A/B F4/F4b: main pré-F51 (merge da F54). O código
# da F51 (card compacto) nasceu no PR #143 → main 323daf1; tudo anterior a
# ele serve como lado "antes". Pós-merge, main móvel conteria a própria
# F51 e o A/B mediria −0B (bug do CI do main em 17/10).
_AB_BASELINE_SHA = "079b13c"

DE_REQUIRED = ("Sehr gute Deutschkenntnisse in Wort und Schrift "
               "erforderlich")


def check(name: str, cond: bool, extra: str = "") -> None:
    global N
    N += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}"
          + (f" ({extra})" if extra else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


def _job(i: int, *, title="Praktikum Supply Chain", company="Acme GmbH",
         desc=None, posted="2026-10-13T00:00:00+00:00", score=10.0,
         url=None, apply_url=None, salary_raw=None, visa=True) -> dict:
    job = {
        "id": f"t{i}", "title": title, "company": company,
        "location": "Berlin, BE, DE, 10115", "country_iso": "de",
        "score": score, "url": url or f"https://jobs.example.com/{i}",
        "description": desc or ("Werkstudent Supply Chain Management "
                                "mit Fokus auf Logistik und Beschaffung. " * 8),
        "posted_at": posted,
        "raw": {},
        "visa_friendly": visa,
    }
    if apply_url is not None:
        job["raw"]["apply_url"] = apply_url
    if salary_raw is not None:
        job["raw"].update(salary_raw)
    return job


def _render(jobs, *, full=False, bm=BM, qm=QM, **kw) -> str:
    return mp.render_minimal_html(
        jobs, total_eligible=len(jobs), generated_at=STAMP,
        now_ref=REF, salary_benchmark_map=bm, quality_map=qm,
        full_list=full,
        profile_maps=mp._profile_maps(jobs) if full else None,
        **kw)


def _card(html: str, jid: str) -> str:
    """Card identificado pela URL (única por fixture). O _job constrói
    id=t<i> com url=.../{i} — a âncora é o sufixo numérico do id."""
    num = jid[1:] if jid.startswith("t") else jid
    href = f'href="https://jobs.example.com/{num}"'
    k = html.find(href)
    if k < 0:
        raise AssertionError(f"card {jid} não encontrado (href ausente)")
    start = html.rfind("<li", 0, k)
    end = html.find("</li>", k)
    return html[start:end + len("</li>")]


def _badge_zone(html: str, jid: str) -> str:
    card = _card(html, jid)
    i = card.find('class="t"')
    j = card.find('<div class="m">')
    return card[i:j if j > 0 else len(card)]


# ---------------------------------------------------------------------------
# A — Legenda única
# ---------------------------------------------------------------------------

def group_a_legend() -> None:
    section("A: legenda única (details/summary, zero JS)")
    jobs = [_job(1), _job(2, company="Bravo SE")]
    html = _render(jobs)
    check("A1 <details class=\"legend\"> presente, FECHADO",
          '<details class="legend"><summary>' in html
          and '<details class="legend" open' not in html)
    zone = html.split("</details>")[0]
    for needle, name in (
        ("🛂", "badge 🛂 explicado"),
        ("🇩🇪", "badge 🇩🇪 explicado"),
        ("🚫", "badge 🚫 explicado"),
        ("Kununu", "badge ⭐ explicado"),
        ("Great Place to Work", "badge 🏆 explicado"),
        ("🆕", "badge 🆕 explicado"),
        ("✅", "badge ✅ (tracker) explicado"),
        ("🔗", "badge 🔗 explicado"),
        ("§16e", "nota §16e na legenda"),
        ("Glossário DE→EN", "glossário na legenda"),
        ("política de visto", "semântica do 🛂"),
        ("decaimento por idade", "score explicado"),
        ("f36_non_de_profile.md", "link docs do perfil EU"),
    ):
        check(f"A2 {name}", needle in zone)
    full = _render(jobs, full=True)
    check("A3 legenda no regime full-list",
          '<details class="legend"><summary>' in full)
    check("A4 rótulo 'estimativa de mercado' na legenda (F29)",
          "estimativa de mercado" in zone)
    check("A4b <dt>*</dt> explica o asterisco",
          "<dt>*</dt>" in zone)
    check("A5 frase §16e duração LITERAL",
          mp.LEGAL_DURATION_PHRASE in html)
    check("A5b frase §16e Zustimmung LITERAL",
          mp.LEGAL_ZUSTIMMUNG_PHRASE in html)
    check("A6 legenda após a barra, antes da lista",
          html.index('<div class="bar">')
          < html.index('<details class="legend">')
          < html.index('<ol id="list">'))
    tail = html.split('<p class="f">')[1]
    check("A7 rodapé sem glossário/§16e duplicados",
          "Glossário" not in tail and "§16e" not in tail)


# ---------------------------------------------------------------------------
# B — Salário compacto
# ---------------------------------------------------------------------------

def group_b_salary() -> None:
    section("B: salário compacto (real + estimado)")
    real = _job(10, salary_raw={"salary_min": 2280, "salary_max": 2280,
                                "salary_currency": "EUR",
                                "salary_period": "month"})
    html = _render([real])
    check("B1 real €2.280/mês", "€2.280/mês" in html)
    check("B1b formato legacy €2280/month ausente",
          "€2280" not in html and "/month" not in html)
    faixa = _job(11, salary_raw={"salary_min": 1200, "salary_max": 1400,
                                 "salary_currency": "EUR",
                                 "salary_period": "month"})
    check("B2 faixa €1.200–€1.400/mês",
          "€1.200–€1.400/mês" in _render([faixa]))
    est = _job(12)  # sem salário citado; categoria praktikum derivável
    html_e = _render([est])
    check("B3 estimado ≈€1.507/mês*", "≈€1.507/mês*" in html_e)
    check("B3b linha longa 'estimativa de mercado: ~' fora do card",
          "estimativa de mercado: ~" not in html_e)
    check("B5 nunca ambos (real -> sem ≈)", "≈€" not in html)
    ns = _job(13, title="Fachkraft Lager")  # categoria não derivável
    check("B4 sem salário/estimativa -> 'remuneração não citada'",
          mp.SALARY_UNSPECIFIED_TEXT in _render([ns]))


# ---------------------------------------------------------------------------
# C — Idade em UM formato
# ---------------------------------------------------------------------------

def group_c_age() -> None:
    section("C: idade em UM formato")
    html_all = ""
    for days, expected in ((3, "3d"), (76, "76d"), (2176, "2176d")):
        posted = (REF - timedelta(days=days)).isoformat()
        html = _render([_job(20 + days, posted=posted)])
        html_all += html
        check(f"C1 {days} dias -> '{expected}'", f">{expected}<" in html)
    check("C1b nenhum formato legacy ('há Nd'/'postada há N dias')",
          "há " not in html_all.replace("há 1", "X")  # glossário pt ok
          and "postada há" not in html_all)
    html_h = _render([_job(29, posted=REF.isoformat())])
    check("C2 posted hoje -> <1d (escaped)",
          (mp._esc("<1d") + "<") in html_h)
    old = _job(30, posted=(REF - timedelta(days=76)).isoformat())
    html_o = _render([old])
    check("C3 >45d destaca pela CLASSE age-stale",
          'class="age age-stale"' in html_o)
    check("C3b texto continua '76d' (não nominal)",
          ">76d<" in html_o and "postada há" not in html_o)


# ---------------------------------------------------------------------------
# D — Badges compactos + aria-hidden + ordem fixa
# ---------------------------------------------------------------------------

def group_d_badges() -> None:
    section("D: badges compactos, aria-hidden, ordem fixa, EN intacto")
    de_job = _job(40, desc=DE_REQUIRED + ". " + "Logistik und Einkauf. " * 5)
    html = _render([de_job, _job(41)])
    check("D1 '🇩🇪' curto (sem 'DE exigido')",
          "DE exigido" not in html
          and 'aria-hidden="true">🇩🇪<' in html)
    html_d = _render([_job(42), _job(48)], dead_link_ids={"t42"})
    check("D1b '🔗' curto (sem 'morta') NOS CARDS",
          "🔗 morta" not in html_d.split('<ol id="list">')[1]
          and "🔗" in html_d)  # emoji existe (legenda) — texto "morta" não
    html_i = _render([_job(43), _job(49)], inapplicable_ids={"t43"})
    check("D1c '🚫' curto (sem 'inaplicável') NOS CARDS",
          "🚫 inaplicável" not in html_i.split('<ol id="list">')[1])
    check("D1d '⭐ N,N' sem '· Kununu'", "· Kununu" not in html)
    check("D1e '🏆 GPTW' sem ano no card",
          "GPTW 2026" not in html and "GPTW 20" not in html)
    qm_sap = {"sap": {"kununu_score": 4.0}}
    html_s = mp.render_minimal_html(
        [_job(44, company="SAP")], total_eligible=1, generated_at=STAMP,
        now_ref=REF, quality_map=qm_sap)
    check("D1f '⭐ 4,0' presente (compacto, com vírgula)",
          "⭐ 4,0" in html_s)
    qm_gptw = {"sap": {"gptw_award": 2026}}
    html_g = mp.render_minimal_html(
        [_job(45, company="SAP")], total_eligible=1, generated_at=STAMP,
        now_ref=REF, quality_map=qm_gptw)
    check("D1g '🏆 GPTW' presente (sem ano)",
          "🏆 GPTW" in html_g and "GPTW 2026" not in html_g)
    check("D2 aria-hidden no 🛂",
          'aria-hidden="true">🛂<' in html)
    # D3 — ordem fixa no card com TODOS os badges renderizáveis no top
    mega = _job(46, company="SAP",
                desc=("Dauer 8 Monate. Requirement: enrolled at a German "
                      "university. " + DE_REQUIRED + ". "
                      + "Logistik. " * 5))
    html_m = mp.render_minimal_html(
        [mega], total_eligible=1, generated_at=STAMP, now_ref=REF,
        quality_map=qm_sap, salary_benchmark_map=BM,
        new_since_ids={"t46"})
    zone = _badge_zone(html_m, "t46")
    seq = ("🛂", "🇩🇪", "⭐", "🆕", "⏳", "⚠️")
    pos = [zone.find(x) for x in seq]
    check("D3 ordem fixa 🛂→🇩🇪→⭐→🆕→⏳→⚠️",
          all(p >= 0 for p in pos) and pos == sorted(pos), str(pos))
    # 🔗/✅ ficam por último (mortos/pessoais): usa a seção 🎯, onde uma
    # vaga morta entra COM badge (radar não corta mortas do evento).
    html_r = mp.render_minimal_html(
        [_job(53)], total_eligible=1, generated_at=STAMP, now_ref=REF,
        watchlist_events=[_job(53)], dead_link_ids={"t53"})
    zone_r = _badge_zone(html_r, "t53")
    check("D3b 🔗 DEPOIS de 🛂 na ordem (seção 🎯)",
          zone_r.find("🛂") < zone_r.find("🔗") and "🔗" in zone_r)
    # D4 — linha EN (F12) intacta
    html_en = _render([_job(47, title="Praktikum im Einkauf")])
    check("D4 linha EN real (F12 intacta: 'EN: Internship im Purchasing')",
          "EN: Internship im Purchasing" in html_en
          and 'class="en"' in html_en)
    check("D4b CSS .en preservado", ".en{color:#9fb3c8" in html_en)
    # D5 — zero title= por badge
    check("D5 badges SEM title= (custo por card removido)",
          'title="Empresa com política' not in html
          and 'title="Anúncio exige' not in html
          and 'title="URL retornou' not in html
          and 'title="A descrição completa' not in html)


# ---------------------------------------------------------------------------
# E — CTA único
# ---------------------------------------------------------------------------

def group_e_cta() -> None:
    section("E: CTA único quando URLs iguais")
    same = _job(50, apply_url="https://jobs.example.com/50")
    html_s = _render([same])
    check("E1 apply_url == url -> SEM botão duplicado",
          html_s.count(">candidatar-se") == 0
          and html_s.count('class="btn"') == 0)
    diff = _job(51, apply_url="https://apply.example.com/51")
    html_d2 = _render([diff])
    check("E2 apply_url != url -> botão candidatar-se",
          html_d2.count(">candidatar-se") == 1)
    none_ = _job(52)
    html_n = _render([none_])
    check("E3 sem apply_url -> abrir vaga",
          ">abrir vaga ↗<" in html_n
          and ">candidatar-se" not in html_n)


# ---------------------------------------------------------------------------
# F — Regimes + caps + A/B
# ---------------------------------------------------------------------------

def _ab_fixture(n: int = 120, n_comp: int = 6) -> list[dict]:
    out = []
    companies = [f"Firma {c} GmbH" for c in range(n_comp)]
    for i in range(n):
        j = _job(
            i, company=companies[i % n_comp],
            score=round(20.0 - i * (0.1 if n <= 120 else 0.05), 2),
            posted=(REF - timedelta(days=i % 90)).isoformat(),
            apply_url=(f"https://apply.example.com/{i}" if i % 2 == 0
                       else None),
            salary_raw=({"salary_min": 2280, "salary_max": 2280,
                         "salary_currency": "EUR", "salary_period": "month"}
                        if i % 5 == 0 else None),
        )
        if i % 7 == 0:
            j["description"] += " Dauer 8 Monate."
        out.append(j)
    return out


def _ab_before(jobs: list[dict]) -> int | None:
    """A/B real: MESMA fixture no minimal_page.py PRÉ-F51 (subprocesso
    isolado, 100% offline), MESMA montagem (render_minimal_html com
    snippets) — comparação de regimes idênticos; o delta é a anatomia
    do card F51, não a cadeia de degradação. None se indisponível.

    O baseline é o SHA CONGELADO do main pré-F51 (merge da F54), NUNCA
    ``main`` móvel: pós-merge o main CONTÉM a F51 e o A/B compararia
    F51 com ela mesma (delta −0B determinístico — quebrou o CI do main
    em 17/10). Pré-F51 o teste é de regressão viva; pós-F51 (este SHA
    já contido), o A/B vira censo de regressão: falha só se o card
    compacto REGREDIR (pós-F51 voltar a crescer)."""
    pre = _AB_BASELINE_SHA
    try:
        blob = subprocess.run(
            ["git", "show", f"{pre}:scripts/minimal_page.py"],
            capture_output=True, text=True, cwd=str(REPO), check=True,
        ).stdout
    except Exception:  # noqa: BLE001
        return None
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        (tdp / "scripts").mkdir()
        (tdp / "scripts" / "minimal_page.py").write_text(
            blob, encoding="utf-8")
        for mod in ("employer_quality.py", "salary_benchmark.py"):
            try:
                src_blob = subprocess.run(
                    ["git", "show", f"{pre}:src/internship_finder/{mod}"],
                    capture_output=True, text=True, cwd=str(REPO),
                    check=True).stdout
            except Exception:  # noqa: BLE001
                return None
            dst = tdp / "src" / "internship_finder"
            dst.mkdir(parents=True, exist_ok=True)
            (dst / mod).write_text(src_blob, encoding="utf-8")
        jobs_path = tdp / "jobs.json"
        jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
        code = (
            "import sys, json\n"
            f"sys.path.insert(0, r'{tdp / 'scripts'}')\n"
            f"sys.path.insert(0, r'{tdp / 'src'}')\n"
            f"sys.path.insert(0, r'{REPO / 'src'}')\n"
            "import minimal_page as mp\n"
            "from internship_finder import salary_benchmark as sb\n"
            "from internship_finder import employer_quality as eq\n"
            f"bm = sb.load_salary_benchmark(r'{REPO / 'config' / 'salary_benchmark.json'}')\n"
            f"qm = eq.load_employer_quality(r'{REPO / 'config' / 'employer_quality.json'}')\n"
            f"jobs = json.load(open(r'{jobs_path}'))\n"
            "html = mp.render_minimal_html(jobs, total_eligible=len(jobs),"
            " generated_at='" + STAMP + "', salary_benchmark_map=bm,"
            " quality_map=qm, with_snippets=True, top=mp.PAGE_TOP)\n"
            "print(len(html.encode('utf-8')))\n"
        )
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("      [A/B antes] subprocesso falhou:",
                  r.stderr.strip().splitlines()[-1] if r.stderr else "?")
            return None
        try:
            return int(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None
        try:
            return int(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None


def group_f_budget() -> None:
    section("F: regimes, caps e A/B (página FICA MENOR)")
    jobs = _ab_fixture()
    html_top = mp.render_size_aware(
        jobs, total_eligible=len(jobs), generated_at=STAMP,
        salary_benchmark_map=BM, quality_map=QM, top=mp.PAGE_TOP)
    size_top = len(html_top.encode("utf-8"))
    check("F2 top-N < 150KB (cap duro)",
          size_top < mp.PAGE_HARD_CAP_BYTES, f"{size_top}B")
    check("F2b top-N <= 100KB (alvo)",
          size_top <= mp.PAGE_TARGET_BYTES, f"{size_top}B")
    html_full = mp.render_size_aware(
        jobs, total_eligible=len(jobs), generated_at=STAMP,
        salary_benchmark_map=BM, quality_map=QM, full_list=True,
        profile_maps=mp._profile_maps(jobs))
    size_full = len(html_full.encode("utf-8"))
    cap_full = mp.page_full_cap_bytes(len(jobs))
    check("F3 full-list <= cap proporcional", size_full <= cap_full,
          f"{size_full}B <= {cap_full}B")
    check("F3b legenda nos 2 regimes",
          '<details class="legend">' in html_top
          and '<details class="legend">' in html_full)
    import re as _re
    check("F1 idade 'Nd' no top-N",
          bool(_re.search(r">\d+d<", html_top)))
    check("F1b idade 'Nd' no full", ">89d<" in html_full)
    check("F1c estimativa compacta no full", "≈€1.507/mês*" in html_full
          or "≈€1.021/mês*" in html_full or "≈14–17 €/h*" in html_full)
    # F4 — A/B na mesma montagem (com snippets), fixture do tamanho da
    # produção (100 cards no top-N): o delta é a anatomia do card.
    jobs_ab = _ab_fixture(900, 150)
    html_ab = mp.render_minimal_html(
        jobs_ab, total_eligible=len(jobs_ab), generated_at=STAMP,
        salary_benchmark_map=BM, quality_map=QM, with_snippets=True,
        top=mp.PAGE_TOP)
    size_ab = len(html_ab.encode("utf-8"))
    before = _ab_before(jobs_ab)
    if before is not None:
        delta = before - size_ab
        check("F4 A/B: pós-F51 MENOR que pré-F51 (mesma montagem)",
              delta > 0, f"{before}B -> {size_ab}B (−{delta}B)")
        check("F4b economia >= 4KB na fixture produção-like",
              delta >= 4_000, f"−{delta}B")
        check("F4c A/B dentro do alvo de 100KB",
              size_ab <= mp.PAGE_TARGET_BYTES, f"{size_ab}B")
    else:
        print("  [SKIP] A/B antes indisponível — ver relatório")


# ---------------------------------------------------------------------------
# G — Zero impacto no pipeline
# ---------------------------------------------------------------------------

def group_g_pipeline() -> None:
    section("G: zero impacto no pipeline")
    src = (REPO / "scripts" / "minimal_page.py").read_text(encoding="utf-8")
    check("G1 renderer não importa score/filters/ranking",
          "import filters" not in src and "import scoring" not in src
          and "import ranking" not in src.replace("import ranking_digest", ""))


def main() -> int:
    print("F51 — card compacto + legenda única (details/summary)")
    group_a_legend()
    group_b_salary()
    group_c_age()
    group_d_badges()
    group_e_cta()
    group_f_budget()
    group_g_pipeline()
    print("\n" + "=" * 60)
    print(f"checks: {N} | falhas: {len(FAILURES)}")
    if FAILURES:
        print("FALHOU:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("OK — F51 verde")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
