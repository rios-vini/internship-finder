import re

INTERNSHIP_PATTERNS = [
    r"\bintern\b",
    r"\binternship\b",
    r"\bco[- ]?op\b",
    r"\btrainee\b",
    r"\bapprentice\b",
    r"\bstudent\b",
    r"\bgraduate\b",
    r"\bundergraduate\b",
    r"\bplacement\b",
]

EXCLUDE_PATTERNS = [
    r"\bsenior\b",
    r"\bsr\.\b",
    r"\bsr\b",
    r"\bprincipal\b",
    r"\bstaff\b",
    r"\blead\b",
    r"\bmanager\b",
    r"\bdirector\b",
    r"\bhead of\b",
    r"\bchief\b",
]


def is_internship(title: str, description: str | None = None) -> bool:
    text = f"{title} {description or ''}".lower()

    if any(re.search(pattern, title.lower()) for pattern in EXCLUDE_PATTERNS):
        return False

    return any(re.search(pattern, text) for pattern in INTERNSHIP_PATTERNS)
