HEX = "0123456789ABCDEF"


def unwrap(chunk):
    out = ""
    at = 0
    while at < len(chunk):
        glyph = chunk[at]
        if glyph != "~":
            out += glyph
            at += 1
            continue
        if at + 2 >= len(chunk):
            raise ValueError("a tilde must be followed by two hex glyphs")
        high = chunk[at + 1]
        low = chunk[at + 2]
        if high not in HEX or low not in HEX:
            raise ValueError("a tilde must be followed by two upper-case hex glyphs")
        code = HEX.index(high) * 16 + HEX.index(low)
        if code < 0x20 or code > 0x7E:
            raise ValueError("an escape must name a printable glyph")
        out += chr(code)
        at += 3
    return out


def wrap(text):
    out = ""
    for glyph in text:
        if glyph == ":":
            out += "~3A"
        elif glyph == ";":
            out += "~3B"
        elif glyph == "~":
            out += "~7E"
        else:
            out += glyph
    return out


def canonical_tag_query(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("the query must be text")
    for glyph in text:
        if ord(glyph) < 0x20 or ord(glyph) > 0x7E:
            raise ValueError("the query carries a glyph outside the printable band")
    if text == "":
        return ""
    pairs = []
    for item in text.split(";"):
        colons = item.count(":")
        if colons == 0:
            raise ValueError("every item must carry a colon")
        if colons > 1:
            raise ValueError("an item must not carry a second bare colon")
        cut = item.index(":")
        key = unwrap(item[:cut])
        value = unwrap(item[cut + 1:])
        if key == "":
            raise ValueError("an item key must not be empty")
        pairs.append((key, value))
    pairs.sort()
    kept = []
    for at, pair in enumerate(pairs):
        if at > 0 and pair == pairs[at - 1]:
            continue
        kept.append(wrap(pair[0]) + ":" + wrap(pair[1]))
    return ";".join(kept)
