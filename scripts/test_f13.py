"""Testes da Fase F13 — radar de empresas-alvo (100% offline).

Cobre as 4 tarefas da fase sem rede e sem ``data/`` de producao:

- **T1 Watchlist**: parse de ``config/company_watchlist.json`` (formato,
  casefold, arquivo ausente/corrompido/vazio = radar OFF; empresa ausente
  do dataset = silencio).
- **T2 Radar**: ``radar_events``/``radar_lines`` — vaga nova em empresa da
  watchlist = evento (independente de score/posicao); vaga nova fora =
  nao; nenhuma nova = secao ausente; match casefold; cap 5 linhas +
  "(+N outras)"; zero eventos = secao AUSENTE (sem linha vazia).
- **T3 Digest**: secao 🎯 montada pelo ``digest_sections`` (presente com
  eventos, ausente sem), posicionada DEPOIS do ⚡ Top 5 e das 🆕, ANTES do
  link; sem watchlist_path = digest byte a byte igual ao de antes
  (regressao zero).
- **T4 Compact (o teste-chave da fase)**: mensagem >4096 com 🆕/🎯 no
  digest -> AMBAS sobrevivem no output (colapsadas para o header com
  contagem quando aperta); Top 5 integro (F12.5 intocado); link presente
  por ultimo; mensagem que cabe sai byte a byte identica (regressao
  zero); ordem de colapso 🎯 antes de 🆕.
- **T5 Toggles**: f-ws (sem Werkstudent) e f-data (Data/BI) client-side —
  data-ws/data-data nos cards, JS em node (padrao test_f6/test_f11),
  Werkstudent por TITULO (employment_type nao serve — 0 ocorrencias
  medidas), keywords data/BI por PALAVRA INTEIRA (substring casaria
  "E-Mobility"/"Elektromobilitat").
- **T6 Pagina**: secao 🎯 equivalente com cards (todos os eventos, sem
  duplicar a secao 🆕), ausente sem watchlist; tamanho < cap duro 150 KB.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
import ranking_digest as rg  # noqa: E402
import refresh_daily as rd  # noqa: E402

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

def _job(i: int, *, company=None, title=None, score=None, location=None,
         apply_url=None, iso="de") -> dict:
    return {
        "id": f"t{i}", "title": title or f"Praktikum Supply Chain {i}",
        "company": company or f"Firma {i} GmbH",
        "location": location or "Berlin, DE", "country_iso": iso,
        "score": 15.0 - (i * 0.1) if score is None else score,
        "url": f"https://jobs.example.com/{i}",
        "description": "supply chain procurement logistics " * 6,
        "raw": {"apply_url": apply_url} if apply_url else {},
    }


def _watchlist_file(base: Path, companies: list[str]) -> Path:
    path = base / "company_watchlist.json"
    path.write_text(
        json.dumps({"_comment": "teste", "companies": companies},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# T1 — watchlist parse
# ---------------------------------------------------------------------------

def test_watchlist_parse() -> None:
    section("T1: watchlist — parse/formato/casefold/ausente=OFF")
    with tempfile.TemporaryDirectory(prefix="t_f13_wl_") as tmp:
        base = Path(tmp)
        # formato real
        path = _watchlist_file(base, ["BoschGroup", "SAP", "lidlstiftup2"])
        wl = rg.load_watchlist(path)
        check("parse da lista companies", wl == ["BoschGroup", "SAP",
                                                 "lidlstiftup2"])
        # arquivo ausente -> None (radar OFF, sem erro)
        check("arquivo ausente -> None",
              rg.load_watchlist(base / "nao_existe.json") is None)
        # corrompido -> None
        bad = base / "corrompido.json"
        bad.write_text("{corrompido", encoding="utf-8")
        check("JSON corrompido -> None", rg.load_watchlist(bad) is None)
        # sem campo companies -> None
        noc = base / "sem_companies.json"
        noc.write_text(json.dumps({"x": 1}), encoding="utf-8")
        check("sem 'companies' -> None", rg.load_watchlist(noc) is None)
        # lista vazia/so strings vazias -> None (radar OFF, nao lista vazia)
        empty = _watchlist_file(base, [])
        check("companies [] -> None", rg.load_watchlist(empty) is None)
        blanks = _watchlist_file(base, ["", "   ", "12", "SAP"])
        check("strings vazias descartadas; nao-string aceito como str",
              rg.load_watchlist(blanks) == ["12", "SAP"])
        # arquivo REAL da fase carrega
        real = Path(__file__).resolve().parent.parent / "config" \
            / "company_watchlist.json"
        wl_real = rg.load_watchlist(real)
        check("watchlist real da fase carrega (>= 30 strings)",
              isinstance(wl_real, list) and len(wl_real) >= 30)
        check("watchlist real: strings EXATAS do dataset (sem case-mangle)",
              all(c == c.strip() and c for c in (wl_real or [])))


# ---------------------------------------------------------------------------
# T2 — radar: eventos e linhas
# ---------------------------------------------------------------------------

def test_radar_events() -> None:
    section("T2: radar_events — evento por vaga nova em empresa da watchlist")
    cur = [
        _job(0, company="BoschGroup", score=15.0),   # nova + watchlist
        _job(1, company="Acme GmbH", score=14.0),     # nova, fora
        _job(2, company="SAP", score=13.0),          # nova + watchlist
        _job(3, company="BoschGroup", score=12.0),   # antiga (nao-evento)
        _job(4, company="REWE Group", score=11.0),    # nova + watchlist
    ]
    prev = [dict(cur[3])]  # so t3 existia ontem
    diff = rg.new_since_previous(cur, prev)
    wl = ["BoschGroup", "SAP", "REWE Group"]
    events = rg.radar_events(diff, cur, wl)
    check("3 eventos (t0/t2/t4; t1 fora; t3 antiga nao)",
          [e["id"] for e in events] == ["t0", "t2", "t4"])
    # match casefold
    events_cf = rg.radar_events(diff, cur, ["boschgroup", "sap"])
    check("match casefold (watchlist minuscula casa)",
          [e["id"] for e in events_cf] == ["t0", "t2"])
    events_cf2 = rg.radar_events(diff, cur, ["  BOSCHGROUP  "])
    check("espacos/case da watchlist normalizados",
          [e["id"] for e in events_cf2] == ["t0"])
    # ordem oficial preservada (score desc), NAO reordenada pelo radar
    check("ordem oficial do ranking preservada",
          [e["score"] for e in events] == [15.0, 13.0, 11.0])
    # vaga nova fora da watchlist: nao-evento
    check("empresa fora da watchlist: zero eventos",
          rg.radar_events(diff, cur, ["Nao Existe Ltda"]) == [])
    # empresa da watchlist AUSENTE do dataset: silencio (nunca casa)
    check("watchlist com empresa ausente do dataset: silencio",
          rg.radar_events(diff, cur, ["SAP", "Empresa Fantasma"]) != []
          and all(e["company"] != "Empresa Fantasma"
                  for e in rg.radar_events(diff, cur, ["Empresa Fantasma"])))
    # diff None (sem snapshot): zero eventos
    check("sem snapshot -> zero eventos",
          rg.radar_events(None, cur, wl) == [])
    # watchlist None/vazia: zero eventos
    check("watchlist None -> zero eventos",
          rg.radar_events(diff, cur, None) == [])
    # nenhuma nova: zero eventos
    diff0 = rg.new_since_previous(cur, cur)
    check("nenhuma vaga nova -> zero eventos",
          rg.radar_events(diff0, cur, wl) == [])


def test_radar_lines() -> None:
    section("T2: radar_lines — header+cap 5+(+N); zero eventos = ausente")
    cur = [
        _job(i, company="BoschGroup", score=15.0 - i,
             title=f"Praktikum Einkauf {i}",
             location=f"Stuttgart {i}, DE")
        for i in range(7)
    ] + [_job(99, company="Acme GmbH", score=1.0)]
    prev = [dict(cur[-1])]  # so a Acme existia
    diff = rg.new_since_previous(cur, prev)
    wl = ["BoschGroup"]
    lines = rg.radar_lines(diff, cur, wl)
    text = "\n".join(lines)
    check("secao presente com 7 eventos", len(lines) == 1 + 5 + 1)
    check("header com contagem total (7)",
          lines[0].startswith(rg.WATCHLIST_SECTION_PREFIX)
          and "7 nova(s)" in lines[0])
    check("cap 5 linhas de vaga",
          sum(1 for ln in lines if ln.startswith("  🎯 ")) == 5)
    check("linha no formato '🎯 <empresa>: <titulo> (<local>)'",
          "🎯 1. BoschGroup: Praktikum Einkauf 0 (Stuttgart 0)" in text)
    check("(+2 outras — ver página) fecha a contagem",
          "(+2 outras — ver página)" in text)
    # zero eventos: secao AUSENTE (sem linha vazia)
    check("zero eventos -> [] (secao ausente)",
          rg.radar_lines(diff, cur, ["Nao Existe"]) == [])
    # sem watchlist/snapshot: ausente
    check("sem watchlist -> []", rg.radar_lines(diff, cur, None) == [])
    check("sem snapshot -> []", rg.radar_lines(None, cur, wl) == [])
    # max_shown parametrico
    lines2 = rg.radar_lines(diff, cur, wl, max_shown=2)
    check("max_shown=2: 2 linhas + (+5 outras)",
          sum(1 for ln in lines2 if ln.startswith("  🎯 ")) == 2
          and "(+5 outras" in "\n".join(lines2))
    # extratores para o compact
    digest = ["", rg.WATCHLIST_SECTION_HEADER + " — 7 nova(s)"] \
        + lines[1:] + ["", "🔗 Ranking completo: https://x/"]
    sec = rg.watchlist_section_lines(digest)
    check("watchlist_section_lines extrai header+corpo",
          sec[0].startswith(rg.WATCHLIST_SECTION_PREFIX) and len(sec) == 7)
    check("watchlist_section_lines: ausente -> []",
          rg.watchlist_section_lines(["", "🆕 x", ""]) == [])
    ns = rg.new_since_section_lines(
        ["", "🆕 Novas desde ontem: 3", "  1. a", "  2. b", "",
         "🎯 Empresas-alvo (watchlist)"])
    check("new_since_section_lines extrai 🆕 header+corpo",
          ns == ["🆕 Novas desde ontem: 3", "  1. a", "  2. b"])
    check("new_since_section_lines: ausente -> []",
          rg.new_since_section_lines(["x"]) == [])



# ---------------------------------------------------------------------------
# T3 — digest_sections: seção 🎯 montada (e byte a byte sem watchlist)
# ---------------------------------------------------------------------------

def test_radar_in_digest_sections() -> None:
    section("T3: digest_sections — 🎯 depois do ⚡ e das 🆕, antes do link")
    with tempfile.TemporaryDirectory(prefix="t_f13_dg_") as tmp:
        base = Path(tmp)
        cur = [
            _job(0, company="BoschGroup", score=15.0,
                 apply_url="https://apply.example.com/t0"),
            _job(1, company="Acme GmbH", score=14.0,
                 apply_url="https://apply.example.com/t1"),
            _job(2, company="SAP", score=13.0,
                 apply_url="https://apply.example.com/t2"),
        ]
        prev = [dict(cur[1])]  # t0/t2 novas
        (base / "cur.json").write_text(json.dumps(cur), encoding="utf-8")
        (base / "prev.json").write_text(json.dumps(prev), encoding="utf-8")
        wl = _watchlist_file(base, ["BoschGroup", "SAP"])

        # SEM watchlist_path (default None): sem seção 🎯 no digest
        secs_no = rg.digest_sections(base / "cur.json", base / "prev.json",
                                     pages_url="https://x/")
        check("sem watchlist_path: seção 🎯 ausente (regressão zero)",
              rg.WATCHLIST_SECTION_PREFIX
              not in "\n".join(secs_no or []))
        # com watchlist: t0 (BoschGroup) e t2 (SAP) são novas + watchlist
        with_secs = rg.digest_sections(base / "cur.json",
                                       base / "prev.json",
                                       pages_url="https://x/",
                                       watchlist_path=wl)
        text = "\n".join(with_secs or [])
        check("seção 🎯 presente com 2 eventos",
              rg.WATCHLIST_SECTION_PREFIX in text and "2 nova(s)" in text)
        check("linhas 🎯 no formato empresa: título (local)",
              "BoschGroup: Praktikum Supply Chain 0 (Berlin)" in text)
        # posicionamento: DEPOIS do ⚡ Top 5 e das 🆕, ANTES do link
        i_ns = text.find("🆕 Novas desde ontem:")
        i_t5 = text.find(rg.TOP5_SECTION_PREFIX)
        i_wl = text.find(rg.WATCHLIST_SECTION_PREFIX)
        i_lk = text.find("🔗 Ranking completo")
        check("🎯 depois das 🆕 e do ⚡, antes do link",
              -1 < i_ns < i_wl and -1 < i_t5 < i_wl < i_lk)
        check("link continua sendo a última linha",
              (with_secs or [])[-1].startswith("🔗 Ranking completo"))
        # watchlist com empresa que NÃO casa nada: seção ausente (silêncio)
        # (arquivo com NOME DISTINTO: _watchlist_file escreve sempre em
        # company_watchlist.json — reutilizar o path sobrescreveria a wl real)
        wl_off = base / "watchlist_off.json"
        wl_off.write_text(json.dumps(
            {"companies": ["Nao Existe Ltda"]}), encoding="utf-8")
        secs_off = rg.digest_sections(base / "cur.json",
                                      base / "prev.json",
                                      pages_url="https://x/",
                                      watchlist_path=wl_off)
        check("watchlist sem match: seção ausente",
              rg.WATCHLIST_SECTION_PREFIX
              not in "\n".join(secs_off or []))
        # watchlist corrompida: best-effort, seção ausente, sem erro
        bad_wl = base / "bad_wl.json"
        bad_wl.write_text("{corrompido", encoding="utf-8")
        secs_bad = rg.digest_sections(base / "cur.json",
                                      base / "prev.json",
                                      pages_url="https://x/",
                                      watchlist_path=bad_wl)
        check("watchlist corrompida: digest sai sem 🎯 e sem erro",
              isinstance(secs_bad, list)
              and rg.WATCHLIST_SECTION_PREFIX
              not in "\n".join(secs_bad))
        # diff gigante (>= NEW_SINCE_BIG_DIFF): o radar acompanha o MESMO
        # diff da 🆕 — eventos seguem a definição de "nova" (cap 5 + resto)
        big_cur = [_job(i, company="BoschGroup") for i in range(600)]
        (base / "big_cur.json").write_text(json.dumps(big_cur),
                                          encoding="utf-8")
        (base / "big_prev.json").write_text("[]", encoding="utf-8")
        secs_big = rg.digest_sections(base / "big_cur.json",
                                      base / "big_prev.json",
                                      pages_url="https://x/",
                                      watchlist_path=wl)
        t_big = "\n".join(secs_big or [])
        check("diff gigante: 🎯 lista os eventos (cap 5 + contagem)",
              rg.WATCHLIST_SECTION_PREFIX in t_big
              and "(+595 outras" in t_big)


# ---------------------------------------------------------------------------
# T4 — compact: 🆕/🎯 NUNCA mais dropadas (o teste-chave da fase)
# ---------------------------------------------------------------------------

def _summary(eligible: int = 50, total: int = 400, n_fail: int = 0) -> dict:
    ok = {"count": 3, "collected": total - n_fail}
    return {
        "run_id": "r", "source_names": {}, "ok": ok,
        "total_collected": total, "eligible": eligible, "dedup_removed": 0,
        "empty": 0, "skipped": 0, "not_found": 0,
        "timeout": [], "error": [("s", f"E{i}", "HTTP_500")
                                 for i in range(n_fail)],
    }


def test_compact_preserves_new_and_watch() -> None:
    section("T4: compact — 🆕/🎯 sobrevivem ao estouro (colapsadas se aperta)")
    # Digest no shape do digest_sections COM 🆕, ⚡ e 🎯: corpo gordo p/
    # estourar 4096 e forçar o compact.
    ns_body = [f"  {i}. {chr(64+i)} vaga nova longa — Empresa {i} — "
               f"https://apply.example.com/new/{i}" for i in range(1, 4)]
    top5 = rg.format_top5([
        _job(i, apply_url=f"https://apply.example.com/{i}")
        for i in range(5)
    ]).splitlines()
    watch_body = [
        f"  🎯 {i}. Empresa Alvo {i}: Praktikum Supply Chain {i} "
        f"(Cidade {i})" for i in range(1, 4)
    ]
    digest = (
        ["", "🎯 Perfil e critérios ativos", "Score do run: min 3 · máx 16",
         "", "🆕 Novas desde ontem: 3"] + ns_body +
        ["", rg.TOP5_SECTION_HEADER] + top5 +
        ["", rg.WATCHLIST_SECTION_HEADER + " — 3 nova(s)"] + watch_body +
        ["", "🔗 Ranking completo (todas as vagas elegíveis): https://x/"]
    )
    summary = _summary()
    msg = rd.build_message(summary, [], 0, always_notify=True,
                           digest_lines=digest)
    # (a) as duas seções presentes no output compactado
    check("🆕 sobrevive ao compact", "🆕 Novas desde ontem: 3" in msg)
    check("🎯 sobrevive ao compact",
          rg.WATCHLIST_SECTION_PREFIX in msg)
    # (b) Top 5 íntegro (F12.5: URLs inteiras)
    check("Top 5 íntegro com as 5 apply_urls",
          all(f"https://apply.example.com/{i}" in msg for i in range(5)))
    # (c) link presente por último
    check("link por último",
          msg.endswith("🔗 Ranking completo (todas as vagas elegíveis): "
                       "https://x/"))
    check("mensagem cabe no limite do Telegram",
          len(msg) <= rd.TELEGRAM_MAX_LEN)
    # (d) caminho feliz: digest enxuto sai INTEIRO (sem compact)
    slim_digest = (
        ["", "🆕 Novas desde ontem: 1", "  1. nova a"] +
        ["", rg.TOP5_SECTION_HEADER, "1. A — B — 12 — https://y/1"] +
        ["", rg.WATCHLIST_SECTION_HEADER + " — 1 nova(s)",
         "  🎯 1. Alvo: título (Local)"] +
        ["", "🔗 Ranking completo: https://x/"]
    )
    msg_slim = rd.build_message(summary, [], 0, always_notify=True,
                                digest_lines=slim_digest)
    check("digest enxuto: sai INTEIRO (regressão zero do caminho feliz)",
          "  🎯 1. Alvo: título (Local)" in msg_slim
          and "  1. nova a" in msg_slim
          and "encurtado" not in msg_slim)


def test_compact_collapse_order() -> None:
    section("T4: ordem de colapso — 🎯 colapsa antes da 🆕")
    top5 = rg.format_top5([
        _job(i, apply_url=f"https://apply.example.com/{i}")
        for i in range(5)]).splitlines()
    summary = _summary()

    # Cenario 1: 🎯 GORDA (3x1200) + 🆕 magra (3x90). O digest inteiro
    # estoura 4096 (perfil curto fora; ~5k só de seções), mas com 🎯
    # colapsada ao header a mensagem cabe -> nivel (ns inteira, wl
    # colapsada). O compact derruba PRIMEIRO o que nao e prioridade
    # (perfil), e so colapsa 🎯 quando base+🆕+🎯+Top5+link nao cabe.
    ns_body = [f"  {i}. nova " + "n" * 90 for i in range(1, 4)]
    watch_body = [f"  🎯 {i}. Alvo: título (Local) " + "w" * 1200
                  for i in range(1, 4)]
    digest = (
        ["", "🎯 Perfil e critérios ativos"] +
        [f"linha perfil {i}" for i in range(3)] +
        ["", "🆕 Novas desde ontem: 3"] + ns_body +
        ["", rg.TOP5_SECTION_HEADER] + top5 +
        ["", rg.WATCHLIST_SECTION_HEADER + " — 3 nova(s)"] + watch_body +
        ["", "🔗 Ranking completo: https://x/"]
    )
    msg = rd.build_message(summary, [], 0, always_notify=True,
                           digest_lines=digest)
    check("c1: mensagem cabe", len(msg) <= rd.TELEGRAM_MAX_LEN)
    check("c1: 🎯 colapsada — header presente, corpo fora",
          rg.WATCHLIST_SECTION_PREFIX in msg
          and "w" * 1200 not in msg)
    check("c1: 🆕 sobrevive INTEIRA (prioridade sobre 🎯)",
          "🆕 Novas desde ontem: 3" in msg
          and "n" * 90 in msg)
    check("c1: Top 5 íntegro", msg.count("https://apply.example.com/") >= 5)
    check("c1: link por último",
          msg.endswith("🔗 Ranking completo: https://x/"))

    # Cenario 2: 🆕 E 🎯 GORDAS (3x1200 cada): so cabe com AMBAS
    # colapsadas ao header com contagem (nivel 3 do compact F13 —
    # 🎯 colapsa antes, e quando ainda nao basta a 🆕 colapsa tambem;
    # NUNCA dropadas inteiras).
    ns_body2 = [f"  {i}. nova " + "n" * 1200 for i in range(1, 4)]
    digest2 = (
        ["", "🎯 Perfil e critérios ativos"] +
        [f"linha perfil {i}" for i in range(3)] +
        ["", "🆕 Novas desde ontem: 3"] + ns_body2 +
        ["", rg.TOP5_SECTION_HEADER] + top5 +
        ["", rg.WATCHLIST_SECTION_HEADER + " — 3 nova(s)"] + watch_body +
        ["", "🔗 Ranking completo: https://x/"]
    )
    msg2 = rd.build_message(summary, [], 0, always_notify=True,
                            digest_lines=digest2)
    check("c2: mensagem cabe", len(msg2) <= rd.TELEGRAM_MAX_LEN)
    check("c2: 🆕 NUNCA dropada — header com contagem sobrevive",
          "🆕 Novas desde ontem: 3" in msg2)
    check("c2: 🎯 NUNCA dropada — header com contagem sobrevive",
          rg.WATCHLIST_SECTION_PREFIX in msg2
          and "3 nova(s)" in msg2)
    check("c2: corpo da 🆕 fora (colapsada ao header)",
          "n" * 1200 not in msg2)
    check("c2: corpo da 🎯 fora (colapsada ao header)",
          "w" * 1200 not in msg2)
    check("c2: Top 5 segue íntegro",
          msg2.count("https://apply.example.com/") >= 5)
    check("c2: link por último",
          msg2.endswith("🔗 Ranking completo: https://x/"))

    # Cenario 3 (regressao F6.1): sem 🆕/🎯 no digest, o compact
    # antigo (base+Top5+link) continua identico.
    digest3 = (
        ["", "🎯 Perfil e critérios ativos"] +
        [f"linha perfil {i} " + "p" * 300 for i in range(12)] +
        ["", rg.TOP5_SECTION_HEADER] + top5 +
        ["", "🔗 Ranking completo: https://x/"]
    )
    msg3 = rd.build_message(summary, [], 0, always_notify=True,
                            digest_lines=digest3)
    check("c3: sem 🆕/🎯 o comportamento F6.1 segue idêntico",
          len(msg3) <= rd.TELEGRAM_MAX_LEN
          and rg.TOP5_SECTION_HEADER in msg3
          and msg3.endswith("🔗 Ranking completo: https://x/")
          and "Perfil e critérios" not in msg3)


def test_compact_regression_zero() -> None:
    section("T4: mensagem que cabe — regressão byte a byte")
    # SEM estouro: output idêntico a base + digest (o compact nem roda)
    digest = ["", "🎯 Perfil e critérios ativos",
              "", "🆕 Novas desde ontem: 1", "  1. Nova — Acme",
              "", rg.TOP5_SECTION_HEADER,
              "1. A — B — 12 — https://apply.example.com/1",
              "", rg.WATCHLIST_SECTION_HEADER + " — 1 nova(s)",
              "  🎯 1. BoschGroup: Praktikum (Stuttgart)",
              "", "🔗 Ranking completo: https://x/"]
    summary = _summary()
    base = rd.build_message(summary, [], 0, always_notify=True)
    msg = rd.build_message(summary, [], 0, always_notify=True,
                           digest_lines=digest)
    expected = base + "\n" + "\n".join(digest)
    check("sem estouro: saída == base + digest (byte a byte)",
          msg == expected)
    # digest None/[]: comportamento de hoje
    check("digest None == base pura",
          rd.build_message(summary, [], 0, always_notify=True,
                           digest_lines=None) == base)
    check("digest [] == base pura",
          rd.build_message(summary, [], 0, always_notify=True,
                           digest_lines=[]) == base)
    # digest sem ⚡ que estoura: linha única pre-F6.1 (contrato vivo)
    huge = ["", "🎯 Perfil"] + ["z" * 100 for _ in range(50)] \
        + ["", "🔗 Ranking completo: https://x/"]
    msg_h = rd.build_message(summary, [], 0, always_notify=True,
                             digest_lines=huge)
    check("sem ⚡: linha única pre-F6.1 preservada",
          "Resumo do ranking encurtado" in msg_h
          and len(msg_h) <= rd.TELEGRAM_MAX_LEN)

# ---------------------------------------------------------------------------
# T5 — toggles client-side: f-ws (Werkstudent) e f-data (Data/BI)
# ---------------------------------------------------------------------------

def test_title_flags() -> None:
    section("T5: is_werkstudent_title/is_data_bi_title — purezas da regra")
    ws = mp.is_werkstudent_title({"title": "Werkstudent (m/w/d) Einkauf"})
    check("werkstudent casefold (minusculo no titulo)",
          mp.is_werkstudent_title({"title": "werkstudent data science"}))
    check("sem werkstudent: False",
          not mp.is_werkstudent_title({"title": "Praktikum Einkauf"}))
    check("Werkstudentin (feminino) também casa",
          mp.is_werkstudent_title({"title": "Werkstudentin IT"}))
    # data/BI por PALAVRA INTEIRA — os FPs medidos no dataset real
    check("data casa", mp.is_data_bi_title({"title": "Praktikum Data Analytics"}))
    check("BI palavra inteira casa",
          mp.is_data_bi_title({"title": "Working Student BI & Reporting"}))
    check("substring 'bi' em E-Mobility NÃO casa (FP morto)",
          not mp.is_data_bi_title({"title": "Praktikum E-Mobility"}))
    check("substring 'bi' em Elektromobilität NÃO casa (FP morto)",
          not mp.is_data_bi_title({"title": "Lieferantennetzwerk Elektromobilität"}))
    check("business intelligence (multi-palavra) casa",
          mp.is_data_bi_title({"title": "Praktikum Business Intelligence"}))
    check("power bi casa",
          mp.is_data_bi_title({"title": "Werkstudent Power BI Dashboard"}))
    check("sql casa", mp.is_data_bi_title({"title": "Praktikum SQL"}))
    check("analyst casa", mp.is_data_bi_title({"title": "Supply Chain Analyst"}))
    check("título comum de supply chain NÃO casa",
          not mp.is_data_bi_title({"title": "Praktikum Verkäufer Kassierer"}))


def test_toggle_attrs_in_html() -> None:
    section("T5: data-ws/data-data nos cards + toggles f-ws/f-data")
    jobs = [
        _job(0, title="Werkstudent Einkauf (m/w/d)"),
        _job(1, title="Praktikum Data Analytics"),
        _job(2, title="Praktikum Verkäufer"),
        _job(3, title="Werkstudent Power BI"),
    ]
    html = mp.render_minimal_html(jobs, total_eligible=4, generated_at="x")
    check("data-ws=1 no card Werkstudent",
          'data-ws="1"' in html and html.count('data-ws="1"') == 2)
    check("data-ws=0 nos outros",
          html.count('data-ws="0"') == 2)
    check("data-data=1 nos cards data/BI",
          html.count('data-data="1"') == 2)
    check("data-data=0 nos outros",
          html.count('data-data="0"') == 2)
    check("toggle f-ws presente com label 'sem Werkstudent'",
          'id="f-ws"' in html and "sem Werkstudent" in html)
    check("toggle f-data presente com label 'Data/BI'",
          'id="f-data"' in html and "Data/BI" in html)
    # zero mudança de ranking: data-s preservado e ordem oficial
    # (gabarito via _fmt_score — o MESMO formatador do render, nunca
    # uma segunda opinião de formatação)
    scores = [f'data-s="{mp._fmt_score(15.0 - i * 0.1)}"' for i in range(4)]
    check("scores/ordem preservados (toggle não reordena)",
          all(s in html for s in scores))


def test_js_filters_node() -> None:
    section("T5: núcleo JS dos 6 filtros (vf/de/country/new/ws/data) em node")
    if shutil.which("node") is None:
        print("  [SKIP] node ausente — núcleo JS não executado (CI tem node)")
        return
    harness = """
