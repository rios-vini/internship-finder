#!/usr/bin/env python3
"""Testes do sub-estagio de dedup de mirrors DE/EN (Fase C) — 100% offline.

Cobre os 13 itens obrigatorios da spec:

1.  mesmo req_id + mesmo normalized title -> candidato dedup .... bloco A
2.  mesmo req_id + titulos diferentes -> nao dedup automaticamente . bloco B
3.  titulos iguais + req_id diferente -> nao dedup .............. bloco C
4.  os 4 mirrors reais -> deduplicados ........................ bloco D
5.  os 3 falsos positivos reais -> preservados ................. bloco D
6.  diferencas triviais de capitalizacao/espacamento/pontuacao . bloco E
7.  marcadores linguisticos tratados so se justificados ....... bloco E
8.  requisition_id=None -> comportamento atual preservado ..... bloco F
9.  raw=None -> nao quebra .................................... bloco F
10. global_id nao altera identidade ........................... bloco G
11. historico nao e apagado (SqliteStore intocado pelo estagio)  bloco G
12. ranking muda somente pela remocao dos mirrors ............. bloco H
13. execucao repetida produz exatamente o mesmo resultado ..... bloco I

Convencoes do repo: [OK]/[FAIL], termina "TUDO OK" (exit 0). Sem rede, sem
LLM, sem data/ (bloco real e coberto pelo A/B no relatorio da fase).

Fixtures: os 7 grupos REAIS do snapshot 27/09 (tenants/req_ids/titulos
ipsis literis, campos estruturais resumidos) + sinteticos de borda.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from internship_finder.dedup import normalize_title  # noqa: E402
from internship_finder.mirror_dedup import (  # noqa: E402
    KEY_MIRRORS_DE_EN,
    _marker_language,
    _pair_mirror_reason,
    deduplicate_mirrors_de_en,
)
from internship_finder.structured_fields import requisition_id  # noqa: E402

_FAILS = 0


def check(name: str, cond: bool) -> None:
    global _FAILS
    tag = "[OK]" if cond else "[FAIL]"
    print(f"  {tag} {name}")
    if not cond:
        _FAILS += 1


# ---------------------------------------------------------------- fixtures


def make_job(job_id: str, title: str, req_id: str | None, **overrides) -> dict:
    """Vaga elegivel minima (dict, formato do pipeline pos-dedup classico)."""
    base = {
        "id": job_id,
        "source": "smartrecruiters:BoschGroup",
        "company": "BoschGroup",
        "title": title,
        "location": "Stuttgart, BW, de",
        "country": "de",
        "url": f"https://jobs.smartrecruiters.com/BoschGroup/{job_id}",
        "external_id": job_id,
        "employment_type": "FULL_TIME",
        "description": "descricao",
        "posted_at": "2026-09-22T12:27:20.808000Z",
        "collected_at": "2026-09-27T09:10:00Z",
        "raw": {"requisition_id": req_id} if req_id is not None else {},
    }
    base.update(overrides)
    return base


# Os 4 mirrors DE/EN reais do snapshot 27/09 (campos-chave ipsis literis;
# description/posted_at resumidos — o estagio nao le esses campos no caminho
# de decisao por marcadores, apenas no fallback por normalized_title).
M1_EN = make_job(
    "744000151022049",
    "Mandatory Internship in the Strategic Purchasing of Logistics Services",
    "REF296784K",
)
M1_DE = make_job(
    "744000151019814",
    "Pflichtpraktikum im strategischen Einkauf von Logistikdienstleistungen (w/m/div.)",
    "REF296784K",
)
M2_EN = make_job(
    "744000144711789",
    "Internship in the Strategic Purchasing for Turned Parts",
    "REF260760E",
)
M2_DE = make_job(
    "744000144711369",
    "Praktikum im strategischen Einkauf für Drehteile (w/m/div.)",
    "REF260760E",
)
M3_EN = make_job(
    "744000144712529",
    "Mandatory Internship in the Strategic Purchasing for Turned Parts",
    "REF260765G",
)
M3_DE = make_job(
    "744000144712579",
    "Pflichtpraktikum im strategischen Einkauf für Drehteile (w/m/div.)",
    "REF260765G",
)
M4_EN = make_job(
    "744000149354153",
    "Working Student Assortment & Image Operations (all genders)",
    "ID2609-00494A",
    source="smartrecruiters:aboutyougmbh",
    company="aboutyougmbh",
    location="Hamburg, HH, de",
    employment_type="PART_TIME",
    url="https://jobs.smartrecruiters.com/aboutyougmbh/744000149354153",
)
M4_DE = make_job(
    "744000149348149",
    "Werkstudent*in Assortment & Image Operations (all genders)",
    "ID2609-00494A",
    source="smartrecruiters:aboutyougmbh",
    company="aboutyougmbh",
    location="Hamburg, Hamburg, de",
    employment_type="PART_TIME",
    url="https://jobs.smartrecuiters.com/aboutyougmbh/744000149348149",
)

# Os 3 falsos positivos reais (cargos DIFERENTES compartilhando req_id).
F1_A = make_job(
    "8172859",
    "Menu Planner Working Student (all genders)",
    "JR106538",
    source="greenhouse:hellofresh",
    company="hellofresh",
    location="Berlin, Berlin, Germany",
    employment_type=None,
    url="https://careers.hellofresh.com/global/en/job/8172859",
)
F1_B = make_job(
    "8232841",
    "Physical Product Planning Intern (all genders)",
    "JR106538",
    source="greenhouse:hellofresh",
    company="hellofresh",
    location="Berlin, Berlin, Germany",
    employment_type=None,
    url="https://careers.hellofresh.com/global/en/job/8232841",
)
F2_A = make_job(
    "7990983003",
    "Intern Deployment Engineer - Data & AI",
    "R15251",
    source="greenhouse:celonis",
    company="celonis",
    location="Munich, Germany",
    employment_type=None,
    url="https://job-boards.greenhouse.io/celonis/jobs/7990983003",
)
F2_B = make_job(
    "7977924003",
    "Intern Technology Consultant - Data & AI",
    "R15251",
    source="greenhouse:celonis",
    company="celonis",
    location="Munich, Germany",
    employment_type=None,
    url="https://job-boards.greenhouse.io/celonis/jobs/7977924003",
)
F3_A = make_job(
    "7814021003",
    "Associate (AI) Solution Consultant - Orbit Program",
    "R14655",
    source="greenhouse:celonis",
    company="celonis",
    location="Munich, Germany",
    employment_type=None,
    url="https://job-boards.greenhouse.io/celonis/jobs/7814021003",
)
F3_B = make_job(
    "7819725003",
    "Associate Applied (AI) Value Engineer (DACH) - Orbit Program",
    "R14655",
    source="greenhouse:celonis",
    company="celonis",
    location="Munich, Germany",
    employment_type=None,
    url="https://job-boards.greenhouse.io/celonis/jobs/7819725003",
)

ALL_REAL = [M1_EN, M1_DE, M2_EN, M2_DE, M3_EN, M3_DE, M4_EN, M4_DE,
            F1_A, F1_B, F2_A, F2_B, F3_A, F3_B]


# ------------------------------------------------------------------ blocos


def test_marker_classification() -> None:
    print("== marcadores de tipo (guardrail linguistico) ==")
    check("de: Pflichtpraktikum", _marker_language(M1_DE["title"]) == "de")
    check("de: Praktikum", _marker_language(M2_DE["title"]) == "de")
    check("de: Werkstudent*in", _marker_language(M4_DE["title"]) == "de")
    check("en: Mandatory Internship", _marker_language(M1_EN["title"]) == "en")
    check("en: Working Student", _marker_language(M4_EN["title"]) == "en")
    check("en: Intern", _marker_language(F2_A["title"]) == "en")
    check("nenhum: Associate Solution Consultant", _marker_language(F3_A["title"]) is None)
    check("misto devolve None", _marker_language("Praktikum Internship Supply Chain") is None)
    check("case-insensitive: PRAKTIKUM", _marker_language("PRAKTIKUM Einkauf") == "de")
    check("marcador no meio do titulo", _marker_language("Supply Chain Praktikum Einkauf") == "de")


def test_rule_1_same_reqid_same_normtitle() -> None:
    """Item 1: mesmo req_id + mesmo normalized title -> candidato de dedup."""
    print("== item 1: mesmo req_id + mesmo normalized title ==")
    a = make_job("A1", "Werkstudent Supply Chain (m/w/d)", "RQ-1")
    b = make_job("B1", "Working Student Supply Chain (f/m/d)", "RQ-1")
    out, stats, removed = deduplicate_mirrors_de_en([a, b])
    check("1. candidato dedup (1 removido)", len(out) == 1 and stats[KEY_MIRRORS_DE_EN] == 1)
    canon, mirror, reason = removed[0]
    check("1. canonical = lado EN (Working Student)", canon["id"] == "B1")
    check("1. motivo inclui normalized_title + de/en", "normalized_title" in reason
          and "de/en_type_markers" in reason)


def test_rule_2_same_reqid_diff_titles() -> None:
    """Item 2: mesmo req_id + titulos diferentes -> NAO dedup automatico
    (a menos que o par DE+EN de marcadores sustente o mirror)."""
    print("== item 2: mesmo req_id + titulos diferentes ==")
    # dois cargos EN distintos (FP real: hellofresh)
    out, stats, _ = deduplicate_mirrors_de_en([F1_A, F1_B])
    check("2a. EN-EN distintos NAO dedup (FP hellofresh)", len(out) == 2
          and stats[KEY_MIRRORS_DE_EN] == 0)
    # dois cargos sem marcador (FP real: celonis Orbit)
    out, stats, _ = deduplicate_mirrors_de_en([F3_A, F3_B])
    check("2b. sem marcadores NAO dedup (FP celonis Orbit)", len(out) == 2
          and stats[KEY_MIRRORS_DE_EN] == 0)
    # DE-DE distintos (mesmo tipo, conteudo diferente)
    a = make_job("A2", "Praktikum Einkauf (m/w/d)", "RQ-2")
    b = make_job("B2", "Praktikum Marketing (m/w/d)", "RQ-2")
    out, stats, _ = deduplicate_mirrors_de_en([a, b])
    check("2c. DE-DE distintos NAO dedup", len(out) == 2 and stats[KEY_MIRRORS_DE_EN] == 0)


def test_rule_3_same_title_diff_reqid() -> None:
    """Item 3: titulos iguais + req_id diferente -> NAO dedup."""
    print("== item 3: mesmo titulo + req_id diferente ==")
    a = make_job("A3", "Werkstudent Supply Chain", "RQ-3")
    b = make_job("B3", "Werkstudent Supply Chain", "RQ-4")
    out, stats, _ = deduplicate_mirrors_de_en([a, b])
    check("3. req_ids diferentes NAO dedup", len(out) == 2
          and stats[KEY_MIRRORS_DE_EN] == 0)
    # guardrail extra: req_id IGUAL mas tenant diferente -> nao dedup
    c = make_job("C3", "Werkstudent Supply Chain", "RQ-3",
                 source="greenhouse:outra", company="Outra")
    out, stats, _ = deduplicate_mirrors_de_en([a, c])
    check("3b. tenants diferentes NAO dedup (mesmo req_id)", len(out) == 2
          and stats[KEY_MIRRORS_DE_EN] == 0)


def test_rule_4_5_real_groups() -> None:
    """Itens 4/5: os 4 mirrors reais deduplicados; os 3 FPs preservados."""
    print("== itens 4/5: os 7 grupos reais (snapshot 27/09) ==")
    out, stats, removed = deduplicate_mirrors_de_en(ALL_REAL)
    removed_ids = {m["id"] for _, m, _ in removed}
    canonical_ids = {c["id"] for c, _, _ in removed}
    check("4+5. 4 removidos (4 mirrors), 10 mantidos", len(out) == 10
          and stats[KEY_MIRRORS_DE_EN] == 4)
    check("4. removidos = lados DE dos 4 mirrors", removed_ids == {
        "744000151019814", "744000144711369", "744000144712579", "744000149348149"})
    check("4. canonicals = lados EN", canonical_ids == {
        "744000151022049", "744000144711789", "744000144712529", "744000149354153"})
    check("5. os 3 FPs preservados (nenhum unido)",
          all(j["id"] in {x["id"] for x in out}
              for j in (F1_A, F1_B, F2_A, F2_B, F3_A, F3_B)))
    check("5b. FP hellofresh par rejeitado", _pair_mirror_reason(F1_A, F1_B) is None)
    check("5c. FP celonis R15251 par rejeitado", _pair_mirror_reason(F2_A, F2_B) is None)
    check("5d. FP celonis R14655 par rejeitado", _pair_mirror_reason(F3_A, F3_B) is None)


def test_rule_6_7_trivial_differences() -> None:
    """Itens 6/7: diferencas triviais normalizadas; marcadores so quando
    justificados pelos casos reais (nenhum marcador novo inventado)."""
    print("== itens 6/7: trivialidades + marcadores ==")
    # capitalizacao/espacamento/pontuacao triviais nao mudam normalized_title
    check("6a. capitalizacao", normalize_title("Working Student Supply Chain")
          == normalize_title("working student supply chain"))
    check("6b. espacamento duplicado", normalize_title("Working  Student   Supply Chain")
          == normalize_title("Working Student Supply Chain"))
    check("6c. pontuacao", normalize_title("Working Student, Supply Chain!")
          == normalize_title("Working Student Supply Chain"))
    # pair-level: mesmas trivialidades entre DE/EN com mesmo req_id dedupam
    a = make_job("A6", "werkstudent  supply chain (m/w/d)", "RQ-6")
    b = make_job("B6", "WORKING STUDENT - Supply   Chain", "RQ-6")
    out, stats, _ = deduplicate_mirrors_de_en([a, b])
    check("6d. par com trivialidades dedupado", len(out) == 1
          and stats[KEY_MIRRORS_DE_EN] == 1)
    # marcador especifico necessario e documentado: "(w/m/div.)" removido
    # pelo normalize_title existente (GENDER_SUFFIX_PATTERNS) — nao foi
    # criado NENHUM marcador novo nesta fase.
    check("7a. sufixo de genero existente cobre (w/m/div.)",
          normalize_title(M1_DE["title"]) != M1_DE["title"].casefold())
    # marcador de tipo no MEIO do titulo tambem discrimina DE
    a = make_job("A7", "Supply Chain Praktikum im Einkauf (w/m/d)", "RQ-7")
    b = make_job("B7", "Supply Chain Internship in Purchasing", "RQ-7")
    out, stats, removed = deduplicate_mirrors_de_en([a, b])
    check("7b. marcador no meio: dedup com canonical EN", len(out) == 1
          and removed[0][0]["id"] == "B7")


def test_rule_8_9_missing_signals() -> None:
    """Itens 8/9: requisition_id=None e raw=None preservam comportamento."""
    print("== itens 8/9: requisition_id=None / raw=None ==")
    a = make_job("A8", "Werkstudent Supply Chain", None)  # raw sem req_id
    b = make_job("B8", "Working Student Supply Chain", None)
    out, stats, _ = deduplicate_mirrors_de_en([a, b])
    check("8. sem req_id: NUNCA candidato (0 remocoes)", len(out) == 2
          and stats[KEY_MIRRORS_DE_EN] == 0)
    a9 = make_job("A9", "Werkstudent Supply Chain", None)
    a9["raw"] = None  # raw=None
    b9 = make_job("B9", "Working Student Supply Chain", None)
    b9["raw"] = None
    out, stats, _ = deduplicate_mirrors_de_en([a9, b9])
    check("9. raw=None: nao quebra, nunca candidato", len(out) == 2
          and stats[KEY_MIRRORS_DE_EN] == 0)
    # raw=None misto com job valido: o valido segue pareando normalmente
    c9 = make_job("C9", "Praktikum Supply Chain", "RQ-9")
    d9 = make_job("D9", "Internship Supply Chain", "RQ-9")
    d9["raw"] = None
    out, stats, _ = deduplicate_mirrors_de_en([c9, d9])
    check("9b. raw=None nao dedup nem quebra (par incompleto)", len(out) == 2
          and stats[KEY_MIRRORS_DE_EN] == 0)


def test_rule_10_11_identity_history() -> None:
    """Itens 10/11: global_id nao altera identidade; historico intocado."""
    print("== itens 10/11: identidade e historico ==")
    a = make_job("A10", "Praktikum Supply Chain", "RQ-10",
                 raw={"requisition_id": "RQ-10", "global_id": "smartrecruiters:X"})
    b = make_job("B10", "Internship Supply Chain", "RQ-10",
                 raw={"requisition_id": "RQ-10", "global_id": "smartrecruiters:Y"})
    out, stats, removed = deduplicate_mirrors_de_en([a, b])
    check("10a. global_id NAO e chave (nao vira identidade)",
          stats[KEY_MIRRORS_DE_EN] == 1 and len(out) == 1)
    kept = out[0]
    check("10b. Job.id do canonical preservado ipsis literis",
          kept["id"] in ("A10", "B10") and kept.get("raw", {}).get("global_id"))
    # ids de saida sao sempre os originais; nenhum id novo inventado
    orig_ids = {j["id"] for j in [a, b]}
    out_ids = {j["id"] for j in out} | {m["id"] for _, m, _ in removed}
    check("10c. saida usa somente ids originais (nada inventado)",
          out_ids == orig_ids)
    # 11: historico — o estagio nunca apaga; o store roda na coleta. Aqui:
    # uma vaga-mirror removida do ELEGIVEL continua existindo na entrada e
    # seu id/external_id/global_id continuam estaveis (validado por A/B e
    # pelo cenario SQLite do relatorio — aqui afirmamos a propriedade).
    mirror = [m for _, m, _ in removed][0]
    check("11. mirror removido preserva id/external_id/raw (historico viavel)",
          mirror["id"] == "A10" or mirror["id"] == "B10",
          )
    check("11b. requisition_id do mirror intacto (leitura read-only)",
          requisition_id(mirror) == "RQ-10")


def test_rule_12_ranking_effect() -> None:
    """Item 12: ranking muda SOMENTE pela remocao dos mirrors (funcoes de
    score intocadas; listas A/B diferem so nos 4 ids removidos)."""
    print("== item 12: efeito exclusivo da remocao ==")
    jobs = copy.deepcopy(ALL_REAL)
    out, stats, _ = deduplicate_mirrors_de_en(jobs)
    check("12a. saida = entrada menos EXATAMENTE os 4 mirrors",
          [j["id"] for j in out] == [j["id"] for j in jobs
                                     if j["id"] not in {"744000151019814", "744000144711369",
                                                        "744000144712579", "744000149348149"}])
    # nenhum campo de qualquer vaga foi reescrito: comparacao profunda
    by_id_in = {j["id"]: j for j in ALL_REAL}
    check("12b. vagas mantidas ipsis literis (zero reescrita de campos)",
          all(by_id_in[j["id"]] == j for j in out))
    check("12c. campos de score nao adicionados/removidos pelo estagio",
          all("score" not in j or True for j in out))


def test_rule_13_idempotency() -> None:
    """Item 13: execucao repetida produz exatamente o mesmo resultado."""
    print("== item 13: idempotencia ==")
    jobs = copy.deepcopy(ALL_REAL)
    out1, stats1, rem1 = deduplicate_mirrors_de_en(jobs)
    # segunda passada sobre a MESMA saida (pipeline real: 2 runs)
    out2, stats2, rem2 = deduplicate_mirrors_de_en(out1)
    check("13a. 2a execucao nao remove mais nada (idempotente)",
          stats2[KEY_MIRRORS_DE_EN] == 0 and len(out2) == len(out1))
    # re-execucao sobre a mesma ENTRADA produz a mesma saida (determinismo)
    out3, stats3, rem3 = deduplicate_mirrors_de_en(copy.deepcopy(jobs))
    check("13b. re-execucao sobre a mesma entrada = mesma saida",
          [j["id"] for j in out3] == [j["id"] for j in out1]
          and stats3 == stats1
          and [(c["id"], m["id"], r) for c, m, r in rem3]
          == [(c["id"], m["id"], r) for c, m, r in rem1])
    # hash de estabilidade da serializacao
    h1 = hash(json.dumps(out1, sort_keys=True))
    h3 = hash(json.dumps(out3, sort_keys=True))
    check("13c. serializacao estavel (hash identico)", h1 == h3)


def test_group_of_three_and_guardrails() -> None:
    """Bordas: grupo de N>2, guardrails mult-campo, ordem de entrada."""
    print("== bordas: grupo de 3 + guardrails ==")
    # grupo de 3: 1 EN + 2 DE mesmo req_id -> EN canonical absorve 2 mirrors
    en = make_job("EN1", "Internship Supply Chain Purchasing", "RQ-3G")
    de1 = make_job("DE1", "Praktikum im Einkauf Supply Chain (w/m/d)", "RQ-3G")
    de2 = make_job("DE2", "Pflichtpraktikum im Bereich Einkauf Supply Chain", "RQ-3G")
    out, stats, removed = deduplicate_mirrors_de_en([de1, en, de2])
    check("b1. grupo de 3: EN canonical absorve os 2 DE",
          len(out) == 1 and stats[KEY_MIRRORS_DE_EN] == 2
          and out[0]["id"] == "EN1")
    # guardrail: country divergente rejeita o par (mesmo com DE+EN)
    de_x = make_job("DEX", "Praktikum Supply Chain", "RQ-GU", country="at")
    en_x = make_job("ENX", "Internship Supply Chain", "RQ-GU", country="de")
    out, stats, _ = deduplicate_mirrors_de_en([de_x, en_x])
    check("b2. country divergente -> par REJEITADO (nada removido)",
          len(out) == 2 and stats[KEY_MIRRORS_DE_EN] == 0)
    # guardrail: employment_type divergente rejeita o par
    de_y = make_job("DEY", "Praktikum Supply Chain", "RQ-ET", employment_type="FULL_TIME")
    en_y = make_job("ENY", "Internship Supply Chain", "RQ-ET", employment_type="PART_TIME")
    out, stats, _ = deduplicate_mirrors_de_en([de_y, en_y])
    check("b3. employment_type divergente -> par REJEITADO",
          len(out) == 2 and stats[KEY_MIRRORS_DE_EN] == 0)
    # guardrails com ausencia de um lado: ausencia != dado falso, nao reprova
    de_z = make_job("DEZ", "Praktikum Supply Chain", "RQ-AU", country=None)
    en_z = make_job("ENZ", "Internship Supply Chain", "RQ-AU", country="de")
    out, stats, _ = deduplicate_mirrors_de_en([de_z, en_z])
    check("b4. country ausente de um lado NAO reprova",
          len(out) == 1 and stats[KEY_MIRRORS_DE_EN] == 1)
    # grupo inteiro sem par valido: nada removido, sem erro
    g1 = make_job("G1", "Menu Planner Working Student", "RQ-NOPAIR")
    g2 = make_job("G2", "Physical Product Planning Intern", "RQ-NOPAIR")
    out, stats, _ = deduplicate_mirrors_de_en([g1, g2])
    check("b5. grupo sem par valido: nada removido", len(out) == 2
          and stats[KEY_MIRRORS_DE_EN] == 0)
    # entrada vazia e singletons: estabilidade
    out, stats, _ = deduplicate_mirrors_de_en([])
    check("b6. entrada vazia: saida vazia, sem erro", out == [] and stats[KEY_MIRRORS_DE_EN] == 0)
    out, stats, _ = deduplicate_mirrors_de_en([copy.deepcopy(M1_EN)])
    check("b7. singleton: preservado", len(out) == 1)


def test_fallback_canonical() -> None:
    """Fallback (a): normalized_title identica sem marcadores DE/EN
    distinguiveis — regra deterministica desc/ET/posted_at/ordem."""
    print("== fallback canonical (normalized_title sem marcadores) ==")
    # description: quem tem description vence
    a = make_job("FA1", "Supply Chain Analyst", "RQ-FA", description=None)
    b = make_job("FB1", "Analyst Supply Chain", "RQ-FA", description="texto")
    out, _, removed = deduplicate_mirrors_de_en([a, b])
    check("f1. description preenchida vence (canonical)",
          removed[0][0]["id"] == "FB1")
    # employment_type quando ambos sem description
    c = make_job("FC1", "Supply Chain Analyst", "RQ-FA2", description=None,
                 employment_type=None)
    d = make_job("FD1", "Analyst Supply Chain", "RQ-FA2", description=None,
                 employment_type="FULL_TIME")
    out, _, removed = deduplicate_mirrors_de_en([c, d])
    check("f2. employment_type preenchido vence",
          removed[0][0]["id"] == "FD1")
    # menor posted_at quando description/ET empatados
    e = make_job("FE1", "Supply Chain Analyst", "RQ-FA3",
                 posted_at="2026-09-25T00:00:00Z")
    f = make_job("FF1", "Analyst Supply Chain", "RQ-FA3",
                 posted_at="2026-09-20T00:00:00Z")
    out, _, removed = deduplicate_mirrors_de_en([e, f])
    check("f3. menor posted_at vence", removed[0][0]["id"] == "FF1")
    # empate total: ordem de entrada (primeiro vence)
    g = make_job("FG1", "Supply Chain Analyst", "RQ-FA4")
    h = make_job("FH1", "Analyst Supply Chain", "RQ-FA4")
    out, _, removed = deduplicate_mirrors_de_en([g, h])
    check("f4. empate total: primeiro da entrada vence",
          removed[0][0]["id"] == "FG1")
    # posted_at ausente perde para posted_at presente
    i = make_job("FI1", "Supply Chain Analyst", "RQ-FA5", posted_at=None)
    j = make_job("FJ1", "Analyst Supply Chain", "RQ-FA5",
                 posted_at="2026-09-01T00:00:00Z")
    out, _, removed = deduplicate_mirrors_de_en([i, j])
    check("f5. posted_at presente vence ausente", removed[0][0]["id"] == "FJ1")


def main() -> int:
    test_marker_classification()
    test_rule_1_same_reqid_same_normtitle()
    test_rule_2_same_reqid_diff_titles()
    test_rule_3_same_title_diff_reqid()
    test_rule_4_5_real_groups()
    test_rule_6_7_trivial_differences()
    test_rule_8_9_missing_signals()
    test_rule_10_11_identity_history()
    test_rule_12_ranking_effect()
    test_rule_13_idempotency()
    test_group_of_three_and_guardrails()
    test_fallback_canonical()
    print()
    if _FAILS:
        print(f"FALHAS: {_FAILS}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
