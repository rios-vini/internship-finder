"""Testes standalone do perfil Materials Engineering (Fase 4).

Cobre ``src/internship_finder/materials_ranking.py``:

- ``materials_score_job`` (score + breakdown PROPRIOS): a vaga NAO sofre
  mutacao (``score``/``score_breakdown`` do perfil principal intactos);
  breakdown honesto (soma == total); componente ``materials`` pesa mais que
  ``adjacent``; contexto (quality/R&D/lab/teste) SO conta com contexto
  tecnico no titulo (gate); titulo pesa mais que descricao (descricao so
  corrobora 1x); penalidades por funcao de negocio no TITULO (nunca na
  descricao — boilerplate nao penaliza); determinismo (2 execucoes iguais).
- Casos de borda do enunciado: "Working Student"/"engineering"/"internship"
  sozinhos NAO recebem relevancia alta; "Materialwirtschaft"/"Materialfluss"
  NAO contam como materiais (compostos de "material" fora do nucleo);
  "Einkauf Aluminium" (funcao comercial + materia) fica abaixo de vaga
  tecnica real; ranking independente (posicoes materiais != posicoes do
  principal; ``rank_jobs`` inalterado).
- ``rank_materials_jobs``: ordena desc deterministico, adiciona
  ``materials_score``/``materials_breakdown``, NAO muta a entrada, segura com
  lista vazia.
- Bloco REAL (``data/eligible_jobs.json`` presente): mesmas vagas (mesmo
  conjunto), business intacto por id, top-30 independente, vagas tecnicas de
  materiais no topo, distribuicao de scores sana. Sem ``data/``, SKIP
  (padrao do projeto para runner limpo).

Uso: .venv/bin/python scripts/test_materials_ranking.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.materials_ranking import (  # noqa: E402
    WEIGHT_MATERIALS_TITLE,
    rank_materials_jobs,
    materials_score_job,
)
from internship_finder.ranking import rank_jobs  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def job(jid: str, title: str, *, desc: str | None = None, **kw) -> dict:
    base = {
        "id": jid, "title": title, "company": "Acme", "location": "Munich, DE",
        "country_iso": "de", "url": f"https://example.com/{jid}",
        "employment_type": "PART_TIME", "description": desc or "",
    }
    base.update(kw)
    return base


def biz(jid: str, title: str, *, desc: str | None = None, score: float = 5.0) -> dict:
    """Vaga com score do perfil principal (simula saida do pipeline)."""
    return job(jid, title, desc=desc, score=score, score_breakdown={"area": 4.0})


def test_core_relevance() -> None:
    print("== relevancia: nucleo > adjacente > contexto; tipo/local base ==")
    strong = materials_score_job(job("a", "Working Student Materials Engineering"))
    check("'Materials Engineering' no titulo pontua o nucleo",
          strong.breakdown["materials"] >= WEIGHT_MATERIALS_TITLE)
    generic = materials_score_job(job("b", "Working Student Engineering (f/m/d)"))
    check("'Engineering' generico NAO pontua o nucleo (frase exigida)",
          generic.breakdown["materials"] == 0.0)
    check("'Engineering' generico nao domina (score total baixo)",
          generic.total <= strong.total - WEIGHT_MATERIALS_TITLE)
    check("apenas tipo+local marcam o generico (base minima honesta)",
          generic.breakdown["type"] > 0 and generic.breakdown["location"] > 0)
    intern = materials_score_job(job("c", "Intern (m/f/d)", desc=""))
    ws = materials_score_job(job("d", "Working Student (m/w/d)"))
    st = materials_score_job(job("e", "Studentische Aushilfe (m/w/d)"))
    check("'Intern'/'Working Student'/'Studentische Aushilfe' sozinhos ficam baixos",
          max(intern.total, ws.total, st.total) < 3.0)


def test_compostos_material() -> None:
    print("== 'material' composto: so o nucleo explicito conta ==")
    for title in ("Working Student Materialwirtschaft",  # procurement de materiais
                  "Masterarbeit Digital-Twin für Materialfluss",  # logistica
                  "Praktikum Material Management"):
        sc = materials_score_job(job("x", title, desc=""))
        check(f"'{title[:45]}' NAO pontua o nucleo (material solto/composto logico)",
              sc.breakdown["materials"] == 0.0)
    for title in ("Praktikum Materialwissenschaft", "Werkstudent Werkstofftechnik",
                  "Intern Materials Engineering", "Praktikum Kunststofftechnik",
                  "Working Student Polymer Engineering"):
        sc = materials_score_job(job("y", title, desc=""))
        check(f"'{title[:45]}' pontua o nucleo",
              sc.breakdown["materials"] > 0)


def test_gate_contexto() -> None:
    print("== contexto (quality/R&D/lab) so com contexto tecnico no titulo ==")
    # Quality sem qualquer sinal tecnico: nao pontua (regra do enunciado).
    q_sem = materials_score_job(job("q1", "Working Student Quality Management (m/w/d)", desc=""))
    check("'Quality' sem contexto tecnico NAO pontua contexto",
          q_sem.breakdown["context"] == 0.0)
    check("'Quality' sem contexto continua baixa (nao vira vaga de materiais)",
          q_sem.total < 3.0)
    # Quality com termo tecnico no titulo: gate abre e pontua.
    q_tec = materials_score_job(job("q2", "Praktikum Qualität Batteriezellenfertigung (w/m/d)", desc=""))
    check("'Qualität' com bateria (contexto tecnico) pontua",
          q_tec.breakdown["context"] > 0.0 and q_tec.breakdown["adjacent"] > 0.0)
    # 'Sales Development' (development EN) nao ganha nada: sem gate.
    sales = materials_score_job(job("q3", "Working Student - Sales Development & Demand Generation", desc=""))
    check("'development' em Sales Development nao pontua (gate fechado)",
          sales.breakdown["context"] == 0.0)
    check("'Sales' no titulo penaliza (funcao de negocio)",
          sales.breakdown["penalties"] < 0)
    # Descricao sozinha nao abre o gate (precisa de titulo); a descricao pode
    # CORROBORAR o nucleo no maximo 1x (contribuicao limitada, calibrada).
    desc_only = materials_score_job(job("q4", "Working Student Data (m/w/d)",
                                        desc="Quality assurance for polymer testing lab"))
    check("descricao com termos de materiais NAO abre o gate (contexto 0, sem titulo)",
          desc_only.breakdown["context"] == 0.0)
    check("descricao sozinha corrobora o nucleo no maximo 1x (limitado)",
          desc_only.breakdown["materials"] <= 1.0 + 1e-9)


def test_penalidades_funcao() -> None:
    print("== penalidades: funcao de negocio no TITULO; descricao nao penaliza ==")
    einkauf = materials_score_job(job("p1", "Werkstudent Einkauf (m/w/d)", desc=""))
    check("'Einkauf' no titulo penaliza (funcao oposta)",
          einkauf.breakdown["penalties"] < 0)
    scc = materials_score_job(job("p2", "Working Student Supply Chain", desc=""))
    check("'Supply Chain' no titulo penaliza",
          scc.breakdown["penalties"] < 0)
    # mesma vaga tecnica com descricao repleta de termos de negocio (ME Office,
    # area organizacional citando Einkauf): NAO penaliza (titulo manda).
    tec = materials_score_job(job(
        "p3", "Praktikum Entwicklung Batteriezelle (w/m/d)",
        desc="Gute Kenntnisse in MS Office. Bereiche: Technologie, Einkauf, "
             "Nachhaltigkeit. Supp.ly Chain auditing in the office of the "
             "finance department with marketing people.",
    ))
    check("descricao com Einkauf/Office/Finance NAO penaliza (titulo limpo)",
          tec.breakdown["penalties"] == 0.0)
    alu = materials_score_job(job("p4", "Praktikant Einkauf Aluminium (w/m/x)", desc=""))
    tec_real = materials_score_job(job("p5", "Praktikum Entwicklung Batteriezelle (w/m/d)", desc=""))
    check("'Einkauf Aluminium' (comercial) fica abaixo de vaga tecnica real",
          alu.total < tec_real.total + 0.01)


def test_descricao_corrobora_1x() -> None:
    print("== descricao so corrobora (1x por bloco): titulo manda ==")
    sem_desc = materials_score_job(job("d1", "Working Student Materials Engineering", desc=""))
    com_desc = materials_score_job(job(
        "d2", "Working Student Materials Engineering",
        desc="Materials Science, Materials Testing, Metallurgy, Polymers, "
             "Composites, Ceramics, Coatings, Corrosion and more materials "
             "terms in a long generic text",
    ))
    from internship_finder.materials_ranking import WEIGHT_MATERIALS_DESC
    check("descricao rica corrobora o nucleo NO MAXIMO 1x (diferenca == peso desc)",
          abs((com_desc.breakdown["materials"] - sem_desc.breakdown["materials"])
              - WEIGHT_MATERIALS_DESC) < 1e-9)
    check("descricao rica aumenta o score (corroboracao, nao dominancia)",
          com_desc.total > sem_desc.total)


def test_breakdown_honesto() -> None:
    print("== breakdown honesto: soma == total; componentes reais ==")
    for t in ("Praktikum Beschichtung (w/m/d)", "Werkstudent Logistik (m/w/d)",
              "Working Student Battery Cell Development", "Intern (m/f/d)"):
        sc = materials_score_job(job("h", t, desc="some text"))
        check(f"soma == total ({t[:40]}...)",
              abs(sc.total - round(sum(sc.breakdown.values()), 2)) < 1e-9)
    sc = materials_score_job(job("h2", "Praktikum Beschichtung (w/m/d)"))
    check("componentes implementados (6, todos reais)",
          set(sc.breakdown) == {"materials", "adjacent", "context", "type",
                                "location", "penalties"})


def test_independencia_do_principal() -> None:
    print("== independencia: score do principal intacto; rankings proprios ==")
    jobs_in = [
        biz("1", "Werkstudent Einkauf (m/w/d)", score=12.0),
        biz("2", "Praktikum Materials Testing (m/w/d)", score=3.0),
        biz("3", "Working Student Data Analytics", score=17.5),
        biz("4", "Internship Mechanical Engineering", score=8.0),
    ]
    before = {j["id"]: (j.get("score"), j.get("score_breakdown")) for j in jobs_in}
    ranked = rank_materials_jobs(jobs_in)
    for j in ranked:
        check(f"business {j['id']} intacto (score/breakdown)",
              before[j["id"]] == (j.get("score"), j.get("score_breakdown")))
    check("materials_score/breakdown adicionados",
          all(j.get("materials_score") is not None
              and isinstance(j.get("materials_breakdown"), dict)
              for j in ranked))
    mat_order = [j["id"] for j in ranked]
    biz_order = [j["id"] for j in rank_jobs(jobs_in)]
    check("ordem materials != ordem business (posicoes independentes)",
          mat_order != biz_order)
    check("vaga tecnica lidera o ranking materials (nao o Data Analytics 17.5)",
          mat_order[0] == "2")
    check("entrada nao mutada (sem materials_score na lista original)",
          all("materials_score" not in j for j in jobs_in))
    check("lista vazia -> []", rank_materials_jobs([]) == [])


def test_determinismo() -> None:
    print("== determinismo ==")
    data = [
        biz("1", "Werkstudent Einkauf (m/w/d)"),
        biz("2", "Praktikum Materials Testing (m/w/d)"),
        biz("3", "Working Student Data Analytics"),
        biz("4", "Internship Mechanical Engineering"),
        biz("5", "Praktikum Beschichtung"),
        biz("6", "Working Student Supply Chain"),
    ]
    a = [j["id"] for j in rank_materials_jobs(data)]
    b = [j["id"] for j in rank_materials_jobs(data)]
    sa = [materials_score_job(j).total for j in data]
    sb = [materials_score_job(j).total for j in data]
    check("2 execucoes -> mesma ordem e mesmos scores",
          a == b and sa == sb)


def test_real_snapshot() -> None:
    print("== bloco real (data/eligible_jobs.json) — Fase 4 ==")
    json_path = Path(__file__).resolve().parent.parent / "data" / "eligible_jobs.json"
    if not json_path.exists():
        print("  [SKIP] data/eligible_jobs.json ausente (runner limpo)")
        return
    data = json.loads(json_path.read_text(encoding="utf-8"))
    n = len(data)
    check("snapshot lista nao vazia", isinstance(data, list) and n > 0)
    mats = rank_materials_jobs(data)
    check("MESMA quantidade de vagas elegiveis (nada sai/nada entra)",
          len(mats) == n)
    before = {j["id"]: j.get("score") for j in data}
    check("score do perfil principal intacto em TODAS as vagas",
          all(before[j["id"]] == j.get("score") for j in mats))
    check("todas com materials_score/materials_breakdown",
          all(isinstance(j.get("materials_score"), (int, float))
              and isinstance(j.get("materials_breakdown"), dict) for j in mats))
    scores = [j["materials_score"] for j in mats]
    check("score maximo do materials e modesto (sem inflacao de descricao)",
          max(scores) < 12.0)
    top = mats[:1][0]
    bd = top["materials_breakdown"]
    check("total == soma dos componentes reais (top 1)",
          abs(top["materials_score"] - round(sum(bd.values()), 2)) < 1e-9)
    biz_top30 = {j["id"] for j in data[:30]}
    mat_top30 = {j["id"] for j in mats[:30]}
    overlap = len([x for x in biz_top30 if x in mat_top30])
    check("Top 30 do principal != Top 30 do materials (posicoes independentes)",
          overlap != 30 and [j["id"] for j in data[:30]] != [j["id"] for j in mats[:30]])
    # Determinismo sobre o snapshot real.
    mats2 = rank_materials_jobs(data)
    check("determinismo no snapshot real",
          [j["id"] for j in mats] == [j["id"] for j in mats2])
    # A vaga tecnicamente mais clara do conjunto lidera (Beschichtung).
    check("vaga de recobrimento/Beschichtung no topo (sinal real de materiais)",
          "beschichtung" in str(mats[0].get("title") or "").lower()
          or any("beschichtung" in str(j.get("title") or "").lower() for j in mats[:5]))


def main() -> int:
    test_core_relevance()
    test_compostos_material()
    test_gate_contexto()
    test_penalidades_funcao()
    test_descricao_corrobora_1x()
    test_breakdown_honesto()
    test_independencia_do_principal()
    test_determinismo()
    test_real_snapshot()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())