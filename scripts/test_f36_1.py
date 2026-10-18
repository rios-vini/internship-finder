"""Testes da Fase F36.1 — seções fantasma 🇪🇺/🧪 (100% offline).

Bug de produção 14/10 (1º cron com a F36): a página publicada saiu SEM
a seção 🇪🇺 "Fora da Alemanha" — e sem erro no log. Duas faces, mesma
família ("seção some quando o canal aperta"):

(a) PÁGINA (scripts/minimal_page.py): ``render_size_aware`` remonta a
    página em cadeia quando ela estoura o orçamento (F11/F20) e a 3ª
    montagem (orçamento 🎯, quando a página SEM snippets ainda estoura
    o cap 150KB) repassava ``materials=`` mas esquecia ``eu=`` — a
    seção sumia exatamente nos dias de página cheia (95 eventos radar
    → 143,7KB > cap). Lição F36: teste com página PEQUENA nunca exercita
    caminho de degradação — a regressão exige fixture que ESTOURE o cap.

(b) DIGEST (scripts/ranking_digest.py + refresh_daily.build_message):
    quando o digest passa de 4096 chars, o compactador F6.1 reconstrói a
    mensagem por prioridade (⚡/🆕/🎯) e as seções 🧪 Materials e 🇪🇺 EU
    nem eram candidatas → 🧪 não aparecia no digest compactado desde
    28/09 (bug latente pré-F36). F36.1 as torna candidatas no padrão
    F13: colapsam ao HEADER (1 linha), NUNCA são dropadas inteiras.

Contratos testados:

- P1: fixture que estoura o cap (com snippets) → cadeia inteira de
  degradação dispara (com provas: stdout "orçamento 🎯 ativo" + linha
  honesta "+N outras") e as seções 🇪🇺/🧪 continuam no HTML final.
- P2: página sob o cap → seções presentes, sem degradação.
- P3: sem dados EU (None OU estrato vazio) → seção ausente sem erro.
- P4: contrato estrutural — TODA montagem de ``render_size_aware``
  repassa ``eu=`` tantas vezes quanto ``materials=`` (a bomba-relógio
  do bug: montagem nova que esquece uma seção).
- D1/D2: extratores ``materials_section_lines``/``eu_section_lines``
  (padrão F13) + contrato prefixo == header real emitido pelas seções.
- D3: digest > 4096 com seções 🧪/🇪🇺 gordas → headers SOBREVIVEM com
  contagem (corpos cedem espaço), ordem 🧪→🇪🇺 preservada, ⚡/🔗 intactos.
- D4: digest que cabe → mensagem byte a byte == base + digest (o
  caminho não-compactado é intocado — A/B de regressão zero).
- D5: digest estourado SEM 🧪/🇪🇺 → headers ausentes (honestidade) e
  nenhum bloco em branco duplicado (guard dos níveis).
- D6: nível 3 do compact (linhas gigantes) → headers colapsados.

Fixtures: campos mínimos + trechos literais dos headers reais; nomes
das vagas sintéticos. Caso "shape real 14/10": top-3 do estrato EU
medido no dia (Resmed/Parfumado/JACOBSDOUWEEGBERTS — ver
references/onda-b-estado.md §BUG F36.1) como empresas da fixture.

Uso:  .venv/bin/python scripts/test_f36_1.py   (ou bash scripts/test_f36_1.py)
"""

from __future__ import annotations

import io
import sys
import unittest.mock as mock
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
import ranking_digest as rg  # noqa: E402
import refresh_daily as rd  # noqa: E402
from internship_finder.eu_ranking import rank_eu_stratum  # noqa: E402
from internship_finder.materials_ranking import rank_materials_jobs  # noqa: E402
from internship_finder.ranking import rank_jobs  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ---------------------------------------------------------------------------
# Fixtures sintéticas (campos mínimos; nenhum payload real)
# ---------------------------------------------------------------------------

COUNTRIES = ["de", "nl", "be", "lu", "fi"]  # 60% DE + estrato não-DE realista


