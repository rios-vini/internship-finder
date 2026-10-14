#!/usr/bin/env python3
"""Testes da Fase F29 — sinais de candidatura no display (100% offline).

Trava o contrato da camada INFORMATIVA (nada entra em score/eligibility/
filters/ranking):

GRUPO A — Loader tolerante (salary_benchmark):
  A1. arquivo curado real do repo carrega com as 4 categorias;
  A2. arquivo ausente -> {} sem erro;
  A3. JSON corrompido -> {} sem erro;
  A4. entrada corrompida (sem text) -> sem estimativa;
  A5. job_salary presente -> NUNCA estimativa (regra inviolável).

GRUPO B — Estimativa rotulada e NUNCA fundida:
  B1. werkstudent -> linha com "14–17 €/h" rotulada;
  B2. praktikum -> linha com "€1.507/mês" rotulada;
  B3. pflichtpraktikum -> linha com "€1.021/mês";
  B4. SEMPRE contém o rótulo LITERAL "estimativa de mercado";
  B5. categoria não derivável -> '';
  B6. no card HTML: detectado presente -> SEM estimativa (nunca ambos);
  B7. no card HTML: ausente + derivável -> estimativa rotulada no card.

GRUPO C — Badge idade (item 3):
  C1. posted_at -> "postada há N dias" no card;
  C2. >45 dias -> classe age-stale (destaque discreto);
  C3. <=45 dias -> sem age-stale;
  C4. sem posted_at -> sem badge (regressão F11).

GRUPO D — Flag duração §16e (item 2):
  D1. duração citada > 6 meses -> flag literal com N;
  D2. 6 meses exatos -> SEM flag (dentro do teto);
  D3. faixa começando <= 6 (6–12) -> SEM flag;
  D4. sem duração citada -> sem flag;
  D5. job_duration ausente (import falha) -> '' best-effort.

GRUPO E — Red-flags (item 4):
  E1. "enrolled at a German university" -> badge;
  E2. "Einschreibung an einer deutschen Hochschule" -> badge;
  E3. anúncio sem matrícula exigida -> sem badge;
  E4. remuneração não citada -> badge honesto;
  E5. remuneração citada -> SEM badge (não acusa);
  E6. red-flag é INFORMATIVA: vaga flagada PERMANECE no ranking exibido.

GRUPO F — Countdown visto no digest (item 6):
  F1. linha presente ANTES do ⚡ Top 5;
  F2. texto derivado de constantes (muda o alvo -> muda a data);
  F3. visa_countdown=False -> ausente (regressão zero).

GRUPO G — Frases jurídicas LITERAIS (item 7):
  G1. página contém a frase de duração LITERAL (substring assert);
  G2. página contém a frase de Zustimmung LITERAL (substring assert);
  G3. as constantes do módulo são a fonte única (frase idêntica).

GRUPO H — Byte budget (item 8, cap do test_f6 intocável):
  H1. render com benchmark + sinais no snapshot real < 150KB;
  H2. estimativa não fere o cap: fixture extrema (todas estimativas) < cap.

GRUPO I — Zero impacto no pipeline:
  I1. nenhum arquivo de score/filters/ranking importado por F29;
  I2. id/score/ordem do ranking NÃO mudam com benchmark ligado.
"""

import json
import re
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

import minimal_page as mp  # noqa: E402
import ranking_digest as rd  # noqa: E402
from internship_finder import salary_benchmark as sb  # noqa: E402
from internship_finder import opportunity_intel as oi  # noqa: E402

FAILURES: list[str] = []
N = 0


def check(name: str, cond: bool) -> None:
    global N
    N += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _job(i: int, *, title="Praktikum Supply Chain", desc="", posted=None,
          salary_text=None, raw=None, score=10.0) -> dict:
    job = {
        "id": f"t{i}", "title": title, "company": "Acme GmbH",
        "location": "Berlin, BE, DE, 10115", "country_iso": "de",
        "score": score, "url": f"https://jobs.example.com/{i}",
        "description": desc or ("Werkstudent Supply Chain Management "
                                "mit Fokus auf Logistik. " * 10),
        "raw": dict(raw or {}),
    }
    if posted:
        job["posted_at"] = posted
    if salary_text:
        job["description"] = salary_text + " " + job["description"]
    return job


# F36 (fix da bomba-relógio da F29): o ref declarado abaixo AGORA é
# repassado ao render (param now_ref) — antes o teste só passava quando
# executado NA data 2026-10-13 (o render usava datetime.now e os checks
# C1/C3b quebravam em qualquer outro dia).
FIXED_REF = datetime(2026, 10, 13, tzinfo=UTC)


