GLYPHS = "KLMNPQRST"


def tessari_value(text: str) -> int:
    if not isinstance(text, str):
        raise ValueError("tessari_value expects text")
    if len(text) == 0:
        raise ValueError("a numeral needs at least one glyph")
    total = 0
    for glyph in text:
        place = GLYPHS.find(glyph)
        if place < 0:
            raise ValueError(f"{glyph} is not a Tessari glyph")
        total = total * 9 + place
    if len(text) > 1 and text[0] == "K":
        raise ValueError("a long numeral never opens with K")
    return total
