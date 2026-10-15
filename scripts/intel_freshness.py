"""F44 — Frescor do intel de empresas: staleness report OFFLINE (padrão F28).

Relatório determinístico, offline (zero HTTP, zero LLM), stdout + exit-code,
sobre o intel curado ``company_intel/company_intelligence.json`` e o mapa
de qualidade ``config/employer_quality.json`` (F15). SÓ LÊ — nunca escreve
no intel (curadoria é humana; este módulo é o GATILHO, não o fetch).

DEFINIÇÃO DE FRESCOR DA ENTRY (decisão F44 — documentada, justificada):

    frescor(entry) = idade em dias do campo ``checked`` DE NÍVEL DE ENTRY,
    medido contra a data de referência (default: hoje).

Justificativa (schema real medido em 2026-10-15 sobre as 88 entries):

- ``checked`` (entry-level): presente em 88/88 — única marca de tempo com
  cobertura TOTAL. Semântica: data da última verificação das fontes da
  entry (``sources[]`` carrega a mesma data por fonte; o comentário do
  arquivo manda "nunca editar sem atualizar sources/checked").
- ``sources[].checked`` (129 ocorrências): por FONTE, não por campo;
  redundante do entry-level quando coexistem (mesma data nas amostras
  medidas), mas sem garantia de alinhamento — usar max() aqui misturaria
  populações.
- ``sources_for.visa_policy[].checked`` (75/88): só existe quando há fonte
  dedicada de visa_policy — frescor de ENTRY por max() deixaria 13 entries
  "sem idade"; e a idade do visa_policy isolado é outro conceito (o
  card sugere ambas; entry-level é a que cobre o arquivo INTEIRO).
- ``turnover.checked`` (1/88): campo raro; ignorado.

O threshold de staleness é PARAMETRIZÁVEL (default 90 dias — convenção
do card F44); o relatório lista empresas ACIMA dele, mais velhas primeiro.

Gatilho (b) — alvos da watchlist SEM intel de Kununu: cruzamento pelo
VALOR INTEIRO normalizado com o MESMO ``opportunity_intel._norm`` do mapa
F15 (casefold + colapso de acentos; NUNCA substring) entre
``config/company_watchlist.json`` (nomes de dataset — "BoschGroup", não
"Bosch") e as empresas com ``kununu_score`` ausente/null do mapa F15
(``kununu_score: null`` = perfil "unavailable" ENTRA no mapa sem score —
ver employer_quality.py). Empresa da watchlist ausente do mapa = sem
Kununu (o caso dominante medido em produção: 27/67 alvos em 2026-10-15).

Determinismo: mesma entrada + mesma ``--ref-date`` = mesmo relatório
byte a byte (nenhuma dependência de rede, relógio-only via default de
hoje — teste trava idempotência com ``--ref-date`` fixo).

Uso::

    python scripts/intel_freshness.py \
        --intel company_intel/company_intelligence.json \
        --watchlist config/company_watchlist.json \
        --employer-quality config/employer_quality.json \
        [--stale-days 90] [--top 5] [--ref-date 2026-10-15]

    python scripts/intel_freshness.py --json   # saída estruturada (1 obj)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

# MESMO normalizador do mapa F15/employer_quality (produção colapsa
# acentos: "München" == "Munchen"; ver opportunity_intel._norm). O
# cruzamento "watchlist tem score no mapa" usa a MESMA chave do mapa —
# divergir aqui criaria falsos "sem Kununu" para nomes com acento.
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from internship_finder.opportunity_intel import _norm  # noqa: E402

DEFAULT_STALE_DAYS = 90
DEFAULT_TOP = 5
INTEL_DEFAULT = "company_intel/company_intelligence.json"
WATCHLIST_DEFAULT = "config/company_watchlist.json"
QUALITY_DEFAULT = "config/employer_quality.json"


def today() -> date:
    """Data de referência default (hoje, TZ local) — hook de teste.

    Padrão ``now_ref`` das fases F29/F38: o chamador de produção usa
    o default; testes determinísticos substituem a função (monkeypatch
    de função Python, nunca do ``datetime`` C-type imutável).
    """
    return datetime.now().astimezone().date()


def _parse_day(value: str) -> date:
    """Data 'YYYY-MM-DD' -> date; nunca lança fora do contrato do CLI."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def _entry_checked(entry: dict) -> str | None:
    """Data entry-level ``checked`` (str) ou None — defensivo."""
    value = entry.get("checked")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_intel_companies(path: str | Path) -> list[dict]:
    """Lê o intel curado e devolve a lista de entries (defensivo).

    Formato real (medido): ``{"_comment": ..., "companies": [entry, ...]}``.
    Arquivo ausente/corrompido/sem lista -> ``[]`` (o chamador decide se é
    erro de CLI; o digest trata como "sem gatilhos").
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001 — leitura defensiva, nunca derruba
        return []
    if isinstance(data, dict):
        companies = data.get("companies")
        if isinstance(companies, list):
            return [c for c in companies if isinstance(c, dict)]
    if isinstance(data, list):  # tolerante a lista crua
        return [c for c in data if isinstance(c, dict)]
    return []


def load_watchlist_companies(path: str | Path) -> list[str]:
    """Lê a watchlist F13 (strings exatas de dataset; defensivo)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        companies = data.get("companies")
        if isinstance(companies, list):
            return [str(c) for c in companies if str(c or "").strip()]
    if isinstance(data, list):
        return [str(c) for c in data if str(c or "").strip()]
    return []


