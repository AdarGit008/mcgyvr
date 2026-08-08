import re

MARKS = "!#$%&*+-?@"
CLASSES = ("lower", "upper", "digit", "mark")


def _class_of(ch):
    if "a" <= ch <= "z":
        return "lower"
    if "A" <= ch <= "Z":
        return "upper"
    if "0" <= ch <= "9":
        return "digit"
    if ch in MARKS:
        return "mark"
    return ""


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def report_secret_faults(phrase: str, policy: dict) -> list:
    if not isinstance(phrase, str):
        raise ValueError("the phrase must be a string")
    if not isinstance(policy, dict):
        raise ValueError("the policy must be a record")
    for key in ("least", "most", "needs", "forbidden"):
        if key not in policy:
            raise ValueError("the policy is missing " + key)
    if not _whole(policy["least"]) or not _whole(policy["most"]):
        raise ValueError("least and most must be whole numbers of one or more")
    if policy["most"] < policy["least"]:
        raise ValueError("most may not fall below least")
    if not isinstance(policy["needs"], list) or not policy["needs"]:
        raise ValueError("needs must be a non-empty list")
    wanted = []
    for name in policy["needs"]:
        if name not in CLASSES:
            raise ValueError("needs names a class outside the four")
        if name in wanted:
            raise ValueError("needs names one class twice")
        wanted.append(name)
    if not isinstance(policy["forbidden"], list):
        raise ValueError("forbidden must be a list")
    for word in policy["forbidden"]:
        if not isinstance(word, str) or re.fullmatch(r"[a-z]+", word) is None:
            raise ValueError("a forbidden word must be small letters only")

    faults = []
    if len(phrase) < policy["least"]:
        faults.append("short")
    if len(phrase) > policy["most"]:
        faults.append("long")
    found = set()
    stray = False
    for ch in phrase:
        kind = _class_of(ch)
        if kind == "":
            stray = True
        else:
            found.add(kind)
    if stray:
        faults.append("stray")
    for name in CLASSES:
        if name in wanted and name not in found:
            faults.append(name)
    lowered = phrase.lower()
    if any(word in lowered for word in policy["forbidden"]):
        faults.append("forbidden")
    return faults
