"""Skill-gap analysis: deterministic, offline.

Answers, from the collected job descriptions alone (no LLM, no network):
which procurement / supply-chain / materials skills do internship postings
actually mention, how often, and which of them are missing from a given
candidate profile?

Design notes
------------
* A SKILL GROUP maps one canonical skill to a list of regex patterns
  (German and English synonyms count together, e.g. "Disposition" and
  "demand planning" feed the same group).
* Matching is word-boundary aware and case-insensitive, tuned for the
  vocabulary observed in real internship postings (see
  ``docs/f28_skill_gap.md`` for the calibration method).
* ``extract_skills`` and ``gap_report`` are pure functions: same input,
  same output, every time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

__all__ = [
    "SKILL_GROUPS",
    "SkillGroup",
    "SkillStats",
    "extract_skills",
    "gap_report",
    "profile_text",
    "JOB_TEXT_FIELDS",
]


@dataclass(frozen=True)
class SkillGroup:
    """One canonical skill plus the regex patterns that detect it."""

    name: str  # canonical, snake_case, stable identifier
    label: str  # human-readable label for reports
    category: str  # e.g. "systems", "procurement", ...
    patterns: tuple  # regex source strings, matched case-insensitively


def _compile(group: SkillGroup) -> re.Pattern:
    return re.compile("|".join(group.patterns), re.IGNORECASE)


def _make(
    name: str,
    label: str,
    category: str,
    patterns: Sequence[str],
) -> SkillGroup:
    return SkillGroup(name=name, label=label, category=category, patterns=tuple(patterns))


# ---------------------------------------------------------------------------
# The versioned skill dictionary.
#
# Calibration: patterns were selected against a deterministic random sample
# of 40 eligible postings (seed=28) plus full-corpus frequency counts on the
# 2026-10-12 snapshot (783 eligible jobs, 704 with description). Entries whose
# vocabulary never appears (e.g. Incoterms, MRP, SAP MM) are kept only if they
# have signal >= 1 in the corpus; the ordering below is roughly by observed
# market frequency so that the report reads naturally.
# ---------------------------------------------------------------------------
SKILL_GROUPS: List[SkillGroup] = [
    # --- systems / ERP -----------------------------------------------------
    _make("sap", "SAP", "systems",
          [r"\bSAP\b", r"\bSAP[ -]?Ariba\b", r"\bAriba\b", r"\bCoupa\b",
           r"\bSAP[ -]?MM\b"]),
    _make("erp", "ERP systems", "systems",
          [r"\bERP\b", r"\bERPs\b", r"enterprise resource planning",
           r"Warenwirtschafts?system", r"Warenwirtschaft",
           r"merchandise management system", r"\bMDG\b"]),
    _make("excel", "Excel / spreadsheets", "systems",
          [r"\bExcel\b", r"\bMS Excel\b", r"spreadsheet", r"Tabellenkalkulation",
           r"Office-Paket", r"MS Office", r"Microsoft Office", r"Office 365",
           r"Microsoft 365", r"Power Query", r"Google Sheets"]),
    _make("powerpoint", "PowerPoint / presentations", "systems",
          [r"PowerPoint", r"Keynote", r"Präsentation", r"presentation skills",
           r"presentations for stakeholders", r"präsentierst", r"Präsentationen"]),
    _make("powerbi", "Power BI / Tableau (BI dashboards)", "data",
          [r"Power\s?BI", r"\bPowerBI\b", r"\bTableau\b", r"Looker",
           r"\bQlik\b", r"\bDAX\b", r"business intelligence",
           r"\bDashboard", r"Dashboards erstellen"]),
    _make("sql", "SQL", "data",
          [r"\bSQL\b", r"\bT-SQL\b", r"\bPostgreSQL\b", r"\bMySQL\b", r"\bOracle\b"]),
    _make("python", "Python", "data",
          [r"\bPython\b", r"\bPandas\b", r"\bNumPy\b", r"scikit-learn", r"\bPyTorch\b",
           r"r\bpython\b"]),
    _make("data_analysis", "Data analysis / Auswertungen", "data",
          [r"data analys", r"datenanalys", r"analytics", r"Auswertung",
           r"Datenanalyse", r"data analytics", r"\bKPIs?\b", r"Kennzahl",
           r"Statistik", r"statistical", r"análise de dados"]),
    _make("automation", "RPA / process automation", "data",
          [r"\bRPA\b", r"robotic process automation", r"Power Automate",
           r"PowerApps", r"UiPath", r"process automation", r"Automatisierung",
           r"automação"]),
    # --- procurement core ---------------------------------------------------
    _make("procurement", "Einkauf / procurement", "procurement",
          [r"\bEinkauf", r"Eink.aufe?s?", r"Beschaffung", r"purchasing",
           r"procurement", r"sourcing", r"compras?", r"aquisi",
           r"strategischer Einkauf", r"strategic sourcing", r"strategic purchasing"]),
    _make("category_management", "Category management", "procurement",
          [r"category management", r"Category-Management", r"Sortiments",
           r"Kategoriemanagement", r"Warengruppenmanagement", r"Warengruppe"]),
    _make("supplier_management", "Supplier / Lieferantenmanagement", "procurement",
          [r"Lieferant", r"suppliers?", r"vendors?", r"Lieferantenmanagement",
           r"supplier management", r"vendor management", r"Lieferantenentwicklung",
           r"Lieferantenbetreuung", r"Lieferantenbewertung", r"fornecedores?"]),
    _make("negotiation", "Verhandlung / negotiation", "procurement",
          [r"Verhandlung", r"negotiat", r"Verhandlungs", r"negocia"]),
    _make("demand_planning", "Bedarfsermittlung / demand planning", "procurement",
          [r"Bedarfsermittlung", r"Bedarfsplanung", r"Bedarfsm", r"demand planning",
           r"demand forecast", r"Bedarfsanalyse", r"disposition", r"Disposition",
           r"autodisposition", r"forecast", r"Forecast", r"Prognose"]),
    _make("tendering", "Ausschreibung / tendering (RFP/RFQ)", "procurement",
          [r"Ausschreibung", r"\btender", r"\bRFP\b", r"\bRFQ\b", r"request for proposal",
           r"Angebotsvergleich", r"Angebotseinholung"]),
    _make("contract_management", "Vertragsmanagement / contract management", "procurement",
          [r"Vertrags", r"\bcontract", r"Vertragsmanagement", r"contract management"]),
    _make("customs_tarifs", "Zoll / customs", "procurement",
          [r"\bZoll\b", r"\bcustoms\b", r"Zollabwicklung", r"Importabwicklung"]),
    _make("incoterms", "Incoterms", "procurement",
          [r"Incoterms?", r"\bEXW\b", r"\bFOB\b", r"\bCIF\b", r"\bDAP\b"]),
    # --- supply chain / logistics ------------------------------------------
    _make("supply_chain", "Supply chain / Lieferkette", "supply_chain",
          [r"supply chain", r"Lieferkette", r"Wertschöpfungskette", r"value chain",
           r"supply-chain"]),
    _make("logistics", "Logistics / Logistik", "supply_chain",
          [r"\blogistics?\b", r"\bLogistik\b", r"Logistika?l", r"logistische",
           r"logística", r"logisticas?"]),
    _make("inventory", "Inventory / Bestandsmanagement", "supply_chain",
          [r"Bestandsmanagement", r"bestandsü", r"Lagerbestand", r"Bestandskontrolle",
           r"inventory", r"Bestandsf", r"bestands", r"inventário", r"estoque",
           r"gestão de inventário"]),
    _make("warehousing", "Warehousing / Lagerlogistik", "supply_chain",
          [r"Lagerlogistik", r"Lagerhaltung", r"Lagerverwaltung", r"warehous",
           r"distribution center", r"Distributionszentrum", r"\bLager\b"]),
    _make("transport", "Transport / freight", "supply_chain",
          [r"Transportmanagement", r"Verkehrsplanung", r"Spedition", r"freight",
           r"Fuhrpark", r"\b3PL\b", r"third-party logistics"]),
    _make("production_planning", "Produktionsplanung / production planning", "supply_chain",
          [r"Produktionsplanung", r"Produktionssteuerung", r"production planning",
           r"PPS\b", r"Feinplanung", r"Materialbedarf", r"\bMRP\b",
           r"material requirements planning"]),
    _make("lean", "Lean / Kanban / JIT", "supply_chain",
          [r"\blean\b", r"\bKanban\b", r"just[- ]in[- ]time", r"\bJIT\b", r"Kaizen",
           r"Six Sigma", r"\bVMI\b", r"vendor managed inventory"]),
    # --- materials / engineering -------------------------------------------
    _make("materials_science", "Werkstoffkunde / materials science", "materials",
          [r"Werkstoff", r"materials science", r"materials engineering",
           r"Materialkunde", r"Materialwissenschaft", r"metallkund"]),
    _make("materials_testing", "Werkstoffprüfung / materials testing", "materials",
          [r"Werkstoffprüf", r"Materialprüf", r"material testing",
           r"zerstörungsfreie Prüfung", r"\bZfP\b", r"\bNDT\b", r"metallograph",
           r"metalografia", r"Vickers", r"dureza Vickers"]),
    _make("quality_management", "Quality management / ISO", "materials",
          [r"Qualitätsmanagement", r"quality management", r"ISO\s?9001",
           r"Qualitätssicherung", r"quality assurance", r"Qualitätsprüf"]),
    _make("cad", "CAD", "materials",
          [r"\bCAD\b", r"SolidWorks", r"AutoCAD", r"\bCATIA\b", r"\bCREO\b",
           r"Solid Edge", r"Fusion 360"]),
    _make("fem", "FEM / simulation", "materials",
          [r"\bFEM\b", r"finite element", r"\bANSYS\b", r"ABAQUS", r"Simulink",
           r"COMSOL"]),
    _make("master_data", "Stammdaten / master data", "procurement",
          [r"Stammdaten", r"master data", r"Datenpflege", r"artikeldaten"]),
    _make("cloud_bigdata", "Cloud / big data", "data",
          [r"\bcloud\b", r"\bAWS\b", r"\bAzure\b", r"big data", r"data lake"]),
    _make("goods_receipt", "Wareneingang / goods receipt", "supply_chain",
          [r"Wareneingang", r"goods receipt", r"Reklamation", r"complaint management"]),
    # --- methods / soft -----------------------------------------------------
    _make("project_management", "Projektmanagement", "methods",
          [r"Projektmanagement", r"project management", r"Projektarbeit",
           r"MS Project", r"Microsoft Project", r"gestão de projetos",
           r"gerenciamento de projetos", r"project planning"]),
    _make("english", "English", "languages",
          [r"\bEnglish\b", r"\bEnglisch\b", r"business English",
           r"inglês", r"Inglês"]),
    _make("german", "Deutsch / German", "languages",
          [r"\bDeutsch\b", r"\bGerman\b", r"business Deutsch", r"Verhandlungssicher",
           r"verhandlungssicher", r"fließend", r"alemão", r"Alemão"]),
    _make("sustainability", "Sustainability / Kreislaufwirtschaft", "methods",
          [r"Nachhaltigkeit", r"sustainab", r"Kreislaufwirtschaft", r"circular economy",
           r"recycling", r"\bLCA\b", r"life cycle assessment", r"sustentabilidade",
           r"reciclagem"]),
    _make("databases", "Databases / Datenbanken", "data",
          [r"Datenbank", r"database", r"\bCRM\b", r"Salesforce"]),
]

# Pre-compiled patterns, index-aligned with SKILL_GROUPS.
_COMPILED: List[re.Pattern] = [_compile(g) for g in SKILL_GROUPS]
_INDEX: Dict[str, int] = {g.name: i for i, g in enumerate(SKILL_GROUPS)}

# Job dict fields used when building the searchable text of one posting.
JOB_TEXT_FIELDS = ("title", "description")


@dataclass
class SkillStats:
    """Aggregated counts for one skill group across the job set."""

    skill: str  # canonical group name
    label: str
    category: str
    freq_title: int  # postings whose TITLE matches
    freq_desc: int  # postings whose DESCRIPTION matches
    freq_any: int  # postings where title OR description matches
    n_jobs: int  # size of the analysed universe
    share_eligible: float  # freq_any / n_jobs
    present_in_profile: Optional[bool] = None  # None when no profile given

    def as_dict(self) -> Dict[str, Any]:
        return {
            "skill": self.skill,
            "label": self.label,
            "category": self.category,
            "freq_title": self.freq_title,
            "freq_desc": self.freq_desc,
            "freq_any": self.freq_any,
            "n_jobs": self.n_jobs,
            "share_eligible": round(self.share_eligible, 4),
            "present_in_profile": self.present_in_profile,
        }


def extract_skills(text: str) -> List[str]:
    """Return canonical skill names detected in ``text`` (sorted, deduped).

    >>> extract_skills("Erfahrung mit SAP Ariba und Excel")
    ['excel', 'sap']
    """
    if not text:
        return []
    found = [g.name for g, rx in zip(SKILL_GROUPS, _COMPILED) if rx.search(text)]
    return sorted(found)


def job_skills(job: Dict[str, Any]) -> Dict[str, str]:
    """Return {'skill': 'title'|'desc'} for one job record."""
    out: Dict[str, str] = {}
    for field_name in JOB_TEXT_FIELDS:
        value = (job.get(field_name) or "") if isinstance(job, dict) else ""
        if not value:
            continue
        for g, rx in zip(SKILL_GROUPS, _COMPILED):
            if rx.search(value):
                out.setdefault(g.name, field_name)
    return out


def gap_report(
    jobs: Iterable[Dict[str, Any]],
    profile_text: Optional[str] = None,
) -> List[SkillStats]:
    """Aggregate skill demand across ``jobs`` and flag profile presence.

    Parameters
    ----------
    jobs: iterable of job dicts with ``title`` and ``description`` keys.
    profile_text: optional free text of the candidate profile. When given,
        ``present_in_profile`` is True for skills detected in it.

    Returns the full skill list (all groups), sorted by ``freq_any`` desc,
    then by name. Consumers slice/derive sections from it.
    """
    jobs = list(jobs)
    n = len(jobs)
    n_title = {g.name: 0 for g in SKILL_GROUPS}
    n_desc = {g.name: 0 for g in SKILL_GROUPS}
    n_any = {g.name: 0 for g in SKILL_GROUPS}

    for job in jobs:
        for skill, where in job_skills(job).items():
            if where == "title" and (job.get("description") or ""):
                # a title match also counts for desc-level visibility; keep
                # the stricter semantics: title matches stay title matches,
                # but the skill is present in the posting either way.
                pass
            n_any[skill] += 1
            if where == "title":
                n_title[skill] += 1
            else:
                n_desc[skill] += 1

    profile_skills = set(extract_skills(profile_text)) if profile_text else set()

    stats = []
    for g in SKILL_GROUPS:
        stats.append(
            SkillStats(
                skill=g.name,
                label=g.label,
                category=g.category,
                freq_title=n_title[g.name],
                freq_desc=n_desc[g.name],
                freq_any=n_any[g.name],
                n_jobs=n,
                share_eligible=(n_any[g.name] / n) if n else 0.0,
                present_in_profile=(g.name in profile_skills) if profile_text is not None else None,
            )
        )
    stats.sort(key=lambda s: (-s.freq_any, s.skill))
    return stats


def profile_text(path: str) -> str:
    """Read a candidate-profile markdown file and return its skills signal.

    Extracts headings + bullet/label/table lines (the parts of a CV-style
    markdown that carry skill vocabulary), skipping long prose paragraphs.
    Tolerant: never raises on odd formatting, returns '' when nothing is
    found.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return ""
    keep: List[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        is_heading = stripped.startswith("#")
        is_bullet = stripped.startswith(("-", "*", "+"))
        is_table_row = stripped.startswith("|") and stripped.count("|") >= 2
        is_label = ("**" in stripped) or (":" in stripped)
        is_short = len(stripped) <= 260
        if (is_heading or is_bullet or is_label or is_table_row) and is_short:
            keep.append(stripped)
    return "\n".join(keep)
