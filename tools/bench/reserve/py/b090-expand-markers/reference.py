import re


def expand_markers(template: str, values: dict) -> str:
    if not isinstance(template, str):
        raise ValueError("expand_markers expects a string template")
    out = []
    i = 0
    while i < len(template):
        ch = template[i]
        if ch != "%":
            out.append(ch)
            i += 1
            continue
        if template[i + 1:i + 2] == "%":
            out.append("%")
            i += 2
            continue
        close = template.find("%", i + 1)
        if close == -1:
            raise ValueError("marker opened and never closed")
        name = template[i + 1:close]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
            raise ValueError("malformed marker name: " + name)
        if name not in values:
            raise ValueError("no value for marker: " + name)
        if not isinstance(values[name], str):
            raise ValueError("marker values must be strings")
        out.append(values[name])
        i = close + 1
    return "".join(out)