def _job(i: int) -> dict:
    """Vaga sintética com os campos mínimos que o render consome.

    Description longa de propósito: o snippet é o campo que mais pesa no
    byte-budget da página (lição F36: a degradação só dispara com
    página GORDA — fixture pequena nunca exercita o caminho).
    """
    iso = COUNTRIES[i % len(COUNTRIES)]
    return {
        "id": f"fx|f361:{i}",
        "title": f"Supply Chain Praktikum Bereich Einkauf {i} (m/w/d)",
        "company": f"NordWerk Logistik GmbH {i}",
        "location": f"Stadt {i}, {iso.upper()}",
        "country_iso": iso,
        "employment_type": "FULL_TIME",
        "url": f"https://jobs.example.com/jobs/{i}",
        "description": "Beschaffung und supplier management. " * 12,
    }


def _big_fixture(n: int = 200):
    """Fixture que ESTOURA o cap: n vagas + 95 eventos radar + diff 🆕."""
    jobs = [_job(i) for i in range(n)]
    ranked = rank_jobs(jobs)
    materials = rank_materials_jobs(jobs)[: mp.MATERIALS_SECTION_TOP]
    eu = rank_eu_stratum(jobs)[: mp.EU_SECTION_TOP]
    # 95 eventos radar (medidos 14/10: 95) — todos "novos de ontem" para
    # a 🆕 existir; o orçamento 🎯 (F20) apara p/ top-RADAR_TOP_N.
    events = [dict(j) for j in ranked[:95]]
    new_ids = {j["id"] for j in events}
    return jobs, materials, eu, events, new_ids


def _summary(*, eligible: int = 777, total: int = 126842, n_fail: int = 2) -> dict:
    """Summary no shape mínimo que ``build_message`` consome."""
    return {
        "run_id": "2026-10-14T09:00:01+00:00",
        "total_collected": total,
        "eligible": eligible,
        "dedup_removed": 512,
        "ok": {"count": 113, "collected": 73138},
        "empty": 10,
        "timeout": [("successfactors:tenant", "Lidl", "TIMEOUT")],
        "error": [("oracle:tenant", "SMA", "HTTP_500")]
        + [("s:t", f"E{i}", "HTTP_500") for i in range(n_fail - 1)],
        "skipped": 0,
        "not_found": 0,
        "source_names": {},
    }


def _alert(kind: str, source: str, company: str, **extra) -> dict:
    d = {"type": kind, "source": source, "company": company}
    d.update(extra)
    return d


def _base_alerts() -> list[dict]:
    return [
        _alert("recurring_error", "successfactors:tenant", "Lidl", runs_seq=30),
        _alert("recurring_error", "oracle:tenant", "SMA", runs_seq=17),
    ]


def _apply_job(i: int) -> dict:
    """Vaga do Top 5 ⚡ (shape do format_top5: raw.apply_url)."""
    return {
        "id": f"j{i}",
        "title": f"Praktikum Data Engineering {i} (m/w/d)",
        "company": f"Firma {i} GmbH",
        "location": "Berlin, Deutschland",
        "score": round(16.6 - i * 0.25, 2),
        "url": f"https://jobs.example.com/jobs/{i}",
        "raw": {"apply_url": f"https://apply.example.com/{i}"},
        "country_iso": "de",
    }


# ---------------------------------------------------------------------------
# P — página (render_size_aware)
# ---------------------------------------------------------------------------

def test_page_over_cap_keeps_sections() -> None:
    print("== P1: página ESTOURA o cap → 🇪🇺/🧪 sobrevivem à degradação ==")
    jobs, materials, eu, events, new_ids = _big_fixture()
    check("fixture: estrato EU não vazio (senão a seção nem existiria)",
          len(eu) == mp.EU_SECTION_TOP, f"eu={len(eu)}")
    buf = io.StringIO()
    with redirect_stdout(buf):
        html = mp.render_size_aware(
            jobs, total_eligible=len(jobs),
            generated_at="2026-10-14T09:35:00Z",
            materials=materials, eu=eu,
            watchlist_events=events, new_since_ids=new_ids, lang="pt",
        )
    stdout = buf.getvalue()
    nbytes = len(html.encode("utf-8"))
    # provas de que o caminho de degradação REALLY rodou (lição F36):
    check("camada 3 (orçamento 🎯) disparou de verdade",
          "orçamento 🎯 ativo" in stdout,
          stdout.strip().splitlines()[-1][:80] if stdout.strip() else "")
    check("linha honesta do orçamento presente (+N outras)",
          "outras vagas de empresas-alvo" in html)
    check(f"página final sob o cap ({nbytes} <= {mp.PAGE_HARD_CAP_BYTES})",
          nbytes <= mp.PAGE_HARD_CAP_BYTES, f"{nbytes} bytes")
    # o contrato da F36.1: a seção 🇪🇺 NÃO pode sumir no caminho estourado
    check("🇪🇺 'Fora da Alemanha' presente no HTML estourado",
          "Fora da Alemanha" in html)
    check("🧪 'Materials Engineering' presente no HTML estourado",
          "Materials Engineering" in html)
    # os 3 perfis (top do dia / materials / eu) coexistem
    check("as 3 seções coexistem (📊 implícita + 🧪 + 🇪🇺)",
          "Materials Engineering" in html and "Fora da Alemanha" in html
          and "Internship Finder — top" in html)


