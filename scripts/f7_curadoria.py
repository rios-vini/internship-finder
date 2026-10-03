#!/usr/bin/env python3
"""F7 curadoria: adiciona campo `country` às 16 DE + novas entries LU/NL/FI/BE.

Idempotente: skip entries que já têm country+checked de hoje. Fontes: todas
verificadas 2026-10-03 (sources/checked em cada entry nova; institucionais no
sources_for.visa_policy quando o estado o exige).
"""
import json
from pathlib import Path

CI = Path(__file__).resolve().parent.parent / "company_intel" / "company_intelligence.json"
TODAY = "2026-10-03"

# ---------------------------------------------------------------- LU
LU = [
    {
        "company": "Amazon EU S.à r.l.",
        "aliases": ["Amazon", "Amazon EU", "Amazon Europe Core", "Amazon Luxembourg"],
        "industry": "E-commerce e cloud (AWS); sede europeia de operações",
        "size": "~196 times corporativas em Luxemburgo (sede europeia)",
        "hq": "Luxembourg City, Luxemburgo (Amazon Europe Core)",
        "international": "HQ europeia em Luxemburgo; operações em toda a UE",
        "business_areas": ["Operações europeias", "AWS", "Retail/Marketplace", "Corporate (finanças, legal, HR)"],
        "website": "https://www.aboutamazon.eu",
        "careers_url": "https://www.amazon.jobs/en/locations/luxembourg",
        "checked": TODAY,
        "sources": [
            {"text": "Amazon Jobs — Luxembourg City (portal de carreiras da sede europeia)",
             "url": "https://www.amazon.jobs/content/en/locations/luxembourg/luxembourg-city",
             "quality": "primary", "checked": TODAY},
            {"text": "Guichet.lu — Conditions of residence for third-country national trainees (título de séjour stagiaire)",
             "url": "https://guichet.public.lu/en/citoyens/immigration/plus-3-mois/ressortissant-tiers/stagiaire/stage-pays-tiers.html",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "Amazon Jobs — 2027 Software Dev Engineer Intern Luxembourg (programa de estágios ativo na sede LU)",
             "url": "https://www.amazon.jobs/en/jobs/10554706/2027-software-dev-engineer-intern-luxembourg",
             "quality": "primary", "checked": TODAY,
             "note": "Programa formal de internships em Luxemburgo; a Autorização de Estada de estagiário (título de séjour 'stagiaire') existe para terceiros-países via guichet.lu — mas a Amazon não declara publicamente que patrocina esse processo para estágios. Institucional ≠ sponsorship da empresa."},
        ]},
    },
    {
        "company": "Deloitte Luxembourg",
        "aliases": ["Deloitte Tax & Consulting S.A.", "Deloitte General Services", "Deloitte LU"],
        "industry": "Consultoria, auditoria e serviços financeiros",
        "size": "~3.000 colaboradores (Luxemburgo)",
        "hq": "Luxembourg City, Luxemburgo",
        "international": "Membro da rede Deloitte (presença global)",
        "business_areas": ["Audit & Assurance", "Consulting", "Tax & Accounting", "Financial Advisory"],
        "website": "https://www2.deloitte.com/lu",
        "careers_url": "https://jobs.deloitte.lu",
        "checked": TODAY,
        "sources": [
            {"text": "Deloitte Luxembourg Careers — portal com stream 'Trainees'",
             "url": "https://jobs.deloitte.lu",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "Deloitte Luxembourg Careers — Trainees (vagas ativas, ex.: Intern Tax Compliance)",
             "url": "https://jobs.deloitte.lu/go/Trainees/3746701",
             "quality": "primary", "checked": TODAY,
             "note": "Stream formal de trainees no portal de carreiras LU; a residence permit 'stagiaire' de Luxemburgo (guichet.lu) cobre terceiros-países com bolsa remunerada, mas a Deloitte não publica declaração de sponsorship."},
        ]},
    },
    {
        "company": "Deutsche Börse Group (Luxembourg)",
        "aliases": ["Deutsche Börse AG", "Deutsche Boerse", "Clearstream"],
        "industry": "Infraestrutura de mercados financeiros (Clearstream custody)",
        "size": "~13.000 colaboradores (grupo)",
        "hq": "Luxembourg City, Luxemburgo (Clearstream); sede do grupo em Eschborn, Alemanha",
        "international": "Grupo alemão com operação principal de custódia em Luxemburgo",
        "business_areas": ["Clearing/custódia (Clearstream)", "Dados e índices", "Negociação"],
        "website": "https://www.deutsche-boerse.com",
        "careers_url": "https://careers.deutsche-boerse.com/students",
        "checked": TODAY,
        "sources": [
            {"text": "Deutsche Börse Group Careers — Students and Interns (internships 3-9 meses em Luxembourg listado)",
             "url": "https://careers.deutsche-boerse.com/students",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "Deutsche Börse Careers — campus page (Luxembourg entre as localidades de internship)",
             "url": "https://careers.deutsche-boerse.com/students",
             "quality": "primary", "checked": TODAY,
             "note": "Internships formais disponíveis em Luxembourg (3-9 meses); sem declaração pública da empresa sobre patrocínio do título 'stagiaire' para terceiros-países."},
        ]},
    },
    {
        "company": "Millicom International Cellular S.A.",
        "aliases": ["Millicom", "Tigo", "Millicom (Tigo)"],
        "industry": "Telecomunicações (Tigo; LatAm)",
        "size": "~15.000 colaboradores",
        "hq": "Luxembourg City, Luxemburgo (148-150 Bd de la Pétrusse)",
        "international": "HQ Luxemburgo; operações na América Latina",
        "business_areas": ["Telecom móvel e fibra (Tigo)", "Serviços financeiros (Tigo Money)"],
        "website": "https://www.millicom.com",
        "careers_url": "https://tigo.wd103.myworkdayjobs.com/tigocareers",
        "checked": TODAY,
        "sources": [
            {"text": "Millicom — Luxembourg HQ (página institucional)",
             "url": "https://www.millicom.com/our-company/markets/luxembourg-hq",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "HQ em Luxemburgo confirmada; páginas de carreiras checadas 2026-10-03 sem evidência pública de programa de estágio LU ou declaração de sponsorship para terceiros-países.",
    },
    {
        "company": "ArcelorMittal",
        "aliases": ["ArcelorMittal S.A."],
        "industry": "Siderurgia e mineração",
        "size": "~111.000 empregados (2025)",
        "hq": "Luxembourg City, Luxemburgo",
        "international": "Operações em 4 continentes; HQ global em Luxemburgo",
        "business_areas": ["Siderurgia (flat/acero longo)", "Mineração", "Distribuição"],
        "website": "https://corporate.arcelormittal.com",
        "careers_url": "https://corporate.arcelormittal.com/careers",
        "checked": TODAY,
        "sources": [
            {"text": "ArcelorMittal — corporate (HQ Luxembourg)",
             "url": "https://corporate.arcelormittal.com",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "HQ global em Luxemburgo; programas de internship/graduate existem (research summer internships) mas a página corporativa não declara sponsorship de título 'stagiaire' LU para terceiros-países — checado 2026-10-03.",
    },
]

# ---------------------------------------------------------------- NL
NL = [
    {
        "company": "Koninklijke Philips N.V.",
        "aliases": ["Philips", "Philips Electronics"],
        "industry": "Tecnologia de saúde (equipamentos médicos)",
        "size": "~69.000 empregados (2025)",
        "hq": "Amsterdã, Países Baixos",
        "international": "Operações globais",
        "business_areas": ["Health systems (imagens, monitoramento)", "Personal health", "Sleep & respiratory care"],
        "website": "https://www.philips.com",
        "careers_url": "https://www.careers.philips.com",
        "checked": TODAY,
        "sources": [
            {"text": "IND Public Register Recognised Sponsors (Work) — Koninklijke Philips N.V., 17001910",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "IND Public Register Work — Koninklijke Philips N.V. (17001910), sponsor reconhecido",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY,
             "note": "Empresa consta no registro público IND de sponsors reconhecidos (categoria Work/HSM). O registro é institutional — não declara sponsorship de internship específico; a residence permit NL para internship existe e a empresa é sponsor reconhecida."},
        ]},
    },
    {
        "company": "ASML Holding N.V.",
        "aliases": ["ASML"],
        "industry": "Equipamentos de litografia para semicondutores",
        "size": "~47.000 empregados (2025)",
        "hq": "Veldhoven, Países Baixos",
        "international": "Operações globais; fabs clientes na Ásia/EUA",
        "business_areas": ["Lithografia EUV/DUV", "Metrologia e inspeção (HMI)", "Computação (software de processo)"],
        "website": "https://www.asml.com",
        "careers_url": "https://www.asml.com/careers",
        "checked": TODAY,
        "sources": [
            {"text": "IND Public Register Recognised Sponsors (Work) — ASML Holding N.V., 17085815",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "IND Public Register Work — ASML Holding N.V. (17085815)",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY,
             "note": "Sponsor reconhecido IND (Work). Mesmo enquadramento da Philips: evidência institucional de capacidade de sponsorship, sem declaração pública específica para estágios."},
        ]},
    },
]


# ---------------------------------------------------------------- NL (cont)
NL += [
    {
        "company": "Nokia (Netherlands)",
        "aliases": ["Nokia Solutions and Networks B.V.", "Nokia Bell Labs (NL)"],
        "industry": "Equipamentos de rede e telecom",
        "size": "~3.500 (NL); ~66.000 global (2025)",
        "hq": "Espoo, Finlândia (grupo); NSN B.V. registrada em Amsterdã",
        "international": "Operações globais",
        "business_areas": ["Redes móveis (5G)", "Network infrastructure", "Cloud e network services"],
        "website": "https://www.nokia.com",
        "careers_url": "https://www.nokia.com/careers",
        "checked": TODAY,
        "sources": [
            {"text": "IND Public Register Recognised Sponsors (Work) — Nokia Solutions and Networks B.V., 34259706",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "IND Public Register Work — Nokia Solutions and Networks B.V. (34259706)",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY,
             "note": "Sponsor reconhecido IND (Work)."},
        ]},
    },
    {
        "company": "KONE (Netherlands)",
        "aliases": ["Kone B.V.", "KONE B.V."],
        "industry": "Elevadores e escadas rolantes",
        "size": "~700 (NL); ~37.000 global (2025)",
        "hq": "Espoo, Finlândia (grupo); Kone B.V. registrada em Woerle",
        "international": "Operações globais",
        "business_areas": ["New Building Solutions", "Service", "Modernização"],
        "website": "https://www.kone.com",
        "careers_url": "https://kone.wd3.myworkdayjobs.com/careers",
        "checked": TODAY,
        "sources": [
            {"text": "IND Public Register Recognised Sponsors (Work) — Kone B.V., 27075288",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "IND Public Register Work — Kone B.V. (27075288)",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY,
             "note": "Sponsor reconhecido IND (Work)."},
        ]},
    },
    {
        "company": "ArcelorMittal (Netherlands)",
        "aliases": ["ArcelorMittal Netherlands B.V."],
        "industry": "Siderurgia",
        "size": "n/d",
        "hq": "Amsterdã, Países Baixos",
        "international": "Subsidiária do grupo ArcelorMittal (HQ Luxemburgo)",
        "business_areas": ["Distribuição de aço", "Projects Europe"],
        "website": "https://corporate.arcelormittal.com",
        "careers_url": "https://corporate.arcelormittal.com/careers",
        "checked": TODAY,
        "sources": [
            {"text": "IND Public Register Recognised Sponsors (Work) — ArcelorMittal Netherlands B.V., 33297298",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "IND Public Register Work — ArcelorMittal Netherlands B.V. (33297298)",
             "url": "https://ind.nl/en/public-register-recognised-sponsors/public-register-work",
             "quality": "primary", "checked": TODAY,
             "note": "Sponsor reconhecido IND (Work)."},
        ]},
    },
]

