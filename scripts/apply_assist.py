#!/usr/bin/env python3
"""F34 — Apply-assist: rascunhos de candidatura por vaga (SOB DEMANDA).

LLM INFORMS, HUMANO DECIDE. Este CLI gera RASCUNHOS que o dono EDITA antes
de qualquer envio — UMA vaga por vez (``--job-id``). Ele NÃO faz parte do
pipeline/cron/digest, NÃO tem auto-submit e NUNCA envia nada para nenhum
destino (zero rede além da API de LLM; nenhum email/formulário/Telegram —
invariante travada em scripts/test_f34.py com bloqueio de socket).

Artefatos por vaga (``data/personal/apply_assist/<job-id>/`` — ``data/`` é
gitignored, nunca versionado):
  cover_letter.md       DRAFT da carta (EN default; ``--lang de`` formal).
                        Header literal 'DRAFT — revisar antes de enviar'.
  keyword_gap.md        skills do anúncio ausentes no perfil (determinístico,
                        mini-dicionário local — a F28 skill_gap.py não foi
                        mergeada; verificado em 13/10).
  interview_briefing.md 8–12 perguntas prováveis EXTRAÍDAS da JD + skeleton
                        STAR apontando QUAL experiência do perfil usar —
                        sem material no perfil → '[FALTA: ...]'.
  visa_facts.md         ESTÁTICO (sem LLM) — frases jurídicas aprovadas,
                        LITERAIS, nunca redigidas além.

Anti-invenção (regra de ouro do PERFIL-CANDIDATO.md): o LLM só pode usar
fatos que estão no perfil fornecido; o que não está vira placeholder. A
API é a mesma do enrichment (NVIDIA integrate, ``z-ai/glm-5.3-flash`` —
NUNCA o glm-5.3 pesado, que queima max_tokens em raciocínio; pitfall do
projeto). 1–3 chamadas por execução; falha de API → erro claro, NADA
parcial silencioso.

Uso:
    python3 scripts/apply_assist.py --job-id "<Job.id>" \
        [--input data/eligible_jobs.json] \
        [--profile ~/.hermes/handoff/f8-maquina-candidatura/PERFIL-CANDIDATO.md] \
        [--lang en|de] [--output data/personal/apply_assist]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.enrichment import llm  # noqa: E402

# F34 (13/10): orcamento de tokens PROPRIO para as chamadas de escrita — o
# MAX_TOKENS=8000 do llm.py e o contrato historico do enrichment (spike E),
# mas o FLASH queima ~7k tokens em reasoning_content em tarefas de escrita
# longa (carta/briefing com perfil+JD): 8000 -> finish_reason=length,
# content=None (medido 13/10 no exemplo real, 2x). 16000 -> stop com folga
# (content ~2k chars, reasoning ~7k). Ferramenta sob demanda, 1 vaga por vez:
# o dobro do orcamento e o custo de fazer a feature funcionar de verdade.
APPLY_ASSIST_MAX_TOKENS = 16000
# Timeout por chamada (medido 13/10: reasoning do FLASH em prompt grande
# excede os 290s do contrato enrichment; 600s cobre com folga).
APPLY_ASSIST_TIMEOUT_S = 600.0
# F34 (13/10, causa-raiz final): o thinking budget do FLASH no endpoint
# NIM e controlado por reasoning_effort (low/high/max, DEFAULT max — docs
# NIM z-ai-glm-5.3-flash). Com max, o modelo "pensa" ~300s e o GATEWAY
# corta com http_504 (medido 302s, 3x). Com low: MESMA carta em 23s
# (content 2.8k chars, reasoning 226). Escrita de rascunho nao precisa de
# thinking profundo — low e o orçamento certo para carta/briefing.
APPLY_ASSIST_REASONING = "low"

# ---------------------------------------------------------------------------
# Constantes da fase
# ---------------------------------------------------------------------------

DEFAULT_INPUT = "data/eligible_jobs.json"
DEFAULT_PROFILE = "~/.hermes/handoff/f8-maquina-candidatura/PERFIL-CANDIDATO.md"
DEFAULT_OUTPUT = "data/personal/apply_assist"

# Header literal do rascunho — testado por substring em test_f34.py.
DRAFT_HEADER = "# DRAFT — revisar antes de enviar"

# Frases jurídicas APROVADAS (visa_facts.md) — LITERAIS, nunca redigir além.
# Fonte: card F34 §3 (verificação §16e Abs. 2 / BeschV §15 Nr. 1 e Nr. 6,
# gesetze-im-internet.de, 12/10).
VISA_FACTS_TEXT = (
    "# Visto §16e — fatos jurídicos (referência rápida por candidatura)\n"
    "\n"
    "Visto §16e (studienbezogenes Praktikum EU): duração máxima de 6 meses "
    "(AufenthG §16e Abs. 2). Segundo a BeschV §15 Nr. 1, Praktikum sob §16e "
    "NÃO exige Zustimmung da Bundesagentur für Arbeit — confirmar "
    "procedimento atualizado com consulado/Ausländerbehörde. "
    "Pflichtpraktikum é isento do salário mínimo por lei; freiwilliges "
    "Praktikum tem piso de €13,90/h (2026). Werkstudent é categoria "
    "contratual DIFERENTE do §16e — enquadramento exige verificação por "
    "vaga. Ofertas >6 meses não cabem no §16e (rota alternativa: BeschV "
    "§15 Nr. 6, até 1 ano durante estudo em universidade estrangeira após "
    "o 4º semestre — exige verificação prévia com as autoridades).\n"
)

# Mini-dicionário de skills para o keyword_gap (F28 skill_gap.py NÃO está
# mergeada no main em 13/10 — verificado). Cada entrada: termo canônico ->
# sinônimos/variantes que podem aparecer na JD (casefold, casamento por
# substring de palavra inteira). O "match" do perfil é feito por lista de
# evidências canônicas do perfil (regex casefold) — deliberadamente
# conservador: só considera presente o que o perfil declara de fato.
SKILL_DICTIONARY: dict[str, tuple[str, ...]] = {
    "Python": ("python",),
    "Power BI": ("power bi", "powerbi"),
    "DAX": ("dax",),
    "Power Query": ("power query",),
    "SQL": ("sql", "sqlite"),
    "Excel": ("excel", "microsoft excel", "ms excel"),
    "Git/GitHub": ("git", "github"),
    "CI/CD": ("github actions", "ci/cd", "continuous integration"),
    "ETL/Data Pipeline": ("etl", "data pipeline", "pipeline de dados", "data analytics pipeline"),
    "Data Analysis": ("data analysis", "data analytics", "análise de dados", "datenanalyse", "data-driven"),
    "Automation": ("automation", "automatisierung", "automatização", "automacao"),
    "Procurement/Purchasing": ("procurement", "purchasing", "beschaffung", "einkauf", "sourcing"),
    "Supply Chain": ("supply chain", "lieferkette", "supply-chain"),
    "Logistics": ("logistics", "logistik"),
    "Inventory Management": ("inventory", "lagerverwaltung", "lagerhaltung", "estoque"),
    "ABC/Pareto Analysis": ("abc analysis", "pareto", "abc-analyse"),
    "Supplier Management": ("supplier management", "lieferanten", "fornecedor", "vendor management"),
    "Negotiation": ("negotiation", "verhandlung", "negociação"),
    "Materials Science": ("materials science", "werkstoff", "materiais", "materialwissenschaft"),
    "CAD": ("cad", "autodesk inventor", "inventor"),
    "Statistics": ("statistik", "statistics", "estatística"),
    "Visualization/Dashboards": ("dashboard", "visualization", "visualisierung", "tableau", "looker"),
    "SAP": ("sap",),
    "ERP": ("erp", "sap", "oracle"),
    "Lean/Process Improvement": ("lean", "process improvement", "kontinuierliche verbesserung", "kaizen"),
    "Project Management": ("project management", "projektmanagement"),
    "Stakeholder Communication": ("stakeholder",),
    "Risk Assessment": ("risk", "risiko"),
    "Forecasting": ("forecast", "prognose", "forecasting"),
    "KPI Reporting": ("kpi", "reporting"),
    "German Language": ("deutsch", "german", "deutschkenntnisse"),
    "English Language": ("englisch", "english"),
    "MS Office": ("ms office", "microsoft office", "office 365"),
    "Data Modeling": ("star schema", "data model", "datenmodell"),
}

# Evidências canônicas do perfil (regex, casefold) — o que o dono TEM.
# Regra anti-invenção: só declara presente o que o perfil declara de fato.
PROFILE_SKILL_EVIDENCE: dict[str, tuple[str, ...]] = {
    "Python": (r"\bpython\b",),
    "Power BI": (r"power\s*bi",),
    "DAX": (r"\bdax\b",),
    "Power Query": (r"power\s*query",),
    "SQL": (r"\bsql\b|\bsqlite\b",),
    "Excel": (r"\bexcel\b|microsoft\s*office",),
    "Git/GitHub": (r"\bgit\b|github",),
    "CI/CD": (r"github\s*actions|\bci\b",),
    "ETL/Data Pipeline": (r"pipeline",),
    "Data Analysis": (r"data\s*analys|an[áa]lise\s*de\s*dados|datenanalyse",),
    "Automation": (r"automat",),
    "Procurement/Purchasing": (r"procurement|purchas|beschaffung|sourcing",),
    "Supply Chain": (r"supply\s*chain",),
    "Logistics": (r"logistics|logistik|log[íi]stica",),
    "Inventory Management": (r"inventory|lagerverwaltung|estoque",),
    "ABC/Pareto Analysis": (r"\babc\b|pareto",),
    "Supplier Management": (r"supplier|lieferant|fornecedor",),
    "Negotiation": (r"negotiat|verhandlung|negociação",),
    "Materials Science": (r"materials|werkstoff|materiais",),
    "CAD": (r"\bcad\b|inventor",),
    "Statistics": (r"estat[íi]stic|statist",),
    "Visualization/Dashboards": (r"dashboard|visualiza",),
    "Project Management": (r"projektmanagement|project\s*management|gestão de projetos",),
    "Stakeholder Communication": (r"stakeholder",),
    "Risk Assessment": (r"risiko|\brisk\b|risco",),
    "Forecasting": (r"forecast|prognose",),
    "KPI Reporting": (r"\bkpi\b|reporting|relat[óo]rio",),
    "English Language": (r"engl|english",),
    "MS Office": (r"office|excel|sheets",),
    "Data Modeling": (r"star\s*schema|modelagem|data\s*model",),
    "German Language": (r"deutsch|german|alem[ãa]o",),
}

# Skills da JD que NÃO consideramos "gap" mesmo sem evidência canônica no
# perfil: alemão é declarado honestamente como A1–A2 no perfil (não é um
# "gap" a apontar — é realidade declarada), e SAP/ERP aparecem em JDs sem
# que sejam expectativa real do estágio (verificação por vaga é manual).
GAP_ALLOWLIST: tuple[str, ...] = ("German Language",)


# ---------------------------------------------------------------------------
# Sumarização determinística do perfil para o LLM
#
# FATO MEDIDO (13/10, exemplo real): com o perfil integral (~9.8k tokens de
# prompt) o glm-5.3-flash quebra NO MESMO sintoma do glm-5.3 pesado — TODO
# o max_tokens queima em reasoning_content e o content volta VAZIO
# (A/B: perfil 20.7k chars → 0 chars; perfil 1.5k chars → 2.1k chars de
# JSON válido). RE-MEDIDO no exemplo real 13/10 com perfil 32.1k chars:
# resumo de 9.0k chars TAMBÉM queima (empty_content ×3) — o gatilho é o
# TAMANHO DO CONTEXTO levando a raciocínio longo, não só o arquivo
# integral. Orçamento seguro empírico: perfil ≤ 6.5k chars no prompt.
#
# Solução: o CLI envia ao LLM um RESUMO ESTRUTURADO dos FATOS (§1–§9 do
# PERFIL), não o arquivo integral. O resumo é DETERMINÍSTICO (sem LLM na
# própria sumarização) e conservador:
# - corta §10 (restrições — o perfil diz "não deve aparecer em documento
#   de candidatura") e §11 (checklist/meta);
# - prioridade de seção: P0 contato/objetivo/disponibilidade/visto (inteiros
#   na medida do possível), P1 experiência/skills/idiomas, P2 educação,
#   P3 projetos (bullets factuais, orçamento residual);
# - dentro da seção: só linhas factuais (headers, bullets, tabelas,
#   subtítulos **bold**); prosa meta/estilo é descartada;
# - orçamento global 6.500 chars, aplicado em ordem de prioridade — seções
#   P0/P1 nunca saem, P3 (projetos) absorve o corte.
# O arquivo original NUNCA é modificado; keyword_gap continua lendo o texto
# integral (evidência canônica sobre o texto completo).
# ---------------------------------------------------------------------------

# Prioridade/foco das seções §1–§9 no resumo para CADA chamada LLM:
# a carta e o briefing precisam de coisas DIFERENTES do perfil.
#   letter   → quem é/contato (§1), objetivo (§2), experiência (§4),
#              skills (§6), idiomas honestos (§7), disponibilidade (§8),
#              visto (§9). Educação (§3) e projetos (§5) ficam FORA:
#              §5 é o mais gordo (9,1k chars) e a carta cita números, não
#              descreve processo; §3 cabe em 1 linha se precisar.
#   briefing → o contrário: perguntas técnicas pedem educação (§3) e
#              projetos com números (§5) para apontar QUAL experiência
#              usar; contato (§1) sobra pouco.
LETTER_SECTIONS: tuple[int, ...] = (1, 2, 4, 6, 7, 8, 9)
BRIEFING_SECTIONS: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9)

# Cota máxima por seção (chars) dentro do orçamento global — evita que
# uma seção gorda (§9 visto com bullets de 600-1.3k chars, §5 projetos
# 9.1k) coma o espaço das críticas (§7 idiomas, §8 disponibilidade).
# Calibrado para a carta (soma das cotas §1+2+4+6+7+8+9 = 4.750 ≤
# PROFILE_BUDGET). Seções fora do mapa: sem cota própria.
SECTION_QUOTA: dict[int, int] = {
    1: 400,    # contato — essenciais do cabeçalho
    2: 400,    # objetivo
    3: 1800,   # educação no briefing — TCC + iniciação
    4: 1200,   # experiência — bullets-chave
    5: 1600,   # projetos no briefing — só bullets com números
    6: 700,    # skills — títulos **bold** + linhas curtas
    7: 800,    # idiomas honestos
    8: 850,    # disponibilidade — quase inteiro
    9: 1000,   # visto — enquadramento §16e + essenciais
}

# Orçamento total do resumo (chars) POR CHAMADA. Medido 13/10 no exemplo
# real: resumo de 9.0k chars queimava o max_tokens do FLASH em reasoning
# (empty_content ×3); ~6.6k (perfil 1.5k + JD 3.8k + template) passou.
# 5.000 de perfil + JD 1.5k (carta) ≈ 9.2k de prompt (~2.8k tokens) —
# abaixo da mediana de produção (4.1k tokens) que roda todo dia.
PROFILE_BUDGET = 5000


def _fact_lines(body: str) -> list[str]:
    """Linhas factuais de uma seção: headers, bullets, tabelas, quotes
    curtos e subtítulos bold; descarta prosa meta/estilo longa."""
    keep: list[str] = []
    for ln in body.splitlines():
        ls = ln.strip()
        if (
            ls.startswith("#")
            or ls.startswith("-")
            or ls.startswith("|")
            or ls.startswith(">")
            or ls.startswith("**")
            or not ls
        ):
            keep.append(ln)
    return keep


def _trim_to_budget(head: str, lines: list[str], budget: int) -> str:
    """Junta head + linhas até o orçamento; marca corte visível."""
    size = len(head) + 1
    keep: list[str] = []
    for ln in lines:
        if size + len(ln) > budget:
            keep.append("  [… trimmed for prompt budget]")
            break
        keep.append(ln)
        size += len(ln) + 1
    return "\n".join([head] + keep)


def summarize_profile_for_llm(
    profile_text: str, apply_sections: tuple[int, ...] = LETTER_SECTIONS
) -> str:
    """Resume o PERFIL-CANDIDATO.md em fatos estruturados para o prompt.

    Determinístico (sem LLM na própria sumarização) e conservador:
    - corta §10 (restrições: o próprio perfil manda NÃO usá-las em
      documentos de candidatura) e §11 (checklist/meta);
    - mantém SÓ as seções pedidas em ``sections`` (foco por chamada:
      ``LETTER_SECTIONS`` para a carta, ``BRIEFING_SECTIONS`` para o
      briefing) como linhas factuais, dentro do orçamento global
      (``PROFILE_BUDGET``) aplicado NA ORDEM dos números de seção;
    - orçamento aplicado em ordem: seções de número menor (quem é,
      objetivo, experiência) entram primeiro e inteiras na medida do
      possível; as últimas absorvem o corte.
    Se o perfil já for curto (<= 6.000 chars), passa integral.
    """
    text = (profile_text or "").strip()
    if len(text) <= 6000:
        return text

    # 1) corta §10 (restrições) e §11 (checklist) em diante.
    m = re.search(r"^## 10\.", text, flags=re.M)
    if m:
        text = text[: m.start()]
    # 2) começa em §1 (descarta cabeçalho meta/nota de uso antes).
    m = re.search(r"^## 1\.", text, flags=re.M)
    if m:
        text = text[m.start():]

    # 3) divide por seção (UMA passada por número — headers duplicados
    #    no arquivo não duplicam conteúdo), guardando os fatos SEM o
    #    header (o header é re-adicionado uma única vez por seção).
    facts_by_num: dict[int, list[str]] = {}
    heads = list(re.finditer(r"^## (\d+)\..*$", text, flags=re.M))
    for idx, h in enumerate(heads):
        num = int(h.group(1))
        if num in facts_by_num:  # primeira ocorrência vence
            continue
        end = heads[idx + 1].start() if idx + 1 < len(heads) else len(text)
        facts_by_num[num] = _fact_lines(text[h.end():end])

    # 4) orçamento global aplicado na ordem pedida, com COTA por seção
    #    (SECTION_QUOTA): seções críticas (idiomas, disponibilidade,
    #    visto) nunca são despejadas por uma seção gorda; a cota corta
    #    dentro da seção (transparência via marca de trim) e o global
    #    corta as últimas da lista.
    out_parts: list[str] = []
    used = 0
    trimmed_any = False
    for num in sorted(apply_sections):
        if num not in facts_by_num:
            continue
        head = f"## {num}."
        remaining = PROFILE_BUDGET - used
        quota = SECTION_QUOTA.get(num)
        if quota is not None:
            remaining = min(remaining, quota)
        if remaining <= len(head) + 40:  # sem espaço útil — corta aqui
            trimmed_any = True
            break
        part = _trim_to_budget(head, facts_by_num[num], remaining)
        if "[… trimmed for prompt budget]" in part:
            trimmed_any = True
        out_parts.append(part)
        used += len(part) + 1

    result = "\n\n".join(out_parts)

    # 5) aviso explícito se o orçamento apertou (dono vê no rascunho que
    #    o prompt foi podado — transparência, não corte silencioso).
    if trimmed_any:
        result += (
            "\n\n[Sections trimmed for prompt budget — the owner's full "
            "profile is the source of truth; expand manually if needed]"
        )
    return result


# JD máxima enviada ao LLM (chars), POR CHAMADA: a carta precisa do
# gist da vaga (1.500 — tarefas iniciais), o briefing precisa das
# exigências (3.500). O corte evita inflar o reasoning do FLASH
# (empty_content medido com prompt gordo, 13/10).
LETTER_JD_LIMIT = 1500
BRIEFING_JD_LIMIT = 3500


def _job_text(job: dict, jd_limit: int = BRIEFING_JD_LIMIT) -> str:
    """Texto da vaga para o LLM: título + empresa + local + descrição
    (limitada a jd_limit chars — o começo da JD concentra tarefas
    e requisitos)."""
    desc = str(job.get("description") or "")
    if len(desc) > jd_limit:
        desc = desc[:jd_limit] + "\n[… description trimmed for prompt budget]"
    parts = [
        f"Title: {job.get('title') or ''}",
        f"Company: {job.get('company') or ''}",
        f"Location: {job.get('location') or ''}",
        f"URL: {job.get('url') or ''}",
        "",
        "Job description:",
        desc,
    ]
    return "\n".join(parts)


def load_job(input_path: str, job_id: str) -> dict:
    """Carrega a vaga por id exato do eligible_jobs.json (uma por execução)."""
    path = Path(input_path).expanduser()
    if not path.is_file():
        raise SystemExit(f"ERRO: input não encontrado: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"ERRO: falha ao ler {path}: {exc}")
    if not isinstance(data, list):
        raise SystemExit(f"ERRO: {path} não é uma lista de vagas")
    for job in data:
        if isinstance(job, dict) and job.get("id") == job_id:
            return job
    raise SystemExit(f"ERRO: job-id não encontrado em {path}: {job_id!r}")


def build_keyword_gap(job: dict, profile_text: str) -> str:
    """keyword_gap.md — skills da JD ausentes no perfil (determinístico).

    Mini-dicionário local (a F28 skill_gap.py não está mergeada no main).
    Presença na JD: substring casefold da variação no título+descrição.
    Presença no perfil: regex de evidência canônica — conservador.
    """
    jd = f"{job.get('title') or ''} {job.get('description') or ''}".casefold()
    profile_low = (profile_text or "").casefold()

    present: list[str] = []
    gaps: list[str] = []

    for canonical, variants in SKILL_DICTIONARY.items():
        jd_hit = next(
            (v for v in variants if v.casefold() in jd), None
        )
        if not jd_hit:
            continue
        evidences = PROFILE_SKILL_EVIDENCE.get(canonical)
        has = bool(
            evidences
            and any(re.search(rx, profile_low) for rx in evidences)
        )
        label = canonical if jd_hit.casefold() == canonical.casefold() else (
            f"{canonical} (JD: {jd_hit})"
        )
        if has or canonical in GAP_ALLOWLIST:
            present.append(label)
        else:
            gaps.append(label)

    lines = [
        "# Keyword gap — skills do anúncio vs. perfil",
        "",
        f"Vaga: **{job.get('title') or ''}** — {job.get('company') or ''}",
        "",
        "Gerado deterministicamente (sem LLM) pelo mini-dicionário da F34.",
        "Presença no perfil é CONSERVADORA: só conta evidência canônica",
        "declarada no PERFIL-CANDIDATO.md — não infere.",
        "",
        "## Presentes no perfil (e exigidas/pedidas na JD)",
    ]
    if present:
        lines.extend(f"- {s}" for s in present)
    else:
        lines.append("- (nenhuma)")
    lines += ["", "## GAPS — pedidas na JD, sem evidência no perfil"]
    lines.extend(f"- {s}" for s in gaps)
    if not gaps:
        lines.append("- (nenhum)")
    lines += [
        "",
        "## Notas",
        "- German Language não entra como gap: o perfil declara alemão",
        "  A1–A2 honestamente (regra dura) — nível é realidade declarada,",
        "  não lacuna a esconder. Se a JD exigir B2+, a vaga NÃO é",
        "  aplicável (o filtro de alemão do pipeline já penaliza isso).",
        "- Itens aqui são INFORMATIVOS para o dono decidir (LLM informs,",
        "  humano decide): usar para preparar entrevista, decidir se a",
        "  vaga vale a pena, ou o que aprender antes de aplicar.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompts (1–3 chamadas LLM por execução; JSON estrito validado no retorno)
# ---------------------------------------------------------------------------

ANTI_FABRICATION_RULES = """ANTI-FABRICATION RULES (absolute):
- Use ONLY facts explicitly present in the CANDIDATE PROFILE below.
- NEVER invent experience, skills, certifications, grades, employers, dates or achievements.
- If the profile has no material for something, output the literal placeholder "[FALTA: <what is missing>]" (Portuguese prefix, keep it).
- Do NOT overstate seniority. The profile marks what is informal/family-business experience and what is a simulation — respect those labels.
- German level: always "A1–A2 (in progress)" — never inflate.
- Output ONLY valid JSON. No markdown fences, no commentary before or after.
"""


COVER_LETTER_PROMPT = """You draft a one-page cover letter (Anschreiben / application letter) for an internship application in Germany.