def test_page_profile_budget_layer() -> None:
    print("== P5: camada 3-b — orçamento 🧪/🇪🇺 (dia real 14/10) ==")
    # O fix devolve as seções à montagem da camada 3; no dia real 14/10
    # (907 vagas + 97 radar + 244 novas) a página voltou a estourar o
    # cap por ~0,9KB. Camada 3-b (mesma família F20): degrada as seções
    # de perfil p/ top-PROFILE_SECTION_BUDGET_TOP com header HONESTO —
    # a seção NUNCA sai inteira, o cap NUNCA estoura.
    def _pad_job(i: int) -> dict:
        j = _job(i)
        j["title"] += "t" * 80  # calibrado: estoura pós-radar, fecha no 3-b
        return j

    n = 160
    jobs = [_pad_job(i) for i in range(n)]
    ranked = rank_jobs(jobs)
    materials = rank_materials_jobs(jobs)[: mp.MATERIALS_SECTION_TOP]
    eu = rank_eu_stratum(jobs)[: mp.EU_SECTION_TOP]
    events = [dict(j) for j in ranked[:95]]
    new_ids = {j["id"] for j in events}
    # prova do aperto: radar top-15 SOZINHO ainda estoura (3-b é necessário)
    # F46: default do render virou EN (decisão do dono 15/10); esta suíte valida o chrome pt da fase — fixtures forçam lang="pt" (contrato (b) da F46).
    radar_only = mp.render_minimal_html(
        jobs, total_eligible=n, generated_at="2026-10-14T09:35:00Z",
        materials=materials, eu=eu, with_snippets=False,
        watchlist_events=events, new_since_ids=new_ids,
        radar_limit=mp.RADAR_TOP_N, lang="pt")
    check("pré-condição: radar-15 sozinho AINDA estoura o cap (3-b dispara)",
          len(radar_only.encode("utf-8")) > mp.PAGE_HARD_CAP_BYTES,
          f"{len(radar_only.encode('utf-8'))} bytes")
    buf = io.StringIO()
    with redirect_stdout(buf):
        html = mp.render_size_aware(
            jobs, total_eligible=n, generated_at="2026-10-14T09:35:00Z",
            materials=materials, eu=eu,
            watchlist_events=events, new_since_ids=new_ids, lang="pt",
        )
    stdout = buf.getvalue()
    nbytes = len(html.encode("utf-8"))
    check("camada 3-b (orçamento 🧪/🇪🇺) disparou de verdade",
          "orçamento 🧪/🇪🇺 ativo" in stdout,
          stdout.strip().splitlines()[-1][:80] if stdout.strip() else "")
    check(f"página final sob o cap ({nbytes} <= {mp.PAGE_HARD_CAP_BYTES})",
          nbytes <= mp.PAGE_HARD_CAP_BYTES, f"{nbytes} bytes")
    check("🇪🇺 presente mesmo no dia mais apertado (nunca mais ghost)",
          "Fora da Alemanha" in html)
    check("🧪 presente mesmo no dia mais apertado",
          "Materials Engineering" in html)
    check("header HONESTO da 🇪🇺 conta o recorte (top N de 10)",
          "top 5 de 10 — orçamento de página do dia" in html)
    check("cards 🇪🇺 degradados para top-5 (10 cards não caberiam)",
          html.count('data-s=') >= 5
          and "Fora da Alemanha" in html)


