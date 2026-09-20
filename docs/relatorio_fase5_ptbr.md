# Relatório Fase 5 — Compreensão PT-BR + explicação do ranking

**Data:** 2026-09-19 · **PR:** #74 (squash `5e1cc95`, CI 27/27) · **Main:** `5e1cc95`
**Snapshot de validação:** run 18/09 — 476 vagas elegíveis (mesmo conjunto da Fase 4).

A Fase 5 adiciona uma **camada estruturada em PT-BR** à interface e **melhora a
explicação do ranking**, sem traduzir descrições inteiras, sem LLM/API/serviço
externo e **sem alterar nenhum número do pipeline** (elegibilidade, filtros,
pesos, score, dedup, coleta).

---

## 1. Arquivos alterados/criados

| Arquivo | Tipo | O que faz |
|---|---|---|
| `src/internship_finder/ptbr.py` | **novo** | Camada PT-BR determinística: glossário (≈80 entradas), `title_pt`, `detect_language`, `employment_type_pt`, `country_label`, `relevance_signals`, `penalties`. Zero dependência nova (stdlib `re`). |
| `scripts/interface.py` | alterado | Render do título PT-BR + tag "Original (EN/DE)"; tipo/pais em PT-BR nos fatos; bloco "por que esta vaga?" com explicadores PT-BR por componente e seção "o que reduziu a nota"; nota no rodapé/cabeçalho; rótulos do breakdown passam a vir do `ptbr.py` (DRY). |
| `scripts/test_ptbr.py` | **novo** | 59 checks: glossário/determinismo, campos PT-BR, explicação do score, render Fase 5, ranking inalterado (fixture + bloco real). |
| `.github/workflows/ci.yml` | alterado | `test_ptbr` entra na suíte (26→27 scripts). |
| `docs/relatorio_fase5_ptbr.md` | **novo** | Este relatório. |
| `README.md` | alterado | Seção "PT-BR (Fase 5)" + como manter o glossário. |
| `PROJECT_STATUS.md` | alterado | Entrada na seção Completed + snapshot atual. |
| `MASTER_PLAN.md` | alterado | Seção 1 + Log de mudanças. |

Não alterados (de propósito): `ranking.py`, `materials_ranking.py`,
`filters.py`, `dedup`, `registry`, coleta, digest do Telegram. Nenhuma
dependência nova (pyproject/requirements intocados).

## 2. Termos/campos exibidos em PT-BR

| Campo | Como | Exemplo |
|---|---|---|
| **Título (derivado)** | Glossário determinístico, campo separado "PT-BR" | `Praktikum Data Analytics / Data Science` → `Estágio (Praktikum) · Análise de Dados / Ciência de Dados` |
| **Título original** | Sempre visível, com tag do idioma | `Original (DE): Praktikum Data Analytics / Data Science` |
| **Tipo do anúncio** | Mapeamento determinístico (valor original entre parênteses) | `FULL_TIME` → `tipo do anúncio: Período integral (FULL_TIME)` |
| **País** | ISO → nome PT-BR | `country_iso=de` → `país: Alemanha` |
| **Modalidade** | Campo real, sem inferência | `remote=true` → `remoto`; ausente → não exibido |
| **"Por que esta vaga?"** | Componentes reais do breakdown com rótulo + detalhe PT-BR | `Área` +6.00 — "termos da área alvo (Procurement, Supply Chain, BI…)" |
| **Penalidades** | Seção dedicada somente quando há componente negativa | `Penalidades` −0.40 — "o que reduziu a nota" |
| **Idioma do título** | Marcadores fortes DE/EN | tag `Original (DE)` / `Original (EN)`; sem marcador → sem tag |

**Não inventado:** requisitos estruturados (o `Job` não tem campo), resumo
textual, tradução integral da descrição — nenhum desses existe e **não foi
criado**. Descrição permanece original, com tag "Original".

## 3. Como a tradução foi implementada

- **Glossário** (`ptbr.GLOSSARY`): pares `(regex, frase_pt, rótulo_pt)`,
  **frases compostas antes de palavras soltas** ("Supply Chain Management"
  antes de "Supply Chain"; "SAP Analytics Cloud" antes de "Analytics").
  Termos profissionais internacionais são preservados junto da tradução:
  `Compras (Procurement)`, `Working Student (Werkstudent)`,
  `Inteligência de Negócios (BI)`.