var cards = [
  {'data-vf':'1','data-de':'required','data-iso':'de','data-new':'0','data-ws':'1','data-data':'0','data-q':'a b'},
  {'data-vf':'0','data-de':'none','data-iso':'nl','data-new':'1','data-ws':'0','data-data':'1','data-q':'c d'},
  {'data-vf':'1','data-de':'none','data-iso':'de','data-new':'0','data-ws':'0','data-data':'1','data-q':'e f'},
  {'data-vf':'0','data-de':'none','data-iso':'de','data-new':'0','data-ws':'1','data-data':'0','data-q':'g h'},
];
var li = function(attrs) { return { getAttribute: function(k) { return attrs[k] || null; } }; };
var els = cards.map(li);
var state = { q:{value:''}, vf:{checked:false}, de:{checked:false},
              country:{value:''}, nw:{checked:false}, ws:{checked:false},
              da:{checked:false} };
function applyF(st) {
  var c = 0;
  els.forEach(function(el) {
    var ok = !st.q.value || el.getAttribute('data-q').indexOf(st.q.value) > -1;
    if (st.vf.checked) ok = ok && el.getAttribute('data-vf') === '1';
    if (st.de.checked) ok = ok && el.getAttribute('data-de') !== 'required';
    if (st.country.value) ok = ok && el.getAttribute('data-iso') === st.country.value;
    if (st.nw.checked) ok = ok && el.getAttribute('data-new') === '1';
    if (st.ws.checked) ok = ok && el.getAttribute('data-ws') !== '1';
    if (st.da.checked) ok = ok && el.getAttribute('data-data') === '1';
    if (ok) c++;
  });
  return c;
}
if (applyF(state) !== 4) console.log('F1_FAIL');
state.ws.checked = true;
if (applyF(state) !== 2) console.log('F2_FAIL');  // esconde os 2 Werkstudent
state.da.checked = true;
if (applyF(state) !== 2) console.log('F3_FAIL');  // sem WS E data/BI: cards 2 e 3
state.ws.checked = false;
if (applyF(state) !== 2) console.log('F4_FAIL');  // só data/BI
state.da.checked = false;
state.vf.checked = true;
if (applyF(state) !== 2) console.log('F5_FAIL');
console.log('JS_OK');
"""
    proc = subprocess.run(["node", "-"], input=harness,
                          capture_output=True, text=True, timeout=30)
    out = proc.stdout.strip()
    check("núcleo dos 6 filtros correto em node", "JS_OK" in out
          and "FAIL" not in out)
    # o _JS REAL da página roda sem erro com DOM nulo (guard F6)
    harness2 = """
