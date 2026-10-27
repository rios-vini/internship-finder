"""F143 — anti-sinal Umschulung/Azubi/Auszubildende + Klinikum/Krankenhaus no healthcare-context.

Data-driven: lê fixtures/f143_fixtures.json (verbatim do NEW 27/10) e verifica
is_student_role + matches_area contra o expected de cada caso. As fixtures são
a especificação — este arquivo apenas as executa.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from internship_finder.filters import is_student_role, matches_area  # noqa: E402


def main() -> int:
    fixtures = json.loads(
        (Path(__file__).resolve().parent.parent / "fixtures" / "f143_fixtures.json").read_text()
    )["f143_fixtures"]
    fails = 0
    total = 0
    for group in ("false_positives", "contra_cases"):
        print(f"== {group} ==")
        for case in fixtures[group]:
            total += 1
            exp = case["expected"]
            got_student = is_student_role(case["title"], case["description"] or None)
            got_area = matches_area(case["title"], case["description"] or None)
            ok = got_student == exp["is_student_role"] and got_area == exp["matches_area"]
            status = "OK" if ok else "FAIL"
            if not ok:
                fails += 1
            print(f"  [{status}] {case['id']}: student={got_student} (exp {exp['is_student_role']}), "
                  f"area={got_area} (exp {exp['matches_area']}) — {exp['reason']}")
    print(f"\nF143: {fails} falha(s) de {total}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())