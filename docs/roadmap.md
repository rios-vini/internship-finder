# Roadmap (histórico)

> ⚠️ **Este documento está obsoleto** (época do MVP) e ficou apenas como
> histórico. A fonte de verdade do plano é o **`MASTER_PLAN.md`** (ranking
> P0–P4 com status ✅/⏳); o estado medido atual está em **`PROJECT_STATUS.md`**.

Este era o plano do MVP. O que ele previa **já foi entregue** e evoluiu muito
além disso (deadline canônico, hardening, SQLite, CI, observabilidade, erros
estruturados, ciclo de vida do multiprocessing — ver `PROJECT_STATUS.md`):

- [x] Coleta orientada a empresas (Bosch 4960, SAP 947, Continental 959 — 6866 vagas normalizadas em JSON/CSV).
- [x] Matching exato de empresa (slug/nome casefold + fallback por token corroborado pelo slug).
- [x] Adapters por ATS com cadeias de fallback (SuccessFactors exige URL como slug).
- [x] CLI com timeout defensivo (nenhuma empresa trava o run).
- [x] Filtros de utilidade: pais (Alemanha/Europa, configurável), tipo de vaga
      (Internship/Working Student/Praktikum/Werkstudent, excluindo full-time/
      senior/manager) e áreas-alvo (Supply Chain, Procurement, BI, Analytics,
      Automação).
- [x] Expansão da lista de empresas-alvo alemãs verificadas (ZF, Bayer, BASF,
      Henkel, Infineon, Zalando, Delivery Hero).
- [x] Deduplicação avançada, ranking e automação periódica (dedup + ranking
      implementados; automação pendente na agenda P2).

Itens que seguiam "fora de escopo por enquanto" (LLM, embeddings, banco de
dados, Docker, frontend): **banco de dados já entrou** (persistência SQLite,
P1 #5); LLM/embeddings seguem fora (ver decisões em `MASTER_PLAN.md`).
