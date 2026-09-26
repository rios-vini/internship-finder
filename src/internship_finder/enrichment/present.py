"""Apresentacao do enrichment (Fase 3) — camada PURA de view, read-only.

Ponto de CONTATO UNICO entre os produtos (ranking HTML, Candidate Fit,
Telegram Daily Digest) e a camada de enrichment: ``scripts/interface.py`` e
``scripts/ranking_digest.py`` importam SOMENTE este modulo. Nenhum modulo do
pipeline (ranking/filters/dedup/app_intel/materials_ranking/coleta/adapters)
importa o pacote — score, eligibility e ordem seguem intactos POR CONSTRUCAO.

Regra arquitetural da fase (spec): *Deterministic pipeline decides. LLM
enrichment informs.* O view apenas ADICIONA contexto na apresentacao:
nunca decide elegibilidade, nunca altera/cria score, nunca reordena, nunca
exclui vaga, nunca bloqueia publicacao.

Semantica obrigatoria (spec secoes 5/8):

- ``not_mentioned`` NUNCA vira "nao"/false — vira omissao (None) ou a frase
  explicita "nada mencionado sobre autorizacao de trabalho na pagina" no
  bloco WA quando TODOS os 8 conceitos sao ausentes (ausencia declarada,
  nunca lida como negativa);
- ``unclear`` NUNCA vira conclusao — vira "incerto";
- record de NAO-extracao (``extracted_at`` ausente) NUNCA e exibido e
  NUNCA vira not_mentioned;
- ``page_is_job_posting=false`` -> record INVISIVEL nos produtos (o texto
  extraido nao e do anuncio desta vaga);
- record com ``pending_content_hash`` = sucesso preservado de conteudo
  ANTIGO: ``stale=True`` — os dados permanecem (ultimo valido), mas a
  apresentacao avisa que a pagina mudou desde a extracao (spec secao 9);
- evidencia = CITACAO LITERAL (<=200 chars) da pagina oficial; a view
  guarda o texto cru e o render escapa (html.escape no HTML; Telegram nao
  envia evidencia).
"""

from __future__ import annotations

import sys
from pathlib import Path

from internship_finder.enrichment.schema import WA_FIELD_NAMES, WAValue
from internship_finder.enrichment.store import EnrichmentStore

# Os 8 conceitos de work authorization (schema): distintos, NUNCA sinonimos.
_WA_CONCEPTS: tuple[str, ...] = tuple(
    name for name in WA_FIELD_NAMES if name != "internship_compatible"
)  # 8 conceitos WA; internship_compatible e tratado a parte

# Rotulos PT-BR por conceito WA (spec secao 5: exibir cada conceito
# SEPARADAMENTE — student status nao colapsa em visa sponsorship etc.).
WA_CONCEPT_LABELS: dict[str, str] = {
    "student_status_required": "matrícula universitária",
    "work_authorization_required": "autorização de trabalho (genérica)",
    "existing_work_authorization_required": "autorização de trabalho já existente",
    "work_permit_required": "work permit (Arbeitserlaubnis)",
    "residence_permit_required": "residence permit (Aufenthaltserlaubnis)",
    "visa_sponsorship": "patrocínio de visto (sponsorship)",
    "international_candidates_explicitly_accepted":
        "aceitação explícita de internacionais",
    "eu_citizenship_required": "cidadania UE",
}

# Campos prioritarios para evidencia (spec secao 3): work authorization /
# sponsorship / student status / idioma / deadline / salary. Somente estes
# ganham o bloco "ver trecho da pagina oficial" no HTML.
_EVIDENCE_FIELDS: tuple[str, ...] = (
    "student_status_required",
    "work_authorization_required",
    "existing_work_authorization_required",
    "work_permit_required",
    "residence_permit_required",
    "visa_sponsorship",
    "international_candidates_explicitly_accepted",
    "eu_citizenship_required",
    "salary",
    "german_requirement",
    "english_requirement",
    "employer_deadline",
    "internship_compatible",
)