def load_employer_quality_companies(path: str | Path) -> list[dict]:
    """Lê o mapa F15 e devolve as entries de empresas (defensivo)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        companies = data.get("companies")
        if isinstance(companies, list):
            return [c for c in companies if isinstance(c, dict)]
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    return []


def stale_entries(
    companies: list[dict], *,
    ref_date: date,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> list[dict]:
    """Empresas com ``checked`` mais velho que ``stale_days`` (mais velhas primeiro).

    Pura e determinística: a idade é truncada em dias; empates de idade
    quebram por nome (casefold) — ordem estável byte a byte.
    """
    stale: list[tuple[int, str, dict]] = []
    for entry in companies:
        checked = _entry_checked(entry)
        if not checked:
            continue
        try:
            checked_date = _parse_day(checked)
        except ValueError:
            continue
        age = (ref_date - checked_date).days
        if age > stale_days:
            stale.append((age, _norm(str(entry.get("company") or "")), entry))
    stale.sort(key=lambda t: (-t[0], t[1]))
    return [
        {"company": entry.get("company") or "—", "checked": _entry_checked(entry),
         "age_days": age}
        for age, _, entry in stale
    ]


def _has_kununu_score(entry: dict) -> bool:
    """``True`` quando a entry do mapa F15 carrega ``kununu_score`` válido.

    ``kununu_score: null`` (perfil "unavailable") e ausência da empresa no
    mapa = SEM score (o badge não renderiza — ver employer_quality.py).
    """
    score = entry.get("kununu_score")
    if score is None:
        return False
    try:
        return float(score) > 0.0
    except (TypeError, ValueError):
        return False


def no_kununu_targets(
    watchlist: list[str], quality_companies: list[dict], *,
    top: int = DEFAULT_TOP,
) -> list[str]:
    """Empresas-alvo da watchlist SEM intel de Kununu (score do mapa F15).

    Match pelo VALOR INTEIRO normalizado (``opportunity_intel._norm`` =
    casefold + colapso de acentos — a MESMA chave do mapa F15, nunca
    substring; a watchlist carrega nomes de dataset — mesmo contrato do
    radar F13). Ordem: alfabética por nome normalizado — estável e
    determinística; a seção é ALERTA de curadoria, não ranking (o radar
    F13 também "não reordena nada, só alerta"). ``top`` corta a lista.
    """
    with_score = {_norm(str(c.get("company") or ""))
                  for c in quality_companies if _has_kununu_score(c)}
    targets = sorted({w for w in watchlist if _norm(str(w)) not in with_score},
                     key=_norm)
    if top and top > 0:
        targets = targets[:top]
    return targets


def freshness_summary(
    companies: list[dict], *,
    ref_date: date,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> dict:
    """Contagens-resumo do frescor do intel (para o relatório e o digest).

    Retorna contagens ABSOLUTAS (não truncadas por ``top``): o header do
    digest carrega a contagem total (padrão F13: header + "ver página").
    """
    total = len(companies)
    with_date = 0
    stale = 0
    oldest: tuple[int, str, str] | None = None  # (age, name_norm, name_raw)
    for entry in companies:
        checked = _entry_checked(entry)
        if not checked:
            continue
        try:
            age = (ref_date - _parse_day(checked)).days
        except ValueError:
            continue
        with_date += 1
        if age > stale_days:
            stale += 1
        name_raw = str(entry.get("company") or "—")
        name_norm = _norm(str(entry.get("company") or ""))
        if (oldest is None or age > oldest[0]
                or (age == oldest[0] and name_norm < oldest[1])):
            oldest = (age, name_norm, name_raw)
    return {
        "entries_total": total,
        "entries_with_checked": with_date,
        "entries_stale": stale,
        "stale_days": stale_days,
        "oldest_age_days": oldest[0] if oldest else None,
        "oldest_company": oldest[2] if oldest else None,
    }


def build_report(
    companies: list[dict],
    watchlist: list[str],
    quality_companies: list[dict], *,
    ref_date: date,
    stale_days: int = DEFAULT_STALE_DAYS,
    top: int = DEFAULT_TOP,
) -> str:
    """Relatório completo em markdown (stdout; determinístico)."""
    stale = stale_entries(companies, ref_date=ref_date, stale_days=stale_days)
    targets = no_kununu_targets(watchlist, quality_companies, top=0)
    summary = freshness_summary(companies, ref_date=ref_date,
                                stale_days=stale_days)

    lines: list[str] = []
    lines.append("# F44 — Frescor do intel de empresas (staleness report)")
    lines.append("")
    lines.append(f"Referência: {ref_date.isoformat()} · threshold: "
                 f">{stale_days} dias sem verificação")
    lines.append("")
    lines.append("## Resumo")
    lines.append("")
    lines.append(f"- Entries no intel: **{summary['entries_total']}** "
                 f"({summary['entries_with_checked']} com data de checked)")
    lines.append(f"- Empresas com checked > {stale_days}d: **{summary['entries_stale']}**")
    if summary["oldest_company"] is not None:
        lines.append(f"- Entry mais velha: **{summary['oldest_company']}** "
                     f"({summary['oldest_age_days']}d)")
    lines.append(f"- Alvos da watchlist SEM intel de Kununu: **{len(targets)}**")
    lines.append("")
    lines.append(f"## (a) Empresas com checked > {stale_days} dias (mais velhas primeiro)")
    lines.append("")
    if stale:
        for s in stale:
            lines.append(f"- {s['company']} — checked {s['checked']} ({s['age_days']}d)")
    else:
        lines.append("— nenhuma (intel fresco no threshold atual)")
    lines.append("")
    lines.append("## (b) Alvos da watchlist SEM intel de Kununu")
    lines.append("")
    if targets:
        for t in targets:
            lines.append(f"- {t}")
    else:
        lines.append("— nenhum (todos os alvos têm score no mapa F15)")
    if targets:
        lines.append("")
        lines.append("## Ritual de curadoria (humano, ~30s/empresa)")
        lines.append("")
        lines.append("1. Escolher empresas da lista (b) — priorizar as com vagas no dia.")
        lines.append("2. CDP attach: abrir o perfil Kununu da empresa e conferir o score.")
        lines.append("3. Curadoria manual: atualizar `kununu_score`/`checked` no mapa F15 "
                     "(`config/employer_quality.json`) — sources/checked sempre juntos.")
        lines.append("4. Commitar o mapa atualizado (o intel só é editado com "
                     "sources/checked; o mapa F15 é o lar do dado Kununu).")
    lines.append("")
    lines.append("<!-- gerado por scripts/intel_freshness.py — determinístico, offline -->")
    return "\n".join(lines) + "\n"


def triggers(
    companies: list[dict],
    watchlist: list[str],
    quality_companies: list[dict], *,
    ref_date: date,
    stale_days: int = DEFAULT_STALE_DAYS,
    top: int = DEFAULT_TOP,
) -> dict:
    """GATILHOS compactos para a seção ⏰ do digest (contrato do digest).

    Sem gatilhos: ``stale_count == 0 and no_kununu_count == 0`` — a seção
    é AUSENTE (digest byte a byte o de antes; A/B do card). As contagens
    são absolutas (o header do digest carrega o total; ``top`` corta só a
    LISTA de exemplos exibida).
    """
    stale = stale_entries(companies, ref_date=ref_date, stale_days=stale_days)
    no_kununu = no_kununu_targets(watchlist, quality_companies, top=0)
    return {
        "stale_count": len(stale),
        "stale_top": [s["company"] for s in stale[:top]],
        "stale_top_checked": [s["checked"] for s in stale[:top]],
        "stale_top_ages": [s["age_days"] for s in stale[:top]],
        "no_kununu_count": len(no_kununu),
        "no_kununu_top": no_kununu[:top],
        "stale_days": stale_days,
    }


def _load_all(intel_path: str | Path, watchlist_path: str | Path,
              quality_path: str | Path) -> tuple[list[dict], list[str], list[dict]]:
    return (load_intel_companies(intel_path),
            load_watchlist_companies(watchlist_path),
            load_employer_quality_companies(quality_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F44 — staleness report do intel de empresas "
                    "(offline, determinístico; só lê).")
    parser.add_argument("--intel", default=INTEL_DEFAULT,
                        help=f"intel curado (default: {INTEL_DEFAULT})")
    parser.add_argument("--watchlist", default=WATCHLIST_DEFAULT,
                        help=f"watchlist F13 (default: {WATCHLIST_DEFAULT})")
    parser.add_argument("--employer-quality", default=QUALITY_DEFAULT,
                        help=f"mapa F15 de Kununu/GPTW (default: {QUALITY_DEFAULT})")
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS,
                        help=f"threshold de staleness em dias "
                             f"(default: {DEFAULT_STALE_DAYS})")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP,
                        help=f"exemplos listados por gatilho (default: {DEFAULT_TOP})")
    parser.add_argument("--ref-date", default=None,
                        help="data de referência YYYY-MM-DD (default: hoje)")
    parser.add_argument("--json", action="store_true",
                        help="saída estruturada (1 objeto JSON) em vez de markdown")
    args = parser.parse_args(argv)

    ref_date = (_parse_day(args.ref_date) if args.ref_date
                else today())
    companies, watchlist, quality = _load_all(
        args.intel, args.watchlist, args.employer_quality)

    if args.json:
        payload = {
            "ref_date": ref_date.isoformat(),
            "summary": freshness_summary(companies, ref_date=ref_date,
                                        stale_days=args.stale_days),
            "triggers": triggers(companies, watchlist, quality,
                                 ref_date=ref_date,
                                 stale_days=args.stale_days, top=args.top),
            "stale_entries": stale_entries(companies, ref_date=ref_date,
                                           stale_days=args.stale_days),
            "no_kununu_targets": no_kununu_targets(watchlist, quality, top=0),
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
        return 0

    report = build_report(companies, watchlist, quality, ref_date=ref_date,
                          stale_days=args.stale_days, top=args.top)
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
