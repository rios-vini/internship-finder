"""Fase E — LLM Enrichment SPIKE (pacote ISOLADO).

Mede quanto conhecimento novo e confiável um LLM extrai de texto JA
COLETADO (description hidratada/feed + official_page context + JSON-LD)
quando os detectores deterministicos nao resolvem (WA-gap, teaser,
condicionais).

Regra arquitetural (spec Fase E, §1/§2/§19/§20):

- O pipeline deterministico permanece a AUTORIDADE (descoberta,
  eligibility, dedup, ranking, filtros). Este pacote NUNCA entra no
  pipeline oficial.
- Nenhum modulo existente importa ``spike_e``; ``spike_e`` nunca importa
  ``ranking``/``filters``/``dedup`` — le ``app_intel``/``opportunity_intel``
 /``structured_fields`` APENAS para computar o lado deterministico da
  comparacao (§11; funcoes puras, read-only).
- Resultado = artefato separado (fora do repo), EVIDENCIA-CANDIDATA,
  nunca verdade canonica. Nada aqui escreve jobs.db / eligible_jobs /
  Pages / cron.
"""
