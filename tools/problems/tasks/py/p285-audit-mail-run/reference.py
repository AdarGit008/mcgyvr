import re

CODE = re.compile(r"[PLE][A-Z]{2}[0-9]{3}")
OFFICE = re.compile(r"[A-Z]{2}")


def _place(letter: str) -> int:
    return ord(letter) - 64


def audit_mail_run(items: list[dict], plan: list[dict]) -> dict:
    if not isinstance(plan, list) or not plan:
        raise ValueError("plan must be a non-empty list")
    bins: set[str] = set()
    for entry in plan:
        if not isinstance(entry, dict):
            raise ValueError("a plan entry must be a record")
        name = entry.get("bin")
        if not isinstance(name, str) or not name:
            raise ValueError("a bin must be a non-empty string")
        if name in ("QUERY", "SPARE"):
            raise ValueError(f"a plan bin may not be {name}")
        if name in bins:
            raise ValueError(f"bins repeat: {name}")
        bins.add(name)
        grades = entry.get("grades")
        if (
            not isinstance(grades, str)
            or not 1 <= len(grades) <= 3
            or len(set(grades)) != len(grades)
        ):
            raise ValueError("grades must be one to three distinct letters")
        for grade in grades:
            if grade not in "PLE":
                raise ValueError(f"unknown grade letter: {grade}")
        offices = entry.get("offices")
        if not isinstance(offices, list) or not offices:
            raise ValueError("offices must be a non-empty list")
        here: set[str] = set()
        for office in offices:
            if not isinstance(office, str) or OFFICE.fullmatch(office) is None:
                raise ValueError("an office must be two capital letters")
            if office in here:
                raise ValueError(f"offices repeat: {office}")
            here.add(office)

    if not isinstance(items, list):
        raise ValueError("items must be a list")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("an item must be a record")
        code = item.get("code")
        if not isinstance(code, str) or CODE.fullmatch(code) is None:
            raise ValueError("an item code must be six characters of the grammar")
        stamped = item.get("stamped")
        if not isinstance(stamped, str) or not stamped:
            raise ValueError("a stamped bin must be a non-empty string")

    misrouted: list[dict] = []
    counts: dict[str, int] = {}
    for item in items:
        code = item["code"]
        total = int(code[3]) + int(code[4]) + _place(code[1]) + _place(code[2])
        if total % 10 != int(code[5]):
            correct = "QUERY"
        else:
            correct = "SPARE"
            for entry in plan:
                if code[0] in entry["grades"] and code[1:3] in entry["offices"]:
                    correct = entry["bin"]
                    break
        counts[correct] = counts.get(correct, 0) + 1
        if item["stamped"] != correct:
            misrouted.append(
                {"code": code, "stamped": item["stamped"], "correct": correct}
            )

    tally = [{"bin": name, "count": counts[name]} for name in sorted(counts)]
    return {"misrouted": misrouted, "tally": tally}