def test_page_profile_limit_default() -> None:
    print("== P5b: profile_limit=None → header padrão 'top 10' (regressão zero) ==")
    jobs = [_job(i) for i in range(7)]
    materials = rank_materials_jobs(jobs)[: mp.MATERIALS_SECTION_TOP]
    eu = rank_eu_stratum(jobs)[: mp.EU_SECTION_TOP]
    html = mp.render_minimal_html(
        jobs, total_eligible=len(jobs), generated_at="2026-10-14T09:35:00Z",
        materials=materials, eu=eu, lang="pt")
    check("página normal mantém header 'top 10' (byte a byte o layout)",
          "Fora da Alemanha — top 10 (perfil EU non-DE)" in html
          and "Materials Engineering — top 10 (perfil alternativo)" in html)
    check("nenhum aviso de orçamento na página normal",
          "orçamento de página do dia" not in html)


def test_page_under_cap() -> None:
    print("== P2: página sob o cap → seções presentes, sem degradação ==")
    jobs = [_job(i) for i in range(7)]
    materials = rank_materials_jobs(jobs)[: mp.MATERIALS_SECTION_TOP]
    eu = rank_eu_stratum(jobs)[: mp.EU_SECTION_TOP]
    buf = io.StringIO()
    with redirect_stdout(buf):
        html = mp.render_size_aware(
            jobs, total_eligible=len(jobs),
            generated_at="2026-10-14T09:35:00Z",
            materials=materials, eu=eu, lang="pt",
        )
    check("página pequena: sem orçamento 🎯 (nenhuma degradação)",
          "orçamento 🎯 ativo" not in buf.getvalue())
    check("🇪🇺 presente na página pequena", "Fora da Alemanha" in html)
    check("🧪 presente na página pequena", "Materials Engineering" in html)


def test_page_without_eu_data() -> None:
    print("== P3: sem dados EU → seção ausente, nunca erro ==")
    jobs = [_job(i) for i in range(7)]
    # (a) chamador sem ranking EU (None): contrato do render "None = sem seção"
    buf = io.StringIO()
    with redirect_stdout(buf):
        html = mp.render_minimal_html(
            jobs, total_eligible=len(jobs),
            generated_at="2026-10-14T09:35:00Z", eu=None, lang="pt",
        )
    check("eu=None → sem seção 🇪🇺 (sem erro)",
          "Fora da Alemanha" not in html)
    # (b) estrato vazio (só vagas DE): rank_eu_stratum devolve [] —
    # o corte do chamador manda [] e o render omite a seção honestamente
    de_only = [dict(j, country_iso="de") for j in jobs[:3]]
    check("fixture só-DE: rank_eu_stratum devolve []",
          rank_eu_stratum(de_only) == [])
    eu_empty = rank_eu_stratum(de_only)[: mp.EU_SECTION_TOP]
    buf = io.StringIO()
    with redirect_stdout(buf):
        html2 = mp.render_minimal_html(
            de_only, total_eligible=len(de_only),
            generated_at="2026-10-14T09:35:00Z", eu=eu_empty, lang="pt",
        )
    check("estrato vazio → sem seção 🇪🇺 (sem erro)",
          "Fora da Alemanha" not in html2)
    check("render_size_aware com eu vazio: idem, sem erro",
          "Fora da Alemanha" not in mp.render_size_aware(
              de_only, total_eligible=len(de_only),
              generated_at="2026-10-14T09:35:00Z", eu=[], lang="pt"))


def test_page_structural_contract() -> None:
    print("== P4: contrato estrutural — TODA montagem repassa eu= ==")
    src = Path(mp.__file__).read_text(encoding="utf-8")
    n_mat = src.count("materials=materials")
    n_eu = src.count("eu=eu")
    check(f"arquivo: eu=eu em TODA montagem que tem materials= ({n_eu}/{n_mat})",
          n_eu >= n_mat, f"materials={n_mat}, eu={n_eu}")
    # a bomba-relógia específica do bug: DENTRO de render_size_aware,
    # cada chamada de render_minimal_html repassa as DUAS seções.
    fn_src = None
    import inspect
    fn_src = inspect.getsource(mp.render_size_aware)
    check("render_size_aware: eu=eu tantas vezes quanto materials=materials",
          fn_src.count("eu=eu") == fn_src.count("materials=materials"),
          f"materials={fn_src.count('materials=materials')}, "
          f"eu={fn_src.count('eu=eu')}")
    check("render_size_aware: >= 3 montagens na cadeia (com snippets/sem/🎯)",
          fn_src.count("materials=materials") >= 3)


# ---------------------------------------------------------------------------
# D — digest (extratores + compactador F6.1)
# ---------------------------------------------------------------------------