# ---------------------------------------------------------------- FI
FI = [
    {
        "company": "Nokia",
        "aliases": ["Nokia Corporation", "Nokia Oyj"],
        "industry": "Equipamentos de rede e telecom",
        "size": "~66.000 empregados (2025)",
        "hq": "Espoo, Finlândia",
        "international": "Operações globais",
        "business_areas": ["Redes móveis (5G/6G)", "Network infrastructure", "Bell Labs (research)"],
        "website": "https://www.nokia.com",
        "careers_url": "https://www.nokia.com/careers/our-locations/finland/students-and-graduates",
        "checked": TODAY,
        "sources": [
            {"text": "Nokia Careers — Student & Graduate opportunities in Finland (~500 trainees/ano em Espoo/Tampere/Oulu)",
             "url": "https://www.nokia.com/careers/our-locations/finland/students-and-graduates",
             "quality": "primary", "checked": TODAY},
            {"text": "Migri — Residence permit application for internship (Finlândia; até 18 meses, salário documentado)",
             "url": "https://migri.fi/en/internship",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "Nokia Careers — Students and Graduates Finland",
             "url": "https://www.nokia.com/careers/our-locations/finland/students-and-graduates",
             "quality": "primary", "checked": TODAY,
             "note": "Programa formal de ~500 trainees/ano na Finlândia; o Migri mantém residence permit específica para internship (path formal). Nokia não publica declaração de sponsorship para trainees de terceiros-países — unclear por honestidade."},
        ]},
    },
    {
        "company": "KONE",
        "aliases": ["KONE Corporation", "KONE Oyj"],
        "industry": "Elevadores e escadas rolantes",
        "size": "~37.000 empregados (2025)",
        "hq": "Espoo, Finlândia",
        "international": "Operações globais",
        "business_areas": ["New Building Solutions", "Service", "Modernização"],
        "website": "https://www.kone.com",
        "careers_url": "https://www.kone.com/global/en/careers/teams/students-and-graduates.html",
        "checked": TODAY,
        "sources": [
            {"text": "KONE Careers — Students and Graduates (trainee positions/International Trainee Program)",
             "url": "https://www.kone.com/global/en/careers/teams/students-and-graduates.html",
             "quality": "primary", "checked": TODAY},
            {"text": "Migri — Residence permit application for internship",
             "url": "https://migri.fi/en/internship",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "KONE Careers — Students and Graduates (trainee positions/International Trainee Program)",
             "url": "https://www.kone.com/global/en/careers/teams/students-and-graduates.html",
             "quality": "primary", "checked": TODAY,
             "note": "Programas de trainee documentados; path formal FI (Migri internship permit). Sem declaração pública de sponsorship — unclear."},
        ]},
    },
    {
        "company": "Wärtsilä",
        "aliases": ["Wärtsilä Oyj Abp", "Wartsila"],
        "industry": "Motores e soluções de energia marítima",
        "size": "~18.000 empregados (2025)",
        "hq": "Helsínque, Finlândia",
        "international": "Operações globais",
        "business_areas": ["Marine Power", "Marine Systems", "Energy Solutions"],
        "website": "https://www.wartsila.com",
        "careers_url": "https://www.wartsila.com/careers",
        "checked": TODAY,
        "sources": [
            {"text": "Wärtsilä — careers (presença no dataset de estágios FI)",
             "url": "https://www.wartsila.com/careers",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Empresa de engenharia FI com vagas de estágio no dataset (Wärtsilä Oyj Abp, fatia successfactors 2026-10-03); sem declaração pública de sponsorship de residence permit de internship — not_verified por honestidade.",
    },
]

# ---------------------------------------------------------------- BE
BE = [
    {
        "company": "AB InBev",
        "aliases": ["Anheuser-Busch InBev", "AB InBev (Belgium)"],
        "industry": "Cervejaria (FMCG)",
        "size": "~155.000 empregados (2025)",
        "hq": "Leuven, Bélgica",
        "international": "Operações globais",
        "business_areas": ["Cervejas (Budweiser, Corona, Stella Artois)", "Global brands", "No-alcohol"],
        "website": "https://www.ab-inbev.com",
        "careers_url": "https://europecareers.ab-inbev.com/programmes/graduate-management-traineeship",
        "checked": TODAY,
        "sources": [
            {"text": "AB InBev Europe Careers — Graduate Management Traineeship (GMT)",
             "url": "https://europecareers.ab-inbev.com/programmes/graduate-management-traineeship",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "candidate_must_have_authorization",
        "sources_for": {"visa_policy": [
            {"text": "AB InBev Europe Careers — GMT eligibility ('A valid permanent visa/work permit is required in the country of application')",
             "url": "https://europecareers.ab-inbev.com/programmes/graduate-management-traineeship",
             "quality": "primary", "checked": TODAY,
             "note": "Citação literal: exige visa/work permit permanente VÁLIDA no país de aplicação — a empresa NÃO patrocina; NEGATIVO para candidatos BR no canal trainee."},
        ]},
    },
    {
        "company": "Solvay",
        "aliases": ["Solvay S.A."],
        "industry": "Química e materiais avançados",
        "size": "~9.000 empregados (2025)",
        "hq": "Bruxelas, Bélgica",
        "international": "Operações globais",
        "business_areas": ["Essential chemistry", "Materiais (soda, peróxidos, sílicas)", "Specialty chemicals"],
        "website": "https://www.solvay.com",
        "careers_url": "https://www.solvay.com/en/career",
        "checked": TODAY,
        "sources": [
            {"text": "Solvay Careers — Teams/Students (~200 internships/ano; vagas Intern ativas em Brussels)",
             "url": "https://www.solvay.com/en/career/teams",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "Solvay Careers — Students (internships formais, ex.: Government and Public Affairs Intern, Brussels)",
             "url": "https://www.solvay.com/en/career/teams",
             "quality": "primary", "checked": TODAY,
             "note": "Programa formal de internships na Bélgica; o single permit trainee BE (empregador submete) é o path institucional, mas a Solvay não publica declaração de sponsorship."},
        ]},
    },
    {
        "company": "Barco NV",
        "aliases": ["Barco"],
        "industry": "Visualização profissional (projeção, controle)",
        "size": "~3.000 empregados (2025)",
        "hq": "Kortrijk, Bélgica",
        "international": "Operações globais",
        "business_areas": ["Entertainment (projeção cinema)", "Healthcare (imagens médicas)", "Enterprise ( meeting/controle)"],
        "website": "https://www.barco.com",
        "careers_url": "https://www.barco.com/en/careers",
        "checked": TODAY,
        "sources": [
            {"text": "Dataset ats-scrapers fatia successfactors — Barco NV, 12 rows estágio BE (2026-10-03)",
             "url": "https://storage.stapply.ai/jobhive/v1/manifest.json",
             "quality": "aggregated", "checked": TODAY},
            {"text": "Barco — Careers",
             "url": "https://www.barco.com/en/careers",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "Barco Careers + single permit trainee BE (empregador submete; ≤6m, Flanders renovável)",
             "url": "https://www.barco.com/en/careers",
             "quality": "primary", "checked": TODAY,
             "note": "Empresa belga com estágios recorrentes (dataset: 12 rows); path institucional BE = single permit trainee submetido pelo empregador. Sem declaração pública de sponsorship."},
        ]},
    },
    {
        "company": "Agfa NV",
        "aliases": ["Agfa-Gevaert", "Agfa", "AGFA NV"],
        "industry": "Imagem digital e impressão offset",
        "size": "~9.000 empregados (2025)",
        "hq": "Mortsel, Bélgica",
        "international": "Operações globais",
        "business_areas": ["Offset solutions", "Digital print", "Radiologia (Agfa Healthcare)"],
        "website": "https://www.agfagraphics.com",
        "careers_url": "https://www.agfagraphics.com/about-us/careers",
        "checked": TODAY,
        "sources": [
            {"text": "Dataset ats-scrapers fatia successfactors — AGFA NV, 4 rows estágio BE (2026-10-03)",
             "url": "https://storage.stapply.ai/jobhive/v1/manifest.json",
             "quality": "aggregated", "checked": TODAY},
            {"text": "Agfa — Careers",
             "url": "https://www.agfagraphics.com/about-us/careers",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "Agfa Careers + single permit trainee BE",
             "url": "https://www.agfagraphics.com/about-us/careers",
             "quality": "primary", "checked": TODAY,
             "note": "Estágios recorrentes (dataset); path institucional BE; sem declaração pública de sponsorship."},
        ]},
    },
    {
        "company": "KBC GROEP NV",
        "aliases": ["KBC Group", "KBC Bank"],
        "industry": "Serviços financeiros (banco-seguradora)",
        "size": "~44.000 empregados (2025)",
        "hq": "Bruxelas, Bélgica",
        "international": "Operações BE/CZ/HU/Eslováquia/Bulgária/Irlanda",
        "business_areas": ["Retail banking", "Insurance", "Asset management"],
        "website": "https://www.kbc.com",
        "careers_url": "https://www.kbc.com/careers",
        "checked": TODAY,
        "sources": [
            {"text": "Dataset ats-scrapers fatia successfactors — KBC GROEP NV, 11 rows estágio BE (2026-10-03)",
             "url": "https://storage.stapply.ai/jobhive/v1/manifest.json",
             "quality": "aggregated", "checked": TODAY},
            {"text": "KBC Group — Careers",
             "url": "https://www.kbc.com/careers",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "KBC Careers + single permit trainee BE",
             "url": "https://www.kbc.com/careers",
             "quality": "primary", "checked": TODAY,
             "note": "Estágios recorrentes (dataset); path institucional BE; sem declaração pública de sponsorship."},
        ]},
    },
]


