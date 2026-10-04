#!/usr/bin/env python3
"""F10 curadoria onda 2: long tail + revisão da F9.

Idempotente no padrão do f9_curadoria.py:
- entries NOVAS (casefold do nome canônico ainda ausente) entram com
  ``country`` = "de" (ou ISO real quando aplicável);
- entries EXISTENTES podem ganhar aliases extras (strings EXATAS do
  dataset), upgrade de visa_policy (TE Connectivity) e REMOÇÃO de
  aliases factualmente errados (Everllence: "Daimler Truck AG"/
  "Daimler Truck" — pendência F9, decisão do orquestrador).

Semântica de estados (intocável, precedente F5/F7/F9):
- explicit_support: inexistente na prática para estágio DE;
- unclear: programa formal / evidência citada -> visa_friendly;
- candidate_must_have_authorization: negativa *** (valiosa);
- not_verified: nota honesta do que foi checado.

Fontes: todas verificadas HOJE (checked = 2026-10-04). Não curadas
(Levio, TYTAN, Exclusive Associates, AVISON, caronsale, cbs) ficam
documentadas no relatório da fase com a evidência medida.
"""
import json
from pathlib import Path

CI = Path(__file__).resolve().parent.parent / "company_intel" / "company_intelligence.json"
TODAY = "2026-10-04"


def _src(text: str, url: str, quality: str) -> dict:
    return {"text": text, "url": url, "quality": quality, "checked": TODAY}


# ---------------------------------------------------------------------------
# ONDA 2 — entries novas (long tail >=4 vagas, alvo real de estágio)
# ---------------------------------------------------------------------------

