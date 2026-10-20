#!/usr/bin/env python3
"""Suite F83 — superfícies públicas: RSS no README + contador de ocultas.

F83 (20/10): conectar repo↔feed↔site e explicar ao visitante o gap
721×725 — título do site = len(shown) pós-filtros do render (721);
about = elegíveis do dia (725); a diferença era invisível. Contratos:

1. CONTADOR (minimal_page.py): ``hidden = total_eligible − len(shown)``
   anexado à LINHA DO STAMP (p_line, <p class="p">) como sufixo
   ``· N oculta(s) pelos filtros`` / ``· N hidden by filters`` (i18n
   via ``_i18n_pair``, fonte única I18N["p_hidden"]), SÓ quando
   hidden > 0; display-only; adição MINÚSCULA (caps de byte respeitados).

ESTADOS, 100% OFFLINE (renders puros + leitura de README; data/
intocada; zero rede):

- A. FONTE ÚNICA: I18N["p_hidden"] com par pt/en (contrato A1 do
  test_f46) e paridade _i18n_pair (mesmos parâmetros nos 2 idiomas);
- B. hidden==0 → sufixo AUSENTE nos DOIS idiomas (pt e en; contratos
  A/B do test_f46 e C do test_f46 dependem disso — B2/full tem hidden=0);
- C. hidden>0 → PRESENTE com o número CERTO em pt E en; a história
  completa em miniatura: título "todas as 6" + about "8 eligible" +
  stamp "· 2 ocultas pelos filtros" (o cenário 721×725 da spec); no
  render EN o texto pt viaja no attr data-i18n-pt (padrão toggle F46)
  e o texto VISÍVEL é só EN;
- D. singular (hidden==1): pt "1 oculta" sem 's' (truque {s} da casa,
  padrão sweet_count), en "1 hidden by filters";
- E. regime top-N legado: cap 2/empresa esconde vagas → contador
  presente (fixture 24 jobs/4 empresas → hidden=16). trava o ramo que
  o strip F83 do test_f46 (_F83_HIDDEN_RE) exists para cobrir — B1;
- F. display-only: sink["shown"] idêntico ao universo vivo (o contador
  NÃO filtra nada), vaga morta fora da página, 2 renders = mesmos
  BYTES (determinismo — nenhum relógio além do stamp);
- G. caps de byte: página com contador ≤ page_full_cap_bytes(total)
  (o sufixo é ~26B pt / ~22B en — MINÚSCULO por construção);
- H. README (contrato LEVE de superfície): link do rss.xml presente
  junto ao bloco Live site (badges) — o feed é vivo, rel=alternate
  existe desde a F46; o README só aponta.

Uso:  python scripts/test_f83.py   (exit 0 = verde)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

import minimal_page as mp  # noqa: E402

STAMP = "2026-10-20 06:30"
FAILURES: list[str] = []
N = 0

RSS_URL = "https://rios-vini.github.io/internship-finder/rss.xml"


def check(name: str, ok: bool, detail: str = "") -> None:
    global N
    N += 1
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def section(name: str) -> None:
    print(f"\n== {name} ==")


def _job(i: int, *, company: str | None = None) -> dict:
    return {
        "id": f"f83-{i:03d}",
        "title": f"Werkstudent Procurement & Supply Chain {i}",
        "company": company or f"Firma {i % 4} & Söhne GmbH",
        "location": "Köln, DE",
        "country_iso": "DE",
        "score": round(20.0 - i * 0.25, 2),
        "url": f"https://example.com/vaga/{i}",
        "description": f"Einkauf, Supply Chain, Praktikum {i}.",
    }


def _render(jobs, *, total_eligible, lang="pt", full=True, top=None,
            dead=(), inapplicable=(), sink=None):
    return mp.render_size_aware(
        jobs, total_eligible=total_eligible, generated_at=STAMP,
        top=top if top is not None else
        (mp.PAGE_TOP_FULL if full else mp.PAGE_TOP),
        full_list=full, vitrine=True, lang=lang,
        dead_link_ids=set(dead), inapplicable_ids=set(inapplicable),
        sink=sink,
    )


def _p_element(html: str) -> str:
    """O <p class="p"> inteiro (linha do stamp) — onde o contador mora."""
    m = re.search(r'<p class="p"[^>]*>.*?</p>', html, re.S)
    return m.group(0) if m else ""


def _visible(html: str) -> str:
    """HTML sem os attrs do toggle (padrão test_f46): o texto VISÍVEL."""
    return re.sub(r'data-i18n-pt(?:-html|)?="[^"]*"', "", html)


# ---------------------------------------------------------------------------
# A — fonte única
# ---------------------------------------------------------------------------

def group_a() -> None:
    section("A: FONTE ÚNICA (I18N) — p_hidden com par pt/en e paridade")
    key = mp.I18N.get("p_hidden")
    check("A1 p_hidden existe com par pt↔en (contrato A1 do test_f46)",
          key is not None and set(key) == {"pt", "en"},
          f"chaves: {sorted(key) if key else None}")
    if not key:
        return
    check("A2 templates: pt leva {n} e {s} (plural da casa); en leva {n}",
          "{n}" in key["pt"] and "{s}" in key["pt"]
          and "{n}" in key["en"] and "{s}" not in key["en"],
          f"pt={key['pt']!r} en={key['en']!r}")
    pt, en = mp._i18n_pair("p_hidden", n=4, s="s")
    check("A3 _i18n_pair: mesmos parâmetros nos dois idiomas",
          pt == " · 4 ocultas pelos filtros"
          and en == " · 4 hidden by filters", f"pt={pt!r} en={en!r}")


# ---------------------------------------------------------------------------
# B — hidden==0 → AUSENTE
# ---------------------------------------------------------------------------

def group_b() -> None:
    section("B: hidden==0 → sufixo AUSENTE nos dois idiomas (full-list)")
    jobs = [_job(i, company=f"Firma {i % 3} GmbH") for i in range(6)]
    for lang in ("pt", "en"):
        html = _render(jobs, total_eligible=6, lang=lang)
        ok = ("oculta" not in html) and ("hidden by filters" not in html)
        check(f"B{'1' if lang == 'pt' else '2'} render {lang}: nenhum "
              f"sufixo (shown == elegíveis)", ok,
              f"{len(html.encode('utf-8'))} bytes")


# ---------------------------------------------------------------------------
# C — hidden>0 → presente, número certo, pt E en
# ---------------------------------------------------------------------------

def group_c() -> None:
    section("C: hidden>0 → presente com o número certo (história 721×725 "
            "em miniatura: título/about/stamp)")
    jobs = [_job(i, company=f"Firma {i % 4} GmbH") for i in range(8)]
    dead_id, inapp_id = jobs[2]["id"], jobs[5]["id"]
    dead_url = jobs[2]["url"]

    pt = _render(jobs, total_eligible=8, lang="pt",
                 dead={dead_id}, inapplicable={inapp_id})
    en = _render(jobs, total_eligible=8, lang="en",
                 dead={dead_id}, inapplicable={inapp_id})

    p_pt, p_en = _p_element(pt), _p_element(en)
    check("C1 pt: ' · 2 ocultas pelos filtros' na linha do stamp",
          " · 2 ocultas pelos filtros" in p_pt)
    check("C2 pt: sufixo exatamente 1× na página (nenhum eco em outro lugar)",
          pt.count(" · 2 ocultas pelos filtros") == 1)
    check("C3 pt: título mostra as EXIBIDAS (6) e about as ELEGÍVEIS (8)",
          "todas as 6 vagas do dia" in pt and "8 eligible roles today" in pt,
          "título 6 × about 8 — o gap que o contador explica")
    check("C4 en: ' · 2 hidden by filters' no texto VISÍVEL do stamp",
          " · 2 hidden by filters" in _visible(p_en))
    check("C5 en: texto pt do dia (com sufixo pt) viaja no attr data-i18n-pt",
          " · 2 ocultas pelos filtros" in p_en
          and "data-i18n-pt=" in p_en)
    check("C6 en: sufixo pt NUNCA visível no EN (só no attr)",
          "ocultas pelos filtros" not in _visible(en))


# ---------------------------------------------------------------------------
# D — singular
# ---------------------------------------------------------------------------

def group_d() -> None:
    section("D: singular (hidden==1) — pt '1 oculta' sem 's'")
    jobs = [_job(i, company=f"Firma {i % 3} GmbH") for i in range(7)]
    dead_id = jobs[3]["id"]
    pt = _render(jobs, total_eligible=7, lang="pt", dead={dead_id})
    en = _render(jobs, total_eligible=7, lang="en", dead={dead_id})
    check("D1 pt: '1 oculta pelos filtros' (singular, sem 's')",
          " · 1 oculta pelos filtros" in _p_element(pt)
          and "1 ocultas" not in pt)
    check("D2 en: '1 hidden by filters'",
          " · 1 hidden by filters" in _visible(_p_element(en)))


# ---------------------------------------------------------------------------
# E — regime top-N legado (cap 2/empresa esconde → contador presente)
# ---------------------------------------------------------------------------

def group_e() -> None:
    section("E: regime top-N legado — cap 2/empresa esconde 16 → presente")
    # 24 jobs em 4 empresas (6 cada): cap 2/empresa do top-N → 8 exibidas,
    # 16 escondidas — exatamente a fixture B1 do test_f46 (o strip
    # _F83_HIDDEN_RE lá existe PARA este ramo).
    jobs = [_job(i, company=f"Firma {i % 4} & Söhne GmbH") for i in range(24)]
    pt = _render(jobs, total_eligible=24, lang="pt", full=False)
    p = _p_element(pt)
    check("E1 top-N: ' · 16 ocultas pelos filtros' na linha do stamp",
          " · 16 ocultas pelos filtros" in p,
          "shown=8 (cap 2/empresa × 4) de 24 elegíveis")
    check("E2 top-N: rodapé honesto 'Top 8 de 24 vagas elegíveis' segue",
          "Top 8 de 24 vagas elegíveis" in pt)


# ---------------------------------------------------------------------------
# F — display-only + determinismo
# ---------------------------------------------------------------------------

def group_f() -> None:
    section("F: display-only — contador não filtra nada; determinismo")
    jobs = [_job(i, company=f"Firma {i % 4} GmbH") for i in range(8)]
    dead_id, inapp_id = jobs[2]["id"], jobs[5]["id"]
    dead_url, alive_ids = jobs[2]["url"], [j["id"] for j in jobs
                                           if j["id"] not in (dead_id, inapp_id)]
    sink: dict = {}
    pt = _render(jobs, total_eligible=8, lang="pt",
                 dead={dead_id}, inapplicable={inapp_id}, sink=sink)
    check("F1 sink['shown'] = as 6 vivas (o contador NÃO filtra nada)",
          [j["id"] for j in sink["shown"]] == alive_ids,
          f"{len(sink['shown'])} shown")
    check("F2 vaga morta fora da página (o sufixo é VERDADE)",
          dead_url not in pt)
    pt2 = _render(jobs, total_eligible=8, lang="pt",
                  dead={dead_id}, inapplicable={inapp_id})
    check("F3 determinismo: mesmo input+stamp → mesmos BYTES",
          pt == pt2, f"{len(pt.encode('utf-8'))} bytes")


# ---------------------------------------------------------------------------
# G — caps de byte
# ---------------------------------------------------------------------------

def group_g() -> None:
    section("G: caps de byte — página com contador sob o cap duro")
    jobs = [_job(i, company=f"Firma {i % 4} GmbH") for i in range(8)]
    en = _render(jobs, total_eligible=8, lang="en",
                 dead={jobs[2]["id"]}, inapplicable={jobs[5]["id"]})
    size, cap = len(en.encode("utf-8")), mp.page_full_cap_bytes(8)
    check("G1 render EN (badge+attr+contador) ≤ cap proporcional",
          size <= cap, f"{size}B ≤ {cap}B")
    sufixo_pt = " · 2 ocultas pelos filtros".encode("utf-8")
    sufixo_en = " · 2 hidden by filters".encode("utf-8")
    check("G2 adição MINÚSCULA por construção (sufixos < 40B cada)",
          len(sufixo_pt) < 40 and len(sufixo_en) < 40,
          f"pt={len(sufixo_pt)}B en={len(sufixo_en)}B")


# ---------------------------------------------------------------------------
# H — README: link do rss.xml junto ao bloco Live site
# ---------------------------------------------------------------------------

def group_h() -> None:
    section("H: README — link do feed RSS junto ao bloco Live site")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    lines = readme.splitlines()
    rss_lines = [i for i, ln in enumerate(lines, 1) if RSS_URL in ln]
    site_lines = [i for i, ln in enumerate(lines, 1)
                  if "rios-vini.github.io/internship-finder/"
                  in ln and "rss.xml" not in ln]
    check("H1 link do rss.xml presente no README",
          bool(rss_lines), f"linhas: {rss_lines}")
    if rss_lines and site_lines:
        check("H2 junto ao bloco Live site (≤ 3 linhas do badge/Link)",
              min(abs(r - s) for r in rss_lines for s in site_lines) <= 3,
              f"rss l.{rss_lines[0]} vs site l.{site_lines[0]}")


def main() -> int:
    print("F83 — superfícies públicas: RSS no README + contador de ocultas")
    group_a()
    group_b()
    group_c()
    group_d()
    group_e()
    group_f()
    group_g()
    group_h()

    print(f"\n{'=' * 60}")
    if FAILURES:
        print(f"F83: {len(FAILURES)} de {N} verificações FALHARAM:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"F83: TUDO OK — {N} verificações")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