# Rotulos PT-BR do nivel de idioma (enrichment) — nivel COMO DECLARADO na
# pagina; ``not_mentioned`` -> None (omitir), ``unclear`` -> "incerto".
_LANGUAGE_LEVEL_LABELS: dict[str, str | None] = {
    "none": "não exigido",
    "conversational": "conversação",
    "fluent": "fluente",
    "business": "fluente para negócios",
    "native": "nativo",
    "unclear": "incerto",
    "not_mentioned": None,
}

_WORK_MODE_LABELS: dict[str, str | None] = {
    "on_site": "presencial",
    "hybrid": "híbrido",
    "remote": "remoto",
    "unclear": "incerto",
    "not_mentioned": None,
}

_SALARY_PERIOD_LABELS: dict[str, str] = {
    "hour": "/hora",
    "month": "/mês",
    "year": "/ano",
}

_SALARY_CURRENCY_SYMBOLS: dict[str, str] = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "CHF": "CHF ",
}

_RECORD_CONFIDENCE_LABELS: dict[str, str] = {
    "high": "alta",
    "medium": "média",
    "low": "baixa",
}

# Trileto true/false/unclear -> rotulo de EXIGENCIA do conceito.
_VALUE_LABELS: dict[str, str] = {
    "true": "exigido",
    "false": "não",
    "unclear": "incerto",
}


def load_enrichment(path: str | Path) -> dict[str, dict]:
    """Le o store (JSONL, key=job_id); QUALQUER falha -> ``{}``.

    Reusa :class:`EnrichmentStore.load` (tolerante a arquivo ausente e a
    linha malformada) e envolve TUDO em try/except: o enrichment nunca
    derruba render/digest/publicacao (spec secao 8). Aviso vai ao stderr.
    """
    try:
        return EnrichmentStore(path).load()
    except Exception as exc:  # noqa: BLE001 — view nunca derruba o produto
        print(
            f"[aviso] enrichment: store nao carregado ({exc.__class__.__name__}: "
            f"{exc}) — seguindo sem enrichment",
            file=sys.stderr,
        )
        return {}


def is_usable(record: dict | None) -> bool:
    """Record exibivel: extracao ocorrida E pagina confirmada como anuncio.

    ``extracted_at`` presente = extracao (records de falha de fetch/LLM nao
    carregam campos — nunca exibir, nunca tratar como not_mentioned).
    ``page_is_job_posting.value is True`` = o texto extraido e de fato o
    anuncio desta vaga; PIP=false -> INVISIVEL nos produtos.
    """
    if not isinstance(record, dict) or record.get("extracted_at") is None:
        return False
    pip = record.get("page_is_job_posting")
    if not isinstance(pip, dict) or pip.get("value") is not True:
        return False
    return True


def is_stale(record: dict | None) -> bool:
    """Sucesso preservado de conteudo ANTIGO (Fase 2): a pagina mudou e a
    re-extracao falhou — o record guarda ``pending_content_hash``. O dado e
    o ultimo VALIDO, mas NAO foi extraido da versao atual da pagina (spec
    secao 9: nunca apresentar stale como extracao atual)."""
    return isinstance(record, dict) and bool(record.get("pending_content_hash"))


def _field(record: dict, name: str) -> dict | None:
    field = record.get(name)
    return field if isinstance(field, dict) else None


def _value(field: dict | None, key: str = "value") -> str | None:
    if field is None:
        return None
    raw = field.get(key)
    return raw if isinstance(raw, str) and raw.strip() else None


def _evidence(field: dict | None) -> str | None:
    if field is None:
        return None
    raw = field.get("evidence")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def _salary_text(record: dict) -> str | None:
    """Salario literal da pagina (ex.: '€2.280/mês'); sem valor -> None.

    Formato: simbolo da moeda quando mapeada, valor literal (nunca
    convertido/estimado), periodo PT-BR quando presente.
    """
    field = _field(record, "salary")
    value = _value(field)
    if value is None:
        return None
    currency = _value(field, "currency")
    symbol = _SALARY_CURRENCY_SYMBOLS.get(currency or "", "")
    period = _value(field, "period")
    period_txt = _SALARY_PERIOD_LABELS.get(period or "", "")
    return f"{symbol}{value}{period_txt}"