NEW_ENTRIES: list[dict] = [
    {
        "company": "ZEISS",
        "aliases": ["zeissgroup", "ZEISS", "Carl Zeiss AG", "Carl Zeiss GmbH"],
        "industry": "Óptica e optoeletrônica (tecnologia óptica)",
        "size": "~45.000 colaboradores (grupo global)",
        "hq": "Oberkochen, Baden-Württemberg, Alemanha",
        "international": "Grupo com presença em ~50 países; ZEISS SMT, ZEISS Medical, etc.",
        "business_areas": ["Semicondutores (EUV/SMC)", "Tecnologia médica", "Microscopia", "Ciência dos materiais"],
        "website": "https://www.zeiss.com",
        "careers_url": "https://www.zeiss.com/career/de/standorte/deutschland/berufseinstieg/studierende.html",
        "checked": TODAY,
        "sources": [
            _src("ZEISS Careers — Studierende (Praktikum/Werkstudierendentätigkeit na Alemanha)", "https://www.zeiss.com/career/de/standorte/deutschland/berufseinstieg/studierende.html", "primary"),
            _src("ZEISS Careers — Berufseinstieg Deutschland", "https://www.zeiss.com/career/de/standorte/deutschland/berufseinstieg.html", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de Praktikum e Werkstudierendentätigkeit (5–20h/semana) citado na página oficial de estudantes da Alemanha; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "ZEISS Studierende: \"Ein Praktikum bei ZEISS bietet Dir die einzigartige Chance, Dein theoretisches Wissen dem Praxischeck zu unterziehen... ZEISS bietet Dir nach Deinen individuellen Interessen und Fähigkeiten maßgeschneiderte Praktika in verschiedenen Bereichen.\" / \"Ein Werkstudium bei ZEISS... Arbeite zwischen 5 und 20 Stunden pro Woche an realen Projekten\"",
             "url": "https://www.zeiss.com/career/de/standorte/deutschland/berufseinstieg/studierende.html", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes (Praktikum/Werkstudierendentätigkeit) citado no portal oficial alemão; a página não declara sponsorship de visto — estado honesto unclear (programa citado)."},
        ]},
    },
    {
        "company": "ABB",
        "aliases": ["Abb", "careers.abb", "ABB AG", "ABB", "ABB Germany"],
        "industry": "Eletrificação e automação industrial",
        "size": "~110.000 colaboradores (grupo global)",
        "hq": "Zurique, Suíça (grupo); operações alemãs em Heidelberg, Mannheim, Ladenburg",
        "international": "Grupo suíço-sueco com operações em ~100 países",
        "business_areas": ["Eletrificação", "Automação de processos", "Robótica e motion", "Machine connectivity"],
        "website": "https://global.abb",
        "careers_url": "https://careers.abb/global/en/early-careers",
        "checked": TODAY,
        "sources": [
            _src("ABB Careers — Early careers (internships, thesis, summer jobs, working students)", "https://careers.abb/global/en/early-careers", "primary"),
            _src("ABB — Internships, apprenticeships & entry-level roles for students", "https://www.abb.com/global/en/company/stories/interns-young-professionals", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal global de internships/working students citado no portal oficial ('lasting from two months to two years, in over 100 countries'), com vagas working student ativas na Alemanha (Heidelberg/Mannheim); sem declaração pública sobre visto não-UE para o contexto DE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "ABB Early Careers: \"We offer scholarships, internships, apprenticeships and summer jobs, lasting from two months to two years, in over 100 countries.\" — vagas working student ativas em Heidelberg/Mannheim (ABB AG, alemanha) no Workday ABB.",
             "url": "https://careers.abb/global/en/early-careers", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de early careers citado no portal oficial, cobrindo a Alemanha (vagas ativas measured no Workday abb.wd3); sem declaração de sponsorship para DE — unclear (programa citado)."},
        ]},
    },
    {
        "company": "C&A",
        "aliases": ["C & A (Canda)", "C&A", "C&A Mode GmbH & Co. KG"],
        "industry": "Varejo de moda (fast fashion)",
        "size": "~41.000 colaboradores (grupo global)",
        "hq": "Düsseldorf/Vilvoorde (Bélgica); C&A Europe com HQ operacional em Düsseldorf",
        "international": "Presença histórica em ~20 países europeus; fundação belga/alemã",
        "business_areas": ["Fashion retail", "Sourcing e supply chain", "Digital/e-commerce", "Sustentabilidade"],
        "website": "https://www.c-and-a.com",
        "careers_url": "https://www.c-and-a.com/eu/en/corporate/company/careers",
        "checked": TODAY,
        "sources": [
            _src("C&A Jobs portal (jobs.canda.com — Working Student e Intern ativos em Düsseldorf)", "https://jobs.canda.com", "primary"),
            _src("C&A Corporate Careers", "https://www.c-and-a.com/eu/en/corporate/company/careers", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de carreiras (jobs.canda.com) com vagas ativas de Intern e Working Student em Düsseldorf; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "C&A jobs portal: \"Intern Consumer Insights (m/f/d) 1\" — Düsseldorf, DE, 40468 (26 Sept 2026) e \"Working Student (m/f/d) PMO Services and Systems — Düsseldorf\"; programa de estudantes ativo no portal oficial da C&A.",
             "url": "https://www.c-and-a.com/eu/en/corporate/company/careers/jobs/working-student-mfd-pmo-services-and-systems-65903-en-us", "quality": "primary", "checked": TODAY,
             "note": "Vagas ativas de Intern/Working Student no portal oficial (jobs.canda.com = C&A Careers); sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "John Deere",
        "aliases": ["John Deere", "Deere & Company", "John Deere GmbH & Co. KG"],
        "industry": "Máquinas agrícolas e construção (heavy equipment)",
        "size": "~83.000 colaboradores (grupo global)",
        "hq": "Moline, Illinois, EUA (grupo); fábrica e centro técnico alemão em Mannheim/Bruchsal/Walldorf",
        "international": "Operações em 160+ países",
        "business_areas": ["Tratores e colheitadeiras", "Precision agriculture", "Engenharia e manufatura (Mannheim)", "Finanças (John Deere Financial)"],
        "website": "https://www.deere.com",
        "careers_url": "https://www.deere.de/de-de/unser-unternehmen/karriere",
        "checked": TODAY,
        "sources": [
            _src("John Deere Deutschland — Karriere (Studentenpraktikum; contato HR Mannheim)", "https://www.deere.de/de-de/unser-unternehmen/karriere", "primary"),
            _src("John Deere jobs portal — Praktikum ativos em Mannheim/Bruchsal/Walldorf/Zweibrücken)", "https://jobs.deere.com", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de Studentenpraktikum citado no site alemão oficial (contato HR Mannheim), com vagas ativas de Praktikum em Mannheim/Bruchsal/Walldorf; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "John Deere Karriere (deere.de): \"Über das Studentenpraktikum — Zum Praktikum\" (seção dedicada ao programa de estágios para estudantes na fábrica de Mannheim).",
             "url": "https://www.deere.de/de-de/unser-unternehmen/karriere", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de Studentenpraktikum citado no site oficial alemão; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Marquardt Group",
        "aliases": ["Marquardt Group", "Marquardt GmbH", "Marquardt"],
        "industry": "Sistemas eletromecânicos (switches, HMI, sensores)",
        "size": "~10.000 colaboradores (grupo global)",
        "hq": "Rietheim-Weilheim, Baden-Württemberg, Alemanha",
        "international": "Fábricas na Alemanha, França, Tunísia, China, EUA, México",
        "business_areas": ["Sistemas de acionamento (drive systems)", "HMI e user interfaces", "Sensores e BMS (bateria)", "Eletromobilidade"],
        "website": "https://www.marquardt.com",
        "careers_url": "https://www.marquardt.com/de/karriere/studierende",
        "checked": TODAY,
        "sources": [
            _src("Marquardt — Studierende (Abschlussarbeit, Praktika & Werkstudentenjobs)", "https://www.marquardt.com/de/karriere/studierende", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de estudantes com programa formal citado (Praktikum, Abschlussarbeit, Werkstudierendentätigkeit) em Rietheim-Weilheim; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Marquardt Studierende: \"Ob Praktikum, Abschlussarbeit oder Werkstudierendentätigkeit – bei Marquardt sammelst du Praxiserfahrung für deinen Berufseinstieg.\" (78604 Rietheim-Weilheim)",
             "url": "https://www.marquardt.com/de/karriere/studierende", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes citado no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "ISAR Aerospace",
        "aliases": ["isaraerospace", "Isar Aerospace", "Isar Aerospace Technologies GmbH"],
        "industry": "Aeroespacial (launch vehicles, New Space)",
        "size": "~500+ colaboradores",
        "hq": "Ottobrunn/Munique, Baviera, Alemanha",
        "international": "Base de lançamento em Kiruna (Suécia); escritórios em Munique",
        "business_areas": ["Motores foguete (Aquila)", "Estruturas de veículo lançador", "Ground systems", "Aviónica"],
        "website": "https://www.isaraerospace.com",
        "careers_url": "https://www.isaraerospace.com/careers",
        "checked": TODAY,
        "sources": [
            _src("ISAR Aerospace job board (greenhouse — vagas Working Student ativas Ottobrunn/Parsdorf)", "https://job-boards.eu.greenhouse.io/isaraerospace", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de vagas com múltiplas posições ativas de Working Student e Internship (Ottobrunn/Parsdorf); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "ISAR Aerospace job board: \"Working Student Sales Operations (f/m/d) — Ottobrunn, Bavaria, Germany\" / \"Talent Acquisition - 6 months Internship (m/f/d)\" / \"Working Student Launch Operations (m/f/d)\" (vagas ativas no portal oficial greenhouse).",
             "url": "https://job-boards.eu.greenhouse.io/isaraerospace", "quality": "primary", "checked": TODAY,
             "note": "Programa de working students/interns com vagas ativas citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Provinzial Versicherung",
        "aliases": ["Provinzial Versicherung", "Provinzial Holding AG", "Provinzial"],
        "industry": "Seguros (grupo de seguros público)",
        "size": "~13.000 colaboradores (grupo Provinzial)",
        "hq": "Münster, Alemanha (grupo); Düsseldorf (Provinzial Rheinland)",
        "international": "Grupo segurador alemão (WestProvinzial + Rheinland), mercado nacional",
        "business_areas": ["Seguros P&C e vida", "HealthTech/digital", "Consultoria de vendas (agenturas)", "Asset management"],
        "website": "https://www.provinzial.de",
        "careers_url": "https://karriere.provinzial.com",
        "checked": TODAY,
        "sources": [
            _src("Provinzial — Studierende & Absolventen (programa formal Praktikum/Werkstudent/Referendariat)", "https://karriere-provinzial.de/einstieg/studierende-absolventen", "primary"),
            _src("Provinzial job portal (Praktikum/Werkstudent ativos Münster/Düsseldorf)", "https://karriere.provinzial.com/Provinzial/go/Stellenanzeigen-Provinzial/4887701", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de estudantes cita programa formal (\"Ob Pflichtpraktikum oder freiwillig – bei uns bist du in der Regel drei bis sechs Monate dabei\"), com vagas ativas de Praktikum/Werkstudent em Münster/Düsseldorf; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Provinzial Studierende & Absolventen: \"Im Praktikum lernst du verschiedene Bereiche kennen... Ob Pflichtpraktikum oder freiwillig – bei uns bist du in der Regel drei bis sechs Monate dabei.\" + vagas ativas \"Praktikum Finance Transformation (all genders) — Münster\".",
             "url": "https://karriere-provinzial.de/einstieg/studierende-absolventen", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estágios (Pflicht/freiwillig, 3–6 meses) citado no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Nordex Group",
        "aliases": ["Nordex Group Career Portal", "Nordex SE", "Nordex Group", "Nordex"],
        "industry": "Energia eólica (turbinas onshore)",
        "size": "~13.000 colaboradores (grupo global)",
        "hq": "Hamburg (gestão) / Rostock (entidade legal), Alemanha",
        "international": "Instalada em ~30 países; produção na Alemanha, Espanha, Brasil, EUA",
        "business_areas": ["Turbinas eólicas onshore", "Service e O&M", "Engenharia de blades", "Projeto e gestão de parques"],
        "website": "https://www.nordex-online.com",
        "careers_url": "https://jobs.nordex-online.com",
        "checked": TODAY,
        "sources": [
            _src("Nordex job portal (Working Student ativos Hamburg/Rostock; Global Sourcing, Diagnostics)", "https://jobs.nordex-online.com", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de vagas com posições ativas de Working Student em Hamburg/Rostock (IT Strategic Sourcing, Global Sourcing, Diagnostics, Commercial Project Management); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Nordex job portal: \"Working student (m/f/d) IT Strategic Sourcing — Hamburg\" / \"Werkstudent (m/w/d) Global Sourcing - Cabinet Systems (Hamburg / Rostock)\" (vagas ativas no portal oficial).",
             "url": "https://jobs.nordex-online.com", "quality": "primary", "checked": TODAY,
             "note": "Programa de working students com vagas ativas citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "BCG",
        "aliases": ["careers.bcg.com", "BCG", "Boston Consulting Group"],
        "industry": "Consultoria estratégica",
        "size": "~25.000 colaboradores (rede global)",
        "hq": "Boston, EUA (grupo); escritórios alemães em Munique, Berlim, Frankfurt, Hamburgo, Düsseldorf, Colônia, Stuttgart",
        "international": "Rede global de consultoria",
        "business_areas": ["Consultoria estratégica", "BCG X (digital/AI)", "BCG Platinion (IT)", "Business services"],
        "website": "https://www.bcg.com",
        "careers_url": "https://careers.bcg.com",
        "checked": TODAY,
        "sources": [
            _src("BCG Careers — Visiting Associate program (estágio 8–10 semanas para estudantes DE/AT)", "https://careers.bcg.com", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de estágio Visiting Associate citado no portal oficial (8–10 semanas, até 12 para Pflichtpraktikum, escritórios DE/AT); working students ativos em Munique; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "BCG Visiting Associate program (DE/AT): \"8 to 10 week internship for students (up to 12 weeks for mandatory internships, known in Germany as Pflichtpraktikum)... gives you full project responsibility from day one. Top performers receive return offers through the FAST FORWARD program.\"",
             "url": "https://careers.bcg.com/global/en/job/58930/Working-Student-Corporate-Finance-and-M-A", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estágio/working student na Alemanha citado no portal oficial (Visiting Associate, working student roles em München); sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "ebm-papst",
        "aliases": ["ebm-papst", "ebm-papst Mulfingen GmbH & Co. KG", "ebm-papst Group"],
        "industry": "Motores e ventilação (technology leadership)",
        "size": "~15.000 colaboradores (grupo global)",
        "hq": "Mulfingen, Baden-Württemberg, Alemanha",
        "international": "Presença em ~30 países; produção Alemanha, China, EUA, etc.",
        "business_areas": ["Motores EC e fans", "Ventilação industrial", "Automotive (bombas)", "Appliances"],
        "website": "https://www.ebmpapst.com",
        "careers_url": "https://career.ebmpapst.com/de/de/education-and-study.html",
        "checked": TODAY,
        "sources": [
            _src("ebm-papst — Ausbildung & Studium (Praktikum und Praxissemester)", "https://career.ebmpapst.com/de/de/education-and-study.html", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de estágios: \"Praktikum und Praxissemester. Ob Pflichtsemester oder freiwilliges Praktikum: Passend zu deinem Studiengang bieten wir bei ebm-papst dir die perfekte...\" — programa formal citado, vagas ativas em Mulfingen; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "ebm-papst Ausbildung & Studium: \"Praktikum und Praxissemester. Ob Pflichtsemester oder freiwilliges Praktikum: Passend zu deinem Studiengang bieten wir bei ebm-papst dir die perfekte [Ergänzung].\"",
             "url": "https://career.ebmpapst.com/de/de/education-and-study.html", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de Praktikum/Praxissemester citado no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "FIR e.V. an der RWTH Aachen",
        "aliases": ["FIREVAnDerRWTHAachen", "FIR e.V. an der RWTH Aachen", "FIR e. V. an der RWTH Aachen", "FIR an der RWTH Aachen"],
        "industry": "Pesquisa aplicada (instituto anexado à RWTH Aachen) — organização de pesquisa",
        "size": "Instituto de pesquisa aplicada (campus RWTH Aachen); ~100 colaboradores",
        "hq": "Aachen, NRW, Alemanha",
        "international": "Instituto afiliado à RWTH Aachen University; cooperações internacionais (research networks)",
        "business_areas": ["Produktionsmanagement", "Business transformation", "Informationsmanagement", "Servicemangement"],
        "website": "https://www.fir.rwth-aachen.de",
        "careers_url": "https://careers.smartrecruiters.com/FIREVAnDerRWTHAachen",
        "checked": TODAY,
        "sources": [
            _src("FIR e.V. — Careers (smartrecruiters: Bachelor-/Masterarbeiten, studentische Hilfskräfte)", "https://careers.smartrecruiters.com/FIREVAnDerRWTHAachen", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Instituto de pesquisa anexado à RWTH Aachen com portal de vagas ativo (Bachelor-/Masterarbeiten, studentische Hilfskräfte 7–19h/semana) — precedente Fraunhofer F9: pathway institucional documentado para estudantes; sem declaração específica sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "FIR e.V. careers portal: \"Bachelor- oder Masterarbeit: Digitale Technologien in der wertsteigernden Kreislaufwirtschaft\" / \"Studentische Hilfskraft: Nachhaltige, zukunftsfähige Produktion - 7-19 Std./Woche\" (vagas ativas para estudantes no instituto anexado à RWTH Aachen).",
             "url": "https://careers.smartrecruiters.com/FIREVAnDerRWTHAachen", "quality": "primary", "checked": TODAY,
             "note": "Instituto de pesquisa universitário (RWTH Aachen) com vagas ativas citadas para estudantes no portal oficial — mesma lógica do precedente Fraunhofer F9 (pathway institucional); sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Vitesco Technologies GmbH",
        "aliases": ["Vitesco Technologies GmbH", "Vitesco Technologies", "Vitesco"],
        "industry": "Eletrônica automotiva (powertrain electrification)",
        "size": "~35.000 colaboradores (grupo, até a integração Schaeffler)",
        "hq": "Regensburg, Baviera, Alemanha",
        "international": "Grupo com operações globais (China, EUA, Europa); desde out/2024 parte do grupo Schaeffler (integração de marcas em andamento)",
        "business_areas": ["Eletrônica de potência (inversores)", "Sensores e atuação", "Battery management", "Soluções de e-mobility"],
        "website": "https://www.vitesco-technologies.com",
        "careers_url": "https://jobs.vitesco-technologies.com",
        "checked": TODAY,
        "sources": [
            _src("Vitesco job portal (Internship e Abschlussarbeit ativos em Regensburg)", "https://jobs.vitesco-technologies.com", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial com vagas ativas de Internship (6 meses) e Abschlussarbeit em Regensburg; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04. Nota de identidade: desde 2024 a Vitesco pertence ao grupo Schaeffler — entry própria porque o match é pela string do dataset e a integração de marcas está em andamento (perfis de carreira ainda publicados sob identidade Vitesco).",
        "sources_for": {"visa_policy": [
            {"text": "Vitesco job portal: \"Internship - Global Category Passives (d/f/m) — Regensburg BT, Deutschland. This position is available from March 1, 2027 for a duration of 6 months.\" / \"Internship - Risk Management Purchasing E-Mobility (d/f/m)\" (vagas ativas de estágio no portal oficial).",
             "url": "https://jobs.vitesco-technologies.com", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de internships com vagas ativas (6 meses) citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "B. Braun SE",
        "aliases": ["B. Braun Melsungen AG", "B. Braun SE", "B. Braun", "B.Braun"],
        "industry": "Tecnologia médica e farmacêutica (healthcare)",
        "size": "~65.000 colaboradores (grupo global)",
        "hq": "Melsungen, Hessen, Alemanha",
        "international": "Grupo familiar com 64 filiais em 64 países",
        "business_areas": ["Hospital care (infusão, cirurgia)", "Aesculap (implantes)", "B. Braun Avitum", "Pharma (fabricação própria)"],
        "website": "https://www.bbraun.com",
        "careers_url": "https://jobs.bbraun.com",
        "checked": TODAY,
        "sources": [
            _src("B. Braun job portal (Hochschulpraktikum ativos em Melsungen)", "https://jobs.bbraun.com", "primary"),
            _src("B. Braun — Karriere Studierende", "https://www.bbraun.com/de/de/karriere/studierende.html", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial com vagas ativas de Hochschulpraktikum (w/m/d) em Melsungen (Controlling, Sustainability Reporting, Prozessoptimierung); programa formal para estudantes citado; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "B. Braun job portal: \"Hochschulpraktikum (w/m/d) im Bereich Controlling — Melsungen\" / \"Hochschulpraktikum (w/m/d) Sustainability Reporting & Controlling\" (vagas ativas de estágio universitário no portal oficial).",
             "url": "https://jobs.bbraun.com", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de Hochschulpraktikum com vagas ativas citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Voith Group",
        "aliases": ["Voith GmbH", "Voith GmbH & Co. KGaA", "Voith SE & Co. KG", "Voith", "Voith Group"],
        "industry": "Tecnologia industrial (máquinas, papel, hidroenergia)",
        "size": "~21.000 colaboradores (grupo global)",
        "hq": "Heidenheim an der Brenz, Baden-Württemberg, Alemanha",
        "international": "Grupo familiar com operações em ~60 países",
        "business_areas": ["Voith Paper", "Voith Hydro", "Voith Turbo (drive systems)", "Voith Digital Solutions"],
        "website": "https://www.voith.com",
        "careers_url": "https://www.voith.com/corp-de/karriere/einstieg/studierende.html",
        "checked": TODAY,
        "sources": [
            _src("Voith — Jobs für Studierende (Praktikum, duales Studium, Abschlussarbeit, Werkstudierendentätigkeit)", "https://www.voith.com/corp-de/karriere/einstieg/studierende.html", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de estudantes com programa formal (Praktikum, Abschlussarbeiten, Werkstudierende, duales Studium) e vagas ativas em Heidenheim/Crailsheim; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Voith Karriere Studierende: \"Bei Voith kannst Du etwas bewegen, auch als Student oder Studentin. Ob im Praktikum, dualen Studium, während der Abschlussarbeit oder Deiner Werkstudierendentätigkeit: Bei uns übernimmst Du Verantwortung...\" — seções Praktikum für Studierende / Werkstudierende / Abschlussarbeiten / Talent-Programme.",
             "url": "https://www.voith.com/corp-de/karriere/einstieg/studierende.html", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes com múltiplas modalidades citado no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "RWE AG",
        "aliases": ["RWE", "RWE AG", "RWE Group"],
        "industry": "Energia (utilities; renováveis e trading)",
        "size": "~20.000 colaboradores (grupo global)",
        "hq": "Essen, NRW, Alemanha",
        "international": "Grupo com operações renováveis na Europa, Américas e Ásia-Pacífico",
        "business_areas": ["Offshore/Onshore wind", "Solar e baterias", "Trading (RWE Supply & Trading)", "Generation nuclear/carvão (encerramento planejado)"],
        "website": "https://www.rwe.com",
        "careers_url": "https://www.rwe.com/karriere-bei-rwe/berufseinsteiger/werkstudierendenjobs-und-praktika",
        "checked": TODAY,
        "sources": [
            _src("RWE — Werkstudierendenjobs & Praktika (programa formal; Praktikum 3–6 meses)", "https://www.rwe.com/karriere-bei-rwe/berufseinsteiger/werkstudierendenjobs-und-praktika", "primary"),
            _src("RWE Careers — Undergraduate & student opportunities", "https://www.rwe.com/en/rwe-careers-portal/early-careers/undergraduate-and-student-opportunities", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial dedicada a Werkstudierendenjobs & Praktika: \"Ein Praktikum bei RWE ist der perfekte Start in deine berufliche Karriere... Ein Praktikum bei RWE dauert in der Regel 3-6 Monate\"; vagas ativas em Essen/Hamburg; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "RWE Karriere: \"Ein Praktikum bei RWE dauert in der Regel 3-6 Monate. Längere Praktika sind möglich, z.B. während eines Gap Years.\" / \"Mit einem Praktikum oder einer Werkstudierendentätigkeit bei RWE bieten sich dir vielfältige Möglichkeiten.\"",
             "url": "https://www.rwe.com/karriere-bei-rwe/berufseinsteiger/werkstudierendenjobs-und-praktika", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de Praktikum/Werkstudent com duração citada no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "EY (Germany)",
        "aliases": ["EY Global Services", "EY GmbH & Co. KG WPG", "EY Deutschland", "Ernst & Young"],
        "industry": "Consultoria, auditoria e serviços financeiros (Big Four)",
        "size": "~400.000 colaboradores (rede global); ~12.000 na Alemanha",
        "hq": "Eschborn/Frankfurt am Main (sede alemã); rede global EY",
        "international": "Membro da rede global EY",
        "business_areas": ["Assurance (auditoria)", "Consulting", "Tax & Law", "Strategy and Transactions (EY-Parthenon)", "Global Services (centros compartilhados)"],
        "website": "https://www.ey.com/de_de",
        "careers_url": "https://jobsgermany.ey.com/studentin",
        "checked": TODAY,
        "sources": [
            _src("EY Deutschland — Jobs für Student:innen (Praktikum, Werkstudierendentätigkeit)", "https://jobsgermany.ey.com/studentin", "primary"),
            _src("EY — Dein Einstieg während des Studiums (student entry-level programs)", "https://www.ey.com/de_de/careers/student-entry-level-programs", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal alemão oficial com seção dedicada a Student:innen (\"Ob im Praktikum oder als Werkstudierende:r in der Wirtschaftsprüfung, Steuerberatung, Strategie- und Transaktionsberatung oder Unternehmensberatung – bei EY bist du mittendrin statt nur dabei.\"); vagas ativas de Praktikant Data Science em Eschborn/Hamburg; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "EY Deutschland Karriere: \"Dein Einstieg während des Studiums — Du willst während des Studiums Praxisluft schnuppern? Ob im Praktikum oder als Werkstudierende:r in der Wirtschaftsprüfung, Steuerberatung, Strategie- und Transaktionsberatung oder Unternehmensberatung – bei EY bist du mittendrin statt nur dabei.\"",
             "url": "https://www.ey.com/de_de/careers/student-entry-level-programs", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de Praktikum/Werkstudent citado no portal oficial alemão; sem declaração de sponsorship no contexto DE — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Celonis SE",
        "aliases": ["celonis", "Celonis", "Celonis SE"],
        "industry": "Software (process mining e process intelligence)",
        "size": "~5.000 colaboradores (grupo global)",
        "hq": "Munique, Baviera, Alemanha (HQ global)",
        "international": "Unicórnio alemão; escritórios em Munique, Madri, Nova York, Londres, Tóquio, etc.",
        "business_areas": ["Process mining (Execution Management)", "Process intelligence (AI)", "Orbit Program (graduate entry)", "Data & AI solutions"],
        "website": "https://www.celonis.com",
        "careers_url": "https://careers.celonis.com/early-careers",
        "checked": TODAY,
        "sources": [
            _src("Celonis — Early careers (Internships and working students; FAQ sobre elegibilidade)", "https://careers.celonis.com/early-careers", "primary"),
        ],
        "visa_policy": "candidate_must_have_authorization",
        "visa_policy_note": "FAQ oficial do programa de early careers declara explicitamente: \"Unfortunately, we do not offer Visa sponsorship for interns and working students. In order to be eligible... you need a valid work permit for the location of the job posting.\" — negativa honesta (não patrocina visto para estágio/working student); checado 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Celonis Early Careers FAQ: \"Does Celonis provide Visa sponsorship to interns and working students? — Unfortunately, we do not offer Visa sponsorship for interns and working students. In order to be eligible for an internship or working student position at Celonis, you need a valid work permit for the location of the job posting.\"",
             "url": "https://careers.celonis.com/early-careers", "quality": "primary", "checked": TODAY,
             "note": "Negativa declarada no FAQ oficial do programa: não patrocina visto para interns/working students — o candidato precisa TER work permit válida para o local. Estado candidate_must_have_authorization (precedentes Lufthansa/Simon-Kucher F9)."},
        ]},
    },
    {
        "company": "MediaMarktSaturn Retail Group",
        "aliases": ["MediaMarktSaturn Retail Group", "Media-Saturn Deutschland GmbH", "MediaMarktSaturn", "MediaMarkt"],
        "industry": "Varejo de eletrônicos (consumer electronics retail)",
        "size": "~60.000+ colaboradores (grupo; maior rede de eletrônicos da Europa)",
        "hq": "Ingolstadt, Baviera, Alemanha",
        "international": "Presença em ~13 países europeus; marcas MediaMarkt e Saturn",
        "business_areas": ["Retail (lojas MediaMarkt/Saturn)", "E-commerce e marketplace", "MediaMarkt Business (B2B)", "Serviços e repair"],
        "website": "https://careers.mediamarktsaturn.com",
        "careers_url": "https://careers.mediamarktsaturn.com",
        "checked": TODAY,
        "sources": [
            _src("MediaMarktSaturn careers portal (Werkstudent ativos Hanau/Ingolstadt)", "https://careers.mediamarktsaturn.com", "primary"),
            _src("MediaMarkt — Jobs & Karriere (Praktikum, duales Studium)", "https://www.mediamarkt.de/de/about-us/jobs-karriere", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de carreiras com vagas ativas de Werkstudent (Hanau, Ingolstadt, München) e seção Praktikum no site público; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "MediaMarkt Jobs & Karriere: \"Praktikum — Profis über die Schulter schauen – ein Praktikum bei MediaMarkt bietet einen Blick hinter die Kulissen.\" + portal oficial com \"Werkstudent Logistik (m/w/d) — Hanau\" / \"Working student Master Data & SEO (m/f/d) — Ingolstadt\".",
             "url": "https://www.mediamarkt.de/de/about-us/jobs-karriere", "quality": "primary", "checked": TODAY,
             "note": "Programa formal (Praktikum/duales Studium) citado no site oficial + vagas Werkstudent ativas no portal do grupo; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Philips Germany",
        "aliases": ["www.careers.philips.com", "Philips Electronics Germany", "Philips Deutschland"],
        "industry": "Tecnologia de saúde (health technology)",
        "size": "Grupo global ~70.000 colaboradores; Philips Germany com sites em Hamburgo, Böblingen",
        "hq": "Best, Países Baixos (grupo); Philips Germany em Hamburgo",
        "international": "Grupo holandês líder em health technology",
        "business_areas": ["Diagnostic imaging", "Patient monitoring", "Personal health", "Image-guided therapy"],
        "website": "https://www.philips.de",
        "careers_url": "https://www.careers.philips.com/student/emea/en/search-results",
        "checked": TODAY,
        "sources": [
            _src("Philips Student Careers EMEA (vagas Working Student/Praktikum na Alemanha)", "https://www.careers.philips.com/student/emea/en/search-results", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de student careers EMEA com vagas ativas de Werkstudent/Praktikum em Hamburgo (Philips Electronics Germany); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04. Nota de identidade: entry SEPARADA da Koninklijke Philips N.V. (NL) porque o match é pela string exata do dataset e a entry NL carrega o registro IND luxemburguês/da Holanda — política de país específico não se estende a vagas DE.",
        "sources_for": {"visa_policy": [
            {"text": "Philips Student Careers EMEA: \"Werkstudent/ Praktikum AI Innovation Marketing (all genders) — Philips in Hamburg, Hamburg, Germany. Mandatory internship: The salary ranges from €900 (Bachelor's degree) - €1,000 (Master's)\" (vagas ativas na Alemanha no portal oficial).",
             "url": "https://www.careers.philips.com/global/en/job/591252/Werkstudent-Praktikum%C2%A0AI-Innovation-Marketing%C2%A0-all%C2%A0genders-%C2%A0", "quality": "primary", "checked": TODAY,
             "note": "Vagas ativas de Werkstudent/Praktikum na Alemanha (Hamburgo) citadas no portal oficial com remuneração de Pflichtpraktikum; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Ferrero Germany",
        "aliases": ["Ferrero International S.A", "Ferrero", "Ferrero Deutschland GmbH"],
        "industry": "Alimentos (chocolate e confeitaria)",
        "size": "~47.000 colaboradores (grupo global)",
        "hq": "Alba, Itália (grupo); Ferrero Deutschland em Frankfurt am Main (Stadtrand)",
        "international": "Grupo italiano com operações em 55+ países",
        "business_areas": ["Chocolates (Nutella, Kinder, Ferrero Rocher)", "Sourcing e supply chain", "Marketing e consumer insights", "Produção (Schwarz Produktion é outra área do grupo)"],
        "website": "https://www.ferrero.com",
        "careers_url": "https://www.ferrerocareers.com/int/en/early-careers",
        "checked": TODAY,
        "sources": [
            _src("Ferrero Careers — Early Careers (Praktikant/Werkstudent ativos Frankfurt)", "https://www.ferrerocareers.com/int/en/early-careers", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de early careers com vagas ativas de Praktikant Marktforschung e Werkstudent em Frankfurt am Main (3–6 meses de estágio); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Ferrero Early Careers: \"Praktikant Marktforschung - Brand & Social Media Monitoring (m/w/d) — Frankfurt am Main, HE, DE\" / \"Werkstudent (w/m/d) Einkauf - Procurement Service Center — Frankfurt\" / \"our 3 to 6-month internships are designed to let you explore Ferrero\".",
             "url": "https://www.ferrerocareers.com/int/en/early-careers", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de internships (3–6 meses) com vagas ativas em Frankfurt citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "ADAC e.V.",
        "aliases": ["ADAC SE", "ADAC Autovermietung GmbH", "ADAC Medien und Reise GmbH", "ADAC Versicherung AG", "ADAC"],
        "industry": "Clube automobilístico e serviços (automotive services)",
        "size": "~22 milhões de membros; ~5.000+ colaboradores centrais",
        "hq": "Munique, Baviera, Alemanha (ADAC Zentrale)",
        "international": "Clube alemão com cooperações internacionais (ARC Europe)",
        "business_areas": ["Pannenhilfe (socorro)", "ADAC Versicherung", "ADAC Luftrettung", "Medien e viagens"],
        "website": "https://www.adac.de",
        "careers_url": "https://karriere.adac.de/praktikum-studentenjob-werkstudent.html",
        "checked": TODAY,
        "sources": [
            _src("ADAC Karriere — Praktika & Werkstudententätigkeit (programa formal; Pflichtpraktikum até 3 meses)", "https://karriere.adac.de/praktikum-studentenjob-werkstudent.html", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de carreira estudantil: \"Immatrikulierte Studierende können bei uns ihr Pflichtpraktikum von bis zu drei Monaten absolvieren\" + programa de Werkstudent descrito; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "ADAC Karriere: \"Wenn du für dein Studium einen spannenden und vielfältigen Praxispartner suchst, bist du beim ADAC genau richtig. Immatrikulierte Studierende können bei uns ihr Pflichtpraktikum von bis zu drei Monaten absolvieren.\"",
             "url": "https://karriere.adac.de/praktikum-studentenjob-werkstudent.html", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de Pflichtpraktikum (até 3 meses) + Werkstudent citado no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "BAUHAUS AG",
        "aliases": ["Bauhaus AG", "bahagag", "BAUHAUS"],
        "industry": "Varejo de materiais de construção e jardinagem (DIY)",
        "size": "~300 Fachcentren na Alemanha; grupo com 160+ lojas",
        "hq": "Mannheim (SCDE/service center) / Wuppertal (grupo BAUHAUS)",
        "international": "Grupo com lojas em 18+ países europeus",
        "business_areas": ["Retail DIY (Fachcentren)", "Service Center Deutschland (SCDE Mannheim)", "Digital commerce", "Logística de loja"],
        "website": "https://www.bauhaus.info",
        "careers_url": "https://jobs.bauhaus.info/studierende-absolventen",
        "checked": TODAY,
        "sources": [
            _src("BAUHAUS — Für Studierende & Absolventen (Studienpraktikum, Werkstudentenjob, Trainee)", "https://jobs.bauhaus.info/studierende-absolventen", "primary"),
            _src("BAUHAUS — Studienpraktikum (programa formal no SCDE Mannheim)", "https://jobs.bauhaus.info/studierende-absolventen/studienpraktikum", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Página oficial de estudantes com programa formal (Studienpraktikum no Service Center Deutschland em Mannheim; Werkstudentenjob; Traineeprogramme): \"Studienpraktika sind eine gute Möglichkeit... Die meisten Praktika finden im BAUHAUS Service Center Deutschland (SCDE) in Mannheim statt\"; a F9 não curou por busca fraca (pendência resolvida com evidência); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "BAUHAUS Studienpraktikum: \"Studienpraktika sind eine gute Möglichkeit, um schon frühzeitig einen ersten Einblick in Ihren potenziellen Traumjob zu erhalten. Die meisten Praktika finden im BAUHAUS Service Center Deutschland (SCDE) in Mannheim statt, wobei BAUHAUS derzeit auch das Praktikumsangebot in den Fachcentren weiter ausbaut.\"",
             "url": "https://jobs.bauhaus.info/studierende-absolventen/studienpraktikum", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de Studienpraktikum citado no portal oficial (re-pesquisa F10 achou a página que a F9 não encontrou); sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
]

# ---------------------------------------------------------------------------
# ENTRIES EXISTENTES — merges de alias, upgrade TE e pendência Everllence
# ---------------------------------------------------------------------------

EXISTING_UPDATES = {
    # PENDÊNCIA F9 (decisão inegociável do orquestrador): Everllence é a
    # ex-MAN Energy Solutions (grupo VW, HQ Augsburg). A spec da F9 dizia
    # "ex-Daimler Truck" por erro; os aliases "Daimler Truck AG"/
    # "Daimler Truck" são factualmente ERRADOS e inertes hoje (0 strings
    # no dataset medido), mas um job futuro da Daimler Truck herdaria o
    # estado unclear ERRADO. MANTÉM "MAN Energy Solutions SE" e
    # "MAN Energy Solutions" (corretos).
    "everllence se": {
        "remove_aliases": ["Daimler Truck AG", "Daimler Truck"],
    },
    # TE Connectivity: única entry F9 not_verified com busca fraca (a F9
    # só documentara o programa US). Re-busca F10 (Tarefa 2.3) com termos
    # alemães achou working student ATIVO na Alemanha no portal oficial
    # (site de Adelberg, BW) -> upgrade not_verified -> unclear com citação.
    "te connectivity": {
        "visa_policy": "unclear",
        "visa_policy_note": "Upgrade F10 (2026-10-04): re-busca com termos alemães achou vaga ativa de working student na Alemanha no portal oficial (Adelberg, BW — site de manufatura TE; 'The intern will work closely with Plant Finance, Operations, Supply Chain...'), com páginas Students/Universitätsprogramme no portal DE; sem declaração de sponsorship de visto — unclear (programa citado).",
        "sources_for": {"visa_policy": [
            {"text": "TE Connectivity careers (portal oficial): \"Working Student in Operations Finance (m/w/d) — Job Locations: Ziegelhau 25, Adelberg, Baden-Württemberg 73099 Germany. This internship offers direct exposure to real-world plant finance activities at the Adelberg manufacturing site, with structured support, mentoring and meaningful analytical work.\" + menu do portal DE com seções \"Universitätsprogramme\" e \"Studenten\".",
             "url": "https://careers.te.com/job/Working-Student-in-Operations-Finance-%28mwd%29/148426-en_US", "quality": "primary", "checked": TODAY,
             "note": "Working student/estágio ATIVO na Alemanha (site de manufatura de Adelberg, BW) citado no portal oficial careers.te.com em locale DE — o programa alemão existe publicamente (a F9 só havia achado o programa US); sem declaração de sponsorship — upgrade para unclear (programa citado)."},
        ]},
    },
    # Alias merges: strings irmãs EXATAS medidas no dataset (mesma empresa).
    # Estados preservados (sem re-decisão de visa_policy nestas entries).
    "knorr-bremse": {
        "extra_aliases": ["Knorr-Bremse Systeme für Schienenfahrzeuge GmbH"],
    },
    "liebherr-international s.a.": {
        "extra_aliases": [
            "Liebherr-Werk Ehingen GmbH",
            "Liebherr-Mischtechnik GmbH",
            "Liebherr-Logistics GmbH",
            "Liebherr Electronics and Drives GmbH",
        ],
    },
    "schaeffler technologies ag & co. kg": {
        "extra_aliases": ["Schaeffler Vehicle Lifetime Solutions Germany GmbH & Co. KG"],
    },
    "bayer": {
        "extra_aliases": ["Bayer AG Pharmaceuticals"],
    },
    "volkswagen ag": {
        "extra_aliases": ["VOLKSWAGEN GROUP Original Teil e Logistik, Vertrieb & Service s GmbH"],
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
    removed: list[tuple[str, str]] = []
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
        for alias in upd.get("remove_aliases", []):
            before = len(aliases)
            entry["aliases"] = [a for a in aliases if a.casefold() != alias.casefold()]
            if len(entry["aliases"]) < before:
                aliases = entry["aliases"]
                known = {a.casefold() for a in aliases}
                removed.append((key, alias))
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
    print(f"aliases REMOVIDOS (pendência F9): {len(removed)}")
    for k, a in removed:
        print(f"  - {a} de {k}")
    print(f"visa_policy upgrades: {len(upgraded)}")
    for c in upgraded:
        print(f"  ~ {c}")
    print(f"total entries: {len(companies)}")


if __name__ == "__main__":
    main()
