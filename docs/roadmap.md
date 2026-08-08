# Roadmap

## Feito (MVP)
- [x] Coleta orientada a empresas (Bosch 4960, SAP 947, Continental 959 — 6866 vagas normalizadas em JSON/CSV).
- [x] Matching exato de empresa (slug/nome casefold + fallback por token corroborado pelo slug).
- [x] Adapters por ATS com cadeias de fallback (SuccessFactors exige URL como slug).
- [x] CLI com timeout defensivo (nenhuma empresa trava o run).

## Proximo
- [ ] Filtros de utilidade: pais (Alemanha/Europa, configuravel), tipo de vaga
      (Internship/Working Student/Praktikum/Werkstudent, excluindo full-time/
      senior/manager) e areas-alvo (Supply Chain, Procurement, BI, Analytics,
      Automacao).
- [ ] Expansao da lista de empresas-alvo alemas verificadas (ZF, Bayer, BASF,
      Henkel, Infineon, Zalando, Delivery Hero).

## Depois (conforme os resultados exigirem)
- [ ] Deduplicacao avancada, ranking, automacao periodica.
- [ ] (Fora de escopo por enquanto: LLM, embeddings, banco de dados, Docker,
      frontend.)
