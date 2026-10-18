"""Testes da Fase F54 — higiene de display: sanitizer de mojibake + aliases de
empresa (100% offline).

Dois defeitos de credibilidade visíveis a recruiters na página pública, ambos
corrigidos NO RENDER (dataset intocado):

1. **Mojibake UTF-8-decodado-como-cp1252** (VERBATIM do card #99 do build ao
   vivo 15/10 — Lidl Dienstleistung / arbeitsagentur 13649-12808131AB-S):
   ``Produkt-Compliance QualitÃ¤t`` → ``Qualität``. O texto a montante era
   UTF-8 válido e uma camada o decodificou como cp1252 (não latin-1 puro:
   ``Ÿ`` = U+0178, ``„``, ``–`` são os chars tipográficos do cp1252 para os
   bytes 0x9F/0x84/0x96). O conserto é o round-trip exato cp1252/latin-1 →
   UTF-8, validado por decode STRICT (texto legítimo nunca é tocado).

2. **Nomes de empresa sujos** (hostnames de ATS) → ``config/display_aliases.json``
   (match EXATO, case-sensitive, sem substring). Regra de honestidade: alias
   troca SÓ o nome de exibição; incerto → ORIGINAL (os 3 [CONFIRMAR-DONO]
   ficam intactos por design).

Contratos testados:

- M1–M8: módulo ``display_hygiene`` — sanitizer (7 padrões da spec + caso real
  + mojibake de 3 bytes cp1252 + idempotência + negativos legítimos + tipos
  não-str), ``looks_mojibake``, ``load_display_aliases`` (arquivo real do repo
  com os 18 seeds; ausente/corrompido → ``{}``; ``_comment`` ignorado),
  ``display_company`` (exato, case-sensitive, sem alias → original) e
  ``display_job_view`` (cópia rasa: original NUNCA mutado, ``raw`` compartilhado).
- R1–R7: render top-N — mojibake corrigido em title/company/location; alias
  aplicado; AMBÍGUOS intactos; ``data-q`` (busca client-side) higienizado;
  INTEL não contaminado (o badge 🛂 casa pela company ORIGINAL, não pelo alias).
- F1–F2: regime FULL-LIST recebe a MESMA higiene (ponto único da spec item 5).
- A1–A3: A/B byte-diff — referência "pré-F54" forjada por monkeypatch
  (``display_job_view`` → identidade, exatamente o comportamento antigo): com
  fixture LIMPA os dois braços são byte a byte IDÊNTICOS (regressão zero); com
  fixture DOENTE a única diferença são as substituições esperadas (replace
  exato reproduz o HTML pós) e os ambíguos ficam iguais nos dois braços.
- C1–C3: caminho CLI/loader — ``--display-aliases`` anunciado no ``--help``;
  default do repo carrega os 18 aliases; caminho inexistente → best-effort
  (sanitizer ativo, nomes ORIGINAIS, nunca erro).

Fixtures: título/company VERBATIM do card #99 real (medido ao vivo); a location
com mojibake é SINTÉTICA (não medida) e está marcada no código. Nenhum payload
de produção, zero rede.

Uso:  .venv/bin/python scripts/test_f54.py   (ou bash scripts/test_f54.py)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/

import minimal_page as mp  # noqa: E402
from internship_finder import display_hygiene as dh  # noqa: E402
from internship_finder import opportunity_intel as oi  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
STAMP = "2026-10-16 12:00"  # carimbo fixo: renders A/B comparáveis
ALIASES_PATH = REPO / "config" / "display_aliases.json"

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    print(f"  [{'OK' if cond else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# VERBATIM do card #99 (build ao vivo 15/10): título e company reais.
REAL_TITLE_MOJIBAKE = (
    "Praktikum Einkauf International - Produkt-Compliance QualitÃ¤t")
REAL_TITLE_FIXED = (
    "Praktikum Einkauf International - Produkt-Compliance Qualität")
REAL_COMPANY = "Lidl Dienstleistung GmbH & Co. KG"     # limpa (sem alias)
# SINTÉTICA (não medida): location com mojibake cp1252 do mesmo padrão.
LOC_MOJIBAKE = "Bad WÃ¶rishofen"
LOC_FIXED = "Bad Wörishofen"


def _job(jid, title, company, location, score=10.0, **extra):
    job = {"id": jid, "title": title, "company": company, "location": location,
           "score": score, "url": f"https://example.com/{jid}"}
    job.update(extra)
    return job


def _fixture_real() -> list[dict]:
    """Amostra com o caso real + seeds de alias + os 3 ambíguos + controle."""
    return [
        _job("lidl|direct:bundesagentur:13649-12808131AB-S",
             REAL_TITLE_MOJIBAKE, REAL_COMPANY, LOC_MOJIBAKE, 12.5),
        _job("dhl|sf_dataset:successfactors:x1",
             "Praktikum Logistik International", "careers.dhl.com",
             "Bonn", 11.0),
        _job("nokia|x2", "Werkstudent Supply Chain", "nestleHRprdRMK",
             "MÃ¼nchen", 10.5),
        _job("fa|sf_dataset:x3", "Werkstudent Materialentwicklung",
             "Fa Exdu Saasfaprod1", "Berlin", 10.0),      # AMBÍGUO
        _job("apply|absolventa:13379831", "Praktikum im Einkauf",
             "Apply now!", "Hamburg", 9.0),               # AMBÍGUO
        _job("edbz|x4", "Werkstudent Procurement", "edbz",
             "Köln", 8.5),                                # AMBÍGUO
        _job("bosch|x5", "Werkstudent Materialentwicklung",
             "Bosch", "Stuttgart", 8.0),                  # controle limpo
    ]


def _fixture_clean() -> list[dict]:
    """Sem mojibake e sem nenhum alias-match — A/B deve ser byte a byte."""
    return [
        _job("a|x", "Werkstudent Materialentwicklung", "Bosch",
             "Stuttgart", 9.0),
        _job("b|x", "Praktikum Logistik", "Siemens", "München", 8.0),
        _job("c|x", "Praktikum Einkauf", "Kärcher", "Winnenden", 7.0),
    ]


def _render(jobs, **kw):
    kw.setdefault("total_eligible", len(jobs))
    kw.setdefault("generated_at", STAMP)
    # F46: default do render virou EN (decisão do dono 15/10); esta suíte
    # valida o chrome/alias da fase — force lang="pt" (contrato (b) F46).
    return mp.render_minimal_html(jobs, lang="pt", **kw)


# ---------------------------------------------------------------------------
# M — módulo display_hygiene
# ---------------------------------------------------------------------------

def test_module_sanitizer() -> None:
    section("M1–M6 — sanitizer de mojibake (função pura, determinística)")
    check("M1 caso real do card #99 (VERBATIM)",
          dh.fix_mojibake(REAL_TITLE_MOJIBAKE) == REAL_TITLE_FIXED,
          repr(dh.fix_mojibake(REAL_TITLE_MOJIBAKE)))

    spec_pairs = [("Ã¤", "ä"), ("Ã¶", "ö"), ("Ã¼", "ü"), ("ÃŸ", "ß"),
                  ("Ã„", "Ä"), ("Ã–", "Ö"), ("Ãœ", "Ü")]
    all_ok = all(dh.fix_mojibake(f"x{p}y") == f"x{e}y" for p, e in spec_pairs)
    check("M2 os 7 padrões da spec (ä ö ü ß Ä Ö Ü)", all_ok)

    # mojibake de 3 bytes via cp1252: E2 82 AC (€) → â‚¬
    check("M3 mojibake cp1252 de 3 bytes (â‚¬ → €)",
          dh.fix_mojibake("â‚¬") == "€")
    check("M3b cp1252 tipográfico isolado num título",
          dh.fix_mojibake("Gehalt â€“ 900 â‚¬ Ã¼ber") == "Gehalt – 900 € über")

    legit = ["Qualität", "café", "Müller GmbH", "für Praktikanten",
             "Ökologie", "Übung", "STRASSENÖKOLOGIE", "São Paulo",
             "Düsseldorf", "Fa Exdu Saasfaprod1", "Ã land", "Werkstudent",
             "Praktikum Einkauf", "AUMOVIO SE Haupverwaltung"]
    untouched = [s for s in legit if dh.fix_mojibake(s) != s]
    check("M4 texto legítimo NUNCA alterado (14 negativos)",
          not untouched, f"alterados: {untouched}")

    once = dh.fix_mojibake(REAL_TITLE_MOJIBAKE)
    check("M5 idempotente (2× == 1×)", dh.fix_mojibake(once) == once)
    check("M6 robusto a vazio/None/não-str",
          dh.fix_mojibake("") == "" and dh.fix_mojibake(None) is None
          and dh.fix_mojibake(123) == 123)  # type: ignore[arg-type]
    check("M6b looks_mojibake true/false",
          dh.looks_mojibake(REAL_TITLE_MOJIBAKE) is True
          and dh.looks_mojibake(REAL_TITLE_FIXED) is False
          and dh.looks_mojibake("") is False)


def test_module_aliases() -> None:
    section("M7–M8 — aliases de display")
    aliases = dh.load_display_aliases(ALIASES_PATH)
    seeds = {
        "lidlstiftup2": "Lidl", "careers.allianz.com": "Allianz",
        "Our jobs - CANAL+ Group": "CANAL+ Group",
        "hairoboticseurope.jobs.personio.com": "HAI Robotics",
        "nestleHRprdRMK": "Nestlé", "FRoSTA AG Career": "FRoSTA",
        "careers.dhl.com": "DHL", "careers.roche.com": "Roche",
        "careers.bcg.com": "BCG", "careers.agcocorp.com": "AGCO",
        "careers.knorr-bremse.com": "Knorr-Bremse", "bil.csod.com": "BIL",
        "issgovernance": "ISS Governance", "trumpf": "TRUMPF",
        "hella": "HELLA", "Gsk": "GSK",
        "AUMOVIO SE Haupverwaltung": "AUMOVIO SE", "auto1": "AUTO1",
    }
    check("M7 arquivo real traz os 18 seeds EXATOS",
          len(aliases) == 18 and all(aliases.get(k) == v for k, v in seeds.items()),
          f"chaves lidas: {len(aliases)}")
    check("M7b _comment não vira alias",
          all(not k.startswith("_") for k in aliases))

    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "nope.json"
        check("M7c ausente → {}", dh.load_display_aliases(missing) == {})
        broken = Path(tmp) / "broken.json"
        broken.write_text("{ não é json", encoding="utf-8")
        check("M7d corrompido → {}", dh.load_display_aliases(broken) == {})
        empty = Path(tmp) / "empty.json"
        empty.write_text('{"aliases": {}}', encoding="utf-8")
        check("M7e vazio → {}", dh.load_display_aliases(empty) == {})

    check("M8 alias exato aplicado",
          dh.display_company("careers.dhl.com", aliases) == "DHL")
    check("M8b case-sensitive (gsK não casa Gsk)",
          dh.display_company("gsK", aliases) == "gsK")
    check("M8c sem alias → original",
          dh.display_company("Bosch", aliases) == "Bosch")
    check("M8d vazio → ''", dh.display_company("", aliases) == ""
          and dh.display_company(None, aliases) == "")

    original = {"id": "x", "title": REAL_TITLE_MOJIBAKE,
                "company": "careers.dhl.com", "location": LOC_MOJIBAKE,
                "score": 1.0, "raw": {"apply_url": "https://a"}}
    view = dh.display_job_view(original, aliases)
    check("M8e view higieniza title/company/location",
          view["title"] == REAL_TITLE_FIXED and view["company"] == "DHL"
          and view["location"] == LOC_FIXED)
    check("M8f original NUNCA mutado",
          original["title"] == REAL_TITLE_MOJIBAKE
          and original["company"] == "careers.dhl.com"
          and original["location"] == LOC_MOJIBAKE)
    check("M8g cópia RASA (raw compartilhado por referência)",
          view["raw"] is original["raw"])


# ---------------------------------------------------------------------------
# R — render top-N
# ---------------------------------------------------------------------------

def test_render_topn() -> None:
    section("R1–R7 — render top-N (higiene display-only)")
    aliases = dh.load_display_aliases(ALIASES_PATH)
    html = _render(_fixture_real(), display_aliases=aliases)

    check("R1 mojibake corrigido no título", REAL_TITLE_FIXED in html)
    check("R1b mojibake corrigido na location", LOC_FIXED in html)
    check("R1c nenhum mojibake residual no HTML",
          "QualitÃ¤t" not in html and "WÃ¶rishofen" not in html
          and "MÃ¼nchen" not in html)
    check("R2 alias aplicado (careers.dhl.com → DHL)",
          "DHL" in html and "careers.dhl.com" not in html)
    check("R2b alias Nestlé aplicado (nestleHRprdRMK)",
          "Nestlé" in html and "nestleHRprdRMK" not in html)
    check("R2c company LIMPA (sem alias) fica intacta",
          "Lidl Dienstleistung GmbH &amp; Co. KG" in html)

    # item 3 da spec: ambíguos NÃO são mapeados — ficam ORIGINAIS
    check("R3 ambíguo 'Fa Exdu Saasfaprod1' intacto",
          "Fa Exdu Saasfaprod1" in html)
    check("R3b ambíguo 'Apply now!' intacto", "Apply now!" in html)
    check("R3c ambíguo 'edbz' intacto", "edbz" in html)
    check("R3d regra de honestidade: desconhecida → original",
          "Bosch" in html)

    # data-q (busca client-side) deve usar o texto EXIBIDO (higienizado)
    import re
    m = re.search(r'data-q="([^"]*Qualit[^"]*)"', html)
    check("R4 data-q higienizado (busca acha o texto exibido)",
          bool(m) and "Qualität" in m.group(1) and "Ã" not in m.group(1),
          (m.group(1)[:70] if m else "sem data-q com Qualit"))

    # R5 — INTEL não contaminado: a company ORIGINAL casa o badge 🛂 mesmo
    # com o alias aplicado no display (o lookup usa o job original).
    intel_map = {}
    with tempfile.TemporaryDirectory() as tmp:
        ip = Path(tmp) / "intel.json"
        ip.write_text(json.dumps({"companies": [{
            "company": "careers.dhl.com",          # chave = string ORIGINAL
            "visa_policy": "unclear",
            "sources": ["https://example.com/dhl-visa"],
            "checked": "2026-10-01",
        }]}), encoding="utf-8")
        intel_map = oi.load_company_intel(ip)
    html_i = _render(_fixture_real(), display_aliases=aliases,
                     company_intel_map=intel_map)
    check("R5 intel casa pela company ORIGINAL (badge 🛂 presente)",
          'class="vf"' in html_i and "DHL" in html_i)
    check("R5b sem intel não há badge (controle)",
          'class="vf"' not in html)

    check("R6 tokens de estrutura intactos (link de candidatura)",
          "candidatar-se" in html or "abrir vaga" in html)
    check("R7 score exibido inalterado (12.5 no card do #99)",
          'data-s="12.5"' in html)


# ---------------------------------------------------------------------------
# F — regime full-list (spec item 5: ambos os regimes)
# ---------------------------------------------------------------------------

def test_render_full() -> None:
    section("F1–F2 — regime full-list recebe a MESMA higiene")
    aliases = dh.load_display_aliases(ALIASES_PATH)
    html = _render(_fixture_real(), display_aliases=aliases, full_list=True)
    check("F1 full: mojibake corrigido", REAL_TITLE_FIXED in html
          and "QualitÃ¤t" not in html)
    check("F1b full: alias aplicado", "DHL" in html
          and "careers.dhl.com" not in html)
    check("F2 full: ambíguos intactos",
          "Fa Exdu Saasfaprod1" in html and "Apply now!" in html
          and "edbz" in html)


# ---------------------------------------------------------------------------
# A — A/B byte-diff
# ---------------------------------------------------------------------------

def test_ab_byte_diff() -> None:
    section("A1–A3 — A/B byte-diff vs referência pré-F54")
    aliases = dh.load_display_aliases(ALIASES_PATH)
    original_view = dh.display_job_view

    def pre_f54(jobs, **kw):
        # Braço A forjado: a "referência pré-F54" = view desligada
        # (exatamente o comportamento antigo: nenhuma higiene).
        dh.display_job_view = lambda job, al: job  # type: ignore[assignment]
        try:
            return _render(jobs, **kw)
        finally:
            dh.display_job_view = original_view  # type: ignore[assignment]

    # A1 — fixture LIMPA: byte a byte idêntico (regressão zero)
    clean = _fixture_clean()
    pre = pre_f54(clean, display_aliases=aliases)
    post = _render(clean, display_aliases=aliases)
    check("A1 fixture limpa: pré-F54 == pós-F54 (byte a byte)", pre == post,
          f"{len(pre)} vs {len(post)} bytes")

    # A2 — fixture DOENTE: a ÚNICA diferença são as substituições esperadas
    dirty = _fixture_real()
    pre = pre_f54(dirty, display_aliases=aliases)
    post = _render(dirty, display_aliases=aliases)
    # Substituições por TOKEN curto: o título mojibake aparece 2× no HTML
    # (título principal + linha EN derivada via translation-cache, que
    # herda a cauda não-traduzida " - Produkt-Compliance QualitÃ¤t") — o
    # replace de string COMPLETA pegaria só a 1ª ocorrência e deixaria
    # resíduo "Ã¤" na linha EN. Tokens de mojibake (Ã+continuation) não
    # ocorrem em texto legítimo (verificado pelos 14 negativos de M4).
    reconstructed = (pre
                     .replace("QualitÃ¤t", "Qualität")
                     .replace(LOC_MOJIBAKE, LOC_FIXED)
                     .replace("MÃ¼nchen", "München")
                     .replace("careers.dhl.com", "DHL")
                     .replace("nestleHRprdRMK", "Nestlé"))
    check("A2 diff == substituições esperadas (replace exato reproduz)",
          reconstructed == post,
          "diff residual além do esperado" if reconstructed != post else "")
    check("A2b o diff NÃO é vazio (a fixture exercita a fase)",
          pre != post)

    # A3 — ambíguos idênticos nos dois braços
    ambiguous = ["Fa Exdu Saasfaprod1", "Apply now!", "edbz"]
    check("A3 ambíguos byte a byte iguais nos 2 braços",
          all(pre.count(a) == post.count(a) and a in post for a in ambiguous))


# ---------------------------------------------------------------------------
# C — CLI / loader
# ---------------------------------------------------------------------------

def test_cli() -> None:
    section("C1–C3 — CLI + loader best-effort")
    script = REPO / "scripts" / "minimal_page.py"
    rc = subprocess.run([sys.executable, str(script), "--help"],
                        capture_output=True, text=True, timeout=60)
    check("C1 --help anuncia --display-aliases",
          "--display-aliases" in rc.stdout, rc.stdout[-200:])

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        (tmpdir / "data").mkdir()
        (tmpdir / "config").mkdir()
        shutil.copy(ALIASES_PATH, tmpdir / "config" / "display_aliases.json")
        (tmpdir / "data" / "jobs.json").write_text(
            json.dumps(_fixture_real()), encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "HOME": str(tmpdir),
               "PYTHONPATH": str(REPO / "src")}
        out = tmpdir / "out.html"
        proc = subprocess.run(
            [sys.executable, str(script), "--input", "data/jobs.json",
             "--top", "50", "--output", str(out),
             "--display-aliases", "config/display_aliases.json",
             "--archive", ""],
            capture_output=True, text=True, timeout=120,
            cwd=tmpdir, env=env,
        )
        html = out.read_text(encoding="utf-8") if out.exists() else ""
        check("C2 CLI end-to-end: sanitizer + alias no HTML",
              proc.returncode == 0 and REAL_TITLE_FIXED in html
              and "careers.dhl.com" not in html and "DHL" in html,
              (proc.stderr or "")[-200:] if proc.returncode else "")

        # C3 — caminho inexistente: best-effort (sanitizer ativo, sem alias)
        out2 = tmpdir / "out2.html"
        proc2 = subprocess.run(
            [sys.executable, str(script), "--input", "data/jobs.json",
             "--top", "50", "--output", str(out2),
             "--display-aliases", "config/nao-existe.json", "--archive", ""],
            capture_output=True, text=True, timeout=120,
            cwd=tmpdir, env=env,
        )
        html2 = out2.read_text(encoding="utf-8") if out2.exists() else ""
        check("C3 alias ausente: best-effort (mojibake OK, nomes originais)",
              proc2.returncode == 0 and REAL_TITLE_FIXED in html2
              and "careers.dhl.com" in html2,
              (proc2.stderr or "")[-200:] if proc2.returncode else "")


# ---------------------------------------------------------------------------
# Q — painel ⭐ de qualidade (F54.1): aliases também lá
# ---------------------------------------------------------------------------

def _tag_stripped(html: str) -> str:
    """Texto VISÍVEL da página: tags fora (mesmo padrão do A/B do
    orquestrador que detectou a fuga). Atributos (href, data-jid, …) vivem
    DENTRO dos colchetes da tag e somem junto — sobra só o texto puro.
    """
    return re.sub(r"<[^>]+>", " ", html)


def _panel_section(html: str) -> str:
    """HTML da seção '⭐ Ponto ótimo' (o painel de qualidade); '' ausente."""
    m = re.search(r"<h2>⭐ Ponto ótimo.*?</ul>", html, re.S)
    return m.group(0) if m else ""


def _fixture_painel() -> list[dict]:
    """Empresas que caem no painel ⭐ via quality_map/intel (offline):
    DHL (GPTW), BCG (Kununu) — as duas strings ALIAS do caso real — e um
    controle limpo (Bosch) que NÃO pode ser aliasado."""
    return [
        _job("dhl|p:1", "Praktikum Logistik International",
             "careers.dhl.com", "Bonn", 11.0),
        _job("dhl|p:2", "Praktikum Supply Chain", "careers.dhl.com",
             "Bonn", 10.0),
        _job("bcg|p:1", "Praktikum Procurement Analytics",
             "careers.bcg.com", "Düsseldorf", 9.0),
        _job("bosch|p:1", "Werkstudent Material", "Bosch",
             "Stuttgart", 8.0),
    ]


def test_quality_panel() -> None:
    section("Q1–Q6 — F54.1: painel ⭐ de qualidade passa pelo MESMO alias")
    aliases = dh.load_display_aliases(ALIASES_PATH)

    # intel (visa_friendly — critério 3 do painel) + quality (critério 2)
    with tempfile.TemporaryDirectory() as tmp:
        ip = Path(tmp) / "intel.json"
        ip.write_text(json.dumps({"companies": [
            {"company": "careers.dhl.com", "visa_policy": "unclear",
             "sources": ["https://example.com/dhl"], "checked": "2026-10-01"},
            {"company": "careers.bcg.com", "visa_policy": "unclear",
             "sources": ["https://example.com/bcg"], "checked": "2026-10-01"},
            {"company": "Bosch", "visa_policy": "unclear",
             "sources": ["https://example.com/bosch"], "checked": "2026-10-01"},
        ]}), encoding="utf-8")
        intel = oi.load_company_intel(ip)

        qp = Path(tmp) / "eq.json"
        qp.write_text(json.dumps({"companies": [
            {"company": "careers.dhl.com", "kununu_score": 3.7,
             "kununu_reviews": 100, "gptw_award": 2026,
             "source_url": "https://example.com/k/dhl", "checked": "2026-10-01"},
            {"company": "careers.bcg.com", "kununu_score": 4.0,
             "kununu_reviews": 50, "gptw_award": None,
             "source_url": "https://example.com/k/bcg", "checked": "2026-10-01"},
            {"company": "Bosch", "kununu_score": 4.0, "kununu_reviews": 200,
             "gptw_award": None,
             "source_url": "https://example.com/k/bosch", "checked": "2026-10-01"},
        ]}), encoding="utf-8")
        from internship_finder import employer_quality as eq
        quality_map = eq.load_employer_quality(qp)

        jobs = _fixture_painel()
        rows = eq.sweet_spot_companies(jobs, quality_map, intel)
        check("Q0 rows derivadas (3 empresas, originais cruas)",
              [r["company"] for r in rows] ==
              ["careers.dhl.com", "Bosch", "careers.bcg.com"],
              str([r["company"] for r in rows]))

        html = _render(jobs, display_aliases=aliases, company_intel_map=intel,
                       quality_map=quality_map, sweet_spot_rows=rows)
        panel = _panel_section(html)
        visible = _tag_stripped(html)

        check("Q1 painel presente no render",
              bool(panel) and "vagas eligible" in panel)
        check("Q2 painel SEM nenhum nome do mapa cru (11/11)",
              all(k not in panel for k in aliases),
              str([k for k in aliases if k in panel]))
        check("Q3 DHL/BCG aliasados no painel",
              "DHL" in panel and "careers.dhl.com" not in panel
              and "BCG" in panel and "careers.bcg.com" not in panel,
              panel[:200])
        # TODO o HTML (texto visível), não só o painel — pega qualquer OUTRA
        # fuga de texto visível que o painel-teste deixaria passar.
        check("Q4 página inteira sem nome do mapa no TEXTO visível",
              all(k not in visible for k in aliases),
              str([k for k in aliases if k in visible]))
        check("Q5 linha do painel no formato esperado",
              "<li>DHL · ⭐ 3,7 · 🏆 GPTW 2026 · 2 vagas eligible</li>" in panel
              and "<li>Bosch · ⭐ 4,0 · Kununu · 1 vaga eligible</li>" in panel
              and "<li>BCG · ⭐ 4,0 · Kununu · 1 vaga eligible</li>" in panel)
        check("Q5b rows ORIGINAIS nunca mutadas (display-only)",
              [r["company"] for r in rows] ==
              ["careers.dhl.com", "Bosch", "careers.bcg.com"])

        # Q6 — cadeia de degradação (render_size_aware): o painel sobrevive
        # às remontagens COM higiene (lição F36.1/F54).
        html_chain = mp.render_size_aware(
            jobs, total_eligible=len(jobs), generated_at=STAMP,
            company_intel_map=intel, quality_map=quality_map,
            sweet_spot_rows=rows, display_aliases=aliases, lang="pt")
        check("Q6 cadeia de degradação: painel limpo em TODAS as montagens",
              all(k not in _tag_stripped(html_chain) for k in aliases))

        # Q7 — sem sweet_spot_rows: painel ausente, render nunca quebra.
        html_empty = _render(jobs, display_aliases=aliases,
                             sweet_spot_rows=[])
        check("Q7 painel ausente (rows vazias) — sem erro, sem seção",
              isinstance(html_empty, str) and not _panel_section(html_empty))


def main() -> int:
    print("F54 — higiene de display: sanitizer mojibake + aliases de empresa")
    test_module_sanitizer()
    test_module_aliases()
    test_render_topn()
    test_render_full()
    test_ab_byte_diff()
    test_cli()
    test_quality_panel()
    print()
    if FAILURES:
        print(f"F54: FALHAS: {len(FAILURES)} de {CHECKS} checks")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print(f"F54: TUDO OK — {CHECKS} checks, 0 falhas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
