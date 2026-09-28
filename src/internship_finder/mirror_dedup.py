"""Deduplicacao de mirrors DE/EN por requisition_id (Fase C) — sub-estagio
deterministico DENTRO do estagio de dedup existente.

CONTEXTO E EVIDENCIA (medida na Fase B e reproduzida no snapshot 27/09):

- ``requisition_id`` sozinho NAO e suficiente: 119 vagas com req_id, 112
  valores unicos, 7 grupos same-tenant com req_id duplicado — 4 sao mirrors
  DE/EN legitimos (mesma vaga publicada nos dois idiomas) e 3 sao FALSOS
  positivos (celonis x2, hellofresh: cargos DIFERENTES que compartilham o
  req_id do processo de hiring). A evidencia completa esta no relatorio da
  Fase C e em ``evidence/reproduce_7_groups.txt``.
- A chave da spec ``requisition_id + titulo normalizado`` e implementada no
  sentido OPERACIONAL medido nos dados: o req_id gera o CANDIDATO (mesmo
  tenant + req_id duplicado — universo fechado de 7 grupos no snapshot) e o
  titulo fornece o GUARDRAIL linguistico: um titulo com marcador de tipo DE
  + outro com marcador de tipo EN (ou, alternativamente, ``normalize_title``
  identica nos dois). NAO e fuzzy matching: sao marcadores de tipo
  deterministicos, a mesma familia de padroes que ``dedup.TYPE_EQUIVALENCES``
  e ``filters.is_student_role`` ja usam no projeto.
- Guardrails mult-campo (spec: "nao crie uma regra baseada em um unico
  campo"): ``country`` IGUAL quando ambos presentes; ``employment_type``
  IGUAL quando ambos presentes. Divergencia em qualquer um rejeita o par
  (candidato-rejeitado auditavel, nada removido).
- Sinais REJEITADOS pela evidencia (documentados para nao voltar atras):
  ``posted_at`` proximo (o FP R15251 tem delta 3s — mais proximo que
  qualquer mirror), ``location`` identica (o mirror ABOUT YOU diverge:
  "Hamburg, Hamburg" vs "Hamburg, HH"; e um campo escasso), descricao
  semelhante (exigiria comparacao textual = fuzzy), idioma estrutural
  (``raw.language`` e None em 412/412 do snapshot) e ``normalized_title``
  identica como REQUISITO (so unificaria 1/4 — os outros tres mirrors sao
  traducoes completas).

REGRA COMPLETA (deterministica e idempotente):

1. CANDIDATO: mesmo tenant (``source``) + mesmo ``requisition_id`` (lido
   via ``structured_fields.requisition_id``, read-only sobre ``raw``).
   Sem req_id ou sem ``raw`` -> nunca candidato (ausencia != dado falso;
   comportamento atual preservado).
2. MIRROR (o par candidato e o mesmo processo se, e somente se):
   (a) ``normalize_title`` identica nos dois titulos; OU
   (b) um titulo com marcador de tipo DE E o outro com marcador de tipo EN;
   E adicionalmente (confirmacao mult-campo):
   (c) ``country`` igual quando ambos presentes;
   (d) ``employment_type`` igual quando ambos presentes.
   Par sem (a) nem (b), ou reprovado em (c)/(d): rejeitado — nada removido.
3. CANONICAL: quando os marcadores linguisticos distinguem DE/EN (regra
   (b), sozinha ou somada a (a)), canonical e o lado EN — a representacao
   util para o candidato do produto (le e aplica em ingles; nos 4 pares
   reais o lado EN tem score Business igual ou maior). Para pares unidos
   apenas por (a), sem marcadores distinguiveis, fallback deterministico:
   (1) description preenchida; (2) employment_type preenchido;
   (3) menor posted_at; (4) ordem de entrada (primeiro vence).
4. Nada de merge de campos: o canonical permanece ipsis literis; o mirror
   sai apenas do conjunto ELEGIVEL ranqueado. O historico SQLite (gravado
   na COLETA, antes e independentemente deste estagio) nao e tocado: a
   vaga-mirror nunca e apagada do banco — apenas deixa de aparecer no
   eligible ranqueado.

Identidade: ``id``/``source``/``external_id``/``global_id`` nao sao
alterados; nenhum ID e inventado. Reversibilidade: ``--no-mirror-dedup``
restaura o comportamento anterior ipsis literis.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from internship_finder.dedup import normalize_title
from internship_finder.structured_fields import requisition_id

# Rotulo do sub-estagio: chave de ``estatisticas`` (CLI/JSONL ``type: run``).
KEY_MIRRORS_DE_EN = "mirrors_de_en"

# ---------------------------------------------------------------------------
# Marcadores de tipo de vaga (guardrail linguistico DE/EN)
# ---------------------------------------------------------------------------

# Marcadores DE, word-boundary, case-insensitive. ``\w*`` cobre flexoes com
# infixo pos-fixado por nao-word-char (ex.: "Werkstudent*in" — o ``*`` nao e
# word char, o padrao casa "werkstudent" ate a borda) e "Praktikant*in".
# ``pflichtpraktikum`` e explicito porque ``\bpraktikum\b`` NAO casa dentro
# de "Pflichtpraktikum" (sem borda antes do "p") — caso real dos mirrors
# Bosch ("Pflichtpraktikum im strategischen Einkauf...").
_DE_TYPE_MARKERS = re.compile(
    r"\b(?:pflichtpraktikum|praktikum|praktikant\w*|werkstudent\w*)\b",
    re.IGNORECASE,
)
# Marcadores EN. "internship" e "intern" precisam estar listados separados:
# "intern" NAO casa dentro de "internship" (o \b exige borda apos "intern",
# e "internship" continua com "s"). "working student" com espaco simples.
_EN_TYPE_MARKERS = re.compile(
    r"\b(?:internship|working student|intern)\b",
    re.IGNORECASE,
)


def _marker_language(title: str | None) -> str | None:
    """Classifica o titulo pelo marcador de tipo: ``"de"`` / ``"en"`` / None.

    Um titulo com marcadores DOS DOIS idiomas (ex.: "Praktikum Internship")
    devolve None (misto: nao e evidencia discriminante para o par). Sem
    marcador algum -> None.
    """
    if not title:
        return None
    de = bool(_DE_TYPE_MARKERS.search(title))
    en = bool(_EN_TYPE_MARKERS.search(title))
    if de and en:
        return None
    if de:
        return "de"
    if en:
        return "en"
    return None


# ---------------------------------------------------------------------------
# Escolha de canonical (deterministica; spec: nao escolha arbitrariamente)
# ---------------------------------------------------------------------------


def _has_description(job: dict[str, Any]) -> bool:
    return bool(job.get("description"))


def _has_employment_type(job: dict[str, Any]) -> bool:
    return bool(job.get("employment_type"))


def _posted_at_sort_key(job: dict[str, Any]) -> tuple[int, str]:
    """Chave de ordenacao para o fallback: menor posted_at primeiro.

    ``posted_at`` ausente e tratado como "infinito" (perde para qualquer
    valor presente) — ausencia nao pode vencer por acaso de ordenacao.
    Comparacao por string ISO: o campo e serializado ISO 8601 pelo modelo;
    para formatos mistos de offset a comparacao lexicografica e um
    aproximacao aceitavel deste fallback de niche (nunca dispara nos 4
    mirrors reais, todos resolvidos pela regra dos marcadores).
    """
    value = job.get("posted_at")
    if value is None:
        return (1, "")
    return (0, str(value))


def _fallback_prefer(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    """``candidate`` deve substituir ``current`` como canonical do fallback?

    Ordem deterministica (spec Fase C): (1) description preenchida;
    (2) employment_type preenchido; (3) menor posted_at; (4) ordem de
    entrada — ``current`` (que veio primeiro) vence o empate total.
    """
    if _has_description(candidate) != _has_description(current):
        return _has_description(candidate)
    if _has_employment_type(candidate) != _has_employment_type(current):
        return _has_employment_type(candidate)
    key_c = _posted_at_sort_key(candidate)
    key_k = _posted_at_sort_key(current)
    if key_c != key_k:
        return key_c < key_k
    return False


# ---------------------------------------------------------------------------
# Regra de par (motivo do mirror + guardrails mult-campo)
# ---------------------------------------------------------------------------


def _pair_mirror_reason(job_a: dict[str, Any], job_b: dict[str, Any]) -> str | None:
    """Motivo pelo qual A e B sao o mesmo mirror, ou None se nao sao.

    (a) ``normalize_title`` identica -> ``"normalized_title"``;
    (b) marcador DE em um + marcador EN no outro -> ``"de/en_type_markers"``;
    ambos -> ``"normalized_title+de/en_type_markers"``; nenhum -> None.
    """
    reasons: list[str] = []
    if normalize_title(job_a.get("title")) == normalize_title(job_b.get("title")):
        reasons.append("normalized_title")
    lang_a = _marker_language(job_a.get("title"))
    lang_b = _marker_language(job_b.get("title"))
    if lang_a and lang_b and lang_a != lang_b:
        reasons.append("de/en_type_markers")
    return "+".join(reasons) if reasons else None


def _pair_guardrails_ok(job_a: dict[str, Any], job_b: dict[str, Any]) -> bool:
    """Guardrails mult-campo: ``country`` e ``employment_type`` iguais
    quando ambos presentes (ausencia de um lado nao reprova — ausencia !=
    dado falso). Divergencia em qualquer um -> par rejeitado."""
    country_a, country_b = job_a.get("country"), job_b.get("country")
    if country_a and country_b and str(country_a) != str(country_b):
        return False
    et_a, et_b = job_a.get("employment_type"), job_b.get("employment_type")
    if et_a and et_b and str(et_a) != str(et_b):
        return False
    return True


# ---------------------------------------------------------------------------
# Estagio (chamado por cli.process_jobs/run_filter_pipeline)
# ---------------------------------------------------------------------------


def deduplicate_mirrors_de_en(
    jobs: list[dict[str, Any]] | list[Any],
) -> tuple[list[dict[str, Any]], dict[str, int], list[tuple[dict[str, Any], dict[str, Any], str]]]:
    """Remove mirrors DE/EN (Fase C) da lista de vagas (dicts ou ``Job``).

    Roda DEPOIS de ``deduplicate`` e ANTES de ``hydrate_descriptions``,
    sobre o conjunto ELEGIVEL. Retorna ``(jobs_sem_mirrors, estatisticas,
    removidos)`` no mesmo formato de ``deduplicate``:

    - ``estatisticas``: ``{KEY_MIRRORS_DE_EN: n_removidos}`` — o CLI soma
      ao ``dedup_removed`` do registro ``type: run`` do JSONL;
    - ``removidos``: lista de ``(canonical, mirror, motivo)`` para auditoria
      (a spec exige rastreabilidade de quem saiu, por que, e quem ficou).

    Candidato = mesma EMPRESA + mesmo tenant (``source``) + mesmo
    ``requisition_id`` (escopo por empresa da dedup classica, P1.1).

    Grupos de N>2: pares sao avaliados em ordem de entrada; um job ja
    removido nao volta a parear; um canonical pode absorver varios mirrors
    (ex.: 1 EN + 2 DE no mesmo req_id). Grupo inteiro sem par valido ->
      nada removido (candidato-rejeitado, visivel nas estatisticas=0).

    Deterministica e idempotente: nenhuma decisao depende de relogio ou
    aleatoriedade; rodar 2x produz o mesmo resultado (o mirror ja removido
    simplesmente nao existe mais na entrada da 2a execucao).
    """
    normalized_jobs: list[dict[str, Any]] = [
        item.to_dict() if hasattr(item, "to_dict") else item for item in jobs
    ]

    # ---- 1. Candidatos: mesma empresa + mesmo tenant (source) + mesmo
    # requisition_id. Escopo por empresa identico ao da dedup classica
    # (P1.1): em tenants ATS compartilhados (ex.: successfactors:jobs cobre
    # SAP/ZF/Kaufland/...), empresas diferentes numeram seus req_ids de
    # forma independente — um req_id igual entre elas representa vagas
    # DIFERENTES e NAO pode gerar candidato (restricao 11 da spec: sem dedup
    # global indiscriminado). ----
    by_candidate: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for idx, job in enumerate(normalized_jobs):
        rid = requisition_id(job)
        if rid is None:
            continue  # requisition_id=None / raw=None -> nunca candidato
        by_candidate[
            (str(job.get("company") or "").strip(), str(job.get("source") or ""), rid)
        ].append(idx)

    removed_idx: set[int] = set()
    removed_audit: list[tuple[dict[str, Any], dict[str, Any], str]] = []

    for (_company, _source, _rid), indices in sorted(by_candidate.items()):
        if len(indices) < 2:
            continue
        group_removed: set[int] = set()
        for i_pos in range(len(indices)):
            if indices[i_pos] in group_removed:
                continue
            job_a = normalized_jobs[indices[i_pos]]
            for j_pos in range(i_pos + 1, len(indices)):
                if indices[j_pos] in group_removed:
                    continue
                job_b = normalized_jobs[indices[j_pos]]
                reason = _pair_mirror_reason(job_a, job_b)
                if reason is None:
                    continue
                if not _pair_guardrails_ok(job_a, job_b):
                    continue
                # ---- 2. Canonical ----
                lang_a = _marker_language(job_a.get("title"))
                lang_b = _marker_language(job_b.get("title"))
                if "de/en_type_markers" in reason:
                    # Marcadores distinguem os lados: canonical = lado EN.
                    canonical, mirror = (
                        (job_a, job_b) if lang_a == "en" else (job_b, job_a)
                    )
                else:
                    # Somente normalized_title identica, sem marcadores
                    # distinguiveis: fallback deterministico do par — o
                    # primeiro da entrada e o ``current``; so troca se o
                    # challenger vencer em descricao/ET/posted_at.
                    if _fallback_prefer(job_b, job_a):
                        canonical, mirror = job_b, job_a
                    else:
                        canonical, mirror = job_a, job_b
                mirror_pos = j_pos if mirror is job_b else i_pos
                removed_audit.append((canonical, mirror, reason))
                group_removed.add(indices[mirror_pos])
                if mirror is job_a:
                    break  # job_a saiu; proxima iteracao externa segue
                # mirror foi job_b: job_a (canonical) continua pareando
            # fim do for j
        # fim do for i
        removed_idx.update(group_removed)

    out = [job for idx, job in enumerate(normalized_jobs) if idx not in removed_idx]
    stats = {KEY_MIRRORS_DE_EN: len(removed_audit)}
    return out, stats, removed_audit
