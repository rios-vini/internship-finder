#!/usr/bin/env python3
"""F85 — Corpus de idioma v2 (test_f85).

F85 fecha os QUALIFICADORES que escapavam do corpus de idioma (registro de
recusas do dono 20/10 — RECUSAS-FEEDBACK-PIPELINE-2026-10.md, 6 vagas
IDIOMA-DE/FR que chegaram à triagem manual com score alto).

PASSO 0 MEDIDO (20/10, universo 108.173 jobs, eligible 725 — 1.879 vagas
com as frases verbatim do registro): ZERO escapes de PADRÃO no eligible —
todas as ``required`` já eram excluídas. Os escapes reais do registro foram
de DADOS/FONTE, não de cobertura (KPMG 310 chars sem a frase; Lidl ReqEng e
Daimler com description VAZIA; SocGen 26000M0G nem coletada; CANAL+
classificado preferred/soft corretamente pelo texto real "French strongly
valued"). Este teste trava o corpus contra os snippets VERBATIM do registro
E estende a cobertura para o drift medido:

- DE: ``native``/``bilingual`` grudados à menção (Native German / Bilingual
  German) — no glued F18 (precedência: vence soft solto na janela larga) e
  no qual de janela ±45; ``sicher(e)``/``verhandlungssicher``/``fluent``/
  ``advanced`` JÁ cobertos (F18/F60) — regressão travada aqui.
- FR: pós-nominal ``français courant``/``français couramment``/``bilingue``
  (26 vagas reais no universo, forma DOMINANTE — o qual-antes não via) e
  qual-antes ``courant/couramment/bilingue/bilingual/francophone/native``
  ("bilingual fluency in English and French", "Maîtrise courante du
  français"); ``excellente maîtrise du français`` já cobria via
  ``excellente``+gap — travado.
- SOFT DEPOIS da menção FR (_FRENCH_SOFT_AFTER_RE, espelho F18 do DE):
  "French strongly valued" (CANAL+ verbatim) segue preferred/soft — NUNCA
  required; FR é SINAL (F60), nunca exclusão.

Regra de severidade INTOCADA (dono): >=B2/sicher/fluent exclui via
``german_required`` (F37.3); básico/``von Vorteil`` NÃO exclui
(counter-cases: Würth 13251590 twin absolventa com alemão não exigido,
"Deutschkenntnisse von Vorteil", "Grundkenntnisse", basic A1-A2). Score e
pesos intocados (elegibilidade > tuning).

100% OFFLINE: fixtures verbatim + drift simulado — zero rede, data/ intocada.
Padrão da suíte: [OK]/[FAIL], lista COMPLETA de violadores no fim.

Uso: .venv/bin/python scripts/test_f85.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.app_intel import french_level, german_level  # noqa: E402
from internship_finder.filters import applicability_exclusion_reason  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" ({detail})" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def gl_req(text: str) -> bool:
    """german_level == required (excluiria via F37.3)."""
    lv = german_level(text)
    return lv is not None and lv.level == "required"


def gl_of(text: str) -> str:
    lv = german_level(text)
    return lv.level if lv else "none"


def fl_of(text: str) -> str:
    lv = french_level(text)
    return lv.level if lv else "none"


def excl_reason(text: str) -> str | None:
    return applicability_exclusion_reason({"title": "", "description": text})


# ---------------------------------------------------------------------------
# A. As 6 fixtures verbatim do registro (RECUSAS-FEEDBACK-PIPELINE-2026-10)
# ---------------------------------------------------------------------------

# Texto REAL coletado (MOLEQLAR absolventa 13258677, desc 4094 chars,
# trecho verbatim do dataset — caso já coberto pela F60; regressão).
MOLEQLAR_VERBATIM = (
    "Du experimentierst mit neuen Tools in dem Moment, in dem sie "
    "rauskommen. Du sprichst sehr gut Deutsch, da unser Arbeitsalltag "
    "hauptsächlich deutschsprachig ist. Warum wir?"
)
# Texto REAL coletado (CANAL+ SF 1373297557, desc 3668 chars, trecho final
# verbatim do dataset — a frase que o dono leu como "francês exigido").
CANAL_VERBATIM = (
    "Interest in the media and entertainment industry. Advanced "
    "proficiency in Excel and Microsoft Office tools. Fluent in English "
    "(written and spoken) required; French strongly valued; additional "
    "European languages are a plus."
)

# Snippets VERBATIM do registro do dono (frases que ele leu nas páginas).
# Nota do Passo 0: para KPMG/Lidl/Daimler a frase NÃO chega ao texto
# coletado hoje (descrição vazia/trincada) — o detector é testado no
# snippet porque é isso que o corpus deve pegar QUANDO o texto chega
# (hidratação futura); o gap de DADOS é outra fase, não do corpus.
KPMG_VERBATIM = "Praktikum Data Science & BI. Voraussetzung: Sehr gute Deutschkenntnisse (C1)."
LIDL_VERBATIM = "Praktikum Controlling International - BI Requirement Engineering. Sehr gute Deutschkenntnisse runden dein Profil ab."
DAIMLER_VERBATIM = "Praktikum im Bereich Einkauf. Du bringst Sichere Deutsch- und Englischkenntnisse mit."
SOCGEN_VERBATIM = (
    "Trainee Junior PM - Global Markets. Profile: Advanced French and "
    "English. Start: November/December 2026."
)


def test_a_fixtures_verbatim() -> None:
    print("== A. 6 fixtures verbatim do registro (o que falhava pega; o que passava segue) ==")
    check("A1. KPMG 'Sehr gute Deutschkenntnisse' (C1) -> required",
          gl_req(KPMG_VERBATIM), gl_of(KPMG_VERBATIM))
    check("A2. MOLEQLAR texto real 'Du sprichst sehr gut Deutsch' -> required (F60 regressão)",
          gl_req(MOLEQLAR_VERBATIM), gl_of(MOLEQLAR_VERBATIM))
    check("A3. Lidl ReqEng 'Sehr gute Deutschkenntnisse' -> required",
          gl_req(LIDL_VERBATIM), gl_of(LIDL_VERBATIM))
    check("A4. Daimler 'Sichere Deutsch- und Englischkenntnisse' -> required",
          gl_req(DAIMLER_VERBATIM), gl_of(DAIMLER_VERBATIM))
    check("A5. SocGen 'Advanced French and English' -> french required (SINAL)",
          fl_of(SOCGEN_VERBATIM) == "required", fl_of(SOCGEN_VERBATIM))
    check("A5b. SocGen german continua None (não há menção de alemão)",
          gl_of(SOCGEN_VERBATIM) == "none", gl_of(SOCGEN_VERBATIM))
    check("A6. CANAL+ texto real -> french preferred (soft; 'strongly valued' NUNCA required)",
          fl_of(CANAL_VERBATIM) == "preferred", fl_of(CANAL_VERBATIM))
    check("A6b. CANAL+ german continua None (inglês fluente não é alemão)",
          gl_of(CANAL_VERBATIM) == "none", gl_of(CANAL_VERBATIM))


def test_a2_integracao_exclusao() -> None:
    print("== A2. Integração com a exclusão F37.3 (applicability_exclusion_reason) ==")
    check("A2.1. Daimler verbatim -> motivo german_required",
          excl_reason(DAIMLER_VERBATIM) == "german_required", str(excl_reason(DAIMLER_VERBATIM)))
    check("A2.2. KPMG verbatim -> motivo german_required",
          excl_reason(KPMG_VERBATIM) == "german_required", str(excl_reason(KPMG_VERBATIM)))
    check("A2.3. MOLEQLAR verbatim -> motivo german_required",
          excl_reason(MOLEQLAR_VERBATIM) == "german_required", str(excl_reason(MOLEQLAR_VERBATIM)))
    check("A2.4. CANAL+ NUNCA exclui por idioma (FR é sinal F60)",
          excl_reason(CANAL_VERBATIM) != "german_required", str(excl_reason(CANAL_VERBATIM)))
    check("A2.5. SocGen NUNCA exclui por idioma (FR é sinal F60)",
          excl_reason(SOCGEN_VERBATIM) != "german_required", str(excl_reason(SOCGEN_VERBATIM)))


# ---------------------------------------------------------------------------
# B. Corpus v2 DE — native/bilingual (novos) + regressão F18/F60
# ---------------------------------------------------------------------------

def test_b_corpus_de() -> None:
    print("== B. Corpus v2 DE: native/bilingual + regressão dos existentes ==")
    # Novos (F85)
    check("B1. 'Native German' -> required",
          gl_req("You are a Native German speaker and communicate clearly."),
          gl_of("You are a Native German speaker and communicate clearly."))
    check("B2. 'Native German skills' (glued, gap médio) -> required",
          gl_req("Ideal: Native German skills for stakeholder work."),
          gl_of("Ideal: Native German skills for stakeholder work."))
    check("B3. 'Bilingual German-English team' (glued, parêntese no gap) -> required",
          gl_req("We are a Bilingual German-English team."),
          gl_of("We are a Bilingual German-English team."))
    check("B4. 'bilingual German' minúsculo -> required (case-insensitive)",
          gl_req("you should have bilingual German skills"),
          gl_of("you should have bilingual German skills"))
    check("B5. 'NATIVE GERMAN' caixa alta -> required",
          gl_req("REQUIREMENTS: NATIVE GERMAN KNOWLEDGE."),
          gl_of("REQUIREMENTS: NATIVE GERMAN KNOWLEDGE."))
    check("B6. 'native German' sobrevive a soft solto na janela larga (precedência F18)",
          gl_req("Native German is expected. Power Platform knowledge is a plus."),
          gl_of("Native German is expected. Power Platform knowledge is a plus."))
    # Regressão F18/F60 — o que já passava CONTINUA passando
    check("B7. regressão: 'Sehr gute Deutschkenntnisse' -> required",
          gl_req("Sehr gute Deutschkenntnisse setzen wir voraus."),
          gl_of("Sehr gute Deutschkenntnisse setzen wir voraus."))
    check("B8. regressão: 'Verhandlungssichere Deutschkenntnisse' -> required",
          gl_req("Verhandlungssichere Deutschkenntnisse (C1) erforderlich."),
          gl_of("Verhandlungssichere Deutschkenntnisse (C1) erforderlich."))
    check("B9. regressão: 'Fließend in Deutsch & Englisch' -> required (STIHL)",
          gl_req("Du bist Fließend in Deutsch & Englisch."),
          gl_of("Du bist Fließend in Deutsch & Englisch."))
    check("B10. regressão: 'Du sprichst sehr gut Deutsch' -> required (MOLEQLAR)",
          gl_req("Du sprichst sehr gut Deutsch."),
          gl_of("Du sprichst sehr gut Deutsch."))
    check("B11. regressão: 'sicher(e)' no glued (Daimler flexões) -> required",
          gl_req("Sicheres Deutsch in Wort und Schrift."),
          gl_of("Sicheres Deutsch in Wort und Schrift."))


# ---------------------------------------------------------------------------
# C. Corpus v2 FR — courant/bilingue/bilingual/francophone (novos)
# ---------------------------------------------------------------------------

def test_c_corpus_fr() -> None:
    print("== C. Corpus v2 FR: pós-nominal courant/bilingue + qual-antes ==")
    # Pós-nominal (26 vagas reais no universo 20/10 — forma dominante)
    check("C1. 'français courant' (pós-nominal) -> required",
          fl_of("Excellente connaissance d'Office. Un français courant est nécessaire.") == "required",
          fl_of("Un français courant est nécessaire."))
    check("C2. 'Un français et un anglais courants' -> required (real ALO/Allianz)",
          fl_of("Trois ans d'expérience en assurance-crédit, ainsi qu'un français et un anglais courants.") == "required",
          fl_of("ainsi qu'un français et un anglais courants."))
    check("C3. 'Un français et anglais courant' -> required (real Bayer)",
          fl_of("Une bonne maîtrise d'Excel et des bases de données. Un français et anglais courant.") == "required",
          fl_of("Un français et anglais courant."))
    check("C4. 'français bilingue' pós-nominal -> required",
          fl_of("Vous maîtrisez le français bilingue.") == "required",
          fl_of("Vous maîtrisez le français bilingue."))
    check("C5. 'parler couramment le français' -> required",
          fl_of("Vous parlez couramment le français.") == "required",
          fl_of("Vous parlez couramment le français."))
    check("C6. 'FRANÇAIS COURANT' caixa alta -> required (case-insensitive)",
          fl_of("LANGUES: FRANÇAIS COURANT ET ANGLAIS.") == "required",
          fl_of("LANGUES: FRANÇAIS COURANT ET ANGLAIS."))
    # Qual-antes (F85)
    check("C7. 'bilingual fluency in English and French' -> required (real ABB)",
          fl_of("Ideal for B2B communications professionals with bilingual fluency in English and French.") == "required",
          fl_of("with bilingual fluency in English and French."))
    check("C8. 'bilingue français/néerlandais' -> required (real rexel)",
          fl_of("Nous recherchons un(e) stagiaire motivé(e), bilingue français/néerlandais.") == "required",
          fl_of("bilingue français/néerlandais."))
    check("C9. 'Maîtrise courante du français' -> required (real Liebherr)",
          fl_of("Maîtrise courante du français et de l'anglais.") == "required",
          fl_of("Maîtrise courante du français et de l'anglais."))
    check("C10. 'francophone ... French' -> required",
          fl_of("You will join a francophone team; fluent French is expected.") == "required",
          fl_of("You will join a francophone team; fluent French is expected."))
    check("C11. regressão: 'Advanced French and English' -> required (SocGen)",
          fl_of("Profile: Advanced French and English.") == "required",
          fl_of("Profile: Advanced French and English."))
    check("C12. regressão: 'excellente maîtrise du français' -> required (gap médio)",
          fl_of("Vous justifiez d'une excellente maîtrise du français.") == "required",
          fl_of("Vous justifiez d'une excellente maîtrise du français."))
    check("C13. regressão: 'fluent French' -> required",
          fl_of("Fluent French required for supplier negotiations.") == "required",
          fl_of("Fluent French required for supplier negotiations."))


# ---------------------------------------------------------------------------
# D. Counter-cases do dono — NÃO excluem (severidade mantida)
# ---------------------------------------------------------------------------

def test_d_counter_cases() -> None:
    print("== D. Counter-cases: von Vorteil / básico / Würth NÃO excluem ==")
    check("D1. 'Deutschkenntnisse von Vorteil' -> preferred (NÃO required)",
          gl_of("Deutschkenntnisse von Vorteil.") == "preferred",
          gl_of("Deutschkenntnisse von Vorteil."))
    check("D1b. ...e a exclusão F37.3 NÃO dispara",
          excl_reason("Deutschkenntnisse von Vorteil.") != "german_required",
          str(excl_reason("Deutschkenntnisse von Vorteil.")))
    check("D2. 'Sehr gute Deutschkenntnisse sind von Vorteil' -> preferred "
          "(soft anexado vence intensidade — caso Allianz 107297 real)",
          gl_of("Sehr gute Deutschkenntnisse sind von Vorteil.") == "preferred",
          gl_of("Sehr gute Deutschkenntnisse sind von Vorteil."))
    check("D3. 'Grundkenntnisse in Deutsch' -> preferred (básico NÃO exclui)",
          gl_of("Grundkenntnisse in Deutsch sind hilfreich.") == "preferred",
          gl_of("Grundkenntnisse in Deutsch sind hilfreich."))
    check("D4. 'basic German (A1/A2)' -> preferred (NÃO exclui)",
          gl_of("Basic German (A1/A2) is sufficient; we work in English.") == "preferred",
          gl_of("Basic German (A1/A2) is sufficient; we work in English."))
    check("D5. Würth twin real (absolventa 13251590): título sem menção + desc vazia -> none",
          german_level("Praktikant (m/w/d) im Bereich Logistik - Import Beschaffung") is None,
          str(german_level("Praktikant (m/w/d) im Bereich Logistik - Import Beschaffung")))
    check("D6. negação explícita vence: 'no German required' -> plus (NÃO exclui)",
          gl_of("No German required, international team.") == "plus",
          gl_of("No German required, international team."))
    check("D6b. ...e a exclusão não dispara",
          excl_reason("No German required, international team.") != "german_required",
          str(excl_reason("No German required, international team.")))
    # Counter-case FR: soft DEPOIS nunca escala a required
    check("D7. 'French a plus' (soft grudado depois) -> preferred",
          fl_of("Fluency in French a plus for this role.") == "preferred",
          fl_of("Fluency in French a plus for this role."))
    check("D8. 'français courant est un plus' -> preferred (soft anexado vence intensidade)",
          fl_of("Un français courant est un plus.") == "preferred",
          fl_of("Un français courant est un plus."))


# ---------------------------------------------------------------------------
# E. Controles negativos (FP-guards) — cada padrão novo sem menção não sinaliza
# ---------------------------------------------------------------------------

def test_e_controles_negativos() -> None:
    print("== E. Controles negativos: padrões novos sem menção não criam sinal ==")
    check("E1. 'bilingual team' sem menção de idioma -> german none",
          gl_of("We are a bilingual team in a dynamic environment.") == "none",
          gl_of("We are a bilingual team in a dynamic environment."))
    check("E2. 'Native English speaker' sem menção de alemão -> german none",
          gl_of("You are a native English speaker with strong communication skills.") == "none",
          gl_of("You are a native English speaker with strong communication skills."))
    check("E3. 'Headquarters in Germany' -> german none (país não é idioma)",
          gl_of("Headquartered in Munich, Germany, Celonis operates globally.") == "none",
          gl_of("Headquartered in Munich, Germany, Celonis operates globally."))
    check("E4. 'French strongly valued' (CANAL+ verbatim) -> preferred, NUNCA required",
          fl_of("Fluent in English (written and spoken) required; French strongly valued.") == "preferred",
          fl_of("Fluent in English (written and spoken) required; French strongly valued."))
    check("E5. 'French course/lessons' não é intensidade (courant\\w* não casa 'course')",
          fl_of("Our Lyon office offers a French course for newcomers.") != "required",
          fl_of("Our Lyon office offers a French course for newcomers."))
    check("E6. 'required; French' do outro lado do ponto-e-vírgula não vaza no FR (CANAL+ guard)",
          fl_of("Fluent in English required; French knowledge helpful.") != "required",
          fl_of("Fluent in English required; French knowledge helpful."))
    check("E7. 'Frenchmen/France' word-boundary não criam token",
          fl_of("Working with France Telecom and Frenchmen abroad.") == "none",
          fl_of("Working with France Telecom and Frenchmen abroad."))
    check("E8. menção nua de francês (CANAL+ fundação) fica plus",
          fl_of("Founded as a French subscription-TV channel 40 years ago.") == "plus",
          fl_of("Founded as a French subscription-TV channel 40 years ago."))
    check("E9. 'bilingual' DE não rebaixa negação: 'keine Deutschkenntnisse nötig' -> plus",
          gl_of("Bilingual team, keine Deutschkenntnisse nötig.") == "plus",
          gl_of("Bilingual team, keine Deutschkenntnisse nötig."))
    check("E10. soft DEPOIS da menção DE segue vencendo (F18 regressão): 'German being a big plus'",
          gl_of("Fluent English with German being a big plus.") == "preferred",
          gl_of("Fluent English with German being a big plus."))


def test_f_ci_membership() -> None:
    print("== F. CI: test_f85 na suite descoberta (auto-discovery F78) ==")
    import ci_discover_tests  # noqa: F401
    names = ci_discover_tests.discover_tests()
    check("F1. suite descoberta do CI inclui test_f85",
          "test_f85" in names, f"{len(names)} suites")
    check("F2. README carrega '126' CI test suites (contrato F73 — bump "
          "da fase; F90 adicionou a test_f90, 125 -> 126)",
          "**126** | CI test suites" in (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8"),
          "README.md sem o bump 125->126")


def main() -> int:
    test_a_fixtures_verbatim()
    print()
    test_a2_integracao_exclusao()
    print()
    test_b_corpus_de()
    print()
    test_c_corpus_fr()
    print()
    test_d_counter_cases()
    print()
    test_e_controles_negativos()
    print()
    test_f_ci_membership()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