Rules:
- Language: {lang_name}. Tone: formal, commercial German business style.
- Structure: German business letter convention — salutation line ("Sehr geehrte Frau X" / "Sehr geehrte Damen und Herren" for DE; "Dear Ms X" / "Dear Hiring Team" for EN), then EXACTLY 3 body paragraphs, then closing ("Mit freundlichen Grüßen" for DE / "Kind regards" for EN) and the full name.
- Paragraph 1 (why them): 2-3 concrete sentences from the job posting and the company — what the role/company does and why it matches the candidate's goal. If the posting names a contact person, address them in the salutation; otherwise use the generic salutation.
- Paragraph 2 (who I am + why me): the candidate's background from the profile with concrete numbers where available (e.g. internship-finder project scale, dashboard numbers, 5 years inventory/supplier management) — honest framing, never inflated.
- Paragraph 3 (practical points + call to action): availability (January 2027), working language English (German A1–A2 in progress, stated honestly), visa under §16e AufenthG presented as routine operational fact (company signs training agreement, Bundesagentur für Arbeit approves — never apologetic), and a closing sentence expressing interest in an interview.
- ONE page maximum. Every sentence must trace to a fact in the profile or the posting.
- Contact block: use the profile's contact data (name, address, phone, email, LinkedIn/GitHub) at the top, then company city and current date placeholder "[DATA]".
{anti_rules}
Return JSON with EXACTLY this shape:
{{
  "salutation": "…",
  "paragraph_1": "…",
  "paragraph_2": "…",
  "paragraph_3": "…",
  "closing": "…",
  "contact_name": "…",
  "contact_block": "multi-line contact block from the profile",
  "subject_line": "Bewerbung um ein Praktikum als … / Application — Internship …"
}}