def test_section_extractors() -> None:
    print("== D1: extratores 🧪/🇪🇺 (padrão F13: header + corpo até o blank) ==")
    digest = [
        "", "🎯 Perfil e critérios ativos", "Score do run: min 3 · máx 16",
        "", "🧪 Perfil Materials Engineering (ranking próprio, mesmas vagas elegíveis)",
        "Top 5:", "  1. Vaga Mat 1 — Empresa (mat 8.5)",
        "  2. Vaga Mat 2 — Empresa (mat 8.0)",
        "", "🇪🇺 Perfil EU non-DE (ranking próprio, mesmas vagas elegíveis)",
        "Top 5:", "  1. Vaga EU 1 — Empresa (eu 15.0)",
        "", "⚡ Top 5 do dia (candidatura direta)",
        "1. A — B — 12.5 — https://x/a",
        "", "🔗 Ranking completo: https://y/",
    ]
    mat = rg.materials_section_lines(digest)
    check("🧪: header + corpo até o próximo blank",
          mat == [digest[4], "Top 5:", "  1. Vaga Mat 1 — Empresa (mat 8.5)",
                  "  2. Vaga Mat 2 — Empresa (mat 8.0)"], f"{mat}")
    eu = rg.eu_section_lines(digest)
    check("🇪🇺: header + corpo até o próximo blank",
          eu == [digest[9], "Top 5:", "  1. Vaga EU 1 — Empresa (eu 15.0)"],
          f"{eu}")
    check("seção ausente → [] (honestidade)",
          rg.materials_section_lines(["🎯 Perfil"]) == []
          and rg.eu_section_lines(["🎯 Perfil"]) == [])
    check("lista vazia/None → [] sem erro",
          rg.materials_section_lines([]) == []
          and rg.eu_section_lines([]) == [])
    check("seção no FIM da lista (sem blank seguinte) → corpo inteiro",
          rg.eu_section_lines(["🇪🇺 Perfil EU non-DE (x)", "  1. A"])
          == ["🇪🇺 Perfil EU non-DE (x)", "  1. A"])
    check("extrator NÃO relambda em seção repetida (primeira vence)",
          rg.materials_section_lines(digest + ["", digest[4]])
          .count(digest[4]) == 1)


def test_prefix_contract() -> None:
    print("== D2: prefixo constante == header real das seções ==")
    # contrato (padrão test_f61): o header que a seção EMITE é o prefixo
    # que o extrator RECONHECE — evoluir o sufixo nunca quebra o compact.
    check("MATERIALS_SECTION_PREFIX == header emitido por materials_lines",
          rg.MATERIALS_SECTION_PREFIX.startswith("🧪 Perfil Materials Engineering"))
    check("EU_SECTION_PREFIX == header emitido por eu_lines",
          rg.EU_SECTION_PREFIX.startswith("🇪🇺 Perfil EU non-DE"))
    # shape real 14/10: top-3 do estrato EU medido no dia (referência
    # onda-b-estado.md §BUG F36.1) — empresas REAIS, campos mínimos.
    real_shape = [
        {"id": "fx|eu:1", "title": "Supply Chain Intern", "company": "Resmed",
         "location": "Amsterdam, NL", "country_iso": "nl",
         "description": "Procurement and planning."},
        {"id": "fx|eu:2", "title": "Logistics Intern", "company": "Parfumado",
         "location": "Brussels, BE", "country_iso": "be",
         "description": "Fragrance supply chain."},
        {"id": "fx|eu:3", "title": "Procurement Intern",
         "company": "JACOBSDOUWEEGBERTS", "location": "Luxembourg, LU",
         "country_iso": "lu", "description": "Public procurement."},
    ]
    eu_sec = rg.eu_lines(real_shape, [])
    check("eu_lines: header VERBATIM reconhecido pelo extrator (caso real 14/10)",
          eu_sec and eu_sec[0].startswith(rg.EU_SECTION_PREFIX),
          eu_sec[0][:60] if eu_sec else "[]")
    check("extrator pega a seção REAL inteira (header + corpo)",
          rg.eu_section_lines([""] + eu_sec) == eu_sec)
    mat_sec = rg.materials_lines(
        [{**j, "country_iso": "de", "location": "Berlin, DE"} for j in real_shape],
        [])
    check("materials_lines: header VERBATIM reconhecido pelo extrator",
          mat_sec and mat_sec[0].startswith(rg.MATERIALS_SECTION_PREFIX),
          mat_sec[0][:60] if mat_sec else "[]")