- **Alternância única** compilada 1× no import; `title_pt` substitui cada
  termo e **separa segmentos traduzidos consecutivos por " · "** (leitura),
  preservando palavras desconhecidas exatamente como estão.
- **Palavras-ponte** (im/in/for/und/and só minúsculas) traduzidas **somente
  em lacunas entre dois segmentos traduzidos** — cabeça/cauda não traduzidas
  ficam intactas ("Direction for a New Business Segment" permanece EN) e o
  sufixo alemão `*in`/`/in` é protegido por lookbehind (`Praktikant*in` não
  vira `Praktikant*em`).
- **Frase de produto protegida**: `SAP Analytics Cloud` tem entrada
  "identidade" (não traduz "Analytics" dentro do nome do produto).
- **Decoração de gênero** (`(f/m/d)`, `(m/w/x)` etc.) removida **apenas do
  campo PT-BR derivado** — o original a mantém.
- **Determinismo total**: mesma vaga → mesma tradução, sempre (testado com
  1.000 chamadas repetidas); custo ≈ 0,5 ms/vaga (476 vagas: ~230 ms para as
  duas funções). Nenhuma rede/estado.
- **Sem tradução quando inseguro**: título sem nenhum termo do glossário →
  `None` → a interface mostra só o original (9 títulos/476, ex.:
  "Students: Data Infrastructure Developer", "Fast Track to Leadership
  Trainee").

## 4. Exemplos reais antes/depois (run 476)

| Original (com tag de idioma) | PT-BR (campo derivado) |
|---|---|
| `Original (DE): Praktikum Data Analytics / Data Science` (STIHL, top 1) | `PT-BR: Estágio (Praktikum) · Análise de Dados / Ciência de Dados` |
| `Original (DE): Praktikant*in - Supply Chain Strategy und Logistikplanung ab November 2026` (Miebach) | `PT-BR: Estagiário(a) (Praktikant)*in - Cadeia de Suprimentos Strategy e Logística ab November 2026` |
| `Original (EN): Master's Thesis in Strategic Procurement - Direction for a New Business Segment` (Uniper) | `PT-BR: Tese de mestrado em Compras Estratégicas - Direction for a New Business Segment` |
| `Original (DE): Werkstudent (m/w/d) Digitalisierung & Data Analytics im Bereich General Service` | `PT-BR: Estudante / Working Student (Werkstudent) · Digitalização & Análise de Dados · na área de · Serviços Gerais` |
| `Original (DE): PRAKTIKUM IM BEREICH OPERATIONS PROCESSES DEVELOPMENT POLYMER` (top 1 Materials) | `PT-BR: Estágio (Praktikum) · na área de · Operações PROCESSES Desenvolvimento · Polímeros` |
| `Original: Fast Track to Leadership Trainee` (9 casos) | *(sem termos traduzíveis — só o original, correto)* |

Cobertura: **467/476 títulos (98%)** geram PT-BR; detecção de idioma: DE 308,
EN 135, n/d 33.

## 5. Como o score breakdown passou a ser explicado

Cada componente **real** do breakdown (perfil ativo) vira uma linha
`rótulo PT-BR + valor real + detalhe do que a componente mede`; componentes
**negativas** são separadas sob o título "o que reduziu a nota (penalidades
reais do breakdown)". Exemplo real (vaga STIHL, perfil principal):

```
por que esta vaga? (score e penalidades)
+12.00  Área      — termos da área alvo (Procurement, Supply Chain, BI, Analytics, Automação)
 +2.00  Idioma    — inglês essencial / alemão no título ou descrição
 +1.50  Skills    — competências do perfil citadas na descrição
 +1.00  Local     — Alemanha explícita (DE) / Berlim
 +1.00  Tipo      — marcador forte de vaga de estudante no título
 Total 17.50
```

No perfil Materials, os explicadores são próprios (`Materiais — termos do
núcleo de materiais…`, `Manufatura/Processo — manufatura/produção e
engenharia de processos`, `Penalidades — função de negócio no título…`) —
**os critérios nunca se misturam** (seletor de perfil da Fase 4). `penalties`
só aparece quando o breakdown traz valor negativo (283 linhas no conjunto
atual entre as duas tabelas); nenhuma penalidade nova foi criada.