def _render(jobs, benchmark=None, **kw) -> str:
    return mp.render_minimal_html(
        jobs, total_eligible=len(jobs), generated_at="2026-10-13 09:00",
        salary_benchmark_map=benchmark, now_ref=FIXED_REF, **kw)


def group_a_loader() -> None:
    print("== A: loader tolerante do benchmark ==")
    bm = sb.load_salary_benchmark(REPO / "config" / "salary_benchmark.json")
    check("A1 arquivo real: 4 categorias",
          set(bm) == {"pflichtpraktikum", "praktikum", "werkstudent",
                      "mindestlohn_2026"})
    check("A2 arquivo ausente -> {} sem erro",
          sb.load_salary_benchmark("/nonexistent/x.json") == {})
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write("{corrompido!!")
        bad = fh.name
    check("A3 JSON corrompido -> {} sem erro", sb.load_salary_benchmark(bad) == {})
    Path(bad).unlink()
    check("A4 entrada sem text -> sem estimativa",
          sb.estimate_for_category({"praktikum": {"source": "x"}},
                                   "praktikum") is None)
    check("A4b categoria inexistente -> None",
          sb.estimate_for_category(bm, "nao_existe") is None)
    # A5 — regra inviolável: job_salary presente JAMAIS gera estimativa
    with_sal = _job(1, salary_text="Vergütung: 1.200 € pro Monat")
    check("A5 job_salary presente -> NUNCA estimativa (inviolável)",
          sb.market_salary_estimate(with_sal, bm) is None)


def group_b_estimate() -> None:
    print("== B: estimativa rotulada, nunca fundida ==")
    bm = sb.load_salary_benchmark(REPO / "config" / "salary_benchmark.json")
    ws = sb.salary_estimate_for_job(_job(2, title="Werkstudent Procurement"), bm)
    pr = sb.salary_estimate_for_job(_job(3), bm)
    pf = sb.salary_estimate_for_job(_job(4, title="Pflichtpraktikum Einkauf"), bm)
    check("B1 werkstudent -> 14–17 €/h", "14–17 €/h" in ws)
    check("B2 praktikum -> €1.507/mês", "€1.507/mês" in pr)
    check("B3 pflichtpraktikum -> €1.021/mês", "€1.021/mês" in pf)
    check("B4 rótulo LITERAL 'estimativa de mercado' sempre presente",
          all(sb.SALARY_ESTIMATE_LABEL in x for x in (ws, pr, pf)))
    check("B4b rótulo ANTES do valor (nunca como dado)",
          all(x.startswith(sb.SALARY_ESTIMATE_LABEL + ":") for x in (ws, pr, pf)))
    check("B5 categoria não derivável -> ''",
          sb.salary_estimate_for_job(_job(5, title="Fachkraft Lager"), bm) == "")
    # B6/B7 — contrato no card HTML (a raiz do elif no _card)
    with_sal = _job(6, salary_text="Vergütung: 1.200 € pro Monat")
    html_sal = _render([with_sal], bm)
    check("B6 detectado presente -> SEM estimativa no card (nunca ambos)",
          "estimativa de mercado" not in html_sal and "€1200" in html_sal)
    no_sal = _job(7)
    html_est = _render([no_sal], bm)
    check("B7 ausente + derivável -> estimativa rotulada no card",
          sb.SALARY_ESTIMATE_LABEL in html_est and "€1.507/mês" in html_est)
    check("B7b benchmark None -> card sem estimativa (regressão zero)",
          "estimativa de mercado" not in _render([no_sal], None))


def group_c_age() -> None:
    print("== C: badge idade ==")
    bm = sb.load_salary_benchmark(REPO / "config" / "salary_benchmark.json")
    ref = datetime(2026, 10, 13, tzinfo=UTC)
    old = _job(8, posted="2026-06-01T00:00:00+00:00")   # 134 dias
    new = _job(9, posted="2026-10-12T00:00:00+00:00")   # 1 dia
    none_posted = _job(10)
    check("C1 'postada há N dias' no card (>45d)",
          "postada há 134 dias" in _render([old], bm))
    check("C2 >45d -> classe age-stale (destaque discreto)",
          "age-stale" in _render([old], bm))
    check("C3 <=45d -> sem age-stale no card",
          'class="age age-stale"' not in _render([new], bm)
          and 'class="age-stale"' not in _render([new], bm))
    check("C3b 'há 1d' formato curto preservado (F11)",
          "há 1d" in _render([new], bm))
    check("C4 sem posted_at -> sem badge (regressão F11)",
          "postada há" not in _render([none_posted], bm))


