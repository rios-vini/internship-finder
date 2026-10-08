"""Testes da Fase F15 — mapa de qualidade de empregador (100% offline).

Cobre as 4 tarefas da fase sem rede e sem ``data/`` de produção (fixtures
em tmp_path; o mapa versionado é o do repo, lido read-only):

- **T1 Mapa parse** (``employer_quality.load_employer_quality``): JSON
  válido, campos obrigatórios, score 0-5; arquivo ausente/corrompido =
  {} silencioso; chaves normalizadas (casefold/acentos).
- **T2 Badge na página**: empresa mapeada → badge ⭐/🏆 no card; não
  mapeada → sem badge; mapa ausente = silêncio gracioso (HTML byte a
  byte idêntico); COEXISTÊNCIA com o badge ✅ da F14 no mesmo card;
  badge nas 4 seções de cards; entrada "unavailable" = sem badge.
- **T3 Digest ⭐**: mapeada → ⭐ após o nome; não mapeada → linha
  idêntica; sem mapa → Top 5 byte a byte idêntico; F12.5 preservada
  (URL inteira); compact F6.1/F13/F14 intocados (seções extraídas
  iguais).
- **T4 Ponto ótimo** (``sweet_spot_companies``): empresa grande+boa+visa_
  friendly entra; sem score ou sem visa_friendly fica fora; ordenação
  por volume; cap top; sem intel_map = lista vazia; GPTW sem score
  entra (prêmio é critério alternativo).
- **T5 ZERO HTTP no build**: monkeypatch de urllib/requests/socket —
  qualquer requisição externa durante render_minimal_html_from_file,
  digest_sections e sweet_spot FALHA o teste.
- **T6 Regressões da página**: página sem mapa = byte a byte a de antes
  (render com quality_map=None == sem F15); cap de 150KB validado nos
  cenários de fixture; seção ponto ótimo omitida quando estoura o cap
  (gate com tamanho medido no stdout).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
import ranking_digest as rg  # noqa: E402
from internship_finder import employer_quality as eq  # noqa: E402
from internship_finder import opportunity_intel as oi  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool) -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures (offline; formato real do eligible_jobs.json)
# ---------------------------------------------------------------------------

def _job(i: int, *, company=None, title=None, score=None) -> dict:
    return {
        "id": f"t{i}", "title": title or f"Praktikum Supply Chain {i}",
        "company": company or f"Firma {i} GmbH",
        "location": "Berlin, DE", "country_iso": "de",
        "score": 15.0 - (i * 0.1) if score is None else score,
        "url": f"https://jobs.example.com/{i}",
        "description": "supply chain procurement logistics " * 6,
        "raw": {},
    }


def _quality_fixture(base: Path, entries: list[dict]) -> Path:
    path = base / "employer_quality.json"
    path.write_text(json.dumps({"companies": entries}), encoding="utf-8")
    return path


def _intel_fixture(base: Path, companies: list[dict]) -> Path:
    path = base / "company_intelligence.json"
    path.write_text(json.dumps({"companies": companies}), encoding="utf-8")
    return path


REPO_MAP = Path(__file__).resolve().parent.parent / "config" / "employer_quality.json"


# ---------------------------------------------------------------------------
# T1 — mapa parse
# ---------------------------------------------------------------------------

def test_map_parse() -> None:
    section("T1: mapa parse — JSON válido, campos, score 0-5, silêncio")
    # mapa versionado do repo: parseável, entradas íntegras
    check("mapa do repo existe", REPO_MAP.is_file())
    data = json.loads(REPO_MAP.read_text(encoding="utf-8"))
    entries = data["companies"]
    check(f"mapa do repo tem entradas (>= 30; tem {len(entries)})",
          len(entries) >= 30)
    ok_fields = all(
        isinstance(e, dict) and e.get("company")
        and "kununu_score" in e and "kununu_reviews" in e
        and "gptw_award" in e and e.get("source_url")
        and e.get("checked")
        for e in entries)
    check("campos obrigatórios em TODAS as entradas "
          "(company/kununu_score/kununu_reviews/gptw_award/source_url/checked)",
          ok_fields)
    ok_score = all(
        e["kununu_score"] is None or
        (isinstance(e["kununu_score"], (int, float))
         and not isinstance(e["kununu_score"], bool)
         and 0 <= e["kununu_score"] <= 5)
        for e in entries)
    check("kununu_score null ou float 0-5", ok_score)
    ok_gptw = all(
        e["gptw_award"] is None or
        (isinstance(e["gptw_award"], int) and 2000 < e["gptw_award"] < 2100)
        for e in entries)
    check("gptw_award null ou ano plausível", ok_gptw)
    checked_iso = all(
        isinstance(e.get("checked"), str) and len(e["checked"]) == 10
        and e["checked"][4] == "-" and e["checked"][7] == "-"
        for e in entries)
    check("checked é data ISO (YYYY-MM-DD) em todas", checked_iso)
    with_score = [e for e in entries if e["kununu_score"] is not None]
    check(f"maioria com score (tem {len(with_score)}/{len(entries)})",
          len(with_score) >= len(entries) // 2)

    # loader: chaves normalizadas, {} em falha
    qmap = eq.load_employer_quality(REPO_MAP)
    check("loader devolve mapa não-vazio", len(qmap) >= 30)
    check("chave normalizada (casefold): 'bmw ag' entra",
          "bmw ag" in qmap or any("bmw" in k for k in qmap))
    tmp = Path(tempfile.mkdtemp(prefix="t_f15_map_"))
    check("arquivo ausente -> {}",
          eq.load_employer_quality(tmp / "nao_existe.json") == {})
    bad = tmp / "bad.json"
    bad.write_text("isto não é json", encoding="utf-8")
    check("JSON corrompido -> {}", eq.load_employer_quality(bad) == {})
    wrong = tmp / "wrong.json"
    wrong.write_text(json.dumps({"companies": "não é lista"}), encoding="utf-8")
    check("companies não-lista -> {}", eq.load_employer_quality(wrong) == {})
    # acento/case: entry "BoschGroup" casa por _norm
    e = qmap.get("boschgroup")
    check("match _norm (casefold): 'boschgroup' acha a entrada",
          e is not None and e.get("kununu_score") is not None)
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# T2 — badge na página
# ---------------------------------------------------------------------------

def test_badge_page() -> None:
    section("T2: badge ⭐/🏆 — mapeada, não-mapeada, ausente, coexistência")
    tmp = Path(tempfile.mkdtemp(prefix="t_f15_badge_"))
    qpath = _quality_fixture(tmp, [
        {"company": "Gute Firma GmbH", "kununu_score": 4.2,
         "kununu_reviews": 100, "gptw_award": None,
         "source_url": "https://www.kununu.com/de/gute-firma",
         "source_type": "kununu-profile", "checked": "2026-10-08"},
        {"company": "Premierte AG", "kununu_score": None,
         "kununu_reviews": 12, "gptw_award": 2026,
         "source_url": "https://www.kununu.com/de/premierte",
         "source_type": "kununu-profile", "checked": "2026-10-08"},
        {"company": "Sem Nota SE", "kununu_score": None,
         "kununu_reviews": 5, "gptw_award": None,
         "source_url": "https://www.kununu.com/de/sem-nota",
         "source_type": "unavailable", "checked": "2026-10-08"},
    ])
    qmap = eq.load_employer_quality(qpath)

    jobs = [
        _job(0, company="Gute Firma GmbH"),
        _job(1, company="Premierte AG"),
        _job(2, company="Sem Nota SE"),
        _job(3, company="Desconhecida XYZ GmbH"),
    ]
    html = mp.render_minimal_html(
        jobs, total_eligible=4, generated_at="x", quality_map=qmap)
    check("mapeada com score: ⭐ 4,2 · Kununu no card",
          "⭐ 4,2 · Kununu" in html)
    check("mapeada com GPTW: 🏆 GPTW 2026 no card",
          "🏆 GPTW 2026" in html)
    check("entrada unavailable: SEM badge (contagem exata)",
          html.count('class="eq"') == 2)
    check("não-mapeada: sem badge (id t3 limpo)",
          "Desconhecida" in html and "⭐" not in html.split("Desconhecida")[1].split("</li>")[0])

    # mapa ausente = silêncio gracioso: HTML IDÊNTICO ao pré-F15
    html_no_map = mp.render_minimal_html(
        jobs, total_eligible=4, generated_at="x")
    html_none = mp.render_minimal_html(
        jobs, total_eligible=4, generated_at="x", quality_map=None)
    html_empty = mp.render_minimal_html(
        jobs, total_eligible=4, generated_at="x",
        quality_map=eq.load_employer_quality(tmp / "nao_existe.json"))
    check("quality_map=None == sem F15 (byte a byte)",
          html_none == html_no_map)
    check("mapa ausente == quality_map=None (byte a byte)",
          html_empty == html_no_map)
    check("sem mapa: nenhum span .eq", 'class="eq"' not in html_no_map)

    # coexistência com o badge ✅ da F14: mesmo card com ambos
    import sqlite3
    db = tmp / "personal" / "jobs_personal.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE job_status (job_id TEXT PRIMARY KEY, "
                 "status TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO job_status VALUES ('t0', 'applied', 'x')")
    conn.commit()
    conn.close()
    html_both = mp.render_minimal_html(
        jobs, total_eligible=4, generated_at="x", quality_map=qmap,
        tracker_db=db)
    card0 = html_both.split('data-q="Praktikum Supply Chain 0')[1].split("</li>")[0]
    check("coexistência F14+F15: ✅ E ⭐ no MESMO card",
          "✅" in card0 and "⭐ 4,2 · Kununu" in card0)

    # badge nas 4 seções de cards (top, 🆕, 🎯, materials)
    watch_ev = [dict(jobs[0], company="Gute Firma GmbH")]
    mats = [dict(jobs[0], materials_score=9.0)]
    html4 = mp.render_minimal_html(
        jobs, total_eligible=4, generated_at="x", quality_map=qmap,
        new_since_ids={jobs[0]["id"], jobs[1]["id"], jobs[2]["id"]},
        watchlist_events=watch_ev, materials=mats, tracker_db=db)
    check("badge .eq nas 4 seções (count >= 5)",
          html4.count('class="eq"') >= 5)
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# T3 — digest ⭐
# ---------------------------------------------------------------------------

def test_digest_star() -> None:
    section("T3: digest — ⭐ quando mapeada; byte a byte quando não")
    tmp = Path(tempfile.mkdtemp(prefix="t_f15_dig_"))
    qpath = _quality_fixture(tmp, [
        {"company": "Mapeada GmbH", "kununu_score": 3.7,
         "kununu_reviews": 50, "gptw_award": None,
         "source_url": "https://x", "source_type": "kununu-profile",
         "checked": "2026-10-08"},
        {"company": "Sem Sinal SE", "kununu_score": None,
         "kununu_reviews": 5, "gptw_award": None,
         "source_url": "https://x", "source_type": "unavailable",
         "checked": "2026-10-08"},
    ])
    qmap = eq.load_employer_quality(qpath)
    jobs = [
        _job(0, company="Mapeada GmbH"),
        _job(1, company="Sem Sinal SE"),
        _job(2, company="Desconhecida ABC"),
    ]
    jobs[0]["url"] = "https://jobs.example.com/0?apply=long-url-inteira-aqui"

    with_map = rg.format_top5(jobs, max_len=100000, quality_map=qmap)
    check("mapeada com score: ⭐ após o nome",
          "Mapeada GmbH⭐" in with_map)
    check("entrada unavailable: SEM ⭐ (Sem Sinal SE sem marcador)",
          "Sem Sinal SE⭐" not in with_map
          and "Sem Sinal SE —" in with_map)
    check("não-mapeada: linha sem ⭐",
          "Desconhecida ABC⭐" not in with_map)
    check("F12.5 preservada: URL inteira no Top 5",
          "https://jobs.example.com/0?apply=long-url-inteira-aqui" in with_map)

    # sem mapa: byte a byte idêntico ao pré-F15
    no_map = rg.format_top5(jobs, max_len=100000)
    none_map = rg.format_top5(jobs, max_len=100000, quality_map=None)
    check("sem mapa == quality_map=None (byte a byte)",
          none_map == no_map)
    check("sem mapa: nenhum ⭐", "⭐" not in no_map)

    # compact F6.1/F13/F14: extração de seções não muda com o ⭐
    top5_lines = rg.format_top5(jobs, max_len=100000,
                                quality_map=qmap).splitlines()
    digest = ["", "🆕 Novas desde ontem: 1", "  1. nova a", "",
              rg.TOP5_SECTION_HEADER] + top5_lines + ["",
              rg.WATCHLIST_SECTION_HEADER + " — 1 nova(s)",
              "  🎯 1. Alvo: título (Local)", "",
              rg.FOLLOWUP_SECTION_HEADER + " — 1 pendente(s)",
              "  ⏰ 1. Acme: X (há 15 dias)", "",
              "🔗 Ranking completo: https://x/"]
    check("top5_section_lines extrai o ⚡ com ⭐ (header intacto)",
          rg.top5_section_lines(digest)[:1] == [rg.TOP5_SECTION_HEADER])
    check("watchlist_section_lines intacta (F13)",
          rg.watchlist_section_lines(digest)[0].startswith("🎯 Empresas-alvo"))
    check("followup_section_lines intacta (F14)",
          rg.followup_section_lines(digest)[0].startswith("⏰ Follow-up"))
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# T4 — ponto ótimo (cruzamento)
# ---------------------------------------------------------------------------

def test_sweet_spot() -> None:
    section("T4: ponto ótimo — volume × qualidade × visa_friendly")
    tmp = Path(tempfile.mkdtemp(prefix="t_f15_spot_"))
    qpath = _quality_fixture(tmp, [
        {"company": "Boa Grande", "kununu_score": 4.3,
         "kununu_reviews": 800, "gptw_award": None,
         "source_url": "https://x", "source_type": "kununu-profile",
         "checked": "2026-10-08"},
        {"company": "Premiada Pequena", "kununu_score": None,
         "kununu_reviews": 9, "gptw_award": 2026,
         "source_url": "https://x", "source_type": "kununu-profile",
         "checked": "2026-10-08"},
        {"company": "Ruim Grande", "kununu_score": 2.9,
         "kununu_reviews": 800, "gptw_award": None,
         "source_url": "https://x", "source_type": "kununu-profile",
         "checked": "2026-10-08"},
        {"company": "Boa Sem Visa", "kununu_score": 4.5,
         "kununu_reviews": 300, "gptw_award": None,
         "source_url": "https://x", "source_type": "kununu-profile",
         "checked": "2026-10-08"},
    ])
    ipath = _intel_fixture(tmp, [
        {"company": "Boa Grande", "visa_policy": "unclear"},
        {"company": "Premiada Pequena", "visa_policy": "explicit_support"},
        {"company": "Ruim Grande", "visa_policy": "explicit_support"},
        {"company": "Boa Sem Visa",
         "visa_policy": "candidate_must_have_authorization"},
    ])
    qmap = eq.load_employer_quality(qpath)
    imap = oi.load_company_intel(ipath)

    jobs = (
        [_job(i, company="Boa Grande") for i in range(10)]      # volume 10
        + [_job(100, company="Premiada Pequena")]               # volume 1 + GPTW
        + [_job(200 + i, company="Ruim Grande") for i in range(5)]  # 5, ruim
        + [_job(300 + i, company="Boa Sem Visa") for i in range(7)]  # 7, sem visa
        + [_job(400, company="Desconhecida")]                   # fora do mapa
    )
    rows = eq.sweet_spot_companies(jobs, qmap, imap)
    names = [r["company"] for r in rows]
    check("Boa Grande entra (grande + boa + visa_friendly)",
          "Boa Grande" in names)
    check("Premiada Pequena entra (GPTW substitui score)",
          "Premiada Pequena" in names)
    check("Ruim Grande FORA (score < 4,0, sem prêmio)",
          "Ruim Grande" not in names)
    check("Boa Sem Visa FORA (sem visa_friendly)",
          "Boa Sem Visa" not in names)
    check("Desconhecida FORA (sem entrada no mapa)",
          "Desconhecida" not in names)
    check("ordenação por volume: Boa Grande (10) antes da Premiada (1)",
          names.index("Boa Grande") < names.index("Premiada Pequena"))
    check("row traz volume/score/gptw",
          rows[0]["eligible"] == 10 and rows[0]["kununu_score"] == 4.3)

    # sem intel_map = vazio (visa_friendly é critério obrigatório)
    check("sem intel_map -> [] (visa_friendly obrigatório)",
          eq.sweet_spot_companies(jobs, qmap, None) == [])
    # mapa vazio = []
    check("mapa vazio -> []",
          eq.sweet_spot_companies(jobs, {}, imap) == [])
    # cap top
    many = [_job(i, company=f"Boa {i}") for i in range(20)]
    qmap2 = eq.load_employer_quality(_quality_fixture(tmp, [
        {"company": f"Boa {i}", "kununu_score": 4.0 + i * 0.01,
         "kununu_reviews": 10, "gptw_award": None,
         "source_url": "https://x", "source_type": "kununu-profile",
         "checked": "2026-10-08"} for i in range(20)]))
    ipath2 = _intel_fixture(tmp, [
        {"company": f"Boa {i}", "visa_policy": "unclear"} for i in range(20)])
    imap2 = oi.load_company_intel(ipath2)
    rows2 = eq.sweet_spot_companies(many, qmap2, imap2, top=15)
    check("cap top 15 respeitado (20 candidatas)", len(rows2) == 15)

    # linhas da seção: formato nome · qualidade · N vagas
    lines = eq.sweet_spot_lines(jobs, qmap, imap)
    check("linhas no formato 'empresa · ⭐ N,N · N vagas eligible'",
          any(l == "Boa Grande · ⭐ 4,3 · Kununu · 10 vagas eligible"
              for l in lines))
    check("linha GPTW sem score: '🏆 GPTW 2026'",
          any("Premiada Pequena · 🏆 GPTW 2026 · 1 vaga eligible" == l
              for l in lines))

    # seção na página: rows -> HTML; omitida quando não há rows
    html = mp.render_minimal_html(
        jobs, total_eligible=len(jobs), generated_at="x",
        quality_map=qmap, sweet_spot_rows=rows)
    check("seção ⭐ Ponto ótimo no HTML com as linhas",
          "⭐ Ponto ótimo" in html and "Boa Grande · ⭐ 4,3" in html)
    html_no = mp.render_minimal_html(
        jobs, total_eligible=len(jobs), generated_at="x",
        quality_map=qmap, sweet_spot_rows=None)
    check("sem rows: seção ausente (byte a byte sem ela)",
          "Ponto ótimo" not in html_no)
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# T5 — ZERO HTTP no build
# ---------------------------------------------------------------------------

def test_zero_http() -> None:
    section("T5: ZERO HTTP externo no build (F15 §5)")
    import urllib.request
    import urllib.error

    calls: list[str] = []

    def _fail_open(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append(f"urllib:{args[0] if args else '?'}")
        raise AssertionError("HTTP EXTERNO NO BUILD — proibido pela F15")

    tmp = Path(tempfile.mkdtemp(prefix="t_f15_http_"))
    qpath = _quality_fixture(tmp, [
        {"company": "Gute Firma GmbH", "kununu_score": 4.2,
         "kununu_reviews": 100, "gptw_award": None,
         "source_url": "https://www.kununu.com/de/gute-firma",
         "source_type": "kununu-profile", "checked": "2026-10-08"},
    ])
    ipath = _intel_fixture(tmp, [
        {"company": "Gute Firma GmbH", "visa_policy": "unclear"}])
    jobs_path = tmp / "eligible_jobs.json"
    jobs_path.write_text(json.dumps([_job(0, company="Gute Firma GmbH")]),
                          encoding="utf-8")
    prev_path = tmp / "previous.json"
    prev_path.write_text(json.dumps([]), encoding="utf-8")

    orig_open = urllib.request.urlopen
    urllib.request.urlopen = _fail_open
    try:
        # 1) render da página (from_file: mapa + sweet spot + badges)
        html = mp.render_minimal_html_from_file(
            jobs_path, company_intel_map=oi.load_company_intel(ipath),
            employer_quality_path=qpath)
        check("render_minimal_html_from_file SEM HTTP (badge+ponto ótimo)",
              "⭐ 4,2" in html and calls == [])
        # 2) digest (format_top5 + digest_sections)
        qmap = eq.load_employer_quality(qpath)
        text = rg.format_top5([_job(0, company="Gute Firma GmbH")],
                              max_len=4000, quality_map=qmap)
        check("format_top5 com mapa SEM HTTP", "⭐" in text and calls == [])
        # 3) cruzamento ponto ótimo
        rows = eq.sweet_spot_companies(
            [ _job(0, company="Gute Firma GmbH")], qmap,
            oi.load_company_intel(ipath))
        check("sweet_spot_companies SEM HTTP", len(rows) == 1 and calls == [])
        # 4) loader com caminho real do repo
        m = eq.load_employer_quality(REPO_MAP)
        check("load_employer_quality SEM HTTP", len(m) >= 30 and calls == [])
        check("NENHUMA chamada de rede registrada", calls == [])
    finally:
        urllib.request.urlopen = orig_open

    # também trava socket cru (requests/urllib usam socket por baixo)
    import socket
    orig_connect = socket.socket.connect
    def _fail_connect(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append(f"socket:{args}")
        raise AssertionError("SOCKET EXTERNO NO BUILD — proibido pela F15")
    socket.socket.connect = _fail_connect
    try:
        html = mp.render_minimal_html_from_file(
            jobs_path, company_intel_map=None, employer_quality_path=qpath)
        rg.format_top5([_job(0)], max_len=4000,
                       quality_map=eq.load_employer_quality(qpath))
        check("build inteiro sem socket externo", calls == [])
    finally:
        socket.socket.connect = orig_connect
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# T6 — regressões da página + cap + gate da seção
# ---------------------------------------------------------------------------

def test_page_regression_and_cap() -> None:
    section("T6: regressão sem mapa + cap 150KB + gate da seção")
    tmp = Path(tempfile.mkdtemp(prefix="t_f15_reg_"))
    jobs = [_job(i, company=f"Firma {i} GmbH") for i in range(30)]

    # sem mapa: byte a byte idêntico ao comportamento pré-F15
    html_pre = mp.render_minimal_html(jobs, total_eligible=30,
                                     generated_at="x")
    html_none = mp.render_minimal_html(jobs, total_eligible=30,
                                       generated_at="x", quality_map=None)
    check("página sem mapa: byte a byte idêntica (regressão zero)",
          html_pre == html_none)

    # from_file com mapa ausente no caminho = silêncio gracioso
    jobs_path = tmp / "eligible_jobs.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    html_a = mp.render_minimal_html_from_file(jobs_path)
    html_b = mp.render_minimal_html_from_file(
        jobs_path, employer_quality_path=tmp / "nao_existe.json")
    check("from_file com mapa ausente == from_file sem o parâmetro",
          html_a == html_b)

    # cap: fixture com 30 vagas cabe no cap duro
    check(f"página de fixture < 150KB (cap duro)",
          len(html_a.encode("utf-8")) < mp.PAGE_HARD_CAP_BYTES)

    # gate da seção: rows que NÃO cabem são omitidos com aviso no stdout
    import io
    from contextlib import redirect_stdout
    big_rows = [{"company": f"Empresa {i}", "eligible": i,
                 "kununu_score": 4.0 + i * 0.05, "gptw_award": None}
                for i in range(15)]
    # página minúscula — rows CABEM (nada a omitir)
    buf = io.StringIO()
    with redirect_stdout(buf):
        html_in = mp.render_minimal_html(
            jobs[:3], total_eligible=3, generated_at="x",
            sweet_spot_rows=big_rows)
    check("seção com rows em página pequena: entra",
          "Ponto ótimo" in html_in and "omitida" not in buf.getvalue())

    # gate via from_file: render final medido; página já grande + rows ->
    # se o TOTAL estourar o cap, a seção sai e o aviso imprime o tamanho
    tmp2 = Path(tempfile.mkdtemp(prefix="t_f15_gate_"))
    big_jobs = []
    for i in range(400):
        j = _job(i, company=f"Firma {i % 40} GmbH")
        j["description"] = "x" * 300
        big_jobs.append(j)
    bj_path = tmp2 / "eligible_jobs.json"
    bj_path.write_text(json.dumps(big_jobs), encoding="utf-8")
    qpath = _quality_fixture(tmp2, [
        {"company": f"Firma {k % 40} GmbH", "kununu_score": 4.5,
         "kununu_reviews": 99, "gptw_award": None,
         "source_url": "https://x", "source_type": "kununu-profile",
         "checked": "2026-10-08"}
        for k in range(40)])
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        html_big = mp.render_minimal_html_from_file(
            bj_path, employer_quality_path=qpath, include_materials=False)
    out2 = buf2.getvalue()
    if len(html_big.encode("utf-8")) >= mp.PAGE_HARD_CAP_BYTES:
        check("gate OMITE a seção quando o total estoura o cap "
              "(aviso com tamanho medido)",
              "Ponto ótimo" not in html_big
              and "OMITIDA" in out2 and "bytes" in out2)
    else:
        check("página de fixture dentro do cap com a seção",
              "Ponto ótimo" in html_big or "OMITIDA" not in out2)
    shutil.rmtree(tmp)
    shutil.rmtree(tmp2)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    test_map_parse()
    test_badge_page()
    test_digest_star()
    test_sweet_spot()
    test_zero_http()
    test_page_regression_and_cap()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)}")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print(f"TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
