# F34 — Apply-assist: rascunhos de candidatura por vaga (sob demanda)

> **LLM INFORMS, HUMANO DECIDE.** Esta camada gera RASCUNHOS que o dono
> EDITA antes de qualquer envio. UMA vaga por vez. Mass-apply e
> auto-submit são PROIBIDOS por design — o CLI não tem subcomando de envio,
> não importa bibliotecas de envio e não conhece nenhum destino além da
> API de LLM (invariante testada).

## O que é

`scripts/apply_assist.py` é um CLI **sob demanda** (não faz parte do
pipeline/cron/digest). Dado um `--job-id` do `eligible_jobs.json`, gera 4
arquivos de apoio à candidatura em `data/personal/apply_assist/<job-id>/`
(`data/` é gitignored — nada pessoal é versionado/publicado):

| Arquivo | Conteúdo | Fonte |
|---|---|---|
| `cover_letter.md` | DRAFT da carta (EN default; `--lang de` = alemão formal), estrutura comercial alemã: bloco de contato, saudação, 3 parágrafos, fecho. Header literal `DRAFT — revisar antes de enviar` | LLM (chamada 1) + perfil |
| `keyword_gap.md` | Skills do anúncio ausentes no perfil, com a variante literal da JD | Determinístico, SEM LLM (mini-dicionário local — a F28 `skill_gap.py` não está mergeada) |
| `interview_briefing.md` | 8–12 perguntas prováveis EXTRAÍDAS daquela JD (técnicas + comportamentais), cada uma com skeleton STAR em inglês apontando QUAL experiência do perfil usar; sem material no perfil → `[FALTA: …]` | LLM (chamada 2) + perfil |
| `visa_facts.md` | Frases jurídicas aprovadas (§16e, BeschV §15, piso €13,90/h, Werkstudent, rota >6 meses) — LITERAIS | ESTÁTICO, sem LLM |

## Como rodar

```bash
# ambiente (mesmo setup do repositório)
python3.12 -m venv .venv && .venv/bin/pip install -e .
export NVIDIA_API_KEY=…   # única fonte da key — nunca em arquivo

# uso (uma vaga por execução)
.venv/bin/python scripts/apply_assist.py \
    --job-id "BoschGroup|smartrecruiters:BoschGroup:744000141914929"

# opções
#   --input   data/eligible_jobs.json   (default)
#   --profile ~/.hermes/handoff/f8-maquina-candidatura/PERFIL-CANDIDATO.md  (default)
#   --lang    en|de   (default en; de = alemão formal)
#   --output  data/personal/apply_assist  (default; gitignored)
```

São 2 chamadas LLM por execução (carta + briefing), dentro do limite da
fase (1–3). Modelo: `z-ai/glm-5.3-flash` — NUNCA o glm-5.3 pesado (queima
max_tokens em raciocínio e devolve vazio; pitfall conhecido). O cliente é
o mesmo do enrichment (`src/internship_finder/enrichment/llm.py`, retry
3 tentativas com backoff 30/60s). Falha de API → erro claro e ZERO
arquivos escritos (nada parcial silencioso).

## O que é rascunho (regras de uso)

- **Nada aqui é enviado por este CLI.** Zero rede além da API de LLM —
  nenhum email, formulário, Telegram ou webhook (travado em
  `scripts/test_f34.py`: suíte roda com `socket.socket.connect` bloqueado).
- **Revise antes de enviar**: header DRAFT, placeholders `[CIDADE-EMPRESA]`,
  `[DATA]`, recrutador e anexos. Atualizar a data no dia do envio e
  estampar a assinatura (`stamp_signature.py` do handoff f8).
- **Anti-invenção**: o prompt proíbe terminantemente inventar experiência.
  O LLM só pode usar fatos do PERFIL-CANDIDATO.md; o que falta vira
  `[FALTA: …]`. O perfil marca o que é experiência familiar/informal e o
  que é simulação (Forage) — os rótulos são preservados.
- **Alemão honesto**: sempre A1–A2 em progresso (regra dura do perfil).
- **`keyword_gap.md` é informativo** — o dono decide se a vaga vale a
  pena, o que estudar antes da entrevista, ou se pula. "German Language"
  nunca é listado como gap (nível real declarado; exigência B2+ = vaga
  não aplicável, o filtro do pipeline já penaliza).

## Limitações (honestas)

- A carta gerada é um ponto de partida — a revisão humana é obrigatória
  (o sistema não sabe o que mudou na empresa esta semana).
- O mini-dicionário de skills cobre o vocabulário procurement/supply/data
  do projeto; termos exóticos da JD podem passar batidos (conservador por
  design: prefere não apontar a apontar errado).
- O briefing de entrevista deriva SÓ da descrição da vaga no
  `eligible_jobs.json`; JDs com pouca descrição geram perguntas mais
  genéricas.
- visa_facts.md é referência rápida, não aconselhamento jurídico — as
  frases mandam confirmar procedimento com consulado/Ausländerbehörde.
- `--profile` aponta para arquivo PESSOAL (`PERFIL-CANDIDATO.md` do
  handoff f8) — NUNCA commitado; outputs individuais ficam em
  `data/personal/` (gitignored) ou `/tmp`.

## Testes

`scripts/test_f34.py` (68ª suíte do CI, 100% offline, FakeTransport):
contrato do CLI (job-id/input/perfil/key ausentes), outputs no path
gitignored, header DRAFT literal, estrutura da carta, determinismo do
keyword_gap, 8–12 perguntas com STAR/[FALTA], frases jurídicas literais
(asserts de substring), falha de API (429×3, JSON incompleto, questions<8
→ SystemExit e ZERO arquivos), e a invariante ZERO-REDE (sockets
bloqueados; nenhum import de envio; destino único = endpoint LLM).