def group_d_duration() -> None:
    print("== D: flag duração §16e ==")
    check("D1 >6 meses -> flag literal",
          mp.duration_flag_text(_job(11, desc="Die Praxisphase dauert 9 Monate."))
          == "duração 9 meses — acima do teto §16e (6 meses)")
    check("D2 6 meses exatos -> SEM flag",
          mp.duration_flag_text(_job(12, desc="Dauer: 6 Monate")) == "")
    check("D3 faixa 6–12 começa dentro do teto -> SEM flag",
          mp.duration_flag_text(_job(13, desc="Praktikum für 6-12 Monate.")) == "")
    check("D4 sem duração citada -> sem flag",
          mp.duration_flag_text(_job(14)) == "")
    html = _render([_job(15, desc="Dauer 8 Monate.")], None)
    check("D5 flag visível no card",
          "duração 8 meses — acima do teto §16e (6 meses)" in html)


def group_e_red_flags() -> None:
    print("== E: red-flags determinísticas ==")
    check("E1 EN 'enrolled at a German university' -> badge",
          mp.enrollment_flag(_job(16, desc="You must be enrolled at a "
                                           "German university.")) ==
          mp.ENROLLMENT_FLAG_TEXT)
    check("E2 DE 'Einschreibung an einer deutschen Hochschule' -> badge",
          mp.enrollment_flag(_job(17, desc="Voraussetzung: Einschreibung an "
                                           "einer deutschen Hochschule.")) ==
          mp.ENROLLMENT_FLAG_TEXT)
    check("E3 sem exigência -> sem badge",
          mp.enrollment_flag(_job(18)) == "")
    check("E4 remuneração ausente -> badge honesto",
          mp.salary_unspecified_flag(_job(19)) == mp.SALARY_UNSPECIFIED_TEXT)
    check("E5 remuneração citada -> SEM badge",
          mp.salary_unspecified_flag(
              _job(20, salary_text="Vergütung: 1.100 € pro Monat")) == "")
    flagged = _job(21, desc="Requirement: enrolled at a German university.")
    html = _render([flagged], None)
    check("E6 red-flag INFORMATIVA: vaga flagada PERMANECE no card",
          "exige matrícula em universidade alemã" in html
          and 'data-s="10' in html)
    html_ns = _render([_job(22)], None)
    check("E6b 'remuneração não citada' no card quando ausente",
          mp.SALARY_UNSPECIFIED_TEXT in html_ns)


def group_f_countdown() -> None:
    print("== F: countdown visto no digest ==")
    tmp = Path(tempfile.mkdtemp())
    cur = [_job(30 + i, title=f"Praktikum Supply Chain {i}") for i in range(6)]
    prev = [dict(cur[1]), dict(cur[2])]  # sobra 4 "novas"
    (tmp / "cur.json").write_text(json.dumps(cur), encoding="utf-8")
    (tmp / "prev.json").write_text(json.dumps(prev), encoding="utf-8")
    lines = rd.digest_sections(tmp / "cur.json", tmp / "prev.json",
                              pages_url="https://x/", visa_countdown=True)
    text = "\n".join(lines or [])
    idx_visa = text.find("📅 Visto §16e:")
    idx_top5 = text.find(rd.TOP5_SECTION_PREFIX)
    check("F1 countdown presente e ANTES do ⚡ Top 5",
          idx_visa != -1 and idx_top5 != -1 and idx_visa < idx_top5)
    check("F1b linha na forma exata da spec",
          "📅 Visto §16e: oferta necessária até ~15/11/2026 p/ início "
          "jan/2027" in text)
    # F2 — data derivada de constantes: mudar o alvo muda a linha
    old_target = rd.VISA_TARGET_START
    old_lead = rd.VISA_LEAD_DAYS
    try:
        rd.VISA_TARGET_START = (2027, 3, 1)
        rd.VISA_LEAD_DAYS = 47
        line = rd.visa_countdown_line()
        check("F2 data derivada de constantes (alvo mar/2027 -> 13/01/2027)",
              "~13/01/2027" in line and "mar/2027" in line)
    finally:
        rd.VISA_TARGET_START = old_target
        rd.VISA_LEAD_DAYS = old_lead
    lines_off = rd.digest_sections(tmp / "cur.json", tmp / "prev.json",
                                   pages_url="https://x/",
                                   visa_countdown=False)
    check("F3 visa_countdown=False -> ausente (regressão zero)",
          "Visto §16e" not in "\n".join(lines_off or []))


