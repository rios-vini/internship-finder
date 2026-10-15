"""Testes da Fase F44 — frescor do intel de empresas (100% offline).

F44 em uma linha: "automatize o gatilho, humanize o fetch" — o relatório
offline (``scripts/intel_freshness.py``) aponta o que está VELHO
(``checked`` > 90d) e que ALVO da watchlist está SEM intel de Kununu; a
seção ⏰ do digest carrega esses gatilhos; o HUMANO faz o fetch (CDP
attach Kununu ~30s/empresa, reverificar sources/checked).

Contratos testados:

- M1/M2: módulo PURO — ``stale_entries`` (idade da entry vs ref-date,
  mais velhas primeiro; empate por nome casefold estável) e
  ``no_kununu_targets`` (watchlist sem score no mapa F15; match EXATO
  casefold+acentos via opportunity_intel._norm — MESMA chave do mapa;
  ordem alfabética determinística, contagem absoluta independente do
  ``top``).
- M3: ``triggers`` — contagens ABSOLUTAS (não truncadas por ``top``;
  o header do digest carrega o total) + ``freshness_summary``.
- M4: loaders defensivos — arquivo ausente/corrompido -> [] (seção
  ausente, nunca erro).
- M5: idempotência/determinismo — mesmo input + mesmo ref-date =
  mesmo relatório byte a byte (print duas vezes, sha256 igual).
- D1: ``intel_lines`` — header ÚNICO carrega as contagens VIVAS
  (parte zerada não aparece); exemplos cap 5 + "(+N outras)"; rodapé
  de ritual só com o gatilho vivo.
- D2: contrato prefixo == header emitido (padrão test_f61/test_f36_1:
  o extrator reconhece pelo PREFIXO EXATO, sufixo pode evoluir).
- D3: ``digest_sections`` — com ``intel_freshness_paths`` + gatilhos:
  seção ⏰ presente ANTES do 🔗 (depois da 🎯; personal_sections F8
  entram depois dela, antes do link); SEM o parâmetro = digest byte a
  byte igual ao de antes (A/B do card, regressão zero — mesmo current/
  previous, sha256).
- D4: A/B SEM gatilhos (intel todo fresco + todos os alvos com score):
  MESMO com ``intel_freshness_paths`` apontando os arquivos, seção
  AUSENTE — digest byte a byte o de antes (o parâmetro sozinho não
  muda nada; só o GATILHO muda).
- C1: compactador — digest >4096 com seção ⏰ Intel presente: header
  com contagens SOBREVIVE (corpo cede espaço), ordem de exibição = ordem
  do digest (⏰ Intel imediatamente ANTES da ⏰ Follow-up pessoal),
  ⚡/🔗 intactos (padrão F36.1: nunca dropada inteira).
- C2: digest estourado SEM seção ⏰ Intel -> nada de header fantasma e
  nenhum bloco em branco duplicado (guard dos níveis).

Fixtures: entries VERBATIM do intel real (campos mínimos: company/
aliases/checked/visa_policy — BMW AG e BASF SE, checked 2026-09-20
medido ao vivo; a data é REAL, o que torna o fixture >90d no ref-date
2027-01-01 sem data inventada) + string VERBATIM da watchlist real
(Vanderlande — alvo medido SEM score no mapa F15) + entries VERBATIM
do mapa F15 (BMW AG 4.0; Deloitte GmbH... não: mapa tem "Deloitte GmbH
Wirtschaftsprüfungsgesellschaft" — o caso real de match EXATO: watchlist
"Deloitte GmbH" sem score porque o nome do mapa é outro; o mesmo
"Fraunhofer-Gesellschaft e.V. Zentrale München" da watchlist NÃO casa
com "Fraunhofer-Gesellschaft" do mapa por ser match EXATO — medido
ao vivo 15/10; ver relatório_fase_f44.md).

Uso:  .venv/bin/python scripts/test_f44.py   (ou bash scripts/test_f44.py)
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import intel_freshness as ifr  # noqa: E402
import ranking_digest as rg  # noqa: E402
import refresh_daily as rd  # noqa: E402

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
# Fixtures VERBATIM (entries reais, campos mínimos; datas REAIS do intel)
# ---------------------------------------------------------------------------

# Entry VERBATIM do intel real (campos mínimos; checked 2026-09-20 real,
# medido ao vivo 15/10 — idades 25d/103d são derivações aritméticas do
# ref-date, nunca datas inventadas).
INTEL_BMW = {
    "company": "BMW AG",
    "aliases": ["BMW"],
    "industry": "Automotivo (carros e motos)",
    "hq": "Munique (München), Alemanha",
    "website": "https://www.bmwgroup.com",
    "careers_url": "https://jobs.bmwgroup.com",
    "checked": "2026-09-20",
    "sources": [
        {"text": "Wikipedia — BMW (infobox e lead)",
         "url": "https://en.wikipedia.org/wiki/BMW",
         "quality": "secondary", "checked": "2026-09-20", "period": "2025"},
    ],
    "visa_policy": "not_verified",
    "country": "de",
}

# Entry VERBATIM (mesma coorte 2026-09-20 — o par BASF/BMW empata em
# idade e exercita o tie-break por nome casefold).
INTEL_BASF = {
    "company": "BASF SE",
    "aliases": ["BASF"],
    "industry": "Química",
    "hq": "Ludwigshafen, Alemanha",
    "website": "https://www.basf.com",
    "checked": "2026-09-20",
    "visa_policy": "unclear",
    "country": "de",
}

# Entry sintética no FORMATO real (checked AUSENTE em campo raro/legado —
# o loader defensivo já viu isso em arquivos curados: sem data = sem
# idade, NUNCA erro).
INTEL_NO_DATE = {
    "company": "Ohne Datum GmbH",
    "aliases": [],
    "checked": "",
    "visa_policy": "unclear",
    "country": "de",
}

INTEL_FIXTURE = [INTEL_BMW, INTEL_BASF, INTEL_NO_DATE]

# Watchlist VERBATIM: strings EXATAS do dataset (F13; "não use nomes
# bonitos"). "Vanderlande" é alvo medido SEM score no mapa F15 (15/10);
# "BoschGroup" é o string de dataset do mapa COM score (4.0).
WATCHLIST_FIXTURE = ["Vanderlande", "BoschGroup", "BMW AG"]

# Mapa F15 VERBATIM (entries reais, campos mínimos): BMW AG com score
# 4.0 (5866 reviews — número real do mapa), BoschGroup 4.0 (7368),
# Vanderlande AUSENTE do mapa (o caso dominante medido: 27/67 alvos).
QUALITY_BMW = {"company": "BMW AG", "kununu_score": 4.0,
               "kununu_reviews": 5866, "gptw_award": None,
               "source_type": "kununu-profile", "checked": "2026-10-08"}
QUALITY_BOSCH = {"company": "BoschGroup", "kununu_score": 4.0,
                 "kununu_reviews": 7368, "gptw_award": 2026,
                 "source_type": "kununu-profile", "checked": "2026-10-08"}
QUALITY_FIXTURE = [QUALITY_BMW, QUALITY_BOSCH]

REF = date(2026, 10, 15)   # data de hoje medida na sessão da fase
REF_LATE = date(2027, 1, 1)  # +78d: coorte 09-20 vira >90d (103d — aritmética)


def _job(i: int) -> dict:
    """Vaga sintética com os campos mínimos que o digest consome."""
    return {
        "id": f"fx|f44:{i}",
        "title": f"Praktikum Einkauf Supply Chain {i} (m/w/d)",
        "company": f"Firma {i} GmbH",
        "location": "Berlin, Deutschland",
        "country_iso": "de",
        "score": round(16.6 - i * 0.25, 2),
        "url": f"https://jobs.example.com/jobs/{i}",
        "description": "Beschaffung und supplier management. " * 8,
    }


def _apply_job(i: int) -> dict:
    """Vaga do Top 5 ⚡ (shape do format_top5: raw.apply_url)."""
    return {**_job(i), "raw": {"apply_url": f"https://apply.example.com/{i}"}}


def _summary(*, eligible: int = 50, total: int = 400, n_fail: int = 2) -> dict:
    return {
        "run_id": "2026-10-15T09:00:01+00:00",
        "total_collected": total,
        "eligible": eligible,
        "dedup_removed": 12,
        "ok": {"count": 40, "collected": 300},
        "empty": 2,
        "timeout": [("successfactors:tenant", "Lidl", "TIMEOUT")],
        "error": [("oracle:tenant", "SMA", "HTTP_500")]
        + [("s:t", f"E{i}", "HTTP_500") for i in range(n_fail - 1)],
        "skipped": 0,
        "not_found": 0,
        "source_names": {},
    }


def _base_alerts() -> list[dict]:
    return [
        {"type": "recurring_error", "source": "successfactors:tenant",
         "company": "Lidl", "runs_seq": 30},
        {"type": "recurring_error", "source": "oracle:tenant",
         "company": "SMA", "runs_seq": 17},
    ]


def _write(root: Path, name: str, payload) -> Path:
    path = root / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _digest_fixture_dir(prefix: str) -> tuple[Path, Path, Path, Path, Path]:
    """tmpdir com cur/prev + intel/watchlist/quality da fixture."""
    tmp = tempfile.mkdtemp(prefix=prefix)
    root = Path(tmp)
    cur = _write(root, "cur.json", [_job(i) for i in range(20)])
    prev = _write(root, "prev.json", [_job(i) for i in range(15, 20)])
    intel = _write(root, "intel.json", {"_comment": "fx", "companies": INTEL_FIXTURE})
    watch = _write(root, "watchlist.json", {"_comment": "fx",
                                            "companies": WATCHLIST_FIXTURE})
    quality = _write(root, "quality.json", {"_meta": {"phase": "F15"},
                                            "companies": QUALITY_FIXTURE})
    return root, cur, prev, intel, (watch, quality)


# ---------------------------------------------------------------------------
# M — módulo puro (intel_freshness)
# ---------------------------------------------------------------------------

def test_stale_entries() -> None:
    section("M1: stale_entries — idade da entry, mais velhas primeiro")
    stale = ifr.stale_entries(INTEL_FIXTURE, ref_date=REF_LATE,
                             stale_days=90)
    check("coorte 09-20 vira stale no ref 2027-01-01 (103d > 90d)",
          [s["company"] for s in stale] == ["BASF SE", "BMW AG"],
          str([s["company"] for s in stale]))
    check("idades aritméticas corretas (2026-09-20 → 2027-01-01 = 103d)",
          all(s["age_days"] == 103 for s in stale))
    check("empate de idade quebra por nome casefold (BASF < BMW)",
          stale[0]["company"] == "BASF SE")
    check("checked vazio não gera idade (NUNCA erro)",
          "Ohne Datum GmbH" not in [s["company"] for s in stale])
    fresh = ifr.stale_entries(INTEL_FIXTURE, ref_date=REF, stale_days=90)
    check("mesma fixture, ref hoje (25d) -> ZERO stale",
          fresh == [], str(fresh))
    check("threshold parametrizável: stale_days=20 pega a coorte hoje",
          [s["company"] for s in
           ifr.stale_entries(INTEL_FIXTURE, ref_date=REF, stale_days=20)]
          == ["BASF SE", "BMW AG"])


def test_no_kununu_targets() -> None:
    section("M2: no_kununu_targets — watchlist sem score no mapa (match exato)")
    targets = ifr.no_kununu_targets(WATCHLIST_FIXTURE, QUALITY_FIXTURE, top=0)
    check("alvo sem entrada no mapa = sem Kununu (caso dominante real)",
          "Vanderlande" in targets)
    check("alvo COM score (BMW AG 4.0 no mapa) não lista",
          "BMW AG" not in targets)
    check("match é EXATO: BoschGroup tem score, não é substring de nada",
          "BoschGroup" not in targets)
    check("lista completa (top=0): só Vanderlande", targets == ["Vanderlande"])
    cut = ifr.no_kununu_targets(WATCHLIST_FIXTURE, QUALITY_FIXTURE, top=5)
    check("top corta a LISTA sem mudar o critério", cut == ["Vanderlande"])
    check("watchlist vazia -> []", ifr.no_kununu_targets([], QUALITY_FIXTURE) == [])
    check("sem mapa -> todos os alvos",
          ifr.no_kununu_targets(["Vanderlande"], []) == ["Vanderlande"])
    # casefold/acentos: MESMA chave do mapa (opportunity_intel._norm)
    check("normalização casefold: 'vanderlande' == 'Vanderlande'",
          ifr.no_kununu_targets(["vanderlande"], QUALITY_FIXTURE) == ["vanderlande"])
    check("acentos colapsam como no mapa ('München AG' == 'Munchen AG')",
          ifr.no_kununu_targets(["München AG"],
                                [{"company": "Munchen AG", "kununu_score": 3.0}]) == [])
    # o caso REAL medido: watchlist carrega string de dataset; nome do
    # mapa DIFERENTE não casa (não inventa cobertura por substring)
    check("caso real: 'Deloitte GmbH' (watchlist) não casa "
          "'Deloitte GmbH Wirtschaftsprüfungsgesellschaft' (mapa)",
          ifr.no_kununu_targets(
              ["Deloitte GmbH"],
              [{"company": "Deloitte GmbH Wirtschaftsprüfungsgesellschaft",
                "kununu_score": 3.9}]) == ["Deloitte GmbH"])


def test_triggers_and_summary() -> None:
    section("M3: triggers — contagens ABSOLUTAS + summary")
    trig = ifr.triggers(INTEL_FIXTURE, WATCHLIST_FIXTURE, QUALITY_FIXTURE,
                        ref_date=REF_LATE, stale_days=90, top=1)
    check("stale_count absoluto (2, não truncado pelo top=1)",
          trig["stale_count"] == 2)
    check("no_kununu_count absoluto (1)", trig["no_kununu_count"] == 1)
    check("stale_top corta a lista de EXEMPLOS (top=1)",
          trig["stale_top"] == ["BASF SE"]
          and trig["stale_top_checked"] == ["2026-09-20"])
    check("no_kununu_top corta exemplos", trig["no_kununu_top"] == ["Vanderlande"])
    check("stale_days propagado (contrato do header)",
          trig["stale_days"] == 90)
    zero = ifr.triggers(INTEL_FIXTURE, WATCHLIST_FIXTURE, QUALITY_FIXTURE,
                        ref_date=REF, stale_days=90)
    check("sem stale E sem no_kununu impossível na fixture (1 alvo sem) — "
          "no_kununu é ref-date-INDEPENDENTE",
          zero["stale_count"] == 0 and zero["no_kununu_count"] == 1)
    none_trig = ifr.triggers(INTEL_FIXTURE, WATCHLIST_FIXTURE, [],
                             ref_date=REF, stale_days=90, top=5)
    check("sem mapa: TODOS os alvos da watchlist viram no_kununu (3)",
          none_trig["no_kununu_count"] == 3)
    summ = ifr.freshness_summary(INTEL_FIXTURE, ref_date=REF, stale_days=90)
    check("summary: 3 entries, 2 com data (vazio não conta)",
          summ["entries_total"] == 3 and summ["entries_with_checked"] == 2)
    check("summary: entry mais velha BASF/BMW 25d (empate, nome menor)",
          summ["oldest_company"] == "BASF SE" and summ["oldest_age_days"] == 25)


def test_loaders_defensive() -> None:
    section("M4: loaders defensivos — ausente/corrompido -> []")
    with tempfile.TemporaryDirectory(prefix="t_f44_load_") as tmp:
        root = Path(tmp)
        check("intel inexistente -> []",
              ifr.load_intel_companies(root / "nope.json") == [])
        bad = root / "bad.json"
        bad.write_text("{corrompido", encoding="utf-8")
        check("JSON quebrado -> [] (nunca erro)",
              ifr.load_intel_companies(bad) == []
              and ifr.load_watchlist_companies(bad) == []
              and ifr.load_employer_quality_companies(bad) == [])
        check("shape lista crua tolerado",
              ifr.load_intel_companies(
                  _write(root, "raw_list.json", INTEL_FIXTURE)) == INTEL_FIXTURE)
        check("sem 'companies' -> []",
              ifr.load_watchlist_companies(
                  _write(root, "empty_obj.json", {"x": 1})) == [])


def test_idempotence() -> None:
    section("M5: idempotência — mesmo input = mesmo relatório byte a byte")
    a = ifr.build_report(INTEL_FIXTURE, WATCHLIST_FIXTURE, QUALITY_FIXTURE,
                         ref_date=REF_LATE, stale_days=90, top=5)
    b = ifr.build_report(INTEL_FIXTURE, WATCHLIST_FIXTURE, QUALITY_FIXTURE,
                         ref_date=REF_LATE, stale_days=90, top=5)
    ha = hashlib.sha256(a.encode()).hexdigest()
    hb = hashlib.sha256(b.encode()).hexdigest()
    check("relatório determinístico (sha256 igual)", ha == hb, ha[:16])
    check("ref-date DIFERENTE muda o relatório (não é cache)",
          hashlib.sha256(
              ifr.build_report(INTEL_FIXTURE, WATCHLIST_FIXTURE,
                              QUALITY_FIXTURE, ref_date=REF,
                              stale_days=90, top=5).encode()
          ).hexdigest() != ha)


# ---------------------------------------------------------------------------
# D — seção do digest (intel_lines + digest_sections)
# ---------------------------------------------------------------------------

def test_intel_lines() -> None:
    section("D1: intel_lines — header com contagens vivas + cap + rodapé")
    trig = ifr.triggers(INTEL_FIXTURE, WATCHLIST_FIXTURE, QUALITY_FIXTURE,
                        ref_date=REF_LATE, stale_days=90, top=5)
    lines = rg.intel_lines(trig)
    check("seção presente com os dois gatilhos vivos",
          lines and lines[0].startswith(rg.INTEL_SECTION_PREFIX))
    check("header carrega as contagens (2 >90d; 1 alvo sem Kununu)",
          "2 >90d" in lines[0] and "1 alvo sem Kununu" in lines[0], lines[0])
    check("exemplos stale com data VERBATIM (checked 2026-09-20)",
          any("🕰" in ln and "2026-09-20" in ln for ln in lines))
    check("exemplo no_kununu com string VERBATIM da watchlist",
          any("⭐" in ln and "Vanderlande" in ln for ln in lines))
    check("rodapé de ritual menciona o fetch humano dos DOIS gatilhos",
          any("→ humano:" in ln and "CDP attach" in ln
              and "sources/checked" in ln for ln in lines))
    # só stale: rodapé NÃO fala de Kununu (orientação viva)
    only_stale = rg.intel_lines(
        {"stale_count": 2, "stale_top": ["BASF SE"],
         "stale_top_checked": ["2026-09-20"], "no_kununu_count": 0,
         "no_kununu_top": [], "stale_days": 90})
    check("só stale: header sem a parte de Kununu (zerada é ruído)",
          ">90d" in only_stale[0] and "Kununu" not in only_stale[0],
          only_stale[0])
    check("só stale: rodapé pede reverificar sources/checked, não CDP",
          any("→ humano:" in ln and "reverificar" in ln and "CDP" not in ln
              for ln in only_stale))
    # só no_kununu: header sem a parte de staleness
    only_kununu = rg.intel_lines(
        {"stale_count": 0, "stale_top": [], "stale_top_checked": [],
         "no_kununu_count": 3, "no_kununu_top": ["Vanderlande"],
         "stale_days": 90})
    check("só no_kununu: header sem a parte >Nd (zerada é ruído)",
          "Kununu" in only_kununu[0] and ">90d" not in only_kununu[0])
    # zero gatilhos -> seção AUSENTE
    check("zero gatilhos -> [] (seção ausente, sem linha vazia)",
          rg.intel_lines({"stale_count": 0, "stale_top": [],
                          "stale_top_checked": [], "no_kununu_count": 0,
                          "no_kununu_top": [], "stale_days": 90}) == [])
    check("triggers None -> []", rg.intel_lines(None) == [])
    # cap 5 + overflow relativo aos exemplos exibidos
    big = ifr.triggers(
        INTEL_FIXTURE * 6, WATCHLIST_FIXTURE + [f"Alvo Extra {i}" for i in range(6)],
        QUALITY_FIXTURE, ref_date=REF_LATE, stale_days=90, top=5)
    big_lines = rg.intel_lines(big, max_shown=2)
    check("cap de exemplos por gatilho (max_shown=2)",
          sum(1 for ln in big_lines if ln.startswith("  🕰")) == 2)
    check("overflow stale relativo aos exemplos (+10 outras)",
          any("(+10 outras" in ln for ln in big_lines))
    check("overflow no_kununu relativo aos exemplos (+5 outras)",
          any("(+5 outras" in ln for ln in big_lines))


def test_prefix_contract() -> None:
    section("D2: contrato prefixo == header emitido (extrator reconhece)")
    check("INTEL_SECTION_HEADER começa pelo PREFIXO exato",
          rg.INTEL_SECTION_HEADER.startswith(rg.INTEL_SECTION_PREFIX))
    check("prefixo DISTINTO do ⏰ Follow-up (F14) — nunca colide",
          rg.INTEL_SECTION_PREFIX != rg.FOLLOWUP_SECTION_PREFIX
          and not rg.FOLLOWUP_SECTION_PREFIX.startswith(rg.INTEL_SECTION_PREFIX)
          and not rg.INTEL_SECTION_PREFIX.startswith(rg.FOLLOWUP_SECTION_PREFIX))
    trig = ifr.triggers(INTEL_FIXTURE, WATCHLIST_FIXTURE, QUALITY_FIXTURE,
                        ref_date=REF_LATE, stale_days=90, top=5)
    sec = rg.intel_lines(trig)
    check("extrator pega a seção REAL inteira (header + corpo até o blank)",
          rg.intel_section_lines([""] + sec + ["", "🔗 link"]) == sec)
    check("extrator de seção ausente -> []",
          rg.intel_section_lines(["🎯 Perfil", "⚡ Top 5"]) == [])
    check("extrator de lista vazia -> []", rg.intel_section_lines([]) == [])


def test_digest_sections_ab() -> None:
    section("D3/D4: digest_sections — A/B byte a byte (regressão zero)")
    root, cur, prev, intel, (watch, quality) = _digest_fixture_dir("t_f44_ab_")
    url = "https://rios-vini.github.io/internship-finder/"
    # A: SEM o parâmetro novo (comportamento pré-F44)
    a = rg.digest_sections(cur, prev, pages_url=url)
    # B: COM o parâmetro, mas arquivos com ZERO gatilhos (intel fresco)
    fresh_intel = _write(root, "fresh_intel.json", {"companies": [
        {**INTEL_BMW, "checked": "2026-10-14"},
        {**INTEL_BASF, "checked": "2026-10-14"},
    ]})
    full_quality = _write(root, "full_quality.json", {"companies":
        QUALITY_FIXTURE + [{"company": "Vanderlande", "kununu_score": 3.8,
                            "kununu_reviews": 42, "gptw_award": None,
                            "source_type": "kununu-profile",
                            "checked": "2026-10-08"}]})
    b = rg.digest_sections(
        cur, prev, pages_url=url,
        intel_freshness_paths=(fresh_intel, watch, full_quality))
    assert a is not None and b is not None
    ha = hashlib.sha256("\n".join(a).encode()).hexdigest()
    hb = hashlib.sha256("\n".join(b).encode()).hexdigest()
    check("A/B: sem gatilhos + parâmetro presente = digest byte a byte "
          "igual ao de antes (sha256)", ha == hb, f"{ha[:16]} vs {hb[:16]}")
    check("A/B: nenhum header ⏰ Intel em nenhum dos dois",
          all(rg.INTEL_SECTION_PREFIX not in ln for ln in a + b))
    # C: COM gatilhos — ref-date via hook ``today()`` (padrão now_ref
    # F29/F38; fixture usa coorte 09-20 que só fica >90d em 2027)
    import unittest.mock as mock
    with mock.patch.object(ifr, "today", return_value=REF_LATE):
        c = rg.digest_sections(
            cur, prev, pages_url=url,
            intel_freshness_paths=(intel, watch, quality))
    assert c is not None
    check("COM gatilhos: seção ⏰ Intel presente",
          any(ln.startswith(rg.INTEL_SECTION_PREFIX) for ln in c))
    check("contagens corretas na seção (2 >90d; 1 alvo sem Kununu)",
          any("2 >90d" in ln and "1 alvo sem Kununu" in ln for ln in c))
    check("seção ANTES do 🔗 link (última linha)",
          any(ln.startswith(rg.INTEL_SECTION_PREFIX) for ln in c[:-1])
          and c[-1].startswith("🔗"))
    check("digest COM gatilhos difere do A (a seção soma, não substitui)",
          hashlib.sha256("\n".join(c).encode()).hexdigest() != ha)
    with mock.patch.object(ifr, "today", return_value=REF_LATE):
        c2 = rg.digest_sections(
            cur, prev, pages_url=url,
            intel_freshness_paths=(intel, watch, quality))
    check("idempotência: mesma chamada = mesmo digest (sha256)",
          hashlib.sha256("\n".join(c2).encode()).hexdigest()
          == hashlib.sha256("\n".join(c).encode()).hexdigest())
    # arquivos corrompidos: best-effort, seção ausente, SEM erro. Os dois
    # gatilhos são INDEPENDENTES: corromper o intel mata só o gatilho (a)
    # (stale); o (b) (watchlist×quality) segue vivo — a seção permanece
    # HONESTA com "1 alvo sem Kununu" e sem a parte stale.
    bad = root / "bad2.json"
    bad.write_text("{", encoding="utf-8")
    d = rg.digest_sections(cur, prev, pages_url=url,
                           intel_freshness_paths=(bad, watch, quality))
    assert d is not None
    check("intel corrompido -> gatilho stale morto (sem '>90d')",
          all(">90d" not in ln for ln in d))
    check("intel corrompido -> digest não derruba, gatilho (b) segue "
          "honesto (⏰ só com alvo sem Kununu)",
          any(ln.startswith(rg.INTEL_SECTION_PREFIX)
              and "1 alvo sem Kununu" in ln for ln in d))
    bad_watch = root / "bad3.json"
    bad_watch.write_text("[", encoding="utf-8")
    bad_qual = root / "bad4.json"
    bad_qual.write_text("nope", encoding="utf-8")
    e = rg.digest_sections(cur, prev, pages_url=url,
                           intel_freshness_paths=(bad, bad_watch, bad_qual))
    assert e is not None
    check("os TRÊS arquivos corrompidos -> seção inteira ausente",
          all(not ln.startswith(rg.INTEL_SECTION_PREFIX) for ln in e))
    check("digest segue íntegro com os 3 corrompidos (link no fim)",
          e[-1].startswith("🔗"))


# ---------------------------------------------------------------------------
# C — compactador (build_message)
# ---------------------------------------------------------------------------

def _big_digest_with_intel() -> list[str]:
    """Digest que estoura 4096 MESMO na reconstrução do compact.

    As linhas gordas vivem nas seções PRESERVADAS (🆕/⚡/🎯) — o digest
    do compactador reconstrói a partir delas, então o aperto real só
    acontece quando elas são grandes (lição F36.1: perfil gordo não
    exercita o colapso; o corpo das seções preservadas é o orçamento).
    """
    trig = ifr.triggers(INTEL_FIXTURE, WATCHLIST_FIXTURE, QUALITY_FIXTURE,
                        ref_date=REF_LATE, stale_days=90, top=5)
    lines = ["", "🎯 Perfil e critérios ativos"]
    lines += [f"linha de perfil {i} — " + "x" * 200 for i in range(14)]
    # Header VERBATIM da 🆕 que o compactador reconhece (F13 extrator):
    # "🆕 Novas desde ontem: <N>" (new_since_lines) — não confundir com
    # o header "🆕 Novas vagas no Top 30" da seção do enunciado Fase 2.
    lines += ["", "🆕 Novas desde ontem: 30"]
    lines += [f"  #{i} — vaga nova {i} — Acme (12.5) — " + "y" * 200
              for i in range(1, 31)]
    lines += ["", "⚡ Top 5 do dia (candidatura direta)"]
    lines += rg.format_top5([_apply_job(i) for i in range(5)]).splitlines()
    lines += ["", rg.WATCHLIST_SECTION_HEADER + " — 3 nova(s)"]
    lines += [f"  🎯 {i}. Alvo {i}: titulo (local)" for i in range(1, 4)]
    lines += [""]
    lines += rg.intel_lines(trig)
    lines += ["", rg.FOLLOWUP_SECTION_HEADER + " — 2 pendente(s) "
              "(aplicadas há mais de 10 dias sem resposta)"]
    lines += ["  ⏰ 1. Firma 3 GmbH: titulo (há 12 dias)",
              "  ⏰ 2. Firma 4 GmbH: titulo (há 15 dias)"]
    lines += ["", "🔗 Ranking completo (todas as vagas elegíveis): "
             "https://rios-vini.github.io/internship-finder/"]
    return lines


def test_compact_keeps_intel_header() -> None:
    section("C1: compact >4096 — header ⏰ Intel sobrevive, layout estável")
    digest = _big_digest_with_intel()
    check("digest do fixture estoura 4096 (como no dia real)",
          len("\n".join(digest)) > rd.TELEGRAM_MAX_LEN,
          f"{len(chr(10).join(digest))} chars")
    msg = rd.build_message(_summary(), _base_alerts(), 2, always_notify=True,
                            disk_pct=90, digest_lines=digest)
    check("mensagem compactada cabe no Telegram",
          len(msg) <= rd.TELEGRAM_MAX_LEN, f"{len(msg)} chars")
    check("header ⏰ Intel com contagens SOBREVIVE ao compact",
          rg.INTEL_SECTION_PREFIX in msg and "1 alvo sem Kununu" in msg)
    check("CORPO da seção cede espaço (exemplos fora, header fica)",
          "Vanderlande" not in msg and "🕰" not in msg)
    check("header ⏰ Follow-up também sobrevive (F14 intacto)",
          rg.FOLLOWUP_SECTION_PREFIX in msg)
    check("ORDEM estável: ⏰ Intel imediatamente ANTES da ⏰ Follow-up "
          "(mesma posição do digest inteiro)",
          msg.index(rg.INTEL_SECTION_PREFIX) < msg.index(rg.FOLLOWUP_SECTION_PREFIX))
    check("⚡ Top 5 preservado com as 5 apply_urls",
          "⚡ Top 5 do dia" in msg
          and msg.count("https://apply.example.com/") == 5)
    check("🆕 colapsada ao header (contagem viva)", "Novas desde ontem" in msg)
    check("🎯 colapsada ao header", rg.WATCHLIST_SECTION_PREFIX in msg)
    check("🔗 link do ranking por último",
          msg.endswith("🔗 Ranking completo (todas as vagas elegíveis): "
                       "https://rios-vini.github.io/internship-finder/"))
    check("nenhum bloco em branco duplicado", "\n\n\n" not in msg)


def test_compact_without_intel() -> None:
    section("C2: compact estourado SEM ⏰ Intel — sem header fantasma")
    digest = _big_digest_with_intel()
    # remove a seção ⏰ Intel (deixa o resto igual)
    sans = [ln for ln in digest
            if not ln.startswith(("  🕰", "  ⭐", "  (+", "  → humano:"))
            and not ln.startswith(rg.INTEL_SECTION_PREFIX)]
    msg = rd.build_message(_summary(), _base_alerts(), 2, always_notify=True,
                            disk_pct=90, digest_lines=sans)
    check("mensagem cabe", len(msg) <= rd.TELEGRAM_MAX_LEN, f"{len(msg)} chars")
    check("sem seção no digest -> nenhum header ⏰ Intel no compact",
          rg.INTEL_SECTION_PREFIX not in msg)
    check("⏰ Follow-up segue presente (vizinho não contaminado)",
          rg.FOLLOWUP_SECTION_PREFIX in msg)
    check("⚡/🔗 intactos", "⚡ Top 5 do dia" in msg
          and msg.startswith("📊") and "🔗" in msg)


def main() -> int:
    test_stale_entries()
    test_no_kununu_targets()
    test_triggers_and_summary()
    test_loaders_defensive()
    test_idempotence()
    test_intel_lines()
    test_prefix_contract()
    test_digest_sections_ab()
    test_compact_keeps_intel_header()
    test_compact_without_intel()
    print()
    if FAILURES:
        print(f"F44: {len(FAILURES)} FALHA(S) de {CHECKS} checks")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print(f"F44: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
