# F28 — Fit-gap de skills: dicionário, relatório e plano de upskilling

> Ferramenta **determinística e offline** que responde: *quais skills os
> anúncios de estágio exigem, com que frequência, e quais faltam no meu
> perfil?* — transformando as centenas de JDs já coletadas numa lista
> objetiva de estudo, ranqueada por frequência de mercado. Zero LLM, zero
> rede, zero integração com pipeline/cron: é uma ferramenta **sob demanda**.

## 1. Componentes

- **Dicionário versionado**: `src/internship_finder/skill_gap.py` — grupos
  canônicos de skills procurement/supply-chain/materials com sinônimos
  **DE/EN que contam juntos** (um grupo = uma linha do relatório). Exemplos:
  `sap` (SAP, SAP Ariba, Coupa, SAP MM), `demand_planning`
  (Bedarfsermittlung, Bedarfsplanung, demand planning, Disposition),
  `procurement` (Einkauf, Beschaffung, purchasing, procurement, sourcing).
- **Funções puras**: `extract_skills(text) -> [skill]` e
  `gap_report(jobs, profile_text) -> [SkillStats]` com
  `{skill, freq_title, freq_desc, freq_any, n_jobs, share_eligible,
  present_in_profile}` — mesmas entradas, mesma saída, sempre.
- **CLI**: `scripts/skill_gap_report.py` (seção 3).
- **Testes**: `scripts/test_f28.py` (26 checks, 100% offline, fixtures
  sintéticas) no array do CI (67→68 scripts).

## 2. Metodologia

1. **Universo**: o snapshot de eligible jobs (`data/eligible_jobs.json`,
   lista de dicts com `title`/`description`). Frequências são calculadas
   sobre o universo inteiro (N anúncios); `share_eligible = freq_any / N`.
2. **Calibração do dicionário**: os padrões foram selecionados contra uma
   amostra aleatória determinística de 40 JDs (seed=28) do snapshot de
   2026-10-12 (783 eligible, 704 com description) **e** contagens de
   frequência no corpus completo — o vocabulário é o que realmente aparece
   nos anúncios (Disposition, Bedarfsermittlung, Warenwirtschaftssystem,
   Category Management, Lieferantenverhandlungen...), não uma lista
   genérica de livro-texto. Sinônimos **PT-BR** foram adicionados para o
   lado do perfil (negociação, fornecedores, estoque/inventário, inglês,
   alemão, logística, análise de dados, gestão de projetos,
   sustentabilidade, metalografia/Vickers...) — verificados com sinal ZERO
   no corpus DE/EN, então afetam apenas a detecção no perfil, sem
   contaminar as frequências de mercado. Entradas sem sinal algum no corpus
   (ex.: Incoterms, MRP) aparecem no relatório com share 0.0%.
3. **Extração**: regex case-insensitive com word boundaries, um grupo
   por skill; um anúncio conta no máximo 1 por skill (presença, não
   ocorrência).
4. **Parser de profile**: o markdown do perfil é lido fora do repo
   (`--profile /caminho/absoluto`), extraíndo headings, bullets, linhas
   de tabela e linhas com rótulo (`:`/`**`), linhas ≤ 260 chars —
   tolerante a formatos, nunca levanta erro. **O texto do perfil nunca
   aparece no relatório gerado**: apenas o veredito booleano por skill
   (`yes`/`NO`).
5. **Relatório**: 3 seções — (a) top skills do mercado por frequência na
   description; (b) GAPS (pedidos pelo mercado, ausentes no perfil)
   ranqueados por share; (c) MATCHES (o perfil já mostra o que o mercado
   pede — reforço positivo).

## 3. Como rodar

```bash
# apenas o mercado (sem perfil):
.venv/bin/python scripts/skill_gap_report.py \
    --input data/eligible_jobs.json --top 40

# contra um perfil (arquivo PESSOAL — mantenha FORA do repo):
.venv/bin/python scripts/skill_gap_report.py \
    --input data/eligible_jobs.json \
    --profile /caminho/fora/do/repo/PERFIL.md \
    --top 40 --output /tmp/upskilling.md
```

Sem `--profile`: só a seção mercado é emitida. `--output -` (default)
escreve em stdout; `--top N` limita as linhas de cada seção.

### Exemplo com fixture sintética

Com 4 anúncios sintéticos e um perfil sintético (o exemplo completo,
reprodutível, vive em `scripts/test_f28.py` — T4), a saída tem a forma:

```markdown
# Skill-gap report — internship market vs profile

Universe: **4 eligible jobs** (4 with a description). ...

## 1. Top skills in the market (top 10 by description frequency)
| # | Skill | Category | freq title | freq desc | freq any | share of eligible | in profile |
|---:|---|---|---:|---:|---:|---:|---|
| 1 | Excel / spreadsheets | systems | 0 | 2 | 2 | 50.0% | yes |
...

## 2. GAPS — asked by the market, not present in the profile (top 10)
| # | Skill | ... | share of eligible | in profile |
|---:|---|---|---:|---|
| 1 | Einkauf / procurement | procurement | ... | 50.0% | NO |
...

## 3. MATCHES — the profile already shows what the market asks (top 10)
| # | Skill | ... | share of eligible | in profile |
...
```

(Nenhuma frase do perfil aparece — só `yes`/`NO` por skill.)

## 4. Limitações honestas

- **Dicionário ≠ NER**: a extração é matching de padrões versionados. Skills
  fora do dicionário não são detectadas (falso negativo); padrões amplos
  podem pegar menções contextuais (falso positivo). O dicionário é
  calibrado para o domínio procurement/supply/materials em DE/EN, não é
  cobertura universal.
- **Frequência ≠ exigência dura**: uma menção na description pode ser
  tarefa desejável, requisito obrigatório ou apenas contexto. O share
  responde "*quantos anúncios mencionam*", não "*quantos exigem*" — leia
  como sinal de mercado, não como filtro de aplicação. Rotulei os números
  como `share of eligible` por esse motivo.
- **Share sobre o universo inteiro**: skills de nicho podem parecer
  irrelevantes no agregado mas ser mandatórias num submercado (ex.:
  Zoll/customs em vagas de importação). Para decisões finais, cruze com a
  leitura das vagas-alvo.
- **Profile parsing simples**: o parser extrai headings/bullets/labels; um
  perfil em formato muito diferente (prosa densa, PDF) pode não ser lido
  por completo — o modo sem `--profile` (só mercado) é sempre disponível.
- **Determinismo pelo design**: nenhuma chamada de rede, nenhum LLM, nenhum
  RNG. Re rodar sobre o mesmo snapshot + perfil produz o mesmo relatório.

## 5. Privacidade

O perfil do candidato é dado pessoal e **nunca** é commitado, lido de
dentro do repo, ou copiado para arquivos versionados. A CLI aceita um
caminho absoluto externo, o texto não é embutido no relatório e os testes
usam fixtures sintéticas. O relatório em si contém apenas estatísticas
agregadas de skills do mercado e vereditos booleanos.
