#!/usr/bin/env python3
"""F98 — reply-tracking + cadência + score_1_5 do dono (ITENS 12 + 9-restrito).

Contratos travados aqui (spec: ~/.hermes/handoff/f98-reply-tracking/
ESPECIFICACAO.md):

1. CADÊNCIA (status Sent, a partir de ``enviada``): +7d nudge · +14d
   ping · +28d encerra. Vivos (Interview/Offer/Responded) NUNCA ganham
   cadência — conversa viva não é encerrada automaticamente.
2. GUARD 30D company-wide: cada ``Rejected`` ativa guard por empresa
   (rejeição sem ``resposta`` usa ``enviada``); guard VENCE —
   ``(hoje - rejeição).days >= 30`` = empresa liberada. Uma rejeição da
   Lidl ≠ rejeição de todas as vagas Lidl para sempre (o teste prova a
   liberação no dia 30 e o aviso "recém-liberada" na janela de 7d).
   Isolamento: rejeição da Lidl NUNCA afeta REWE; strings distintas
   (Lidl vs Lidl Stiftung) NÃO casam (match casefold exato).
3. ITEM 9 RESTRITO — guardrails da casa: score 1–5 é do DONO; veredito
   é ARITMÉTICA da escala career-ops (≥4.5 APLICAR · 4.0–4.4 VALE ·
   3.5–3.9 OVERRIDE · <3.5 CONTRA); reply_tracking.py é STANDALONE
   (zero imports de src/internship_finder, zero rede) e o pipeline não
   o importa — nenhum threshold automático no funil; score 0–10 do
   pipeline intocado (H1–H5).
4. Template: templates/registro_candidaturas.md é parseável pelo
   PRÓPRIO parser (cabeçalhos reconhecidos, zero linhas inválidas) e
   carrega o bloco da regra da casa + as 5 dimensões + a escala.
5. Parser fail-loud: status desconhecido, data ilegível, coluna a mais
   = linha inválida COM MOTIVO — nunca adivinhada. Células faltando
   são preenchidas; CRLF tolerado; classificação por CABEÇALHO (a
   ordem das seções não importa).
6. Noise-first: rejeições colapsadas em contagem por empresa (o título
   de uma rejeitada NUNCA vira linha completa); relatório em ordem
   encerra → ping → nudge.
7. CLI somente-leitura: --init copia o template byte a byte e RECUSA
   sobrescrever; exit 0 quieto · 1 atenção · 2 registro ilegível.

Fixtures: datas sintéticas congeladas (``--today 2026-10-22``); cenário
espelha o fluxo real do dono (Lidl rejeita Preismanagement → guard
30d → nova candidatura Lidl avisada). Zero rede; data/ intocada.

Uso:  .venv/bin/python scripts/test_f98.py
"""
from __future__ import annotations

import io
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import reply_tracking as rt  # noqa: E402

RESULTS: list[tuple[bool, str]] = []

TODAY = date(2026, 10, 22)

CAND_HEADER = "| enviada | empresa | vaga | id_fonte | status | resposta | score_1_5 | nota |"
CAND_SEP = "|---|---|---|---|---|---|---|---|"
TRIAGE_HEADER = "| empresa | vaga | id_fonte | score_1_5 | verdict | notas |"
TRIAGE_SEP = "|---|---|---|---|---|---|"