## 6. Original continua disponível

O título original é sempre exibido abaixo do PT-BR com tag `Original
(EN/DE)`, e **é o link que abre o anúncio na fonte** (scheme http/https
validado, P2.3). A descrição em `details` é etiquetada `Original` e não é
traduzida. Nada substitui o conteúdo original.

## 7. Os dois perfis funcionam

Página com seletor `[Procurement / Supply Chain | Materials Engineering]`:
cada perfil tem sua tabela, seu ranking e sua explicação. A camada PT-BR é
comum (título/tipo/pais), mas o "por que esta vaga?" usa os rótulos e
explicadores **do perfil ativo**. Bloco real: 476/476 em cada tabela.

## 8. Ranking não alterado

Nenhuma linha de `ranking.py`/`materials_ranking.py`/`filters.py` mudou.
Evidências no `test_ptbr.py`:
- `render_html` não muta as vagas (deep-copy antes/depois idênticos);
- `data-score` e `data-rank` da página == valores do snapshot (ordem do
  pipeline preservada, biz e materials, 476 idênticos);
- determinismo de render (2 chamadas → mesmo HTML);
- suíte antiga 26/26 intacta após a mudança (mesmos checks verdes).

## 9. Testes executados

- Suíte **local 27/27 scripts — 1.345 checks — 0 falhas** (cwd `/home/ubuntu/internship-finder`).
- `test_ptbr.py` (novo): 59 checks — EN/DE, Procurement, Materials,
  Manufacturing, sem termos traduzíveis, sem campos opcionais, original
  visível, PT-BR visível, breakdown PT-BR, penalidades, perfil principal,
  perfil Materials, ranking antes/depois.
- `test_interface.py`: 136 checks — intacto após a Fase 5.
- **CI GitHub Actions**: aguardando rodar no PR (27 scripts).

## 10. URL do GitHub Pages

https://rios-vini.github.io/internship-finder/ (publicado após o merge —
mesmo fluxo `publish_pages.py`; o cron 06:00 America/Sao_Paulo regenera a
partir de `main`).

## 11. Documentação atualizada

README (seção "PT-BR na interface (Fase 5)" com a manutenção do glossário),
`docs/architecture.md` (camada PT-BR), PROJECT_STATUS (Completed + snapshot)
e MASTER_PLAN (Seção 1 + Log 19/09). Este relatório é o registro da fase.

## 12. Commits

- **#74** (PR `feature/fase5-ptbr-ranking-explanation`, squash `5e1cc95` no main).
- `src/internship_finder/ptbr.py` + `scripts/test_ptbr.py` — módulo + testes.
- `scripts/interface.py` + `.github/workflows/ci.yml` — integração + CI.
- `README.md`/`PROJECT_STATUS.md`/`MASTER_PLAN.md`/`docs/...` — docs.

## 13. Limitações conhecidas

- **Não é tradução fluente**: o glossário substitui termos em ordem original;
  títulos complexos ("Master's Thesis in Strategic Procurement - Direction
  for a New Business Segment") ficam parcialmente em EN (a parte traduzida é
  suficiente para entender o cargo/área; o original está logo abaixo).
- **Descrição nunca é traduzida** (decisão do dono): leia o anúncio
  original antes de aplicar — link sempre presente.
- **Gender agreement do PT-BR**: "Estagiário(a)", "Engenheiro(a)" etc. usam
  a forma neutra com parênteses (limitação do glossário, aceita).
- **9/476 títulos sem tradução** (sem termos no glossário) — por design.
- **Termos novos**: para cobrir novo jargão, adicionar entrada no
  `GLOSSARY` (frase composta antes da genérica) + teste; sem isso, o termo
  permanece no original (comportamento seguro).
- **Idioma do título** é por marcadores fortes (sem stoplist): títulos
  mistos são rotulados pelo marcador mais forte (ex.: "Praktikum Data
  Analytics" → `Original (DE)`), o que é o caso na maioria esmagadora dos
  anúncios alemães.