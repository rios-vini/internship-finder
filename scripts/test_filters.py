"""Testes dos filtros de tipo/estudante e pais (scripts/test_filters.py).

Doze casos definidos pelo dono na pos-auditoria (Fase 1), mais niveis de
integracao: consistencia dos marcadores/exclusoes, adapter (flag
``Job.internship``) e resolver (empresa/ATS inexistente). Uso:

    .venv/bin/python scripts/test_filters.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.adapters.ats import AtsJobAdapter  # noqa: E402
from internship_finder.filters import (  # noqa: E402
    PROGRAM_EXCLUSION_PATTERNS,
    STUDENT_TYPE_PATTERNS,
    TYPE_EXCLUSION_PATTERNS,
    infer_country_iso,
    is_student_role,
    matches_country,
    parse_country_spec,
)
from internship_finder.models.company import Company  # noqa: E402
from internship_finder.resolver.company_resolver import CompanyResolver  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        FAILURES.append(name)


def test_type_rules() -> None:
    print("== regras de tipo (12 casos do dono) ==")
    # 1. Internship -> aceitar
    check("1. Internship aceito", is_student_role("Internship (m/f/d) - Supply Chain"))
    # 2. Praktikum -> aceitar
    check("2. Praktikum aceito", is_student_role("Praktikum im Einkauf"))
    # 3. Werkstudent -> aceitar
    check("3. Werkstudent aceito", is_student_role("Werkstudent (w/m/d) Data Analytics"))
    # 4. Working Student + Part-time -> aceitar
    check(
        "4. Working Student + PART_TIME aceito",
        is_student_role("Working Student (f/m/d) - BI", None, "PART_TIME"),
    )
    # 5. Part-time sem indicador estudantil -> rejeitar
    check(
        "5. PART_TIME sozinho rejeitado",
        not is_student_role("Sales Assistant (m/f/d)", None, "PART_TIME"),
    )
    # 6. Senior + Praktikum -> aceitar (marcador forte vence senioridade)
    check(
        "6. Senior + Praktikum aceito",
        is_student_role("Praktikum - Assistenz des Senior Vice Presidents"),
    )
    # 7. Graduate Trainee -> rejeitar (mesmo com employment_type "trainee")
    check(
        "7. Graduate Trainee rejeitado",
        not is_student_role("Graduate Trainee - Procurement", None, "trainee"),
    )
    # 8. Management Trainee -> rejeitar
    check(
        "8. Management Trainee rejeitado",
        not is_student_role("Management Trainee - Operations", None, "trainee"),
    )
    # 9. JMP / Junior Managers Program -> rejeitar (exclusao vence employment_type)
    check(
        "9a. Junior Managers Program rejeitado",
        not is_student_role(
            "Junior Managers Program (Trainee) - Purchasing", None, "trainee"
        ),
    )
    check(
        "9b. JMP abreviado rejeitado",
        not is_student_role("JMP - Leadership Journey", None, "trainee"),
    )
    # Trainee generico deixou de ser marcador: sem outro marcador, nao passa.
    check(
        "9c. 'Trainee' generico nao e marcador",
        not is_student_role("Trainee - Finance", None, "FULL_TIME"),
    )
    # "Internship Trainee" / contexto estudantil continua aceito (coberto por
    # intern/internship — sem regra extra).
    check(
        "9d. 'Internship Trainee' aceito (contexto estudantil)",
        is_student_role("Internship Trainee (f/m/d) - Supply Chain"),
    )


def test_type_exclusion_rules() -> None:
    print("== exclusao de tipo: Duales Studium/Ausbildung/Schulpraktikum (Fase 1) ==")
    # Casos do dono (decisao pos-auditoria): excluir Duales Studium, Ausbildung
    # e Schuelerpraktikum; PRESERVAR Internship/Intern, Praktikum, Werkstudent
    # e Working Student.
    check("D1. 'Schuelerpraktikum' excluido",
          not is_student_role("Schülerpraktikum"))
    check("D2. 'Praktikum (w/m/d)' aceito",
          is_student_role("Praktikum (w/m/d)"))
    check("D3. 'Duales Studium BWL' excluido",
          not is_student_role("Duales Studium BWL"))
    check("D4. 'Werkstudent im Bereich Data Analytics' aceito",
          is_student_role("Werkstudent im Bereich Data Analytics"))
    check("D5. 'Ausbildung zum Fachinformatiker' excluido",
          not is_student_role("Ausbildung zum Fachinformatiker"))
    check("D6. 'Working Student Supply Chain (m/f/d)' aceito",
          is_student_role("Working Student Supply Chain (m/f/d)"))
    # Composicao: "Schuelerpraktikum" contem "praktikum" como substring — a
    # palavra composta e excluida mesmo assim; "Hochschulpraktikum" (estagio
    # universitario, B. Braun no dataset real) NAO e excluido (\b inicial).
    check("D7. 'Schuelerpraktikum im Logistikzentrum' excluido (composicao)",
          not is_student_role("Längerfristiges Schülerpraktikum im Logistikzentrum (m/w/d)"))
    check("D8. 'Hochschulpraktikum' aceito (estagio universitario valido)",
          is_student_role("Hochschulpraktikum (w/m/d) Sustainability Reporting & Controlling"))
    check("D9. 'Schulpraktikum' excluido (estagio escolar)",
          not is_student_role("Technisches Schulpraktikum (m/w/d)"))
    check("D10. 'Praktikum im Rahmen des Dualen Studiums' excluido (genitivo)",
          not is_student_role("Praktikum im Rahmen des Dualen Studiums"))
    # Variantes reais do dataset: Dualer Master, Dual Study, Duale:r Student:in,
    # Duale Hochschule, Dualer Student, ausbildungsintegriertes Duales Studium.
    check("D11. 'Dualer Master (M.Eng.)' excluido",
          not is_student_role("Dualer Master (M.Eng.) - Systems Engineering - Fachrichtung Elektrotechnik"))
    check("D12. 'Dual Study programme ...' excluido (ingles)",
          not is_student_role("Dual study programme 2026: Data Science and Artificial Intelligence (B.Sc)"))
    check("D13. 'Duale:r Student:in' excluido (dois-pontos genero-inclusivo)",
          not is_student_role("Duale:r Student:in - Spedition und Logistik (m/w/d)"))
    check("D14. 'Dual Study Kooperation' vence 'Industriepraktikum' (dual)",
          not is_student_role("Industriepraktikum - Hardware-Software-Design (Dual Study Kooperation FH OÖ Hagenberg)"))
    check("D15. 'Duale Hochschule' excluido",
          not is_student_role("Studium Wirtschaftsingenieurwesen - Duale Hochschule BW Heidenheim / Start 2027"))
    check("D16. 'Dualer Student Studiengang (B. A)' excluido",
          not is_student_role("Dualer Student Studiengang (B. A) Betriebswirtschaft - Fachrichtung Logistikmanagement (w/m/d)"))
    check("D17. 'Ausbildungsintegriertes Duales Studium' excluido",
          not is_student_role("Ausbildungsintegriertes Duales Studium Digital Engineering Maschinenbau (w/m/d) 2027"))
    # Ausbildung e equivalentes.
    check("D18. 'Berufsausbildung' excluido",
          not is_student_role("Berufsausbildung"))
    check("D19. 'Ausbildung Elektronikerin ...' excluido (VW real)",
          not is_student_role("Ausbildung Elektronikerin / Elektroniker für Automatisierungstechnik (w/m/d) 2027"))
    check("D20. 'Ausbildung als Industriekaufmann/-frau' excluido (ZF real)",
          not is_student_role("Ausbildung als Industriekaufmann/-frau (m/w/d) ab 01.09.2027"))
    # Estagios escolares (nao universitarios).
    check("D21. 'Praktikum fuer Schueler:innen' excluido (SAP real)",
          not is_student_role("Herbstpraktikum für Schüler:innen (m/w/d) Standort Walldorf 27.10 - 30.10.2026 (STAR)"))
    check("D22. 'Berufsorientierungspraktikum' excluido (BASF/Evonik real)",
          not is_student_role("Berufsorientierungspraktikum (m/w/d) Rheinfelden"))
    check("D23. 'Schulpraktikum ... Berufsausbildung' excluido (MAHLE real)",
          not is_student_role("Schulpraktikum Stuttgart 2026 - Schwerpunkt kaufmännische Berufsausbildung (m/w/d)"))
    # Servico voluntario (nao estagio universitario).
    check("D24. 'FSJ' excluido",
          not is_student_role("FSJ im Bereich Logistik"))
    check("D25. 'Freiwilliges Soziales Jahr' excluido",
          not is_student_role("Freiwilliges Soziales Jahr im Bereich Einkauf"))
    # NAO excluir "studium" sozinho: Werkstudent em contexto de estudo e valido.
    check("D26. 'Werkstudent ... Studium' aceito ('studium' sozinho nao exclui)",
          is_student_role("Werkstudent im Bereich Data Science - Studium der Wirtschaftsinformatik"))
    check("D27. 'Pflichtpraktikum Logistik' aceito (Bosch real, Top 20)",
          is_student_role("Pflichtpraktikum Logistik - Schwerpunkt Data & Analytics"))
    # Sem marcador estudantil: titulo dual NAO passa (nao e regressao — nunca
    # foi eligible; "Master ... dual" nao tem marcador de tipo).
    check("D28. 'Master ... dual' sem marcador estudantil nao passa",
          not is_student_role("Master Maschinenbau - Produktionssysteme dual (m/w/d) ab 01.03.2027"))


def test_location_level() -> None:
    print("== vaga sem localizacao (dois niveis) ==")
    spec_de = parse_country_spec("de")
    # is_student_role NAO depende de localizacao: aceita se tipo/area.
    check(
        "10a. is_student_role independe de localizacao (aceita)",
        is_student_role("Werkstudent - Data Analytics"),
    )
    check("10b. infer_country_iso sem localizacao -> None", infer_country_iso() is None)
    # matches_country com spec "de" REJEITA vaga sem localizacao.
    check(
        "10c. matches_country 'de' rejeita sem localizacao",
        not matches_country(None, None, None, spec_de),
    )
    check(
        "10d. matches_country 'de' aceita com country_iso=de",
        matches_country("de", None, None, spec_de),
    )
    check(
        "10e. matches_country 'all' aceita sem localizacao",
        matches_country(None, None, None, parse_country_spec("all")),
    )


def test_no_description() -> None:
    print("== vaga sem descricao ==")
    check(
        "11a. sem descricao nao quebra (titulo com marcador aceita)",
        is_student_role("Praktikum Logistik", None),
    )
    check(
        "11b. sem descricao, titulo sem marcador rejeita",
        not is_student_role("Junior Buyer (m/f/d)", None),
    )
    check(
        "11c. sem descricao, classificacao so pelo titulo",
        is_student_role("Working Student (f/m/d) - Procurement", None),
    )


def test_ats_independence() -> None:
    print("== independencia de ATS ==")
    # is_student_role nao recebe origem/ATS: mesma vaga de estagio e aceita.
    check(
        "12a. is_student_role independe do ATS (INTERN aceito)",
        is_student_role("Intern - Supply Chain", None, "INTERN"),
    )
    resolver = CompanyResolver()
    check(
        "12b. resolver empresa inexistente -> lista vazia",
        resolver.resolve("empresa-inexistente-xyz-123") == [],
    )


def test_consistency() -> None:
    print("== consistencia: marcadores x exclusoes ==")
    joined = " ".join(STUDENT_TYPE_PATTERNS).lower()
    check("trainee fora dos marcadores fortes", "trainee" not in joined)
    check("junior managers fora dos marcadores fortes", "junior managers" not in joined)
    check("jmp fora dos marcadores fortes", "jmp" not in joined)
    check(
        "exclusoes com os 4 programas do dono",
        len(PROGRAM_EXCLUSION_PATTERNS) == 4,
    )
    # Fase 1: regra de tipo com padroes EXPLICITOS (nada de palavra solta
    # generica — "praktikum"/"studium" NAO podem virar exclusao).
    check("exclusao de tipo nao tem 'praktikum' solto",
          all("praktikum" != p.strip(r"\b") for p in TYPE_EXCLUSION_PATTERNS))
    check("exclusao de tipo nao tem 'studium' solto",
          all("studium" != p.strip(r"\b") for p in TYPE_EXCLUSION_PATTERNS))
    check("exclusao de tipo tem 15 padroes explicitos",
          len(TYPE_EXCLUSION_PATTERNS) == 15)
    # Adaptador (flag Job.internship) usa a mesma regra.
    company = Company(ats="smartrecruiters", slug="BoschGroup", name="Bosch Group")
    adapter = AtsJobAdapter()
    jmp_job = adapter.to_job(
        {"title": "Junior Managers Program (Trainee) - Purchasing",
         "employment_type": "trainee",
         "url": "https://jobs.example/jmp"},
        company,
    )
    check("adapter: JMP -> internship False", jmp_job.internship is False)
    praktikum = adapter.to_job(
        {"title": "Praktikum Logistik - Data & Analytics",
         "url": "https://jobs.example/praktikum"}, company
    )
    check("adapter: Praktikum -> internship True", praktikum.internship is True)
    dual = adapter.to_job(
        {"title": "Duales Studium BWL - Logistik (B.A.) 2027",
         "url": "https://jobs.example/dual"}, company
    )
    check("adapter: Duales Studium -> internship False", dual.internship is False)
    hochschul = adapter.to_job(
        {"title": "Hochschulpraktikum (w/m/d) im Bereich Controlling",
         "url": "https://jobs.example/hochschul"}, company
    )
    check("adapter: Hochschulpraktikum -> internship True",
          hochschul.internship is True)
    # Fase 3: country_iso tem FONTE UNICA — o adapter usa
    # filters.infer_country_iso (ISO valido via COUNTRY_CODES); a heuristica
    # antiga (tail da location) morria em codigo postal.
    friedrichshafen = adapter.to_job(
        {
            "title": "Praktikum Logistik",
            "location": "Friedrichshafen, BW, DE, 88046",
            "url": "https://jobs.example/friedrichshafen",
        },
        company,
    )
    check(
        "adapter: 'Friedrichshafen, BW, DE, 88046' -> country_iso 'de'",
        friedrichshafen.country_iso == "de",
    )
    sem_pais = adapter.to_job({"title": "Praktikum Logistik",
                               "url": "https://jobs.example/sem-pais"}, company)
    check(
        "adapter: sem localizacao -> country_iso None",
        sem_pais.country_iso is None,
    )
    # Fase 2 (Phenom/DHL): a API Phenom compoe "Cidade, Estado, Nome do Pais"
    # sem campo country_iso — o fallback por NOME do pais no ultimo segmento
    # recupera o ISO. Nomes divididos em 2 segmentos tambem sao reconhecidos.
    phenom_de = adapter.to_job(
        {
            "title": "Praktikum Logistik (m/w/d)",
            "location": "Bonn, Nordrhein-Westfalen, Germany",
            "url": "https://jobs.example/phenom-de",
        },
        company,
    )
    check("F2. Phenom 'Bonn, ..., Germany' -> country_iso 'de'",
          phenom_de.country_iso == "de")
    phenom_us = adapter.to_job(
        {
            "title": "Intern - Supply Chain",
            "location": "Goodyear, Arizona, United States of America",
            "url": "https://jobs.example/phenom-us",
        },
        company,
    )
    check("F2. Phenom '..., United States of America' -> 'us'",
          phenom_us.country_iso == "us")
    check("F2. infer: 'Chengdu, ..., China, People's Republic of' -> 'cn'",
          infer_country_iso(
              location="Chengdu, Sichuan, China, People's Republic of"
          ) == "cn")
    check("F2. infer: 'Seoul, ..., Korea, (South) Republic' -> 'kr'",
          infer_country_iso(
              location="Seoul, Seoul Teugbyeolsi, Korea, (South) Republic"
          ) == "kr")
    # Junk de 2 letras corrigido: o NOME do pais no fim vence o codigo
    # ruidoso armazenado (nunca inventa pais).
    check("F2. 'Remseck am Neckar, ..., Germany' (stored 'am') -> 'de'",
          infer_country_iso(location="Remseck am Neckar, Baden-Württemberg, Germany",
                            country_iso="am") == "de")
    check("F2. 'Cienega de flores, ..., Mexico' (stored 'de') -> 'mx'",
          infer_country_iso(location="Cienega de flores, Nuevo Leon, Mexico",
                            country_iso="de") == "mx")
    # Regressao: formato SAP "Cidade, DE, CEP" continua resolvendo pelo
    # codigo ISO na location (nao ha nome de pais no fim).
    check("F2. regressao SAP 'Walldorf, DE, 69190' -> 'de'",
          infer_country_iso(location="Walldorf, DE, 69190") == "de")
    # Fase 3 (Workday): a API Workday expoe apenas a string de localizacao
    # (na maioria cidade sozinha) — country_iso/region/lat/lon vem None. O
    # fallback de token de 2 letras NAO pode inventar pais de palavra no meio
    # da localizacao: 'de' em espanhol/portugues, 'im' em alemao, 'do' em
    # portugues. Locais reais da coleta Workday:
    check("F3. Workday 'Ecatepec, Estado de México' -> None (era 'de' falso)",
          infer_country_iso(location="Ecatepec, Estado de México") is None)
    check("F3. Workday 'Freiburg im Breisgau' -> None (era 'im' falso)",
          infer_country_iso(location="Freiburg im Breisgau") is None)
    check("F3. Workday 'São Bernardo do Campo' -> None (era 'do' falso)",
          infer_country_iso(location="São Bernardo do Campo") is None)
    check("F3. Workday 'El Prat de Llobregat' -> None (era 'de' falso)",
          infer_country_iso(location="El Prat de Llobregat") is None)
    # Cidade sozinha (formato Workday predominante) NAO vira pais:
    check("F3. Workday 'Leverkusen' -> None (sem pais na localizacao)",
          infer_country_iso(location="Leverkusen") is None)
    check("F3. Workday 'Oberkochen' -> None",
          infer_country_iso(location="Oberkochen") is None)
    check("F3. Workday 'Nuremberg' -> None",
          infer_country_iso(location="Nuremberg") is None)
    check("F3. Workday '2 Locations' -> None",
          infer_country_iso(location="2 Locations") is None)
    # Adapter com o shape real da coleta Workday (raw sem country_iso):
    wd_job = adapter.to_job(
        {
            "title": "Werkstudent Supply Chain Excellence (m/w/x)",
            "location": "Oberkochen",
            "url": "https://jobs.example/wd",
            "requisition_id": "R123",
            "ats_type": "workday",
        },
        company,
    )
    # P0.1: o resolver (fallback pos-infer_country_iso) resolve cidade DE
    # conhecida -> 'de' no adapter. A funcao infer_country_iso em si continua
    # imutavel (retorna None p/ Oberkochen); o adapter agora preenche via
    # geocoding.resolve_country_iso (camada de cidades DE conhecidas, sem rede).
    check("F3. adapter Workday 'Oberkochen' -> country_iso 'de' (resolver P0.1)",
          wd_job.country_iso == "de")
    # Regressoes da Fase 3: ISO em posicao confiavel continua valendo.
    check("F3. 'Neckarsulm, DE' (ultimo segmento) -> 'de'",
          infer_country_iso(location="Neckarsulm, DE") == "de")
    check("F3. 'Stuttgart, BW, de' (ultimo segmento) -> 'de'",
          infer_country_iso(location="Stuttgart, BW, de") == "de")
    check("F3. 'Berlin, DE, 10557' (CEP depois) -> 'de'",
          infer_country_iso(location="Berlin, DE, 10557") == "de")
    check("F3. Covestro 'Dormagen, North Rhine-Westphalia, Germany' -> 'de'",
          infer_country_iso(
              location="Dormagen, North Rhine-Westphalia, Germany"
          ) == "de")
    # Limite documentado: sigla de estado US como ultimo segmento colide com
    # ISO valido ("IN" = Indiana/India) — comportamento mantido de proposito
    # (nao ha contexto para distinguir; nunca produz 'de').
    check("F3. limite conhecido 'Lafayette, IN' -> 'in' (estado US)",
          infer_country_iso(location="Lafayette, IN") == "in")


def main() -> int:
    test_type_rules()
    test_type_exclusion_rules()
    test_location_level()
    test_no_description()
    test_ats_independence()
    test_consistency()
    print()
    if FAILURES:
        print(f"FALHAS: {len(FAILURES)} -> {FAILURES}")
        return 1
    print("TUDO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