def check(label: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((bool(cond), label))
    print(("  [OK] " if cond else "  [FAIL] ") + label
          + (f"  [{detail}]" if detail and not cond else ""))


def make_reg(cand_rows: list[str], triage_rows: list[str] | None = None) -> str:
    """Documento mínimo com as tabelas (classificação é por cabeçalho)."""
    doc = "# REGISTRO\n\n"
    if triage_rows is not None:
        doc += TRIAGE_HEADER + "\n" + TRIAGE_SEP + "\n"
        doc += "\n".join(triage_rows) + "\n\n"
    doc += CAND_HEADER + "\n" + CAND_SEP + "\n"
    doc += "\n".join(cand_rows)
    return doc


def run(text: str, today: date = TODAY):
    reg = rt.parse_registro(text, today)
    out = io.StringIO()
    with redirect_stdout(out):
        report, attention = rt.build_report(reg, today)
    return reg, report, attention


def cand(d: str, emp: str, vaga: str, status: str = "Sent",
         resp: str = "", score: str = "", ident: str = "") -> str:
    return f"| {d} | {emp} | {vaga} | {ident} | {status} | {resp} | {score} |  |"


def main() -> int:
    print("F98: reply-tracking + cadência + score_1_5 (ITENS 12 + 9-restrito)")

    # ------------------------------------------------ A. cadência (Sent)
    print("A. cadência: nudge +7d · ping +14d · encerra +28d (limites)")
    a6 = rt.cadence_of(date(2026, 10, 16), TODAY)
    a7 = rt.cadence_of(date(2026, 10, 15), TODAY)
    a13 = rt.cadence_of(date(2026, 10, 9), TODAY)
    a14 = rt.cadence_of(date(2026, 10, 8), TODAY)
    a27 = rt.cadence_of(date(2026, 9, 25), TODAY)
    a28 = rt.cadence_of(date(2026, 9, 24), TODAY)
    a40 = rt.cadence_of(date(2026, 9, 12), TODAY)
    check("A1. +6d = aguardando", a6 == ("aguardando", 6), str(a6))
    check("A2. +7d = nudge", a7 == ("nudge", 7), str(a7))
    check("A3. +13d = nudge", a13 == ("nudge", 13), str(a13))
    check("A4. +14d = ping", a14 == ("ping", 14), str(a14))
    check("A5. +27d = ping", a27 == ("ping", 27), str(a27))
    check("A6. +28d = encerra", a28 == ("encerra", 28), str(a28))
    check("A7. +40d = encerra", a40 == ("encerra", 40), str(a40))
    _reg, rep, attn = run(make_reg(
        [cand("2026-10-18", "DHL", "Supply Chain Intern"),
         cand("2026-10-19", "DHL", "Outra")]))
    check("A8. foresight: nudge em ≤3d aparece (4d); 3d fica calado",
          ("AGUARDANDO" in rep) and ("Outra" not in rep), rep)
    check("A9. nada vencendo + sem avisos = sem atenção (🙂 + exit 0)",
          (not attn) and ("Nada vencendo" in rep), rep)

    # --------------------------------------------- B. guard 30d company-wide
    print("B. guard 30d company-wide (rejeição ≠ bloqueio eterno)")
    g = rt.guards_of({"lidl": [(date(2026, 10, 18), "Lidl")]}, TODAY)[0]
    check("B1. rejeição 4d atrás: guard ATIVO (26d restantes)",
          g.active and g.until == date(2026, 11, 17) and g.days_left == 26,
          f"{g}")
    g30 = rt.guards_of({"lidl": [(date(2026, 9, 22), "Lidl")]}, TODAY)[0]
    check("B2. dia 30 = liberada (guard EXPIROU — nunca eterno)",
          (not g30.active) and g30.days_left == 0 and g30.until == TODAY,
          f"{g30}")
    g38 = rt.guards_of({"lidl": [(date(2026, 9, 14), "Lidl")]}, TODAY)[0]
    check("B3. expirou há 8d: fora da janela de aviso (7d)",
          (not g38.active) and g38.days_left == 8, f"{g38}")
    _reg, rep, _attn = run(make_reg([
        cand("2026-09-10", "Lidl", "Preismanagement", "Rejected",
             resp="2026-09-15"),
        cand("2026-09-08", "BASF", "Global HR Reporting", "Rejected",
             resp="2026-09-14")]))
    check("B4. relatório: 'recém-liberada' + '≠ bloqueio eterno'",
          ("recém-liberada" in rep) and ("bloqueio eterno" in rep), rep)
    _reg, rep, _attn = run(make_reg([
        cand("2026-10-18", "Lidl", "Preismanagement", "Rejected",
             resp="2026-10-18"),
        cand("2026-10-08", "REWE", "Einkauf Praktikum")]))
    guard_block = rep.split("GUARD 30D", 1)[1].split("\n\n", 1)[0] \
        if "GUARD 30D" in rep else ""
    check("B5. isolamento: rejeição Lidl guarda SÓ Lidl (REWE segue no "
          "ping, fora do guard)",
          ("Lidl" in guard_block) and ("REWE" not in guard_block)
          and ("PING" in rep) and ("REWE" in rep), guard_block)
    gs = rt.guards_of({"lidl": [(date(2026, 9, 20), "Lidl"),
                                (date(2026, 10, 18), "Lidl")]}, TODAY)
    check("B6. 2 rejeições: a MAIS RECENTE governa (18/10)",
          len(gs) == 1 and gs[0].reject_date == date(2026, 10, 18), str(gs))
    _reg, rep, _attn = run(make_reg([
        cand("2026-10-01", "Lidl", "Preismanagement", "Rejected"),  # sem resp
        cand("2026-10-20", "Lidl", "Int BI")]))
    check("B7. sem resposta: guard usa o ENVIO (01/10) e candidatura "
          "20/10 avisada como enviada sob guard",
          ("ENVIADAS SOB GUARD" in rep) and ("rejeição 2026-10-01" in rep), rep)
    ug = rt.guard_at_send({"lidl": [(date(2026, 10, 18), "Lidl")]},
                          "lidl", date(2026, 11, 17))
    check("B8. enviada 30d após a rejeição: NÃO é sob guard (venceu)",
          ug is None, str(ug))
    ug2 = rt.guard_at_send({"lidl": [(date(2026, 10, 18), "Lidl")]},
                           "lidl", date(2026, 11, 18))
    check("B9. enviada 31d após: livre p/ sempre", ug2 is None, str(ug2))
    ug3 = rt.guard_at_send({"lidl": [(date(2026, 10, 18), "Lidl")]},
                           "lidl", date(2026, 10, 20))
    check("B10. enviada 2d após a rejeição: SOB guard (28d)",
          ug3 is not None and ug3.days_left == 28, str(ug3))
    ug4 = rt.guard_at_send({"lidl": [(date(2026, 10, 18), "Lidl")]},
                           "rewe ", date(2026, 10, 20))
    check("B11. isolamento por empresa: REWE não guarda pela rejeição Lidl",
          ug4 is None, str(ug4))
    ug5 = rt.guard_at_send({"lidl stiftung": [(date(2026, 10, 18), "Lidl Stiftung")]},
                           "lidl", date(2026, 10, 20))
    check("B12. match casefold EXATO: 'lidl stiftung' ≠ 'lidl' (usar UM "
          "nome por empresa)", ug5 is None, str(ug5))
    _reg, rep, _attn = run(make_reg([
        cand("2026-10-18", "Lidl", "Preismanagement", "Rejected",
             resp="2026-10-18"),
        cand("2026-10-19", "LIDL", "Int BI")]))  # caixa alta
    check("B13. casefold: 'LIDL' casa com 'Lidl' no guard",
          ("ENVIADAS SOB GUARD" in rep), rep)
    older = rt.guard_at_send({"lidl": [(date(2026, 9, 20), "Lidl"),
                                       (date(2026, 10, 18), "Lidl")]},
                             "lidl", date(2026, 10, 5))
    check("B14. rejeição ANTIGA cobre envio ANTERIOR à mais recente",
          older is not None and older.reject_date == date(2026, 9, 20)
          and older.days_left == 15, str(older))

    # ------------------------------------------- C. score 1–5 + veredito (dono)
    print("C. score_1_5 + verdict derivado (aritmética — nunca LLM)")
    for s, want in ((5.0, "APLICAR"), (4.5, "APLICAR"), (4.4, "VALE"),
                    (4.0, "VALE"), (3.9, "OVERRIDE"), (3.5, "OVERRIDE"),
                    (3.4, "CONTRA"), (1.0, "CONTRA")):
        got = rt.verdict_of(s)
        check(f"C1. {s} → {want}", got == want, got)
    v, err = rt.parse_score("4,5")
    check("C2. '4,5' (vírgula PT) → 4.5", (v, err) == (4.5, None), f"{v},{err}")
    v, err = rt.parse_score("4")
    check("C3. '4' → 4.0", (v, err) == (4.0, None), f"{v},{err}")
    v, err = rt.parse_score("")
    check("C4. vazio → (None, None) — sem score NÃO é erro",
          (v, err) == (None, None))
    v, err = rt.parse_score("alto")
    check("C5. lixo → aviso (fail-loud, nunca adivinha)",
          v is None and err is not None, err or "")
    v, err = rt.parse_score("5.5")
    check("C6. 5.5 fora da escala 1–5 → aviso",
          v is None and err is not None and "escala" in err, err or "")
    v, err = rt.parse_score("0.5")
    check("C7. 0.5 fora da escala → aviso",
          v is None and err is not None and "escala" in err, err or "")
    tri = ("| Lidl | Int BI | sf:1 | 4.5 | CONTRA | x |\n"
           "| BASF | JC | AA | 2.5 | CONTRA | y |\n"
           "| X | Y |  |  | APLICAR | z |\n")
    reg, _rep, _attn = run(make_reg([cand("2026-10-21", "A", "B")],
                                    triage_rows=tri.splitlines()))
    warns = " ".join(m for _ln, m in reg.warnings)
    check("C8. veredito ≠ derivado → aviso (4.5/CONTRA)",
          ("4.5" in warns) and ("APLICAR" in warns), warns)
    check("C9. veredito conferente → sem aviso (2.5/CONTRA)",
          ("2.5" not in warns), warns)
    mismatches = [m for _l, m in reg.warnings if "derivado" in m]
    check("C10. veredito sem score: sem mismatch (só 1 aviso no total)",
          len(mismatches) == 1 and reg.triage[2].score is None
          and reg.triage[2].verdict == "APLICAR", str(reg.warnings))
    tri2 = "| A | B |  | 4.0 | TALVEZ |  |\n"
    reg, _rep, _attn = run(make_reg([cand("2026-10-21", "A", "B")],
                                    triage_rows=tri2.splitlines()))
    check("C11. veredito fora do vocabulário → aviso 'desconhecido'",
          any("desconhecido" in m for _l, m in reg.warnings)
          and reg.triage[0].verdict is None, str(reg.warnings))
    reg, rep, _attn = run(make_reg(
        [cand("2026-10-21", "A", "B")],
        triage_rows="| RELX | Associate | sf:9 | 4.5 |  |  |\n"
                    "| Lidl | Int BI | sf:1 |  |  |  |\n".splitlines()))
    check("C12. relatório deriva vereditos do dono p/ copiar + conta "
          "pendentes de score",
          ("4.5 → APLICAR" in rep) and ("1 sem score_1_5" in rep), rep)

    # ------------------------------------------------- D. template do registro
    print("D. template templates/registro_candidaturas.md (contrato lockstep)")
    tpath = ROOT / "templates" / "registro_candidaturas.md"
    ttext = tpath.read_text(encoding="utf-8")
    reg, _rep, _attn = run(ttext)
    check("D1. template existe e é parseável pelo próprio parser "
          "(zero inválidas, zero avisos, zero linhas)",
          tpath.is_file() and not reg.invalid and not reg.warnings
          and not reg.candidaturas and not reg.triage, str(reg.invalid))
    for st in ("Sent", "Interview", "Offer", "Rejected", "Responded"):
        check(f"D2. vocabulário de status no template: {st}", st in ttext)
    for needle in ("NUNCA", "holístico", "0–10", "INTOCADO", "threshold"):
        check(f"D3. regra da casa no template: '{needle}'", needle in ttext)
    for dim in ("Match CV", "North-star", "Comp", "Sinais culturais", "Red flags"):
        check(f"D4. dimensão da rubrica: {dim}", dim in ttext)
    check("D5. escala career-ops no template (rótulos da spec)",
          all(k in ttext for k in ("APLICAR", "VALE", "OVERRIDE", "CONTRA")))
    check("D6. cadência documentada: +7d · +14d · +28d",
          ("+7d" in ttext) and ("+14d" in ttext) and ("+28d" in ttext))
    check("D7. guard 30d documentado + anti-eterno",
          ("30 dias" in ttext) and ("bloqueio eterno" in ttext))
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "nested" / "registro.md"
        rc = rt.main(["--init", "--registro", str(target)])
        check("D8. --init cria registro do template (dirs pais inclusos) "
              "byte a byte",
              rc == 0 and target.read_bytes() == tpath.read_bytes())
        rc = rt.main(["--init", "--registro", str(target)])
        check("D9. --init NUNCA sobrescreve (exit 2, arquivo intacto)",
              rc == 2 and target.read_bytes() == tpath.read_bytes())

    # ------------------------------------------------- E. parser fail-loud
    print("E. parser: robusto + fail-loud (nunca adivinha)")
    base = [cand("2026-10-20", "Lidl", "Int BI")]
    r1, _, _ = run(make_reg(base))
    r2, _, _ = run(make_reg(base).replace("\n", "\r\n"))
    check("E1. CRLF == LF (mesma extração)",
          [(c.empresa, c.vaga) for c in r1.candidaturas]
          == [(c.empresa, c.vaga) for c in r2.candidaturas])
    reg, _, _ = run(make_reg(["| 2026-10-20 | Lidl | Int BI |  | Sent"]))
    check("E2. células faltando no fim = preenchidas (não inválida)",
          len(reg.candidaturas) == 1 and not reg.invalid, str(reg.invalid))
    reg, _, _ = run(make_reg(["| 2026-10-20 | Lidl | V |  | Sent |  |  |  | x |"]))
    check("E3. coluna a mais → linha inválida com motivo",
          len(reg.invalid) == 1 and "colunas" in reg.invalid[0][1],
          str(reg.invalid))
    reg, _rep, _ = run(make_reg([cand("2026-10-20", "Lidl", "V", status="Ghosted")]))
    check("E4. status desconhecido → inválida com motivo (nunca adivinha)",
          any("Ghosted" in m for _l, m in reg.invalid), str(reg.invalid))
    reg, _, _ = run(make_reg([cand("20/10/2026", "Lidl", "V")]))
    check("E5. DD/MM/AAAA aceito", len(reg.candidaturas) == 1
          and reg.candidaturas[0].enviada == date(2026, 10, 20))
    reg, _, _ = run(make_reg([cand("20/10/26", "Lidl", "V")]))
    check("E6. DD/MM/AA → inválida (ano de 4 dígitos obrigatório)",
          len(reg.candidaturas) == 0 and bool(reg.invalid), str(reg.invalid))
    reg, rep, _ = run(make_reg([cand("2027-01-05", "Lidl", "V")]))
    check("E7. envio no futuro → aviso (linha mantida)",
          any("futuro" in m for _l, m in reg.warnings)
          and len(reg.candidaturas) == 1, str(reg.warnings))
    reg, _, _ = run("# sem tabelas\nsó texto\n")
    check("E8. zero tabelas de pipe → inválido severo (exit 2 no CLI)",
          any("sem nenhuma tabela" in m for _l, m in reg.invalid))
    reg, _, _ = run("| coluna | outra |\n|---|---|\n| x | y |\n")
    check("E9. tabela com cabeçalho alienígena → nenhuma reconhecível",
          any("reconhecível" in m for _l, m in reg.invalid))
    so_triagem = ("# só triagem\n\n" + TRIAGE_HEADER + "\n" + TRIAGE_SEP
                  + "\n| A | B |  | 4.0 |  |  |\n")
    reg, rep, attn = run(so_triagem)
    check("E10. só triagem (sem tabela de candidaturas) → aviso + atenção",
          any("CANDIDATURAS" in m for _l, m in reg.warnings) and attn
          and len(reg.triage) == 1, str(reg.warnings))
    reg, _, _ = run(make_reg(
        ["| 2026-10-20 | **Lidl** | **Int BI** |  | sent |  |  |  |"]))
    check("E11. células em **negrito** limpas + status casefold",
          len(reg.candidaturas) == 1 and reg.candidaturas[0].empresa == "Lidl"
          and reg.candidaturas[0].status == "SENT", str(reg.invalid))
    swapped = ("# t\n\n" + CAND_HEADER + "\n" + CAND_SEP + "\n"
               + cand("2026-10-20", "Lidl", "V") + "\n\n"
               + TRIAGE_HEADER + "\n" + TRIAGE_SEP + "\n"
               + "| A | B |  | 4.0 |  |  |\n")
    reg, _, _ = run(swapped)
    check("E12. seções em qualquer ordem (classificação por cabeçalho)",
          len(reg.candidaturas) == 1 and len(reg.triage) == 1 and not reg.invalid)
    reg, _, _ = run(make_reg([cand("2026-10-20", "Lidl", "V", resp="amanhã")]))
    check("E13. resposta não-data → linha inválida com motivo",
          any("resposta" in m for _l, m in reg.invalid), str(reg.invalid))

    # ------------------------------------------- F. noise-first no relatório
    print("F. relatório noise-first (ruído colapsado, ordem, exits)")
    rows = [
        cand("2026-09-24", "Lidl", "SAP BI Reporting"),          # encerra
        cand("2026-10-08", "REWE", "Einkauf Praktikum"),        # ping
        cand("2026-10-15", "Bosch", "Einkauf Praktikum"),       # nudge
        cand("2026-10-01", "Lidl", "Preismanagement", "Rejected",
             resp="2026-10-18"),
        cand("2026-10-01", "KPMG", "Data Science", "Rejected",
             resp="2026-10-05"),
        cand("2026-10-14", "RELX", "Associate", "Interview",
             resp="2026-10-21"),
    ]
    reg, rep, attn = run(make_reg(rows))
    check("F1. rejeitadas NUNCA viram linha completa (título ausente; "
          "só a contagem)",
          ("Preismanagement" not in rep) and ("Data Science" not in rep)
          and ("2 rejeições em 2 empresas" in rep), rep)
    check("F2. ruído por empresa: 'Lidl ×1, KPMG ×1'",
          ("Lidl ×1" in rep) and ("KPMG ×1" in rep), rep)
    order = (rep.index("ENCERRA"), rep.index("PING"), rep.index("NUDGE"))
    check("F3. ordem noise-first: encerra → ping → nudge",
          order[0] < order[1] < order[2], str(order))
    check("F4. sinais listados (Interview) e sem cadência",
          ("SINAIS" in rep) and ("Interview: RELX" in rep)
          and ("ENCERRA" not in rep.split("SINAIS")[1]), rep)
    check("F5. algo vencendo → atenção (exit 1)", attn)
    reg, rep, attn = run(make_reg([cand("2026-10-21", "A", "B"),
                                   cand("2026-10-22", "C", "D")]))
    check("F6. tudo fresco → sem atenção + 🙂 + próximo nudge datado",
          (not attn) and ("Nada vencendo" in rep)
          and ("2026-10-28" in rep), rep)

    # ------------------------------------------- G. CLI somente-leitura
    print("G. CLI: --today determinístico, default, exits")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "r.md"
        p.write_text(make_reg(rows), encoding="utf-8")
        cmd = [sys.executable, str(ROOT / "scripts" / "reply_tracking.py"),
               "--registro", str(p), "--today", "2026-10-22"]
        out1 = subprocess.run(cmd, capture_output=True, text=True)
        out2 = subprocess.run(cmd, capture_output=True, text=True)
        check("G1. determinístico: 2 runs byte a byte + exit 1",
              out1.stdout == out2.stdout and out1.returncode == 1,
              f"rc={out1.returncode}")
        missing = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "reply_tracking.py"),
             "--registro", str(Path(tmp) / "nope.md")],
            capture_output=True, text=True)
        check("G2. registro ausente → exit 2 com --init no stderr",
              missing.returncode == 2 and "--init" in missing.stderr,
              missing.stderr)
        bad = Path(tmp) / "bad.md"
        bad.write_text("| x | y |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
        out3 = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "reply_tracking.py"),
             "--registro", str(bad), "--today", "2026-10-22"],
            capture_output=True, text=True)
        check("G3. nenhuma tabela reconhecível → exit 2",
              out3.returncode == 2, out3.stdout)
        out4 = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "reply_tracking.py"),
             "--init"], capture_output=True, text=True, cwd=tmp)
        default_target = Path(tmp) / "data" / "personal" / "registro_candidaturas.md"
        check("G4. --init default: cria data/personal/registro_candidaturas.md "
              "(gitignored — nunca versionado/publicado)",
              out4.returncode == 0 and default_target.is_file()
              and default_target.read_bytes() == tpath.read_bytes(),
              out4.stdout + out4.stderr)
    check("G5. constante do default = data/personal/registro_candidaturas.md",
          str(rt.DEFAULT_REGISTRO) == "data/personal/registro_candidaturas.md")

    # --------------------------------------- H. guardrails da casa (ITEM 9)
    print("H. guardrails: LLM não decide; pipeline intocado")
    src = (ROOT / "scripts" / "reply_tracking.py").read_text(encoding="utf-8")
    body = src.split('"""', 2)[2]  # código sem docstring
    check("H1. reply_tracking.py é STANDALONE (zero imports de src/)",
          "internship_finder" not in body)
    check("H2. zero rede (sem urllib/requests/httpx/socket)",
          all(m not in body for m in ("urllib", "requests", "httpx", "socket")))
    pipeline_mods = list((ROOT / "src" / "internship_finder").glob("*.py")) + [
        ROOT / "scripts" / "refresh_daily.py",
        ROOT / "scripts" / "ranking_digest.py",
        ROOT / "scripts" / "publish_pages.py",
    ]
    leakers = [f.name for f in pipeline_mods
               if f.is_file() and "reply_tracking" in
               f.read_text(encoding="utf-8", errors="ignore")]
    check("H3. pipeline não importa reply_tracking (src/ + entrypoints)",
          not leakers, str(leakers))
    check("H4. vocabulário de status == spec (5, fechado)",
          rt.STATUSES == ("SENT", "INTERVIEW", "OFFER", "REJECTED", "RESPONDED"))
    check("H5. veredito == escala career-ops + constantes da cadência/guard",
          rt.VERDICTS == ("APLICAR", "VALE", "OVERRIDE", "CONTRA")
          and rt.NUDGE_DAYS == 7 and rt.PING_DAYS == 14
          and rt.CLOSE_DAYS == 28 and rt.GUARD_DAYS == 30)

    fails = [label for ok, label in RESULTS if not ok]
    print(f"\nF98: {len(RESULTS)} checks, {len(fails)} falhas")
    if fails:
        for f in fails:
            print(f"  FAIL: {f}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
