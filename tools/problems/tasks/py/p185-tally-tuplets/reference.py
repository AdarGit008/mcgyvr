import re

WHOLE = 64
DENOMINATORS = (1, 2, 4, 8, 16, 32, 64)


def _span_units(text):
    shape = re.fullmatch(r"(\d+)/(\d+)", text)
    if shape is None:
        raise ValueError("not a plain span: " + text)
    top, bottom = shape.group(1), shape.group(2)
    if len(top) > 1 and top[0] == "0":
        raise ValueError("numerator written with a padding zero")
    if int(top) == 0:
        raise ValueError("numerator of zero")
    if len(bottom) > 1 and bottom[0] == "0":
        raise ValueError("denominator written with a padding zero")
    if int(bottom) not in DENOMINATORS:
        raise ValueError("denominator outside the seven allowed")
    return int(top) * (WHOLE // int(bottom))


def _entry_units(entry):
    brace = entry.find("{")
    if brace == -1:
        if "}" in entry:
            raise ValueError("closing brace with nothing open")
        return _span_units(entry)
    figure = entry[:brace]
    if not figure.isdigit() or (len(figure) > 1 and figure[0] == "0"):
        raise ValueError("bad repetition figure")
    if int(figure) < 2:
        raise ValueError("figure below two")
    if not entry.endswith("}") or len(entry) == brace + 1:
        raise ValueError("brace never closed")
    body = entry[brace + 1 : len(entry) - 1]
    if body == "":
        raise ValueError("brace closed with nothing inside")
    total = 0
    for member in body.split("+"):
        total += _span_units(member)
    stretched = total * (int(figure) - 1)
    if stretched % int(figure) != 0:
        raise ValueError("squeeze is not a whole number of units")
    return stretched // int(figure)


def tally_tuplets(score: str, meter: str) -> list:
    if not isinstance(score, str) or not isinstance(meter, str):
        raise ValueError("score and meter must be strings")
    holds = _span_units(meter)
    report = []
    for measure in score.split(";"):
        entries = [piece for piece in measure.split(" ") if piece]
        if not entries:
            raise ValueError("a measure with no entries in it")
        carried = 0
        for entry in entries:
            carried += _entry_units(entry)
        report.append(carried - holds)
    return report
