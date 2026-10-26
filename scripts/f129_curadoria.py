#!/usr/bin/env python3
"""F129 curadoria onda 3: ~30 empresas-alvo novas confirmadas ao vivo (tenant + careers-verificado).

Idempotente no padrão do f9_curadoria.py/f10_curadoria.py:
- entries NOVAS (casefold do nome canônico ainda ausente) entram com ``country`` = "de";
- entries EXISTENTES podem ganhar aliases extras (strings EXATAS do dataset) e upgrade de visa_policy.

Semântica de estados (intocável, precedente F5/F7/F9/F10):
- explicit_support: inexistente na prática para estágio DE;
- unclear: programa formal / evidência citada -> visa_friendly;
- candidate_must_have_authorization: negativa *** (valiosa);
- not_verified: nota honesta do que foi checado.

Fontes: todas verificadas HOJE (checked = 2026-10-26).
"""

import json
from pathlib import Path

CI = Path(__file__).resolve().parent.parent / "company_intel" / "company_intelligence.json"
TODAY = "2026-10-26"


def _src(text: str, url: str, quality: str) -> dict:
    return {"text": text, "url": url, "quality": quality, "checked": TODAY}


# ---------------------------------------------------------------------------
# NOVAS ENTRIES — empresas confirmadas com programa de estudantes na DE
# ---------------------------------------------------------------------------