JOB POSTING:
{job_text}

=== CANDIDATE PROFILE (only source of personal facts) ===
{profile_text}"""

INTERVIEW_PROMPT = """You prepare an interview briefing for ONE specific internship posting.

Task: extract 8 to 12 likely interview questions derived ONLY from THIS job description (mix: technical questions about the skills/tasks it mentions, plus behavioral questions about the situations it implies). Each question must be specific to this JD — no generic question bank.

For EACH question provide a STAR-method answer skeleton IN ENGLISH (Situation / Task / Action / Result bullets are suggestions — point WHICH experience from the profile to use). The skeleton must POINT to concrete profile material (project, job, number). If the profile has NO material for that question, the skeleton must contain the literal placeholder "[FALTA: <what the candidate needs to describe>]".
{anti_rules}
Return JSON with EXACTLY this shape:
{{
  "questions": [
    {{
      "question": "…",
      "kind": "technical|behavioral",
      "star_skeleton": "…multi-line skeleton pointing to profile experience or [FALTA: …]…"
    }}
  ]
}}
Constraints: 8 <= len(questions) <= 12. Every skeleton grounded in the profile or marked [FALTA: …].

JOB POSTING:
{job_text}

=== CANDIDATE PROFILE (only source of personal facts) ===
{profile_text}"""


def _require_fields(
    parsed: dict, fields: tuple[str, ...], context: str
) -> dict:
    """Valida os campos obrigatórios do JSON estrito (nada parcial silencioso)."""
    if not isinstance(parsed, dict):
        raise SystemExit(
            f"ERRO: LLM devolveu JSON de topo não-objeto ({context})"
        )
    missing = [f for f in fields if not str(parsed.get(f) or "").strip()]
    if missing:
        raise SystemExit(
            f"ERRO: LLM devolveu JSON incompleto ({context}); "
            f"campos ausentes/vazios: {missing}"
        )
    return parsed


def run_cover_letter(
    key: str,
    job: dict,
    profile_text: str,
    lang: str,
    transport=None,
    backoff=llm.DEFAULT_BACKOFF_S,
    sleep: Callable[[float], None] = llm.time.sleep,
) -> dict:
    """Chamada LLM 1: cover letter (JSON estrito validado)."""
    lang_name = "German (Deutsch)" if lang == "de" else "English"
    prompt = COVER_LETTER_PROMPT.replace("{lang_name}", lang_name).replace(
        "{anti_rules}", ANTI_FABRICATION_RULES
    ).replace("{job_text}", _job_text(job, LETTER_JD_LIMIT)).replace(
        "{profile_text}", profile_text
    )
    parsed, _usage, _latency, attempts, error = llm.extract(
        key, prompt, transport=transport, backoff=backoff, sleep=sleep,
        max_tokens=APPLY_ASSIST_MAX_TOKENS, timeout_s=APPLY_ASSIST_TIMEOUT_S,
        reasoning_effort=APPLY_ASSIST_REASONING,
    )
    if parsed is None:
        raise SystemExit(
            f"ERRO: API de LLM falhou para cover_letter após {attempts} "
            f"tentativa(s): {error} — NADA foi gerado (falha clara, sem "
            "parcial silencioso)."
        )
    return _require_fields(
        parsed,
        ("salutation", "paragraph_1", "paragraph_2", "paragraph_3",
         "closing", "contact_name", "contact_block", "subject_line"),
        "cover_letter",
    )


def run_interview_briefing(
    key: str,
    job: dict,
    profile_text: str,
    transport=None,
    backoff=llm.DEFAULT_BACKOFF_S,
    sleep: Callable[[float], None] = llm.time.sleep,
) -> list:
    """Chamada LLM 2: interview briefing (JSON estrito validado)."""
    prompt = INTERVIEW_PROMPT.replace(
        "{anti_rules}", ANTI_FABRICATION_RULES
    ).replace("{job_text}", _job_text(job, BRIEFING_JD_LIMIT)).replace(
        "{profile_text}", profile_text
    )
    parsed, _usage, _latency, attempts, error = llm.extract(
        key, prompt, transport=transport, backoff=backoff, sleep=sleep,
        max_tokens=APPLY_ASSIST_MAX_TOKENS, timeout_s=APPLY_ASSIST_TIMEOUT_S,
        reasoning_effort=APPLY_ASSIST_REASONING,
    )
    if parsed is None:
        raise SystemExit(
            f"ERRO: API de LLM falhou para interview_briefing após "
            f"{attempts} tentativa(s): {error} — NADA foi gerado (falha "
            "clara, sem parcial silencioso)."
        )
    questions = parsed.get("questions")
    if (
        not isinstance(questions, list)
        or not (8 <= len(questions) <= 12)
    ):
        raise SystemExit(
            "ERRO: LLM devolveu 'questions' inválido "
            f"(esperado lista de 8–12, veio "
            f"{type(questions).__name__}"
            f" len={len(questions) if isinstance(questions, list) else 'n/a'}) "
            "— NADA foi gerado."
        )
    for idx, item in enumerate(questions):
        if (
            not isinstance(item, dict)
            or not str(item.get("question") or "").strip()
            or not str(item.get("star_skeleton") or "").strip()
        ):
            raise SystemExit(
                f"ERRO: pergunta {idx + 1} do briefing incompleta "
                "(question/star_skeleton ausentes) — NADA foi gerado."
            )
    return questions


def render_cover_letter(letter: dict, job: dict, lang: str) -> str:
    """Monta cover_letter.md com o header DRAFT literal."""
    lines = [DRAFT_HEADER]
    lines.append("")
    if lang == "de":
        lines.append("*Rascunho em ALEMÃO formal — revisar antes de enviar. "
                     "Nunca enviar sem revisão e sem assinatura/data.*")
    else:
        lines.append("*Draft in ENGLISH — review before sending. Never send "
                     "without review and signature/date.*")
    lines += [
        "",
        "---",
        "",
        str(letter.get("contact_block") or "").rstrip(),
        "",
        "[CIDADE-EMPRESA], [DATA]",
        "",
        f"**{letter.get('subject_line')}**",
        "",
        str(letter.get("salutation")),
        "",
        str(letter.get("paragraph_1")),
        "",
        str(letter.get("paragraph_2")),
        "",
        str(letter.get("paragraph_3")),
        "",
        str(letter.get("closing")),
        "",
        str(letter.get("contact_name")),
        "",
        "---",
        "",
        "## Placeholders a conferir antes do envio",
        "- [CIDADE-EMPRESA] / [DATA] / [ENDEREÇO-EMPRESA] — conferir no site.",
        "- Nome do recrutador no posting? Se sim, conferir a saudação.",
        f"- Anexos: CV (assinado, data do dia), {job.get('title') or 'vaga'}"
        " — conferir o que o portal pede.",
        "",
    ]
    return "\n".join(lines)


def render_interview_briefing(questions: list, job: dict) -> str:
    """Monta interview_briefing.md (STAR skeletons, EN, anti-invenção)."""
    lines = [
        "# Interview briefing — DRAFT (preparação, não enviar)",
        "",
        f"Vaga: **{job.get('title') or ''}** — {job.get('company') or ''} "
        f"({job.get('location') or ''})",
        "",
        "Perguntas EXTRAÍDAS desta JD (técnicas + comportamentais), cada uma",
        "com skeleton STAR em inglês apontando QUAL experiência do perfil",
        "usar. '[FALTA: …]' = material que não está no perfil — descrever",
        "com o dono antes da entrevista (anti-invenção).",
        "",
    ]
    for idx, item in enumerate(questions, start=1):
        kind = str(item.get("kind") or "technical")
        lines += [
            f"## {idx}. [{kind}] {item.get('question')}",
            "",
            str(item.get("star_skeleton")),
            "",
        ]
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "F34 apply-assist: rascunhos de candidatura por vaga "
            "(LLM informs, humano decide — NUNCA envia nada)."
        )
    )
    parser.add_argument("--job-id", required=True,
                        help="Job.id canônico (exato) da vaga no input JSON")
    parser.add_argument("--input", default=DEFAULT_INPUT,
                        help=f"caminho do JSON de vagas (default {DEFAULT_INPUT})")
    parser.add_argument("--profile", default=DEFAULT_PROFILE,
                        help="PERFIL-CANDIDATO.md (PESSOAL — nunca commitado)")
    parser.add_argument("--lang", choices=("en", "de"), default="en",
                        help="idioma da carta (default en; de = formal)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT,
                        help="diretório base de saída (gitignored)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    job = load_job(args.input, args.job_id)

    profile_path = Path(args.profile).expanduser()
    if not profile_path.is_file():
        raise SystemExit(f"ERRO: perfil não encontrado: {profile_path}")
    profile_text = profile_path.read_text(encoding="utf-8")

    # A key vem EXCLUSIVAMENTE do env (nunca default, nunca em arquivo).
    key = llm.get_api_key()
    if not key:
        raise SystemExit(
            "ERRO: NVIDIA_API_KEY ausente no ambiente — não é possível "
            "gerar os rascunhos (nada parcial silencioso)."
        )

    # Resumo determinístico dos FATOS para o prompt — ver docstring de
    # summarize_profile_for_llm: perfil integral (~9.8k tokens) queima o
    # max_tokens do FLASH em reasoning e devolve content VAZIO (medido
    # 13/10). Foco POR CHAMADA: a carta quer contato/experiência/visto;
    # o briefing quer educação/projetos. keyword_gap lê o texto integral.
    letter_profile = summarize_profile_for_llm(profile_text, apply_sections=LETTER_SECTIONS)
    briefing_profile = summarize_profile_for_llm(profile_text, apply_sections=BRIEFING_SECTIONS)

    out_dir = Path(args.output).expanduser() / args.job_id

    # (1) keyword_gap.md — determinístico, SEM LLM. Gerado em memória
    # primeiro: a fase manda falha clara sem parcial silencioso, então só
    # criamos o diretório e escrevemos em disco após TODAS as chamadas LLM
    # terem sucesso.
    keyword_gap_md = build_keyword_gap(job, profile_text)

    # (2) cover letter — chamada LLM 1 (com o resumo em foco carta).
    letter = run_cover_letter(key, job, letter_profile, args.lang)
    # (3) interview briefing — chamada LLM 2 (resumo em foco briefing).
    questions = run_interview_briefing(key, job, briefing_profile)

    out_dir.mkdir(parents=True, exist_ok=True)

    cover_letter_md = render_cover_letter(letter, job, args.lang)
    briefing_md = render_interview_briefing(questions, job)

    # Tudo validado → agora sim, escreve os 4 arquivos.
    (out_dir / "cover_letter.md").write_text(cover_letter_md, encoding="utf-8")
    (out_dir / "keyword_gap.md").write_text(keyword_gap_md, encoding="utf-8")
    (out_dir / "interview_briefing.md").write_text(
        briefing_md, encoding="utf-8"
    )
    (out_dir / "visa_facts.md").write_text(VISA_FACTS_TEXT, encoding="utf-8")

    print(f"OK — apply_assist: 4 rascunhos em {out_dir}")
    print("    cover_letter.md / keyword_gap.md / interview_briefing.md "
          "/ visa_facts.md")
    print("    DRAFT — revisar antes de enviar. NADA é enviado por este CLI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
