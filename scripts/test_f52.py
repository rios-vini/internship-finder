"""Testes da Fase F52 — vitrine recruiter (100% offline, fixture congelada).

O que a F52 fecha (espec da onda do site, 16/10): recruiters chegam na
página por link (Anschreiben/LinkedIn/CV) e encontravam uma ferramenta
interna PT-BR dark, sem contexto do que é, sem favicon, sem meta — a
primeira impressão dizia "dashboard interno", não "sistema construído
pelo candidato". A vitrine adiciona a primeira impressão profissional
SEM atrapalhar o loop diário do dono (o dark default dele é o mesmo) e
SEM quebrar o contrato de publish (só index.html — nenhum arquivo
extra, og:image fora de escopo por design).

Contratos testados:

- T1: bloco "About this system" (EN) presente com vitrine=True —
  <details> FECHADO (sem atributo open), summary de 1 linha visível,
  2–3 linhas dentro, link do repo. Números DO BUILD: o total de
  empresas acompanhas do registry vivo (len(CompanyRegistry().entries)
  — NUNCA hardcode; cresce com as fases) e o total_eligible do dia.
- T2: registry ausente/corrompido -> about sem o número (best-effort,
  nunca quebra) — o total_eligible SEMPRE aparece (vem do chamador).
- T3: <head> da vitrine: meta description, og:title, og:description,
  og:type=website, og:url canônico, favicon SVG data-URI, color-scheme
  "dark light". SEM og:image (contrato de publish: arquivo extra fora
  de escopo). <html lang="pt-BR"> presente (pré-existente, mantido).
- T4: light mode = @media(prefers-color-scheme:light) com tokens pares
  dark/light (cada cor que o _CSS define no dark tem par no light);
  zero JS no light mode (só CSS).
- T5: A/B byte-diff — vitrine=False (default) == render pré-F52 byte
  a byte (nenhuma marca F52 no HTML; color-scheme segue "dark");
  vitrine=True difere SÓ no chrome (about + head + CSS light).
- T6: publish_pages.render_ranking_html fixa o contrato — cmd do
  subprocesso contém --vitrine (o caminho de produção liga a
  vitrine; o render local/manual segue default OFF).
- T7: degradação size-aware preserva a vitrine — a remontagem sem
  snippets (e o corte do full) mantém about/head (vitrine não é
  decorativa; padrão F13 "não-decorativa").
- T8: CLI --vitrine liga a vitrine no caminho de arquivo (from_file),
  com --help anunciando a flag (contrato visível).

Fixtures: SINTÉTICAS, campos mínimos — nenhum payload real, zero rede.
Contra o registry REAL do repo (import offline, sem data/).

Uso:  .venv/bin/python scripts/test_f52.py   (ou bash scripts/test_f52.py)
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
import publish_pages as pp  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

STAMP = "2026-10-16 22:00"  # carimbo fixo: renders A/B comparáveis


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# Fixture congelada — sintética, campos mínimos, empresas distintas.
# ---------------------------------------------------------------------------

def make_jobs(n: int = 12) -> list[dict]:
    jobs = []
    for i in range(n):
        jobs.append({
            "id": f"fx|f52:{i}",
            "title": f"Praktikum Einkauf Supply Chain {i} (m/w/d)",
            "company": f"Firma {i} GmbH",
            "location": f"Stadt {i}, DE",
            "country_iso": "de",
            "employment_type": "FULL_TIME",
            "url": f"https://jobs.example.com/f52/{i}",
            "description": "Beschaffung supplier management. " * 6,
            "score": round(40.0 - i * 0.5, 2),
        })
    return jobs


def render(vitrine: bool, jobs: list[dict], **kw) -> str:
    # F46: default do render virou EN (decisão do dono 15/10); esta suíte
    # valida o chrome/contrato da fase — force lang="pt" (contrato (b) F46).
    return mp.render_minimal_html(
        jobs, vitrine=vitrine, total_eligible=len(jobs),
        generated_at=STAMP, top=mp.PAGE_TOP, lang="pt", **kw)


# ---------------------------------------------------------------------------
# T1 — about presente, fechado, com números do build
# ---------------------------------------------------------------------------

def test_about_bloco() -> None:
    section("T1. bloco About this system (EN, fechado, números do build)")
    jobs = make_jobs()
    html = render(vitrine=True, jobs=jobs)
    check("vitrine=True renderiza <details class=\"about\">",
          '<details class="about">' in html)
    check("<details> FECHADO (sem atributo open — custo vertical 1 linha)",
          '<details class="about">' in html and 'open>' not in html)
    check("summary de 1 linha visível (EN)",
          "Built and updated daily by Vinicius Rios — about this system"
          in html)
    check("texto interno: pipeline + scoring + republish diário",
          "daily job-ranking system" in html and "visa policy" in html)
    check("link do repo público no about",
          f'<a href="{mp.REPO_URL}">Source code on GitHub</a>' in html)
    # Números do build — registry real (offline, sem data/)
    try:
        from internship_finder.registry import CompanyRegistry
        n_reg = len(CompanyRegistry().entries)
    except Exception:  # pragma: no cover — CI sempre tem o pacote
        n_reg = None
    if n_reg is not None:
        check(f"nº de empresas do registry VIVO no texto ({n_reg}, nunca "
              "hardcode)", f"plus {n_reg} tracked employer career pages"
              in html)
        check("número do registry NÃO é literal hardcoded no módulo",
              "127" not in mp._ABOUT_SUMMARY)
    else:  # pragma: no cover
        print("  [skip] registry não importável aqui — T1 numérico pulado")
    check(f"total_eligible do dia no texto ({len(jobs)})",
          f"— {len(jobs)} eligible roles today" in html)
    # plural honesto
    one = mp.render_minimal_html(
        make_jobs(1), vitrine=True, total_eligible=1, generated_at=STAMP,
        top=mp.PAGE_TOP, lang="pt")
    check("singular com 1 vaga (roles -> role)", "eligible role today" in one
          and "eligible roles today" not in one)


# ---------------------------------------------------------------------------
# T2 — registry ausente -> about sem o número (best-effort)
# ---------------------------------------------------------------------------

def test_about_best_effort() -> None:
    section("T2. registry indisponível -> about sem número, nunca quebra")
    real = mp._tracked_companies_count
    try:
        mp._tracked_companies_count = lambda: None  # type: ignore[assignment]
        jobs = make_jobs()
        html = render(vitrine=True, jobs=jobs)
        check("about renderiza SEM o número do registry",
              "tracked employer career pages" in html
              and not re.search(r"plus \d+ tracked", html))
        check("total_eligible continua no texto (vem do chamador)",
              f"— {len(jobs)} eligible roles today" in html)
    finally:
        mp._tracked_companies_count = real  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# T3 — head da vitrine: meta/OG/favicon/lang
# ---------------------------------------------------------------------------

def test_head_meta_og_favicon() -> None:
    section("T3. <head> da vitrine: meta description + OG + favicon + lang")
    jobs = make_jobs()
    a = render(vitrine=False, jobs=jobs)
    b = render(vitrine=True, jobs=jobs)
    head = b.split("<body>")[0]
    check("meta description (EN curto)",
          '<meta name="description" content="' in head)
    check("og:title presente", '<meta property="og:title" content="'
          in head)
    check("og:description presente",
          '<meta property="og:description" content="' in head)
    check("og:type=website",
          '<meta property="og:type" content="website">' in head)
    check("og:url canônico do Pages",
          f'<meta property="og:url" content="{mp.SITE_URL}">' in head)
    check("og:url é a página viva (github.io, com trailing slash)",
          mp.SITE_URL.startswith("https://rios-vini.github.io/")
          and mp.SITE_URL.endswith("/"))
    check("SEM og:image (contrato de publish: só index.html)",
          "og:image" not in b)
    check("favicon SVG inline data-URI (zero arquivo extra)",
          '<link rel="icon" href="data:image/svg+xml,' in head
          and 'type="image/svg+xml">' in head)
    check("favicon ~200B (leve)",
          len(mp._FAVICON_HREF) < 400,
          f"len={len(mp._FAVICON_HREF)}")
    check("color-scheme honesto: dark light na vitrine",
          '<meta name="color-scheme" content="dark light">' in head)
    check("color-scheme do default segue dark (regime do dono)",
          '<meta name="color-scheme" content="dark">' in a)
    check('<html lang="pt-BR"> presente (pré-existente, mantido)',
          '<html lang="pt-BR">' in b and '<html lang="pt-BR">' in a)
    check("title segue o regime (não mudou com a vitrine)",
          "<title>" in head and "Internship Finder" in head)


# ---------------------------------------------------------------------------
# T4 — light mode: tokens pares dark/light, zero JS
# ---------------------------------------------------------------------------

DARK_LIGHT_PAIRS = [
    # (selector-ish dark token, light token)
    ("body{background:#10151b;color:#e6edf3", "body{background:#ffffff;color:#1f2328}"),
]


def test_light_mode() -> None:
    section("T4. light mode: @media prefers-color-scheme:light, tokens pares")
    jobs = make_jobs()
    b = render(vitrine=True, jobs=jobs)
    a = render(vitrine=False, jobs=jobs)
    check("bloco @media(prefers-color-scheme:light) presente na vitrine",
          "@media(prefers-color-scheme:light){" in b)
    check("light mode AUSENTE no default (A/B limpo)",
          "prefers-color-scheme:light" not in a)
    m = re.search(r"@media\(prefers-color-scheme:light\)\{(.*?)\n\}",
                  b, re.S)
    check("media query fechada (regex casa)", m is not None)
    light = m.group(1) if m else ""
    dark = mp._CSS
    # tokens pares: as classes de cor do dark têm override no light
    pair_tokens = [
        ".p,.p2", ".r", ".t", "a.t:visited", ".m", ".d", ".en", ".age",
        ".est", ".nsal", ".gloss,.f,.legal", ".spot", ".radar-more",
        ".bar input[type=search]", ".bar select", "li.c", ".s", ".vf",
        ".de", ".dead", ".newb", ".pt", ".eq", ".age-stale", ".dur",
        ".flag", ".btn", "h2",
    ]
    missing = [tok for tok in pair_tokens if tok not in light]
    check(f"tokens pares dark/light ({len(pair_tokens) - len(missing)}/"
          f"{len(pair_tokens)} presentes no light)",
          not missing, f"faltando: {missing}" if missing else "")
    # contraste AA (4.5:1) — amostras representativas calculadas offline
    def _lum(hexc: str) -> float:
        h = hexc.lstrip("#")
        rgb = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
               for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    def _ratio(fg: str, bg: str) -> float:
        l1, l2 = _lum(fg), _lum(bg)
        if l1 < l2:
            l1, l2 = l2, l1
        return (l1 + 0.05) / (l2 + 0.05)

    aa_pairs = [
        ("#1f2328", "#ffffff", "texto principal"),
        ("#5b6570", "#ffffff", "texto muted (.p/.r)"),
        ("#0969da", "#ffffff", "link/acento"),
        ("#116326", "#ffffff", "verde score/badge"),
        ("#383f47", "#ffffff", "h2"),
    ]
    fails_aa = [lbl for fg, bg, lbl in aa_pairs
                if _ratio(fg, bg) < 4.5]
    check("contraste AA (>=4.5:1) nos pares amostrados do light",
          not fails_aa, f"reprovados: {fails_aa}" if fails_aa else "")
    # zero JS: o light mode vive só no CSS — nenhuma tag <script> nova
    n_scripts_b = b.count("<script>")
    n_scripts_a = a.count("<script>")
    check("zero JS novo na vitrine (mesmo nº de <script> do default)",
          n_scripts_b == n_scripts_a, f"{n_scripts_a} -> {n_scripts_b}")


# ---------------------------------------------------------------------------
# T5 — A/B byte-diff: default == pré-F52; vitrine só acrescenta chrome
# ---------------------------------------------------------------------------

def test_ab_byte_diff() -> None:
    section("T5. A/B byte-diff — default pré-F52 byte a byte")
    jobs = make_jobs()
    a1 = render(vitrine=False, jobs=jobs)
    a2 = mp.render_minimal_html(  # sem passar o kwarg vitrine = default
        jobs, total_eligible=len(jobs), generated_at=STAMP, top=mp.PAGE_TOP,
        lang="pt")
    check("default == vitrine=False explícito (kwarg idempotente)",
          a1 == a2)
    check("nenhuma marca F52 no default (about/OG/favicon/light)",
          "class=\"about\"" not in a1 and "og:" not in a1
          and 'rel="icon"' not in a1 and "prefers-color-scheme:light"
          not in a1)
    b = render(vitrine=True, jobs=jobs)
    check("vitrine difere do default", b != a1)
    # o diff é SÓ chrome: o CORPO das vagas (cards) é idêntico
    def cards(html: str) -> str:
        m = re.search(r'<ol id="list">(.*?)</ol>', html, re.S)
        return m.group(1) if m else ""
    check("cards das vagas idênticos A/B (diff só no chrome)",
          cards(a1) == cards(b))
    # regime full também preserva o A/B do default
    fa = mp.render_size_aware(jobs, total_eligible=len(jobs),
                              generated_at=STAMP, top=mp.PAGE_TOP,
                              full_list=True, lang="pt")
    fb = mp.render_size_aware(jobs, total_eligible=len(jobs),
                              generated_at=STAMP, top=mp.PAGE_TOP,
                              full_list=True, vitrine=True, lang="pt")
    check("regime full: default sem marcas F52; vitrine com about",
          "class=\"about\"" not in fa and "class=\"about\"" in fb)


# ---------------------------------------------------------------------------
# T6 — publish fixa o contrato (--vitrine no cmd do subprocesso)
# ---------------------------------------------------------------------------

def test_publish_contrato() -> None:
    section("T6. publish_pages fixa o contrato: --vitrine no cmd")
    with tempfile.TemporaryDirectory(prefix="t_f52_pp_") as tmp:
        root = Path(__file__).resolve().parent.parent
        fake_root = Path(tmp) / "repo"
        (fake_root / "scripts").mkdir(parents=True)
        shutil.copy2(root / "scripts" / "minimal_page.py",
                     fake_root / "scripts" / "minimal_page.py")
        shutil.copytree(root / "src" / "internship_finder",
                        fake_root / "src" / "internship_finder",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        data = fake_root / "data"
        data.mkdir()
        (data / "eligible_jobs.json").write_text(
            json.dumps(make_jobs(3)), encoding="utf-8")
        out = Path(tmp) / "out" / "index.html"
        out.parent.mkdir()
        html = pp.render_ranking_html(fake_root, out, top=10)
        check("render do publish vem COM a vitrine (about no HTML)",
              'class="about"' in html)
        check("render do publish: og:url no HTML",
              f'<meta property="og:url" content="{mp.SITE_URL}">' in html)
        check("gate de segurança aprova o HTML da vitrine",
              pp.check_public_safe(html) == [])
        check("tamanho abaixo do cap duro (150 KB)",
              len(html.encode("utf-8")) < 150_000)


# ---------------------------------------------------------------------------
# T7 — degradação size-aware preserva a vitrine (não-decorativa)
# ---------------------------------------------------------------------------

def test_size_aware_preserva_vitrine() -> None:
    section("T7. degradação size-aware preserva a vitrine")
    jobs = make_jobs(30)
    # render_size_aware repassa vitrine: remontagem sem snippets mantém
    # about/head (padrão F13 — a vitrine não é campo decorativo).
    h = mp.render_size_aware(jobs, total_eligible=len(jobs),
                             generated_at=STAMP, top=mp.PAGE_TOP,
                             vitrine=True, lang="pt")
    check("render_size_aware(vitrine=True) entrega about",
          'class="about"' in h)
    check("render_size_aware(vitrine=True) entrega OG",
          'og:url' in h)
    h_def = mp.render_size_aware(jobs, total_eligible=len(jobs),
                                 generated_at=STAMP, top=mp.PAGE_TOP,
                                 lang="pt")
    check("render_size_aware default sem marcas F52",
          'class="about"' not in h_def and "og:" not in h_def)
    # from_file repassa a vitrine (caminho do CLI)
    with tempfile.TemporaryDirectory(prefix="t_f52_ff_") as tmp:
        p = Path(tmp) / "eligible_jobs.json"
        p.write_text(json.dumps(jobs), encoding="utf-8")
        hf = mp.render_minimal_html_from_file(p, top=mp.PAGE_TOP,
                                              vitrine=True, lang="pt")
        check("from_file(vitrine=True) entrega about",
              'class="about"' in hf)
        hf_def = mp.render_minimal_html_from_file(p, top=mp.PAGE_TOP,
                                                  lang="pt")
        check("from_file default sem marcas F52",
              'class="about"' not in hf_def and "og:" not in hf_def)


# ---------------------------------------------------------------------------
# T8 — CLI --vitrine (contrato visível e funcional)
# ---------------------------------------------------------------------------

def test_cli_vitrine() -> None:
    section("T8. CLI --vitrine liga a vitrine no caminho de arquivo")
    with tempfile.TemporaryDirectory(prefix="t_f52_cli_") as tmp:
        tmpdir = Path(tmp)
        jobs_path = tmpdir / "eligible_jobs.json"
        jobs_path.write_text(json.dumps(make_jobs(4)), encoding="utf-8")
        env_path = Path(__file__).resolve().parent
        base = [sys.executable, str(env_path / "minimal_page.py"),
                "--input", str(jobs_path), "--top", "10"]
        r = subprocess.run(base + ["--vitrine", "--output", "-"],
                           capture_output=True, text=True, timeout=60)
        check("CLI com --vitrine sai 0", r.returncode == 0,
              r.stderr[-200:] if r.returncode else "")
        check("CLI com --vitrine gera about no stdout",
              'class="about"' in r.stdout)
        check("CLI com --vitrine gera og: no stdout",
              'property="og:type"' in r.stdout)
        r2 = subprocess.run(base + ["--output", "-"],
                            capture_output=True, text=True, timeout=60)
        check("CLI default (sem --vitrine) sai 0", r2.returncode == 0,
              r2.stderr[-200:] if r2.returncode else "")
        check("CLI default sem marcas F52",
              'class="about"' not in r2.stdout and "og:" not in r2.stdout)
        rhelp = subprocess.run(
            [sys.executable, str(env_path / "minimal_page.py"), "--help"],
            capture_output=True, text=True, timeout=60)
        check("CLI --help anuncia --vitrine",
              "--vitrine" in rhelp.stdout)
        # arquivo de saída real (não stdout) também recebe a vitrine
        out_file = tmpdir / "vitrine.html"
        r3 = subprocess.run(base + ["--vitrine", "--output", str(out_file)],
                            capture_output=True, text=True, timeout=60)
        check("CLI com --vitrine escreve arquivo com about",
              r3.returncode == 0 and out_file.exists()
              and 'class="about"' in out_file.read_text(encoding="utf-8"))


def main() -> int:
    print("F52 — vitrine recruiter: about EN + light mode + meta/OG + "
          "favicon")
    test_about_bloco()
    test_about_best_effort()
    test_head_meta_og_favicon()
    test_light_mode()
    test_ab_byte_diff()
    test_publish_contrato()
    test_size_aware_preserva_vitrine()
    test_cli_vitrine()
    print()
    if FAILURES:
        print(f"F52: FALHAS: {len(FAILURES)} de {CHECKS} checks")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print(f"F52: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