var document = { querySelectorAll: function () { return []; },
  getElementById: function () { return null; } };
%s
console.log('REALJS_OK');
""" % mp._JS
    proc2 = subprocess.run(["node", "-"], input=harness2,
                           capture_output=True, text=True, timeout=30)
    check("_JS real da página roda em node (guards)",
          proc2.returncode == 0 and "REALJS_OK" in proc2.stdout)


# ---------------------------------------------------------------------------
# T6 — página: seção 🎯 equivalente (cards, dedup com 🆕, cap 150 KB)
# ---------------------------------------------------------------------------

def test_page_watchlist_section() -> None:
    section("T6: página — seção 🎯 com cards; dedup com 🆕; ausente sem wl")
    jobs = [
        _job(0, company="BoschGroup", score=15.0, title="Nova A Bosch"),
        _job(1, company="SAP", score=14.0, title="Nova B SAP"),
        _job(2, company="Acme", score=13.0, title="Nova C Acme"),
        _job(3, company="BASF SE", score=12.0, title="Velha BASF"),
    ]
    prev = [dict(jobs[3])]
    diff = rg.new_since_previous(jobs, prev)
    events = rg.radar_events(diff, jobs, ["BoschGroup", "SAP"])
    new_ids = diff[0]
    # com watchlist_events: seção presente com TODOS os eventos
    html = mp.render_minimal_html(jobs, total_eligible=4, generated_at="x",
                                  new_since_ids=new_ids,
                                  watchlist_events=events)
    check("seção 🎯 presente na página",
          "🎯 Empresas-alvo — 2 nova(s)" in html)
    check("cards dos eventos na seção",
          "Nova A Bosch" in html and "Nova B SAP" in html)
    # sem watchlist_events: seção ausente (regressão zero)
    html_no = mp.render_minimal_html(jobs, total_eligible=4,
                                     generated_at="x",
                                     new_since_ids=new_ids)
    check("sem watchlist_events: seção 🎯 ausente",
          "🎯 Empresas-alvo" not in html_no)
    # sem eventos (lista vazia): seção ausente
    html_zero = mp.render_minimal_html(jobs, total_eligible=4,
                                       generated_at="x",
                                       new_since_ids=new_ids,
                                       watchlist_events=[])
    check("zero eventos: seção 🎯 ausente (sem linha vazia)",
          "🎯 Empresas-alvo" not in html_zero)

    # semântica espelhada ao digest: evento pode aparecer na 🆕 E na 🎯
    # (critérios diferentes — "nova" vs "nova E alvo"); a seção 🎯 mostra
    # TODOS os eventos, sem dedup entre seções (o digest faz igual).
    new_ids_all = {j["id"] for j in jobs}
    html_dup = mp.render_minimal_html(
        jobs, total_eligible=4, generated_at="x",
        new_since_ids=new_ids_all, watchlist_events=events)
    check("seção 🎯 independente da 🆕 (sem dedup — espelha o digest)",
          "🎯 Empresas-alvo — 2 nova(s)" in html_dup)
    # o card do evento aparece na seção 🎯 (região entre o h2 🎯 e o fim)
    watch_region = html_dup.split("🎯 Empresas-alvo — 2 nova(s)", 1)[1] \
        if "🎯 Empresas-alvo — 2 nova(s)" in html_dup else ""
    check("cards dos 2 eventos DENTRO da seção 🎯",
          "Nova A Bosch" in watch_region
          and "Nova B SAP" in watch_region)


def test_page_size_cap() -> None:
    section("T6: página com seção 🎯 — cap duro 150 KB vivo")
    jobs = [_job(i, company=f"Empresa {i}",
                 title=f"Werkstudent Data Analytics {i} "
                       f"{'x' * 40}")
            for i in range(100)]
    events = jobs[:12]  # 12 eventos
    html = mp.render_minimal_html(jobs, total_eligible=100,
                                  generated_at="x",
                                  new_since_ids={j["id"] for j in events},
                                  watchlist_events=events)
    size = len(html.encode("utf-8"))
    check(f"página com 12 eventos < 150 KB ({size} bytes)", size < 150_000)


def test_from_file_watchlist() -> None:
    section("T6: render_minimal_html_from_file — watchlist via arquivo")
    with tempfile.TemporaryDirectory(prefix="t_f13_ff_") as tmp:
        base = Path(tmp)
        cur = [
            _job(0, company="BoschGroup", score=15.0, title="Nova A"),
            _job(1, company="Acme", score=14.0, title="Nova B"),
            _job(2, company="SAP", score=13.0, title="Velha C"),
        ]
        (base / "eligible_jobs.json").write_text(json.dumps(cur),
                                                 encoding="utf-8")
        arch = base / "archive"
        yday = arch / "20261005T090002Z"
        yday.mkdir(parents=True)
        (yday / "eligible_jobs.json").write_text(json.dumps(cur[1:]),
                                                encoding="utf-8")
        wl = _watchlist_file(base, ["BoschGroup", "SAP"])
        html = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=arch,
            include_materials=False, watchlist_path=wl)
        check("from_file: seção 🎯 com 1 evento (t0 nova Bosch; "
              "t2 SAP antiga NÃO conta)",
              "🎯 Empresas-alvo — 1 nova(s)" in html
              and "Nova A" in html)
        # watchlist ausente: página sem seção, sem erro
        html_no = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=arch,
            include_materials=False)
        check("from_file sem watchlist: seção ausente (regressão zero)",
              "🎯 Empresas-alvo" not in html_no)
        # watchlist corrompida: best-effort
        bad = base / "bad.json"
        bad.write_text("{corrompido", encoding="utf-8")
        html_bad = mp.render_minimal_html_from_file(
            base / "eligible_jobs.json", archive_root=arch,
            include_materials=False, watchlist_path=bad)
        check("from_file watchlist corrompida: sem seção, sem erro",
              "🎯 Empresas-alvo" not in html_bad)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    test_watchlist_parse()
    test_radar_events()
    test_radar_lines()
    test_radar_in_digest_sections()
    test_compact_preserves_new_and_watch()
    test_compact_collapse_order()
    test_compact_regression_zero()
    test_title_flags()
    test_toggle_attrs_in_html()
    test_js_filters_node()
    test_page_watchlist_section()
    test_page_size_cap()
    test_from_file_watchlist()
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
