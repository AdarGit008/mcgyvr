import re


def _read_minute(text: str) -> int:
    if re.fullmatch(r"[0-9]+", text) is None:
        raise ValueError("a minute is written in decimal figures")
    value = int(text)
    if value > 1440:
        raise ValueError("a minute never runs past 1440")
    return value


def first_skill_gap(shifts: list[list[str]], required: list[list[str]]) -> str:
    if not isinstance(shifts, list):
        raise ValueError("the roster must be a list")
    tours = []
    rostered = set()
    for row in shifts:
        if not isinstance(row, list) or len(row) < 4:
            raise ValueError("a tour is a name, two minutes and at least one skill")
        for field in row:
            if not isinstance(field, str) or not field:
                raise ValueError("every tour field is a non-empty string")
        if row[0] in rostered:
            raise ValueError("that name is rostered twice")
        rostered.add(row[0])
        start = _read_minute(row[1])
        end = _read_minute(row[2])
        if start >= end:
            raise ValueError("a tour must end after it starts")
        skills = set()
        for skill in row[3:]:
            if skill in skills:
                raise ValueError("a tour writes one skill twice")
            skills.add(skill)
        tours.append((start, end, skills))

    if not isinstance(required, list) or not required:
        raise ValueError("there must be something to demand")
    demands = []
    for row in required:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError("a demand is exactly four fields")
        for field in row:
            if not isinstance(field, str) or not field:
                raise ValueError("every demand field is a non-empty string")
        if re.fullmatch(r"[0-9]+", row[1]) is None:
            raise ValueError("a headcount is written in decimal figures")
        least = int(row[1])
        if least < 1:
            raise ValueError("a demand asks for at least one person")
        opens = _read_minute(row[2])
        closes = _read_minute(row[3])
        if opens >= closes:
            raise ValueError("a demand must close after it opens")
        demands.append((row[0], least, opens, closes))

    cuts = set()
    for start, end, _ in tours:
        cuts.add(start)
        cuts.add(end)
    for _, _, opens, closes in demands:
        cuts.add(opens)
        cuts.add(closes)
    marks = sorted(cuts)
    for left, right in zip(marks, marks[1:]):
        for skill, least, opens, closes in demands:
            if opens > left or right > closes:
                continue
            answering = 0
            for start, end, skills in tours:
                if start <= left and right <= end and skill in skills:
                    answering += 1
            if answering < least:
                return f"{left}-{right} {skill}"
    return "covered"