def group_g_legal() -> None:
    print("== G: frases jurídicas LITERAIS ==")
    html = _render([_job(40)], None)
    check("G1 frase duração LITERAL na página (substring assert)",
          "§16e: duração máxima 6 meses (AufenthG §16e Abs. 2)." in html)
    check("G2 frase Zustimmung LITERAL na página (substring assert)",
          "Praktikum sob §16e NÃO exige Zustimmung da Bundesagentur für "
          "Arbeit (BeschV §15 Nr. 1) — confirmar procedimento atualizado "
          "com consulado/Ausländerbehörde." in html)
    check("G3 constantes do módulo = fonte única",
          mp.LEGAL_DURATION_PHRASE == "§16e: duração máxima 6 meses "
          "(AufenthG §16e Abs. 2)."
          and "BeschV §15 Nr. 1" in mp.LEGAL_ZUSTIMMUNG_PHRASE)


def group_h_budget() -> None:
    print("== H: byte budget (cap F6 intocável) ==")
    bm = sb.load_salary_benchmark(REPO / "config" / "salary_benchmark.json")
    # snapshot real quando existe (clone de desenvolvimento); senão fixture
    real = REPO / "data" / "eligible_jobs.json"
    if real.exists():
        jobs = json.loads(real.read_text(encoding="utf-8"))
        src = "snapshot real"
    else:
        jobs = [_job(100 + i, title=f"Praktikum Supply Chain {i} " + "x" * 60,
                     desc="Werkstudent Beschaffung Logistik Einkauf. " * 8)
                for i in range(100)]
        src = "fixture 100 vagas"
    html = mp.render_size_aware(jobs, total_eligible=len(jobs),
                                 generated_at="2026-10-13 09:00",
                                 salary_benchmark_map=bm)
    size = len(html.encode("utf-8"))
    check(f"H1 página com sinais F29 < 150KB cap ({src}: {size} bytes)",
          size < mp.PAGE_HARD_CAP_BYTES)
    # H2 — pior caso: TODAS as vagas recebem estimativa (werkstudent p/ hora)
    ws_jobs = [dict(j, title=f"Werkstudent Supply Chain {i} " + "x" * 40)
               for i, j in enumerate(jobs[:100])]
    html2 = mp.render_size_aware(ws_jobs, total_eligible=len(ws_jobs),
                                  generated_at="2026-10-13 09:00",
                                  salary_benchmark_map=bm)
    check(f"H2 pior caso estimativas < 150KB ({len(html2.encode('utf-8'))} bytes)",
          len(html2.encode("utf-8")) < mp.PAGE_HARD_CAP_BYTES)


def group_i_zero_impact() -> None:
    print("== I: zero impacto no pipeline ==")
    # I1 — F29 não importa score/filters/ranking
    src_mp = (REPO / "scripts" / "minimal_page.py").read_text(encoding="utf-8")
    src_sb = (REPO / "src" / "internship_finder" /
              "salary_benchmark.py").read_text(encoding="utf-8")
    for forbidden in ("from internship_finder import ranking",
                      "from internship_finder import filters",
                      "from internship_finder.ranking",
                      "from internship_finder.filters"):
        check(f"I1 sem import proibido '{forbidden}'",
              forbidden not in src_mp and forbidden not in src_sb)
    # I2 — ids/scores/ordem idênticos com e sem benchmark
    jobs = [_job(200 + i, title=f"Praktikum {i}", score=15.0 - i)
            for i in range(20)]
    bm = sb.load_salary_benchmark(REPO / "config" / "salary_benchmark.json")
    h_on = _render(jobs, bm)
    h_off = _render(jobs, None)
    ids_on = re.findall(r'data-q="([^"]+)"', h_on)
    ids_off = re.findall(r'data-q="([^"]+)"', h_off)
    check("I2 ids/ordem idênticos com e sem benchmark", ids_on == ids_off)
    scores_on = re.findall(r'data-s="([^"]+)"', h_on)
    scores_off = re.findall(r'data-s="([^"]+)"', h_off)
    check("I2b scores idênticos com e sem benchmark", scores_on == scores_off)


def main() -> int:
    print("F29: sinais de candidatura no display — loader, badges, "
          "estimativa rotulada, countdown, frases jurídicas, budget")
    group_a_loader()
    group_b_estimate()
    group_c_age()
    group_d_duration()
    group_e_red_flags()
    group_f_countdown()
    group_g_legal()
    group_h_budget()
    group_i_zero_impact()
    print()
    if FAILURES:
        print(f"F29: {N - len(FAILURES)} OK, {len(FAILURES)} FAIL")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print(f"F29: {N} OK, 0 FAIL")
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
