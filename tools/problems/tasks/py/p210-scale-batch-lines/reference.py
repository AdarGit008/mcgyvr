import re

LINE = re.compile(r"([1-9][0-9]*) (g|ml|each) ([A-Za-z]+(?: [A-Za-z]+)*)")
TICK = {"g": 1, "ml": 5, "each": 1}


def _whole_portion(value: int, base: int, want: int, tick: int) -> int:
    top = value * want
    settled = ((2 * top + base * tick) // (2 * base * tick)) * tick
    return tick if settled == 0 else settled


def scale_batch_lines(items: list, want: int, base: int) -> list:
    if not isinstance(items, list):
        raise ValueError("the sheet must be a list")
    for portions in (want, base):
        if isinstance(portions, bool) or not isinstance(portions, int) or portions < 1:
            raise ValueError("a portion count must be a whole number above zero")
    named = set()
    out = []
    for line in items:
        if not isinstance(line, str):
            raise ValueError("every sheet line must be a string")
        hit = LINE.fullmatch(line)
        if hit is None:
            raise ValueError("the line breaks its shape: " + line)
        value = int(hit.group(1))
        measure = hit.group(2)
        name = hit.group(3)
        if name in named:
            raise ValueError("two lines name the same stuff: " + name)
        named.add(name)
        settled = _whole_portion(value, base, want, TICK[measure])
        out.append(str(settled) + " " + measure + " " + name)
    return out
