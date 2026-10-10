# Relatório — Fase 7: Company & Location Intelligence

**Data**: 2026-09-20/21 · **Branch**: `feature/fase7-company-location-intel` ·
**Estado**: suíte local 29/29, CI (29 scripts) verde · **Fonte de verdade**:
MASTER_PLAN.md (Log) + PROJECT_STATUS.md + este relatório.

## 1. Arquivos alterados/criados

| Arquivo | Tipo | Conteúdo |
|---|---|---|
| `src/internship_finder/opportunity_intel.py` | novo | Módulo puro/determinístico da camada: company intel, custo de vida, salário, work mode, cidade/região, duração, pathway, turnover |
| `company_intel/company_intelligence.json` | novo | 12 empresas curadas com fonte+data+qualidade (estrutura reutilizável por empresa) |
| `company_intel/location_intel.json` | novo | Custo de vida de 12 cidades (Numbeo, ago–set/2026) |
| `scripts/interface.py` | alterado | Seções recolhíveis Oportunidade (Empresa/Benefícios/Carreira/Pathway/Localização/Salário/Turnover/Fontes), chips, Compare opportunities (JS), `--company-intel`/`--location-intel` |
| `scripts/test_opportunity_intel.py` | novo | Suite standalone 29ª do CI (offline, fixture + bloco real + arquivos curados) |
| `src/internship_finder/ptbr.py` | alterado | Rótulos PT-BR: work mode, pathway, qualidade de fonte, período de salário, fatores de comparação |
| `.github/workflows/ci.yml` | alterado | Array 28→29 |
| `docs/relatorio_fase7_company_location_intel.md` | novo | Este relatório |
| `README.md`, `docs/architecture.md`, `PROJECT_STATUS.md` | alterados | Documentação da camada |

## 2–8. Dados implementados

- **Empresa** (12 curadas): setor, porte (empregados + ano), sede, presença
  internacional, áreas de atuação, site oficial, página de carreiras
  (domínio do ANÚNCIO — primária) — cada campo com fonte. Sem campo
  verificado → a interface mostra `Not mentioned`/`Not available` (nunca
  inventa).
- **Benefícios**: campo curado; nesta curadoria **nenhum benefício foi
  confirmado em fonte oficial** (páginas de carreiras com cookie-wall) →
  exibido `Not mentioned` para todas. Nenhum benefício é presumido por ser
  comum na Alemanha.
- **Carreira/desenvolvimento**: 1 empresa com evidência oficial
  (Fraunhofer — programas estruturados para estudantes/trainees e
  recém-formados, página oficial). Demais: `Not mentioned`.
- **Internship → Full-time pathway**: estados `Explicitly supported` /
  `Evidence available` / `Not mentioned` / `Unknown` — nunca probabilidade.
  Percentual oficial só como dado factual com fonte (campo
  `pathway_percentage`; nenhuma entrada preenchida nesta curadoria →
  `Not disclosed`).
- **Turnover**: 1 registro com fonte secundária e período (Schaeffler,
  anúncio de 2024 de ~4.700 cortes — fato registrado, **não** vira
  avaliação da empresa nem do estágio). Demais: `Not available`.
- **Salário**: extraído por EVIDÊNCIA do próprio anúncio (`Gehalt`/
  `Vergütung`/`Salary`/`Compensation` + valor/faixa + moeda e/ou período);
  run real 20/09: **18 vagas com salário citado** (ex.: STIHL
  `Gehalt: 2.117 €/Monat`; Bayer `2.280 €`). Sem citação → `Not disclosed`
  (nenhum valor externo/inventado).
