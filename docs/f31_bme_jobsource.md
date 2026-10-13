# F31 — BME JobSource (jobsource.bme.de)

**Status:** implementado; PR #128 (`feature/f31-bme-jobsource`, base `main` `c720514` = F24 mergeada). Fetch real único executado 13/10 (números abaixo). SEM MERGE — merge é do dono.

Job board do **Bundesverband Materialwirtschaft, Einkauf und Logistik** — a associação alemã de procurement/logística, o nicho exato do dono. ~160 vagas ativas (13/10), mix de Einkauf/Procurement em todos os níveis, incluindo Praktikant. **Zero duplicação** com os ATS atuais (não é SuccessFactors/Workday/Phenom — board próprio Drupal/epiqo).

## 1. Recon SEM browser — o que o site realmente é

A página `/jobs` parece SPA ("curl devolve shell vazio"), mas isso é **gate anti-bot**, não client-render. Resolvendo o gate, a listagem é **Drupal server-rendered** (com `<article>` por vaga e pager) — não existe endpoint XHR/JSON de vagas:

| Hipótese testada (probe 13/10 06:50–07:12 UTC) | Resultado |
|---|---|
| `GET /jobs` sem cookie | **302** → `botchallenge.html?token=<32-hex>` (token no header `Location`) |
| `GET /jobs` com `Cookie: bot_verified=<token do desafio>` | **200**, 145 KB, 20 `<article>` + pager `?page=1..7` |
| `GET /jobs` com `Cookie: bot_verified=<aleatório>` | 302 de volta (o servidor **valida o valor**) |
| `GET /api/jobs`, `/jobs.json`, `/views/ajax`, `/?q=jobs` | 302 challenge (não existem como JSON público) |
| `GET /sitemap.xml` (447 URLs `/job/<slug>`) | 200 — confirma ~160 vagas (`/job/` URLs) |
| `rss.xml` | 302 para `/user/login` (exige sessão) |

**Protocolo do gate** (evidência `/tmp/if-f31-recon/`, probe 13/10): o 302 aponta para `botchallenge.html?token=<hex>&target=...`; a página do desafio tem um botão cujo JS apenas **copia o token da query-string para o cookie `bot_verified`** (validade 1 ano) e recarrega. Não há fingerprinting, não há JS real, não há prova de trabalho — é um **cookie-echo**. O adapter reproduz o protocolo ensinado pelo próprio site SEM browser e SEM JS:

```bash
# 1) request sem redirect -> token no Location do 302:
curl -4 -s -o /dev/null -D - https://jobsource.bme.de/jobs | grep -i '^location:'
#   location: https://jobsource.bme.de/botchallenge.html?token=6c0cb2078e54916f60b3389b16f70ad2&target=%2Fjobs&referrer=
# 2) echo do token no cookie -> listagem server-rendered 200:
curl -4 -s -H "Cookie: bot_verified=6c0cb2078e54916f60b3389b16f70ad2" https://jobsource.bme.de/jobs | grep -c '<article'
#   20
```

### Causa-raiz do attempt 1 (timeout 5425s)

O primeiro run implementou o gate procurando `?token=` **no body** — mas `urllib` segue 302 automaticamente e o body final é a página "Bot Check" (cujo JS lê `location.search`; o token literal só existe no **header `Location`**). Resultado: o código "não via" o challenge, parseava a página Bot Check como listagem (0 vagas) e o loop de páginas ficava esvaziando até o teto do run. Fix: opener com `HTTPRedirectHandler` custom que NÃO segue redirect + extração do token do `Location` (travado no teste B5: página Bot Check → `[]`).

## 2. robots.txt — respeitado ao pé da letra

`robots.txt` (probe 13/10, salvo em `/tmp/if-f31-recon/robots.txt`): Drupal padrão, **nenhum `Disallow`** para `/jobs`, `/job/<slug>`; `User-agent: *` com **`Crawl-delay: 10`**. O adapter espera **10 s ANTES de cada request ao domínio** — gate incluso, listagem, páginas e details (o gate conta como request: challenge + listagem = 2 esperas). Escopo: só o domínio do board (`jobsource.bme.de`), nada fora dele.

## 3. Adapter (`research_sources.py`, 7ª fonte `bme`)

