"""Registry operacional de empresas da coleta (fonte de verdade).

Substitui a lista de empresas que hoje vive copiada no README/docs e era colada
manualmente no ``--companies``. Cada entrada traz o **nome canônico de coleta**
(a consulta usada no ``--companies`` / ``collect_company``) e, quando o tenant
da base é conhecido, o ATS/tenant de referência. ``enabled`` habilita/desabilita
a empresa sem editar texto corrido.

O ``status``/``última coleta`` por empresa NÃO é duplicado aqui: é derivado do
JSONL de métricas existente (``data/collection_metrics.jsonl``), que já registra
o estado por tenant com o nome da empresa. O registry apenas materializa o
agregado por empresa de forma read-only e defensiva (registro malformado nunca
derruba). Assim o estado operacional tem uma única fonte (o JSONL) e o registry
expõe a **configuração** (quais empresas, habilitadas, tenant de referência).

A **consistência** entre o tenant declarado no registry e o tenant que o
runtime de fato resolve/coleta é verificável por ``tenant_consistency_report``
(configuração x resultado real, classificação por empresa — ver docstring da
função) e exposta pelo ``--health`` (chave ``registry_consistency``).

TENANT COMPARTILHADO ``phenom:nan`` (F81): o slug ``nan`` é o identificador
LITERAL de um tenant Phenom compartilhado da base upstream — declarado aqui
para DHL/Allianz/Merck/Kuehne+Nagel e resolvido em runtime (sem declaração)
também para ABB/Philips/Roche/BCG. NÃO é NaN/bug do pandas nem erro a
purgar/renomear: a série é saudável (32/32 runs ``ok``; 1.064–1.115
vagas/dia na medição do F49 §2.1, 17/10/2026, registro ``type: tenant`` do
JSONL de métricas) e o guard de regressão vive em ``scripts/test_f81.py``
(lista estável de declarantes + fixture verbatim + contra-caso do
KEY_BUILD). A sanidade de KEY_BUILD (F80) mira ``ats_type`` de FATIA do
dataset (``sf_dataset:<ats_type>``) — nunca este slug de TENANT.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class RegistryEntry(BaseModel):
    """Uma empresa operacional da coleta (configuração, não resultado)."""

    name: str  # nome canônico de coleta (consulta do --companies)
    ats: str | None = None  # ATS de referência quando conhecido (ex.: "successfactors")
    tenant: str | None = None  # tenant de referência na base (ex.: "successfactors:jobs")
    enabled: bool = True  # false desabilita a empresa sem removê-la do registry


# --- Seed: 159 empresas operacionais (12 da validação inicial + 27 da
# --- expansão E2 + 25 da expansão internacional P3 #23: 8 DE + 17 NL/CH/AT
# --- + 17 da expansão de cobertura 15/09/2026 + 6 da auditoria 16/09/2026
# --- + 9 da auditoria próxima fronteira 17/09/2026 + 5 da última onda de
# --- cobertura 18/09/2026: Sungrow EMEA, AutoScout24, Huawei Research Center
# --- Germany, EAT HAPPY GROUP, VDI Technologiezentrum GmbH
# --- + 9 da onda de fontes F16 08/10/2026: Brenntag, ALTANA Job Portal,
# --- Atlas Copco Group, SKF, Decathlon Digital EN, DSV, Heidelberg Materials,
# --- Sandvik, Rhenus
# --- + 17 da onda F32 Hidden Champions 13/10/2026: Blickle, Bundesdruckerei,
# --- Delo, EBM-Papst, ElringKlinger, Freudenberg, Karlstorz, KAESER Careers,
# --- Körber Group | Job Market, Jobs - Multivac, Ottobock Karriereportal,
# --- Mapal Group, Jobs | LEMKEN The Agrovision Company, Grammer, Leoni,
# --- Walter, Rational
# --- + 18 da onda F88 top-up de frescor 21/10/2026: KPMG DE, Vetter, AGCO,
# --- mllerservi (Theo Müller), Deutsche Börse, Witglobal (Würth), Levio,
# --- Indie Campers, Vitesco, Marquardt Group, Kraft Heinz, aumovio,
# --- Vodafone, Vanderlande, Stryker, Endress+Hauser, Pirelli, GALERIA
# --- + 2 da onda F100 curadoria EN-source 22/10/2026: Issgovernance,
# --- JACOBS DOUWE EGBERTS
# --- + 4 da onda F123 RMK wave-3 25/10/2026: MAHLE, Aldi Süd, E.ON, KUKA
# --- (RSS por keyword em tenants RMK/J2W, pubDate + description embutida).
# --- Nomes canônicos = consulta real do ``--companies``
# --- (README.md + docs/empresas_verificacao.md + docs/relatorio_expansao.md +
# --- docs da auditoria de cobertura 15/09 + auditoria próxima onda 16/09).
# --- Tenant/ATS de referência preenchidos a partir dos docs quando conhecidos;
# --- ``None`` deixa "a base decide" (find_company resolve o tenant em runtime).
SEED = [
    # --- 12 da validação inicial (2026-08-10) ---
    RegistryEntry(name="Bosch", ats="smartrecruiters", tenant="smartrecruiters:BoschGroup"),
    RegistryEntry(name="SAP", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Continental", ats="smartrecruiters", tenant="smartrecruiters:continental"),
    RegistryEntry(name="ZF", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Bayer", ats="eightfold", tenant="eightfold:bayer"),
    RegistryEntry(name="BASF", ats="successfactors", tenant="successfactors:basf"),
    RegistryEntry(name="Henkel", ats="cornerstone", tenant="cornerstone:henkel"),
    RegistryEntry(name="Infineon", ats="eightfold", tenant="eightfold:infineon"),
    RegistryEntry(name="Zalando", ats="workday", tenant="workday:zalando/zalandositewd"),
    RegistryEntry(name="Delivery Hero", ats="smartrecruiters", tenant="smartrecruiters:deliveryhero"),
    RegistryEntry(name="Covestro", ats="workday", tenant="workday:covestro/cov_external"),
    RegistryEntry(name="Evonik", ats="workday", tenant="workday:evonik/external_careers"),
    # --- 27 da expansão E2 (2026-08-12) ---
    # DHL — 1º declarante do tenant COMPARTILHADO ``phenom:nan``. O slug
    # "nan" é o identificador LITERAL do tenant Phenom na base upstream
    # (artefato do manifest adotado como slug), NÃO um NaN/bug do pandas:
    # série saudável 32/32 runs ok; 1.064–1.115 vagas/dia (medição F49
    # §2.1, 17/10/2026, registro ``type: tenant`` do JSONL de métricas).
    # Serve no registry: DHL/Allianz/Merck/Kuehne+Nagel; só em runtime
    # (resolução dinâmica, não declarada): ABB/Philips/Roche/BCG. Nenhuma
    # fase futura deve tratar ``phenom:nan`` como NaN a purgar/renomear —
    # o quase-erro do prompt da F80 (ats_type "nan" → loud) mira FATIA do
    # dataset, não slug de TENANT. Guard: scripts/test_f81.py.
    RegistryEntry(name="DHL", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Hellmann", ats="workday", tenant="workday:hellmann/hellmannexternaljobs"),
    # Lidl: o RCM do successfactors serve o feed completo
    # (https://jobs.lidl/sitemal.xml) gerado SOB DEMANDA, sem cache (TTFB
    # ~10s; medido 17/09: 120 MB em 6 min com a conexao ainda aberta). O
    # timeout de tenant (60s + 25s de margem) nunca e suficiente; corrigir
    # exigiria timeout global de ~15 min + ~150 MB de XML/dia para 1 empresa.
    # Externo ao projeto: falha conhecida legitima (timeout recorrente).
    RegistryEntry(name="Lidl", ats="successfactors", tenant="successfactors:lidlstiftuP2"),
    RegistryEntry(name="Kaufland", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="VWAGLPPROD10", ats="successfactors", tenant="successfactors:VWAGLPPROD10"),
    RegistryEntry(name="Schaeffler", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Mahle", ats="successfactors", tenant="successfactors:mahleinter"),
    RegistryEntry(name="Trumpf", ats="workday"),
    RegistryEntry(name="SICK AG", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Voith", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="knorrbremsP2", ats="successfactors", tenant="successfactors:knorrbremsP2"),
    RegistryEntry(name="brosefahrz", ats="successfactors", tenant="successfactors:brosefahrz"),
    RegistryEntry(name="Phoenix Contact", ats="greenhouse", tenant="greenhouse:phoenixcontact"),
    RegistryEntry(name="KraussMaffei", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="kronesag", ats="successfactors", tenant="successfactors:kronesag"),
    RegistryEntry(name="bbraunprd", ats="successfactors", tenant="successfactors:bbraunprd"),
    RegistryEntry(name="Sartorius", ats="workday", tenant="workday:sartorius/sartoriuscareers"),
    RegistryEntry(name="freseniusglobal", ats="workday", tenant="workday:freseniusglobal/fse"),
    RegistryEntry(name="Deutsche Telekom", ats="eightfold", tenant="eightfold:telekom-growthhub"),
    RegistryEntry(name="Celonis", ats="greenhouse", tenant="greenhouse:celonis"),
    RegistryEntry(name="DATEV", ats="workday"),
    RegistryEntry(name="Statista", ats="ashby", tenant="ashby:statista"),
    RegistryEntry(name="Scout24", ats="greenhouse", tenant="greenhouse:scout24"),
    # F58 (18/10): Siemens Healthineers MIGROU de ATS (Avature -> Phenom,
    # ~fim 09/2026 — F49 secao 2.5: a URL avature responde 302 para
    # careers.siemens-healthineers.com/global/en e o scraper antigo parseia
    # 0 vagas = "empty" silencioso por 19+ runs, com a empresa viva e
    # contratando). Tenant phenom VALIDADO AO VIVO com fetch real pelo
    # caminho exato do pipeline (823 vagas em ~3s, defaults do scraper).
    # O manifest upstream AINDA resolve so a linha avature morta (verificado
    # ao vivo 18/10), entao a coleta usa o override de migracao
    # TENANT_ATS_OVERRIDES (collectors/ats_scraper.py) — remove-lo quando o
    # upstream atualizar a linha. Evidencias e A/B: relatorio F58
    # (~/.hermes/handoff/f58-siemens-phenom/).
    RegistryEntry(name="Siemens Healthineers", ats="phenom", tenant="phenom:https://careers.siemens-healthineers.com"),
    RegistryEntry(name="Zeiss Group", ats="workday", tenant="workday:zeissgroup/external"),
    RegistryEntry(name="draegerP", ats="successfactors", tenant="successfactors:draegerP"),
    RegistryEntry(name="Uniper", ats="successfactors", tenant="successfactors:jobs"),
    # --- 8 da expansão internacional P3 #23 (2026-09-08) — Lote A (DE) ---
    # Validadas com scripts/verify_companies.py --fetch (match exato + scraper
    # + fetch real OK >0 vagas); tenant copiado da saída (sem invenção).
    # Otto (jazzhr:otto) REMOVIDA em 15/09: falso positivo — otto.applytojob.com
    # não é o Otto Group (auditoria de cobertura; ver seção J.8).
    # Allianz — declara o tenant COMPARTILHADO ``phenom:nan`` (slug "nan"
    # LITERAL da base upstream — NÃO NaN/bug; ver bloco da DHL acima e
    # scripts/test_f81.py). Série saudável: 1.757 vagas no run 19/10/2026.
    RegistryEntry(name="Allianz", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Adidas", ats="moka", tenant="moka:adidas/140456"),
    RegistryEntry(name="Puma", ats="workday", tenant="workday:puma/jobs_at_puma"),
    RegistryEntry(name="Hella", ats="cornerstone", tenant="cornerstone:hella"),
    RegistryEntry(name="Fraunhofer", ats="successfactors", tenant="successfactors:fraunhofer"),
    # Merck — declara o tenant COMPARTILHADO ``phenom:nan`` (slug "nan"
    # LITERAL da base upstream — NÃO NaN/bug; ver bloco da DHL acima e
    # scripts/test_f81.py). Série saudável: 359 vagas no run 19/10/2026.
    RegistryEntry(name="Merck", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Boehringer Ingelheim", ats="successfactors", tenant="successfactors:BoehringerPRD"),
    RegistryEntry(name="HelloFresh", ats="greenhouse", tenant="greenhouse:hellofresh"),
    # --- 17 da expansão internacional P3 #23 (2026-09-08) — Lote B (NL/CH/AT) ---
    RegistryEntry(name="Philips", ats="workday", tenant="workday:philips/jobs-and-careers"),
    RegistryEntry(name="ING", ats="workday", tenant="workday:ing/icsnldgen"),
    RegistryEntry(name="Heineken", ats="successfactors", tenant="successfactors:C0000032666P"),
    RegistryEntry(name="Adyen", ats="greenhouse", tenant="greenhouse:adyen"),
    RegistryEntry(name="Nestlé", ats="successfactors", tenant="successfactors:jobdetails"),
    RegistryEntry(name="Novartis", ats="workday", tenant="workday:novartis/novartis_careers"),
    RegistryEntry(name="ABB", ats="workday", tenant="workday:abb/External_Career_Page"),
    RegistryEntry(name="Red Bull", ats="smartrecruiters", tenant="smartrecruiters:RedBull"),
    RegistryEntry(name="Roche", ats="workday", tenant="workday:roche/roche-ext"),
    RegistryEntry(name="Swiss Re", ats="successfactors", tenant="successfactors:careers"),
    RegistryEntry(name="Schindler", ats="successfactors", tenant="successfactors:job"),
    RegistryEntry(name="Shell", ats="workday", tenant="workday:shell/shellcareers"),
    RegistryEntry(name="Unilever", ats="workday", tenant="workday:unilever/unilever_experienced_professionals"),
    # F72 (20/10): AkzoNobel migrou de successfactors para phenom ~29/09/2026
    # — feed legacy sitemal.xml em 500 cronico desde ent (22 runs
    # FETCH_ERROR collected=0) com o portal VIVO na plataforma Phenom
    # (careers.akzonobel.com/gb/en HTTP 200). Tenant phenom validado AO VIVO
    # (F72, caminho exato do pipeline): 225 vagas em ~2s. O manifest
    # upstream AINDA resolve so a linha successfactors:careers -> a coleta
    # usa o override de migracao TENANT_ATS_OVERRIDES
    # (collectors/ats_scraper.py; mesmo padrao F58 do Siemens Healthineers)
    # — remover quando o upstream atualizar a linha. Evidencia e serie
    # completa: relatorio F72 (~/.hermes/handoff/f72-auditoria-127/).
    RegistryEntry(name="AkzoNobel", ats="phenom", tenant="phenom:https://careers.akzonobel.com"),
    RegistryEntry(name="Rabobank", ats="workday", tenant="workday:rabobank/jobs"),
    RegistryEntry(name="NXP", ats="workday", tenant="workday:nxp/careers"),
    RegistryEntry(name="OMV", ats="successfactors", tenant="successfactors:omvagPRD"),
    # --- 17 da expansão de cobertura (2026-09-15, auditoria de cobertura) ---
    # Validadas AO VIVO em 15/09 com scripts/verify_companies.py --fetch (match
    # exato + scraper + fetch real); tenant copiado da RESOLUÇÃO REAL do runtime
    # (find_company), não do nome amigável — o tenant declarado precisa existir
    # no conjunto resolvido para o relatório de consistência não apontar drift.
    # Nomes canônicos = consulta de coleta (slug quando o nome natural não
    # resolve exato: BAUHAUS->bahagag, MediaMarkt->mediasatur, About You->
    # aboutyougmbh).
    RegistryEntry(name="Liebherr", ats="successfactors", tenant="successfactors:LiMySLive"),
    RegistryEntry(name="STIHL", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Simon-Kucher", ats="cornerstone", tenant="cornerstone:simon-kucher"),
    RegistryEntry(name="bahagag", ats="successfactors", tenant="successfactors:bahagag"),
    # F59 (19/10) — BCG: o widget BambooHR (embed2.php) passou a servir JSON
    # PURO (probe ao vivo 19/10: HTTP 200, 623 bytes, Accept-agnóstico) com
    # as MESMAS vagas Remote dentro (departments[].positions[]); o parser
    # HTML do pacote upstream (marcador bhrPositionID_) acha 0 vagas =
    # "empty" silencioso desde 08/10. Quebra de PARSE, não fim das vagas.
    # Conserto na camada do defeito (decisão F49 §2.6): PR #300 no upstream
    # kalil0321/ats-scrapers — parser tolerante ao JSON (detecção
    # content-based), mesmo formato de saída do caminho HTML.
    # F59.1 (19/10): o parser do PR #300 está VENDADO em
    # upstream_patches/bamboohr.py — patch SELF-REMOVÍVEL (auto-detect no
    # ponto de uso: o pacote INSTALADO é sondado contra o fixture BCG
    # verbatim; pacote com fix = bypass total, sem fix = patch ativo;
    # kill switch INTERNSHIP_FINDER_UPSTREAM_PATCH_BAMBOOHR, default ON).
    # Janela de divergência com o upstream: ZERO. O zero_return do health
    # cessa no 1º cron pós-merge DESTE repo (a coleta volta a achar as
    # vagas); quando o upstream mergear+release+upgrade, o patch vira
    # no-op sozinho e o canário (d) da suíte test_f59_1 força a remoção
    # (checklist no topo do módulo). Evidência: relatório F49 §2.6 + F59
    # + F59.1.
    RegistryEntry(name="BCG", ats="bamboohr", tenant="bamboohr:bcg"),
    RegistryEntry(name="mediasatur", ats="successfactors", tenant="successfactors:mediasatur"),
    RegistryEntry(name="Tchibo", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="HORNBACH", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="aboutyougmbh", ats="smartrecruiters", tenant="smartrecruiters:aboutyougmbh"),
    RegistryEntry(name="Hager Group", ats="successfactors", tenant="successfactors:HagerGroup"),
    RegistryEntry(name="Lanxess", ats="successfactors", tenant="successfactors:lanxessP"),
    RegistryEntry(name="Linde", ats="cornerstone", tenant="cornerstone:linde"),
    RegistryEntry(name="Sonepar", ats="successfactors", tenant="successfactors:career"),
    RegistryEntry(name="Flix", ats="greenhouse", tenant="greenhouse:flix"),
    # Kuehne+Nagel: phenom:nan (jobs.kuehne-nagel.com) e o tenant validado.
    # O runtime tambem resolve cornerstone:kuehne-nagel (manifest upstream):
    # kuehne-nagel.csod.com NAO resolve (NXDOMAIN — careersite extinto, K+N
    # migrou para phenom). FETCH_ERROR recorrente esperado por run; sem
    # exclusao per-tenant legitima (registry declara referencia, base decide).
    # F81: phenom:nan é o tenant COMPARTILHADO cujo slug "nan" é LITERAL da
    # base upstream (NÃO NaN/bug — ver bloco da DHL acima e test_f81). A
    # série DESTE tenant é a evidência da medição F49 §2.1: 1.064–1.115
    # vagas/dia, 32/32 runs ok (17/10/2026; registro verbatim no test_f81).
    RegistryEntry(name="Kuehne+Nagel", ats="phenom", tenant="phenom:nan"),
    RegistryEntry(name="Vattenfall", ats="smartrecruiters", tenant="smartrecruiters:Vattenfall"),
    RegistryEntry(name="4flow", ats="workday", tenant="workday:4flow/4flow"),
    # --- 6 da auditoria de cobertura 16/09/2026 (próxima onda) ---
    # Identidades validadas AO VIVO em 16/09 (fetch real read-only; ver
    # /home/ubuntu/auditoria_proxima_onda_2026-09-16.md). BMW AG, Jobs Festo,
    # Wacker e Webasto Jobportal COMPARTILHAM successfactors:jobs mas têm URLs
    # de manifest distintas (jobs.bmwgroup.com / jobs.festo.com /
    # jobs.wacker.com / jobs.webasto.com) — o coletor desambigua por URL
    # (URL_SLUG_ATS), nunca pelo slug genérico "jobs" (padrão
    # STIHL/Tchibo/HORNBACH 15/09; regra da auditoria 16/09).
    # Nome canônico = nome EXATO do manifest quando ele não resolve pelo nome
    # natural (Jobs Festo, Webasto Jobportal, Wacker) — nunca deduzir a
    # empresa pelo slug compartilhado. SMA resolve também o tenant oracle
    # `fa-exow-saasfaprod1/cx_1` (manifest upstream, name="SMA"): identidade
    # confirmada 17/09 = HOMÔNIMO — academia marítima em Sharjah/UAE (7 vagas
    # faculty, Marine Engineering/Maritime Business; site vivo). Slug do
    # manifest é relativo e o scraper oracle exige URL completa (oracle ∉
    # URL_SLUG_ATS) → FETCH_ERROR recorrente esperado por run. NÃO corrigir
    # via URL_SLUG_ATS (coletaria entidade não validada) nem excluir
    # oracle-específico (decisão 17/09). Unidade falha nunca entra no
    # SQLite/lifecycle (P1.2).
    RegistryEntry(name="BMW AG", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="SMA", ats="successfactors", tenant="successfactors:sma"),
    RegistryEntry(name="Jobs Festo", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Wacker", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Webasto Jobportal", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Roland Berger", ats="smartrecruiters", tenant="smartrecruiters:rolandberger"),
    # --- 9 da auditoria próxima fronteira (2026-09-17, READ-ONLY; relatório
    # --- /home/ubuntu/auditoria_proxima_fronteira_2026-09-17.md) ---
    # Validadas AO VIVO em 17/09 com fetch real read-only (manifest 80.390
    # empresas; funil oficial student/área/pais): todas com eligible DE>0
    # medido. Nome canônico = nome EXATO do manifest quando o nome natural
    # resolve falso positivo ou zero (regra da auditoria 16/09): "audibene /
    # hear.com" desambigua das 4 entradas audibene (join/personio/teamtailor
    # também existem) e "cbs Corporate Business Solutions GmbH" evita o FP
    # workable:cbs-9 (name "CBS"). O match EXATO do CompanyCollector
    # short-circuita o fallback token, então homônimas com name diferente não
    # entram na coleta (Picnic→só greenhouse:teampicnic, não "Picnic
    # Delivery"; Engelhart→só greenhouse, não join.com "Engelhart & Dirr";
    # Holzland Becker→só recruitee, não softgarden "Manfred Scherf
    # Holzfachhandel"). Tenants copiados da RESOLUÇÃO REAL do runtime.
    RegistryEntry(name="Picnic", ats="greenhouse", tenant="greenhouse:teampicnic"),
    RegistryEntry(name="AIXTRON SE", ats="softgarden", tenant="softgarden:aixtron"),
    RegistryEntry(name="CarOnSale", ats="greenhouse", tenant="greenhouse:caronsale"),
    RegistryEntry(name="cbs Corporate Business Solutions GmbH", ats="recruitee", tenant="recruitee:cbsconsulting"),
    RegistryEntry(name="CURRENTA GRUPPE", ats="recruitee", tenant="recruitee:currentagruppe"),
    RegistryEntry(name="Engelhart", ats="greenhouse", tenant="greenhouse:engelhart"),
    RegistryEntry(name="Holzland Becker", ats="recruitee", tenant="recruitee:holzlandbecker"),
    RegistryEntry(name="Miebach Consulting GmbH", ats="recruitee", tenant="recruitee:miebachconsulting"),
    RegistryEntry(name="audibene / hear.com", ats="greenhouse", tenant="greenhouse:audibenehearcom"),
    # --- 5 da última onda de cobertura (2026-09-18, última busca ampla) ---
    # Validadas AO VIVO em 18/09 com fetch real read-only (manifest 80.390
    # empresas; funil oficial student/área/pais) — todas com eligible DE>0
    # medido. Nomes canônicos = nomes EXATOS do manifest (resolução única de
    # tenant, conferida com CompanyCollector): "sungrow-emea" (o nome
    # comercial "Sungrow EMEA" NÃO resolve — mesmo padrão bahagag/
    # mediasatur), "AutoScout24" (board distinto do group Scout24 já
    # presente, greenhouse:scout24; empresa efetiva nos jobs = AutoScout24),
    # "Huawei Research Center Germany", "EAT HAPPY GROUP",
    # "VDI Technologiezentrum GmbH". Sungrow e AutoScout24 só renderam
    # eligible após a melhoria GENÉRICA de country inference (18/09,
    # countries.py): padrões "<País> - <Cidade>" (personio) e
    # "<Cidade> (<País>)" (greenhouse) — ver PR; sem geocoding externo.
    RegistryEntry(name="sungrow-emea", ats="personio", tenant="personio:sungrow-emea"),
    RegistryEntry(name="AutoScout24", ats="greenhouse", tenant="greenhouse:autoscout24"),
    RegistryEntry(name="Huawei Research Center Germany", ats="teamtailor", tenant="teamtailor:huaweiresearchcentergermanyaustria"),
    RegistryEntry(name="EAT HAPPY GROUP", ats="teamtailor", tenant="teamtailor:eathappygroup"),
    RegistryEntry(name="VDI Technologiezentrum GmbH", ats="softgarden", tenant="softgarden:vdijobs"),
    # --- 9 da onda de fontes F16 (2026-10-08, bucket B do gap analysis de
    # --- grandes empregadores; validadas AO VIVO com fetch real read-only
    # --- via scripts/verify_companies.py --fetch: nome EXATO do manifest +
    # --- >0 vagas + leitura de títulos/company para excluir homônimo) ---
    # Nomes canônicos = nomes EXATOS do manifest companies.csv (a resolução
    # pelo nome comercial falha: "ALTANA" resolve bamboohr/greenhouse de
    # homônimas; "Atlas Copco" sem match — o nome do manifest é
    # "Atlas Copco Group"; "Decathlon Digital" não existe — o board EN é
    # "Decathlon Digital EN"; "Rhenus" resolve o tenant adp do manifest, que
    # o scraper rejeita — o board VIVO é workday rhe/R1111 sob o nome
    # "Rhe (R1111)"; "Sandvik" tem 7 sub-boards workday, o principal é
    # "Sandvik (Sandvik Jobs)"; Heidelberg Materials aparece como
    # "Heidelbergmaterials" no workday global + jazzhr US — o global cobre
    # o grupo; DSV vive sob o título de página "Work for DSV and forward
    # your career | DSV" com tenant genérico successfactors:jobs (jobs.dsv.com
    # desambigua por URL — mesmo padrão STIHL/BMW AG), identidade confirmada
    # pelos títulos (Ausbildung Lichtenau/Burgstadt DE) e company=dsvas.
    # Falhas do bucket B ficaram FORA (pendências documentadas no relatório
    # da fase): Deutsche Bank (smartrecruiters EMPTY), Munich Re (bamboohr =
    # subsidiária Dublin + scraper quebrado), Symrise (join.com 422 ATS-wide),
    # Honeywell/Nokia (oracle precisa URL completa — fora de URL_SLUG_ATS,
    # precedente SMA; boards smartrecruiters EMPTY), Unilever TMICC (workday
    # permission denied S22).
    RegistryEntry(name="Brenntag", ats="workday", tenant="workday:brenntag/brenntag_jobs"),
    RegistryEntry(name="ALTANA Job Portal", ats="successfactors", tenant="successfactors:altanamana"),
    RegistryEntry(name="Atlas Copco Group", ats="successfactors", tenant="successfactors:atlascopcoP"),
    RegistryEntry(name="SKF", ats="successfactors", tenant="successfactors:career"),
    RegistryEntry(name="Decathlon Digital EN", ats="greenhouse", tenant="greenhouse:decathlontechnologyen"),
    RegistryEntry(name="Work for DSV and forward your career | DSV", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Heidelbergmaterials", ats="workday", tenant="workday:heidelbergmaterials/global_hm_career_site"),
    RegistryEntry(name="Sandvik (Sandvik Jobs)", ats="workday", tenant="workday:sandvik/sandvik-jobs"),
    RegistryEntry(name="Rhe (R1111)", ats="workday", tenant="workday:rhe/R1111"),
    # --- 17 da onda F32 Hidden Champions (2026-10-13, listas-semente
    # --- estáticas karrierebibel.de Top 100 + kipode.de; validadas AO VIVO
    # --- com fetch real read-only via scripts/verify_companies.py --fetch
    # --- --limit 8 --timeout 30: match EXATO no manifest + scraper + vagas>0;
    # --- metodologia, tabela aprovadas/rejeitadas com evidências e fontes em
    # --- docs/f32_hidden_champions.md) ---
    # Nomes canônicos = nome natural quando resolve EXATO no manifest
    # (Blickle, Delo, Freudenberg...); nome EXATO do manifest quando o
    # comercial não resolve (KAESER Careers, Körber Group | Job Market,
    # Jobs - Multivac, Ottobock Karriereportal | Aktuelle Stellenangebote und,
    # Mapal Group, Jobs | LEMKEN The Agrovision Company — boards
    # successfactors cujo nome de página difere do comercial; Karlstorz —
    # sem til no manifest). Vários tenants successfactors:jobs são
    # desambiguados por URL (jobs.blickle.career / jobs.koerber.com /
    # jobs.multivac.com / jobs.ottobock.com / jobs.mapal.com — mesmo padrão
    # STIHL/BMW AG 16/09). Walter = Walter AG (Zell am Harmersbach/Tübingen
    # nos títulos) sob o workday global da Sandvik (Sandvik comprou a Walter
    # AG em 2023; board "walter-jobs" — mesmo padrão "Sandvik (Sandvik Jobs)"
    # da F16). EBM-Papst resolve como "ebm-papst" (cornerstone, URL completa).
    # Bundesdruckerei resolve como "Bundesdruckerei  GmbH" (softgarden).
    # 8 empresas já presentes no SEED (Continental, Hella, KraussMaffei,
    # Liebherr, Phoenix Contact, Sartorius, Stihl, Trumpf) confirmaram match
    # ao vivo e foram ignoradas; 108 candidatas dedupadas -> tabela completa
    # de rejeitadas com motivo no relatório da fase.
    RegistryEntry(name="Blickle", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Bundesdruckerei", ats="softgarden", tenant="softgarden:bundesdruckerei"),
    RegistryEntry(name="Delo", ats="workday", tenant="workday:delo/DELO-Jobs"),
    RegistryEntry(name="EBM-Papst", ats="cornerstone", tenant="cornerstone:https://ebmpapst.csod.com/ux/ats/careersite/4/home?c=ebmpapst"),
    RegistryEntry(name="ElringKlinger", ats="workday", tenant="workday:elringklinger/external"),
    RegistryEntry(name="Freudenberg", ats="workday", tenant="workday:freudenberg/freudenberg-group"),
    RegistryEntry(name="Karlstorz", ats="successfactors", tenant="successfactors:karlstor01"),
    RegistryEntry(name="KAESER Careers", ats="successfactors", tenant="successfactors:KAESERP"),
    RegistryEntry(name="Körber Group | Job Market", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Jobs - Multivac", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Ottobock Karriereportal | Aktuelle Stellenangebote und", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Mapal Group", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Jobs | LEMKEN The Agrovision Company", ats="successfactors", tenant="successfactors:lemkengmbh"),
    RegistryEntry(name="Grammer", ats="cornerstone", tenant="cornerstone:grammer-performance-management"),
    RegistryEntry(name="Leoni", ats="smartrecruiters", tenant="smartrecruiters:LEONI1"),
    RegistryEntry(name="Walter", ats="workday", tenant="workday:sandvik/walter-jobs"),
    RegistryEntry(name="Rational", ats="successfactors", tenant="successfactors:jobs"),
    # --- 18 da onda F88 top-up de frescor (2026-10-21, watchlist F13 x SEED:
    # --- as 44 empresas sem tenant, menos Amazon [conector próprio same-day];
    # --- descoberta via F76.1 discovery_rules + find_company no inventário
    # --- upstream 80.390 empresas, validação AO VIVO com o scraper REAL
    # --- [validate_slug/validate_candidate] + ground-truth de host pelas
    # --- URLs do eligible de 20/10; A/B de dedup coletado no clone para
    # --- KPMG/AGCO/aumovio: o dedup 3-pass [estágio URL] removeu 100% dos
    # --- pares tenant x dataset — zero duplicação pós-filtro) ---
    # Nomes canônicos = nome EXATO do inventário que o CompanyCollector
    # resolve (match exato ou token; o nome comercial da watchlist NÃO
    # resolve: "KPMG" resolve IT/UK/US — a linha DE é "KPMG | DE - KPMG
    # Global"; "Würth" não existe — a linha do grupo é "Witglobal";
    # "indiecampers" não casa exato — o inventário tem "Indie Campers";
    # "Vitesco" resolve por token [VitescoProd]). REWE Group (karriere
    # .rewe-group.com) validou com o scraper mas ENTROU COMO REJEITADA:
    # patologia Lidl-like medida (sitemal.xml = 114 MB, GET cru 342s) —
    # a referência de patologia a evitar. A tentativa workday
    # "ag/airbus" (Airbus): 2.964 vagas coletadas, 0 elegíveis (locations
    # sem país parseável, country=None em 2.761) — rejeitada no A/B.
    # 2 empresas JÁ presentes no SEED confirmaram match ao vivo e foram
    # ignoradas (precedente F32): Zeiss Group (workday zeissgroup/external,
    # linha existente) e BAUHAUS ('bahagag', mesma linha bewerben.bauhaus.info).
    # Counter-cases sem tenant no universo do registry (ADAC, Everllence,
    # MTU x3, Google, TikTok, Kärcher, Exclusive Associates, Bechtle AG
    # [só HanseVision, subsidiária]): NÃO adicionados — procedimento
    # test_f88 Grupo E. AUMOVIO SE Haupverwaltung/Würth Industrie Service/
    # Müller Service/REWE Markt/REWE digital/Airbus* são cobertos pelas
    # entradas de grupo (aumovio, Witglobal, mllerservi) ou seguem fonte
    # dataset (Airbus). Vodafone: multi-match 3 linhas (eightfold 1.201 +
    # SR empty + SF 1.272, 479 DE-like) — coleta dupla tolerada, norma do
    # SEED (19 nomes já resolvem 2-4 tenants; dedup cross-source cuida do
    # overlap).
    RegistryEntry(name="KPMG | DE - KPMG Global", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="Vetter", ats="successfactors", tenant="successfactors:careers"),
    RegistryEntry(name="AGCO", ats="successfactors", tenant="successfactors:careers"),
    RegistryEntry(name="mllerservi", ats="successfactors", tenant="successfactors:mllerservi"),
    RegistryEntry(name="Deutsche Börse AG", ats="successfactors", tenant="successfactors:career"),
    RegistryEntry(name="Witglobal", ats="successfactors", tenant="successfactors:wrthitinteP2"),
    RegistryEntry(name="Levio", ats="greenhouse", tenant="greenhouse:levio"),
    RegistryEntry(name="Indie Campers", ats="greenhouse", tenant="greenhouse:indiecampers"),
    RegistryEntry(name="Vitesco", ats="successfactors", tenant="successfactors:VitescoProd"),
    RegistryEntry(name="Marquardt Group", ats="cornerstone", tenant="cornerstone:https://marquardt-group.csod.com/ux/ats/careersite/5/home?c=marquardt-group"),
    RegistryEntry(name="Kraft Heinz", ats="eightfold", tenant="eightfold:kraftheinz"),
    RegistryEntry(name="aumovio", ats="smartrecruiters", tenant="smartrecruiters:aumovio"),
    RegistryEntry(name="Vodafone", ats="successfactors", tenant="successfactors:vodafone"),
    RegistryEntry(name="Vanderlande", ats="workday", tenant="workday:vanderlande/careers"),
    RegistryEntry(name="Stryker", ats="workday", tenant="workday:stryker/strykercareers"),
    RegistryEntry(name="Endress+Hauser", ats="successfactors", tenant="successfactors:careers"),
    RegistryEntry(name="Pirelli", ats="successfactors", tenant="successfactors:jobs"),
    RegistryEntry(name="GALERIA", ats="cornerstone", tenant="cornerstone:galeria"),
    # --- 2 da onda F100 curadoria EN-source (2026-10-22, spec F100 item (b):
    # --- varredura do eligible [N=708] por empresas com >=3 vagas EN e
    # --- score médio >=5 ausentes do registry; 4 candidatas brutas, 2
    # --- cobertas [Amazon: conector próprio amazon_jobs; 'Kraftheinz':
    # --- tenant Kraft Heinz da F88, residual de alias F88 §9], 2 validadas
    # --- AO VIVO com o scraper REAL [discovery_rules.validate_slug] e
    # --- adicionadas; A/B de dedup coletado no clone: o dedup 3-pass
    # --- removeu os pares tenant x dataset [ISS: tier company+title+location,
    # --- URL do dataset difere da do tenant; JDE: estágio URL, mesma URL
    # --- space do SmartRecruiters] — zero duplicação pós-filtro. Origem do
    # --- Passo 0: Infineon/Zalando/Celonis JÁ têm tenants vivos no SEED
    # --- [gap era de funil, não de curadoria]; Siemens AG = portal custom
    # --- jobs.siemens.com, ATS fora dos 14 suportados — documentado, sem
    # --- entry [patologia 'empty silencioso' F58]. Evidências e A/B:
    # --- relatório F100 ~/.hermes/handoff/f100-registry-gap/) ---
    # Issgovernance (Institutional Shareholder Services — proxy advisory,
    # board workday issgovernance.wd1.myworkdayjobs.com/isscareers): 75 vagas
    # validadas ao vivo (POST wday/cxs, 6,5 s); internships EN em Berlim
    # (Corporate Governance Data Procurement etc.), fatia de hoje = 4
    # eligible; coleta tenant 75 -> funil 7 tipo -> 1 área -> 1 país.
    RegistryEntry(name="Issgovernance", ats="workday", tenant="workday:issgovernance/isscareers"),
    # JACOBS DOUWE EGBERTS (JDE Peet's — café, board SmartRecruiters
    # careers.smartrecruiters.com/JACOBSDOUWEEGBERTS): 175 vagas validadas
    # ao vivo (GET api.smartrecruiters.com, 18 s); internships EN Supply
    # Chain/Planning em Bruxelas [be], fatia de hoje = 3 eligible; coleta
    # tenant 175 -> funil 25 tipo -> 4 área -> 4 país.
    RegistryEntry(name="JACOBS DOUWE EGBERTS", ats="smartrecruiters", tenant="smartrecruiters:JACOBSDOUWEEGBERTS"),
    # --- 4 da onda F123 RMK wave-3 (2026-10-25, caça manual: RSS por keyword
    # --- em tenants RMK/J2W (mesma plataforma de jobs.sap.com/BMW já no
    # --- registry): pubDate presente + description embutida; 20 itens/feed
    # --- (truncagem RMK). As 4 empresas AUSENTES das 694 eligible. Validadas
    # --- AO VIVO em 25/10: careers.mahle.com, jobs.aldi-sued.de,
    # --- careers.eon.com, jobs.kuka.com — todos 200 com <item>.
    # MAHLE: careers.mahle.com (sucessfactors:jobs — tenant RMK/J2W, feed
    # completo em Stuttgart; ~20 Praktika/semana, 100% fora do acervo).
    # Espelhos DE/EN da mesma vaga com job IDs IDÊNTICOS (ex.: 1440980033
    # aparece nos 2 locales) — normalize_url/dedup tier 4 colapsa.
    RegistryEntry(name="MAHLE", ats="successfactors", tenant="successfactors:jobs"),
    # ALDI SUED: jobs.aldi-sued.de (successfactors:jobs — kw=(Praktikum):
    # 20 itens, 7 frescos 22-25/10; ~90% Schülerpraktikum — detector F86
    # segura). kw=(Einkauf) traz 20 itens (Abiturientenprogramm etc.).
    RegistryEntry(name="Aldi Süd", ats="successfactors", tenant="successfactors:jobs"),
    # E.ON: careers.eon.com (successfactors:jobs — ATENÇÃO multi-brand:
    # feed traz Westnetz/Bayernwerk/HanseWerk como company; 13 itens
    # kw=(Praktikum), ~90% Schülerpraktikum; kw=(Werkstudent) 6 itens
    # estudante real. slugs medidos ANTES de alias F66 — company do feed
    # usado como company; F66 Levio proíbe fundir holding/filial).
    RegistryEntry(name="E.ON", ats="successfactors", tenant="successfactors:jobs"),
    # KUKA: jobs.kuka.com (successfactors:jobs — Pflichtpraktikum 6-mo
    # com start jan/fev/sofort; 10/10 de estudante (oposto de Aldi/E.ON).
    # 2 do nicho do dono: Rührreibschweißen E-Mobility [materials] e
    # Inhouse Consulting).
    RegistryEntry(name="KUKA", ats="successfactors", tenant="successfactors:jobs"),
    # --- 2 da onda F125 Avature (2026-10-26, caça manual: portais Avature
    # --- com RSS feed funcional; validados AO VIVO em 26/10/2026) ---
    # Siemens Energy: jobs.siemens-energy.com (Avature — RSS feed em
    # /en_US/jobs/SearchJobsGermany/feed/?folderRecordsPerPage=20; job URL
    # format: /jobs/FolderDetail/<slug>/<id>/; pubDate presente; DE filter
    # via country-specific search pages SearchJobsGermany, SearchJobsUS, etc.)
    RegistryEntry(name="Siemens Energy", ats="avature", tenant="avature:https://jobs.siemens-energy.com"),
    # TenneT: careers.tennet.eu (Avature — RSS feed em
    # /en_US/careers/SearchJobs/feed/?jobRecordsPerPage=20; job URL format:
    # /careers/JobDetail/<slug>/<id>/; pubDate presente; multinacional NL/DE
    # — filtro DE critico via country-specific feeds ou location parsing)
    RegistryEntry(name="TenneT", ats="avature", tenant="avature:https://careers.tennet.eu"),
    # --- 6 da onda F124+F126 (2026-10-26, port do clone divergente f126-us-centric-tenants) ---
    # F124 Phenom tenants: Hugo Boss, Mars, Viega (config local com locale/country corretos)
    # Hugo Boss: careers.hugoboss.com (Phenom — locale en_global, country global)
    RegistryEntry(name="Hugo Boss", ats="phenom", tenant="phenom:https://careers.hugoboss.com"),
    # Mars: careers.mars.com (Phenom — locale en_global, country global)
    RegistryEntry(name="Mars", ats="phenom", tenant="phenom:https://careers.mars.com"),
    # Viega: careers.viega.com (Phenom — locale en_eu, country eu)
    # Viega estava incorretamente na base como SuccessFactors; tenant Phenom validado
    RegistryEntry(name="Viega", ats="phenom", tenant="phenom:https://careers.viega.com"),
    # F126 US-centric tenants: Texas Instruments, Analog Devices, Copeland (config local)
    # Texas Instruments: Oracle Cloud (edbz.fa.us2.oraclecloud.com) — nao esta na base
    RegistryEntry(name="Texas Instruments", ats="oracle", tenant="oracle:https://edbz.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1"),
    # Analog Devices: Workday (analogdevices.wd1.myworkdayjobs.com) — nao esta na base
    RegistryEntry(name="Analog Devices", ats="workday", tenant="workday:https://analogdevices.wd1.myworkdayjobs.com/External"),
    # Copeland: Workday (copeland.wd5.myworkdayjobs.com) — nao esta na base
    RegistryEntry(name="Copeland", ats="workday", tenant="workday:https://copeland.wd5.myworkdayjobs.com/copeland_external_careers_page"),
]


def _status_sort_key(rec: dict) -> tuple:
    """Chave de ordenacao: run_id (string ordenavel) primeiro; fallback timestamp.

    Espelha ``health._sort_key`` (P3 lote 1): registros com ``run_id`` string
    ordenam antes dos que so tem ``timestamp``; sem ambos, mantem a ordem de
    chegada (sort estavel). ``run_id``/``timestamp`` nao-string ou vazios sao
    tratados como ausentes — o status nunca derruba por tipo inesperado.
    """
    run_id = rec.get("run_id")
    if isinstance(run_id, str) and run_id.strip():
        return (0, run_id)
    ts = rec.get("timestamp")
    if isinstance(ts, str) and ts.strip():
        return (1, ts)
    return (2, "")


class CompanyRegistry:
    """Fonte de verdade das empresas operacionais da coleta.

    Carrega o seed em código (sem persistência em ``data/`` durante a tarefa).
    ``company_status`` agrega o estado por empresa a partir do JSONL de métricas
    existente (LEITURA defensiva; nunca escreve e nunca derruba).
    """

    def __init__(self, entries: list[RegistryEntry] | None = None) -> None:
        self._entries: dict[str, RegistryEntry] = {}
        for e in entries if entries is not None else SEED:
            self._entries[e.name] = e

    @property
    def entries(self) -> list[RegistryEntry]:
        """Entradas ordenadas por nome (determinístico)."""
        return [self._entries[n] for n in sorted(self._entries)]

    def get(self, name: str) -> RegistryEntry | None:
        return self._entries.get(name)

    def enabled(self, names: list[str] | None = None) -> list[RegistryEntry]:
        """Entradas habilitadas; ``names`` opcional restringe o subconjunto.

        Ordem de ``names`` preservada quando fornecido (importante para a ordem
        de coleta do CLI); sem ele, ordem alfabética do seed. Uma entrada
        desabilitada nunca entra no resultado.
        """
        if names is None:
            return [e for e in self.entries if e.enabled]
        result = []
        for n in names:
            e = self._entries.get(n)
            if e is not None and e.enabled:
                result.append(e)
        return result

    def company_status(self, metrics: Path | str) -> dict[str, dict]:
        """Estado por empresa derivado do JSONL de métricas (read-only).

        Para cada empresa do registry, agrega os registros ``type: tenant`` que
        carregam aquele ``company``: último ``status``, última data e total de
        vagas da última coleta. O "último" registro é o mais recente por
        ``(run_id, timestamp)`` (P3 lote 1, espelho de ``health._sort_key``) —
        NÃO a última linha do arquivo: JSONL pode chegar fora de ordem.
        Registros malformados são ignorados sem derrubar.
        Empresas sem nenhum registro aparecem com ``status=None``.
        """
        if not Path(metrics).exists():
            return {e.name: {"status": None, "last_run": None, "last_collected": None}
                    for e in self.entries}
        company_rows: dict[str, list[dict]] = {e.name: [] for e in self.entries}
        for line in Path(metrics).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict) or rec.get("type") != "tenant":
                continue
            company = rec.get("company")
            if company not in company_rows:
                continue
            company_rows[company].append(rec)

        status: dict[str, dict] = {}
        for name, rows in company_rows.items():
            if not rows:
                status[name] = {"status": None, "last_run": None, "last_collected": None}
                continue
            # run mais recente por (run_id, timestamp) — nao por posicao no
            # arquivo (linhas podem vir fora de ordem; P3 lote 1).
            last = sorted(rows, key=_status_sort_key)[-1]
            status[name] = {
                "status": last.get("status"),
                "last_run": last.get("timestamp"),
                "last_collected": last.get("collected"),
            }
        return status


def registry_names(registry: CompanyRegistry, names: list[str] | None = None) -> list[str]:
    """Nomes de coleta a partir do registry (lista de ``str`` para o CLI).

    Sem ``names`` devolve TODAS as habilitadas (ordem alfabética); com ``names``
    devolve a interseção na ordem informada.
    """
    return [e.name for e in registry.enabled(names)]


# --- Consistencia Registry x runtime (P2: tenant declarado x tenant real) ---

# Status da classificacao por empresa (chaves do relatorio de consistencia):
#  - "consistent"  — tenant declarado == unica resolucao do runtime (normal);
#  - "drift"       — tenant DECLARADO (nao-None) ausente das resolucoes do
#    runtime: o registry diz X e o runtime resolve/coleta so Y — divergencia;
#  - "multi"       — declarado presente entre N>1 resolucoes: o registry nao
#    declara ser exaustivo, so referencia; coleta extra e informativa, nao e
#    erro;
#  - "dynamic"     — declarado ``None`` e o runtime resolveu: resolucao
#    dinamica deliberada (a base decide), NAO e drift;
#  - "not_found"   — o runtime nao resolveu nenhum tenant para a empresa
#    (sem match exato na base);
#  - "no_data"     — nenhuma informacao de runtime para a empresa (ex.: ainda
#    nao coletada no run de referencia).
TENANT_CONSISTENT = "consistent"
TENANT_DRIFT = "drift"
TENANT_DYNAMIC = "dynamic"
TENANT_MULTI = "multi"
TENANT_NOT_FOUND = "not_found"
TENANT_NO_DATA = "no_data"


def tenant_consistency_status(
    declared_tenant: str | None,
    runtime_sources: list[str],
) -> str:
    """Classifica o tenant declarado no registry contra os tenants resolvidos.

    Regra central: so existe DRIFT quando o registry declara um tenant
    explicito e o runtime resolve ALGO diferente — listas vazias sao
    ``not_found`` (sem resolucao nao ha o que comparar; o erro original de
    coleta continua visivel no JSONL via status ``not_found``, nao e mascarado)
    e ``None`` declarado e sempre ``dynamic`` (resolveu) ou ``not_found``
    (nao resolveu) — nunca drift. Tenants compartilhados entre empresas nao
    afetam a classificacao: ela consome so a resolucao DA empresa.
    """
    sources = [s for s in (runtime_sources or [])
               if isinstance(s, str) and s.strip()]
    if not sources:
        return TENANT_NOT_FOUND
    if declared_tenant is None:
        return TENANT_DYNAMIC
    if declared_tenant not in sources:
        return TENANT_DRIFT
    return TENANT_MULTI if len(sources) > 1 else TENANT_CONSISTENT


def tenant_consistency_report(
    entries: list[RegistryEntry],
    runtime_tenants: dict[str, list[str]],
) -> list[dict]:
    """Relatorio de consistencia Registry x runtime, por empresa.

    ``runtime_tenants`` mapeia o nome canonico da empresa -> tenants
    (``ats:slug``) resolvidos pelo runtime no ponto de referencia (ex.: os
    registros ``type: tenant`` do run mais recente do JSONL de metricas via
    ``latest_run_tenants``, ou a resolucao viva de ``find_company``).

    Empresa AUSENTE do dict = ``no_data`` (sem informacao de runtime); presente
    com lista vazia = ``not_found`` (resolvida e nao encontrada).

    A identidade da comparacao e POR EMPRESA (nome canonico do registry),
    nunca ``source`` isolado como identidade global: o MESMO tenant pode ser
    compartilhado por varias empresas (ex.: ``successfactors:jobs`` cobre
    SAP/ZF/Kaufland/...; ``phenom:nan`` — slug ``nan`` LITERAL da base
    upstream, NÃO NaN/bug (F81) — cobre DHL/Allianz/Merck/Kuehne+Nagel no
    registry e, so em runtime, ABB/Philips/Roche/BCG) e a
    classificacao de uma empresa nunca depende do que outra coletou.

    Devolve uma linha por entrada (ordem do registry, deterministica), com
    ``company``, ``ats``, ``registry_tenant``, ``runtime_tenants`` (ordenado)
    e ``status`` — JSON-serializavel.
    """
    report: list[dict] = []
    for e in entries:
        sources = runtime_tenants.get(e.name)
        if sources is None:
            status = TENANT_NO_DATA
        else:
            status = tenant_consistency_status(e.tenant, sources)
        report.append(
            {
                "company": e.name,
                "ats": e.ats,
                "registry_tenant": e.tenant,
                "runtime_tenants": sorted(
                    s for s in (sources or []) if isinstance(s, str) and s.strip()
                ),
                "status": status,
            }
        )
    return report


def latest_run_tenants(records: list[dict]) -> dict[str, list[str]]:
    """Tenants resolvidos pelo runtime no run MAIS RECENTE dos ``records``.

    Consome os registros ``type: tenant`` do JSONL de metricas: agrupa por
    ``company`` os ``source`` (``ats:slug``) do run com o ``run_id`` maior
    (ISO 8601 ordena cronologicamente). Registrar de ``not_found`` (sem
    ``source``) marca a empresa com lista vazia — distinto de empresa sem
    nenhum registro (ausente do dict). Malformados sao ignorados, nunca
    derrubam (mesmo espirito do health). Deduplica sources por empresa.
    """
    latest: str | None = None
    for r in records:
        if not isinstance(r, dict) or r.get("type") != "tenant":
            continue
        rid = r.get("run_id")
        if isinstance(rid, str) and rid and (latest is None or rid > latest):
            latest = rid
    if latest is None:
        return {}
    out: dict[str, list[str]] = {}
    for r in records:
        if not isinstance(r, dict) or r.get("type") != "tenant":
            continue
        if r.get("run_id") != latest:
            continue
        company = r.get("company")
        if not (isinstance(company, str) and company):
            continue
        source = r.get("source")
        if isinstance(source, str) and source.strip():
            sources = out.setdefault(company, [])
            if source not in sources:
                sources.append(source)
        elif r.get("status") == "not_found":
            # Convencao do CLI: ``not_found`` grava a empresa SEM tenant
            # (``source`` vazio) — marca a empresa com lista vazia, para o
            # relatorio distinguir de "sem dados". Registro sem source e sem
            # status ``not_found`` e malformado/legado: ignorado (o health
            # tambem o ignora).
            out.setdefault(company, [])
    return out