- **Localização**: cidade/região a partir da string real (108 cidades
  extraídas no run 20/09); "Germany"/"Deutschland"/"DE" **não** viram
  cidade; endereço com CEP resolve a cidade (ex.: "Dornkaulstraße 2, 52134
  Herzogenrath" → Herzogenrath). Work mode por evidência: hybrid 91 / remote
  5 / on_site 105 / not_mentioned 273 (run 20/09).
- **Custo de vida**: 12 cidades (Berlin, München, Stuttgart, Hamburg, Köln,
  Leipzig, Dresden, Düsseldorf, Nürnberg, Frankfurt, Heidelberg, Bonn) —
  estimativa mensal 1 pessoa sem aluguel, aluguel 1 quarto centro,
  transporte mensal; contexto com fonte+período, nunca verdade absoluta.

## 9. Fontes utilizadas

- **Primary**: anúncio original (domínio do kit de carreiras = `careers_url`;
  salário/modalidade/duração citados no texto); páginas oficiais de carreiras
  (Fraunhofer jobs-and-career; SAP/SmartRecruiters/VW/STIHL portais).
- **Secondary**: Wikipedia (infobox e histórico — setor, sede, empregados,
  ano; Schaeffler workforce 2024).
- **Aggregated**: Numbeo (custo de vida — estimativas aproximadas de usuários,
  ago–set/2026).

## 10. Política de freshness

- Empresa (dados corporativos): validade meses; re-verificação manual por PR
  (arquivo curado; `checked` por entrada, ex.: 2026-09-20).
- Custo de vida: validade semanas/meses; `period` por cidade (ex.: ago/2026)
  e `checked` global 2026-09-20; caveat exibido na interface.
- Vaga (salário/modalidade/duração/cidade): recomputado a CADA geração do
  HTML a partir do snapshot do dia (nunca vive em cache).
- Informação antiga: a interface mostra data de verificação em cada seção
  com fonte ("verificado em 20 set 2026").

## 11. Política de cache

- Zero rede em tempo de render: os arquivos curados SÃO o cache (versionados
  no repo). Sem TTL em runtime; a "validade" é a política acima aplicada na
  curadoria (PR de atualização). Não existe consulta a API externa no
  pipeline: nada para expirar e nada que possa derrubar o refresh.

## 12. Exemplo real de Company Intelligence (SAP — run 20/09)

Vaga "Working Student (f/m/d) - Operations & Automation for SAP S/4HANA"
(Berlin): setor Software empresarial; porte 110.650 empregados (2025);
sede Walldorf; careers jobs.sap.com (domínio do anúncio); work mode Híbrido;
custo de vida Berlim ≈ €1.058/mês sem aluguel, 1 quarto €1.304, passe €63
(Numbeo ago/2026); salário Not disclosed; pathway Unknown (Not disclosed);
benefícios/carreira Not mentioned (sem fonte confirmada).

## 13. Exemplo real de comparação (run 20/09)

| Fator | STIHL Praktikum Data Analytics | SAP Working Student Operations & Automation |
|---|---|---|
| Job Fit (score) | 15,0 | 11,0 |
| Work mode | Não mencionado | Híbrido |
| Cidade | Fellbach | Berlim |
| Salário | €2.117/mês (citado no anúncio) | Not disclosed |
| Custo de vida | Not available (cidade sem dados) | ~€1.058/mês (sem aluguel) |
| Empresa | Ferramentas florestais; Waiblingen; 20.246 emp. (2025) | Software empresarial; Walldorf; 110.650 emp. (2025) |
| Pathway | Unknown | Unknown |

A comparação mostra dados; não elege vencedora (a decisão é do usuário).

## 14. Confirmação: ranking principal NÃO alterado

- Nenhum toque em `ranking.py`, `materials_ranking.py`, `filters.py`, dedup
  ou coleta. O score exibido continua sendo exclusivamente o do pipeline.
- Verificação no real (run 20/09): os `data-score` da página gerada são
  EXATAMENTE os scores do snapshot (medido; ver `test_opportunity_intel`).
- Opportunity Intelligence nunca entra no score (nem benefícios, turnover,
  custo de vida, salário, porte, prestígio, carreira ou efetivação —
  enunciado §12). Nenhum "Company Score" é calculado (§1, §21).

## 15. Testes executados

- `scripts/test_opportunity_intel.py` (novo, 29º do CI): salário (9 casos
  DE/EN + determinismo), work mode (6), cidade/região (6, incl. rua+CEP e
  "Germany"), loaders (ausente/malformado/alias/reuso), custo de vida (4),
  pathway/percentual/turnover (7), duração (3), integração interface
  (12 — seções, data-attrs, score intocado, dados não mutados, sem arquivos
  curados não quebra), arquivos curados (fonte+qualidade+checked; cobertura
  do topo real do ranking 10/10), bloco real (18 com salário; modalidades;
  108 cidades).
- Suíte local completa: **29/29 scripts, 0 falhas** (mesmo array do CI).
- Determinismo: 2 gerações do HTML idênticas exceto timestamp de geração.

## 16. Comportamento em caso de falha externa

- Arquivo curado ausente/corrompido → `{}` (loader nunca levanta exceção);
  a página renderiza normalmente com `Not available`/`Not mentioned` e o
  ranking segue intacto (testado: render_html com mapas vazios).
- Zero dependência de rede no build: não existe API externa consultada em
  runtime, logo não há falha externa que possa derrubar coleta/ranking/
  publicação (§15 do enunciado).
- Site oficial bloqueado (caso teampicnic) → entrada mínima só com o que foi
  verificado (careers do anúncio), resto `null`.

## 17. URL do GitHub Pages

https://rios-vini.github.io/internship-finder/ — publicada após o merge da
fase (publish manual com run_id `fase7-<commit>` no gate exit 0; o cron
09:00 UTC segue publicando diariamente).

## 18. Limitações encontradas

- Benefícios/carreira/pathway: a maioria das páginas oficiais de carreiras
  responde cookie-wall ou nav-only ao extrator → nesta curadoria ficaram
  `Not mentioned`/`Unknown` (honesto; expandir = PRs de curadoria pontuais).
- Custo de vida: só grandes cidades no Numbeo; municípios-sede (Walldorf,
  Fellbach, Waiblingen, Wolfsburg...) ficam `Not available` (sem inferir
  por proximidade). Valores são agregados aproximados, não oficiais.
- Salário detectável apenas quando citado no anúncio (18/474 no run 20/09);
  não há coleta de salários externos (nem Glassdoor — deliberado).
- Turnover: apenas dados públicos confiáveis curados (1 empresa nesta
  rodada); nenhuma agregação automática de reviews (deliberado, §5/§22).
- Compare opportunities: máximo de 4 vagas por comparação (tela).
- Empresa curada ≠ empresa com vagas: 12 de 67 empresas do run (10/10 do
  topo por nº de vagas) — as demais exibem a camada completa com
  `Not available`/`Not mentioned`.

## 19. Commits

(mesma lista em MASTER_PLAN Log 20/09/2026 — FASE 7)

## Deliberadamente de fora (sem Fase 8)

Lista curta de funcionalidades consideradas e NÃO implementadas nesta fase,
para decisão futura separada:

- Coleta automática de benefícios por scraper de páginas de
  carreiras (hoje: curadoria manual; scraping frágil é anti-enunciado §14).
- Salário de fontes externas (Glassdoor/Levels) com fonte — hoje só o
  anúncio (§10).
- Comparação "vencedora" automática ou ranking de empresas — proibido nesta
  fase (§1/§20/§21); possível como feature separada futura.
- Custo de vida por inferência de região/metro (ex.: Walldorf→Heidelberg) —
  hoje `Not available` (§8).
- Mapa/interativo de localizações (visual, não dados).
- Status pessoal de candidaturas (Interessar/Revisar/Aplicada/Ignorar) —
  continua evolução futura (página estática sem backend).
- Alertas Telegram por empresa/benefício — o digest segue compacto (§19).