def _digest_with_profiles(*, profile_lines: int, top5_lines=None) -> list[str]:
    """Digest gigante com seções 🧪/🇪🇺 gordas (shape do digest_sections).

    ``profile_lines`` linhas de corpo por seção de perfil — o "gordo" que
    cede espaço no compact; headers são os VERBATIM do digest real.
    """
    top5_lines = top5_lines or rg.format_top5(
        [_apply_job(i) for i in range(5)]).splitlines()
    lines = ["", "🎯 Perfil e critérios ativos"]
    lines += [f"linha de perfil {i} — " + "x" * 200 for i in range(14)]
    lines += ["", "🆕 Novas vagas no Top 30 (30):"]
    lines += [f"  #{i} — vaga nova {i} — Acme (12.5)" for i in range(1, 31)]
    lines += ["", rg.MATERIALS_SECTION_PREFIX]
    lines += [f"  {p}. Vaga Mat {p} — Empresa (mat 8.5)"
              for p in range(1, profile_lines + 1)]
    lines += ["", rg.EU_SECTION_PREFIX]
    lines += [f"  {p}. Vaga EU {p} — Empresa (eu 13.5)"
              for p in range(1, profile_lines + 1)]
    lines += ["", "⚡ Top 5 do dia (candidatura direta)"] + top5_lines
    lines += ["", "🔗 Ranking completo (todas as vagas elegíveis): "
             "https://rios-vini.github.io/internship-finder/"]
    return lines


def test_compact_keeps_profile_headers() -> None:
    print("== D3: digest >4096 com 🧪/🇪🇺 gordas → headers sobrevivem ==")
    digest = _digest_with_profiles(profile_lines=40)
    check("digest do fixture estoura 4096 (como no dia do bug)",
          len("\n".join(digest)) > rd.TELEGRAM_MAX_LEN,
          f"{len('}'.join([])) or len(chr(10).join(digest))} chars")
    msg = rd.build_message(_summary(), _base_alerts(), 2, always_notify=True,
                           disk_pct=90, digest_lines=digest)
    check("mensagem compactada cabe no Telegram",
          len(msg) <= rd.TELEGRAM_MAX_LEN, f"{len(msg)} chars")
    check("header 🧪 Perfil Materials sobrevive ao compact",
          "Perfil Materials" in msg)
    check("header 🇪🇺 Perfil EU non-DE sobrevive ao compact",
          "Perfil EU non-DE" in msg)
    check("ordem de preservação: 🧪 antes de 🇪🇺 (ordem do digest)",
          msg.index("Perfil Materials") < msg.index("Perfil EU non-DE"))
    check("CORPO das seções cede espaço (vagas fora, header fica)",
          "Vaga Mat" not in msg and "Vaga EU" not in msg)
    check("⚡ Top 5 do dia preservado com as 5 apply_urls",
          "⚡ Top 5 do dia" in msg
          and msg.count("https://apply.example.com/") == 5)
    check("🔗 link do ranking por último",
          msg.endswith("🔗 Ranking completo (todas as vagas elegíveis): "
                       "https://rios-vini.github.io/internship-finder/"))
    check("base operacional integra (problemas detalhados)",
          "Problemas detectados" in msg and "Lidl" in msg)


def test_compact_fits_regression_zero() -> None:
    print("== D4: digest que CABE → base + digest byte a byte (regressão zero) ==")
    digest = ["", "🎯 Perfil e critérios ativos", "Score do run: min 3 · máx 16",
              "", "🧪 Perfil Materials Engineering (ranking próprio)",
              "Top 5:", "  1. Vaga Mat 1 — Empresa (mat 8.5)",
              "", "🇪🇺 Perfil EU non-DE (ranking próprio)",
              "Top 5:", "  1. Vaga EU 1 — Empresa (eu 15.0)",
              "", "⚡ Top 5 do dia (candidatura direta)",
              "1. A — B — 12.5 — https://apply.example.com/1",
              "", "🔗 Ranking completo: https://x/"]
    base = rd.build_message(_summary(eligible=50, total=400, n_fail=0), [], 0,
                            always_notify=True)
    msg = rd.build_message(_summary(eligible=50, total=400, n_fail=0), [], 0,
                           always_notify=True, digest_lines=digest)
    check("mensagem com digest que cabe == base + digest (byte a byte)",
          msg == base + "\n" + "\n".join(digest))
    check("seções 🧪/🇪🇺 inteiras presentes (sem compact, sem colapso)",
          "Vaga Mat 1" in msg and "Vaga EU 1" in msg)
    check("sem marcador de encurtamento", "encurtado" not in msg)


