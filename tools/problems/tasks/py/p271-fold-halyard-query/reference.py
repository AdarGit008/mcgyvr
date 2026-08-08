HEXLOW = "0123456789abcdef"


def loosen(chunk):
    out = ""
    at = 0
    while at < len(chunk):
        glyph = chunk[at]
        if glyph != "_":
            out += glyph
            at += 1
            continue
        if at + 2 >= len(chunk):
            raise ValueError("an underscore must be followed by two hex glyphs")
        high = chunk[at + 1]
        low = chunk[at + 2]
        if high not in HEXLOW or low not in HEXLOW:
            raise ValueError("an underscore must be followed by two lower-case hex glyphs")
        code = HEXLOW.index(high) * 16 + HEXLOW.index(low)
        if code < 0x21 or code > 0x7E:
            raise ValueError("an escape must name a visible glyph")
        out += chr(code)
        at += 3
    return out


def tighten(text):
    out = ""
    for glyph in text:
        if glyph == "&":
            out += "_26"
        elif glyph == ",":
            out += "_2c"
        elif glyph == "=":
            out += "_3d"
        elif glyph == "_":
            out += "_5f"
        else:
            out += glyph
    return out


def fold_halyard_query(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("the query must be text")
    for glyph in text:
        if ord(glyph) < 0x21 or ord(glyph) > 0x7E:
            raise ValueError("the query carries a glyph outside the visible band")
    if text == "":
        return ""
    flags = set()
    carried = {}
    for parameter in text.split("&"):
        marks = parameter.count("=")
        if marks > 1:
            raise ValueError("a parameter must not carry a second bare equals")
        if marks == 0:
            name = loosen(parameter).lower()
            if name == "":
                raise ValueError("a parameter name must not be empty")
            flags.add(name)
            continue
        cut = parameter.index("=")
        name = loosen(parameter[:cut]).lower()
        if name == "":
            raise ValueError("a parameter name must not be empty")
        value = loosen(parameter[cut + 1:])
        carried.setdefault(name, set()).add(value)
    for name in flags:
        if name in carried:
            raise ValueError("a name cannot stand alone and carry a value too")
    out = []
    for name in sorted(flags):
        out.append(tighten(name))
    for name in sorted(carried):
        values = [tighten(value) for value in sorted(carried[name])]
        out.append(tighten(name) + "=" + ",".join(values))
    return "&".join(out)
