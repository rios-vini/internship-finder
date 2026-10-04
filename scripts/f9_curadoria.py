#!/usr/bin/env python3
"""F9 curadoria onda 1: top empresas por volume de elegíveis (Grupos A + B).

Idempotente no padrão do f7_curadoria.py:
- entries NOVAS (casefold do nome canônico ainda ausente) entram com
  ``country`` = "de";
- entries EXISTENTES podem ganhar aliases extras (strings EXATAS do
  dataset) e upgrade de visa_policy (Fraunhofer not_verified -> unclear).

Semântica de estados (intocável, precedente F5/F7):
- explicit_support: inexistente na prática para estágio DE;
- unclear: programa formal / evidência citada -> visa_friendly;
- candidate_must_have_authorization: negativa honesta (valiosa);
- not_verified: nota honesta do que foi checado.

Fontes: todas verificadas HOJE (checked = 2026-10-04). Grupo C (não curado)
fica documentado no relatório da fase — script só escreve A + B + updates.
"""
import json
from pathlib import Path

CI = Path(__file__).resolve().parent.parent / "company_intel" / "company_intelligence.json"
TODAY = "2026-10-04"


def _src(text: str, url: str, quality: str) -> dict:
    return {"text": text, "url": url, "quality": quality, "checked": TODAY}


# ---------------------------------------------------------------------------
# GRUPO A — aliases quebrados (quick win): entries novas completas
# ---------------------------------------------------------------------------