NEW_ENTRIES: list[dict] = [
    # === Aldi Süd ===
    {
        "company": "Aldi Süd",
        "aliases": [
            "ALDI SÜD",
            "Aldi Süd",
            "Aldi Dienstleistung SE & Co. oHG",
            "ALDI Süd Stiftung & Co. KG",
        ],
        "industry": "Varejo de alimentos (discounter; grupo Aldi Süd)",
        "size": "Mais de 50.000 colaboradores na Alemanha (portal de carreiras)",
        "hq": "Mülheim an der Ruhr, NRW, Alemanha",
        "international": "Operações na Alemanha, Áustria, Suíça, EUA, UK, China, Austrália; parte do grupo Aldi Süd",
        "business_areas": [
            "Operações de loja (Filialen)",
            "Logística e centros de distribuição",
            "Administração central (Dienstleistung)",
            "Compras e categorias",
            "TI e digital",
        ],
        "website": "https://www.aldi-sued.de",
        "careers_url": "https://karriere.aldi-sued.de/studenten-absolventen",
        "checked": TODAY,
        "sources": [
            _src(
                "ALDI SÜD Karriereseite — Studenten & Absolventen (Praktikum, Werkstudent, duales Masterstudium, Abschlussarbeit)",
                "https://karriere.aldi-sued.de/studenten-absolventen",
                "primary",
            ),
            _src(
                "ALDI SÜD FAQ Studierende: Praktika ab 3. Semester; Pflichtpraktikum até 6 meses, voluntário até 3 meses; inscrição online obrigatória",
                "https://karriere.aldi-sued.de/studenten-absolventen/faq",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de estudantes (Praktikum, Werkstudent, duales Masterstudium) citado no portal oficial alemão; FAQ 2026-10-26 não declara patrocínio de visto/autorização para não-UE — estado honesto unclear (programa citado).",
        "sources_for": {"visa_policy": [
            {
                "text": "ALDI SÜD FAQ Studierende: \"Unsere Praktika richten sich an Studierende ab dem dritten Semester... Ein Pflichtpraktikum ist allerdings nur dann möglich, wenn es ausdrücklich in deiner Studien- beziehungsweise Prüfungsordnung vorgeschrieben ist.\" — página oficial de FAQ para estudantes, sem menção a sponsorship de visto.",
                "url": "https://karriere.aldi-sued.de/studenten-absolventen/faq",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estágios (obrigatórios até 6 meses, voluntários até 3 meses) com inscrição online; a página não declara sponsorship de visto para não-UE — unclear (programa citado).",
            },
        ]},
    },

    # === Aldi Nord ===
    {
        "company": "Aldi Nord",
        "aliases": [
            "ALDI Nord",
            "Aldi Nord",
            "Aldi-Nord",
            "ALDI Einkauf GmbH & Co. oHG",
        ],
        "industry": "Varejo de alimentos (discounter; grupo Aldi Nord)",
        "size": "Mais de 90.000 colaboradores no grupo (8 países; site oficial)",
        "hq": "Essen, NRW, Alemanha (ALDI Nord Campus)",
        "international": "Operações na Alemanha, Bélgica, França, Luxemburgo, Países Baixos, Polônia, Portugal, Espanha, EUA (Trader Joe's); parte do grupo Aldi Nord",
        "business_areas": [
            "Operações de loja (Filialen)",
            "Logística e centros de distribuição",
            "Administração central (Campus Essen)",
            "Compras e categorias",
        ],
        "website": "https://www.aldi-nord.de",
        "careers_url": "https://www.aldi-nord.de/karriere/ausbildung/praktikum-fuer-studierende.html",
        "checked": TODAY,
        "sources": [
            _src(
                "ALDI Nord — Praktikum für Studierende (página oficial com detalhes do programa)",
                "https://www.aldi-nord.de/karriere/ausbildung/praktikum-fuer-studierende.html",
                "primary",
            ),
            _src(
                "ALDI Nord Karriereseite — visão geral com áreas de estudantes, logística, venda",
                "https://www.aldi-nord.de/karriere.html",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de Praktikum für Studierende cita programa de estágios com insights em várias áreas empresariais; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "ALDI Nord — Praktikum für Studierende: \"Mit einem Praktikum für Studierende bei ALDI Nord erhältst du Einblicke in verschiedene Unternehmensbereiche, arbeitest an realen Projekten mit und kannst dein theoretisches Wissen in die Praxis umsetzen.\" — página oficial do programa de estágios.",
                "url": "https://www.aldi-nord.de/karriere/ausbildung/praktikum-fuer-studierende.html",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estágios para estudantes citado no portal oficial; sem declaração de sponsorship de visto — unclear (programa citado).",
            },
        ]},
    },

    # === E.ON ===
    {
        "company": "E.ON",
        "aliases": [
            "E.ON SE",
            "E.ON",
            "E.ON Energy",
            "E.ON Deutschland",
        ],
        "industry": "Energia (utilities; redes, renováveis, soluções para clientes)",
        "size": "~75.000 colaboradores (grupo global; site oficial)",
        "hq": "Essen, NRW, Alemanha",
        "international": "Presença na Europa (DE, UK, SE, NL, HU, CZ, RO, IT, PL, TR) e global via parcerias",
        "business_areas": [
            "Redes de distribuição (Energy Networks)",
            "Soluções para clientes (Customer Solutions)",
            "Renováveis (Renewables)",
            "Geração e trading",
        ],
        "website": "https://www.eon.com",
        "careers_url": "https://www.eon.com/de/ueber-uns/karriere/studierende-young-professionals",
        "checked": TODAY,
        "sources": [
            _src(
                "E.ON International Graduate Programme — página oficial (requisitos: residence permit/visa conforme nacionalidade para AC presencial em Essen)",
                "https://www.eon.com/de/ueber-uns/karriere/studierende-young-professionals/international-graduate-programme.html",
                "primary",
            ),
        ],
        "visa_policy": "candidate_must_have_authorization",
        "visa_policy_note": "Página oficial do International Graduate Programme declara: \"Für die Teilnahme am Präsenz-AC in Essen ist je nach Staatsangehörigkeit ein entsprechender Aufenthaltstitel oder ein Visum erforderlich\" — o candidato não-UE precisa ter autorização própria; não há declaração de patrocínio de visto para estágios/trainee na DE.",
        "sources_for": {"visa_policy": [
            {
                "text": "E.ON International Graduate Programme (DE): \"Für die Teilnahme am Präsenz-AC in Essen ist je nach Staatsangehörigkeit ein entsprechender Aufenthaltstitel oder ein Visum erforderlich.\" — requisito declarado no portal oficial: candidato precisa ter Aufenthaltstitel/Visum próprio.",
                "url": "https://www.eon.com/de/ueber-uns/karriere/studierende-young-professionals/international-graduate-programme.html",
                "quality": "primary",
                "checked": TODAY,
                "note": "Exigência de autorização de residência/visto própria para Assessment Center presencial — candidate_must_have_authorization (negativa honesta).",
            },
        ]},
    },

    # === KUKA ===
    {
        "company": "KUKA",
        "aliases": [
            "KUKA AG",
            "KUKA Deutschland GmbH",
            "KUKA Robotics",
            "KUKA SE & Co. KGaA",
        ],
        "industry": "Automação industrial e robótica (Industry 4.0)",
        "size": "~15.000 colaboradores (grupo global; site oficial)",
        "hq": "Augsburg, Baviera, Alemanha",
        "international": "Presença global com subsidiárias na Europa, EUA, China, Coreia, Brasil, México; parte do grupo Midea (China)",
        "business_areas": [
            "Robótica e automação (sistemas, software, controllers)",
            "Tecnologia de soldagem",
            "Sistemas de manufatura",
            "Pesquisa e desenvolvimento (Industry 4.0)",
        ],
        "website": "https://www.kuka.com",
        "careers_url": "https://www.kuka.com/de-de/unternehmen/karriere/studenten",
        "checked": TODAY,
        "sources": [
            _src(
                "KUKA — Studierende (Praktikum, Werkstudent, Abschlussarbeit; três opções oficiais com vagas ativas em Augsburg/Bremen)",
                "https://www.kuka.com/de-de/unternehmen/karriere/studenten",
                "primary",
            ),
            _src(
                "KUKA — Praktikum für Studierende (duas modalidades: Vor-Praktikum pré-estudo e estágio durante o curso; inscrição online exclusiva)",
                "https://www.kuka.com/de-de/unternehmen/karriere/studenten/praktikum-f%C3%BCr-studenten",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de estudantes com três pilares (Praktikum, Werkstudent, Abschlussarbeit) e vagas ativas no portal oficial alemão; páginas checadas 2026-10-26 sem declaração pública sobre visto/autorização para não-UE — estado honesto unclear (programa citado).",
        "sources_for": {"visa_policy": [
            {
                "text": "KUKA Studierende: \"Studierende haben drei Optionen, um bei KUKA Praxiserfahrung zu sammeln: Sie arbeiten als Werkstudent/in, schreiben Ihre Abschlussarbeit bei KUKA oder machen ein Praktikum.\" — portal oficial com vagas ativas em Augsburg e Bremen; sem menção a visto/patrocínio.",
                "url": "https://www.kuka.com/de-de/unternehmen/karriere/studenten",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estudantes com três modalidades e inscrição online exclusiva; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === Hugo Boss ===
    {
        "company": "Hugo Boss",
        "aliases": [
            "HUGO BOSS AG",
            "HUGO BOSS",
            "Hugo Boss AG",
            "Boss",
        ],
        "industry": "Moda e lifestyle premium (vestuário, acessórios, fragrâncias)",
        "size": "~19.000 colaboradores (grupo global; site oficial)",
        "hq": "Metzingen, Baden-Württemberg, Alemanha",
        "international": "Presença em 127 países; marcas BOSS e HUGO; parte do grupo Hugo Boss AG",
        "business_areas": [
            "Design e desenvolvimento de produto",
            "Marketing e marca",
            "Supply chain e sourcing",
            "Digital e e-commerce",
            "Finanças e controle",
        ],
        "website": "https://www.hugoboss.com",
        "careers_url": "https://careers.hugoboss.com/global/en/search-results",
        "checked": TODAY,
        "sources": [
            _src(
                "HUGO BOSS Careers — Application process (portal Phenom; reembolso de viagem para entrevistas na DE/AT/CH)",
                "https://careers.hugoboss.com/global/en/your-application",
                "primary",
            ),
            _src(
                "HUGO BOSS Global Jobs — portal de vagas global com filtro por país (Alemanha listada)",
                "https://careers.hugoboss.com",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Portal oficial de carreiras (Phenom) com processo de aplicação documentado e reembolso de viagem para DE/AT/CH; páginas de estudantes/estágios e FAQ checadas 2026-10-26 sem declaração pública aplicável sobre visto/autorização para estágios na Alemanha.",
    },

    # === Mars (Alemanha) ===
    {
        "company": "Mars Germany",
        "aliases": [
            "Mars GmbH",
            "Mars Germany",
            "Mars Petcare Germany",
            "Mars Wrigley Germany",
        ],
        "industry": "Alimentos, petcare e confeitaria (FMCG global)",
        "size": "~150.000 Associados (grupo global); operações DE em Unterhaching, Viersen, Colônia, Verden",
        "hq": "McLean, VA, EUA (grupo); Mars Germany em Unterhaching, Baviera",
        "international": "Operações em 80+ países; marcas M&M's, Snickers, Pedigree, Royal Canin, Whiskas, Ben's Original",
        "business_areas": [
            "Mars Petcare (Royal Canin, Whiskas, Pedigree, Banfield, BluePearl)",
            "Mars Wrigley (M&M's, Snickers, Twix, Extra, Orbit, Skittles)",
            "Mars Food & Nutrition (Ben's Original, Cocoavia)",
            "Mars Edge (ciência da nutrição)",
        ],
        "website": "https://www.mars.com",
        "careers_url": "https://careers.mars.com/global/en/search-results",
        "checked": TODAY,
        "sources": [
            _src(
                "Mars Careers Global — vagas ativas de estágio/trainee na Alemanha (Unterhaching, Viersen, Colônia, Verden) para Supply Chain, Finance, Marketing, Statistics",
                "https://careers.mars.com/global/en/search-results",
                "primary",
            ),
            _src(
                "Mars Internship Experience (US) — FAQ declara explicitamente: \"As we are unable to sponsor visas for our Early Talent programs, you'll need to have permanent work authorization for the country you intern in\"",
                "https://careers.mars.com/us/en/mars-internship-and-co-op-experience",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Portal global de carreiras com vagas ativas de estágio/trainee na Alemanha (ex: Cologne, Unterhaching, Viersen); a declaração explícita de \"no visa sponsorship for Early Talent programs\" refere-se ao programa US — não se estende automaticamente à operação DE (regra F10: registro IND por país). Páginas DE checadas 2026-10-26 sem declaração própria sobre visto.",
    },

    # === Viega ===
    {
        "company": "Viega",
        "aliases": [
            "Viega GmbH & Co. KG",
            "Viega",
            "Viega Deutschland",
        ],
        "industry": "Tecnologia de instalação (sistemas de pressionamento, pré-isolados, drenagem)",
        "size": "~5.700 colaboradores mundialmente; >10 localidades globais (site oficial)",
        "hq": "Attendorn, NRW, Alemanha",
        "international": "Produção e vendas na Europa, EUA, China, Índia; líder mundial em sistemas de pressionamento metálicos",
        "business_areas": [
            "Sistemas de pressionamento (Megapress, Profipress, Sanpress)",
            "Tecnologia de pré-isolados",
            "Drenagem e sistemas de esgoto",
            "Tecnologia de conexão para gás",
        ],
        "website": "https://www.viega.de",
        "careers_url": "https://careers.viega.com/de/de/search-results",
        "checked": TODAY,
        "sources": [
            _src(
                "Viega — Studierende (Praktikum, Werkstudententätigkeit, Traineeprogramm, Abschlussarbeit; contato direto por obra/fábrica)",
                "https://www.viega.de/de/unternehmen/karriere/studierende.html",
                "primary",
            ),
            _src(
                "Viega Karriereseite — visão geral com 0 vagas atuais para estudantes mas programa estruturado descrito",
                "https://www.viega.de/de/unternehmen/karriere.html",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de estudantes descreve quatro modalidades (Praktikum 3 meses, Werkstudent, Trainee 18 meses com mentor e intercâmbio, Abschlussarbeit) com contatos por fábrica; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "Viega Studierende: \"Bei uns hast du verschiedene Möglichkeiten, deine theoretischen Kenntnisse in der Praxis anzuwenden: zum Beispiel mit einem praxisintegrierten Studium in den Semesterferien im Projektgeschäft, einem Praktikum in einem unserer Fachbereiche oder einer Anstellung als Werkstudent.\" — portal oficial com detalhes de duração (3 meses Praktikum, 18 meses Trainee) e contatos.",
                "url": "https://www.viega.de/de/unternehmen/karriere/studierende.html",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estudantes com múltiplas modalidades e contatos dedicados por fábrica; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === Siemens Energy (Alemanha) ===
    {
        "company": "Siemens Energy Germany",
        "aliases": [
            "Siemens Energy AG",
            "Siemens Energy",
            "Siemens Energy Global GmbH & Co. KG",
        ],
        "industry": "Tecnologia energética (turbinas a gás/vapor, transmissão, transformadores, hidrogênio verde)",
        "size": "~100.000 colaboradores (grupo global; site oficial); sites DE em Berlim, Erlangen, Mülheim, Dresden, Görlitz",
        "hq": "Munique, Baviera, Alemanha (sede global)",
        "international": "Presença em 90+ países; spin-off da Siemens AG (2020); listada na bolsa de Frankfurt",
        "business_areas": [
            "Gas Services (turbinas a gás, compressores)",
            "Grid Technologies (transmissão, transformadores, subestações)",
            "Transformation of Industry (hidrogênio, eletrificação industrial)",
            "Steam Turbines",
        ],
        "website": "https://www.siemens-energy.com",
        "careers_url": "https://jobs.siemens-energy.com/de_DE/search-results",
        "checked": TODAY,
        "sources": [
            _src(
                "Siemens Energy Jobs — portal global (Avature) com vagas de estudante/estágio na Alemanha (Berlin, Erlangen, Mülheim, Dresden); programa Early Careers documentado",
                "https://jobs.siemens-energy.com/de_DE/search-results",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Portal de carreiras global (Avature) com filtro por país Alemanha e vagas de estudante ativas; a menção \"Siemens Energy employees with current visa sponsorship may be eligible for internal transfers\" refere-se a vagas US — não se aplica à operação DE (regra F10). Páginas DE checadas 2026-10-26 sem declaração própria sobre visto para estágios.",
    },

    # === TenneT ===
    {
        "company": "TenneT Germany",
        "aliases": [
            "TenneT TSO GmbH",
            "TenneT Germany",
            "TenneT",
        ],
        "industry": "Operador de sistema de transmissão (TSO; energia elétrica de alta tensão)",
        "size": "~5.000 colaboradores (TenneT Germany; site oficial); maior TSO da Alemanha",
        "hq": "Bayreuth, Baviera, Alemanha (sede TSO GmbH); gestão em Hamburgo",
        "international": "TSO na Alemanha e Países Baixos; parte do grupo TenneT Holding B.V. (NL); conexão offshore Nordsee",
        "business_areas": [
            "Operação de rede de altíssima tensão (380/220 kV)",
            "Conexão offshore de parques eólicos",
            "Gestão de congestionamento (Redispatch 2.0)",
            "Desenvolvimento de rede (Target Grid 2045)",
        ],
        "website": "https://www.tennet.eu",
        "careers_url": "https://karriere.tennet.eu/apprentice",
        "checked": TODAY,
        "sources": [
            _src(
                "TenneT Karriereseite — Auszubildende, Duale Studenten & Schülerpraktikanten (programa formal com onboarding week em Goslar; inscrição online)",
                "https://karriere.tennet.eu/apprentice",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de carreira para estudantes/duais/aprendizes descreve programa estruturado com onboarding week no Zeppelin training centre (Goslar) e inscrição online; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "TenneT Karriereseite: \"Auszubildende, Duale Studenten & Schülerpraktikanten... With practical hands-on training, individual support and exciting challenges, we offer you the perfect opportunity to start your career.\" — programa formal para estudantes duais e aprendizes no maior TSO da Alemanha.",
                "url": "https://karriere.tennet.eu/apprentice",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estudantes duais/aprendizes com onboarding estruturado; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === Texas Instruments (Alemanha) ===
    {
        "company": "Texas Instruments Germany",
        "aliases": [
            "Texas Instruments Deutschland GmbH",
            "TI Germany",
            "TI Deutschland",
        ],
        "industry": "Semicondutores (analógicos, embedded processing)",
        "size": "~34.000 colaboradores (grupo global); site DE em Freising (Munique) — MINT Camp, vendas, design",
        "hq": "Dallas, TX, EUA (grupo); TI Germany em Freising, Baviera",
        "international": "Design, manufatura e vendas em 30+ países; sites de design em Freising, Belfast, Bangalore, etc.",
        "business_areas": [
            "Semicondutores analógicos",
            "Processadores embarcados",
            "Referência de tensão e data converters",
            "Educação STEM (MINT Camp em Freising)",
        ],
        "website": "https://www.ti.com",
        "careers_url": "https://careers.ti.com",
        "checked": TODAY,
        "sources": [
            _src(
                "TI Careers — Engineer your future (requisito: \"Be authorized to work in the United States without visa sponsorship now or in the future\" — programa US)",
                "https://careers.ti.com/engineer-your-future",
                "primary",
            ),
            _src(
                "TI Corporate Citizenship Report 2025 — MINT Camp em Freising, Alemanha recebe estudantes para carreiras STEM",
                "https://www.ti.com/lit/ml/szzo174/szzo174.pdf",
                "secondary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "A declaração explícita de \"no visa sponsorship\" e requisito de autorização de trabalho própria refere-se ao programa US (careers.ti.com) — não se estende à operação DE (regra F10: registro IND por país). O MINT Camp em Freising é citado no relatório de cidadania corporativa 2025, mas páginas de carreiras DE checadas 2026-10-26 sem declaração própria sobre visto para estágios na Alemanha.",
    },

    # === Analog Devices (Alemanha) ===
    {
        "company": "Analog Devices Germany",
        "aliases": [
            "Analog Devices GmbH",
            "ADI Germany",
            "Analog Devices Deutschland",
        ],
        "industry": "Semicondutores (analog, mixed-signal, DSP, RF)",
        "size": "~26.000 colaboradores (grupo global); site DE em München/Livingston — design center, vendas",
        "hq": "Wilmington, MA, EUA (grupo); ADI Germany em München, Baviera",
        "international": "Design centers e vendas em 30+ países; ~500 estagiários/ano globalmente, 60% conversão para full-time",
        "business_areas": [
            "Conversores de dados (ADC/DAC)",
            "Amplificadores e RF/microwave",
            "Processadores de sinal digital (SHARC, Blackfin)",
            "Power management e MEMS",
        ],
        "website": "https://www.analog.com",
        "careers_url": "https://www.analog.com/en/careers/student-resources.html",
        "checked": TODAY,
        "sources": [
            _src(
                "Analog Devices — Student Resources (programa global de estágios: 500+/ano, verão 12-14 semanas, co-ops 6-12 meses; parceiros universitários globais)",
                "https://www.analog.com/en/careers/student-resources.html",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Página global de Student Resources descreve programa de estágios/co-ops com parceiros universitários worldwide; não há página específica para estágios na Alemanha nem declaração de visto/autorização para o contexto DE checadas 2026-10-26 (regra F10: registro IND por país).",
    },

    # === Copeland (Alemanha) ===
    {
        "company": "Copeland Germany",
        "aliases": [
            "Copeland GmbH",
            "Copeland Germany",
            "Copeland Climate Technologies Germany",
        ],
        "industry": "Tecnologia climática (compressores, refrigeração, HVACR, aquecimento)",
        "size": "~18.000 colaboradores (grupo global, pós-spin-off Emerson 2024); operações DE em Sulzbach/Frankfurt",
        "hq": "St. Louis, MO, EUA (grupo); Copeland Germany em Sulzbach, Hessen",
        "international": "Presença global; marcas Copeland, Vilter, Carlyle, White-Rodgers; foco em sustentabilidade e descarbonização",
        "business_areas": [
            "Compressores para refrigeração comercial e industrial",
            "Soluções HVACR (bombas de calor, VRF)",
            "Controles e termostatos (White-Rodgers, Sensi)",
            "Soluções de transição energética (CO2, propano, HFOs)",
        ],
        "website": "https://www.copeland.com",
        "careers_url": "https://www.copeland.com/de-de/careers",
        "checked": TODAY,
        "sources": [
            _src(
                "Copeland DE — Karriereseite em alemão (Students & Graduates; Early Career Development Program Accelerate; portal de vagas local)",
                "https://www.copeland.com/de-de/careers",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Karriereseite alemã (copeland.com/de-de/careers) com seção Students & Graduates e programa Accelerate Early Career Development; páginas checadas 2026-10-26 sem declaração pública sobre visto/autorização para não-UE nos estágios alemães. A declaração de \"no visa sponsorship\" do programa US NÃO se aplica à entry DE (regra F10: registro IND por país).",
    },

    # === DSV (Alemanha) ===
    {
        "company": "DSV Germany",
        "aliases": [
            "DSV Road GmbH",
            "DSV Air & Sea GmbH",
            "DSV Germany",
            "DSV Solutions GmbH",
        ],
        "industry": "Logística e transporte (road, air, sea, solutions; absorveu DB Schenker 2024)",
        "size": "~75.000 colaboradores (grupo global); >1.500 escritórios; operação DE significativa pós-aquisição Schenker",
        "hq": "Hedehusene, Dinamarca (grupo); DSV Germany em Hamburgo, Frankfurt, Munique, etc.",
        "international": "Presença em 80+ países; aquisição da DB Schenker (2024) expandiu rede europeia",
        "business_areas": [
            "DSV Road (transporte rodoviário)",
            "DSV Air & Sea (frete aéreo e marítimo)",
            "DSV Solutions (contract logistics, warehousing)",
            "Integração DB Schenker (em andamento)",
        ],
        "website": "https://www.dsv.com",
        "careers_url": "https://www.dsv.com/en/careers/job-areas/trainee-programmes",
        "checked": TODAY,
        "sources": [
            _src(
                "DSV Trainee Programmes — global trainee programme (freight forwarding certification via DSV Trainee Academy; rotações internacionais)",
                "https://www.dsv.com/en/careers/job-areas/trainee-programmes",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Programa global de traineeships documentado (DSV Trainee Academy, certificação freight forwarder, rotações internacionais); página de carreiras DE e estágios checadas 2026-10-26 sem declaração pública sobre visto/autorização para não-UE.",
    },

    # === BioNTech ===
    {
        "company": "BioNTech",
        "aliases": [
            "BioNTech SE",
            "BioNTech",
            "BioNTech Germany",
        ],
        "industry": "Biotecnologia/imunoterapia (mRNA, oncologia, doenças infecciosas; absorveu CureVac 2025)",
        "size": "~4.500 colaboradores (grupo global; relatório 2025); HQ em Mainz, sites em Marburg, Idar-Oberstein, Cambridge UK, Boston USA",
        "hq": "Mainz, Rheinland-Pfalz, Alemanha (An der Goldgrube 12)",
        "international": "Operações globais; parcerias com Pfizer, Roche/Genentech, Bristol Myers, Fosun, InstaDeep (AI subsidiary); listada na Nasdaq (BNTX)",
        "business_areas": [
            "Oncologia (mRNA cancer vaccines, ADC, bispecific antibodies, CAR-T)",
            "Doenças infecciosas (COVID-19, influenza, HIV, TB mRNA vaccines)",
            "Plataforma mRNA e manufatura própria",
            "IA para descoberta de fármacos (InstaDeep)",
        ],
        "website": "https://www.biontech.de",
        "careers_url": "https://www.biontech.de/career",
        "checked": TODAY,
        "sources": [
            _src(
                "BioNTech Career — página de carreiras (link no rodapé do site oficial; Investors/Media/Career)",
                "https://www.biontech.de/career",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Site oficial (biontech.de) tem link Career no rodapé; páginas de estudantes/estágios e FAQ checadas 2026-10-26 sem declaração pública aplicável sobre visto/autorização para estágios na Alemanha.",
    },

    # === GIZ ===
    {
        "company": "GIZ",
        "aliases": [
            "Deutsche Gesellschaft für Internationale Zusammenarbeit (GIZ) GmbH",
            "GIZ GmbH",
            "GIZ",
        ],
        "industry": "Cooperação internacional para desenvolvimento sustentável (empresa federal alemã)",
        "size": "~25.000 colaboradores (global); principais locais DE: Berlim, Bonn, Eschborn",
        "hq": "Bonn/Eschborn, NRW, Alemanha (sede legal: Eschborn; representação: Berlim)",
        "international": "Projetos em 120+ países; empresa 100% federal (BMZ acionista); regime próprio de estágio remunerado e limitado",
        "business_areas": [
            "Cooperação técnica bilateral e multilateral",
            "Assessoria em políticas públicas",
            "Gestão de programas de desenvolvimento",
            "Serviços de consultoria internacional",
        ],
        "website": "https://www.giz.de",
        "careers_url": "https://www.giz.de/en/career/jobs/internships",
        "checked": TODAY,
        "sources": [
            _src(
                "GIZ — Internships (programa oficial: estágios na DE em Berlim/Bonn/Eschborn e worldwide; máx 6 meses; requisitos: matrícula universitária ou graduação ≤6 meses; seguro saúde obrigatório na DE)",
                "https://www.giz.de/en/career/jobs/internships",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Empresa federal alemã com regime próprio de estágio (remunerado, máx 6 meses, na DE e worldwide); página oficial declara requisitos (matrícula, graduação ≤6 meses, seguro saúde obrigatório na DE) e menciona estágios abroad — statement de internacionalidade explícito, ótimo para visa_friendly; sem declaração incondicional de patrocínio de visto — unclear (programa federal citado).",
        "sources_for": {"visa_policy": [
            {
                "text": "GIZ Internships: \"In Germany, you can complete an internship in one of our major locations in Berlin, Bonn or Eschborn... Internships in Germany or abroad are possible for a maximum of six months... For an internship within Germany, you need statutory health insurance unless the internship is a mandatory part of a vocational training programme.\" — programa federal explícito para não-UE (worldwide), com regras claras de seguro e duração.",
                "url": "https://www.giz.de/en/career/jobs/internships",
                "quality": "primary",
                "checked": TODAY,
                "note": "Empresa federal com programa de estágio próprio (remunerado, ≤6 meses, DE + worldwide); requisitos declarados incluem seguro saúde obrigatório na DE — evidência de pathway institucional para internacionais (unclear), não sponsorship incondicional.",
            },
        ]},
    },

    # === INVERTO ===
    {
        "company": "INVERTO",
        "aliases": [
            "Inverto GmbH",
            "INVERTO",
            "Inverto, a BCG company",
        ],
        "industry": "Consultoria de procurement e supply chain (subsidiária da Boston Consulting Group)",
        "size": "~1.000 colaboradores (EMESA + NA); escritórios DE: Colônia, Munique, Berlim (novo 2025)",
        "hq": "Colônia, NRW, Alemanha (sede EMESA)",
        "international": "Parte do BCG; escritórios na Europa, Oriente Médio, África do Sul, América do Norte, Ásia-Pacífico",
        "business_areas": [
            "Procurement consulting (strategic sourcing, category management)",
            "Supply chain transformation",
            "Digital procurement (analytics, AI)",
            "Sustainability & ESG in supply chain",
        ],
        "website": "https://inverto.com",
        "careers_url": "https://inverto.com/en/careers/search-jobs",
        "checked": TODAY,
        "sources": [
            _src(
                "INVERTO FAQ — Work authorization: \"Work authorization requirements vary by region and location. In Asia Pacific, you do not need to hold an existing work permit to apply... For other locations, visa sponsorship may be available for certain positions.\" DACH: Sapphire Program para estagiários de alto desempenho",
                "https://inverto.com/en/careers/faqs",
                "primary",
            ),
            _src(
                "INVERTO Careers — Consulting Track (Intern → Associate Consultant → ... Managing Director); working students em Colônia/Munique",
                "https://inverto.com/en/careers/career-opportunities/consulting-track",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "FAQ oficial declara: \"Work authorization requirements vary by region and location... For other locations, visa sponsorship may be available for certain positions\" + DACH tem Sapphire Program para retenção de estagiários de alto desempenho — statement condicional de sponsorship possível, não garantia incondicional; checado 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "INVERTO FAQ: \"Work authorization requirements vary by region and location. In Asia Pacific, you do not need to hold an existing work permit to apply... For other locations, visa sponsorship may be available for certain positions.\" + DACH: Sapphire Program para estagiários destaque — sponsorship condicional/por vaga.",
                "url": "https://inverto.com/en/careers/faqs",
                "quality": "primary",
                "checked": TODAY,
                "note": "Declaração condicional oficial (varia por região/vaga; sponsorship \"may be available\") — regra da curadoria: condicional => unclear, não explicit_support. Programa Sapphire DACH citado como retenção.",
            },
        ]},
    },

    # === Beiersdorf ===
    {
        "company": "Beiersdorf",
        "aliases": [
            "Beiersdorf AG",
            "Beiersdorf",
            "NIVEA Company",
        ],
        "industry": "Cuidados com a pele e cosméticos (NIVEA, Eucerin, Hansaplast, La Prairie)",
        "size": "~20.000 colaboradores (grupo global); HQ em Hamburgo",
        "hq": "Hamburgo, Alemanha",
        "international": "Presença em 150+ países; marcas globais NIVEA, Eucerin, Hansaplast, La Prairie, Aquaphor",
        "business_areas": [
            "Consumer (NIVEA, Eucerin, Hansaplast)",
            "Tesa (fitas adesivas — divisão separada)",
            "La Prairie (luxo)",
            "Pesquisa e desenvolvimento (skin science)",
        ],
        "website": "https://www.beiersdorf.com",
        "careers_url": "https://www.beiersdorf.com/career/students",
        "checked": TODAY,
        "sources": [
            _src(
                "Beiersdorf — BEYOND Graduate Program (trainee 18-24 meses; benefícios variam por país; aplicação via sites locais)",
                "https://www.beiersdorf.com/career/students/trainee-program/overview",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "BEYOND Graduate Program (trainee) documentado com benefícios que variam por país (\"please find further information on the local websites of the countries you want to apply to\"); páginas de estágio/working student DE checadas 2026-10-26 sem declaração própria sobre visto.",
    },

    # === Aurubis ===
    {
        "company": "Aurubis",
        "aliases": [
            "Aurubis AG",
            "Aurubis",
            "Aurubis Hamburg",
        ],
        "industry": "Multimetais e reciclagem (cobre, metais preciosos, sulfuric acid; líder global em reciclagem de cobre)",
        "size": "~7.000 colaboradores (grupo); HQ Hamburg + Lünen, Stolberg, Emmerich, Röthenbach, Beerse (BE), Buffalo (US), Pirdop (BG)",
        "hq": "Hamburgo, Alemanha (Brooktorkai 18, HafenCity)",
        "international": "Produção e reciclagem na Europa (DE, BE, BG, FI, NL) e EUA; maior reciclador de cobre do mundo",
        "business_areas": [
            "Produção de cátodos de cobre",
            "Reciclagem de materiais complexos (e-scrap, resíduos industriais)",
            "Produtos de cobre contínuo (wire rod, shapes)",
            "Metais preciosos e sulfuric acid",
        ],
        "website": "https://www.aurubis.com",
        "careers_url": "https://jobs.aurubis.com/zielgruppe/studierende-berufseinsteigende",
        "checked": TODAY,
        "sources": [
            _src(
                "Aurubis Jobs — Studierende & Berufseinsteigende (vagas ativas de Werkstudent em Hamburg: Umweltschutz, Instandhaltung, Anlagentechnik EMR; portal oficial)",
                "https://jobs.aurubis.com/zielgruppe/studierende-berufseinsteigende",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de vagas (jobs.aurubis.com) lista vagas ativas de Werkstudent em Hamburg (Umweltschutz, Instandhaltung, Anlagentechnik EMR) com requisitos de matrícula; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "Aurubis Jobs: \"Werkstudent Umweltschutz (m/w/d) (Hamburg) — Bei Aurubis erhältst du spannende Einblicke in die Themen REACH, Chemikaliensicherheit und Sicherheitsdatenblätter... Eingeschriebener Student (m/w/d) im Bereich...\". Vagas ativas de Werkstudent no portal oficial DE.",
                "url": "https://jobs.aurubis.com/zielgruppe/studierende-berufseinsteigende",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa de Werkstudent com vagas ativas citadas no portal oficial (Hamburg); sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === Jungheinrich ===
    {
        "company": "Jungheinrich",
        "aliases": [
            "Jungheinrich AG",
            "Jungheinrich",
            "Jungheinrich Deutschland",
        ],
        "industry": "Intralogística (empilhadeiras, sistemas de armazenagem, automação, robótica; líder em Li-ion)",
        "size": "~20.000 colaboradores (grupo); >8.200 na DE; 23 Niederlassungen/Stützpunkte na DE",
        "hq": "Hamburgo, Alemanha (Stammsitz Barmbek)",
        "international": "42 países; Magazino GmbH (robótica autônoma) como subsidiária",
        "business_areas": [
            "Empilhadeiras e equipamentos de armazenagem",
            "Sistemas de automação (AGV, shuttle, picking robótico)",
            "Energia (Li-ion, lead-acid, fuel cell)",
            "Serviços e digitalização (Jungheinrich +C)",
        ],
        "website": "https://www.jungheinrich.de",
        "careers_url": "https://www.jungheinrich.de/karriere/praktikum-und-werkstudium",
        "checked": TODAY,
        "sources": [
            _src(
                "Jungheinrich — Praktikum und Werkstudium (página dedicada: envio de e-mail para karriere@jungheinrich.de com Wunschzeitraum, Einsatzort, CV, último certificado; inscrição direta)",
                "https://www.jungheinrich.de/karriere/praktikum-und-werkstudium",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial dedicada a Praktikum und Werkstudium com instrução de aplicação direta por e-mail (karriere@jungheinrich.de) e campos obrigatórios (Wunschzeitraum, Einsatzort, CV, Zeugnis); sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "Jungheinrich Praktikum und Werkstudium: \"Als Werkstudentin oder Werkstudent bei Jungheinrich sammelst du Praxiserfahrung, wendest Wissen an und startest deine Karriere. Schick uns eine E-Mail mit Wunschzeitraum, Einsatzort, kurzem Lebenslauf und deinem letzten Zeugnis an karriere@jungheinrich.de!\" — página oficial com aplicação direta por e-mail.",
                "url": "https://www.jungheinrich.de/karriere/praktikum-und-werkstudium",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de Praktikum/Werkstudent com aplicação direta por e-mail dedicada; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === Hermes Deutschland ===
    {
        "company": "Hermes Deutschland",
        "aliases": [
            "Hermes Germany GmbH",
            "Hermes Deutschland",
            "Hermes Germany",
            "Hermes Fulfilment GmbH",
        ],
        "industry": "Logística de encomendas e fulfilment (maior parcel delivery DE; >1M pacotes/dia; 5.500+ colaboradores)",
        "size": "~5.500 colaboradores (Hermes Germany); parte do grupo Otto / Hermes Europe",
        "hq": "Hamburgo, Alemanha",
        "international": "Hermes Europe com redes em DE, FR, UK, IT, AT, PL, RU; parte do grupo Otto (DE)",
        "business_areas": [
            "Entrega de encomendas (B2C, C2C)",
            "Fulfilment e warehousing (Hermes Fulfilment)",
            "Logística internacional (Hermes Europe)",
            "Serviços de retorna e value-added",
        ],
        "website": "https://www.hermesworld.com",
        "careers_url": "https://www.hermesworld.com/de/karriere/unsere-gesellschaften/hermes-germany/studierende-absolventen",
        "checked": TODAY,
        "sources": [
            _src(
                "Hermes World — Studierende & Absolventen bei der Hermes Germany (Praktikum em Marketing, Vertrieb, HR, Controlling, Software-Entwicklung, Supply-Chain-Management)",
                "https://www.hermesworld.com/de/karriere/unsere-gesellschaften/hermes-germany/studierende-absolventen",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de estudantes da Hermes Germany lista áreas de estágio (Marketing, Vertrieb, HR, Controlling, Software, Supply Chain) e menciona que estagiários assumem responsabilidade desde o dia 1; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "Hermes Germany Studierende & Absolventen: \"Ob Marketing oder Vertrieb, Human Resources oder Controlling, Software-Entwicklung oder Supply-Chain-Management: Ein Praktikum bei Hermes bietet dir als Student...\" — página oficial com áreas de estágio listadas.",
                "url": "https://www.hermesworld.com/de/karriere/unsere-gesellschaften/hermes-germany/studierende-absolventen",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estágios em múltiplas áreas corporativas citado no portal oficial; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === Zollner ===
    {
        "company": "Zollner",
        "aliases": [
            "Zollner Elektronik AG",
            "Zollner AG",
            "Zollner Elektronik",
        ],
        "industry": "EMS (Electronic Manufacturing Services; líder europeu; PCB assembly, box build, test)",
        "size": "~15.000 colaboradores (grupo); maior empregador da região Cham (Oberpfalz); sites DE: Zandt, Cham, Nürnberg, etc.",
        "hq": "Zandt, Baviera, Alemanha",
        "international": "Produção na DE, RO, CN, IN, US, CZ, HU, RO; >20 localidades globais",
        "business_areas": [
            "PCB assembly (SMT, THT)",
            "Box build e system integration",
            "Test engineering (ICT, FCT, boundary scan)",
            "Supply chain management e component engineering",
        ],
        "website": "https://www.zollner.de",
        "careers_url": "https://www.zollner.de/karriere/stellenboerse",
        "checked": TODAY,
        "sources": [
            _src(
                "Zollner Karriereseite — Stellenbörse + Initiativbewerbung + Schüler/Ausbildung/Duales Studium (programa para estudantes mencionado: Praktikum, Abschlussarbeit, Werkstudentenjobs)",
                "https://www.zollner.de/karriere",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Karriereseite menciona programa para estudantes (\"Das Angebot reicht von Ferienjobs über Praktika – gerne auch Schülerpraktika – bis hin zu einer Ausbildung, zu Abschlussarbeiten und Werkstudentenjobs\") mas sem página dedicada a estudantes nem declaração de visto; checado 2026-10-26.",
    },

    # === EJOT ===
    {
        "company": "EJOT",
        "aliases": [
            "EJOT GmbH & Co. KG",
            "EJOT SE & Co. KG",
            "EJOT",
        ],
        "industry": "Tecnologia de fixação (parafusos, âncoras, sistemas de fixação para construção, automotivo, eletrônica)",
        "size": "~3.900 colaboradores (grupo); 38 empresas; >36.000 produtos; 100+ anos (site oficial)",
        "hq": "Bad Berleburg, NRW, Alemanha (Wittgenstein)",
        "international": "Subsidiárias em 30+ países (Europa, Américas, Ásia, África); family-owned",
        "business_areas": [
            "Fixação para construção (Construction)",
            "Fixação automotiva (Automotive)",
            "Fixação para eletrônica (EJOT EC, pt® screws)",
            "Sistemas de ancoragem química e mecânica",
        ],
        "website": "https://www.ejot.com",
        "careers_url": "https://www.ejot.com/studenten",
        "checked": TODAY,
        "sources": [
            _src(
                "EJOT — Students (Internship, Werkstudent, Academic Thesis, Holiday Employment; aplicação via portal online; 86% orgulho, 90% recomendam, 88% ficariam 5+ anos)",
                "https://www.ejot.com/studenten",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de estudantes descreve quatro modalidades (Internship, Werkstudent, Academic Thesis, Holiday Employment) com aplicação via portal online e estatísticas de satisfação; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "EJOT Students: \"Gain valuable experience during an internship, as a student trainee or in the course of your thesis... If you are interested, please write to us via our online applicant portal.\" — página oficial com quatro modalidades e portal de aplicação.",
                "url": "https://www.ejot.com/studenten",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estudantes com quatro modalidades e portal de aplicação online; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === DMK (Deutsches Milchkontor) ===
    {
        "company": "DMK",
        "aliases": [
            "DMK Deutsches Milchkontor GmbH",
            "DMK Group",
            "DMK",
            "Milram",
        ],
        "industry": "Laticínios (queijo, leite, ingredientes, whey; maior cooperativa leiteira DE)",
        "size": "~7.500 colaboradores (grupo); sites DE: Zeven, Bremen, Altentreptow, Edewecht, Georgsmarienhütte, Rosenheim",
        "hq": "Zeven, Baixa Saxônia, Alemanha",
        "international": "Exportação global; marcas Milram, Oldenburger, Humana, DMK Baby; joint ventures na China, EUA",
        "business_areas": [
            "Queijos (fatiados, ralados, especiais)",
            "Leite e bebidas lácteas",
            "Ingredientes (whey, casein, milk powder)",
            "Nutrição infantil (Humana) e medical nutrition",
        ],
        "website": "https://www.dmk.de",
        "careers_url": "https://dmk.de/de/karriere/stellenangebote",
        "checked": TODAY,
        "sources": [
            _src(
                "DMK Stellenangebote — portal de vagas (filtro por localização; vagas técnicas, produção, logística, vendas; sem página dedicada a estudantes visível)",
                "https://dmk.de/de/karriere/stellenangebote",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Portal de vagas geral com filtro por localização; nenhuma página dedicada a programas de estudantes/estágios encontrada nas buscas 2026-10-26 — não verificado.",
    },

    # === Zentis ===
    {
        "company": "Zentis",
        "aliases": [
            "Zentis GmbH & Co. KG",
            "Zentis Fruchtwelt GmbH & Co. KG",
            "Zentis",
        ],
        "industry": "Alimentos (geleias, chocolate, nut spreads, marzipan, fruit preparations; marcas: Nusspli, Belmandel, Pflümli, Zentis Bärchen)",
        "size": "~1.500 colaboradores (grupo); HQ Aachen, produção em Aachen, Grafschaft, Polônia, EUA",
        "hq": "Aachen, NRW, Alemanha",
        "international": "Produção em DE, PL, US; exportação global; parte do grupo Hero (CH) desde 2023",
        "business_areas": [
            "Fruit preparations (para laticínios, sorvetes, panificação)",
            "Sweet spreads (Nusspli, Belmandel, Pflümli, vegan balls)",
            "Marzipan e raw marzipan mass",
            "Chocolate confectionery",
        ],
        "website": "https://www.zentis.de",
        "careers_url": "https://www.zentis.de/de/karriere/ausbildung-und-berufsstart",
        "checked": TODAY,
        "sources": [
            _src(
                "Zentis — Ausbildung & Berufsstart (Praktikum para estudantes: Hochschulpraktikum, duração individual, acompanhamento por colegas experientes, projetos responsáveis)",
                "https://www.zentis.de/de/karriere/ausbildung-und-berufsstart",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de Ausbildung & Berufsstart menciona Praktikum para estudantes (Hochschulpraktikum, duração individual, betreuung, projetos responsáveis) com botão de aplicação direta; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "Zentis Ausbildung & Berufsstart: \"Für Schüler:innen und Studierende... Dauer individuell... Wertvolle Praxiserfahrung in vielfältigen Arbeitsbereichen... Betreuung durch erfahrene Kolleginnen und Kollegen... Aktive Unterstützung bei verantwortungsvollen Projekten.\" — página oficial com programa de Hochschulpraktikum.",
                "url": "https://www.zentis.de/de/karriere/ausbildung-und-berufsstart",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de Hochschulpraktikum para estudantes citado no portal oficial; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === Rockwool (DEUTSCHE ROCKWOOL) ===
    {
        "company": "Rockwool Germany",
        "aliases": [
            "DEUTSCHE ROCKWOOL GmbH & Co. KG",
            "Rockwool Deutschland",
            "Rockwool Germany",
            "Rockwool",
        ],
        "industry": "Isolamento de lã de rocha (leader mundial; fire resilience, acústico, térmico)",
        "size": "~12.000 colaboradores (grupo global); DEUTSCHE ROCKWOOL em Gladbeck (NRW) — sede e fábrica principal",
        "hq": "Gladbeck, NRW, Alemanha (Rockwool Str. 37-41)",
        "international": "Grupo dinamarquês (HQ Hedehusene); produção em 40+ fábricas no mundo; líder mundial em stone wool",
        "business_areas": [
            "Isolamento térmico, acústico e fire protection",
            "Sistemas de telhado e fachada",
            "Isolamento industrial e técnico",
            "Horticultura (Grodan)",
        ],
        "website": "https://www.rockwool.com",
        "careers_url": "https://www.rockwool.com/de/unternehmen/karriere/praktika-und-studentenjobs",
        "checked": TODAY,
        "sources": [
            _src(
                "ROCKWOOL — Praktika und Studentenjobs (página dedicada: aplicação por e-mail bewerbung@rockwool.com; contatos por área kaufmännisch/gewerblich-technisch; FAQ com duração flexível, áreas: Einkauf, Vertrieb, Marketing, Personal, Logistik, Controlling)",
                "https://www.rockwool.com/de/unternehmen/karriere/praktika-und-studentenjobs",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial dedicada a Praktika und Studentenjobs com aplicação por e-mail direta (bewerbung@rockwool.com), contatos nomeados por área (kaufmännisch/gewerblich-technisch), FAQ com duração flexível e áreas listadas; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "ROCKWOOL Praktika und Studentenjobs: \"Praktische Erfahrungen sind für die berufliche Zukunft ebenso ausschlaggebend wie die Theorie... Bewirb dich initiativ oder auf ein offenes Stellenangebot per E-Mail... Student/-in: Bitte füge deiner Bewerbung Anschreiben, Lebenslauf, einen Leistungsnachweis und die Immatrikulationsbescheinung deiner Universität bei.\" — página oficial com processo de aplicação documentado.",
                "url": "https://www.rockwool.com/de/unternehmen/karriere/praktika-und-studentenjobs",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estágios/student jobs com aplicação por e-mail, contatos dedicados e FAQ; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === Südpack ===
    {
        "company": "Südpack",
        "aliases": [
            "SÜDPACK Verpackungen SE & Co. KG",
            "Südpack",
            "Suedpack",
        ],
        "industry": "Filmes de alta performance para embalagens (food, medical, non-food, technical; >60 anos)",
        "size": "~2.500 colaboradores (grupo); sites DE: Ochsenhausen, Biberach, Villingen-Schwenningen",
        "hq": "Ochsenhausen, Baden-Württemberg, Alemanha",
        "international": "Produção na DE, FR, ES, PL, US, BR, CN, IN; foco em sustentabilidade (PPWR, closed-loop recycling)",
        "business_areas": [
            "Filmes para embalagens de carne e queijo",
            "Filmes médicos e farmacêuticos",
            "Compostos (convencionais e bio-based)",
            "Sustentabilidade e reciclagem em ciclo fechado",
        ],
        "website": "https://www.sudpack.com",
        "careers_url": "https://careers.sudpack.com",
        "checked": TODAY,
        "sources": [
            _src(
                "SÜDPACK — Career portal (link no site oficial; Phenom ATS; vagas para estudantes não explicitamente listadas na busca)",
                "https://careers.sudpack.com",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Portal de carreiras (Phenom ATS) acessível via site oficial; páginas de estudantes/estágios checadas 2026-10-26 sem declaração pública aplicável sobre visto/autorização para estágios na Alemanha.",
    },

    # === tk nucera (thyssenkrupp nucera) ===
    {
        "company": "tk nucera",
        "aliases": [
            "thyssenkrupp nucera AG & Co. KGaA",
            "thyssenkrupp nucera",
            "tk nucera",
            "thyssenkrupp nucera Germany",
        ],
        "industry": "Eletrolisadores para hidrogênio verde (alcalina AWE; engenharia, procurement, construction; >600 projetos, >10 GW instalados)",
        "size": "~600 colaboradores (grupo); HQ Dortmund + Arnstadt, Milão, Houston, Riad, Mumbai",
        "hq": "Dortmund, NRW, Alemanha (Freie-Vogel-Str. 385a)",
        "international": "Projetos em 8 países/4 continentes; listada na bolsa de Frankfurt; parte do grupo thyssenkrupp",
        "business_areas": [
            "Eletrolisadores alcalinos (AWE) para H2 verde",
            "Engenharia, procurement, construction (EPC)",
            "Service e operações de plantas",
            "P&D em tecnologias de hidrogênio",
        ],
        "website": "https://www.thyssenkrupp-nucera.com",
        "careers_url": "https://new-era-is-you.com/de/students",
        "checked": TODAY,
        "sources": [
            _src(
                "thyssenkrupp nucera — Students (página dedicada: Working Student, Intern, Abschlussarbeit; vagas ativas em Dortmund/Duisburg: Graphic Design, R&D AWE, Strategic Program Management; FAQ com duração 3-6 meses, flexível conforme estudos)",
                "https://new-era-is-you.com/de/students",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial dedicada a estudantes (new-era-is-you.com/de/students) com vagas ativas de Working Student (Graphic Design, R&D AWE Design), Intern (Strategic Program Management) e Abschlussarbeit em Dortmund/Duisburg; FAQ declara duração 3-6 meses ajustável ao plano de estudos; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "thyssenkrupp nucera Students: \"Als Werkstudent:in kombinieren Sie Ihr Studium mit praktischen Erfahrungen in einem dynamischen Arbeitsumfeld... Die Dauer beträgt in der Regel 3 bis 6 Monate. Anpassungen sind je nach Studienplan möglich.\" — página oficial com vagas ativas em Dortmund/Duisburg e FAQ.",
                "url": "https://new-era-is-you.com/de/students",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estudantes com vagas ativas (Working Student, Intern, Abschlussarbeit) e FAQ sobre duração/horas; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === Applied Materials (Alemanha) ===
    {
        "company": "Applied Materials Germany",
        "aliases": [
            "Applied Materials GmbH",
            "Applied Materials Germany",
            "Applied Materials Dresden",
        ],
        "industry": "Equipamentos de semicondutores (material engineering solutions; líder global em WFE; sites DE: Dresden, Alzenau, Feldkirchen-Westerham)",
        "size": "~34.000 colaboradores (grupo global); sites DE em Dresden (manufatura/engineering), Alzenau, Feldkirchen",
        "hq": "Santa Clara, CA, EUA (grupo); Applied Materials Germany em Dresden, Saxônia",
        "international": "Operações globais; Flexible Technology Group em Alzenau (reciclabilidade de embalagens); MINT Camp em Freising (TI)",
        "business_areas": [
            "Equipamentos de deposição, gravação, ion implantation, CMP",
            "Semicondutores avançados (EUV, advanced packaging)",
            "Display (OLED, LCD)",
            "Automação de software (Automation Software)",
        ],
        "website": "https://www.appliedmaterials.com",
        "careers_url": "https://jobs.appliedmaterials.com/location/dresden-jobs/95/2921044-2842566-2935022/4",
        "checked": TODAY,
        "sources": [
            _src(
                "Applied Materials — Students and Early Career (programa global: estágios verão/co-op/yearlong; eventos com executivos, tech talks, ERGs, skills training; Dresden jobs ativos)",
                "https://www.appliedmaterials.com/sg/en/careers/students-early-career.html",
                "primary",
            ),
            _src(
                "Applied Materials Jobs — Dresden (vagas ativas: Customer Engineer, Process Support Engineer, Field Quality Engineer, Installation Engineer em Dresden, Saxony)",
                "https://jobs.appliedmaterials.com/location/dresden-jobs/95/2921044-2842566-2935022/4",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Programa global de Students and Early Career documentado (estágios verão/co-op/yearlong, eventos, mentorship); vagas ativas em Dresden no portal oficial; páginas DE checadas 2026-10-26 sem declaração própria sobre visto/autorização para estágios na Alemanha (regra F10: registro IND por país).",
    },

    # === sonnen ===
    {
        "company": "sonnen",
        "aliases": [
            "sonnen GmbH",
            "sonnen Group",
            "sonnen eServices Deutschland GmbH",
        ],
        "industry": "Armazenamento de energia inteligente (home batteries, VPP, sonnenFlat; 100% Shell desde 2019)",
        "size": "~1.500 colaboradores (grupo); produção em Wildpoldsried (Allgäu) + nova fábrica na Austrália; VPP na DE, IT, UK, US, AU",
        "hq": "Wildpoldsried, Baviera, Alemanha",
        "international": "Presença na DE, AT, CH, IT, UK, BE, NL, SE, US, AU; virtual power plants em múltiplos países",
        "business_areas": [
            "Home batteries (sonnenBatterie 10 hybrid/performance)",
            "Virtual Power Plant (sonnenVPP, regelleistung precificada DE/IT/UK)",
            "Energiedienstleistungen (sonnenFlat, sonnenFinance)",
            "Wallbox (sonnenCharger) e Home Energy Management",
        ],
        "website": "https://www.sonnen.de",
        "careers_url": "https://www.sonnen.de/karriere",
        "checked": TODAY,
        "sources": [
            _src(
                "sonnen — Karriereseite (link no rodapé: Karriere; páginas de imprensa mostram expansão europeia, novo Operations Center DE, produção 10k/mês)",
                "https://www.sonnen.de/karriere",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Karriereseite linkada no rodapé do site oficial; páginas de estudantes/estágios e imprensa checadas 2026-10-26 (expansão europeia, Operations Center, VPP) sem declaração pública sobre visto/autorização para estágios na Alemanha.",
    },

    # === Süss MicroTec ===
    {
        "company": "Süss MicroTec",
        "aliases": [
            "SÜSS MicroTec SE",
            "Suess MicroTec",
            "Süss MicroTec SE",
        ],
        "industry": "Equipamentos para semicondutores (lithography, bonding, coating, photomask; HQ Garching bei München; TecDAX/MDAX)",
        "size": "~1.300 colaboradores (grupo); HQ Garching, sites em Sternenfels, EUA, JP, CN, TW, MY, SG",
        "hq": "Garching bei München, Baviera, Alemanha",
        "international": "Vendas e serviço em 20+ países; listada no Prime Standard (TecDAX, MDAX); parceria estratégica Ignite Next (2026)",
        "business_areas": [
            "Mask aligners e UV projection scanners",
            "Coaters e developers (spin/spray)",
            "Temporary/permanent bonding para advanced packaging",
            "Photomask cleaning e processing",
        ],
        "website": "https://www.suss.com",
        "careers_url": "https://www.suss.com/career",
        "checked": TODAY,
        "sources": [
            _src(
                "SÜSS MicroTec — Career (link no site oficial; páginas de imprensa/financeiras dominam buscas; página de estudantes não encontrada nas buscas 2026-10-26)",
                "https://www.suss.com/career",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Site oficial (suss.com) tem link Career; buscas 2026-10-26 retornam apenas páginas financeiras/imprensa (ARIVA, wallstreet-online, boerse.de, investing.com) — nenhuma página dedicada a programas de estudantes/estágios encontrada — não verificado.",
    },

    # === TRIMET ===
    {
        "company": "TRIMET",
        "aliases": [
            "TRIMET Aluminium SE",
            "TRIMET Aluminium",
            "TRIMET",
        ],
        "industry": "Produção de alumínio (primário e reciclado; maior produtor UE; 8 localidades; 2.400 colaboradores; meta: alumínio climate-neutral 2045)",
        "size": "~2.400 colaboradores (grupo); sites DE: Essen, Hamburg, Voerde, Harzgerode, Kernfurt, etc.",
        "hq": "Essen, NRW, Alemanha (sede legal: TRIMET Aluminium SE)",
        "international": "Produção na DE e FR; reciclagem em Hamm (nova fábrica 2024); Aluminium Stewardship Initiative certificado",
        "business_areas": [
            "Alumínio primário (eletrólise)",
            "Reciclagem (scrap, anodos gastos, wire rod)",
            "Ligas de alumínio (auto, aero, embalagem, construção)",
            "Fundição (casting, rolling)",
        ],
        "website": "https://www.trimet.de",
        "careers_url": "https://www.trimet.de/karriere",
        "checked": TODAY,
        "sources": [
            _src(
                "TRIMET — Career (página oficial: \"No positions available at the moment\"; menciona ~50 aprendizes/ano; Ausbildung & duales Studium; sem página de estudantes/estágios visível)",
                "https://www.trimet.de/karriere",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Página oficial de carreira exibe \"No positions available at the moment\" e foca em Ausbildung & duales Studium (~50 jovens/ano); nenhuma página dedicada a estágios/working students para universitários encontrada nas buscas 2026-10-26 — não verificado.",
    },

    # === Schunk ===
    {
        "company": "Schunk",
        "aliases": [
            "SCHUNK GmbH & Co. KG",
            "Schunk",
            "Schunk GmbH",
        ],
        "industry": "Tecnologia de fixação, garras e automação (líder mundial em toolholding, workholding, gripping, automation; Lauffen/Mengen)",
        "size": "~4.000 colaboradores (grupo); sites DE: Lauffen am Neckar, Mengen, Hausen; global em 30+ países",
        "hq": "Lauffen am Neckar, Baden-Württemberg, Alemanha",
        "international": "Produção e vendas na Europa, Américas, Ásia; competence leader em clamping, gripping, automation",
        "business_areas": [
            "Toolholding e workholding (estacionário e rotativo)",
            "Gripping technology (mecânico, magnético, vácuo, adesivo)",
            "Automation technology (quick-change, robot accessories)",
            "Estacionário e rotativo para machine tools",
        ],
        "website": "https://schunk.com",
        "careers_url": "https://schunk.com/de/de/karriere/studierende",
        "checked": TODAY,
        "sources": [
            _src(
                "SCHUNK — Studierende (página DE: Praxissemester, Vorpraktikum, Bachelor/Master/Diplomarbeit, Technikerarbeit, Schülerpraktikum 2026; vagas ativas em Lauffen/Mengen; aplicação via portal)",
                "https://schunk.com/de/de/karriere/studierende",
                "primary",
            ),
            _src(
                "SCHUNK — Job offers Germany (63 vagas; filtros: Internship and working student position em Lauffen/Hausen/Mengen: Schülerpraktikum, Praxissemester, Abschlussarbeit, Vorpraktikum, Technikerarbeit)",
                "https://schunk.com/de/en/career/job-offers",
                "primary",
            ),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de estudantes (DE) lista modalidades formais (Praxissemester, Vorpraktikum, Bachelor/Master/Diplomarbeit, Technikerarbeit, Schülerpraktikum) com vagas ativas em Lauffen/Mengen/Hausen no portal de vagas (63 resultados DE); sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-26.",
        "sources_for": {"visa_policy": [
            {
                "text": "SCHUNK Studierende: \"Praxissemester 2026... Vorpraktikum 2026... Bachelor- /Master- und Diplomarbeit 2026... Technikerarbeit 2026\" — página oficial DE com modalidades formais e vagas ativas no portal (Lauffen/Mengen/Hausen).",
                "url": "https://schunk.com/de/de/karriere/studierende",
                "quality": "primary",
                "checked": TODAY,
                "note": "Programa formal de estudantes com múltiplas modalidades (Praxissemester, Vorpraktikum, Abschlussarbeiten, Technikerarbeit) e vagas ativas no portal oficial; sem declaração de sponsorship — unclear (programa citado).",
            },
        ]},
    },

    # === CeramTec ===
    {
        "company": "CeramTec",
        "aliases": [
            "CeramTec GmbH",
            "CeramTec Group",
            "CeramTec",
        ],
        "industry": "Cerâmica técnica avançada (medical: implantes ortopédicos/dentários; industrial: substrates, heat sinks, cutting tools; HQ Plochingen)",
        "size": "~3.500 colaboradores (grupo); sites DE: Plochingen (HQ), Lauf, Marktredwitz, Ebersbach, Lohmar, Wilhermsdorf",
        "hq": "Plochingen, Baden-Württemberg, Alemanha (CeramTec-Platz 1-9)",
        "international": "Produção na Europa (DE, CZ, SK), EUA, Ásia; >100 materiais cerâmicos; 120+ anos de expertise",
        "business_areas": [
            "Medical Technology (ortopedia, dental, cirurgia)",
            "Industrial (substrates, heat sinks eMobility, cutting tools SPK)",
            "Electronics (carriers, RF power, hermetic seals)",
            "Automotive/Mobility (sensores, e-mobility)",
        ],
        "website": "https://www.ceramtec.com",
        "careers_url": "https://www.ceramtec.com/contact",
        "checked": TODAY,
        "sources": [
            _src(
                "CeramTec — Contact Form (dropdown: \"careers at CeramTec\" encaminha para contato direto; Download Area com brochures técnicos; sem página de estudantes/estágios visível nas buscas)",
                "https://www.ceramtec.com/contact",
                "primary",
            ),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Formulário de contato com opção \"careers at CeramTec\" para encaminhamento direto; Download Area com brochures técnicos; buscas 2026-10-26 não retornam página dedicada a programas de estudantes/estágios — não verificado.",
    },
]

# ---------------------------------------------------------------------------
# UPDATES DE ENTRIES EXISTENTES — aliases extras medidos no dataset
# ---------------------------------------------------------------------------

EXISTING_UPDATES = {
    # MAHLE já existe no arquivo (adicionado na F9) — garantir aliases medidos
    "mahle": {
        "extra_aliases": [
            "MAHLE International GmbH",
            "MAHLE GmbH",
            "Mahle",
            "MAHLE Industrieservice GmbH",
        ],
    },
    # Hugo Boss já existe como tenant F124 (Phenom) — garantir aliases completos
    "hugo boss": {
        "extra_aliases": [
            "HUGO BOSS AG",
            "HUGO BOSS",
            "Boss",
        ],
    },
    # Mars Germany — entry separada da Mars global (regra F10: IND por país)
    # Verificar se já existe entrada "Mars" genérica
    # Não existe no arquivo atual — será adicionada como NEW_ENTRY acima
    # Texas Instruments Germany — entry separada (regra F10)
    # Analog Devices Germany — entry separada (regra F10)
    # Copeland Germany — entry separada (regra F10)
    # DSV Germany — entry separada (regra F10)
    # BioNTech — entry nova
    # Siemens Energy Germany — entry separada de Siemens AG (regra F10)
    # Siemens AG já existe no arquivo — garantir aliases
    "siemens": {
        "extra_aliases": [
            "Siemens AG",
            "Siemens Energy AG",
            "Siemens Healthineers AG",
        ],
    },
}


def main() -> None:
    data = json.loads(CI.read_text(encoding="utf-8"))
    companies = data["companies"]
    by_name = {e["company"].casefold(): e for e in companies}

    added: list[str] = []
    for entry in NEW_ENTRIES:
        key = entry["company"].casefold()
        if key in by_name:
            print(f"SKIP (existe): {entry['company']}")
            continue
        entry["country"] = "de"
        companies.append(entry)
        by_name[key] = entry
        added.append(entry["company"])

    merged: list[tuple[str, str]] = []
    upgraded: list[str] = []
    for key, upd in EXISTING_UPDATES.items():
        entry = by_name.get(key)
        if entry is None:
            print(f"UPDATE alvo ausente: {key}")
            continue
        aliases = entry.setdefault("aliases", [])
        known = {a.casefold() for a in aliases}
        for alias in upd.get("extra_aliases", []):
            if alias.casefold() not in known:
                aliases.append(alias)
                known.add(alias.casefold())
                merged.append((key, alias))
        if upd.get("visa_policy") and entry.get("visa_policy") != upd["visa_policy"]:
            entry["visa_policy"] = upd["visa_policy"]
            entry["checked"] = TODAY
            if upd.get("visa_policy_note"):
                entry["visa_policy_note"] = upd["visa_policy_note"]
            if upd.get("sources_for"):
                entry["sources_for"] = upd["sources_for"]
            upgraded.append(entry["company"])

    CI.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"entries adicionadas: {len(added)}")
    for c in added:
        print(f"  + {c}")
    print(f"aliases fundidos em entries existentes: {len(merged)}")
    for k, a in merged:
        print(f"  + {a} -> {k}")
    print(f"visa_policy upgrades: {len(upgraded)}")
    for c in upgraded:
        print(f"  ~ {c}")
    print(f"total entries: {len(companies)}")


if __name__ == "__main__":
    main()