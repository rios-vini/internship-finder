"""Testes da fase F6.1 — Top 5 sobrevive ao encurtamento do Telegram (offline).

Cobre o bug real de 03/10 (cron 09:00 UTC, mensagem Telegram id 519): a
mensagem base + digest de 2.214 vagas estourou TELEGRAM_MAX_LEN = 4096 e o
compactador antigo colapsou o digest INTEIRO em 1 linha, matando a secao
"⚡ Top 5 do dia" — a feature mais valiosa do produto. O novo compactador tem
PRIORIDADE de secoes: base integra -> secao ⚡ com apply_urls -> 🔗 link por
ultimo; o resto do digest pode ser cortado/resumido.

Cenarios (spec F6.1 item 4):

(a) mensagem que CABE -> identica a hoje (regressao zero);
(b) base curta + digest gigante (cenario real de 03/10) -> compact com a
    secao ⚡ completa (5 apply_urls) E o 🔗 link, len <= 4096;
(c) base gigante (muitos problemas) -> problemas resumidos em contagem,
    Top 5 + link sobrevivem, len <= 4096;
(d) digest vazio/None -> comportamento de hoje preservado;
(e) Top 5 gigante (URLs longas) -> format_top5 ja trunca seguro; o compact
    respeita o teto (nivel 3: linhas inteiras, header preservado).

Extras (invariantes da implementacao):

- extrator ``top5_section_lines`` (header + corpo; [] quando ausente);
- format_top5 integrado ao compact (linhas identicas as da secao original);
- personal_sections apos a secao ⚡ nao corrompem a extracao;
- mensagem final termina no link (aposenso do texto util).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import ranking_digest as rg  # noqa: E402
import refresh_daily as rd  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _summary(*, eligible: int = 2214, total: int = 95801, n_fail: int = 4) -> dict:
    """Summary no shape real do run de 03/10 (4 de 127 fontes falharam)."""
    return {
        "run_id": "2026-10-03T09:00:02.347210+00:00",
        "total_collected": total,
        "eligible": eligible,
        "dedup_removed": 496,
        "ok": {"count": 113, "collected": 73138},
        "empty": 10,
        "timeout": [("successfactors:lidlstiftuP2", "Lidl", "TIMEOUT")],
        "error": [
            ("successfactors:careers", "AkzoNobel", "HTTP_500"),
            ("cornerstone:kuehne-nagel", "Kuehne+Nagel", "HTTP_500"),
            ("oracle:fa-exow-saasfaprod1/cx_1", "SMA", "HTTP_500"),
        ],
        "skipped": 0,
        "not_found": 0,
        "source_names": {},
    }


def _alert(kind: str, source: str, company: str, **extra) -> dict:
    d = {"type": kind, "source": source, "company": company}
    d.update(extra)
    return d


def _base_alerts_real() -> list[dict]:
    """Os 5 problemas reais de 03/10 (2 falhas de run + 3 alertas health)."""
    return [
        _alert("recurring_error", "successfactors:lidlstiftuP2", "Lidl",
               runs_seq=30),
        _alert("regression", "successfactors:careers", "AkzoNobel",
               ok_history=21),
        _alert("recurring_error", "cornerstone:kuehne-nagel", "Kuehne+Nagel",
               runs_seq=18),
        _alert("recurring_error", "oracle:fa-exow-saasfaprod1/cx_1", "SMA",
               runs_seq=17),
        _alert("zero_return", "avature", "Siemens Healthineers",
               ok_history=22, last_ok_collected=6),
    ]


def _job(i: int, *, apply_url: str | None = None, title: str | None = None,
         company: str | None = None, score: float | None = None,
         iso: str = "de") -> dict:
    return {
        "id": f"j{i}",
        "title": title or f"Praktikum Data Engineering {i} (m/w/d)",
        "company": company or f"Firma {i} GmbH",
        "location": "Berlin, Deutschland",
        "score": score if score is not None else round(16.6 - i * 0.25, 2),
        "url": f"https://jobs.example.com/jobs/{i}",
        "raw": {"apply_url": apply_url or f"https://apply.example.com/{i}"},
        "country_iso": iso,
    }


def _digest_gigante(n_jobs: int = 2214, *, top5_apply_len: int = 0) -> list[str]:
    """Digest no shape do digest_sections com ranking de 2.214 vagas.

    Perfil/score/novas/mudancas/materials/enrichment sao as secoes cortaveis;
    a secao ⚡ e a de valor; o link e sempre a ultima linha.
    """
    jobs = [_job(i) for i in range(n_jobs)]
    top5_lines = rg.format_top5(jobs).splitlines()
    if top5_apply_len:
        # URLs longas: cada apply_url com top5_apply_len chars de caminho
        jobs = [_job(i, apply_url=f"https://apply.example.com/{i}/" + "x" * top5_apply_len)
                for i in range(n_jobs)]
        top5_lines = rg.format_top5(jobs).splitlines()
    lines = ["", "🎯 Perfil e critérios ativos",
             "Áreas: Supply Chain · Procurement · BI · Analytics · RPA",
             "Localização principal: Germany (spec 'de')",
             "Tipo: Internship/Intern · Working Student · Praktikum — 29 marcadores ativos",
             "Sinais no score: área no título (+2) · skills (+0.75) · inglês (+1.5) · tipo (+1) · DE (+1)",
             "Score do run: min 3.5 · mediana 9.1 · máx 16.6 "
             f"({n_jobs} vagas elegíveis)"]
    lines += ["", "🆕 Novas vagas no Top 30 (23):"]
    lines += [f"  #{i} — vaga nova {i} — Acme (12.5)" for i in range(1, 31)]
    lines += ["", "🏆 Top 5 atual"]
    lines += [f"  {p}. Vaga {p} — Empresa ({16.5 - p})" for p in range(1, 6)]
    lines += ["", "📈 Mudanças no ranking (Top 30)"]
    lines += [f"  ↑ {d} — vaga {d} — Empresa (#{d} → #{d + 1})" for d in range(1, 16)]
    lines += ["", "🧪 Perfil Materials Engineering (ranking próprio)"]
    lines += [f"  {p}. Vaga Mat {p} — Empresa (mat 8.5)" for p in range(1, 6)]
    lines += ["", "🔎 Dados da página oficial (enrichment)"]
    lines += [f"  #{i} — vaga {i} — salário textual ok" for i in range(1, 31)]
    lines += ["", "⚡ Top 5 do dia (candidatura direta)"] + top5_lines
    lines += ["", "🔗 Ranking completo (todas as vagas elegíveis): "
             "https://rios-vini.github.io/internship-finder/"]
    return lines


def main() -> None:
    test_extract_top5()
    test_fits_regression_zero()
    test_real_scenario_0310()
    test_giant_base_problems()
    test_empty_digest()
    test_giant_top5()
    print()
    if FAILURES:
        print(f"FALHAS ({len(FAILURES)}):")
        for name in FAILURES:
            print(f"  - {name}")
        raise SystemExit(1)
    print("TUDO OK")


# ---------------------------------------------------------------------------
# (extra) extrator da secao ⚡
# ---------------------------------------------------------------------------

def test_extract_top5() -> None:
    print("== F6.1-x: top5_section_lines extrai header + corpo ==")
    sec = rg.top5_section_lines(
        ["", "🎯 Perfil", "Score", "", "⚡ Top 5 do dia (candidatura direta)",
         "1. A — B — 12.5 — https://x/a", "2. C — D — 11 — https://x/b",
         "", "🔗 Ranking: https://y/"])
    check("extrai header + linhas ate o blank", sec == [
        "⚡ Top 5 do dia (candidatura direta)",
        "1. A — B — 12.5 — https://x/a", "2. C — D — 11 — https://x/b"])
    check("secao ausente -> []", rg.top5_section_lines(["🎯 Perfil"]) == [])
    check("lista vazia -> []", rg.top5_section_lines([]) == [])
    check("secao no fim (sem blank seguinte) -> corpo inteiro",
          rg.top5_section_lines(["⚡ Top 5 do dia (candidatura direta)", "1. A"])
          == ["⚡ Top 5 do dia (candidatura direta)", "1. A"])
    # secoes pessoais (Fase 8) entram DEPOIS da ⚡ no digest final — o blank
    # entre elas termina a extracao no lugar certo
    full = ["", "⚡ Top 5 do dia (candidatura direta)", "1. A — B — 1 — u",
            "", "⚠️ Application reminders", "3 vaga(s) vencem nos próximos dias",
            "", "🔗 Ranking: https://y/"]
    check("extracao para no blank antes das secoes pessoais",
          rg.top5_section_lines(full) == [
              "⚡ Top 5 do dia (candidatura direta)", "1. A — B — 1 — u"])
    # contrato: digest_sections embute o header via constante (mesma string)
    check("header do digest_sections == header reconhecido pelo extrator",
          rg.TOP5_SECTION_HEADER.startswith(rg.TOP5_SECTION_PREFIX))


# ---------------------------------------------------------------------------
# (a) mensagem que cabe -> identica a hoje (regressao zero)
# ---------------------------------------------------------------------------

def test_fits_regression_zero() -> None:
    print("== F6.1-a: mensagem que cabe sai INTEGRA (regressao zero) ==")
    summary = _summary(eligible=50, total=400, n_fail=0)
    digest = ["", "🎯 Perfil e critérios ativos", "Score do run: min 3 · máx 16",
              "", "🆕 Novas vagas no Top 30", "  #1 — Nova — Acme (12.0)",
              "", "⚡ Top 5 do dia (candidatura direta)",
              "1. A — B — 12.5 — https://apply.example.com/1",
              "", "🔗 Ranking completo: https://x/"]
    base = rd.build_message(summary, [], 0, always_notify=True)
    msg = rd.build_message(summary, [], 0, always_notify=True,
                           digest_lines=digest)
    expected = (rd.build_message(summary, [], 0, always_notify=True)
                + "\n" + "\n".join(digest))
    check("mensagem com digest que cabe == base + digest (byte a byte)",
          msg == expected)
    check("base pura preservada no comeco", msg.startswith(base))
    check("termina no link", msg.endswith("🔗 Ranking completo: https://x/"))
    check("sem marcador de encurtamento", "encurtado" not in msg)


# ---------------------------------------------------------------------------
# (b) cenario real de 03/10: base curta + digest de 2.214 vagas
# ---------------------------------------------------------------------------

def test_real_scenario_0310() -> None:
    print("== F6.1-b: cenario real 03/10 — digest de 2.214 vagas ==")
    import json
    import tempfile
    jobs = [_job(i) for i in range(2214)]
    previous = [dict(j) for j in jobs[500:]]
    with tempfile.TemporaryDirectory(prefix="t_f61_") as tmp:
        root = Path(tmp)
        (root / "current.json").write_text(
            json.dumps(jobs), encoding="utf-8")
        (root / "previous.json").write_text(
            json.dumps(previous), encoding="utf-8")
        digest = rg.digest_sections(
            current_path=root / "current.json",
            previous_path=root / "previous.json",
            pages_url="https://rios-vini.github.io/internship-finder/")
    full = "\n".join(digest)
    check("digest simulado estoura 4096 (como no dia do bug)",
          len(full) > rd.TELEGRAM_MAX_LEN, )
    summary = _summary()  # run real: 95.801 brutas -> 2.214 elegiveis
    alerts = _base_alerts_real()
    msg = rd.build_message(summary, alerts, 2, always_notify=True,
                           disk_pct=90, digest_lines=digest)
    check("mensagem final cabe no Telegram", len(msg) <= rd.TELEGRAM_MAX_LEN)
    check("secao ⚡ preservada", "⚡ Top 5 do dia (candidatura direta)" in msg)
    apply_urls = msg.count("https://apply.example.com/")
    check("as 5 apply_urls do Top 5 sobrevivem", apply_urls == 5,
          )
    check("link do ranking completo por ultimo",
          msg.endswith("🔗 Ranking completo (todas as vagas elegíveis): "
                       "https://rios-vini.github.io/internship-finder/"))
    check("base operacional integra (problemas detalhados presentes)",
          "Problemas detectados" in msg and "Lidl" in msg
          and "recorrente há 30 runs" in msg)
    check("secoes cortaveis fora (perfil/mudancas/materials)",
          "Mudanças no ranking" not in msg
          and "Perfil Materials" not in msg)
    top5_in_msg = rg.top5_section_lines(msg.split("\n"))
    check("linhas do Top 5 identicas as do digest original (format_top5)",
          top5_in_msg == rg.top5_section_lines(digest))




# ---------------------------------------------------------------------------
# (c) base gigante: problemas resumidos em contagem
# ---------------------------------------------------------------------------

def test_giant_base_problems() -> None:
    print("== F6.1-c: base gigante — problemas viram contagem ==")
    n_prob = 60
    summary = _summary(n_fail=n_prob)
    summary["timeout"] = []  # contagem esperada == n_prob exatamente
    summary["error"] = [
        ("successfactors:tenant", f"Empresa Gigante {i}", "HTTP_500")
        for i in range(n_prob)]
    # MESMA serie (source, company) das falhas: no cenario real os alertas
    # health reincidem sobre as series que falharam no run (dedup no
    # build_message — aqui cada falha gera 1 linha, nao 2).
    alerts = [
        _alert("recurring_error", "successfactors:tenant",
               f"Empresa Gigante {i}", runs_seq=30)
        for i in range(n_prob)]
    digest = ["", "🎯 Perfil e critérios ativos"] \
        + [f"linha de perfil {i} — " + "x" * 120 for i in range(12)] \
        + ["", "⚡ Top 5 do dia (candidatura direta)"] \
        + rg.format_top5([_job(i) for i in range(5)]).splitlines() \
        + ["", "🔗 Ranking completo: https://x/"]
    msg = rd.build_message(summary, alerts, 2, always_notify=True,
                           digest_lines=digest)
    check("mensagem com base gigante cabe", len(msg) <= rd.TELEGRAM_MAX_LEN)
    check("lista de problemas colapsada em contagem",
          f"⚠️ {n_prob} problemas (ver ranking)" in msg)
    check("detalhe dos problemas removido", "Empresa Gigante 59" not in msg)
    check("Top 5 sobrevive com apply_urls",
          "⚡ Top 5 do dia" in msg
          and msg.count("https://apply.example.com/") == 5)
    check("link por ultimo", msg.endswith("🔗 Ranking completo: https://x/"))


# ---------------------------------------------------------------------------
# (d) digest vazio/None -> comportamento de hoje
# ---------------------------------------------------------------------------

def test_empty_digest() -> None:
    print("== F6.1-d: digest vazio/None — comportamento de hoje ==")
    summary = _summary(eligible=50, total=400, n_fail=4)
    alerts = _base_alerts_real()
    # digest None (gate negado / falha na montagem): mensagem base pura
    msg_none = rd.build_message(summary, alerts, 2, always_notify=True,
                                digest_lines=None)
    base_only = rd.build_message(summary, alerts, 2, always_notify=True)
    check("digest None == mensagem base pura (byte a byte)",
          msg_none == base_only)
    # digest vazio: idem (o if digest_lines e falsy)
    msg_empty = rd.build_message(summary, alerts, 2, always_notify=True,
                                 digest_lines=[])
    check("digest [] == mensagem base pura", msg_empty == base_only)
    # digest SEM secao ⚡ que estoura: compact pre-F6.1 (1 linha + link)
    digest = ["", "🎯 Perfil"] + ["z" * 100 for _ in range(50)] \
        + ["", "🔗 Ranking completo: https://x/"]
    msg = rd.build_message(summary, alerts, 2, always_notify=True,
                           digest_lines=digest)
    check("sem ⚡ -> linha unica pre-F6.1 com o link",
          "Resumo do ranking encurtado" in msg and "https://x/" in msg)
    check("sem ⚡ -> cabe no limite", len(msg) <= rd.TELEGRAM_MAX_LEN)


# ---------------------------------------------------------------------------
# (e) Top 5 gigante: format_top5 ja trunca; compact respeita o teto
# ---------------------------------------------------------------------------

def test_giant_top5() -> None:
    print("== F6.1-e: Top 5 gigante (URLs longas) — teto respeitado ==")
    summary = _summary()
    alerts = _base_alerts_real()
    # URLs de 300 chars: desde a F12.5 a URL sai INTEIRA (elipse dentro do
    # link = 404 ao clicar; bug real do Telegram de 05/10). As linhas
    # ficam longas (~360 chars) — forçamos estouro com perfil gigante
    # para exercitar o compact com o Top 5 de linhas longas.
    jobs = [_job(i, apply_url=f"https://apply.example.com/{i}/"
                + "y" * 300) for i in range(5)]
    top5_lines = rg.format_top5(jobs).splitlines()
    check("F12.5: URLs de 300 chars saem INTEIRAS no Top 5",
          all(f"https://apply.example.com/{i}/" + "y" * 300 in ln
              for i, ln in enumerate(top5_lines)))
    digest = ["", "🎯 Perfil e critérios ativos"] \
        + ["linha de perfil " + "x" * 240 for _ in range(14)] \
        + ["", "⚡ Top 5 do dia (candidatura direta)"] + top5_lines \
        + ["", "🔗 Ranking completo: https://x/"]
    msg = rd.build_message(summary, alerts, 2, always_notify=True,
                           digest_lines=digest)
    check("mensagem com Top 5 de linhas longas cabe",
          len(msg) <= rd.TELEGRAM_MAX_LEN)
    check("as 5 URLs inteiras sobrevivem ao compact (F12.5: sem clip)",
          msg.count("https://apply.example.com/") == 5)
    check("link por ultimo", msg.endswith("🔗 Ranking completo: https://x/"))

    # Nivel 3 forcado: linhas de vaga GIGANTES (bypass do clip de TITULO
    # via monkeypatch do limite em runtime — a constante do codigo intacta).
    # O compact corta por LINHAS INTEIRAS: mantem header + as linhas que
    # couberem, nunca no meio de uma linha.
    import unittest.mock as mock
    giant_lines = [f"{i}. " + "T" * 1500 for i in range(1, 6)]
    digest_g = ["", "🎯 Perfil"] \
        + ["linha " + "x" * 200 for _ in range(30)] \
        + ["", "⚡ Top 5 do dia (candidatura direta)"] + giant_lines \
        + ["", "🔗 Ranking completo: https://x/"]
    summary60 = _summary(n_fail=60)
    summary60["error"] = [("s", f"E{i}", "HTTP_500") for i in range(60)]
    alerts60 = [_alert("recurring_error", f"s{i}", f"E{i}", runs_seq=30)
                for i in range(60)]
    with mock.patch.object(rg, "TOP5_TITLE_LIMIT", 1500):
        msg_g = rd.build_message(summary60, alerts60, 2, always_notify=True,
                                 digest_lines=digest_g)
    check("nivel 3: mensagem cabe mesmo com linhas de 1500 chars",
          len(msg_g) <= rd.TELEGRAM_MAX_LEN)
    check("nivel 3: header da secao preservado",
          "⚡ Top 5 do dia" in msg_g)
    kept_lines = [ln for ln in msg_g.split("\n")
                  if ln.startswith(("2.", "3.", "4.", "5."))]
    check("nivel 3: nenhuma linha cortada no meio (inteiras ou ausentes)",
          all(len(ln) in (0, 1503) for ln in kept_lines))
    check("nivel 3: link por ultimo", msg_g.endswith("🔗 Ranking completo: https://x/"))


if __name__ == "__main__":
    main()
