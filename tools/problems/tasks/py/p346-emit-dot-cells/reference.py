BASE = ("1", "12", "14", "145", "15", "124", "1245", "125", "24", "245")
CAPITAL = "6"
NUMBER = "3456"
BLANK = "0"
LOWER = "abcdefghijklmnopqrstuvwxyz"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"


def _raise(pattern: str, extra: str) -> str:
    return "".join(sorted(set(pattern + extra)))


def _build_cells() -> dict[str, str]:
    cells: dict[str, str] = {}
    for i in range(10):
        cells["abcdefghij"[i]] = BASE[i]
        cells["klmnopqrst"[i]] = _raise(BASE[i], "3")
    for i, letter in enumerate("uvxyz"):
        cells[letter] = _raise(BASE[i], "36")
    cells["w"] = "2456"
    return cells


CELLS = _build_cells()


def emit_dot_cells(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("the argument must be a string")
    if len(text) == 0:
        raise ValueError("the argument must not be empty")
    out: list[str] = []
    in_run = False
    for i, ch in enumerate(text):
        if ch == " ":
            if i > 0 and text[i - 1] == " ":
                raise ValueError("two spaces may not stand next to each other")
            out.append(BLANK)
            in_run = False
            continue
        if ch in DIGITS:
            if not in_run:
                out.append(NUMBER)
                in_run = True
            out.append(BASE[9 if ch == "0" else DIGITS.index(ch) - 1])
            continue
        in_run = False
        if ch in UPPER:
            out.append(CAPITAL)
            out.append(CELLS[ch.lower()])
            continue
        if ch in LOWER:
            out.append(CELLS[ch])
            continue
        raise ValueError("only ASCII letters, ASCII digits and spaces may be rendered")
    return "-".join(out)
