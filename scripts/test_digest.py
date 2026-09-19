"""Testes do digest do ranking (scripts/test_digest.py) — Fase 2.

Standalone e OFFLINE (tempfile, sem rede, sem ``data/`` real): leitura
defensiva do ranking, comparacao com o snapshot anterior (nova vaga vs vaga
que subiu — o conceito central da Fase 2), mudancas no Top 30 (entrou/saiu/
movimentos), estatisticas de score, derivacao da URL estavel do GitHub Pages,
perfil/criterios ativos LIDOS das constantes vivas (filters/ranking — sem
regra duplicada) e montagem das secoes do digest. Tambem confere o invariante
de que o default de pais do digest espelha o default do CLI (``cli.py``).

Uso:

    .venv/bin/python scripts/test_digest.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ranking_digest as rdg  # noqa: E402
from internship_finder import filters as filters_mod  # noqa: E402
from internship_finder import ranking as ranking_mod  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def _job(jid: str, title: str, score: float, url: str | None = None) -> dict:
    return {
        "id": jid, "title": title, "company": "Acme", "location": "Berlin, DE",
        "score": score, "url": url or f"https://example.com/{jid}",
    }


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_load_ranking() -> None:
    print("== load_ranking (defensivo) ==")
    with tempfile.TemporaryDirectory(prefix="t_dg_load_") as tmp:
        base = Path(tmp)
        p = base / "eligible_jobs.json"
        _write(p, [_job("a", "A", 4.0), _job("b", "B", 3.0)])
        data = rdg.load_ranking(p)
        check("lista validar lida em ordem", len(data) == 2 and data[0]["id"] == "a")
        check("arquivo ausente -> []", rdg.load_ranking(base / "nao_existe.json") == [])
        p.write_text("{corrupto", encoding="utf-8")
        check("JSON malformado -> []", rdg.load_ranking(p) == [])
        _write(p, {"not": "a list"})
        check("JSON nao-lista -> []", rdg.load_ranking(p) == [])
        _write(p, [{"title": "sem id"}, _job("c", "C", 2.0)])
        filtered = rdg.load_ranking(p)
        check("entradas sem id descartadas (as validas ficam)",
              len(filtered) == 1 and filtered[0]["id"] == "c")
        _write(p, [])
        check("lista vazia -> []", rdg.load_ranking(p) == [])


def test_top_positions() -> None:
    print("== top_positions (posicao 1-based) ==")
    ranking = [_job(f"j{i}", f"T{i}", 10 - i) for i in range(5)]
    top3 = rdg.top_positions(ranking, 3)
    check("3 primeiros com posicao 1-based",
          top3 == [(1, ranking[0]), (2, ranking[1]), (3, ranking[2])])
    check("cap respeitado com n > tamanho",
          len(rdg.top_positions(ranking, 99)) == 5)


def test_new_top_entries() -> None:
    print("== novas vagas no Top 30 vs vagas antigas que subiram ==")
    prev = [ _job("old-1", "Antiga top", 9.0),
             _job("old-2", "Antiga top2", 8.5),
             _job("climber", "Antiga fora do top 30", 7.0),
             _job("old-3", "Antiga top3", 8.0), ]
    cur = [
        _job("fresh", "Nova vaga", 10.0),          # nova + top 30 -> NOVAS
        _job("climber", "Antiga fora do top 30", 7.0),  # antiga, subiu -> NAO e nova
        _job("old-2", "Antiga top2", 8.5),         # antiga, ja estava -> NAO e nova
        _job("old-1", "Antiga top", 9.0),
        _job("old-3", "Antiga top3", 8.0),
        _job("fresh-2", "Nova vaga 2", 6.5),       # nova, na posicao 6
    ]
    novas = rdg.new_top_entries(cur, prev, top=3)
    check("so a vaga nova no Top 3 e listada",
          [(p, j["id"]) for p, j in novas] == [(1, "fresh")])
    novas6 = rdg.new_top_entries(cur, prev, top=6)
    check("nova fora do corte de top nao aparece (top=3)",
          "fresh-2" not in [j["id"] for _, j in novas])
    check("nova dentro do corte aparece com posicao real (top=6)",
          [(p, j["id"]) for p, j in novas6] == [(1, "fresh"), (6, "fresh-2")])
    check("vaga antiga que subiu NAO e 'nova'",
          "climber" not in [j["id"] for _, j in novas6])


def test_ranking_changes() -> None:
    print("== mudancas no Top 30 (entrou/saiu/movimentos) ==")
    prev = [_job(f"p{i}", f"P{i}", 9.0 - i) for i in range(10)]  # p0..p9 (pos 1..10)
    # cur: p8 salta para o topo (pos 9 -> 1), p0 cai para o fim (pos 1 -> 9);
    # os demais ficam nas mesmas posicoes.
    cur = [prev[8], prev[1], prev[2], prev[3], prev[4],
           prev[5], prev[6], prev[7], prev[0], prev[9]]
    changes = rdg.ranking_changes(cur, prev, top=10, min_delta=5, max_movers=3)
    check("sem entradas/saidas (mesmo conjunto de ids)",
          changes["entered"] == [] and changes["exited"] == [])
    movers = [(j["id"], p, c) for j, p, c in changes["movers"]]
    check("p8 subiu 8 posicoes (pos 9 -> 1)", ("p8", 9, 1) in movers)
    check("p0 caiu 8 posicoes (pos 1 -> 9)", ("p0", 1, 9) in movers)
    check("movimento pequeno (p1: pos 2 -> 2, delta 0) nao listado",
          all(j["id"] != "p1" for j, _, _ in changes["movers"]))
    check("apenas os 2 movimentos reais (max_movers=3 nao corta)",
          len(changes["movers"]) == 2)
    # bug classico: mesma POSICAO com vagas diferentes nao pode virar mover
    prev2 = [_job("x1", "X1", 9.0), _job("x2", "X2", 8.0), _job("x3", "X3", 7.0)]
    cur2 = [_job("y1", "Y1", 9.0), _job("x2", "X2", 8.0), _job("y3", "Y3", 7.0)]
    ch2 = rdg.ranking_changes(cur2, prev2, top=3, min_delta=1)
    check("entered/exited por ID (posicao 1 troca de vaga -> entered+exited)",
          {j["id"] for _, j in ch2["entered"]} == {"y1", "y3"}
          and {j["id"] for _, j in ch2["exited"]} == {"x1", "x3"})
    check("mesma posicao com vaga diferente nao gera mover fantasma",
          ch2["movers"] == [])
    # determinismo com deltas empatados (ordem estavel por |delta|, depois id)
    prev3 = [_job("qa", "QA", 9.0), _job("qb", "QB", 8.0), _job("qc", "QC", 7.0)]
    cur3 = [prev3[1], prev3[2], prev3[0]]  # pos: qb 1, qc 2, qa 3
    ch3 = rdg.ranking_changes(cur3, prev3, top=3, min_delta=1, max_movers=5)
    check("determinismo de movers (ordem por |delta|, depois id)",
          [(j["id"], p, c) for j, p, c in ch3["movers"]]
          == [("qa", 1, 3), ("qb", 2, 1), ("qc", 3, 2)])


def test_score_stats() -> None:
    print("== score_stats ==")
    ranking = [_job("a", "A", 1.0), _job("b", "B", 6.25), _job("c", "C", 17.5),
               _job("d", "D", 6.25)]
    stats = rdg.score_stats(ranking)
    check("min/mediana/max corretos (par: mediana 6.25)",
          stats and stats["min"] == 1.0 and stats["max"] == 17.5
          and stats["median"] == 6.25 and stats["count"] == 4)
    stats3 = rdg.score_stats(ranking[:3])
    check("mediana impar = elemento central", stats3 and stats3["median"] == 6.25)
    check("sem scores -> None", rdg.score_stats([_job("a", "A", None)]) is None)
    check("lista vazia -> None", rdg.score_stats([]) is None)


def test_pages_url() -> None:
    print("== pages_url (derivacao + fallback) ==")
    check("origin https com .git",
          rdg.pages_url("https://github.com/rios-vini/internship-finder.git")
          == "https://rios-vini.github.io/internship-finder/")
    check("origin ssh (git@)",
          rdg.pages_url("git@github.com:outro-owner/meu-repo.git")
          == "https://outro-owner.github.io/meu-repo/")
    check("origin com subcaminho ignorado",
          rdg.pages_url("https://github.com/a/b.git/extra") == "https://a.github.io/b/")
    check("sem origin -> fallback", rdg.pages_url(None) == rdg.PAGES_URL_FALLBACK)
    check("origin nao-github -> fallback",
          rdg.pages_url("https://gitlab.com/a/b.git") == rdg.PAGES_URL_FALLBACK)
    check("fallback e URL https valida de Pages",
          rdg.PAGES_URL_FALLBACK.startswith("https://")
          and rdg.PAGES_URL_FALLBACK.endswith("/"))


def test_profile_lines() -> None:
    print("== perfil/criterios ativos (constantes vivas, sem duplicacao) ==")
    lines = rdg.profile_lines()
    joined = " | ".join(lines)
    check("secao de perfil presente", "🎯 Perfil e critérios ativos" in lines[0])
    check("localizacao principal Germany (spec 'de')",
          "Germany" in joined and "'de'" in joined)
    check("rotulos de area primaria do filtro (canonicos e compactos)",
          "Supply Chain" in joined and "Procurement/Purchasing" in joined
          and "BI" in joined and "Analytics" in joined
          and "Automação de Processos (RPA)" in joined)
    check("contagem de marcadores de tipo == constantes vivas",
          f"{len(filters_mod.STUDENT_TYPE_PATTERNS)} marcadores" in joined)
    check("contagem de exclusoes == constantes vivas",
          f"({len(filters_mod.TYPE_EXCLUSION_PATTERNS) + len(filters_mod.PROGRAM_EXCLUSION_PATTERNS)} padrões)" in joined)
    check("sinais refletem os pesos VIVOS do ranking",
          f"+{ranking_mod.WEIGHT_AREA_TITLE:g}" in joined
          and f"+{ranking_mod.WEIGHT_LANG_EN:g}" in joined
          and f"+{ranking_mod.WEIGHT_DE_EXPLICIT:g}" in joined)
    check("penalidades vivas",
          f"({ranking_mod.PENALTY_SENIOR:g})" in joined
          and f"({ranking_mod.PENALTY_MANAGER:g})" in joined)
    check("um rotulo por area (variantes agrupadas no mesmo rotulo)",
          joined.count("Procurement/Purchasing") == 1
          and "Procurement (Einkauf)" not in joined)


def test_default_country_espelha_cli() -> None:
    print("== invariante: spec de pais do digest == default do CLI ==")
    cli_source = Path(__file__).resolve().parent.parent / "src" / "internship_finder" / "cli.py"
    text = cli_source.read_text(encoding="utf-8")
    check("cli.py declara --country default 'de'",
          'default="de"' in text)
    check("digest.DEFAULT_COUNTRY_SPEC == 'de'",
          rdg.DEFAULT_COUNTRY_SPEC == "de")


def _fixture_files(tmp: Path, current: list[dict], previous: list[dict]):
    cur_path = tmp / "eligible_jobs.json"
    prev_path = tmp / "previous.json"
    _write(cur_path, current)
    _write(prev_path, previous)
    return cur_path, prev_path


def test_digest_sections() -> None:
    print("== digest_sections (montagem completa) ==")
    with tempfile.TemporaryDirectory(prefix="t_dg_full_") as tmp:
        base = Path(tmp)
        url = "https://owner.github.io/repo/"
        # cenario: 1 vaga nova no topo + 1 antiga que estava FORA do top 4 e
        # subiu para dentro + 1 que saiu (as antigas dentro nao mudam de top)
        previous = [
            _job("old-top", "Antiga top", 9.0, "https://ex.com/old-top"),
            _job("stable-a", "Estavel A", 6.0),
            _job("stable-b", "Estavel B", 6.5),
            _job("leaver", "Vai sair do top", 6.5),
            _job("climber", "Antiga fora do top", 7.0),
        ]
        current = [
            _job("fresh", "Nova vaga", 12.0, "https://ex.com/fresh"),
            _job("climber", "Antiga fora do top", 7.0),
            _job("old-top", "Antiga top", 9.0, "https://ex.com/old-top"),
            _job("stable-a", "Estavel A", 6.0),
            _job("stable-b", "Estavel B", 6.5),
        ]
        cur_path, prev_path = _fixture_files(base, current, previous)
        sections = rdg.digest_sections(cur_path, prev_path, pages_url=url, top=4)
        check("secoes montadas", sections is not None)
        text = "\n".join(sections or [])
        check("perfil antes de novas (ordem do enunciado)",
              text.index("🎯 Perfil") < text.index("🆕 Novas vagas"))
        check("novas antes do Top 5",
              text.index("🆕 Novas vagas") < text.index("🏆 Top 5"))
        check("Top 5 antes das mudancas",
              text.index("🏆 Top 5") < text.index("📈 Mudanças"))
        check("mudancas antes da secao materials (Fase 4)",
              text.index("📈 Mudanças") < text.index("🧪 Perfil Materials"))
        check("secao materials antes do link",
              text.index("🧪 Perfil Materials") < text.index("🔗 Ranking completo"))
        check("link do ranking completo e a ULTIMA linha",
              (sections or [])[-1] == f"🔗 Ranking completo (todas as vagas elegíveis): {url}")
        check("Top 5 materials com score proprio (mat)",
              "Top 5:" in text and "(mat " in text)
        check("vaga nova listada com posicao, titulo, score e link",
              "#1 — Nova vaga — Acme — Berlin — 12" in text
              and "https://ex.com/fresh" in text)
        slice_novas = text[text.index("🆕 Novas vagas"):text.index("🏆 Top 5")]
        check("vaga antiga que subiu NAO esta na secao 'novas'",
              "Antiga fora do top" not in slice_novas)
        check("vaga antiga que subiu aparece em 'Entraram no Top 30'",
              "Entraram no Top 30:" in text and "Antiga fora do top" in text)
        check("vaga que saiu aparece em 'Saíram do Top 30'",
              "Saíram do Top 30:" in text and "Vai sair do top" in text)
        check("Top 5 lista as primeiras posicoes",
              "🏆 Top 5 atual" in text and "1. Nova vaga — Acme (12)" in text)
        check("linha de score do run presente (mediana de 5 valores)",
              "Score do run: min 6 · mediana 7 · máx 12 (5 vagas elegíveis)" in text)

        # sem snapshot anterior (primeiro digest): nao trata tudo como novo
        cur_path2, _ = _fixture_files(base, previous, [])
        sections2 = rdg.digest_sections(cur_path2, Path(tmp) / "previous.json",
                                        pages_url=url, top=4)
        text2 = "\n".join(sections2 or [])
        check("sem snapshot: aviso 'primeiro digest' presente",
              "Sem snapshot do run anterior" in text2)
        check("sem snapshot: secoes de novas/mudancas ausentes",
              "🆕 Novas vagas" not in text2 and "📈 Mudanças" not in text2)
        check("sem snapshot: Top 5 e link continuam",
              "🏆 Top 5 atual" in text2
              and text2.rstrip().endswith(f"🔗 Ranking completo (todas as vagas elegíveis): {url}"))
        check("sem snapshot: secao materials so com Top 5 (sem novas)",
              "🧪 Perfil Materials" in text2
              and "Novas no Top 30 Materials" not in text2)

        # ranking atual vazio -> None (sem digest)
        cur3, _ = _fixture_files(base, [], previous)
        check("ranking atual vazio -> None",
              rdg.digest_sections(cur3, prev_path, pages_url=url) is None)


def test_mensagem_sem_novas() -> None:
    print("== secao 'novas' vazia e honesta ==")
    with tempfile.TemporaryDirectory(prefix="t_dg_empty_") as tmp:
        base = Path(tmp)
        prev = [_job("a", "A", 5.0), _job("b", "B", 4.0)]
        cur = prev[:]  # mesmas vagas
        cur_path, prev_path = _fixture_files(base, cur, prev)
        sections = rdg.digest_sections(cur_path, prev_path,
                                       pages_url="https://x.github.io/r/", top=2)
        text = "\n".join(sections or [])
        check("informa explicitamente que nao ha novas",
              "— nenhuma vaga nova no Top 30" in text)
        check("informa que nao ha mudancas relevantes",
              "— sem mudanças relevantes no Top 30" in text)


def test_digest_deterministico() -> None:
    print("== determinismo (2 execucoes identicas) ==")
    with tempfile.TemporaryDirectory(prefix="t_dg_det_") as tmp:
        base = Path(tmp)
        prev = [_job(f"p{i}", f"P{i}", 20 - i) for i in range(20)]
        cur = [_job(f"c{i}", f"C{i}", 30 - i) for i in range(5)] + prev[8:]
        cur_path, prev_path = _fixture_files(base, cur, prev)
        a = rdg.digest_sections(cur_path, prev_path,
                                pages_url="https://x.github.io/r/", top=15)
        b = rdg.digest_sections(cur_path, prev_path,
                                pages_url="https://x.github.io/r/", top=15)
        check("mesmas entradas -> mesmo texto", a is not None and a == b)


def test_materials_lines() -> None:
    print("== secao materials (Fase 4): top proprio + novas no Top 30 ==")
    cur = [
        _job("m1", "Praktikum Materials Testing", 3.0),
        _job("m2", "Working Student Battery Cell Development", 4.5),
        _job("biz1", "Werkstudent Logistik", 12.0),      # alto no principal
        _job("new1", "Praktikum Beschichtung", 5.0),      # nova, nao existia
        _job("m3", "Werkstudent Einkauf Aluminium", 6.0),  # penalizada
        _job("m4", "Intern Polymer Processing", 4.0),
        _job("m5", "Praktikum Verfahrenstechnik", 4.0),
    ]
    prev = [j for j in cur if j["id"] != "new1"]
    lines = rdg.materials_lines(cur, prev)
    text = "\n".join(lines)
    check("cabecalho do perfil materials presente",
          "🧪 Perfil Materials Engineering" in text)
    mat_order = [j["id"] for j in rdg.rank_materials_jobs(cur)]
    check("Top 5 materials segue o RANKING materials (nao o do principal)",
          "1. Praktikum Materials Testing" in text
          or mat_order[0] == "m1")
    check("'Werkstudent Logistik' (topo do principal) nao lidera materials",
          "1. Werkstudent Logistik" not in text)
    check("'Einkauf Aluminium' penalizada nao aparece no Top 5",
          "Einkauf Aluminium" not in text)
    check("nova vaga materials listada em 'Novas no Top 30 Materials'",
          "Novas no Top 30 Materials" in text and "Praktikum Beschichtung" in text)
    # mesmo conjunto -> nenhuma nova
    lines2 = rdg.materials_lines(prev, prev)
    check("sem novas -> '— nenhuma vaga nova no Top 30 Materials'",
          "— nenhuma vaga nova no Top 30 Materials" in "\n".join(lines2))
    # determinismo
    lines3 = rdg.materials_lines(cur, prev)
    check("determinismo da secao materials", lines == lines3)
    check("sem ranking atual -> []", rdg.materials_lines([], prev) == [])


def main() -> int:
    test_load_ranking()
    test_top_positions()
    test_new_top_entries()
    test_ranking_changes()
    test_score_stats()
    test_pages_url()
    test_profile_lines()
    test_default_country_espelha_cli()
    test_digest_sections()
    test_mensagem_sem_novas()
    test_materials_lines()
    test_digest_deterministico()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())