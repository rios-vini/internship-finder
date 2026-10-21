"""F93 — cap de empresa no digest do Telegram (fim do monopólio Lidl).

O digest passa a respeitar a MESMA regra de exibição que o site já aplica
desde a F11 T4/F20: máx. ``minimal_page.COMPANY_MAX_CARDS`` (=2) vagas por
empresa no corte exibido — a 3ª+ de uma empresa é pulada e a vaga seguinte
de outra empresa sobe (ordem oficial preservada, nunca reordena). Escopo
(spec): seções top5 (🏆 resumo E ⚡ apply_url — o MESMO corte, as duas
nunca divergem) e 🆕 "Novas desde ontem" (top-3 da F11). Contrapartida de
informação: as ocultas NÃO somem — 1 linha "N vaga(s) ocultas pelo cap de
empresa (top empresas: …)" fecha o CORPO da seção ⚡ (viaja com o produto
do dia em TODOS os níveis do compact — o extrator puxa header+corpo).
Seção 🎯 Empresas-alvo (watchlist) INTOCIDA: por-empresa por construção
(só empresas curadas aparecem; cap 5/dia ``RADAR_MAX_SHOWN``) e cada
evento é sinal deliberado do dono. Display-only: scores, ordem, JSON e
CSV intocados.

Casos da spec (travados aqui):
1. 5 vagas Lidl no top  -> digest mostra 2 + linha de ocultas;
2. sem Lidl/monopólio   -> digest IDÊNTICO ao de antes (regressão);
3. cap não reordena     -> ordem por score preservada;
4. limite 4096 chars    -> respeitado COM a linha nova (compact);
5. watchlist intocada   -> radar lista todas as novas da empresa-alvo.

Guardas de vizinhança: F25 (excluded_ids demove ANTES do cap — a
excluída não vira "oculta pelo cap"), F11 (big_diff >= 500 mostra SÓ a
contagem — não há lista que o cap desloque), sync site×digest (mesma
``apply_company_cap``, mesma ``COMPANY_MAX_CARDS`` — o digest nunca
inventa regra própria).

Standalone e OFFLINE (sem rede, sem escrever em data/): fixtures JSON em
tmpdir. Uso:

    .venv/bin/python scripts/test_f93.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))  # importa ranking_digest/refresh_daily
sys.path.insert(0, str(SCRIPTS.parent / "src"))

import refresh_daily as rd  # noqa: E402
import ranking_digest as rg  # noqa: E402
from minimal_page import COMPANY_MAX_CARDS, apply_company_cap  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool) -> None:
    global CHECKS
    CHECKS += 1
    tag = "OK" if cond else "FAIL"
    print(f"[{tag}] {name}")
    if not cond:
        FAILURES.append(name)


def _job(jid: str, company: str, score: float,
         title: str = "Praktikum Einkauf") -> dict:
    return {
        "id": jid, "title": title, "company": company,
        "location": "Berlin, DE", "score": score,
        "url": f"https://ex.com/{jid}",
        "raw": {"apply_url": f"https://apply.com/{jid}"},
    }


def _write_ranking(path: Path, jobs: list[dict]) -> None:
    path.write_text(json.dumps(jobs), encoding="utf-8")


def _monopoly() -> tuple[list[dict], list[dict]]:
    """O cenário medido da spec: Lidl dominando o topo por score.

    5 Lidl nas 5 primeiras posições + 3 empresas distintas atrás. As
    Lidl são todas ANTIGAS (no snapshot anterior) — o foco é o corte
    top5; as 3 novas (Bosch/SAP/BASF) são distintas entre si, então a
    seção 🆕 não sofre cap nesse cenário (regressão isolada do top5).
    """
    cur = ([_job(f"l{i}", "Lidl", 15.0 - i) for i in range(5)]
           + [_job("b1", "Bosch", 10.0), _job("s1", "SAP", 9.5),
              _job("f1", "BASF", 9.0)])
    prev = [_job(f"l{i}", "Lidl", 15.0 - i) for i in range(5)]
    return cur, prev


def _summary() -> dict:
    """Summary no shape real de run (chaves que o build_message lê)."""
    return {
        "run_id": "2026-10-21T09:00:02.347210+00:00",
        "total_collected": 95_801,
        "eligible": 704,
        "dedup_removed": 496,
        "ok": {"count": 113, "collected": 73_138},
        "empty": 10,
        "timeout": [("successfactors:lidlstiftuP2", "Lidl", "TIMEOUT")],
        "error": [("successfactors:careers", "AkzoNobel", "HTTP_500")],
        "skipped": 0,
        "not_found": 0,
        "source_names": {},
    }


def _alert(kind: str, source: str, company: str, **extra) -> dict:
    d = {"type": kind, "source": source, "company": company}
    d.update(extra)
    return d


def _many_alerts(n: int) -> list[dict]:
    """N falhas crônicas (runs_seq >= 15) — base operacional gorda para
    forçar o compact do Telegram (>4096) no teste E."""
    return [
        _alert("recurring_error", f"src:{i}", f"Empresa {i} GmbH",
               runs_seq=20 + i)
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# A — helpers puros (company_cap_hidden / cap_hidden_line / _company_capped)
# ---------------------------------------------------------------------------

def test_a_helpers() -> None:
    print("== A: helpers puros do cap (F93) ==")
    lidl = [_job(f"l{i}", "Lidl", 15.0 - i) for i in range(5)]
    # A1: hidden = exatamente o que o cap deslocou do top-`limit` SEM cap
    hidden = rg.company_cap_hidden(lidl + [_job("b", "Bosch", 1.0)],
                                   limit=5)
    check("A1 hidden = 3ª+ da empresa no corte sem cap (l2, l3, l4)",
          [j["id"] for j in hidden] == ["l2", "l3", "l4"])
    # A2: sem repetição >2/empresa -> nada oculto
    distinct = [_job(f"d{i}", f"Firma {i} GmbH", 9.0 - i) for i in range(8)]
    check("A2 sem monopólio -> hidden vazio",
          rg.company_cap_hidden(distinct, limit=5) == [])
    # A3: cap_hidden_line — None sem ocultas; contagem desc; máx 3 empresas
    check("A3a linha None quando nada oculto", rg.cap_hidden_line([]) is None)
    line = rg.cap_hidden_line(hidden)
    check("A3b contagem + top empresa no formato da spec",
          line == "ℹ️ 3 vaga(s) ocultas pelo cap de empresa "
                  "(top empresas: Lidl +3)")
    many = ([_job("x1", "Lidl", 9.0), _job("x2", "Lidl", 8.9),
             _job("x3", "Lidl", 8.8)]
            + [_job(f"y{i}", f"Y{i}", 8.0 - i) for i in range(5)])
    mline = rg.cap_hidden_line(many)
    check("A3c >3 empresas: máx 3 listadas + reticências (ordem desc)",
          mline == "ℹ️ 8 vaga(s) ocultas pelo cap de empresa "
                   "(top empresas: Lidl +3, Y0 +1, Y1 +1, …)")
    # A4: default = regra do SITE (fonte única); override explícito funciona
    shown = rg._company_capped(lidl, limit=5)
    check("A4a default == COMPANY_MAX_CARDS do site (2 Lidl listadas)",
          [j["id"] for j in shown] == ["l0", "l1"]
          and COMPANY_MAX_CARDS == 2)
    check("A4b mesmo corte do minimal_page.apply_company_cap (sync)",
          [j["id"] for j in shown]
          == [j["id"] for j in apply_company_cap(lidl, limit=5)])
    over = rg._company_capped(lidl, limit=5, max_per_company=4)
    check("A4c override explícito de max_per_company respeitado",
          [j["id"] for j in over] == ["l0", "l1", "l2", "l3"])


# ---------------------------------------------------------------------------
# B — spec caso 1: 5 Lidl no top -> 2 listadas + linha de ocultas
# ---------------------------------------------------------------------------

def test_b_monopoly() -> None:
    print("== B: 5 Lidl no top -> digest mostra 2 + linha de ocultas ==")
    cur, prev = _monopoly()
    with tempfile.TemporaryDirectory(prefix="t_f93_mono_") as tmp:
        root = Path(tmp)
        _write_ranking(root / "cur.json", cur)
        _write_ranking(root / "prev.json", prev)
        sec = rg.digest_sections(root / "cur.json", root / "prev.json",
                                pages_url="https://x.io/")
        check("B0 digest montado", sec is not None)
        text = "\n".join(sec or [])
        # B1: 🏆 e ⚡ mostram exatamente 2 Lidl — MESMO corte, nunca divergem
        resumo = text[text.index("🏆 Top 5 atual"):].splitlines()[1:6]
        comp_resumo = [l.split(" — ")[1].split(" (")[0] for l in resumo]
        check("B1a 🏆 lista exatamente 2 Lidl e completa com as seguintes",
              comp_resumo == ["Lidl", "Lidl", "Bosch", "SAP", "BASF"])
        t5 = rg.top5_section_lines(sec or [])
        comp_t5 = [l.split(" — ")[1] for l in t5[1:6]]
        check("B1b ⚡ lista exatamente 2 Lidl (mesmas empresas do 🏆)",
              comp_t5 == comp_resumo)
        # B2: linha de ocultas DENTRO do corpo do ⚡ (sobrevive ao compact)
        cap_lines = [l for l in t5 if "ocultas pelo cap" in l]
        check("B2a linha de ocultas no corpo do ⚡, formato da spec",
              cap_lines == ["ℹ️ 3 vaga(s) ocultas pelo cap de empresa "
                            "(top empresas: Lidl +3)"])
        check("B2b linha fecha o corpo (depois das 5 vagas, índice 6)",
              t5.index(cap_lines[0]) == 6)
        # B3: as ocultas são exatamente as 3 Lidl deslocadas do top-5 cru
        hidden = rg.company_cap_hidden(cur, limit=5)
        check("B3 ocultas = as 3 Lidl deslocadas (l2, l3, l4), ordem oficial",
              [j["id"] for j in hidden] == ["l2", "l3", "l4"]
              and all(j["company"] == "Lidl" for j in hidden))
        # B4: display-only — a contagem do run continua contando TODAS
        check("B4 display-only: contagem do run intacta (8 elegíveis)",
              "(8 vagas elegíveis)" in text)
        # B5: 🆕 desde ontem sem repetição -> intacta (3 novas listadas)
        ns = rg.new_since_section_lines(sec or [])
        check("B5 🆕 intacta quando as novas são distintas (3 listadas)",
              ns[0] == "🆕 Novas desde ontem: 3" and len(ns) == 4)


# ---------------------------------------------------------------------------
# C — spec caso 2: sem monopólio -> digest IDÊNTICO ao de antes (regressão)
# ---------------------------------------------------------------------------

def test_c_regressao() -> None:
    print("== C: sem monopólio -> NENHUM byte novo (regressão) ==")
    cur = [_job(f"d{i}", f"Firma {i} GmbH", 15.0 - i,
                title=f"Praktikum {i}") for i in range(8)]
    prev = [dict(j) for j in cur[:5]]  # 5 antigas, 3 novas (distintas)
    with tempfile.TemporaryDirectory(prefix="t_f93_reg_") as tmp:
        root = Path(tmp)
        _write_ranking(root / "cur.json", cur)
        _write_ranking(root / "prev.json", prev)
        sec = rg.digest_sections(root / "cur.json", root / "prev.json",
                                 pages_url="https://x.io/")
        text = "\n".join(sec or [])
        check("C1 nenhuma linha de ocultas em digest sem monopólio",
              "ocultas" not in text)
        # C2: ⚡ byte a byte o gabarito pré-F93 (contrato travado)
        expected = [
            "⚡ Top 5 do dia (candidatura direta)",
            "1. Praktikum 0 — Firma 0 GmbH — 15 — https://apply.com/d0",
            "2. Praktikum 1 — Firma 1 GmbH — 14 — https://apply.com/d1",
            "3. Praktikum 2 — Firma 2 GmbH — 13 — https://apply.com/d2",
            "4. Praktikum 3 — Firma 3 GmbH — 12 — https://apply.com/d3",
            "5. Praktikum 4 — Firma 4 GmbH — 11 — https://apply.com/d4",
        ]
        check("C2 ⚡ idêntico ao pré-F93 (gabarito literal, 5 linhas)",
              rg.top5_section_lines(sec or []) == expected)
        resumo = text[text.index("🏆 Top 5 atual"):].splitlines()[1:6]
        check("C3 🏆 idêntico ao pré-F93 (5 linhas, empresas na ordem)",
              [l.split(" — ")[1].split(" (")[0] for l in resumo]
              == [f"Firma {i} GmbH" for i in range(5)])
        ns = rg.new_since_section_lines(sec or [])
        check("C4 🆕 intacta: 3 novas distintas listadas (sem cap, sem ocultas)",
              ns[0] == "🆕 Novas desde ontem: 3"
              and "Firma 5 GmbH" in ns[1] and "ocultas" not in "\n".join(ns))


# ---------------------------------------------------------------------------
# D — spec caso 3: cap NÃO reordena (ordem por score preservada)
# ---------------------------------------------------------------------------

def test_d_ordem() -> None:
    print("== D: cap não reordena — ordem oficial preservada ==")
    # Lidl intercalada nas posições 1,2,4,6,8 — o cap pula, nunca reordena
    cur = ([_job("l0", "Lidl", 15.0), _job("l1", "Lidl", 14.5),
            _job("b0", "Bosch", 14.0), _job("l2", "Lidl", 13.5),
            _job("s0", "SAP", 13.0), _job("l3", "Lidl", 12.5),
            _job("f0", "BASF", 12.0), _job("l4", "Lidl", 11.5),
            _job("m0", "MAHLE", 11.0), _job("z0", "Zeiss", 10.5)])
    with tempfile.TemporaryDirectory(prefix="t_f93_ord_") as tmp:
        root = Path(tmp)
        _write_ranking(root / "cur.json", cur)
        _write_ranking(root / "prev.json", cur)  # nada novo: foco no corte
        sec = rg.digest_sections(root / "cur.json", root / "prev.json",
                                 pages_url="https://x.io/")
        t5 = rg.top5_section_lines(sec or [])
        ids = [l.rsplit("https://apply.com/", 1)[-1] for l in t5[1:6]]
        check("D1 ordem oficial preservada: l2 (3ª Lidl) pulada, s0/f0 sobem",
              ids == ["l0", "l1", "b0", "s0", "f0"])
        scores = [float(l.split(" — ")[2]) for l in t5[1:6]]
        check("D2 scores estritamente decrescentes no corte exibido",
              all(scores[i] > scores[i + 1] for i in range(len(scores) - 1)))
        hidden = rg.company_cap_hidden(cur, limit=5)
        check("D3 ocultas também em ordem oficial (só l2 no corte cru)",
              [j["id"] for j in hidden] == ["l2"])
        check("D4 cap não reordena o que entra (ids do corte estão no ranking"
              " na MESMA ordem relativa)",
              [cur.index(next(j for j in cur if j["id"] == i))
               for i in ids] == sorted(
                  cur.index(next(j for j in cur if j["id"] == i))
                  for i in ids))


# ---------------------------------------------------------------------------
# E — spec caso 4: limite 4096 respeitado COM a linha nova (compact)
# ---------------------------------------------------------------------------

def test_e_4096() -> None:
    print("== E: limite 4096 do Telegram respeitado com a linha nova ==")
    # digest de dia Lidl grande (todas as seções) + base operacional com
    # crônicas -> a montagem ingênua estoura 4096 e o compact aciona
    cur = ([_job(f"l{i}", "Lidl", 15.0 - i) for i in range(5)]
           + [_job(f"d{i}", f"Firma {i} GmbH", 10.0 - i * 0.001,
                   title=f"Praktikum Bereich {i} Einkauf")
              for i in range(1200)])
    prev = [_job(f"l{i}", "Lidl", 15.0 - i) for i in range(5)]
    with tempfile.TemporaryDirectory(prefix="t_f93_4096_") as tmp:
        root = Path(tmp)
        _write_ranking(root / "cur.json", cur)
        _write_ranking(root / "prev.json", prev)
        digest = rg.digest_sections(root / "cur.json", root / "prev.json",
                                    pages_url="https://x.io/")
        text = "\n".join(digest or [])
        check("E0 digest do dia Lidl montado e grande (compact exercitado)",
              len(text) > 3800
              and "ocultas pelo cap de empresa" in text and "Lidl +3" in text)
        msg = rd.build_message(_summary(), _many_alerts(40), 2,
                               always_notify=True, disk_pct=91,
                               digest_lines=digest)
        check("E1 mensagem final cabe no Telegram (<= 4096)",
              msg is not None and len(msg) <= rd.TELEGRAM_MAX_LEN)
        check("E2 compact REAL: corpo das seções cortáveis fora da mensagem",
              "(mat " not in (msg or "") and "Mudanças" not in (msg or ""))
        check("E3 linha de ocultas SOBREVIVE ao compact (viaja com o ⚡)",
              "ocultas pelo cap de empresa" in (msg or "")
              and "Lidl +3" in (msg or ""))
        check("E4 ⚡ inteiro (header + 5 apply_urls) e link por último",
              "⚡ Top 5 do dia (candidatura direta)" in (msg or "")
              and (msg or "").count("https://apply.com/") == 5
              and (msg or "").endswith(
                  "🔗 Ranking completo (todas as vagas elegíveis): https://x.io/"))


# ---------------------------------------------------------------------------
# F — spec caso 5: watchlist INTOCIDA + cap no top-3 da 🆕
# ---------------------------------------------------------------------------

def test_f_watchlist_newsince() -> None:
    print("== F: watchlist intocada + cap no new_since ==")
    # 4 Lidl NOVAS (empresa da watchlist) + 3 novas de outras empresas
    cur = ([_job(f"l{i}", "Lidl", 15.0 - i) for i in range(4)]
           + [_job("b1", "Bosch", 11.0), _job("s1", "SAP", 10.5),
              _job("f1", "BASF", 10.0)])
    prev = [_job("old", "Old Corp", 1.0)]
    with tempfile.TemporaryDirectory(prefix="t_f93_wl_") as tmp:
        root = Path(tmp)
        _write_ranking(root / "cur.json", cur)
        _write_ranking(root / "prev.json", prev)
        (root / "watchlist.json").write_text(
            json.dumps({"companies": ["Lidl"]}), encoding="utf-8")
        sec = rg.digest_sections(root / "cur.json", root / "prev.json",
                                 pages_url="https://x.io/",
                                 watchlist_path=root / "watchlist.json")
        text = "\n".join(sec or [])
        # F1: o radar lista TODAS as 4 novas Lidl — cap por empresa NÃO
        # existe na watchlist (cap RADAR_MAX_SHOWN=5 é por DIA)
        watch = rg.watchlist_section_lines(sec or [])
        radar_lidl = [l for l in watch if l.startswith("  🎯") and "Lidl" in l]
        check("F1 watchlist INTOCIDA: radar lista as 4 novas Lidl",
              len(radar_lidl) == 4)
        # F2: o ⚡ capped (2 Lidl) — a divergência entre superfícies é o
        # DESING: o radar é alerta de empresa-alvo, o ⚡ é o corte do dia
        t5 = rg.top5_section_lines(sec or [])
        check("F2 ⚡ capped: 2 Lidl no corte",
              len([l for l in t5 if "— Lidl — " in l]) == 2)
        # F3: 🆕 top-3 com cap — 2 Lidl + 1 Bosch; contagem exata (7)
        ns = rg.new_since_section_lines(sec or [])
        check("F3 🆕 top-3 com cap: 2 Lidl + Bosch; contagem exata 7",
              ns[0] == "🆕 Novas desde ontem: 7"
              and "Lidl" in ns[1] and "Lidl" in ns[2] and "Bosch" in ns[3]
              and "(+4 outras novas — ver página)" in ns[-1])
        # F4: linha de ocultas = UNIÃO por id (l2 oculta no ⚡ E na 🆕 = 1;
        # l3 oculta só no ⚡) — 2 ocultas, contadas 1 vez cada
        cap_in_t5 = [l for l in t5 if "ocultas pelo cap" in l]
        check("F4 linha de ocultas = união por id (l2 e l3, sem dupla contagem)",
              cap_in_t5 == ["ℹ️ 2 vaga(s) ocultas pelo cap de empresa "
                            "(top empresas: Lidl +2)"])
        # F5: unitário — 4 novas Lidl -> 2 listadas + header exato + (+2)
        four = [_job(f"l{i}", "Lidl", 9.0 - i) for i in range(4)]
        ns4 = rg.new_since_lines(({j["id"] for j in four}, set()),
                                 four + [_job("b", "Bosch", 1.0)])
        check("F5 4 novas Lidl -> 2 listadas; contagem 4; (+2 outras)",
              ns4[0] == "🆕 Novas desde ontem: 4"
              and len([l for l in ns4 if "Lidl" in l]) == 2
              and any("(+2 outras novas" in l for l in ns4))
        check("F6 sem repetição a 🆕 é byte a byte a de antes (3 distintas)",
              rg.new_since_lines(({"a", "b", "c"}, set()),
                                 [_job("a", "A", 3.0), _job("b", "B", 2.0),
                                  _job("c", "C", 1.0)])
              == ["🆕 Novas desde ontem: 3",
                  "  1. Praktikum Einkauf — A — 3 — https://apply.com/a",
                  "  2. Praktikum Einkauf — B — 2 — https://apply.com/b",
                  "  3. Praktikum Einkauf — C — 1 — https://apply.com/c"])


# ---------------------------------------------------------------------------
# G — guardas de vizinhança (F25 / F11 big_diff / sync site×digest)
# ---------------------------------------------------------------------------

def test_g_guardas() -> None:
    print("== G: guardas de vizinhança ==")
    cur = [_job("l0", "Lidl", 15.0), _job("l1", "Lidl", 14.0),
           _job("l2", "Lidl", 13.0), _job("b0", "Bosch", 12.0),
           _job("s0", "SAP", 11.0)]
    with tempfile.TemporaryDirectory(prefix="t_f93_g_") as tmp:
        root = Path(tmp)
        _write_ranking(root / "cur.json", cur)
        _write_ranking(root / "prev.json", cur)
        # G1 — F25: a demovida sai ANTES do cap (não conta pro cap, não
        # vira "oculta pelo cap" — exclusão é semântica de liveness)
        sec = rg.digest_sections(root / "cur.json", root / "prev.json",
                                 pages_url="https://x.io/",
                                 excluded_ids={"l2"})
        t5 = rg.top5_section_lines(sec or [])
        ids = [l.rsplit("https://apply.com/", 1)[-1] for l in t5[1:6]]
        check("G1 demovida (F25) sai antes do cap: sem ocultas, corte segue",
              not any("ocultas" in l for l in t5)
              and ids == ["l0", "l1", "b0", "s0"])
        direct = rg.format_top5(cur, excluded_ids={"l2"})
        check("G1b format_top5 puro: cap APÓS as exclusões (mesmo corte)",
              [l.rsplit("https://apply.com/", 1)[-1]
               for l in direct.splitlines()] == ["l0", "l1", "b0", "s0"])
        # G2 — F11 big_diff: >=500 novas mostra SÓ contagem (sem lista a
        # deslocar, a 🆕 não gera ocultas); o cap do ⚡ segue valendo
        big = ([_job(f"l{i}", "Lidl", 15.0 - i) for i in range(3)]
               + [_job(f"d{i}", f"Firma {i} GmbH", 12.0 - i * 0.01)
                  for i in range(600)])
        _write_ranking(root / "big.json", big)
        _write_ranking(root / "prevbig.json", [_job("old", "Old", 1.0)])
        sec_big = rg.digest_sections(root / "big.json",
                                     root / "prevbig.json",
                                     pages_url="https://x.io/")
        text_big = "\n".join(sec_big or [])
        ns_big = rg.new_since_section_lines(sec_big or [])
        check("G2a big_diff: 🆕 só contagem (header + aviso, 2 linhas)",
              len(ns_big) == 2 and "evento de dataset novo" in ns_big[1])
        check("G2b big_diff NÃO gera ocultas da 🆕 (nada listado a deslocar)",
              not any("ocultas" in l for l in ns_big))
        check("G2c cap do ⚡ segue valendo no evento (2 Lidl + 1 oculta)",
              "ocultas pelo cap de empresa (top empresas: Lidl +1)"
              in text_big)
        # G3 — sync site×digest: mesma constante, mesma função
        check("G3 COMPANY_MAX_CARDS == 2 (fonte única: minimal_page)",
              COMPANY_MAX_CARDS == 2)
        sample = ([_job(f"l{i}", "Lidl", 15.0 - i) for i in range(5)]
                  + [_job("b", "Bosch", 1.0)])
        check("G3b corte do digest == apply_company_cap do site (sync total)",
              [j["id"] for j in rg._company_capped(sample, limit=5)]
              == [j["id"] for j in apply_company_cap(sample, limit=5)])


def main() -> int:
    test_a_helpers()
    test_b_monopoly()
    test_c_regressao()
    test_d_ordem()
    test_e_4096()
    test_f_watchlist_newsince()
    test_g_guardas()
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