def view(record: dict | None) -> dict | None:
    """Record utilizavel -> dict de CAMPOS PRONTOS para exibicao (None fora).

    Labels sao decididos UMA vez aqui e reusados por HTML e Telegram.
    Campos ausentes/not_mentioned ficam ``None`` (OMITIR no render — o
    not_mentioned nunca vira "nao"). ``unclear`` vira "incerto". Atributo
    ``stale=True`` marca extracao de conteudo antigo (nota de apresentacao,
    nunca como se fosse da versao atual da pagina).
    """
    if not isinstance(record, dict) or not is_usable(record):
        return None
    out: dict = {
        "salary_text": _salary_text(record),
        "work_mode": None,
        "location": None,
        "german": None,
        "english": None,
        "student_status": None,
        "wa": {},
        "wa_all_not_mentioned": False,
        "internship_compatible": None,
        "deadline_date": None,
        "evidences": {},
        "stale": is_stale(record),
        "confidence": _RECORD_CONFIDENCE_LABELS.get(
            str(record.get("confidence") or ""), None
        ),
    }
    # modalidade — so valores com significado; not_mentioned/None -> omitir
    mode = _value(_field(record, "work_mode"))
    out["work_mode"] = _WORK_MODE_LABELS.get(mode or "", None)
    # local declarado NA PAGINA (nao o do feed)
    out["location"] = _value(_field(record, "location"))
    # idiomas — nivel como declarado; not_mentioned -> None (omitir)
    out["german"] = _LANGUAGE_LEVEL_LABELS.get(
        _value(_field(record, "german_requirement"), "level") or "", None
    )
    out["english"] = _LANGUAGE_LEVEL_LABELS.get(
        _value(_field(record, "english_requirement"), "level") or "", None
    )
    # student status — conceito WA distintivo (spec secao 5)
    ss = _value(_field(record, "student_status_required"))
    if ss in ("true", "false", "unclear"):
        out["student_status"] = _VALUE_LABELS[ss]
    # os 8 conceitos WA: cada um SEPARADO, somente quando valor != not_mentioned
    for concept in _WA_CONCEPTS:
        raw = _value(record, concept) or _value(_field(record, concept))
        if raw in ("true", "false", "unclear"):
            out["wa"][concept] = {
                "label": _VALUE_LABELS[raw],
                "evidence": _evidence(_field(record, concept)),
            }
    out["wa_all_not_mentioned"] = not out["wa"]
    # internship_compatible — WAValue proprio
    ic = _value(_field(record, "internship_compatible"))
    if ic in ("true", "false", "unclear"):
        out["internship_compatible"] = {
            "true": "compatível", "false": "incompatível",
            "unclear": "incerto",
        }[ic]
    # deadline EXPLICITO do empregador (nunca inferido do posted_at)
    deadline_field = _field(record, "employer_deadline")
    raw_date = (deadline_field or {}).get("date")
    out["deadline_date"] = (
        str(raw_date)[:10]
        if isinstance(raw_date, str) and raw_date.strip() else None
    )
    # evidencias prioritarias (spec secao 3) — texto literal <=200 chars
    for name in _EVIDENCE_FIELDS:
        ev = _evidence(_field(record, name))
        if ev:
            out["evidences"][name] = ev
    return out


def view_map(records: dict[str, dict]) -> dict[str, dict]:
    """{job_id: view} — records nao utilizaveis ficam DE FORA do map (o
    render trata ausencia de id como 'sem bloco', igual a vaga sem record)."""
    out: dict[str, dict] = {}
    for job_id, record in (records or {}).items():
        v = view(record)
        if v is not None:
            out[str(job_id)] = v
    return out


