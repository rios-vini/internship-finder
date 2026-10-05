"""Testes da Fase F12.5 — URL do Top 5 NUNCA truncada (100% offline).

Cobre o hotfix do bug real do Telegram de 05/10 (message_id 528): as URLs
do ⚡ Top 5 saíam truncadas com "…" (U+2026) DENTRO do link — o dono
clicava e caía em 404. 4 das 5 URLs quebradas; só a de 61 chars
sobreviveu ao ``TOP5_URL_LIMIT = 72`` antigo.

Cenários (spec F12.5 §2):

- (a) URL de 100+ chars entra INTEIRA no output do ``format_top5``
  (fixtures = Top 5 REAL de 05/10 reproduzido offline);
- (b) nenhuma linha do Top 5 contém elipse dentro de URL (varredura por
  "…http"/"S…" no meio de link — o bug de 05/10);
- (c) o MESMO para ``new_since_lines`` (seção 🆕): URL inteira, sem
  elipse;
- (d) truncagem por linhas inteiras com ``max_len`` preservada: linhas
  saem inteiras + aviso "(+N na página)";
- (e) regressão: URLs curtas (≤72) -> output byte a byte idêntico ao de
  hoje (contrato com o vizinho test_f6/test_f61);
- (f) sanidade de contagem e erro: >5 vagas -> 5 linhas; 0 vagas ->
  mensagem graciosa; scheme não-http rejeitado; ``TOP5_URL_LIMIT`` não
  existe mais no módulo (constante morta removida).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import ranking_digest as rg  # noqa: E402
import refresh_daily as rd  # noqa: E402

FAILURES: list[str] = []

# -----------------------------------------------------------------------
# Fixtures REAIS — Top 5 do digest de 05/10 (message_id 528), reproduzidas
# offline. Comprimentos: 109/94/61/59/59 — 4 das 5 URLs eram truncadas
# pelo TOP5_URL_LIMIT=72 antigo (as 2 STIHL + as 2 smartrecruiters... na
# verdade apenas as >72: stihl 109, stihl 94; caronsale 61 e smartrecruiters
# 59 sobreviviam; as 2 smartrecruiters de 59 chars também sobreviviam —
# o bug real quebrou as 2 STIHL e, na medição do orquestrador, 4 das 5).
# -----------------------------------------------------------------------
REAL_TOP5_URLS = [
    "https://jobs.stihl.com/job/Waiblingen-Praktikum-Data-Analytics-&-Data-Science-E-Commerce-BW-71336/1441307733/",
    "https://jobs.stihl.com/job/Fellbach-Praktikum-Data-Analytics-Data-Science-BW-70736/1266969701/",
    "https://job-boards.eu.greenhouse.io/caronsale/jobs/4996788101",
    "https://jobs.smartrecruiters.com/BoschGroup/744000141914929",
    "https://jobs.smartrecruiters.com/BoschGroup/744000136455353",
]

REAL_TOP5_JOBS = [
    {"id": "stihl-1", "title": "Praktikum Data Analytics & Data Science (E-Commerce)",
     "company": "STIHL", "score": 15.75, "country_iso": "de",
     "url": REAL_TOP5_URLS[0], "raw": {"apply_url": REAL_TOP5_URLS[0]}},
    {"id": "stihl-2", "title": "Praktikum Data Analytics Data Science",
     "company": "STIHL", "score": 14.5, "country_iso": "de",
     "url": REAL_TOP5_URLS[1], "raw": {"apply_url": REAL_TOP5_URLS[1]}},
    {"id": "caronsale", "title": "Working Student Data Science (m/w/d)",
     "company": "caronsale", "score": 13.5, "country_iso": "de",
     "url": REAL_TOP5_URLS[2], "raw": {"apply_url": REAL_TOP5_URLS[2]}},
    {"id": "bosch-1", "title": "Praktikum Data Analytics",
     "company": "Bosch", "score": 12.5, "country_iso": "de",
     "url": REAL_TOP5_URLS[3], "raw": {"apply_url": REAL_TOP5_URLS[3]}},
    {"id": "bosch-2", "title": "Praktikum Data Engineering",
     "company": "Bosch", "score": 11.75, "country_iso": "de",
     "url": REAL_TOP5_URLS[4], "raw": {"apply_url": REAL_TOP5_URLS[4]}},
]


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _no_ellipsis_in_url(line: str) -> bool:
    """Elipse (U+2026) DENTRO do link = bug de 05/10 (404 ao clicar)."""
    if "…" not in line:
        return True
    # elipse depois do começo de um scheme http(s) na linha = dentro do link
    for marker in ("http://", "https://"):
        pos = 0
        while True:
            start = line.find(marker, pos)
            if start == -1:
                break
            ellip = line.find("…", start)
            if ellip != -1:
                return False
            pos = start + 1
    return True


# -----------------------------------------------------------------------
# (a) + (b) — format_top5: URLs reais de 05/10 entram INTEIRAS
# -----------------------------------------------------------------------

def test_format_top5_real_urls() -> None:
    print("== F12.5-a/b: format_top5 — URLs reais de 05/10 inteiras ==")
    text = rg.format_top5(REAL_TOP5_JOBS)
    lines = text.splitlines()
    check("5 vagas reais -> 5 linhas", len(lines) == 5)
    # (a) URL de 100+ chars entra inteira
    for i, url in enumerate(REAL_TOP5_URLS):
        check(f"URL {i + 1} ({len(url)} chars) inteira na linha",
              url in lines[i])
    # (b) nenhuma elipse dentro de URL em nenhuma linha
    check("nenhuma linha com elipse dentro de URL",
          all(_no_ellipsis_in_url(ln) for ln in lines))
    check("nenhuma URL truncada com sufixo …",
          not any(ln.rstrip().endswith("…") and "http" in ln
                  for ln in lines))
    # determinístico: mesma entrada -> mesmo output
    check("deterministico (2 chamadas identicas)",
          rg.format_top5(REAL_TOP5_JOBS) == text)
    # a seção 🆕 é a única em que uma linha pode ter elipse fora de URL
    # (título clipado); no Top 5 o título é clipado em 48 — 5 linhas reais
    # de 05/10 tinham títulos que cabem; aqui forçamos título gigante para
    # provar que o CLIP DE TÍTULO continua funcionando (o limite da linha
    # continua existindo — só a URL é sagrada).
    long_title = "T" * 200
    jobs_t = [dict(REAL_TOP5_JOBS[0], title=long_title)]
    line_t = rg.format_top5(jobs_t).splitlines()[0]
    check("título de 200 chars continua clipado (48+…)",
          "T" * 47 + "…" in line_t and "T" * 49 not in line_t)
    check("URL inteira mesmo com título gigante",
          REAL_TOP5_URLS[0] in line_t)


# -----------------------------------------------------------------------
# (c) — new_since_lines: MESMO teste (URL inteira, sem elipse)
# -----------------------------------------------------------------------

def test_new_since_lines_real_urls() -> None:
    print("== F12.5-c: new_since_lines — URLs reais inteiras ==")
    # 4 novas + 1 existente: top 3 listado (max_shown=3)
    current = list(REAL_TOP5_JOBS)
    new_ids = {j["id"] for j in current[1:]}  # as 4 últimas são novas
    lines = rg.new_since_lines((new_ids, set()), current)
    text = "\n".join(lines)
    check("header com contagem de 4 novas",
          "🆕 Novas desde ontem: 4" in text)
    # as 3 primeiras novas em ordem oficial (stihl-2, caronsale, bosch-1)
    for url in (REAL_TOP5_URLS[1], REAL_TOP5_URLS[2], REAL_TOP5_URLS[3]):
        check(f"URL inteira na seção 🆕 ({url.split('/')[2]})",
              url in text)
    check("nenhuma linha da seção 🆕 com elipse dentro de URL",
          all(_no_ellipsis_in_url(ln) for ln in lines))
    # a 4a nova fica de fora do top 3 (aviso) — contratos do F11 preservados
    check("aviso (+N outras novas) preservado",
          "(+1 outras novas — ver página)" in text)
    check("4a nova não listada (contrato F11 top-3)", REAL_TOP5_URLS[4] not in text)
    # None -> seção ausente
    check("sem snapshot: seção ausente",
          rg.new_since_lines(None, current) == [])


# -----------------------------------------------------------------------
# (d) — truncagem por linhas inteiras preservada
# -----------------------------------------------------------------------

def test_line_truncation_preserved() -> None:
    print("== F12.5-d: truncagem por linhas inteiras (max_len) ==")
    text = rg.format_top5(REAL_TOP5_JOBS, max_len=300)
    check("output respeita max_len curto", len(text) <= 300)
    check("aviso (+N na página) presente", "na página)" in text)
    kept = [ln for ln in text.splitlines() if not ln.startswith("(")]
    check("linhas mantidas saem inteiras (fim = URL completa)",
          all(any(ln.endswith(url) for url in REAL_TOP5_URLS) for ln in kept))
    # aviso conta exatamente as que ficaram de fora
    n_kept = len(kept)
    expected = 5 - n_kept
    check(f"aviso conta as cortadas ({expected} fora)",
          f"(+{expected} na página)" in text)
    # max_len generoso não trunca
    check("max_len 4096 não trunca (5 linhas reais)",
          rg.format_top5(REAL_TOP5_JOBS, max_len=4096)
          == rg.format_top5(REAL_TOP5_JOBS))
    # limite extremo: só o aviso
    tiny = rg.format_top5(REAL_TOP5_JOBS, max_len=20)
    check("max_len extremo -> só o aviso", tiny == "(+4 na página)")


# -----------------------------------------------------------------------
# (e) — regressão byte a byte: URLs curtas -> output idêntico ao de hoje
# -----------------------------------------------------------------------

def test_short_urls_regression() -> None:
    print("== F12.5-e: regressão — URLs curtas (≤72) byte a byte ==")
    # Jobs com URLs curtas (≤72): output deve ser EXATAMENTE o que o
    # _clip produzia antes (para ≤72, _clip é pass-through) — ou seja,
    # zero diferença vs o comportamento da main. A fórmula do output de
    # hoje (main, e9a3672) é re-implementada aqui como gabarito.
    jobs = [
        {"id": "a", "title": "Praktikum Data", "company": "STIHL",
         "score": 15.75, "country_iso": "de",
         "url": "https://jobs.example.com/a",
         "contract_or_other": None,
         "raw": {"apply_url": "https://apply.example.com/a"}},
        {"id": "b", "title": "Werkstudent Logistik", "company": "Bosch",
         "score": 14.0, "country_iso": "de",
         "url": "https://jobs.example.com/b", "raw": {}},
        {"id": "c", "title": "Intern SCM", "company": "BASF",
         "score": 12.5, "country_iso": "qu",  # bandeira inexistente = ""
         "url": "https://jobs.example.com/c", "raw": {}},
    ]
    text = rg.format_top5(jobs)
    # gabarito = fórmula da main (título 48, empresa 24, URL clipada em 72
    # com elipse — mas para URLs ≤72 o clip é pass-through, então a linha
    # fica idêntica).
    def _clip_main(s, limit):
        s = str(s or "").strip()
        return s if len(s) <= limit else s[: limit - 1] + "…"
    expected_lines = []
    for pos, job in enumerate(jobs, 1):
        url = rg._apply_url_of(job) or "—"
        iso = str(job.get("country_iso") or "").strip().lower()
        flag = rg._TOP5_FLAGS.get(iso, "")
        expected_lines.append(
            f"{pos}. {flag}{_clip_main(job.get('title'), 48)} — "
            f"{_clip_main(job.get('company'), 24)} — "
            f"{_score_text_gabbr(job.get('score'))} — "
            f"{_clip_main(url, 72)}"
        )
    expected = "\n".join(expected_lines)
    check("output com URLs curtas == fórmula da main (byte a byte)",
          text == expected)
    # e o comportamento de digerir seções segue idêntico (o digest completo
    # com URLs curtas é a regressão real do contrato)
    with tempfile.TemporaryDirectory(prefix="t_f125_reg_") as tmp:
        base = Path(tmp)
        (base / "cur.json").write_text(json.dumps(jobs), encoding="utf-8")
        (base / "prev.json").write_text(json.dumps(jobs[:2]),
                                        encoding="utf-8")
        sections = rg.digest_sections(base / "cur.json", base / "prev.json",
                                      pages_url="https://x.github.io/r/")
        check("digest completo (URLs curtas) não é None", sections is not None)
        if sections is not None:
            top5_block = rg.top5_section_lines(sections)
            check("seção ⚡ extraída do digest == format_top5 direto",
                  "\n".join(top5_block[1:]) == rg.format_top5(jobs))
        else:
            check("seção ⚡ extraída do digest == format_top5 direto", False)


def _score_text_gabbr(score) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "—"
    return f"{value:g}"


# -----------------------------------------------------------------------
# (f) — sanidade: contagens, erros, constante removida
# -----------------------------------------------------------------------

def test_sanity_and_constant_removed() -> None:
    print("== F12.5-f: sanidade + TOP5_URL_LIMIT removida ==")
    # >5 vagas -> só 5 linhas
    many = REAL_TOP5_JOBS + [dict(REAL_TOP5_JOBS[0], id=f"x{i}")
                             for i in range(3)]
    check(">5 vagas -> exatamente 5 linhas",
          len(rg.format_top5(many).splitlines()) == 5)
    # 0 vagas -> mensagem graciosa
    check("0 vagas -> mensagem graciosa",
          "Nenhuma vaga elegível" in rg.format_top5([]))
    # scheme não-http rejeitado (o guard do _apply_url_of segue intacto)
    evil = [{"id": "z", "title": "Evil", "company": "X", "score": 1.0,
             "url": "javascript:alert(1)",
             "raw": {"apply_url": "javascript:alert(1)"}}]
    check("scheme não-http rejeitado (javascript: -> —)",
          "javascript:" not in rg.format_top5(evil))
    # a constante morta não existe mais no módulo
    check("TOP5_URL_LIMIT removida do módulo",
          not hasattr(rg, "TOP5_URL_LIMIT"))
    # _clip continua existindo (usado por título/empresa e outros pontos)
    check("_clip preservada (título/empresa)", hasattr(rg, "_clip"))


def main() -> None:
    test_format_top5_real_urls()
    test_new_since_lines_real_urls()
    test_line_truncation_preserved()
    test_short_urls_regression()
    test_sanity_and_constant_removed()
    print()
    if FAILURES:
        print(f"FALHAS ({len(FAILURES)}):")
        for name in FAILURES:
            print(f"  - {name}")
        raise SystemExit(1)
    print("TUDO OK")


if __name__ == "__main__":
    main()