def test_compact_without_profiles() -> None:
    print("== D5: digest estourado SEM 🧪/🇪🇺 → ausência honesta, sem blank duplo ==")
    digest = ["", "🎯 Perfil e critérios ativos"]
    digest += [f"linha de perfil {i} — " + "x" * 200 for i in range(20)]
    digest += ["", "🆕 Novas vagas no Top 30 (30):"]
    digest += [f"  #{i} — vaga nova {i} — Acme (12.5)" for i in range(1, 31)]
    digest += ["", "⚡ Top 5 do dia (candidatura direta)"]
    digest += rg.format_top5([_apply_job(i) for i in range(5)]).splitlines()
    digest += ["", "🔗 Ranking completo: https://x/"]
    msg = rd.build_message(_summary(), _base_alerts(), 2, always_notify=True,
                           disk_pct=90, digest_lines=digest)
    check("mensagem cabe", len(msg) <= rd.TELEGRAM_MAX_LEN)
    check("sem 🧪/🇪🇺 no digest → headers ausentes no compact (honestidade)",
          "Perfil Materials" not in msg and "Perfil EU non-DE" not in msg)
    check("nenhum bloco em branco duplicado (guard dos níveis)",
          "\n\n\n" not in msg)
    check("⚡ e 🔗 seguem intactos",
          "⚡ Top 5 do dia" in msg and msg.endswith("🔗 Ranking completo: https://x/"))


def test_compact_level3_keeps_headers() -> None:
    print("== D6: nível 3 do compact (linhas gigantes) → headers colapsados ==")
    # linhas de vaga de 1500 chars forçam o teto defensivo do ⚡
    # (monkeypatch do limite em runtime — padrão test_f61-e)
    giant = [f"{i}. " + "T" * 1500 for i in range(1, 6)]
    digest = ["", "🎯 Perfil"]
    digest += [f"linha {i} — " + "x" * 200 for i in range(30)]
    digest += ["", "🧪 Perfil Materials Engineering (ranking próprio, mesmas vagas elegíveis)"]
    digest += [f"  {p}. Vaga Mat {p} — Empresa (mat 8.5)" for p in range(1, 6)]
    digest += ["", "🇪🇺 Perfil EU non-DE (ranking próprio, mesmas vagas elegíveis)"]
    digest += [f"  {p}. Vaga EU {p} — Empresa (eu 13.5)" for p in range(1, 6)]
    digest += ["", "⚡ Top 5 do dia (candidatura direta)"] + giant
    digest += ["", "🔗 Ranking completo: https://x/"]
    with mock.patch.object(rg, "TOP5_TITLE_LIMIT", 1500):
        msg = rd.build_message(_summary(), _base_alerts(), 2, always_notify=True,
                               disk_pct=90, digest_lines=digest)
    check("nível 3: mensagem cabe mesmo com linhas de 1500 chars",
          len(msg) <= rd.TELEGRAM_MAX_LEN, f"{len(msg)} chars")
    check("nível 3: header 🧪 colapsado presente (1 linha)",
          "Perfil Materials" in msg and "Vaga Mat" not in msg)
    check("nível 3: header 🇪🇺 colapsado presente (1 linha)",
          "Perfil EU non-DE" in msg and "Vaga EU" not in msg)
    check("nível 3: header ⚡ preservado", "⚡ Top 5 do dia" in msg)
    check("nível 3: link por último", msg.endswith("🔗 Ranking completo: https://x/"))


def main() -> int:
    test_page_over_cap_keeps_sections()
    test_page_profile_budget_layer()
    test_page_profile_limit_default()
    test_page_under_cap()
    test_page_without_eu_data()
    test_page_structural_contract()
    test_section_extractors()
    test_prefix_contract()
    test_compact_keeps_profile_headers()
    test_compact_fits_regression_zero()
    test_compact_without_profiles()
    test_compact_level3_keeps_headers()
    print()
    if FAILURES:
        print(f"F36.1: {len(FAILURES)} FALHA(S) de {CHECKS} checks")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print(f"F36.1: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
