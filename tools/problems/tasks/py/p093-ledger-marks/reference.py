import re


def link_ledger_marks(marks: list[str], aliases: dict[str, str]) -> list:
    for retired, replacement in aliases.items():
        if retired == replacement:
            raise ValueError("alias table maps a code to itself")
        if replacement in aliases:
            raise ValueError("alias replacement is itself retired")
    groups: dict[str, list[str]] = {}
    for raw in marks:
        if not isinstance(raw, str):
            raise ValueError("mark must be a string")
        m = re.fullmatch(r"([A-Za-z]{2,3})[-/ ](\d+)([A-Za-z])", raw)
        if m is None:
            raise ValueError("malformed ledger mark")
        house = m.group(1).upper()
        serial = int(m.group(2))
        check = m.group(3).upper()
        if serial == 0:
            raise ValueError("serial value must be at least 1")
        if check != chr(65 + serial % 26):
            raise ValueError("check letter does not match serial")
        house = aliases.get(house, house)
        canonical = f"{house}-{serial}-{check}"
        groups.setdefault(canonical, []).append(raw)
    return [[canonical, raws] for canonical, raws in groups.items()]