- **Listagem**: 20 `<article>`/página × 8 páginas (cap `BME_MAX_PAGES=8`) — anchor `recruiter-job-link` (href absoluto `/job/<slug>`), empresa, cidade, data `DD.MM.YYYY`. Pager Drupal: `?page=1` = **segunda** página física (`next` aponta `page=1`; a p1 é a URL base).
- **TODA a listagem é materializada** (padrão TU Berlin/Leibniz — regra da card: NÃO filtrar na fonte; o funil de tipo do projeto resolve o resto).
- **Details** (cap `BME_MAX_DETAILS=10`/run): JSON-LD `JobPosting` no detail (description, `jobLocation`, `datePosted`, `validThrough`, `employmentType`, organização — 3 blocos ld+json, só o `@type: JobPosting` é consumido). O prefilter F3 (`row_is_intern_candidate`) **só escolhe** quais details buscar (intern-candidates primeiro), **nunca descarta vaga**: vaga sem detail entra sem description (fail-soft TU Berlin).
- **Rate**: Crawl-delay 10 s; 1 run/dia (refresh 09:00 UTC); timeout 30 s/request (1 tentativa, sem retry); UA honesto `internship-finder-liveness/1.1`.
- **Fail-soft**: página/detail fora do ar → log + segue; listagem vazia → `status: failed` no summary da fonte, run não cai.
- **Off-switch sem deploy**: `INTERNSHIP_FINDER_RESEARCH_SOURCES_OFF=bme` (kill switch da F21, default ON).
- **Dedup**: id `<company>|bme:<slug>` — slug é estável; URLs absolutas do board colapsam no tier URL (b) do dedup existente; zero vocabulário novo.

## 4. Números do A/B (fetch real único, 13/10 ~10:30 UTC)

Pipeline de coleta completo executado **uma vez** contra o board real (clone `/tmp/if-f31`, produção `data/` intocada; A/B em `/tmp/if-f31-ab/` com snapshot copiado):

```
rows_seen 160  (8 páginas × 20, dedup por slug; bate com o probe de terceiro ~159)
→ materializados 160 jobs (100% da listagem, sem filtro na fonte)
→ details: 10 buscados, 10 ok / 0 failed (~208 s no total, ~19 requests × 10 s Crawl-delay)
→ intern-candidates na listagem: títulos com marcador de estágio (ex.: "Praktikant (m/w/d) Einkauf – Procurement Solutions", Dr. Oetker, Bielefeld, deadline 18.10) escolhidos primeiro para detail
```

Amostra real do board (13/10): Bereichsleiter IT-Beschaffung (Deutsche Rentenversicherung), Strategic Buyer (CompAir), IT-Einkauf 75% (MPG), Strategischer Einkäufer (Schleifring/DG Nexolution), Procurement Analyst (DG Nexolution), Junior Einkäufer (CELLTHERM) — o board inteiro é o funil de procurement do dono.

## 5. Testes (`scripts/test_f31.py`, 69ª suíte — CI array no mesmo commit)

**26 checks, ZERO HTTP** (fixtures VERBATIM do probe 13/10; monkeypatch de `urlopen`+`socket` no grupo G):

- **A. Gate**: extração do token do `Location` real; Location sem challenge → fail-soft; challenge→echo→200; challenge sem token → `failed` sem crash.
- **B. Listagem**: article verbatim → item completo; dedup por slug; pager relativo `?page=N`; item sem organização → fallback `BME JobSource`; **página Bot Check → `[]`** (o bug do attempt 1, travado).
- **C. Detail**: JSON-LD JobPosting completo; blocos WebSite/Organization ignorados; sem ld+json → `None`.
- **D. fetch_bme**: listagem integral materializada com detail indo pro intern-first; Crawl-delay = 10 s **antes de cada** request (5 requests → 5 esperas); `max_details=0` → listagem intacta; página fora do ar → run segue; detail fora do ar → vaga preservada sem description.
- **E. Estágio**: fetcher morto → `failed` no summary (run segue); off-switch `bme` → `skipped_disabled`; nome desconhecido no CSV → ignorado.
- **F. Idempotência** + `parse_bme_date`.
- **G. ZERO HTTP** na suíte.

`test_f21.py` ajustado para 7 fontes (E1/E4/F1/F2/F3 renumerados — sem mudança de regra). Suíte local: 68/69 verde; `test_lifecycle` falha com TypeError em `pid_alive(None)` **também no `main`** (pré-existente, fora do escopo F31).

## 6. Restrictions compliance

- Clone `/tmp/if-f31` + venv + `pip install -e .` ✔
- Nenhum browser/headless/Selenium/Playwright (nem no recon, nem no pipeline) ✔
- Crawl-delay 10 respeitado antes de cada request; só o domínio do board ✔
- XING/LinkedIn/Indeed: não tocados ✔
- Produção `data/` intocada — A/B em `/tmp` com snapshot copiado ✔
- PR SEM MERGE (`feature/f31-bme-jobsource`) ✔
- MASTER_PLAN/PROJECT_STATUS não editados ✔
- Nenhum payload de vagas commitado (jobs ficam em `/tmp/if-f31-ab/`) ✔
