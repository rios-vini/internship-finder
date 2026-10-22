#!/usr/bin/env python3
"""reply_tracking.py — F98: cadência de follow-up + guard 30d do REGISTRO.

Origem: ITENS-DELEGACAO-HERMES.md ITEM 12 (reply-tracking + cadência) +
ITEM 9 RESTRITO (colunas score_1_5 + verdict do registro). Lê o REGISTRO
de candidaturas do dono (markdown estruturado, template em
``templates/registro_candidaturas.md``) e APONTA o que precisa de ação
hoje — é SOMENTE-LEITURA: nunca escreve no registro, nunca marca vaga,
nunca decide nada por conta própria.

Regra da casa (guardrail ITEM 9): o ``score_1_5`` é o score HOLÍSTICO do
DONO (5 dimensões: match CV, north-star, comp, sinais culturais, red
flags). Este script só faz ARITMÉTICA sobre o que o dono escreveu —
deriva o veredito da escala career-ops (≥4.5 APLICAAR; 4.0–4.4 VALE;
3.5–3.9 OVERRIDE; <3.5 CONTRA — rótulos APLICAR/VALE/OVERRIDE/CONTRA) e
AVISA quando o veredito escrito diverge do derivado. LLM/pipeline NUNCA
decide ranking/veredito: este módulo não importa NADA de
``src/internship_finder`` (garantido por contrato no test_f98) e o score
0–10 interno do pipeline fica intocado — o 1–5 é camada de triagem do
dono no REGISTRO, sem threshold automático no funil.

Cadência (apenas status ``Sent``, a partir da data de envio):
+7 dias nudge 👋 · +14 dias ping 🏓 · +28 dias encerra ⏹.
Status vivos (``Interview``/``Offer``/``Responded``) não têm cadência —
uma conversa viva NUNCA é encerrada automaticamente.

Rejeição company-wide com data-guard de 30 dias: cada linha ``Rejected``
ativa um guard por empresa (rejeição sem ``resposta`` usa a data de
``enviada``). O guard AVISA (não bloqueia — a decisão é do dono) e
VENCE: ``(hoje - rejeição).days >= 30`` = empresa liberada. Uma rejeição
da Lidl ≠ rejeição de todas as vagas Lidl para sempre. Rejeições de
empresas diferentes nunca se misturam (match casefold por string exata
da coluna ``empresa``).

Noise-first: o relatório despacha o ruído primeiro (encerra acumulado →
ping → nudge), colapsa rejeições em contagem por empresa (nunca uma
linha por recusa) e mantém os sinais limpos no fim. Linha que a máquina
não consegue classificar (status desconhecido, data ilegível) vira
linha inválida com motivo — NUNCA é adivinhada.

Contratos:
- ``parse_registro(text)`` classifica TODAS as tabelas de pipe do arquivo
  pelo CABEÇALHO (não pela seção): ``| enviada | empresa | vaga |
  id_fonte | status | resposta | score_1_5 | nota |`` (candidaturas) e
  ``| empresa | vaga | id_fonte | score_1_5 | verdict | notas |``
  (triagem). Cabeçalho reconhecível em qualquer ordem/seção; tabelas com
  outro cabeçalho são ignoradas (o template carrega a tabela de escala).
- Datas ISO ``AAAA-MM-DD`` ou ``DD/MM/AAAA`` (4 dígitos de ano); outros
  formatos = linha inválida (fail-loud, nunca DD/MM/AA nem MM/DD).
- Exit codes: 0 = nada vencendo/sem avisos; 1 = algo vencendo OU aviso
  OU linha inválida (atenção do dono); 2 = registro ilegível (ausente,
  ilegível, ou nenhuma tabela reconhecível).
- ``--init`` copia o template do repo para ``--registro`` se (e só se)
  o arquivo ainda não existir; ``data/`` segue gitignored — o registro
  do dono NUNCA é versionado nem publicado.

Uso:
    python3 scripts/reply_tracking.py [--registro CAMINHO] [--today AAAA-MM-DD]
    python3 scripts/reply_tracking.py --init [--registro CAMINHO]

Zero dependências além da stdlib; zero rede; zero writes fora do --init.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------- constantes

STATUSES = ("SENT", "INTERVIEW", "OFFER", "REJECTED", "RESPONDED")
SIGNAL_STATUSES = ("INTERVIEW", "OFFER", "RESPONDED")

NUDGE_DAYS = 7  # +1 semana
PING_DAYS = 14  # +2 semanas
CLOSE_DAYS = 28  # +4 semanas
GUARD_DAYS = 30  # data-guard company-wide
GUARD_NOTICE_DAYS = 7  # janela p/ avisar "guard expirou" (empresa liberada)
FORESIGHT_DAYS = 3  # nudge vencendo em ≤3d aparece como "aguardando"

VERDICTS = ("APLICAR", "VALE", "OVERRIDE", "CONTRA")

DEFAULT_REGISTRO = Path("data/personal/registro_candidaturas.md")
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "registro_candidaturas.md"

CAND_HEADER = ("enviada", "empresa", "vaga", "id_fonte", "status",
               "resposta", "score_1_5", "nota")
TRIAGE_HEADER = ("empresa", "vaga", "id_fonte", "score_1_5", "verdict", "notas")

_RE_DDMMYYYY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


# ------------------------------------------------------------------- datas


def parse_date(raw: str) -> date | None:
    """ISO AAAA-MM-DD ou DD/MM/AAAA (ano com 4 dígitos). Nunca DD/MM/AA."""
    s = _clean_cell(raw)
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    m = _RE_DDMMYYYY.match(s)
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_score(raw: str) -> tuple[float | None, str | None]:
    """'4,5' → (4.5, None); vazio → (None, None); lixo/fora de 1–5 → (None, motivo)."""
    s = _clean_cell(raw).replace(",", ".")
    if not s:
        return None, None
    try:
        v = float(s)
    except ValueError:
        return None, f"score_1_5 ilegível: '{_clean_cell(raw)}'"
    if not 1.0 <= v <= 5.0:
        return None, f"score_1_5 fora da escala 1–5: {v}"
    return round(v, 1), None


def verdict_of(score: float) -> str:
    """Escala career-ops (aritmética sobre o score do DONO — nunca LLM)."""
    if score >= 4.5:
        return "APLICAR"
    if score >= 4.0:
        return "VALE"
    if score >= 3.5:
        return "OVERRIDE"
    return "CONTRA"


# ------------------------------------------------------------------ parser


@dataclass
class TriageRow:
    empresa: str
    vaga: str
    id_fonte: str
    score: float | None
    verdict: str | None  # o que o dono escreveu (None = em branco)
    notas: str
    line_no: int


@dataclass
class Candidatura:
    enviada: date
    empresa: str
    vaga: str
    id_fonte: str
    status: str  # canônico upper
    resposta: date | None
    score: float | None
    nota: str
    line_no: int


@dataclass
class Registro:
    triage: list[TriageRow] = field(default_factory=list)
    candidaturas: list[Candidatura] = field(default_factory=list)
    invalid: list[tuple[int, str]] = field(default_factory=list)  # (linha, motivo)
    warnings: list[tuple[int, str]] = field(default_factory=list)


def _clean_cell(raw: str) -> str:
    s = raw.strip()
    if s.startswith("**") and s.endswith("**") and len(s) >= 4:
        s = s[2:-2].strip()
    return s


def _norm_empresa(raw: str) -> str:
    return " ".join(_clean_cell(raw).casefold().split())


def _split_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(cells: list[str]) -> bool:
    filled = [c for c in cells if c != ""]
    return bool(filled) and all(re.fullmatch(r":?-{3,}:?", c) for c in filled)


def _is_blank_row(cells: list[str]) -> bool:
    return all(not _clean_cell(c) for c in cells)


def _header_key(cells: list[str]) -> tuple[str, ...]:
    return tuple(" ".join(_clean_cell(c).casefold().split()) for c in cells)


def _tables(lines: list[str]) -> list[tuple[int, list[tuple[int, list[str]]]]]:
    """Tabelas de pipe: [(linha do cabeçalho, [(linha, células), ...])]."""
    out: list[tuple[int, list[tuple[int, list[str]]]]] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            start = i
            rows: list[tuple[int, list[str]]] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append((i + 1, _split_cells(lines[i])))
                i += 1
            out.append((start + 1, rows))
        else:
            i += 1
    return out


def parse_registro(text: str, today: date) -> Registro:
    """Classifica as tabelas pelo CABEÇALHO (ordem/seção não importa)."""
    reg = Registro()
    lines = text.splitlines()
    saw_pipe = any(ln.lstrip().startswith("|") for ln in lines)
    saw_cand_table = False
    saw_triage_table = False

    for _header_line, rows in _tables(lines):
        if not rows:
            continue
        header_cells = rows[0][1]
        if _is_separator(header_cells) or _is_blank_row(header_cells):
            continue
        key = _header_key(header_cells)
        if key == CAND_HEADER:
            saw_cand_table = True
            for line_no, cells in rows[1:]:
                _parse_cand_row(reg, cells, line_no, today)
        elif key == TRIAGE_HEADER:
            saw_triage_table = True
            for line_no, cells in rows[1:]:
                _parse_triage_row(reg, cells, line_no)
        # outro cabeçalho (ex.: escala de veredito do template) = ignorado

    if not saw_pipe:
        reg.invalid.append((0, "registro sem nenhuma tabela de pipe"))
    elif saw_triage_table and not saw_cand_table:
        reg.warnings.append(
            (0, "nenhuma tabela de CANDIDATURAS reconhecida (cabeçalho "
                "'enviada | empresa | vaga | id_fonte | status | resposta | "
                "score_1_5 | nota') — cadências não computadas"))
    elif not saw_cand_table and not saw_triage_table:
        reg.invalid.append(
            (0, "nenhuma tabela reconhecível (candidaturas nem triagem) — "
                "confira os cabeçalhos contra templates/registro_candidaturas.md"))
    return reg


def _parse_cand_row(reg: Registro, cells: list[str], line_no: int,
                    today: date) -> None:
    if _is_separator(cells) or _is_blank_row(cells):
        return
    if len(cells) > len(CAND_HEADER):
        reg.invalid.append(
            (line_no, f"{len(cells)} colunas (esperado {len(CAND_HEADER)})"))
        return
    cells = cells + [""] * (len(CAND_HEADER) - len(cells))  # pad células faltando

    enviada = parse_date(cells[0])
    if enviada is None:
        reg.invalid.append(
            (line_no, f"data de envio ausente/inválida: '{_clean_cell(cells[0])}'"))
        return
    empresa = _clean_cell(cells[1])
    if not empresa:
        reg.invalid.append((line_no, "empresa vazia"))
        return
    vaga = _clean_cell(cells[2])
    if not vaga:
        reg.invalid.append((line_no, "vaga vazia"))
        return
    status = _clean_cell(cells[4]).upper()
    if status not in STATUSES:
        reg.invalid.append(
            (line_no, f"status desconhecido '{_clean_cell(cells[4])}' "
                      "(use Sent|Interview|Offer|Rejected|Responded)"))
        return
    resposta_raw = _clean_cell(cells[5])
    resposta = parse_date(resposta_raw)
    if resposta_raw and resposta is None:
        reg.invalid.append((line_no, f"data de resposta inválida: '{resposta_raw}'"))
        return
    score, err = parse_score(cells[6])
    if err:
        reg.warnings.append((line_no, err))
    if enviada > today:
        reg.warnings.append((line_no, f"data de envio no futuro ({enviada.isoformat()})"))

    reg.candidaturas.append(Candidatura(
        enviada=enviada, empresa=empresa, vaga=vaga,
        id_fonte=_clean_cell(cells[3]), status=status, resposta=resposta,
        score=score, nota=_clean_cell(cells[7]), line_no=line_no))


def _parse_triage_row(reg: Registro, cells: list[str], line_no: int) -> None:
    if _is_separator(cells) or _is_blank_row(cells):
        return
    if len(cells) > len(TRIAGE_HEADER):
        reg.invalid.append(
            (line_no, f"{len(cells)} colunas (esperado {len(TRIAGE_HEADER)})"))
        return
    cells = cells + [""] * (len(TRIAGE_HEADER) - len(cells))

    empresa = _clean_cell(cells[0])
    if not empresa:
        reg.invalid.append((line_no, "empresa vazia (triagem)"))
        return
    vaga = _clean_cell(cells[1])
    if not vaga:
        reg.invalid.append((line_no, "vaga vazia (triagem)"))
        return
    score, err = parse_score(cells[3])
    if err:
        reg.warnings.append((line_no, err))
    verdict_raw = _clean_cell(cells[4])
    verdict: str | None = None
    if verdict_raw:
        verdict = verdict_raw.upper()
        if verdict not in VERDICTS:
            reg.warnings.append(
                (line_no, f"veredito desconhecido: '{verdict_raw}' "
                          f"(use {'|'.join(VERDICTS)})"))
            verdict = None
        elif score is not None and verdict != verdict_of(score):
            reg.warnings.append(
                (line_no, f"veredito '{verdict}' ≠ derivado "
                          f"'{verdict_of(score)}' (score {score})"))

    reg.triage.append(TriageRow(
        empresa=empresa, vaga=vaga, id_fonte=_clean_cell(cells[2]),
        score=score, verdict=verdict, notas=_clean_cell(cells[5]),
        line_no=line_no))


# ------------------------------------------------------------------- guard


@dataclass
class Guard:
    empresa_norm: str
    display: str
    reject_date: date
    active: bool
    until: date
    days_left: int  # ativo: dias restantes; expirado: dias desde a liberação


def rejections_of(cands: list[Candidatura]) -> dict[str, list[tuple[date, str]]]:
    """Rejeições company-wide: {empresa_norm: [(data, display), ...]}."""
    out: dict[str, list[tuple[date, str]]] = {}
    for c in cands:
        if c.status != "REJECTED":
            continue
        r = c.resposta or c.enviada
        out.setdefault(_norm_empresa(c.empresa), []).append((r, c.empresa))
    return out


def guards_of(rejections: dict[str, list[tuple[date, str]]],
              today: date) -> list[Guard]:
    """Estado do guard por empresa (rejeição MAIS RECENTE governa)."""
    guards: list[Guard] = []
    for norm, rejs in rejections.items():
        r, display = max(rejs)
        days = (today - r).days
        active = 0 <= days < GUARD_DAYS
        until = r + timedelta(days=GUARD_DAYS)
        guards.append(Guard(
            empresa_norm=norm, display=display, reject_date=r, active=active,
            until=until,
            days_left=(GUARD_DAYS - days) if active else (days - GUARD_DAYS)))
    return sorted(guards, key=lambda g: (not g.active, g.empresa_norm))


def guard_at_send(rejections: dict[str, list[tuple[date, str]]],
                  empresa_norm: str, enviada: date) -> Guard | None:
    """Guard vigente NA data de envio (rejeições mais antigas contam)."""
    rejs = [r for r, _d in rejections.get(empresa_norm, []) if r <= enviada]
    if not rejs:
        return None
    r = max(rejs)
    if (enviada - r).days >= GUARD_DAYS:
        return None
    display = next(d for rr, d in rejections[empresa_norm] if rr == r)
    return Guard(empresa_norm=empresa_norm, display=display, reject_date=r,
                 active=True, until=r + timedelta(days=GUARD_DAYS),
                 days_left=GUARD_DAYS - (enviada - r).days)


# ----------------------------------------------------------------- cadência


def cadence_of(enviada: date, today: date) -> tuple[str, int]:
    """('aguardando'|'nudge'|'ping'|'encerra', dias desde o envio)."""
    age = (today - enviada).days
    if age >= CLOSE_DAYS:
        return "encerra", age
    if age >= PING_DAYS:
        return "ping", age
    if age >= NUDGE_DAYS:
        return "nudge", age
    return "aguardando", age


# ------------------------------------------------------------------ relatório


def _cand_line(c: Candidatura, age: int) -> str:
    bits = f"  - {c.empresa} | {c.vaga} | enviada {c.enviada.isoformat()} ({age}d)"
    if c.id_fonte:
        bits += f" | {c.id_fonte}"
    return bits


def build_report(reg: Registro, today: date) -> tuple[str, bool]:
    """Relatório noise-first. Retorna (texto, atenção→exit 1)."""
    lines: list[str] = []
    cands = reg.candidaturas
    sent = [c for c in cands if c.status == "SENT"]
    signals = [c for c in cands if c.status in SIGNAL_STATUSES]
    rejected = [c for c in cands if c.status == "REJECTED"]
    rejections = rejections_of(cands)
    guards = guards_of(rejections, today)
    attention = False

    lines.append(f"⏰ CADÊNCIA — hoje {today.isoformat()} · "
                 f"{len(cands)} candidaturas · {len(reg.triage)} triagem")

    # cadências vencendo (noise-first: encerra acumulado primeiro)
    due: dict[str, list[tuple[Candidatura, int]]] = {"encerra": [], "ping": [], "nudge": []}
    waiting: list[tuple[Candidatura, int]] = []
    for c in sent:
        stage, age = cadence_of(c.enviada, today)
        if stage == "aguardando":
            waiting.append((c, age))
        else:
            due[stage].append((c, age))

    icons = {"encerra": "⏹ ENCERRA (≥28d sem resposta)", "ping": "🏓 PING (≥14d)",
             "nudge": "👋 NUDGE (≥7d)"}
    for stage in ("encerra", "ping", "nudge"):
        if due[stage]:
            attention = True
            lines.append(f"{icons[stage]}: {len(due[stage])}")
            lines.extend(_cand_line(c, age) for c, age in due[stage])

    foresight = [(c, age) for c, age in waiting
                 if NUDGE_DAYS - age <= FORESIGHT_DAYS]
    if foresight:
        lines.append(f"⏳ AGUARDANDO (nudge em ≤{FORESIGHT_DAYS}d): {len(foresight)}")
        lines.extend(_cand_line(c, age) for c, age in foresight)

    # guard 30d company-wide (informa; vence — nunca bloqueio eterno)
    active_guards = [g for g in guards if g.active]
    expired_recent = [g for g in guards
                       if not g.active and 0 <= g.days_left <= GUARD_NOTICE_DAYS]
    if guards:
        header = f"🛡 GUARD 30D company-wide: {len(active_guards)} ativo(s)"
        if expired_recent:
            header += f" · {len(expired_recent)} recém-liberada(s)"
        lines.append(header)
        for g in active_guards:
            lines.append(f"  - {g.display}: rejeição {g.reject_date.isoformat()} · "
                         f"guard ATIVO até {g.until.isoformat()} (faltam {g.days_left}d)")
        for g in expired_recent:
            lines.append(f"  - {g.display}: rejeição {g.reject_date.isoformat()} · "
                         f"guard EXPIROU {g.until.isoformat()} → empresa liberada "
                         f"(rejeição antiga ≠ bloqueio eterno)")

    # candidaturas enviadas sob guard (o nudge delas provavelmente é ruído)
    under_guard = []
    for c in sent:
        g = guard_at_send(rejections, _norm_empresa(c.empresa), c.enviada)
        if g:
            under_guard.append((c, g))
    if under_guard:
        attention = True
        lines.append(f"⚠ ENVIADAS SOB GUARD: {len(under_guard)}")
        for c, g in under_guard:
            lines.append(f"  - {c.empresa} | {c.vaga} | enviada "
                         f"{c.enviada.isoformat()} · guard {g.display} "
                         f"(rejeição {g.reject_date.isoformat()})")

    # triagem em empresa sob guard ATIVO (aviso na hora da decisão)
    triage_guard = [t for t in reg.triage
                    if any(g.empresa_norm == _norm_empresa(t.empresa)
                           for g in active_guards)]
    if triage_guard:
        attention = True
        lines.append(f"🛡 TRIAGEM sob guard ativo: {len(triage_guard)}")
        for t in triage_guard:
            g = next(g for g in active_guards
                     if g.empresa_norm == _norm_empresa(t.empresa))
            lines.append(f"  - {t.empresa} | {t.vaga} — guard até "
                         f"{g.until.isoformat()} (rejeição "
                         f"{g.reject_date.isoformat()})")

    # sinais (sem cadência — conversa viva nunca é encerrada automaticamente)
    if signals:
        lines.append(f"✅ SINAIS (sem cadência): {len(signals)}")
        for c in signals:
            resp = (f"resposta {c.resposta.isoformat()}" if c.resposta
                    else "sem data de resposta")
            lines.append(f"  - {c.status.title()}: {c.empresa} | {c.vaga} | {resp}")

    # ruído: rejeições colapsadas por empresa (nunca uma linha por recusa)
    if rejected:
        per_emp: dict[str, int] = {}
        for c in rejected:
            per_emp[c.empresa] = per_emp.get(c.empresa, 0) + 1
        summary = ", ".join(f"{e} ×{n}" for e, n in
                            sorted(per_emp.items(), key=lambda kv: (-kv[1], kv[0])))
        lines.append(f"🔇 RUÍDO: {len(rejected)} rejeições em "
                     f"{len(per_emp)} empresas ({summary})")

    # triagem: contagens + vereditos derivados (o dono copia p/ o registro)
    if reg.triage:
        unscored = [t for t in reg.triage if t.score is None]
        lines.append(f"📋 TRIAGEM: {len(reg.triage)} linhas · "
                     f"{len(unscored)} sem score_1_5")
        for t in reg.triage:
            if t.score is not None:
                lines.append(f"  - {t.empresa} | {t.vaga}: {t.score} → "
                             f"{verdict_of(t.score)}")

    if not attention and not reg.warnings and not reg.invalid:
        extra = ""
        if waiting:
            nxt = min(c.enviada for c, _ in waiting) + timedelta(days=NUDGE_DAYS)
            extra = f" · próximo nudge {nxt.isoformat()}"
        lines.append(f"🙂 Nada vencendo hoje · {len(waiting)} aguardando{extra}")

    if reg.warnings:
        attention = True
        lines.append(f"❗ AVISOS: {len(reg.warnings)}")
        lines.extend(f"  - linha {ln}: {msg}" for ln, msg in reg.warnings)

    if reg.invalid:
        attention = True
        lines.append(f"🚫 LINHAS INVÁLIDAS: {len(reg.invalid)}")
        lines.extend(f"  - linha {ln}: {msg}" for ln, msg in reg.invalid)

    return "\n".join(lines), attention


# ---------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="reply_tracking.py",
        description="F98 — cadência de follow-up + guard 30d do REGISTRO "
                    "(somente-leitura; o dono decide).")
    ap.add_argument("--registro", type=Path, default=DEFAULT_REGISTRO,
                    help=f"caminho do registro (default: {DEFAULT_REGISTRO})")
    ap.add_argument("--today", type=date.fromisoformat, default=None,
                    help="data de referência AAAA-MM-DD (default: hoje)")
    ap.add_argument("--init", action="store_true",
                    help="cria o registro a partir do template (recusa "
                         "sobrescrever arquivo existente)")
    args = ap.parse_args(argv)

    if args.init:
        target = args.registro
        if target.is_file():
            print(f"✗ {target} já existe — --init nunca sobrescreve",
                  file=sys.stderr)
            return 2
        if not TEMPLATE.is_file():
            print(f"✗ template ausente: {TEMPLATE}", file=sys.stderr)
            return 2
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TEMPLATE, target)
        print(f"template criado: {target}")
        return 0

    path = args.registro
    if not path.is_file():
        print(f"✗ registro não encontrado: {path} (crie com --init)",
              file=sys.stderr)
        return 2
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"✗ registro ilegível: {e}", file=sys.stderr)
        return 2

    today = args.today or date.today()
    reg = parse_registro(text, today)
    report, attention = build_report(reg, today)
    print(report)

    if reg.invalid and not reg.candidaturas and not reg.triage:
        return 2  # registro ilegível (nenhuma tabela reconhecível)
    return 1 if attention else 0


if __name__ == "__main__":
    raise SystemExit(main())
