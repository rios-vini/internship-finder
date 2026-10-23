# Fixtures F97 — os 5 pacotes Lidl simultâneos (JDs verbatim)

Fonte: `REGISTRO-AVALIACOES-VAGAS-2026-10.md` (lotes 13–18/10) — os 5
pacotes de candidatura Lidl preparados pelo dono. Materializados em
arquivos para o `scripts/jd_similarity.py` e a suíte `scripts/test_f97.py`
(o dataset não embute o texto do praktikum_info — description vazia).

| Arquivo | Vaga | id no dataset | Origem do texto |
|---|---|---|---|
| `lidl_sap_bi.txt` | Praktikum Controlling International – SAP BI Reporting | `lidlstiftup2\|sf_dataset:successfactors:1436050633` (Ref 747147) | description embutida na fatia SF — `data/archive/20261015T090002Z/eligible_jobs.json` de produção (lote 13/10; "ab sofort" — ITEM 3) |
| `lidl_projete.txt` | Praktikum Controlling International – Projekte | `lidlstiftup2\|sf_dataset:successfactors:1426446133` (Ref 735605) | idem, archive 20261015T090002Z (re-post da Ref 753653 — ITEM 7) |
| `lidl_int_bi.txt` | Praktikum Controlling International – Business Intelligence | `Lidl Stiftung & Co. KG\|praktikum_info:13308134` | JSON-LD JobPosting de praktikum.info, coletado ao vivo em 22/10/2026 (datePosted 2026-10-17; validThrough 2026-12-02) |
| `lidl_lieferantenentwicklung.txt` | Praktikum Lieferantenentwicklung & Prozessoptimierung | `Lidl Stiftung & Co. KG\|praktikum_info:13308139` | idem (datePosted 2026-10-17; validThrough 2026-12-02) |
| `lidl_preismanagement.txt` | Praktikum Preismanagement & Datenanalyse Non Food | `Lidl Stiftung & Co. KG\|praktikum_info:13355221` | idem (datePosted 2026-10-15; validThrough 2026-12-07) |

Formato de cada arquivo: **título na 1ª linha**, linha vazia, corpo do JD
(mesma composição `title + description` que a CLI usa no modo `--job-id`).
Texto do anúncio público, sem dados pessoais; template Lidl (Einleitung +
Wir bieten) preservado verbatim — é exatamente ele que o detector de
boilerplate (runs comuns) precisa enxergar.

A matriz medida com esses fixtures (Passo 0) está congelada no
`scripts/test_f97.py` (`MEASURED`): trio Controlling International ⇒
`reuse_with_edits` (J 0.188–0.233); SAP BI × Preismanagement ⇒
`regenerate` (J 0.165) — os domínios divergem, a carta precisa citar
"Pricing Non Food".
