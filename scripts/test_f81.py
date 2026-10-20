"""Testes F81 — phenom:nan: tenant compartilhado documentado + guard de regressão.

FASE SEM PURGE: nada removido, nada renomeado, zero mudança de coleta.
Esta suíte é 100% OFFLINE (zero rede, ``data/`` intocada) e trava o
contrato da fase (roadmap v5; spec
``~/.hermes/handoff/f81-phenom-nan-doc/ESPECIFICACAO.md``).

``phenom:nan`` é um TENANT LITERAL COMPARTILHADO do registry — o slug
``nan`` é o identificador do tenant Phenom na base upstream (artefato do
manifest adotado como slug), declarado para DHL/Allianz/Merck/
Kuehne+Nagel e resolvido em runtime (sem declaração) também para
ABB/Philips/Roche/BCG. NÃO é NaN/bug do pandas. Série saudável: 32/32
runs ``ok``, 1.064–1.115 vagas/dia (medição F49 §2.1, 17/10/2026). O
prompt da F80 quase cometeu o erro de tratá-lo como NaN — esta suíte
existe para que nenhuma fase futura o repita.

Grupos (spec F81, itens 2a/2b/2c):

(a) DECLARAÇÕES ESTÁVEIS — as entradas que declaram ``phenom:nan``
    continuam declarando, exatamente a lista documentada (Allianz/DHL/
    Kuehne+Nagel/Merck), com ``ats="phenom"`` e habilitadas. A lista é o
    CONTRACT (spec: "contagem estável — lista as empresas"): onda futura
    que adicionar/remover um declarante atualiza-a AQUI conscientemente —
    quebrar é vermelho, nunca silencioso. Controles negativos provam que
    o validador apanha 5º declarante, purge (``tenant=None``) e rename;

(b) CONTRA-CASO DO KEY_BUILD — a sanidade planejada pela F80
    (``ats_type`` "nan" → loud ANTES de compor ``source =
    f"sf_dataset:{ats_type}"``) NÃO dispara para o tenant ``phenom:nan``
    legítimo. A distinção é o alvo: o slug ``nan`` como TENANT é
    válido; ``nan`` como ``ats_type`` de FATIA do dataset é inválido.
    Provado com row REAL do dataset (Kuehne+Nagel, fatia ``phenom``,
    run 19/10/2026): ``row_to_job(row, "phenom")`` compõe identidade
    ``sf_dataset:phenom:<ats_id>`` sem erro — "nan" NUNCA aparece como
    ``ats_type`` (a fatia chama-se ``phenom``; não existe fatia ``nan``).
    O sentido loud é verificado CONDICIONALMENTE (F81 PRECEDE F80 na
    cadeia): se a sanidade já existir (F80 mergeada), ``row_to_job(row,
    "nan")`` DEVE ser loud; se ainda não (main atual), o teste documenta
    o comportamento silencioso (``sf_dataset:nan``) que a F80 fechará —
    verde nos dois mundos e exercitando a sanidade no dia em que ela
    nascer (vermelho se a F80 mirar o slug de TENANT em vez do
    ``ats_type`` de FATIA). O lado registry também é travado:
    ``tenant_consistency_status``/``tenant_consistency_report`` tratam
    ``phenom:nan`` como tenant normal (``consistent`` quando o runtime
    casa) — nenhuma camada pode rejeitar slug ``nan`` como TENANT;

(c) FIXTURES VERBATIM — registro REAL ``type: tenant`` do JSONL de
    métricas (Kuehne+Nagel, run 17/10/2026, ``collected=1115`` — o ponto
    medido da série F49 §2.1) e row REAL do dataset (``raw`` do job
    ``jobs.kuehne-nagel.com|sf_dataset:phenom:9621``, run 19/10/2026),
    ambos capturados read-only de ``data/`` de produção em 20/10/2026.
    A row REGENERA o id real observado em produção (prova de verbatim +
    determinismo do KEY_BUILD).

Uso:  .venv/bin/python scripts/test_f81.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.dataset_source import row_to_job  # noqa: E402
from internship_finder.registry import (  # noqa: E402
    SEED,
    RegistryEntry,
    TENANT_CONSISTENT,
    tenant_consistency_report,
    tenant_consistency_status,
)

FAILURES: list[str] = []

# Contract da lista estável (spec F81 item 2a: "contagem estável — lista as
# empresas"). Onda futura que adicionar/remover um declarante de phenom:nan
# atualiza esta lista CONSCIENTEMENTE (a quebra é o aviso, nunca silenciosa).
PHENOM_NAN_DECLARERS: list[str] = ["Allianz", "DHL", "Kuehne+Nagel", "Merck"]


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def _declarers(seed: list[RegistryEntry]) -> list[str]:
    """Nomes (ordenados) das entradas que declaram tenant ``phenom:nan``."""
    return sorted(e.name for e in seed if e.tenant == "phenom:nan")


# ---------------------------------------------------------------------------
# Fixture C1 — registro REAL ``type: tenant`` (data/collection_metrics.jsonl
# de produção, leitura read-only 20/10/2026). Evidência da medição F49 §2.1:
# série phenom:nan 32/32 runs ``ok``, 1.064–1.115 vagas/dia — ponto 17/10:
# 1.115 (Kuehne+Nagel).
# ---------------------------------------------------------------------------
KN_TENANT_RECORD_20261017 = {
    "type": "tenant",
    "run_id": "2026-10-17T09:00:02.925663+00:00",
    "timestamp": "2026-10-17T09:32:08.480643+00:00",
    "company": "Kuehne+Nagel",
    "source": "phenom:nan",
    "ats": "phenom",
    "status": "ok",
    "collected": 1115,
    "error": None,
    "error_code": None,
    "duration": 4.5,
}

# ---------------------------------------------------------------------------
# Fixture C2 — row REAL do dataset (fatia ``phenom``): ``raw`` do job
# ``jobs.kuehne-nagel.com|sf_dataset:phenom:9621`` do run 2026-10-19
# (data/jobs.json de produção, leitura read-only 20/10/2026). Verbatim do
# CSV upstream MENOS ``description`` (contrato do ``raw`` — ver docstring
# de ``row_to_job``); por isso REGENERA o id real (grupo B, check b3).
# Nota factual: a URL é o domínio PRÓPRIO da empresa
# (jobs.kuehne-nagel.com) — o slug "nan" é identificador na base
# upstream, não o careersite.
# ---------------------------------------------------------------------------
KN_DATASET_ROW_20261019 = {
    "url": "https://jobs.kuehne-nagel.com/job/9621",
    "title": "Praktikant (m/w/d) im Bereich Projektmanagement Kontraktlogistik",
    "company": "jobs.kuehne-nagel.com",
    "ats_type": "phenom",
    "ats_id": "9621",
    "location": "Nuernberg, Bayern, Germany",
    "country_iso": "DE",
    "region": "",
    "language": "",
    "lat": "",
    "lon": "",
    "is_remote": "",
    "salary_min": "",
    "salary_max": "",
    "salary_currency": "",
    "salary_period": "",
    "salary_summary": "",
    "employment_type": "",
    "department": "Contract Logistics",
    "team": "",
    "posted_at": "2026-03-10T00:00:00+00:00",
    "requisition_id": "KUNAGLOBAL9621EXTERNALENGLOBAL",
    "apply_url": "",
    "commitment": "",
    "raw": "{\"category\": \"Contract Logistics\", \"jobSeqNo\": \"KUNAGLOBAL9621EXTERNALENGLOBAL\"}",
}

# Id REAL observado na produção para a fixture C2 (run 2026-10-19) — o
# KEY_BUILD é determinístico: row verbatim + ats_type da fatia regeneram
# exatamente este id (contra-prova de verbatim no grupo B).
KN_JOB_ID_REAL = "jobs.kuehne-nagel.com|sf_dataset:phenom:9621"


# ---------------------------------------------------------------------------
# Grupo A — declarações estáveis (SEM purge: nada removido, nada renomeado)
# ---------------------------------------------------------------------------

def test_declaracoes_estaveis() -> None:
    print("A — declarações estáveis (lista das empresas; SEM purge)")
    declarantes = _declarers(SEED)
    check("a1. declarantes de phenom:nan == lista estável (4 empresas)",
          declarantes == PHENOM_NAN_DECLARERS,
          f"real={declarantes} esperado={PHENOM_NAN_DECLARERS}")
    entries = {e.name: e for e in SEED if e.tenant == "phenom:nan"}
    check("a2. todos os declarantes com ats='phenom'",
          len(entries) == len(PHENOM_NAN_DECLARERS)
          and all(e.ats == "phenom" for e in entries.values()),
          f"{[ (n, e.ats) for n, e in sorted(entries.items()) ]}")
    check("a3. todos habilitados (enabled=True — purge inclui desabilitar)",
          all(e.enabled for e in entries.values()),
          f"desabilitados={[n for n, e in entries.items() if not e.enabled]}")
    # Controles negativos: o validador NÃO é vacuo — apanha 5º declarante,
    # purge (tenant→None) e rename (slug trocado) com a MESMA regra.
    sintetico = RegistryEntry(name="Empresa Sintetica F81", ats="phenom",
                              tenant="phenom:nan")
    d5 = _declarers(list(SEED) + [sintetico])
    check("a4. [negativo] 5º declarante é apontado (quebra futura = consciente)",
          d5 != PHENOM_NAN_DECLARERS and "Empresa Sintetica F81" in d5,
          f"{d5}")
    purged = [e.model_copy(update={"tenant": None}) if e.name == "DHL" else e
              for e in SEED]
    dp = _declarers(purged)
    check("a5. [negativo] purge (tenant→None) é apontado ('DHL' some da lista)",
          dp != PHENOM_NAN_DECLARERS and "DHL" not in dp, f"{dp}")
    renamed = [e.model_copy(update={"tenant": "phenom:dhl"}) if e.name == "DHL"
               else e for e in SEED]
    dr = _declarers(renamed)
    check("a6. [negativo] rename do slug é apontado ('DHL' some da lista)",
          dr != PHENOM_NAN_DECLARERS and "DHL" not in dr, f"{dr}")


# ---------------------------------------------------------------------------
# Grupo B — contra-caso do KEY_BUILD (sanidade F80 x tenant legítimo)
# ---------------------------------------------------------------------------

def test_keybuild_contra_caso() -> None:
    print("B — contra-caso do KEY_BUILD (ats_type de FATIA ≠ slug de TENANT)")
    job = row_to_job(dict(KN_DATASET_ROW_20261019), "phenom")
    check("b1. row_to_job(row REAL KN, 'phenom') devolve Job (sem exceção)",
          job is not None)
    if job is None:
        return
    check("b2. source == 'sf_dataset:phenom' (fatia; nunca 'sf_dataset:nan')",
          job.source == "sf_dataset:phenom", job.source)
    check("b3. id == id real observado na produção (run 19/10/2026)",
          job.id == KN_JOB_ID_REAL, job.id)
    check("b4. identidade sem segmento de fatia 'nan'",
          ":nan:" not in job.id and ":nan" not in job.source, job.id)
    # b5 explícito: a sanidade (presente ou futura) NÃO dispara para o
    # tenant legítimo — ats_type "phenom" é o valor CORRETO para rows de
    # empresas servidas por phenom:nan. Uma sanidade over-broad (que mire
    # o slug de TENANT em vez do ats_type de FATIA) encosta AQUI e fica
    # vermelha: este é o contra-caso alvo da fase.
    try:
        row_to_job(dict(KN_DATASET_ROW_20261019), "phenom")
        check("b5. sanidade de KEY_BUILD NÃO dispara p/ o tenant phenom:nan "
              "legítimo (ats_type='phenom')", True)
    except Exception as exc:  # noqa: BLE001 — qualquer guard loud é erro aqui
        check("b5. sanidade de KEY_BUILD NÃO dispara p/ o tenant phenom:nan "
              "legítimo (ats_type='phenom')", False,
              f"{type(exc).__name__}: {exc}"[:120])
    # b6: o sentido loud, CONDICIONAL à cadeia (F81 PRECEDE F80).
    loud = False
    loud_msg = ""
    j2 = None
    try:
        j2 = row_to_job(dict(KN_DATASET_ROW_20261019), "nan")
    except Exception as exc:  # noqa: BLE001 — sanidade de ats_type, qualquer tipo
        loud = True
        loud_msg = f"{type(exc).__name__}: {exc}"
    if loud:
        check("b6. [F80 presente] ats_type='nan' de FATIA é loud — e o caso "
              "legítimo continua verde (b1–b5)",
              ("ats" in loud_msg.lower()) or ("nan" in loud_msg.lower()),
              loud_msg[:100])
    else:
        check("b6. [pré-F80] ats_type='nan' ainda silencioso → source "
              "'sf_dataset:nan' (buraco documentado que a F80 fecha; o slug "
              "'nan' como TENANT segue válido — b7/b8)",
              j2 is not None and j2.source == "sf_dataset:nan",
              str(getattr(j2, "source", None)))
    # b7/b8: lado registry — phenom:nan é um tenant NORMAL na classificação
    # de consistência (nenhuma camada pode rejeitar slug 'nan' como TENANT).
    st = tenant_consistency_status("phenom:nan", ["phenom:nan"])
    check("b7. tenant_consistency_status(phenom:nan, ['phenom:nan']) == "
          "'consistent'", st == TENANT_CONSISTENT, st)
    rep = tenant_consistency_report(entries=SEED,
                                    runtime_tenants={"Kuehne+Nagel": ["phenom:nan"]})
    kn = next((r for r in rep if r["company"] == "Kuehne+Nagel"), None)
    check("b8. report: Kuehne+Nagel com runtime ['phenom:nan'] == 'consistent' "
          "(sem caso especial p/ 'nan')",
          kn is not None and kn["status"] == TENANT_CONSISTENT
          and kn["registry_tenant"] == "phenom:nan",
          f"status={kn['status'] if kn else 'linha ausente'}")


# ---------------------------------------------------------------------------
# Grupo C — fixtures verbatim (registro real + row real, com proveniência)
# ---------------------------------------------------------------------------

def test_fixtures_verbatim() -> None:
    print("C — fixtures verbatim (registro real 17/10 + row real 19/10)")
    rec = KN_TENANT_RECORD_20261017
    check("c1. registro REAL type:tenant (KN 17/10): source phenom:nan + "
          "ats phenom + status ok + company Kuehne+Nagel",
          rec["type"] == "tenant" and rec["source"] == "phenom:nan"
          and rec["ats"] == "phenom" and rec["status"] == "ok"
          and rec["company"] == "Kuehne+Nagel")
    check("c2. ponto medido F49 §2.1 (17/10/2026): collected=1115 na banda "
          "1.064–1.115 vagas/dia",
          rec["run_id"].startswith("2026-10-17") and rec["collected"] == 1115
          and 1064 <= rec["collected"] <= 1115,
          f"run_id={rec['run_id']} collected={rec['collected']}")
    kn = next((e for e in SEED if e.name == "Kuehne+Nagel"), None)
    check("c3. registry declara EXATAMENTE o tenant do registro real "
          "(fixture ↔ SEED)",
          kn is not None and kn.tenant == rec["source"] == "phenom:nan",
          f"registry={kn.tenant if kn else None}")
    row = KN_DATASET_ROW_20261019
    check("c4. row REAL do dataset (fatia phenom, run 19/10): ats_type "
          "'phenom' + ats_id '9621' + company jobs.kuehne-nagel.com",
          row["ats_type"] == "phenom" and row["ats_id"] == "9621"
          and row["company"] == "jobs.kuehne-nagel.com")
    check("c5. row REAL nunca carrega 'nan' como ats_type (o slug vive no "
          "TENANT, não na fatia)",
          row["ats_type"] != "nan" and "nan" not in row["ats_type"],
          f"ats_type={row['ats_type']}")
    check("c6. URL da vaga = domínio PRÓPRIO da empresa ('nan' não é o "
          "careersite — é o identificador na base)",
          row["url"] == "https://jobs.kuehne-nagel.com/job/9621"
          and "nan" not in row["url"], row["url"])


def main() -> int:
    print("F81 — phenom:nan: doc do tenant compartilhado + guard de regressão "
          "(SEM purge)")
    print()
    test_declaracoes_estaveis()
    print()
    test_keybuild_contra_caso()
    print()
    test_fixtures_verbatim()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
