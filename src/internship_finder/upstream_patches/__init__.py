"""Camada de patches vendored de defeitos do pacote upstream (ats-scrapers).

Cada módulo aqui existe SÓ enquanto o upstream não tem o fix — cada um é
auto-removível (auto-detect no ponto de uso) e carrega o próprio
checklist de remoção no topo. Regras da camada:

- verbatim do PR upstream correspondente onde possível;
- auto-detect COMPORTAMENTAL (o parser do pacote INSTALADO é exercitado
  contra um fixture verbatim real, offline): pacote com fix = bypass
  total (comportamento 100% upstream); sem fix = patch ativo;
- kill switch env por patch (padrão F1, default ON);
- o canário de remoção da suíte própria FALHA quando o pacote passar a
  ter o fix nativamente — a remoção deixa de ser opcional.

Atual: ``bamboohr`` (F59.1 — parser JSON do embed2.php; upstream PR
#300, kalil0321/ats-scrapers, fork rios-vini/ats-scrapers head 85c270a).
"""