def _fit_line(key: str, kind: str, detail: str) -> dict:
    """Linha no shape do render existente de Candidate Fit."""
    return {"key": key, "kind": kind, "detail": detail}


def fit_lines(view_data: dict | None) -> list[dict]:
    """Linhas de enrichment para o Candidate Fit (spec secao 4).

    ADICIONA contexto depois dos sinais deterministicos (nunca substitui);
    sem nova pontuacao. Prioridade (max ~6 linhas): eu_citizenship >
    student_status > internship_compatible > idiomas > demais WA.

    - ``eu_citizenship_required=true`` -> ALERTA (bloqueador real p/ o dono);
    - ``visa_sponsorship`` true -> ok / false -> warn;
    - conceitos de EXIGENCIA (existing/work permit/residence) true -> warn;
    - ``unclear`` -> kind info (nunca conclusivo);
    - ``not_mentioned`` -> SEM linha (fit nao vira lista de ausencias).
    """
    if not view_data:
        return []
    lines: list[dict] = []
    wa = view_data.get("wa") or {}
    eu = wa.get("eu_citizenship_required")
    if eu is not None:
        if eu["label"] == "exigido":
            lines.append(_fit_line(
                "enr_eu_citizenship", "warn",
                "Exige cidadania UE (página oficial)",
            ))
        elif eu["label"] == "incerto":
            lines.append(_fit_line(
                "enr_eu_citizenship", "info",
                "Cidadania UE: incerto na página oficial",
            ))
    if view_data.get("student_status"):
        text = {
            "exigido": "Exige matrícula universitária (página oficial)",
            "não": "Não exige matrícula universitária (página oficial)",
            "incerto": "Matrícula universitária: incerto (página oficial)",
        }.get(view_data["student_status"], "")
        if text:
            kind = "ok" if view_data["student_status"] == "exigido" else "info"
            lines.append(_fit_line("enr_student_status", kind, text))
    if view_data.get("internship_compatible"):
        value = view_data["internship_compatible"]
        if value == "incerto":
            lines.append(_fit_line(
                "enr_internship", "info",
                "Compatível com estágio/praktikum: incerto (página oficial)",
            ))
        else:
            kind = "ok" if value == "compatível" else "warn"
            lines.append(_fit_line(
                "enr_internship", kind,
                "Compatível com estágio/praktikum (página oficial)",
            ))
    for lang_key, label in (("english", "Inglês"), ("german", "Alemão")):
        level = view_data.get(lang_key)
        if level:
            lines.append(_fit_line(
                f"enr_{lang_key}", "info",
                f"{label} (página oficial): {level}",
            ))
    for concept in ("visa_sponsorship", "existing_work_authorization_required",
                    "work_permit_required", "residence_permit_required",
                    "work_authorization_required",
                    "international_candidates_explicitly_accepted"):
        entry = wa.get(concept)
        if entry is None:
            continue
        label = WA_CONCEPT_LABELS.get(concept, concept)
        if entry["label"] == "exigido" and concept == "visa_sponsorship":
            # sponsorship EXIGIDO = o empregador patrocina: sinal positivo
            lines.append(_fit_line(
                "enr_wa", "ok",
                f"Patrocina visto/sponsorship (página oficial): {label}",
            ))
        elif entry["label"] in ("exigido", "não") and concept != "visa_sponsorship":
            kind = "warn" if entry["label"] == "exigido" else "info"
            verb = "Exige" if entry["label"] == "exigido" else "Não exige"
            lines.append(_fit_line(
                "enr_wa", kind, f"{verb} {label} (página oficial)",
            ))
        elif entry["label"] == "não" and concept == "visa_sponsorship":
            # visa_sponsorship=false = extracao diz que nao patrocina — warn
            lines.append(_fit_line(
                "enr_wa", "warn",
                "Sem patrocínio de visto (página oficial): " + label,
            ))
        elif entry["label"] == "unclear":
            lines.append(_fit_line(
                "enr_wa", "info", f"{label}: incerto (página oficial)",
            ))
    return lines[:6]
