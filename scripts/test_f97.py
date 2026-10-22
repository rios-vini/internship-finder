#!/usr/bin/env python3
"""F97 — jd-similarity: reuse | reuse_with_edits | regenerate (offline).

ITEM 10 da delegação: antes de reusar carta/CV entre vagas do MESMO
empregador, comparar os JDs. Fixtures = os 5 pacotes Lidl simultâneos do
REGISTRO-AVALIACOES-VAGAS-2026-10.md (lotes 13–18/10): SAP BI, Projete,
Int BI, Lieferantenentwicklung, Preismanagement — mesmo empregador
("lidlstiftup2" no SF / "Lidl Stiftung & Co. KG" no praktikum.info),
JDs irmãos com template compartilhado (~70% dos tokens).

PROVENANCE dos fixtures (``fixtures/f97/``, verbatim):
- ``lidl_sap_bi.txt`` / ``lidl_projete.txt``: description do dataset SF
  (archive 20261015T090002Z do eligible_jobs.json de produção), ids
  ``lidlstiftup2|sf_dataset:successfactors:1436050633`` (Ref 747147,
  "ab sofort" — lote 13/10) e ``...1426446133`` (Ref 735605, re-post —
  ITEM 7).
- ``lidl_int_bi.txt`` / ``lidl_lieferantenentwicklung.txt`` /
  ``lidl_preismanagement.txt``: praktikum.info 13308134 / 13308139 /
  13355221 — description AUSENTE no dataset (praktikum_info não embute
  texto), JD coletado ao vivo 22/10/2026 do JSON-LD JobPosting das
  páginas (datePosted 15–17/10, validThrough 02–12/07-12).

A escala medida no Passo 0 (grid run_min 4–8 × genre × stem no relatório
da fase; escolha: r6, sem stemming, sem stoplist de gênero — maior gap
estável trio×cross, +0.023, imune a perturbação de 1 frase editada):

  trio Controlling International: J_resto 0.188–0.233 => reuse_with_edits
  sap_bi × preismanagement:       J_resto 0.165 => regenerate (spec: divergem)
  demais pares cross:             J_resto 0.085–0.154 => regenerate
  coverage: template 0.66–0.73 | quase-idêntico 0.997 | idêntico 1.000
  limiares: reuse coverage>=0.90; edits J>=0.176 (média do gap 0.165|0.188)

Grupos (todos offline, zero rede, zero data/ de produção — CLI roda em
tmpdir com cwd arbitrário):
1. funções puras (tokens, jaccard, runs, veredito, tópicos, aliases);
2. fixtures Lidl ×5 — 10 pares: vereditos + J medidos congelados (±0.002);
3. controles: idêntico => reuse; quase-idêntico (1 frase editada,
   simulando re-post) => reuse; domínios distintos => regenerate+tópicos;
4. CLI: exit codes (sinal NUNCA é gate: regenerate => rc 0), --job-id
   (exato/substring único/não-achado/ambíguo), --json, JD sem texto
   (excluído com aviso; 2 JDs => erro), mesmo-empregador via alias F66
   (lidlstiftup2 ≡ Lidl Stiftung & Co. KG, sem aviso falso) × aviso
   cross-employer, determinismo (2 runs idênticos), fonte sem rede.

Uso:  python3 scripts/test_f97.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import jd_similarity as js  # noqa: E402

FIXTURES = ROOT / "fixtures" / "f97"
REAL_ALIASES = ROOT / "config" / "dedup_company_aliases.json"

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    mark = "[OK]" if cond else "[FAIL]"
    print(f"{mark} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# 1. Funções puras
# ---------------------------------------------------------------------------


def test_pure() -> None:
    print("1. funções puras")
    # raw_tokens: lowercase, ß→ss, split em não-alfanuméricos
    toks = js.raw_tokens("Power-BI 1.300 Fuß Ärzte")
    check("1a. raw_tokens: lowercase+ß→ss+split", toks == ["power", "bi", "1", "300", "fuss", "ärzte"], f"{toks}")
    # content_tokens: len>=2, sem dígitos puros, sem stopwords; "bi" sobrevive
    cont = js.content_tokens(["power", "bi", "1", "300", "der", "und", "x", "reporting"])
    check("1b. content_tokens: filtra stopwords/dígitos/curtos; mantém 'bi'",
          cont == ["power", "bi", "reporting"], f"{cont}")
    # jaccard: convenções
    check("1c. jaccard: ambos vazios => 1.0", js.jaccard([], []) == 1.0)
    check("1c. jaccard: disjuntos => 0.0", js.jaccard(["a"], ["b"]) == 0.0)
    check("1c. jaccard: {a,b}×{b,c} => 1/3", abs(js.jaccard(["a", "b"], ["b", "c"]) - 1 / 3) < 1e-9)
    # strip_common_runs: idêntico cobre tudo
    seq = "einleitung wir bieten ihnen qualität zum guten preis weltweit".split()
    ra, rb, cov = js.strip_common_runs(seq, seq[:])
    check("1d. runs: idênticos => resto vazio, coverage 1.0",
          not ra and not rb and cov == 1.0)
    # run menor que run_min NÃO é boilerplate (conteúdo genuíno sobrevive)
    shared = "unterstützung bei der erstellung von".split()  # 5 tokens
    ra, rb, cov = js.strip_common_runs(shared + ["a"], shared + ["b"])
    check("1d. runs: frase de 5 tokens (< run_min=6) NÃO é stripada",
          cov == 0.0 and "unterstützung" in ra and "unterstützung" in rb)
    ra, rb, cov = js.strip_common_runs(shared + ["a"], shared + ["b"], run_min=4)
    check("1d. runs: run_min=4 stripa a mesma frase (knob de calibração)",
          abs(cov - 5 / 6) < 1e-9 and ra == ["a"] and rb == ["b"],
          f"cov={cov} ra={ra} rb={rb}")
    # veredito: fronteiras medidas
    check("1e. verdict: coverage 0.90 => reuse", js.verdict(0.90, 0.0)[0] == js.REUSE)
    check("1e. verdict: coverage 0.899 (template, não conteúdo) => NÃO reuse",
          js.verdict(0.899, 0.0)[0] == js.REGENERATE)
    check("1e. verdict: J 0.176 (exato no limiar) => reuse_with_edits borderline",
          js.verdict(0.5, 0.176) == (js.REUSE_WITH_EDITS, True))
    check("1e. verdict: J 0.20 => reuse_with_edits, não borderline",
          js.verdict(0.5, 0.20) == (js.REUSE_WITH_EDITS, False))
    check("1e. verdict: J 0.161 => regenerate borderline (banda 0.015)",
          js.verdict(0.5, 0.161) == (js.REGENERATE, True))
    check("1e. verdict: J 0.10 => regenerate, sem borderline",
          js.verdict(0.5, 0.10) == (js.REGENERATE, False))
    # tópicos: ranking tf desc → 1ª posição; filtro de apresentação
    cand = ["b", "b", "a", "c", "du", "bereich"] + ["d"] * 3
    topics = js.distinctive_topics(cand, ["a"])
    check("1f. topics: tf desc + stopwords de apresentação fora",
          topics == ["d", "b", "c"], f"{topics}")
    check("1f. topics: limit respeitado", len(js.distinctive_topics(cand, [], 2)) == 2)
    # aliases F66 fail-closed + identidade
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.json"
        bad.write_text("{ not json", encoding="utf-8")
        check("1g. aliases: arquivo corrompido => {} (fail-closed)",
              js.load_company_aliases(bad) == {})
        good = Path(tmp) / "good.json"
        good.write_text(json.dumps({"aliases": {"lidlstiftup2": "Lidl Stiftung & Co. KG", "x": "x"}}), encoding="utf-8")
        al = js.load_company_aliases(good)
        check("1g. aliases: mapa válido carrega; auto-alias descartado",
              al == {"lidlstiftup2": "Lidl Stiftung & Co. KG"}, f"{al}")
        check("1g. mesmo-empregador via alias: lidlstiftup2 ≡ Lidl Stiftung & Co. KG",
              js.same_employer("lidlstiftup2", "Lidl Stiftung & Co. KG", al) is True)
        check("1g. empregadores distintos => False",
              js.same_employer("Bosch GmbH", "Lidl Stiftung & Co. KG", al) is False)
        check("1g. empresa desconhecida (jd-file) => None, nunca aviso falso",
              js.same_employer(None, "Lidl Stiftung & Co. KG", al) is None)


# ---------------------------------------------------------------------------
# 2. Fixtures Lidl ×5 — a matriz medida
# ---------------------------------------------------------------------------

# (labels do par) -> (J_resto medido no Passo 0, veredito esperado, borderline)
MEASURED = {
    frozenset({"lidl_sap_bi", "lidl_projete"}): (0.1882, "reuse_with_edits", True),
    frozenset({"lidl_sap_bi", "lidl_int_bi"}): (0.1957, "reuse_with_edits", False),
    frozenset({"lidl_projete", "lidl_int_bi"}): (0.2333, "reuse_with_edits", False),
    frozenset({"lidl_sap_bi", "lidl_preismanagement"}): (0.1648, "regenerate", True),
    frozenset({"lidl_projete", "lidl_preismanagement"}): (0.1538, "regenerate", False),
    frozenset({"lidl_int_bi", "lidl_preismanagement"}): (0.1461, "regenerate", False),
    frozenset({"lidl_sap_bi", "lidl_lieferantenentwicklung"}): (0.1026, "regenerate", False),
    frozenset({"lidl_projete", "lidl_lieferantenentwicklung"}): (0.0847, "regenerate", False),
    frozenset({"lidl_int_bi", "lidl_lieferantenentwicklung"}): (0.1204, "regenerate", False),
    frozenset({"lidl_lieferantenentwicklung", "lidl_preismanagement"}): (0.1165, "regenerate", False),
}

FILES = [
    "lidl_sap_bi.txt",
    "lidl_projete.txt",
    "lidl_int_bi.txt",
    "lidl_lieferantenentwicklung.txt",
    "lidl_preismanagement.txt",
]


def _docs_from_fixtures() -> list[js.JdDoc]:
    docs = []
    for fname in sorted(FILES):
        text = (FIXTURES / fname).read_text(encoding="utf-8").strip()
        doc = js.JdDoc(label=Path(fname).stem, company=None,
                       title=text.splitlines()[0], text=text)
        doc.raw = js.raw_tokens(doc.text)
        doc.content = js.content_tokens(doc.raw)
        docs.append(doc)
    return docs


def test_fixtures() -> None:
    print("2. fixtures Lidl ×5 (5 pacotes simultâneos do registro)")
    for fname in FILES:
        check(f"2a. fixture presente: {fname}", (FIXTURES / fname).is_file())
    docs = _docs_from_fixtures()
    check("2a. 5 JDs carregados", len(docs) == 5)
    pairs = js.compare_all(docs, {}, 8)
    check("2a. 10 pares", len(pairs) == 10, f"{len(pairs)}")
    by_pair = {frozenset((p["a"], p["b"])): p for p in pairs}
    for key, (j_exp, verdict_exp, bord_exp) in sorted(MEASURED.items(), key=lambda kv: sorted(kv[0])[0]):
        p = by_pair[key]
        label = " × ".join(sorted(key))
        check(f"2b. {label}: {verdict_exp}", p["verdict"] == verdict_exp,
              f"J={p['jaccard_rest']} esperado~{j_exp}")
        check(f"2c. {label}: J={p['jaccard_rest']:.4f} == medido {j_exp}",
              abs(p["jaccard_rest"] - j_exp) <= 0.002)
        check(f"2d. {label}: borderline={bord_exp}", p["borderline"] == bord_exp)
    # coverage: template compartilhado, longe do reuse (0.90)
    covs = [p["coverage"] for p in pairs]
    check("2e. coverage dos irmãos Lidl: 0.60–0.75 (template; folga vs 0.90)",
          all(0.60 <= c <= 0.75 for c in covs), f"{[round(c, 3) for c in covs]}")
    # resumo da matriz: 3 edits (trio Controlling International) + 7 regenerate
    counts: dict[str, int] = {}
    for p in pairs:
        counts[p["verdict"]] = counts.get(p["verdict"], 0) + 1
    check("2f. resumo: 3× reuse_with_edits + 7× regenerate",
          counts == {"reuse_with_edits": 3, "regenerate": 7}, f"{counts}")
    # spec: SAP BI × Preismanagement DIVERGEM (regenerate) e a carta precisa
    # citar o time/produto específico — "Pricing Non Food" ≠ "SAP BI Reporting"
    p = by_pair[frozenset({"lidl_sap_bi", "lidl_preismanagement"})]
    preis_topics = p["topics_for_b"] if p["b"] == "lidl_preismanagement" else p["topics_for_a"]
    sap_topics = p["topics_for_b"] if p["b"] == "lidl_sap_bi" else p["topics_for_a"]
    check("2g. regenerate LISTA tópicos do novo JD (pricing/nonfood family)",
          {"pricing", "non", "food"} <= set(preis_topics), f"{preis_topics}")
    check("2g. tópicos exclusivos do JD de referência (sap/bi family)",
          {"sap", "bi"} <= set(sap_topics), f"{sap_topics}")


# ---------------------------------------------------------------------------
# 3. Controles
# ---------------------------------------------------------------------------


def _doc(label: str, text: str, company: str | None = None) -> js.JdDoc:
    doc = js.JdDoc(label=label, company=company, title=None, text=text)
    doc.raw = js.raw_tokens(doc.text)
    doc.content = js.content_tokens(doc.raw)
    return doc


def test_controls() -> None:
    print("3. controles")
    base = (FIXTURES / "lidl_sap_bi.txt").read_text(encoding="utf-8")
    # idênticos => reuse
    pairs = js.compare_all([_doc("a", base), _doc("b", base)], {}, 8)
    check("3a. JDs idênticos => reuse (coverage 1.0)",
          pairs[0]["verdict"] == js.REUSE and pairs[0]["coverage"] == 1.0,
          f"{pairs[0]}")
    # quase-idênticos (1 frase editada — re-post com edicao menor) => reuse
    near = base.replace("Schnittstellen", "Stakeholder")
    pairs = js.compare_all([_doc("a", base), _doc("b", near)], {}, 8)
    check("3b. quase-idênticos (1 frase editada) => reuse via coverage>=0.90",
          pairs[0]["verdict"] == js.REUSE and pairs[0]["coverage"] >= 0.90,
          f"cov={pairs[0]['coverage']}")
    # espelho com bullet ADICIONADO => ainda reuse (min das direções)
    plus = base + "\nZusätzliche Aufgabe: Unterstützung bei der Pflege von Metadaten und Datenqualität."
    pairs = js.compare_all([_doc("a", base), _doc("b", plus)], {}, 8)
    check("3c. espelho com 1 bullet novo => reuse (min-cobertura ainda >=0.90)",
          pairs[0]["verdict"] == js.REUSE, f"cov={pairs[0]['coverage']}")
    # domínios distintos => regenerate + tópicos nos dois lados
    dom_a = ("Data Engineer Internship. Du baust Datenpipelines mit Python, "
             "Spark und Airflow und trainierst Machine-Learning-Modelle in AWS.")
    dom_b = ("Praktikum Social Media Marketing. Du erstellst Content für "
             "Instagram und TikTok, planst Kampagnen und analysierst Engagement.")
    pairs = js.compare_all([_doc("a", dom_a), _doc("b", dom_b)], {}, 8)
    p = pairs[0]
    check("3d. domínios distintos => regenerate", p["verdict"] == js.REGENERATE, f"{p}")
    check("3e. tópicos não-vazios nos dois lados",
          p["topics_for_b"] and p["topics_for_a"],
          f"b={p['topics_for_b'][:3]} a={p['topics_for_a'][:3]}")
    # mesmo-empregador conhecido e IGUAL => sinal True no par
    lidl_alias = js.load_company_aliases(REAL_ALIASES)
    pairs = js.compare_all(
        [_doc("a", base, company="lidlstiftup2"), _doc("b", near, company="Lidl Stiftung & Co. KG")],
        lidl_alias, 8)
    check("3f. par com empresas conhecidas e iguais (alias F66) => same_employer True",
          pairs[0]["same_employer"] is True)
    pairs = js.compare_all(
        [_doc("a", base, company="Bosch GmbH"), _doc("b", near, company="Lidl Stiftung & Co. KG")],
        lidl_alias, 8)
    check("3g. empregadores diferentes => same_employer False (aviso no CLI)",
          pairs[0]["same_employer"] is False)


# ---------------------------------------------------------------------------
# 4. CLI (subprocess; cwd=tmpdir — prova que não depende de data/ do repo)
# ---------------------------------------------------------------------------


def _run(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "jd_similarity.py"), *args],
        capture_output=True, text=True, cwd=cwd, timeout=120,
    )


def _eligible(tmp: Path, jobs: list[dict]) -> Path:
    path = tmp / "eligible_jobs.json"
    path.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
    return path


def test_cli() -> None:
    print("4. CLI (subprocess, cwd fora do repo)")
    f_sap = str(FIXTURES / "lidl_sap_bi.txt")
    f_preis = str(FIXTURES / "lidl_preismanagement.txt")
    f_proj = str(FIXTURES / "lidl_projete.txt")

    # 4a. par regenerate => rc 0 (SINAL, NUNCA GATE) + tópicos no output
    r = _run(["--jd-file", f_sap, "--jd-file", f_preis], cwd=tempfile.gettempdir())
    check("4a. regenerate com rc 0 (sinal, nunca gate)", r.returncode == 0,
          f"rc={r.returncode} err={r.stderr[:200]}")
    check("4a. veredito + tópicos no stdout",
          "regenerate" in r.stdout and "tópicos que a carta" in r.stdout)
    # 4b. idênticos => reuse no output humano
    r = _run(["--jd-file", f_sap, "--jd-file", f_sap], cwd=tempfile.gettempdir())
    check("4b. idênticos => 'reuse' no stdout, rc 0",
          r.returncode == 0 and "reuse" in r.stdout and "coverage=1.000" in r.stdout)
    # 4c. --json: shape de máquina
    r = _run(["--jd-file", f_sap, "--jd-file", f_preis, "--json"], cwd=tempfile.gettempdir())
    data = json.loads(r.stdout)
    pair = data["pairs"][0]
    check("4c. --json: docs/pairs/thresholds",
          set(data) >= {"docs", "pairs", "thresholds"} and len(data["pairs"]) == 1)
    check("4c. --json: campos do par",
          set(pair) >= {"a", "b", "same_employer", "coverage", "jaccard_rest",
                        "verdict", "borderline", "topics_for_b", "topics_for_a"})
    check("4c. --json: limiares medidos expostos",
          data["thresholds"]["reuse_with_edits_jaccard"] == 0.176
          and data["thresholds"]["reuse_coverage"] == 0.90)
    check("4c. --json: same_employer null p/ --jd-file (sem metadado)",
          pair["same_employer"] is None)
    # 4d. menos de 2 JDs => rc 2
    r = _run(["--jd-file", f_sap])
    check("4d. <2 JDs => rc 2", r.returncode == 2, f"rc={r.returncode}")
    r = _run([])
    check("4d. sem args => rc 2", r.returncode == 2)
    # 4e/4f. --job-id: exato, substring único, não-achado, ambíguo
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        jid_lidl = "Lidl Stiftung & Co. KG|praktikum_info:13308134"
        jid_lidl2 = "lidlstiftup2|sf_dataset:successfactors:1436050633"
        jid_bosch = "Bosch GmbH|smartrecruiters:BoschGroup:744000141914929"
        jobs = [
            {"id": jid_lidl, "company": "Lidl Stiftung & Co. KG",
             "title": "Praktikum Controlling International - Business Intelligence",
             "description": "Du unterstützt bei der Digitalisierung weltweiter Reporting-Prozesse mit BI-Tools."},
            {"id": jid_lidl2, "company": "lidlstiftup2",
             "title": "Praktikum Controlling International - SAP BI Reporting",
             "description": "Digitalisierung und Weiterentwicklung des Reportings mit SAP Analytics Cloud."},
            {"id": jid_bosch, "company": "Bosch GmbH",
             "title": "Praktikum Data Engineering",
             "description": "Du baust Datenpipelines mit Python und Airflow für Machine-Learning-Anwendungen."},
        ]
        elig = _eligible(tmp, jobs)
        # exato
        r = _run(["--input", str(elig), "--job-id", jid_lidl, "--job-id", jid_lidl2,
                  "--aliases", str(REAL_ALIASES)], cwd=str(tmp))
        check("4e. job-id exato ×2 (mesmo empregador via alias) => rc 0, sem aviso",
              r.returncode == 0 and "empregadores diferentes" not in r.stdout,
              f"rc={r.returncode}")
        # substring único
        r = _run(["--input", str(elig), "--job-id", "13308134", "--job-id", "1436050633"],
                 cwd=str(tmp))
        check("4f. substring único resolve => rc 0", r.returncode == 0,
              f"rc={r.returncode} err={r.stderr[:150]}")
        # não-achado
        r = _run(["--input", str(elig), "--job-id", "nao-existe", "--job-id", jid_lidl],
                 cwd=str(tmp))
        check("4g. job-id não encontrado => rc 2 + msg no stderr",
              r.returncode == 2 and "não encontrado" in r.stderr)
        # ambíguo (dois ids contêm 'Lidl')
        r = _run(["--input", str(elig), "--job-id", "Lidl", "--job-id", jid_bosch],
                 cwd=str(tmp))
        check("4h. job-id ambíguo => rc 2 + msg no stderr",
              r.returncode == 2 and "ambíguo" in r.stderr)
        # JD vazio: excluído com aviso
        empty_id = "Leer GmbH|recruitee:2100111"
        jobs_empty = jobs + [{"id": empty_id, "company": "Leer GmbH",
                              "title": "Praktikum ohne Text", "description": ""}]
        sub = tmp / "sub"
        sub.mkdir()
        elig2 = _eligible(sub, jobs_empty)
        r = _run(["--input", str(elig2), "--job-id", empty_id, "--job-id", jid_lidl,
                  "--jd-file", f_proj], cwd=str(tmp))
        check("4i. JD sem texto excluído com aviso (par restante calculado, rc 0)",
              r.returncode == 0 and "excluído" in r.stderr
              and "1 par" in r.stdout, f"rc={r.returncode} out={r.stdout[:120]}")
        r = _run(["--input", str(elig2), "--job-id", empty_id, "--job-id", jid_lidl],
                 cwd=str(tmp))
        check("4i. só 2 JDs e 1 sem texto => rc 2 (nada a comparar)",
              r.returncode == 2, f"rc={r.returncode}")
        # aviso cross-employer quando empresas CONHECIDAS divergem
        r = _run(["--input", str(elig), "--job-id", jid_lidl, "--job-id", jid_bosch],
                 cwd=str(tmp))
        check("4j. empregadores diferentes => aviso ⚠ no stdout, rc 0",
              r.returncode == 0 and "empregadores diferentes" in r.stdout)
    # 4k. determinismo: 2 runs idênticos byte a byte
    args = ["--jd-file", f_sap, "--jd-file", f_proj, "--jd-file", f_preis]
    r1 = _run(args, cwd=tempfile.gettempdir())
    r2 = _run(args, cwd=tempfile.gettempdir())
    check("4k. determinismo: 2 runs => stdout idêntico", r1.stdout == r2.stdout)
    # 4l. sem rede: fonte não importa sockets/http
    src = (ROOT / "scripts" / "jd_similarity.py").read_text(encoding="utf-8")
    check("4l. fonte sem imports de rede (socket/urllib/http/requests)",
          not any(imp in src for imp in ("import socket", "import urllib",
                                          "import requests", "import http")))
    # invisíveis (pitfall F10): zero ZWSP/BOM/LRM/RLM nos artefatos da fase.
    # Agulhas construídas via chr() — literais no fonte seriam self-hit.
    invisible = {chr(0x200B), chr(0xFEFF), chr(0x200E), chr(0x200F)}
    worst = []
    for path in [ROOT / "scripts" / "jd_similarity.py",
                 ROOT / "scripts" / "test_f97.py", *sorted(FIXTURES.glob("*.txt"))]:
        text = path.read_text(encoding="utf-8")
        hits = {hex(ord(c)): text.count(c) for c in invisible if c in text}
        if hits:
            worst.append((path.name, hits))
    check("4m. zero caracteres invisíveis (ZWSP/BOM/LRM/RLM)", not worst, f"{worst}")


def main() -> int:
    test_pure()
    test_fixtures()
    test_controls()
    test_cli()
    print(f"\n{CHECKS} checks, {len(FAILURES)} falhas")
    if FAILURES:
        for f in FAILURES:
            print(f"  FALHOU: {f}")
        return 1
    print("==== test_f97 OK ====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
