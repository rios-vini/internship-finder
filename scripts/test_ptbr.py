"""Testes standalone — Fase 5: camada PT-BR (glossario, rotulos, score explicado).

Cobre ``src/internship_finder/ptbr.py`` (novo) e a integracao em
``scripts/interface.py`` (render do titulo PT-BR + explicacao do breakdown):

1. ``title_pt``: traduz titulo EN e DE de forma deterministica (glossario);
   titulo sem termos traduziveis -> ``None``; decoracao de genero removida
   SOMENTE no campo derivado; o original nunca e alterado; frases de produto
   (SAP Analytics Cloud) protegidas de traducao generica.
2. ``detect_language``: marcadores fortes DE/EN -> 'de'/'en'; sem marcador
   -> None.
3. ``employment_type_pt`` / ``country_label``: rotulos PT-BR a partir dos
   campos REAIS; desconhecido -> original/None (nada inventado).
4. ``relevance_signals`` / ``penalties``: valores REAIS do breakdown do perfil
   ativo, ordenados por |valor|; negativos = penalidades; ausencia de breakdown
   -> [].
5. Render (fixture + bloco real): titulo PT-BR visivel, Original visivel com
   idioma, tipo/pais em PT-BR, "por que esta vaga?" com explicadores PT-BR por
   perfil, penalidades separadas, descricao NAO traduzida.
6. Ranking inalterado: a renderizacao nao muta as vagas nem re-ranqueia —
   ordem/score identicos ao snapshot (fixture e bloco real com
   data/eligible_jobs.json).

Padrao dos demais scripts: [OK]/[FAIL] e termina com "TUDO OK" (exit 0) ou
"FALHAS:" (exit != 0).

Uso:  .venv/bin/python scripts/test_ptbr.py
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import interface  # noqa: E402
from internship_finder import ptbr  # noqa: E402
from internship_finder.materials_ranking import rank_materials_jobs  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def test_title_pt() -> None:
    print("== title_pt: traducao deterministica por glossario ==")
    cases = [
        ("Working Student Procurement Analytics",
         "Estudante / Working Student · Compras (Procurement) · Análise de Dados"),
        ("Praktikum Data Analytics / Data Science",
         "Estágio (Praktikum) · Análise de Dados / Ciência de Dados"),
        ("Internship Supply Chain", "Estágio (Internship) · Cadeia de Suprimentos"),
        ("Werkstudent Logistik (m/w/d)", "Estudante / Working Student (Werkstudent) · Logística"),
        # Glossario ponta a termo profissional internacional preservado.
        ("Praktikum Procurement", "Estágio (Praktikum) · Compras (Procurement)"),
        ("Werkstudent Materials Engineering",
         "Estudante / Working Student (Werkstudent) · Engenharia de Materiais"),
        ("Intern Manufacturing", "Estagiário(a) (Intern) · Manufatura"),
        # Composto mais especifico vence o generico.
        ("Working Student Supply Chain Analytics",
         "Estudante / Working Student · Análise de Dados da Cadeia de Suprimentos"),
        # Decoracao de genero sai so do campo derivado.
        ("Werkstudent Data Science (w/m/x)",
         "Estudante / Working Student (Werkstudent) · Ciência de Dados"),
    ]
    for title, expect in cases:
        got = ptbr.title_pt(title)
        check(f"'{title}' -> '{expect}'", got == expect)
    check("titulo sem termos traduziveis -> None",
          ptbr.title_pt("Brand Marketing Campaign") is None)
    check("None/vazio -> None", ptbr.title_pt(None) is None and ptbr.title_pt("") is None)
    # Determinismo: mesmo titulo -> mesmo resultado (chamadas repetidas).
    t = "Working Student Procurement Analytics"
    check("deterministico (chamadas repetidas)",
          ptbr.title_pt(t) == ptbr.title_pt(t) == ptbr.title_pt(t))
    # Frase de produto NAO traduz "Analytics" genérico.
    check("produto protegido (SAP Analytics Cloud)",
          "Análise de Dados" not in (ptbr.title_pt("Working Student SAP Analytics Cloud") or ""))
    # O original nunca e alterado pela funcao.
    orig = "Werkstudent Logistik (m/w/d)"
    ptbr.title_pt(orig)
    check("funcao pura (nao muta o input)", orig == "Werkstudent Logistik (m/w/d)")


def test_detect_language() -> None:
    print("== detect_language: marcadores fortes, sem stoplist ==")
    check("titulo DE -> 'de'", ptbr.detect_language("Praktikum Data Analytics / Data Science") == "de")
    check("Werkstudent DE -> 'de'", ptbr.detect_language("Werkstudent - Logistik / Supply Chain") == "de")
    check("titulo EN -> 'en'", ptbr.detect_language("Working Student Procurement Analytics") == "en")
    check("Internship EN -> 'en'", ptbr.detect_language("Internship Analytics Advisory (all genders)") == "en")
    check("sem marcador -> None", ptbr.detect_language("Brand Marketing Campaign") is None)
    check("None -> None", ptbr.detect_language(None) is None)


def test_fields_pt() -> None:
    print("== employment_type_pt / country_label (rotulos PT-BR reais) ==")
    for raw, expect in [("FULL_TIME", "Período integral"), ("PART_TIME", "Meio período"),
                        ("INTERN", "Estágio"), ("CONTRACT", "Contrato"),
                        ("full_time", "Período integral")]:
        check(f"employment_type {raw!r} -> {expect!r}", ptbr.employment_type_pt(raw) == expect)
    check("employment_type None -> ''", ptbr.employment_type_pt(None) == "")
    check("employment_type desconhecido -> original",
          ptbr.employment_type_pt("SUPER_FLEX") == "SUPER_FLEX")
    check("country de -> Alemanha", ptbr.country_label("de") == "Alemanha")
    check("country DE (case) -> Alemanha", ptbr.country_label("DE") == "Alemanha")
    check("country desconhecido -> None", ptbr.country_label("zz") is None)
    check("country None -> None", ptbr.country_label(None) is None)


# Fixture minima de vaga ranqueada (mesmo formato do snapshot real).
def _job(**kw) -> dict:
    base = {
        "id": "x", "title": "Working Student Procurement Analytics", "company": "Co",
        "location": "Berlin, DE", "country_iso": "de", "remote": None,
        "url": "https://jobs.example/x", "employment_type": "FULL_TIME",
        "internship": True,
        "score": 9.5,
        "score_breakdown": {"area": 6.0, "skills": 0.75, "language": 2.0,
                            "type": 1.0, "location": 1.0, "penalties": -0.4},
        "materials_score": 4.0,
        "materials_breakdown": {"materials": 2.5, "adjacent": 0.0, "context": 0.0,
                                "type": 1.0, "location": 1.0, "penalties": -1.5},
        "description": "You support the procurement team. English required.",
    }
    base.update(kw)
    return base


def test_relevance_signals() -> None:
    print("== relevance_signals / penalties: valores REAIS do breakdown ==")
    j = _job()
    sig = ptbr.relevance_signals(j, profile="biz")
    # 6 componentes != 0: area, language, type, location, skills, penalties.
    check("6 sinais (todos os componentes != 0)", len(sig) == 6)
    # Ordenado por |valor| desc (empate 1.0 desempata por chave asc).
    check("ordem por |valor| desc", [s["key"] for s in sig]
          == ["area", "language", "location", "type", "skills", "penalties"])
    check("valores sao os REAIS do breakdown",
          {s["key"]: s["value"] for s in sig} == {
              "area": 6.0, "skills": 0.75, "language": 2.0, "type": 1.0,
              "location": 1.0, "penalties": -0.4})
    check("rotulo PT-BR presente", all(s["label"] for s in sig))
    pen = ptbr.penalties(j, profile="biz")
    check("penalidades so negativas", len(pen) == 1 and pen[0]["value"] == -0.4
          and pen[0]["kind"] == "neg" and pen[0]["key"] == "penalties")
    # Perfil Materials: componentes proprios.
    sig_mat = ptbr.relevance_signals(j, profile="mat")
    check("perfil mat usa materials_breakdown", {s["key"] for s in sig_mat}
          == {"materials", "type", "location", "penalties"})
    check("penalidade mat == -1.5", ptbr.penalties(j, profile="mat")[0]["value"] == -1.5)
    check("sem breakdown -> []", ptbr.relevance_signals({}, profile="biz") == [])
    check("breakdown vazio -> []", ptbr.relevance_signals({"score_breakdown": {}}, profile="biz") == [])


def _render(jobs: list[dict], **kw) -> str:
    base = dict(total=len(jobs), source_label="fixture.json", filters_desc=[],
                generated_at="2026-09-08T00:00:00Z")
    base.update(kw)
    return interface.render_html(jobs, **base)


def test_render_ptbr() -> None:
    print("== render: titulo PT-BR, Original, tipo/pais, explicação, penalidades ==")
    j = _job()
    page = _render([j])
    # PT-BR visivel + tag.
    check("titulo PT-BR renderizado",
          'class="tag tag-pt">PT-BR</span>' in page
          and "Estudante / Working Student · Compras (Procurement) · Análise de Dados" in page)
    # Original sempre visivel, com idioma.
    check("Original rotulado com idioma",
          'class="tag tag-orig">Original (EN)</span>' in page
          and "Working Student Procurement Analytics" in page)
    # Tipo e pais em PT-BR nos fatos.
    check("tipo do anuncio em PT-BR (com original entre parenteses)",
          "tipo do anúncio: Período integral (FULL_TIME)" in page)
    check("pais em PT-BR", "país: Alemanha" in page)
    # Explicacao do score: rotulos PT-BR + detalhe por componente.
    check("explicadores PT-BR no breakdown",
          'class="bd-l">Área</span>' in page and "termos da área alvo" in page)
    check("penalidades separadas em seccao dedicada",
          'class="bd-pen"' in page and "-0.40" in page)
    check("total do breakdown intacto", "Total <b>9.50</b>" in page)
    # Descricao NAO traduzida: texto original permanece sem traducao.
    check("descricao original preservada (sem traducao)",
          "You support the procurement team." in page
          and 'class="tag tag-orig">Original</span>' in page)
    # Vaga sem campos opcionais: nao quebra, nao inventa.
    page2 = _render([_job(employment_type=None, description=None, country_iso=None,
                          application_deadline=None)])
    check("vaga sem campos opcionais renderiza (sem fatos inventados)",
          "país: " not in page2 and "tipo do anúncio: " not in page2)
    # Perfil Materials na mesma pagina usa os explicadores proprios.
    mats = rank_materials_jobs([j])
    mat_rank_map = {str(m["id"]): i for i, m in enumerate(mats, 1)}
    page3 = _render([j], materials=mats, materials_rank_map=mat_rank_map,
                    materials_stats=interface._compute_stats(
                        mats, total=1, score_key="materials_score"))
    check("explicadores do perfil Materials (proprios)",
          "termos do núcleo de materiais" in page3
          and "função de negócio no título" in page3)


def test_ranking_unchanged() -> None:
    print("== ranking inalterado: render nao muta nem re-ranqueia ==")
    jobs = [_job(id=f"j{i}") for i in range(3)]
    before = copy.deepcopy(jobs)
    _render(jobs)
    check("render_html nao muta as vagas (sem chaves/valores novos)",
          jobs == before)
    # Ordem/score preservados na serializacao da pagina (data-score).
    page = _render(jobs)
    scores = re.findall(r'data-score="([\d.]+)"', page)
    check("data-score == score do snapshot em ordem",
          [float(s) for s in scores] == [9.5, 9.5, 9.5])
    # Determinismo total: duas renderizacoes identicas.
    check("render deterministico (2 chamadas identicas)",
          _render(jobs) == _render(jobs))


def test_real_snapshot() -> None:
    print("== bloco real (data/eligible_jobs.json): PT-BR + ranking intacto ==")
    json_path = ROOT / "data" / "eligible_jobs.json"
    if not json_path.exists():
        print("  [SKIP] data/eligible_jobs.json ausente (runner limpo)")
        return
    data = json.loads(json_path.read_text(encoding="utf-8"))
    n = len(data)
    check("snapshot lista nao vazia", isinstance(data, list) and n > 0)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="t_ptbr_") as td:
        out = Path(td) / "index.html"
        rc = interface.main(["--input", "data/eligible_jobs.json", "--top", "100000",
                             "--output", str(out)])
        page = out.read_text(encoding="utf-8")
    check("gera pagina de dois perfis (rc 0)", rc == 0 and len(page) > 100_000)
    # PT-BR coberto? titulos traduziveis devem exibir tag PT-BR nas duas tabelas.
    n_tx = sum(1 for j in data if ptbr.title_pt(j.get("title")))
    check(f"tag PT-BR nas duas tabelas ({n_tx} titulos traduziveis)",
          page.count('class="tag tag-pt">PT-BR</span>') == 2 * n_tx)
    # Original SEMPRE visivel (uma tag Original por linha, nas duas tabelas):
    check("tag Original em todas as linhas",
          page.count('class="tag tag-orig"') >= 2 * n)
    # Ranking intacto: ordem dos titulos na tabela biz == ordem do snapshot.
    biz_body = page.split('<table id="tbl-biz"')[1].split("</tbody>")[0]
    mat_body = page.split('<table id="tbl-mat"')[1].split("</tbody>")[0]
    import html as _html
    expect_biz = [_html.escape(str(j.get("title") or "")) for j in data]
    mats = rank_materials_jobs(data)
    expect_mat = [_html.escape(str(j.get("title") or "")) for j in mats]
    titles_biz = re.findall(r'data-title="([^"]*)"', biz_body)
    titles_mat = re.findall(r'data-title="([^"]*)"', mat_body)
    check("ordem do principal == ranking do pipeline (intacto)",
          titles_biz == expect_biz)
    check("ordem do materials == ranking materials (intacto)",
          titles_mat == expect_mat)


def main() -> int:
    test_title_pt()
    test_detect_language()
    test_fields_pt()
    test_relevance_signals()
    test_render_ptbr()
    test_ranking_unchanged()
    test_real_snapshot()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())