GRUPO_A = [
    {
        "company": "Lidl",
        "aliases": [
            "Lidl Dienstleistung GmbH & Co. KG",
            "lidlstiftup2",
            "Lidl Stiftung & Co. KG",
            "Lidl Deutschland",
        ],
        "industry": "Varejo de alimentos (discounter; grupo Schwarz)",
        "size": "Mais de 3.250 lojas na Alemanha (site oficial de carreiras)",
        "hq": "Neckarsulm, Alemanha",
        "international": "Presente em ~30 países europeus; parte do grupo Schwarz (com Kaufland)",
        "business_areas": ["Operações de loja e logística", "Compras e gestão de categorias", "TI e analytics", "Financeiro e controlling"],
        "website": "https://www.lidl.de",
        "careers_url": "https://jobs.lidl.de/studenten",
        "checked": TODAY,
        "sources": [
            _src("Lidl Jobs — portal Studenten (Studentenjob, Praktikum, Trainee)", "https://jobs.lidl.de/studenten", "primary"),
            _src("International Careers with Lidl (programas internacionais do grupo)", "https://careers.lidl", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de estudantes com programa formal (Studentenjob/Praktikum/Trainee); sem declaração pública específica sobre visto/autorização para não-UE nas páginas checadas em 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Lidl Jobs — Studenten: \"Ob Studentenjob, Praktikum oder Einstieg nach dem Studium: Bei uns stehen dir vielfältige Jobmöglichkeiten offen.\"",
             "url": "https://jobs.lidl.de/studenten", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes no portal oficial alemão (Praktikum/Trainee/Studentenjob); a página não declara patrocínio de visto — estado honesto unclear (programa citado), não explicit_support."},
        ]},
    },
    {
        "company": "DHL Group",
        "aliases": [
            "careers.dhl.com",
            "DHL",
            "Deutsche Post DHL Group",
            "DHL Group",
        ],
        "industry": "Logística e correio",
        "size": "Um dos maiores grupos de logística do mundo",
        "hq": "Bonn, Alemanha",
        "international": "Rede global de logística e correio",
        "business_areas": ["Express", "Global Forwarding", "Post & Parcel Germany", "Supply Chain"],
        "website": "https://group.dhl.com",
        "careers_url": "https://careers.dhl.com/global/en/students-graduates",
        "checked": TODAY,
        "sources": [
            _src("DHL Group Careers — Students & graduates (internships locais + AIESEC Upgrade Program internacional)", "https://careers.dhl.com/global/en/students-graduates", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de estudantes com internships locais e programa internacional (AIESEC Upgrade); sem declaração específica sobre visto/autorização nas páginas checadas em 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "DHL Group Careers — Students & graduates: \"We offer a wide range of locally-run internship opportunities across our sites worldwide.\" / AIESEC Upgrade Program: \"It's the only international internship program of DHL\"",
             "url": "https://careers.dhl.com/global/en/students-graduates", "quality": "primary", "checked": TODAY,
             "note": "Programas formais de estágio (locais em cada país + internacional via AIESEC) citados no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
]

# ---------------------------------------------------------------------------
# GRUPO B — curadoria completa por volume de elegíveis (pesquisa 2026-10-04)
# ---------------------------------------------------------------------------

GRUPO_B: list[dict] = [
    {
        "company": "REWE Group",
        "aliases": ["REWE Group", "REWE Markt GmbH", "REWE", "REWE-Beteiligungs-Holding International GmbH", "REWE digital GmbH"],
        "industry": "Varejo e supermercados (cooperativa de comércio)",
        "size": "~345.000 colaboradores (grupo, citado no portal de vagas)",
        "hq": "Colônia (Köln), Alemanha",
        "international": "Operações principalmente na Europa; marcas REWE, PENNY, toom",
        "business_areas": ["Varejo alimentar (REWE, PENNY)", "Logística e supply chain", "E-commerce e digital", "Turismo (DER, jatrola)"],
        "website": "https://www.rewe-group.com",
        "careers_url": "https://jobs.rewe-group.com",
        "checked": TODAY,
        "sources": [
            _src("REWE Group Karriere — Praktikum & Werkstudierenden-Jobs (programa formal)", "https://jobs.rewe-group.com/praktikum-werkstudium", "primary"),
            _src("REWE Group Karriere — FAQs (Praktika, Initiativbewerbung, Werksstudierende)", "https://jobs.rewe-group.com/faq", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de estágios/Werkstudent citado no portal oficial; sem declaração pública sobre visto/autorização para não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "REWE Group Karriere: \"Sowohl ein Praktikum als auch eine Werkstudierendenstelle kann den Grundstein für deine Karriere bei der REWE Group legen.\" — página oficial de Praktikum & Werkstudium (praticas 3–6 meses, remuneradas).",
             "url": "https://jobs.rewe-group.com/praktikum-werkstudium", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes no portal oficial; a página não declara sponsorship de visto — estado honesto unclear (programa citado)."},
        ]},
    },
    {
        "company": "Deloitte (Germany)",
        "aliases": ["Deloitte GmbH Wirtschaftsprüfungsgesellschaft", "Deloitte GmbH", "Deloitte Deutschland"],
        "industry": "Consultoria, auditoria e serviços financeiros (Big Four)",
        "size": "Maior firma de serviços profissionais da Alemanha (rede Deloitte global)",
        "hq": "Frankfurt am Main, Alemanha (sede alemã)",
        "international": "Membro da rede global Deloitte",
        "business_areas": ["Audit & Assurance", "Consulting", "Tax & Legal", "Financial Advisory", "SAP Consulting"],
        "website": "https://www2.deloitte.com/de",
        "careers_url": "https://job.deloitte.com",
        "checked": TODAY,
        "sources": [
            _src("Deloitte Deutschland Karriere — Praktikum & Werkstudententätigkeit (programa formal)", "https://job.deloitte.com/praktikum-werkstudententaetigkeit-_jtc4", "primary"),
            _src("Deloitte Karriere — FAQ Bewerbung (regras p/ Praktikant:innen/Werkstudierende)", "https://job.deloitte.com/bewerbung/faq", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de Praktikum/Werkstudent no portal oficial alemão; FAQ checado 2026-10-04 sem declaração pública sobre visto para não-UE nos estágios alemães.",
        "sources_for": {"visa_policy": [
            {"text": "Deloitte Karriere: \"Werde Werkstudent:in bei Deloitte! ... Werkstudium: starte im Anschluss als Werkstudent:in\" — página oficial de Praktikum & Werkstudententätigkeit com vagas ativas (ex. SAP Consulting Praktikant/Werkstudent).",
             "url": "https://job.deloitte.com/praktikant-werkstudent-sap-consulting-_ljp11", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes com vagas ativas citadas no portal alemão; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Airbus",
        "aliases": ["Airbus Defence and Space GmbH", "Airbus Operations GmbH Werk Bremen", "Airbus Operations GmbH", "Airbus Logistik GmbH"],
        "industry": "Aeroespacial e defesa",
        "size": "Mais de 150.000 colaboradores (grupo global)",
        "hq": "Leiden (sede legal); operações principais em Toulouse, Hamburg, Munique (grupo); entidade alemã em Munique",
        "international": "Sites na Europa (DE/FR/ES/UK), EUA e mundial",
        "business_areas": ["Commercial Aircraft", "Defence and Space", "Helicopters", "Funções corporativas"],
        "website": "https://www.airbus.com",
        "careers_url": "https://www.airbus.com/en/careers",
        "checked": TODAY,
        "sources": [
            _src("Airbus Careers — FAQ oficial (students, internships, visa)", "https://www.airbus.com/en/careers/faqs", "primary"),
            _src("Airbus Careers — Interns (\"Internships and/or working student positions in Germany\")", "https://www.airbus.com/en/careers/students-and-graduates/interns", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "FAQ oficial: suporte a visto/relocation depende do papel e país — condicional; programa formal de interns/working students na Alemanha citado. Checado 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Airbus Careers FAQ: \"Visa and relocation support depend on the role, country and applicable legislation. This may be discussed during the recruitment process where relevant.\"",
             "url": "https://www.airbus.com/en/careers/faqs", "quality": "primary", "checked": TODAY,
             "note": "Declaração CONDICIONAL oficial (depende do papel/país) — regra da curadoria: condicional => unclear, nunca explicit_support. Programa formal de interns na Alemanha citado na página Interns."},
        ]},
    },
    {
        "company": "Vodafone",
        "aliases": ["Vodafone Procurement Company S.a.r.l.", "Vodafone GmbH", "Vodafone Germany"],
        "industry": "Telecomunicações",
        "size": "~80.000 colaboradores (grupo global); Vodafone Germany é a maior operação europeia",
        "hq": "Düsseldorf, Alemanha (Vodafone GmbH); grupo com sede em Newbury, UK",
        "international": "Grupo global; operação alemã com sede em Düsseldorf",
        "business_areas": ["Rede móvel e fixa", "B2B/Geschäftskunden", "Technology & IoT", "TV e conteúdo"],
        "website": "https://www.vodafone.com",
        "careers_url": "https://careers.vodafone.com/de/en/your-opportunities",
        "checked": TODAY,
        "sources": [
            _src("Vodafone Careers Germany — Internships (programa formal, Pflichtpraktikum €1.200)", "https://careers.vodafone.com/de/en/your-opportunities/internships", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de internships no portal alemão (3–6 meses, remunerado); sem declaração pública sobre visto/autorização não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Vodafone Careers Germany: \"Your internship runs for 3 to 6 months. ... Are you doing a mandatory internship? Then you receive €1,200.\"",
             "url": "https://careers.vodafone.com/de/en/your-opportunities/internships", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de internships com remuneração citada no portal oficial alemão; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "KPMG",
        "aliases": ["KPMG International Cooperative", "KPMG Deutschland", "KPMG AG"],
        "industry": "Consultoria, auditoria e serviços financeiros (Big Four)",
        "size": "~12.000 colaboradores (KPMG Deutschland)",
        "hq": "Frankfurt am Main, Alemanha (KPMG AG Wirtschaftsprüfungsgesellschaft)",
        "international": "Rede global KPMG",
        "business_areas": ["Audit", "Consulting", "Deal Advisory", "Tax & Legal", "Data Analytics"],
        "website": "https://kpmg.com/de",
        "careers_url": "https://karriere.kpmg.de",
        "checked": TODAY,
        "sources": [
            _src("KPMG Karriere — Werkstudententätigkeit (programa formal)", "https://karriere.kpmg.de/dein-einstieg/studierende/werkstudententaetigkeit.html", "primary"),
            _src("KPMG Karriere — Praktikum (programa formal)", "https://karriere.kpmg.de/dein-einstieg/studierende/praktikum.html", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de Praktikum/Werkstudent no portal de carreiras alemão; páginas checadas 2026-10-04 sem declaração pública sobre visto não-UE nos estágios alemães (a página US de sponsorship NÃO se aplica ao contexto DE).",
        "sources_for": {"visa_policy": [
            {"text": "KPMG Karriere: \"Als Werkstudent:in erhältst Du einen umfangreichen Einblick in die Arbeitswelt bei KPMG.\" — página oficial de Werkstudententätigkeit + página Praktikum no portal alemão.",
             "url": "https://karriere.kpmg.de/dein-einstieg/studierende/werkstudententaetigkeit.html", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes no portal oficial alemão; sem declaração de sponsorship no contexto DE — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Würth Group",
        "aliases": ["Würth Group", "Würth Industrie Service GmbH & Co. KG", "Würth", "Adolf Würth GmbH & Co. KG"],
        "industry": "Fixações, montagem e ferramentas (Fastening & Assembly)",
        "size": "~88.000 colaboradores (grupo global)",
        "hq": "Künzelsau, Baden-Württemberg, Alemanha",
        "international": "Mais de 400 empresas em 80+ países",
        "business_areas": ["Fixações e parafusos", "Würth Industrie Service (C-Parts)", "Eletrônica (Würth Elektronik)", "Financeiro (incl. Recaro stake)"],
        "website": "https://www.wuerth.com",
        "careers_url": "https://www.wuerth.com/wuerth-gruppe/Karriere/Einstiegsstufen/Einstiegsstufen.php",
        "checked": TODAY,
        "sources": [
            _src("Würth Group — Einstiegsstufen (Praktikum, Werkstudent, Trainee)", "https://www.wuerth.com/wuerth-gruppe/Karriere/Einstiegsstufen/Einstiegsstufen.php", "primary"),
            _src("Würth Industrie Service — Studierende (Praktikum/Abschlussarbeiten)", "https://www.wuerth-industrie.com/web/de/karriere/studierende/praktikum.php", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programas formais de Praktikum/Werkstudent citados no portal do grupo e da Würth Industrie Service; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Würth Group — Einstiegsstufen: \"Dafür bietet die Würth-Gruppe vielfältige Möglichkeiten: Praktikum, ...\" (página oficial de entradas para estudantes).",
             "url": "https://www.wuerth.com/wuerth-gruppe/Karriere/Einstiegsstufen/Einstiegsstufen.php", "quality": "primary", "checked": TODAY,
             "note": "Programa formal citado no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Stryker",
        "aliases": ["Stryker", "Stryker GmbH & Co. KG", "Stryker Leibinger GmbH & Co. KG", "Stryker Endoscopy GmbH"],
        "industry": "Tecnologia médica (medical devices)",
        "size": "~53.000 colaboradores (grupo global, 2024)",
        "hq": "Kalamazoo, EUA (grupo); operações alemãs em Freiburg, Schönkirchen, Duisburg, Tuttlingen",
        "international": "Fortune 500; ~75 países",
        "business_areas": ["Ortopedia", "Cirurgia e neurotecnologia", "MedSurg", "Endoscopia (Freiburg)"],
        "website": "https://www.stryker.com",
        "careers_url": "https://careers.stryker.com/students-and-graduates",
        "checked": TODAY,
        "sources": [
            _src("Stryker Careers — Student and Graduate programs in Europe (internship programs in Germany, Switzerland and Austria)", "https://careers.stryker.com/students-and-graduates", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de internships na Alemanha citado no portal oficial (GSA region); sem declaração específica sobre visto não-UE para estágios DE nas páginas checadas 2026-10-04 (a regra US 'no sponsorship for interns' é do contexto americano).",
        "sources_for": {"visa_policy": [
            {"text": "Stryker Careers: \"Internship programs in Germany, Switzerland and Austria run at varying times throughout the year and across many different functions including Sales, Clinical Specialist, Manufacturing, Engineering and more.\"",
             "url": "https://careers.stryker.com/students-and-graduates", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de internships na Alemanha citado no portal oficial; sem declaração de sponsorship para DE — unclear (programa citado). A nota US (Extern: 'Stryker does not sponsor visas for interns') refere-se ao programa americano, não ao alemão."},
        ]},
    },
    {
        "company": "AGCO",
        "aliases": ["AGCO", "AGCO GmbH", "Fendt"],
        "industry": "Máquinas agrícolas (agricultural equipment)",
        "size": "~23.000 colaboradores (grupo global)",
        "hq": "Duluth, Geórgia, EUA (grupo); Fendt em Marktoberdorf, Alemanha",
        "international": "Marcas globais: Fendt, Massey Ferguson, Valtra, Challenger",
        "business_areas": ["Tratores (Fendt)", "Colheitadeiras", "Peças e serviços", "Digital farming"],
        "website": "https://www.agco.com",
        "careers_url": "https://careers.agcocorp.com/go/Fendt/2576000",
        "checked": TODAY,
        "sources": [
            _src("AGCO/Fendt Careers — vagas de estudantes em Marktoberdorf (Praktikant/Werkstudent SoSe 2027)", "https://careers.agcocorp.com/go/Fendt/2576000", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de Praktikum/Werkstudent na Fendt (Marktoberdorf) com vagas ativas no portal oficial; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "AGCO/Fendt Careers: \"Praktikant / Werkstudent (m/w/d) im Bereich Fendt Go-to-Market Training (SoSe 2027)\" — vagas ativas de estudantes em Marktoberdorf no portal oficial da AGCO.",
             "url": "https://careers.agcocorp.com/go/Fendt/2576000", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes com vagas ativas citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "TRUMPF",
        "aliases": ["trumpf", "TRUMPF SE + Co. KG", "TRUMPF GmbH + Co. KG", "Trumpf"],
        "industry": "Máquinas-ferramenta a laser e eletrônica de potência",
        "size": "Mais de 18.000 colaboradores (grupo global)",
        "hq": "Ditzingen, Baden-Württemberg, Alemanha",
        "international": "~70 subsidiárias operacionais no mundo; fábricas em DE, AT, CH, US, CN",
        "business_areas": ["Máquinas a laser e sistemas", "Eletrônica de potência (triodentes)", "Lasers de femtossegundo", "Serviços digitais (Axoom)"],
        "website": "https://www.trumpf.com",
        "careers_url": "https://www.trumpf.com/de_DE/karriere/studierende",
        "checked": TODAY,
        "sources": [
            _src("TRUMPF Karriere — Studierende (Praktikum, Werkstudententätigkeit, Abschlussarbeit)", "https://www.trumpf.com/de_DE/karriere/studierende", "primary"),
            _src("TRUMPF Karriere — Studierende in Deutschland (portal Workday TRUMPF_Students)", "https://trumpf.wd3.myworkdayjobs.com/TRUMPF_Students", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de Praktikum/Werkstudent com portal próprio de estudantes (Workday); Auslandspraktika citados; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "TRUMPF Karriere: \"Mit einem Praktikum, einer Werkstudententätigkeit oder einer Abschlussarbeit sammeln Sie während des Studiums Praxiserfahrung – in allen unseren Unternehmensbereichen auf der ganzen Welt.\"",
             "url": "https://www.trumpf.com/de_DE/karriere/studierende", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes com portal dedicado; a página cita Auslandspraktika (internacionais) mas não declara sponsorship de visto — unclear (programa citado)."},
        ]},
    },
    {
        "company": "aumovio",
        "aliases": ["aumovio", "AUMOVIO SE Haupverwaltung", "AUMOVIO SE", "Aumovio"],
        "industry": "Tecnologia automotiva (semicondutores, sensores, eletrônica de potência)",
        "size": "~30.000 colaboradores (grupo, desde o spin-off da Continental em 2025)",
        "hq": "Frankfurt am Main, Alemanha (holding aumovio SE)",
        "international": "Spin-off listado do grupo Continental (set/2025); sites em Regensburg, Villingen-Schwenningen, Lindau, Babenhausen",
        "business_areas": ["Semicondutores automotivos", "Sensores", "Eletrônica de potência", "Display e UX"],
        "website": "https://www.aumovio.com",
        "careers_url": "https://jobs.aumovio.com",
        "checked": TODAY,
        "sources": [
            _src("AUMOVIO — Job openings (\"AUMOVIO is a Talent Factory\": internship, thesis, graduate entry)", "http://www.aumovio.com/en/career/job-openings.html", "primary"),
            _src("AUMOVIO Jobportal — Technical Internship at AUMOVIO (vaga ativa de estágio)", "https://jobs.aumovio.com/en/detail-page/job-detail/REF9006X-p-b630c7e77211665dbe5006ec7e90203e/technical-internship-at-aumovio-tm-", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial com vagas ativas de internship (\"Talent Factory\"); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "AUMOVIO Job openings: \"Whether you join us through an internship, thesis program, or graduate entry, you'll find opportunities to grow\" + vaga ativa \"Technical Internship at AUMOVIO™\" no jobportal.",
             "url": "http://www.aumovio.com/en/career/job-openings.html", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de internships com vagas ativas citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "TikTok",
        "aliases": ["TikTok", "TikTok Information Technologies Germany GmbH", "ByteDance"],
        "industry": "Plataforma de conteúdo e e-commerce (internet)",
        "size": "~150.000 colaboradores (ByteDance, grupo global)",
        "hq": "Pequim/Singapura (grupo); operações alemãs em Munique e Berlim",
        "international": "Plataforma global ByteDance; escritórios EMEA",
        "business_areas": ["TikTok Shop (e-commerce)", "GBS (Global Business Solutions)", "Trust & Safety", "Produto e operações"],
        "website": "https://www.tiktok.com",
        "careers_url": "https://lifeattiktok.com/earlycareers/emea",
        "checked": TODAY,
        "sources": [
            _src("TikTok Early Careers — Program Europe, UK and Middle East (internships and graduate roles)", "https://lifeattiktok.com/earlycareers/emea", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de internships EMEA citado no portal oficial de early careers (vagas ativas em Munique, ex. Business Development Intern TikTok Shop); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "TikTok Early Careers EMEA: \"TikTok offers a range of internships and graduate roles, providing limitless possibilities to gain valuable experience and kickstart your career.\"",
             "url": "https://lifeattiktok.com/earlycareers/emea", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de internships EMEA citado no portal oficial, com vagas ativas em Munique (TikTok Shop Operations, 2027 start); sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Müller Service GmbH",
        "aliases": ["mllerservi", "Müller Service GmbH", "Unternehmensgruppe Theo Müller", "Müller"],
        "industry": "Laticínios e alimentos (grupo Theo Müller)",
        "size": "~30.000 colaboradores (grupo Theo Müller)",
        "hq": "Fischach (Aretsried), Baviera, Alemanha",
        "international": "Grupo familiar alemão; marcas Müller, Müller Milch, etc.",
        "business_areas": ["Laticínios (Müller)", "Foods (Casa Fiesta, etc.)", "Ingredientes (Milk & Whey)", "Logística e serviços"],
        "website": "https://www.muellergroup.com",
        "careers_url": "https://careers.muellergroup.com/Mueller_CE/go/All-Jobs/4444401",
        "checked": TODAY,
        "sources": [
            _src("Jobbörse der Unternehmensgruppe Theo Müller (Praktikum/Werkstudent em Leppersdorf, Freising, Aretsried)", "https://careers.muellergroup.com/Mueller_CE/go/All-Jobs/4444401", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de carreiras do grupo com vagas ativas de Praktikum/Werkstudent (Studenten); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04. Nota: alias 'mllerservi' é string truncada do dataset (Müller Service GmbH — empregador legal das vagas Aretsried/Fischach).",
        "sources_for": {"visa_policy": [
            {"text": "Jobbörse Theo Müller Gruppe: \"Praktikum Forschung & Entwicklung Käse (m/w/d) — Leppersdorf | Bereich: Forschung & Entwicklung | Einstiegslevel: Studenten\" (vagas ativas no portal oficial).",
             "url": "https://careers.muellergroup.com/Mueller_CE/go/All-Jobs/4444401", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes com vagas ativas (Praktikum/Werkstudent) citadas no portal oficial do grupo; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Vetter Pharma-Fertigung GmbH & Co. KG",
        "aliases": ["Vetter Pharma-Fertigung GmbH & Co. KG", "Vetter Pharma International GmbH", "Vetter"],
        "industry": "Manufatura farmacêutica por contrato (CDMO)",
        "size": "~7.400 colaboradores",
        "hq": "Ravensburg, Baden-Württemberg, Alemanha",
        "international": "Sites em Ravensburg, Langenargen (DE) e Rankweil (AT), EUA (Chicago area)",
        "business_areas": ["Enchimento asséptico (syringes, vials, cartridges)", "Desenvolvimento analítico", "P embalagem e serialização", "Quality Management"],
        "website": "https://www.vetter-pharma.com",
        "careers_url": "https://www.vetter-pharma.com/de/karriere/einstiegsmoeglichkeiten/studierende",
        "checked": TODAY,
        "sources": [
            _src("Vetter Karriere — Studierende (Praktikum Quality Management / Produktion & Technik)", "https://www.vetter-pharma.com/de/karriere/einstiegsmoeglichkeiten/studierende/qualitaetsmanagement", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de Praktikum para estudantes citado no portal oficial (várias divisões); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Vetter Karriere — Studierende: \"Praxiserfahrung im Quality Management während des Studiums bei Vetter sammeln\" (páginas oficiais de Praktikum por divisão).",
             "url": "https://www.vetter-pharma.com/de/karriere/einstiegsmoeglichkeiten/studierende/qualitaetsmanagement", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estágios com páginas dedicadas por divisão no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "MTU Aero Engines AG",
        "aliases": ["MTU Aero Engines AG", "MTU Maintenance Hannover GmbH", "MTU Maintenance Berlin-Brandenburg GmbH", "MTU Aero Engines", "MTU Maintenance"],
        "industry": "Motores de aviação (OEM e MRO)",
        "size": "~12.000 colaboradores (grupo)",
        "hq": "Munique, Alemanha",
        "international": "Sites em Munique, Hannover-Langenhagen, Ludwigsfelde, Berlim-Brandenburgo; JV com Pratt & Whitney e Lufthansa",
        "business_areas": ["Desenvolvimento e fabricação de turbinas", "MRO (Maintenance Hannover/Berlin)", "Defesa (motores militares)", "Industrial gas turbines"],
        "website": "https://www.mtu.de",
        "careers_url": "https://www.mtu.de/de/karriere/jobboerse",
        "checked": TODAY,
        "sources": [
            _src("MTU Aero Engines — Jobbörse (Praktikum/Werkstudent ativos em München, Hannover, Ludwigsfelde)", "https://www.mtu.de/de/karriere/jobboerse", "primary"),
            _src("MTU Careers — Internship (programa formal com direct e pool postings)", "https://www.mtu.de/careers/students/internship", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de internships com página própria (direct/pool postings) e vagas ativas de Praktikum/Werkstudent no portal; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "MTU Careers — Internship: \"At MTU, we offer two different job postings for interns. Direct postings: In this type of postings, the department posts a vacant position for a very specific topic, and you can apply individually.\"",
             "url": "https://www.mtu.de/careers/students/internship", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de internships com vagas ativas (München/Hannover/Ludwigsfelde) citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Lufthansa Group",
        "aliases": ["Lufthansa Technik AG", "Deutsche Lufthansa AG", "Lufthansa", "Lufthansa Industry Solutions"],
        "industry": "Aviação (grupo de linhas aéreas e MRO)",
        "size": "~110.000 colaboradores (grupo); Lufthansa Technik >22.000",
        "hq": "Colônia (sede legal), Alemanha; hub em Frankfurt e Munique",
        "international": "Global player de aviação; Lufthansa Technik com 30+ subsidiárias internacionais",
        "business_areas": ["Lufthansa Airlines (passageiros)", "Lufthansa Technik (MRO)", "Cargo (Lufthansa Cargo)", "IT (Industry Solutions)"],
        "website": "https://www.lufthansagroup.com",
        "careers_url": "https://www.lufthansagroup.careers/en/internship",
        "checked": TODAY,
        "sources": [
            _src("Lufthansa Group Careers — Internship (requisitos oficiais do programa)", "https://www.lufthansagroup.careers/en/internship", "primary"),
            _src("Lufthansa Technik — Entry opportunities for students (internships/working student)", "https://www.lufthansa-technik.com/en/entry-opportunities-for-students", "primary"),
        ],
        "visa_policy": "candidate_must_have_authorization",
        "visa_policy_note": "Página oficial do programa de internship do grupo declara que o candidato precisa ter work and residence permit em mãos no início do estágio — negativa honesta (não patrocina o processo para não-UE); página JS-rendered, citação verificada no índice de busca do conteúdo oficial 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Lufthansa Group Careers — Internship: \"If a work and residence permit is required for the country of assignment, it must be available at the latest at the beginning of the internship - otherwise the [internship cannot begin]\".",
             "url": "https://www.lufthansagroup.careers/en/internship", "quality": "primary", "checked": TODAY,
             "note": "Requisito declarado no portal oficial do programa: a autorização de trabalho/residência precisa já estar disponível no início — para não-UE isso significa prover a própria autorização (não há declaração de patrocínio). Página renderizada via JS; texto verificado via índice de busca (snippet) do conteúdo oficial em 2026-10-04."},
        ]},
    },
    {
        "company": "MAHLE",
        "aliases": ["MAHLE International GmbH", "MAHLE GmbH", "Mahle", "MAHLE Industrieservice GmbH"],
        "industry": "Autopeças e sistemas térmicos (mobility)",
        "size": "~72.000 colaboradores (grupo global)",
        "hq": "Stuttgart, Alemanha",
        "international": "Presença em 30+ países; produção e P&D globais",
        "business_areas": ["Sistemas térmicos e gestão térmica", "Filtragem e periferia de motores", "Eletrificação (e-mobility)", "Aftersales"],
        "website": "https://www.mahle.com",
        "careers_url": "https://www.jobs.mahle.com/germany/de/your-future-at-mahle/students",
        "checked": TODAY,
        "sources": [
            _src("MAHLE Karriere — Praktikum & Abschlussarbeit (programa formal)", "https://www.jobs.mahle.com/germany/de/your-future-at-mahle/students/praktikum", "primary"),
            _src("MAHLE Karriere — Werkstudierendentätigkeit (programa formal)", "https://www.jobs.mahle.com/germany/de/your-future-at-mahle/students/werkstudierendentaetigkeit", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de Praktikum/Werkstudent no portal alemão; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "MAHLE Karriere: \"Ob Bachelor- oder Master-Studiengang – bei MAHLE kannst du ab dem 3. Fachsemester dein technisches oder kaufmännisches Praktikum absolvieren.\"",
             "url": "https://www.jobs.mahle.com/germany/de/your-future-at-mahle/students/praktikum", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estágios com regras citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Infineon Technologies AG",
        "aliases": ["Infineon", "Infineon Technologies", "Infineon Technologies AG"],
        "industry": "Semicondutores",
        "size": "~58.000 colaboradores (grupo global)",
        "hq": "Neubiberg (Munique), Alemanha",
        "international": "Sites em Regensburg, Dresden, AT, BE, e globais",
        "business_areas": ["Power semiconductors (IGBT/SiC)", "Microcontroladores", "Sensores", "Security/connected systems"],
        "website": "https://www.infineon.com",
        "careers_url": "https://www.infineon.com/careers/students-graduates/students",
        "checked": TODAY,
        "sources": [
            _src("Infineon — Students (programa formal de intern/working student, thesis, graduate)", "https://www.infineon.com/careers/students-graduates/students", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de estudantes com vagas ativas no portal (Working Student Data Analytics & AI etc.); a página exige matrícula universitária (lei alemã) mas não declara política de visto; checado 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Infineon Students page: \"Join a company where you can get valuable experience – even before you graduate\" + vaga oficial: \"Proper students (according to the German law) are welcome: To work as a student employee with us, you must be enrolled at a university\".",
             "url": "https://www.infineon.com/careers/students-graduates/students", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes com vagas ativas (intern + working student) citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "AIXTRON SE",
        "aliases": ["AIXTRON SE", "AIXTRON"],
        "industry": "Equipamentos de deposição para semicondutores (MOCVD)",
        "size": "~3.400 colaboradores",
        "hq": "Herzogenrath (perto de Aachen), Alemanha",
        "international": "Listada na Prime Standard (MDAX/TecDAX); subsidiárias e clientes globais",
        "business_areas": ["Equipamentos MOCVD", "Power electronics (SiC)", "Optoeletrônica (LED, display)", "Serviços e processos"],
        "website": "https://www.aixtron.com",
        "careers_url": "https://www.aixtron.com/en/careers/students",
        "checked": TODAY,
        "sources": [
            _src("AIXTRON — Careers: Students (programa formal Pflicht/Freiwillig Praktikum 6–9 meses)", "https://www.aixtron.com/en/careers/students", "primary"),
            _src("AIXTRON — Vacancies (Praktikum IT Data/AI, Project Purchasing ativos)", "https://www.aixtron.com/en/careers/vacancies", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de estágios (Pflicht/Freiwillig, 6–9 meses, remunerado) com vagas ativas no portal; exige matrícula universitária válida; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "AIXTRON Students: \"At AIXTRON, you can also complete a mandatory or voluntary internship. These internships usually last six to nine months and require you to work 40 hours per week. ... you should also work in a structured, reliable and focused manner and possess a valid enrolment certificate.\"",
             "url": "https://www.aixtron.com/en/careers/students", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estágios com vagas ativas citadas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Rheinmetall AG",
        "aliases": ["Rheinmetall AG", "Rheinmetall", "Rheinmetall Defence Electronics GmbH"],
        "industry": "Tecnologia de defesa e automotivo",
        "size": "~80.000 colaboradores (grupo, com expansão recente)",
        "hq": "Düsseldorf, Alemanha",
        "international": "Sites em Unterlüß, Flensburg, Düsseldorf e internacional",
        "business_areas": ["Defesa (veículos, armas, munição, eletrônica)", "Autonomous systems", "Power systems (civis)", "Eletrônica e sensores"],
        "website": "https://www.rheinmetall.com",
        "careers_url": "https://www.rheinmetall.com/de/karriere/einstiegsmoeglichkeiten/studierende",
        "checked": TODAY,
        "sources": [
            _src("Rheinmetall — Einstieg für Studierende (Praktikum/Werkstudent com depoimentos)", "https://www.rheinmetall.com/de/karriere/einstiegsmoeglichkeiten/studierende", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de Praktikum/Werkstudent no portal oficial (página dedicada com processo citado); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Rheinmetall Einstieg für Studierende: \"Werkstudierendentätigkeit: Studium und Job perfekt kombiniert\" + \"Praktikant Markets & M&A Rheinmetall AG ... Potenzielle Chance auf eine anschließende Werkstudierendentätigkeit oder Abschlussarbeit\".",
             "url": "https://www.rheinmetall.com/de/karriere/einstiegsmoeglichkeiten/studierende", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes (Praktikum/Werkstudent) citado no portal oficial com vagas ativas; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Kärcher",
        "aliases": ["Alfred Kärcher SE & Co. KG", "Kärcher SE & Co. KG", "Kärcher"],
        "industry": "Tecnologia de limpeza (alta pressão, industrial)",
        "size": "~16.000 colaboradores (grupo)",
        "hq": "Winnenden, Baden-Württemberg, Alemanha",
        "international": "Presença em 160+ países; produção global",
        "business_areas": ["Máquinas de alta pressão", "Aspiradores", "Limpeza industrial e municipal", "Sistemas de água/irrigação"],
        "website": "https://www.kaercher.com",
        "careers_url": "https://careers.kaercher.com",
        "checked": TODAY,
        "sources": [
            _src("Kärcher Careers — portal (Praktikum/Internship ativos, ex. Productmanagement)", "https://careers.kaercher.com/go/Alfred-K%C3%A4rcher-SE-&-Co_-KG/9009555", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial com vagas ativas de Praktikum/Internship e Werkstudent (ex. Winnenden); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Kärcher Careers: \"Praktikum / Internship Productmanagement Home and Garden — Winnenden, DE, 71364\" (vaga ativa no portal oficial da Alfred Kärcher SE & Co. KG).",
             "url": "https://careers.kaercher.com/go/Alfred-K%C3%A4rcher-SE-&-Co_-KG/9009555", "quality": "primary", "checked": TODAY,
             "note": "Vagas ativas de Praktikum/Internship no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "adidas AG",
        "aliases": ["adidas", "Adidas", "adidas AG"],
        "industry": "Artigos esportivos (sportswear)",
        "size": "~62.000 colaboradores (grupo)",
        "hq": "Herzogenaurach, Baviera, Alemanha",
        "international": "Global HQ em Herzogenaurach com times de 100+ nações; escritórios e mercados mundiais",
        "business_areas": ["Produto e design", "Marketing e marca", "Supply chain", "Global procurement", "Digital/IT"],
        "website": "https://www.adidas-group.com",
        "careers_url": "https://careers.adidas-group.com/teams/students/internships-students",
        "checked": TODAY,
        "sources": [
            _src("adidas Careers — Internships (Herzo-FAQ oficial para estágios na HQ alemã)", "https://careers.adidas-group.com/teams/students/internships-students", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "FAQ oficial da HQ alemã: apoia com paperwork do work permit, MAS não cobre taxas de visto/relocation; estudante precisa estar matriculado durante todo o estágio — condicional (unclear), não suporte incondicional.",
        "sources_for": {"visa_policy": [
            {"text": "adidas Herzo-FAQ: \"In Germany, we have many interns from all over the world. However, you must be enrolled as a student for the whole period of the internship in order to obtain a work permit. We will be happy to support you in this process with the paperwork; however, we do not cover the relocation- or visa fees.\"",
             "url": "https://careers.adidas-group.com/teams/students/internships-students", "quality": "primary", "checked": TODAY,
             "note": "Declaração CONDICIONAL oficial: suporte com paperwork SIM, cobertura de taxas NÃO, matrícula obrigatória — regra da curadoria: condicional => unclear (não explicit_support)."},
        ]},
    },
    {
        "company": "Endress+Hauser InfoServe GmbH+Co. KG",
        "aliases": ["Endress+Hauser InfoServe GmbH+Co. KG", "Endress + Hauser Wetzer GmbH & Co.KG", "Endress+Hauser", "Endress+Hauser Group"],
        "industry": "Instrumentação de processo e serviços (automation)",
        "size": "Grupo Endress+Hauser: ~17.000 colaboradores mundialmente",
        "hq": "Maulburg, Alemanha (InfoServe); grupo em Reinach, Suíça",
        "international": "Grupo familiar global com entidades de serviço na Alemanha",
        "business_areas": ["Serviços de instrumentação", "Calibração e repair", "Digital services", "Training"],
        "website": "https://www.endress.com",
        "careers_url": "https://www.endress.com/de/endress-hauser-gruppe/de-karriere",
        "checked": TODAY,
        "sources": [
            _src("Endress+Hauser — Karriere portal (Praktikum/Abschlussarbeit ativos em Maulburg)", "https://www.endress.com/de/endress-hauser-gruppe/de-karriere", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal de carreiras com vagas ativas de Praktikum/Abschlussarbeit na InfoServe (Maulburg); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Endress+Hauser careers: \"Praktikum oder Abschlussarbeit Datenbasiertes Produktions-Cockpit\" — Endress+Hauser Group, Maulburg (vaga ativa de estágio no portal/agregadores oficiais).",
             "url": "https://www.endress.com/de/endress-hauser-gruppe/de-karriere", "quality": "primary", "checked": TODAY,
             "note": "Vagas ativas de Praktikum citadas no portal oficial do grupo (entidade InfoServe em Maulburg); sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "TE Connectivity",
        "aliases": ["TE Connectivity", "TE Connectivity Ltd.", "TE"],
        "industry": "Conectores e sensores (industrial technology)",
        "size": "~85.000 colaboradores (grupo global)",
        "hq": "Schaffhausen, Suíça (holding); operações alemãs em Waiblingen, Bensheim, Berlim",
        "international": "Presença global (50+ países); customers em transporte, indústria, data centers",
        "business_areas": ["Conectores (Transportation)", "Sensores", "Industrial (automation)", "Data & devices"],
        "website": "https://www.te.com",
        "careers_url": "https://careers.te.com",
        "checked": TODAY,
        "sources": [
            _src("TE Connectivity — Careers (portal global; Students section)", "https://careers.te.com", "primary"),
        ],
        "visa_policy": "not_verified",
        "visa_policy_note": "Portal de carreiras global e páginas Students checados 2026-10-04: o programa de internships documentado publicamente é o americano (10–12 semanas, verão, sites EUA); não foi encontrada declaração pública sobre programa de estágio formal na Alemanha nem sobre visto/autorização para o contexto DE.",
    },
    {
        "company": "Pirelli Deutschland GmbH",
        "aliases": ["PirelliTyres", "Pirelli Deutschland GmbH", "Pirelli Tyres", "Pirelli"],
        "industry": "Pneus (manufacturing)",
        "size": "~2.500 colaboradores na Alemanha (Breuberg + München); grupo ~30.000",
        "hq": "Breuberg, Hessen, Alemanha (subsidiária alemã); grupo em Milão, Itália",
        "international": "Grupo italiano; planta alemã em Breuberg (produção, R&D, admin) e escritório em München",
        "business_areas": ["Produção de pneus premium", "R&D e process development", "Supply chain", "Marketing/PR (München)"],
        "website": "https://www.pirelli.com",
        "careers_url": "https://corporate.pirelli.com/corporate/en-ww/careers/work-with-us",
        "checked": TODAY,
        "sources": [
            _src("Pirelli — Work with us (portal de carreiras oficial; Breuberg/München com Praktika e Initiativbewerbung)", "https://corporate.pirelli.com/corporate/en-ww/careers/work-with-us", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de carreiras lista Praktika/Initiativbewerbung para Breuberg e München; página da empresa (Hobit/IQB) confirma \"Studierende für ein Pflichtpraktikum\" em todos os Fachbereiche; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Pirelli Deutschland (perfil oficial IQB Career Services): \"Wir suchen für verschiedene Bereiche: Studierende für ein Pflichtpraktikum\" + portal Work with us: \"Sollte sich in unserem Portal für Sie zurzeit keine offene Stelle befinden ... können Sie sich gerne initiativ bewerben. In Breuberg und München\"",
             "url": "https://iqb.de/unternehmensportraets/pirelli-deutschland-gmbh", "quality": "secondary", "checked": TODAY,
             "note": "Programa formal de Pflichtpraktikum para estudantes citado no perfil oficial da empresa em portal universitário (IQB) + portal oficial de carreiras com Initiativbewerbung ativa; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Bechtle AG",
        "aliases": ["Bechtle AG", "Bechtle"],
        "industry": "TI (IT systemhaus e e-commerce)",
        "size": "~15.000 colaboradores (grupo)",
        "hq": "Neckarsulm, Alemanha",
        "international": "Presença na Europa (DE, AT, CH, e mais)",
        "business_areas": ["IT Systemhaus (serviços e soluções)", "E-commerce (Bechtle direct)", "Managed Services", "Software licensing"],
        "website": "https://www.bechtle.com",
        "careers_url": "https://www.bechtle.com/karriere/studierende",
        "checked": TODAY,
        "sources": [
            _src("Bechtle — Karriere für Student:innen (Praktikum, Werkstudent, Abschlussarbeit)", "https://www.bechtle.com/karriere/studierende", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Programa formal de estudantes no portal oficial (\"ob im Praktikum, als Werkstudent:in oder mit deiner Abschlussarbeit\"); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Bechtle Karriere: \"Bei Bechtle bist du sofort voll drin in der IT-Welt – ob im Praktikum, als Werkstudent:in oder mit deiner Abschlussarbeit.\"",
             "url": "https://www.bechtle.com/karriere/studierende", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes citado no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "SMA Solar Technology AG",
        "aliases": ["SMA Solar Technology AG", "SMA Solar Technology", "SMA"],
        "industry": "Energia solar (inversores fotovoltaicos)",
        "size": "~4.000 colaboradores na Alemanha",
        "hq": "Kassel, Hessen, Alemanha",
        "international": "Presença global; produção em Niestetal (Kassel) e no exterior",
        "business_areas": ["Inversores solares (residenciais, comerciais, utilidade)", "Serviços e O&M", "Energia (EV charging)", "Digital energy services"],
        "website": "https://www.sma.de",
        "careers_url": "https://sma.jobs/go/Student_Arbeit/3798501",
        "checked": TODAY,
        "sources": [
            _src("SMA Solar — Studierende @ SMA Solar Technology AG (portal oficial)", "https://sma.jobs/go/Student_Arbeit/3798501", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Portal oficial de estudantes com vagas ativas de Werkstudent (Kassel); sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "SMA Solar Jobs: \"Dein Einstieg als Werkstudent*in. Du hast Lust an der Energiewende mitzuarbeiten, die Zukunft mitzugestalten und die gelernte Theorie in der Praxis anzuwenden?\"",
             "url": "https://sma.jobs/go/Student_Arbeit/3798501", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de Werkstudent com vagas ativas no portal oficial; sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Everllence SE",
        "aliases": ["Everllence SE", "Everllence", "Daimler Truck AG", "Daimler Truck", "MAN Energy Solutions SE", "MAN Energy Solutions"],
        "industry": "Engenharia e tecnologia de powertrain/energia (grandes motores, compressores, turbomáquinas)",
        "size": "~15.000 colaboradores; 140+ sites em 50+ países",
        "hq": "Augsburg, Alemanha (HQ global)",
        "international": "Grupo com tradição de 260+ anos; parte do ecossistema Volkswagen Group",
        "business_areas": ["Motores a diesel/gás (marítimo, energia)", "Turbo machinery (compressores, turbinas)", "Pós-tratamento e serviços", "Descarbonização (carbon capture, heat pumps)"],
        "website": "https://www.everllence.com",
        "careers_url": "https://www.everllence.com/career/career-path",
        "checked": TODAY,
        "sources": [
            _src("Everllence — Career paths (Students: working student, intern, thesis; Dual Studies in Germany)", "https://www.everllence.com/career/career-path", "primary"),
            _src("Everllence — Jobs at Everllence Germany (Augsburg HQ: \"Entry via internship, working student job or thesis\")", "https://www.everllence.com/career/international-jobs/germany", "primary"),
        ],
        "visa_policy": "unclear",
        "visa_policy_note": "Nota de identidade (2026-10-04): a spec da fase chamava Everllence de 'ex-Daimler Truck'; o site oficial diz 'MAN Energy Solutions is now Everllence' (grupo VW, HQ Augsburg) — curado pelo fato vivo, aliases de Daimler Truck mantidos por segurança de match. Programa formal de students (intern/working student/thesis) citado no portal; sem declaração pública sobre visto não-UE nas páginas checadas 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Everllence Germany: \"Entry via internship, working student job or thesis\" + Career paths: \"At Everllence, you put what you have learned into practice as a working student or intern.\"",
             "url": "https://www.everllence.com/career/international-jobs/germany", "quality": "primary", "checked": TODAY,
             "note": "Programa formal de estudantes citado no portal oficial (Augsburg HQ); sem declaração de sponsorship — unclear (programa citado)."},
        ]},
    },
    {
        "company": "Simon-Kucher & Partners",
        "aliases": ["simon-kucher", "Simon-Kucher", "Simon-Kucher & Partners", "Simon Kucher"],
        "industry": "Consultoria de estratégia (pricing e growth)",
        "size": "~2.000 colaboradores (consultants) em 30+ escritórios globais",
        "hq": "Bonn, Alemanha",
        "international": "Consultoria global (Bonn, Berlim, Boston, Amsterdã, Varsóvia etc.)",
        "business_areas": ["Pricing strategy", "Commercial strategy", "Marketing/sales", "Monetização e growth"],
        "website": "https://www.simon-kucher.com",
        "careers_url": "https://www.simon-kucher.com/en/careers",
        "checked": TODAY,
        "sources": [
            _src("Simon-Kucher — Consulting Career Opportunities (Student Jobs and Internships)", "https://www.simon-kucher.com/en/careers", "primary"),
            _src("Simon-Kucher — FAQs für Studierende (requisitos oficiais de aplicação)", "https://www.simon-kucher.com/de/faqs-fuer-studierende-deine-bewerbung-bei-simon-kucher", "primary"),
        ],
        "visa_policy": "candidate_must_have_authorization",
        "visa_policy_note": "FAQ oficial para estudantes exige explicitamente: \"Für Nicht-EU-Bürger:innen: Eine gültige Aufenthalts- und Arbeitserlaubnis\" — o candidato não-UE precisa JÁ ter autorização de residência e trabalho; negativa honesta (não patrocina), checado 2026-10-04.",
        "sources_for": {"visa_policy": [
            {"text": "Simon-Kucher FAQ für Studierende — Erforderliche Unterlagen: \"Für Nicht-EU-Bürger:innen: Eine gültige Aufenthalts- und Arbeitserlaubnis\"",
             "url": "https://www.simon-kucher.com/de/faqs-fuer-studierende-deine-bewerbung-bei-simon-kucher", "quality": "primary", "checked": TODAY,
             "note": "Exigência declarada no FAQ oficial: não-UE precisa apresentar Aufenthalts- und Arbeitserlaubnis válidas (já obtidas) — candidate_must_have_authorization, não sponsorship."},
        ]},
    },
]

EXISTING_UPDATES = {
    # Mercedes-Benz Group: 25 vagas com a string "Mercedes-Benz Group AG" (com AG)
    # não casavam com o canônico "Mercedes-Benz Group"; +1 da Mercedes-AMG GmbH.
    # Estado re-verificado hoje (2026-10-04) SEM evidência nova de suporte a
    # visto -> mantém candidate_must_have_authorization (fonte F7 preservada).
    "mercedes-benz group": {
        "extra_aliases": ["Mercedes-Benz Group AG", "Mercedes-AMG GmbH"],
    },
    # Fraunhofer: re-pesquisa F9 achou pathway institucional para brasileiros
    # (não-UE) documentado pelo Liaison Office Brazil -> upgrade
    # not_verified -> unclear com citação textual.
    "fraunhofer-gesellschaft": {
        "extra_aliases": ["Fraunhofer-Gesellschaft e.V. Zentrale München"],
        "visa_policy": "unclear",
        "visa_policy_note": "Upgrade F9 (2026-10-04): pathway institucional para estudantes/pesquisadores brasileiros (não-UE) documentado pela Fraunhofer (Liaison Office Brazil), incluindo carta de convite do empregador e comprovante de estágio/salário para fins de imigração; não é declaração incondicional de patrocínio.",
        "sources_for": {"visa_policy": [
            {"text": "Fraunhofer Liaison Office Brazil — Careers at Fraunhofer: \"Proof of enrollment at university, letter proving your internship and salary in Germany (for immigration purposes if necessary)\"; pré-requisitos de visto incluem \"Invitation letter from your employer\"",
             "url": "https://www.brazil.fraunhofer.com/en/career-at-fraunhofer.html", "quality": "primary", "checked": TODAY,
             "note": "Página oficial do escritório de ligação da Fraunhofer documenta o caminho institucional de brasileiros para estágios/trabalho nos institutos, com carta de convite do empregador como pré-requisito padrão de visto — evidência de programa institucional para não-UE (unclear), não sponsorship incondicional."},
        ]},
    },
}


def main() -> None:
    data = json.loads(CI.read_text(encoding="utf-8"))
    companies = data["companies"]
    by_name = {e["company"].casefold(): e for e in companies}

    added: list[str] = []
    for entry in GRUPO_A + GRUPO_B:
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
