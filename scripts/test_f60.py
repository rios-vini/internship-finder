#!/usr/bin/env python3
''''true; V="$(dirname "$0")/../.venv/bin/python"; [ -x "$V" ] || V=python3; exec "$V" -- "$0" "$@" # '''
"""Suite F60 — Idioma: 3 lacunas do registro de desfechos 10/2026.

Poliglota de 1 linha (bash: ``exec`` re-invoca sob python3; python: string
no-op) — ``bash scripts/test_f60.py`` e ``python scripts/test_f60.py``
rodam a mesma suíte; o CI usa ``python scripts/$t.py`` (contrato ci.yml).

F60 (19/10): o dono rotulou ~37 desfechos reais; 3 vagas com alemão
exigido passaram no filtro f-de e 1 exigia francês sem sinal algum.
Verificação por classe (evidência do snapshot 736 + probes ao vivo
19/10, UA ``internship-finder-diagnostic/1.0``):

- CLASSE A — texto PRESENTE, classificação falha (MOLEQLAR
  ``absolventa:13258677`` — a card citava o id da twin Würth
  ``absolventa:13251590``, que sempre esteve correta; verificado contra
  o REGISTRO-AVALIACOES 10/2026): o ``qual`` só casava ``gute|guter|
  gutes`` — nunca o ``gut`` BARE de "sehr gut Deutsch"; e
  ``deutschsprachig\s*(team|umfeld|...)`` exigia substantivo DEPOIS —
  em "Arbeitsalltag hauptsächlich deutschsprachig" ele vem ANTES.
  Fix: ``gut`` bare nas listas de intensidade (janela glued ±25 SEM
  cruzar vírgula + janela ±45), verbo de 2ª pessoa ("Du sprichst ...
  Deutsch") e "deutschsprachig" qualificado por advérbio ou janela
  reversa — todos ``required``.
- CLASSE B — texto AUSENTE do pipeline (KPMG ``sf 927796101`` e Lidl BI
  ReqEng ``praktikum_info:13308116`` — a card citava a irmã VÁLIDA
  ``13308134``, sem requisito de idioma): probes provam que a página
  viva do Lidl TEM o texto (JSON-LD com "Sehr gute Deutschkenntnisse"
  verbatim; o dataset serve description VAZIA) e que o feed RSS do KPMG
  carrega SÓ a intro de 314 chars (o requisito vive no template
  JS-rendered do Career Site Builder — o HTML do servidor tem 422 chars
  de texto visível). O detector BASE e o FIXADO classificam o texto
  enriquecido como ``required/qual``: a falha é de COMPLETUDE de dados
  (upstream), não do detector. Fix local impossível sem browser
  (decisão do dono); issues upstream preparadas em
  ~/.hermes/handoff/f60-idioma/.
- CLASSE A2 — francês como SINAL (CANAL+ ``sf 1373297557``):
  ``french_level`` classifica menções (french/französisch/français) com
  os mesmos qualificadores de evidência; badge 🇫🇷 + ``data-fr`` na
  página. NUNCA exclusão: nenhum filtro JS consome ``data-fr`` e o
  ranking NÃO lê francês (vaga fora dos mercados-alvo é outro filtro).

ZERO REDE: fixtures VERBATIM (frases contíguas byte a byte do snapshot
736 congelado em /tmp na medição F60 + JSON-LD do probe Lidl + citação
do registro do dono). Nenhum socket; data/ intocado.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from internship_finder import app_intel  # noqa: E402
from internship_finder.ranking import (  # noqa: E402
    PENALTY_LANG_DE_PREFERRED,
    PENALTY_LANG_DE_REQUIRED,
    WEIGHT_LANG_EN,
    _language_score,
)

ROOT = Path(__file__).resolve().parent.parent
import ci_discover_tests  # noqa: E402  # F78: suíte do CI = descoberta

CHECKS: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    CHECKS.append((name, bool(cond), detail))


# ---------------------------------------------------------------------------
# Fixtures VERBATIM — frases contíguas byte a byte (snapshot 736 congelado
# 19/10, extração F60) + JSON-LD do probe ao vivo + citação do registro.
# ---------------------------------------------------------------------------
# MOLEQLAR absolventa:13258677 (description @2338) — a falha mais grave da
# classe A: passou no f-de com penalties=0.0, language=0.0.
MOLEQLAR_VERBATIM = (
    "Du sprichst sehr gut Deutsch, da unser Arbeitsalltag "
    "hauptsächlich deutschsprachig ist."
)
# Vodafone Procurement sf 770523101 (Düsseldorf) — flip adicional achado
# pela medição F60 no universo 736 (audorado: evidência textual citada).
VODAFONE_VERBATIM = "Du sprichst Deutsch, gerne auch Englisch (Optional)"
# eaze join_com:16389102 (Berlin) — flip adicional (nativo!).
EAZE_VERBATIM = "Du sprichst Deutsch auf muttersprachlichem Niveau."
# CANAL+ sf 1373297557 (Luxembourg) — eixo francês (description @3603).
CANALPLUS_VERBATIM = (
    "Fluent in English (written and spoken) required; French strongly "
    "valued; additional European languages are a plus."
)
# Lidl BI ReqEng praktikum_info:13308116 — "Dein Profil" VERBATIM do JSON-LD
# da página viva (probe GET 19/10, UA internship-finder-diagnostic/1.0;
# description do dataset: 0 chars). Entidades HTML de propósito: o
# normalize_text do detector as decodifica (contrato do item 5).
LIDL_ENRICHED_VERBATIM = (
    "Dein Profil<br><ul><li>Studium* im Bereich "
    "Wirtschaftsiwssenschaften oder ein vergleichbarer Studiengang"
    "</li><li>Idealerweise Interesse an IT Themen sowie erste "
    "praktische Erfahrung mit BI Produkten</li><li>Sehr guter "
    "Umgang mit Google Sheets</li><li>Sehr gute "
    "Deutschkenntnisse</li></ul><p>\xa0</p><p>"
    "*Bitte füge deiner Bewerbung deinen aktuellen Notenspiegel hinzu."
    "</p><br>"
)
# KPMG sf 927796101 — citação do DONO (registro 10/2026; o requisito vive
# só no template JS-rendered do CSB: probe provou RSS = intro de 314
# chars, HTML do servidor = 422 chars de texto visível sem o posting).
KPMG_OWNER_QUOTE = "Sehr gute Deutschkenntnisse"

# Contra-casos ANTI-FALSO-POSITIVO (mandato da card: nenhuma vaga
# inglês-só pode virar excluída) — medidos no universo 736 ANTES/DEPOIS.
CONTRA_CASES = [
    # (texto, nível esperado — 'none' = GermanLevel None)
    ("English required, German is a plus", "preferred"),  # contrato F18 vivo
    ("Fluent in English (written and spoken) required; additional "
     "European languages are a plus.", "none"),
    ("You will work in an international team. English is our working "
     "language.", "none"),
    ("Wir bieten gut bezahlte Praktika. Bewirb dich jetzt!", "none"),
    ("Sehr gute Englischkenntnisse werden erwartet", "none"),
    ("Good communication skills in English required", "none"),
    ("Keine Deutschkenntnisse erforderlich", "plus"),  # negação -> neutro
    ("No German required for this position", "plus"),
]


# ---------------------------------------------------------------------------
# S1 — CLASSE A: detector no texto MOLEQLAR verbatim (+ flips medidos)
# ---------------------------------------------------------------------------
def s1_classe_a() -> None:
    gl = app_intel.german_level(MOLEQLAR_VERBATIM)
    check("A1 MOLEQLAR verbatim -> required (era plus/bare: passava no f-de)",
          gl is not None and gl.level == "required",
          f"got {gl.level if gl else None}/{gl.reason if gl else '-'}")
    check("A1 MOLEQLAR: o 'gut' BARE é o que qualifica ('sehr gut Deutsch')",
          gl is not None and gl.reason == "qual",
          f"reason={gl.reason if gl else '-'}")

    gv = app_intel.german_level(VODAFONE_VERBATIM)
    check("A2 Vodafone verbatim ('Du sprichst Deutsch, gerne auch Englisch "
          "(Optional)') -> required (verbo 2ª pessoa)",
          gv is not None and gv.level == "required" and gv.reason == "verb",
          f"got {gv.level if gv else None}/{gv.reason if gv else '-'}")

    ge = app_intel.german_level(EAZE_VERBATIM)
    check("A3 eaze verbatim ('Du sprichst Deutsch auf muttersprachlichem "
          "Niveau.') -> required",
          ge is not None and ge.level == "required",
          f"got {ge.level if ge else None}/{ge.reason if ge else '-'}")

    gd = app_intel.german_level("Sprichst du fließend Deutsch?")
    check("A4 ordem invertida 'Sprichst du ... Deutsch' -> required",
          gd is not None and gd.level == "required",
          f"got {gd.level if gd else None}")

    gu = app_intel.german_level("unser Team ist deutschsprachig")
    check("A5 janela REVERSA 'Team ... deutschsprachig' -> required",
          gu is not None and gu.level == "required" and gu.reason == "verb",
          f"got {gu.level if gu else None}/{gu.reason if gu else '-'}")

    ga = app_intel.german_level(
        "Unser Arbeitsalltag ist überwiegend deutschsprachig.")
    check("A6 advérbio 'überwiegend deutschsprachig' -> required",
          ga is not None and ga.level == "required",
          f"got {ga.level if ga else None}")


def s2_regras_preservadas() -> None:
    """Regras Fase 6/F18 que o fix NÃO pode quebrar."""
    gf = app_intel.german_level("Du arbeitest in einem deutschsprachigen Team")
    check("P1 forward 'deutschsprachiges Team' segue required (padrão original)",
          gf is not None and gf.level == "required",
          f"got {gf.level if gf else None}")

    gs = app_intel.german_level(
        "Wir suchen jemanden für unser deutschsprachiges Büro in Berlin")
    check("P2 'deutschsprachig' SOLTO (sem substantivo/advérbio da lista) "
          "segue plus — regra Fase 6 preservada",
          gs is not None and gs.level == "plus",
          f"got {gs.level if gs else None}")

    gk = app_intel.german_level("Sehr gute Deutschkenntnisse")
    check("P3 'Sehr gute Deutschkenntnisse' (flexão gutE) segue required "
          "— nenhuma regressão no caso original",
          gk is not None and gk.level == "required",
          f"got {gk.level if gk else None}")

    gn = app_intel.german_level("Du hast keine Deutschkenntnisse? "
                                "Kein Problem — Englisch reicht uns.")
    check("P4 negação na janela vence o novo pattern 'sprichst'/intensidade",
          gn is None or gn.level in ("plus", "preferred"),
          f"got {gn.level if gn else None}")

    gb = app_intel.german_level("Wir bieten ein gutes Praktikum in München")
    check("P5 'gutes Praktikum' NÃO qualifica língua (sem token de idioma "
          "na janela — docstring Fase 6)",
          gb is None,
          f"got {gb.level if gb else None}")


def s3_contra_casos() -> None:
    """Anti-FP: nenhuma vaga inglês-só pode virar excluída (required)."""
    for text, expected in CONTRA_CASES:
        gl = app_intel.german_level(text)
        got = gl.level if gl else "none"
        check(f"CC {expected:<9} <- {text[:58]!r}", got == expected,
              f"got {got}")


def s4_classe_b() -> None:
    """Texto enriquecido dos probes: detector (BASE e FIX) = required.

    A falha KPMG/Lidl é de COMPLETUDE (texto ausente do pipeline), não do
    detector — a prova é o mesmo veredito no texto enriquecido.
    """
    gl = app_intel.german_level(LIDL_ENRICHED_VERBATIM)
    check("B1 Lidl BI ReqEng ENRIQUECIDO (JSON-LD da página viva, verbatim) "
          "-> required/qual ('Sehr gute Deutschkenntnisse' presente no "
          "texto; dataset serve description VAZIA)",
          gl is not None and gl.level == "required" and gl.reason == "qual",
          f"got {gl.level if gl else None}/{gl.reason if gl else '-'}")

    gk = app_intel.german_level(KPMG_OWNER_QUOTE)
    check("B2 KPMG citação-do-dono ('Sehr gute Deutschkenntnisse', registro "
          "10/2026) -> required/qual (o texto existe só no template "
          "JS-rendered do CSB — probe: RSS = intro 314 chars)",
          gk is not None and gk.level == "required" and gk.reason == "qual",
          f"got {gk.level if gk else None}/{gk.reason if gk else '-'}")

    # A falha REPRODUZIDA como ela vive no dataset: description vazia.
    gl_empty = app_intel.german_level(
        "Praktikum Controlling International - BI Requirement Engineering")
    check("B3 REPRO da falha no dataset: só o título (description=0 chars) "
          "-> None — detector cego por COMPLETUDE, não por pattern",
          gl_empty is None,
          f"got {gl_empty.level if gl_empty else None}")

    gl_kpmg_ds = app_intel.german_level(
        "Praktikum Data Science / Data Analytics & BI (w/m/d) Begleite KPMG "
        "bei den zukünftigen Herausforderungen unserer Kund:innen.")
    check("B4 REPRO KPMG no dataset: intro de 310 chars (RSS verbatim) "
          "-> None — o requisito não está no feed",
          gl_kpmg_ds is None,
          f"got {gl_kpmg_ds.level if gl_kpmg_ds else None}")


def s5_classe_a2_frances() -> None:
    """Francês: SINAL com qualificadores; nunca exclusão."""
    fl = app_intel.french_level(CANALPLUS_VERBATIM)
    check("F1 CANAL+ verbatim -> preferred/soft ('French strongly valued'; "
          "o 'required' é do INGLÊS e fica do outro lado do ';')",
          fl is not None and fl.level == "preferred" and fl.reason == "soft",
          f"got {fl.level if fl else None}/{fl.reason if fl else '-'}")

    fr = app_intel.french_level("French required for this role")
    check("F2 'French required' -> required/verb_direct",
          fr is not None and fr.level == "required" and fr.reason == "verb_direct",
          f"got {fr.level if fr else None}/{fr.reason if fr else '-'}")

    fq = app_intel.french_level("Sie bringen gute Französischkenntnisse mit")
    check("F3 'gute Französischkenntnisse' -> required/qual",
          fq is not None and fq.level == "required" and fq.reason == "qual",
          f"got {fq.level if fq else None}/{fq.reason if fq else '-'}")

    fn = app_intel.french_level("No French required for this position")
    check("F4 negação 'No French required' -> plus (neutro)",
          fn is not None and fn.level == "plus",
          f"got {fn.level if fn else None}")

    fb = app_intel.french_level("We are a French company with offices in Paris")
    check("F5 menção nua 'French company' -> plus (menção difusa)",
          fb is not None and fb.level == "plus",
          f"got {fb.level if fb else None}")

    fz = app_intel.french_level("Java Python SQL team in Munich")
    check("F6 sem menção -> None", fz is None, f"got {fz.level if fz else None}")

    # guarda anti-vazamento: francês não toca o detector de alemão
    gde = app_intel.german_level(CANALPLUS_VERBATIM)
    check("F7 CANAL+ verbatim no detector de ALEMÃO -> None (francês não "
          "vaza; 'Germany' na description é país, word-bounded)",
          gde is None, f"got {gde.level if gde else None}")
    # ...e o 'required' do inglês não contamina o francês como required:
    check("F8 veredito CANAL+ NÃO é required (o 'required; French' tem "
          "ponto-e-vírgula — janela [\w\s,()-] não atravessa)",
          fl is not None and fl.level != "required",
          f"got {fl.level if fl else None}")


def s6_ranking() -> None:
    """O ranking consome german_level como ANTES; francês NÃO é lido."""
    check("R1 PENALTY_LANG_DE_REQUIRED segue -2.0",
          PENALTY_LANG_DE_REQUIRED == -2.0, f"got {PENALTY_LANG_DE_REQUIRED}")
    check("R2 PENALTY_LANG_DE_PREFERRED segue -0.5",
          PENALTY_LANG_DE_PREFERRED == -0.5, f"got {PENALTY_LANG_DE_PREFERRED}")
    lang_m = _language_score(MOLEQLAR_VERBATIM)
    check("R3 _language_score(MOLEQLAR) = -2.0 (alemão required, sem inglês)",
          lang_m == PENALTY_LANG_DE_REQUIRED, f"got {lang_m}")
    lang_c = _language_score(CANALPLUS_VERBATIM)
    check("R4 _language_score(CANAL+) = +1.5 (inglês; francês NÃO penaliza "
          "— SINAL, nunca exclusão)",
          lang_c == WEIGHT_LANG_EN, f"got {lang_c}")
    lang_fr = _language_score("French required for this client role")
    check("R5a francês required NÃO penaliza: score 0.0 (sem menção de "
          "alemão/inglês — francês fora do _language_score)",
          lang_fr == 0.0, f"got {lang_fr}")
    lang_mix = _language_score("French required. German is a plus.")
    check("R5b misto francês+alemão-soft: penalidade é a do ALEMÃO "
          "preferred (-0.5), nada do francês",
          lang_mix == PENALTY_LANG_DE_PREFERRED, f"got {lang_mix}")


def s7_render() -> None:
    """Página: data-fr + badge 🇫🇷 (sinal) — NENHUM filtro JS consome."""
    import minimal_page as mp  # noqa: E402

    base = {
        "id": "x", "source": "s", "title": "T", "company": "C",
        "location": "L", "country": "", "remote": False,
        "url": "https://example.com/j", "external_id": "x1",
        "score": 1.0, "score_breakdown": {}, "visa_friendly": False,
        "country_iso": "de", "description": "",
    }
    canal = dict(base, id="canal", country_iso="lu",
                 title="Procurement Intern",
                 description=CANALPLUS_VERBATIM)
    moleq = dict(base, id="moleq", description=MOLEQLAR_VERBATIM)
    plain = dict(base, id="plain", description="Java Python SQL team")
    html = mp.render_minimal_html(
        [canal, moleq, plain], total_eligible=3,
        generated_at="2026-10-19T04:00:00Z")

    check("V1 data-fr='preferred' no card CANAL+",
          'data-fr="preferred"' in html)
    check("V2 data-fr='none' nos cards sem menção",
          'data-fr="none"' in html)
    check("V3 badge 🇫🇷 presente (sinal francês)",
          'class="fr"' in html and "🇫🇷" in html)
    check("V4 MOLEQLAR: data-de='required' + badge 🇩🇪 (contrato F11 vivo)",
          'data-de="required"' in html and "🇩🇪" in html)
    n_badges = html.count('class="fr"')
    check("V5 card SEM menção não ganha badge 🇫🇷 (só 1 badge; as outras "
          "ocorrências do emoji são a legenda pt/en)",
          n_badges == 1, f"badges={n_badges}")
    check("V6 legenda explica o sinal ('francês (sinal)')",
          "francês (sinal)" in html and "never an exclusion" in html)
    # NUNCA exclusão: nenhum bloco JS lê data-fr
    for js_name in ("_JS", "_JS_PROFILE_TPL", "_JS_LAZY_CORE", "_JS_LAZY_IO"):
        js_src = getattr(mp, js_name, "")
        check(f"V7 {js_name} NÃO consome data-fr (francês nunca filtra)",
              "data-fr" not in js_src, f"len={len(js_src)}")


def s8_universo_mini_ab() -> None:
    """A/B em mini-universo embutido: critério anti-FP como invariante.

    Espelha a medição real F60 (736 vagas): ANTES 0 required / DEPOIS 4
    (MOLEQLAR, Vodafone×2, eaze — todos com evidência 'sprichst'/'gut'
    citada); 0 flips para baixo; 0 contra-casos viram required.
    """
    universe = [
        ("MOLEQLAR-like", MOLEQLAR_VERBATIM, "required"),
        ("Vodafone-like", VODAFONE_VERBATIM, "required"),
        ("eaze-like", EAZE_VERBATIM, "required"),
        ("English-only 1", "English required working language team", "none"),
        ("English-only 2", "Data engineering with Python and SQL", "none"),
        ("German-soft", "Deutschkenntnisse sind von Vorteil", "preferred"),
    ]
    req = [name for name, text, exp in universe
           if (gl := app_intel.german_level(text)) and gl.level == "required"]
    check("U1 mini-universo: EXATAMENTE os 3 casos 'sprichst/gut' viram "
          "required (nenhum inglês-só)", len(req) == 3 and
          set(req) == {"MOLEQLAR-like", "Vodafone-like", "eaze-like"},
          f"required={req}")
    levels_ok = all(
        ((gl := app_intel.german_level(text)) is None and exp == "none")
        or (gl is not None and gl.level == exp)
        for _, text, exp in universe)
    check("U2 mini-universo: níveis finais exatos por vaga (contrato "
          "completo, incl. soft 'von Vorteil' -> preferred)", levels_ok)
    check("U3 test_f60 na suíte descoberta do CI (F78 — mesma suíte que o CI roda)",
          "test_f60" in ci_discover_tests.discover_tests())


def main() -> int:
    s1_classe_a()
    s2_regras_preservadas()
    s3_contra_casos()
    s4_classe_b()
    s5_classe_a2_frances()
    s6_ranking()
    s7_render()
    s8_universo_mini_ab()
    fails = [c for c in CHECKS if not c[1]]
    print(f"F60: {len(CHECKS) - len(fails)} OK, {len(fails)} FAIL")
    for name, _, detail in fails:
        print(f"  FAIL: {name} {detail}")
    print("TUDO OK" if not fails else "HÁ FALHAS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