# ---------------------------------------------------------------- BE (cont, 2)
BE += [
    {
        "company": "UCB",
        "aliases": ["UCB Pharma", "UCB Biopharma"],
        "industry": "Biofarmacêutica",
        "size": "~9.000 empregados (2025)",
        "hq": "Bruxelas, Bélgica",
        "international": "Ativa em ~40 países",
        "business_areas": ["Neurologia", "Imunologia", "Biotech manufacturing (Braine-l'Alleud)"],
        "website": "https://www.ucb.com",
        "careers_url": "https://careers.ucb.com/global/en/early-careers-global-programs",
        "checked": TODAY,
        "sources": [
            {"text": "UCB Early Careers — Global Programs (VIE 12-24 meses em funções BE; AIESEC traineeship)",
             "url": "https://careers.ucb.com/global/en/early-careers-global-programs",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "unclear",
        "sources_for": {"visa_policy": [
            {"text": "UCB Early Careers — VIE program (emphasis em funções científicas/manufatura na Bélgica) + AIESEC traineeship",
             "url": "https://careers.ucb.com/global/en/early-careers-global-programs",
             "quality": "primary", "checked": TODAY,
             "note": "Programas formais de early careers BE (VIE — administrado pela Business France; AIESEC — visa de trainee próprio). Path existente, mas os programas têm estruturas específicas (não é o single permit padrão); sem declaração de sponsorship genérico."},
        ]},
    },
    {
        "company": "Bekaert",
        "aliases": ["Bekaert Group", "Bridon-Bekaert Ropes Group"],
        "industry": "Transformação de aço e materiais avançados",
        "size": "~24.000 empregados (2025)",
        "hq": "Zwevegem, Bélgica",
        "international": "Operações globais",
        "business_areas": ["Steel wire solutions", "Rubber reinforcement (Dramix)", "Ropes group"],
        "website": "https://www.bekaert.com",
        "careers_url": "https://www.bekaert.com/en/careers",
        "checked": TODAY,
        "sources": [
            {"text": "Bekaert — Careers (Global Graduates program; Early Careers; Schools & Universities)",
             "url": "https://www.bekaert.com/en/careers",
             "quality": "primary", "checked": TODAY},
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Programas de early careers/Global Graduates existem; sem declaração pública sobre sponsorship de single permit trainee BE para terceiros-países — checado 2026-10-03.",
    },
]

# ---------------------------------------------------------------- apply
COUNTRIES = {"lu": LU, "nl": NL, "fi": FI, "be": BE}

def main() -> None:
    data = json.loads(CI.read_text(encoding="utf-8"))
    companies = data["companies"]
    existing = {e["company"].casefold() for e in companies}
    added = []
    for iso, entries in COUNTRIES.items():
        for e in entries:
            if e["company"].casefold() in existing:
                print(f"SKIP (existe): {e['company']}")
                continue
            e["country"] = iso
            companies.append(e)
            added.append((iso, e["company"]))
    # campo country nas 16 DE existentes
    de_count = 0
    for e in companies:
        if "country" not in e:
            e["country"] = "de"
            de_count += 1
    CI.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"adicionadas: {len(added)}")
    for iso, co in added:
        print(f"  {iso}: {co}")
    print(f"DE marcadas com country=de: {de_count}")
    print(f"total entries: {len(companies)}")

if __name__ == "__main__":
    main()
