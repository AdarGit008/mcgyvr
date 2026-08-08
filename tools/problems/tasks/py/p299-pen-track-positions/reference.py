import re

BRACED = re.compile(r"\{(.+)\}")


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def pen_track_positions(text: str, font: dict) -> dict:
    if not isinstance(text, str):
        raise ValueError("pen_track_positions expects a string of glyphs")
    if not isinstance(font, dict):
        raise ValueError("the font must be an object")
    advances = font.get("advances")
    groups = font.get("groups")
    pairs = font.get("pairs")
    if not isinstance(advances, dict) or not isinstance(groups, dict):
        raise ValueError("advances and groups must be plain mappings")
    for glyph, advance in advances.items():
        if not _whole(advance) or advance < 0:
            raise ValueError(f"an advance is a whole number of zero or more: {glyph}")
    for name, held in groups.items():
        if not isinstance(held, str):
            raise ValueError(f"a group holds a string of glyphs: {name}")
    if not isinstance(pairs, list):
        raise ValueError("pairs must be a table list")

    def check_side(side) -> None:
        if not isinstance(side, str):
            raise ValueError("a side is written as text")
        if len(side) == 1:
            return
        braced = BRACED.fullmatch(side)
        if braced is None or braced.group(1) not in groups:
            raise ValueError(
                f"a side is one glyph or braces around a known group: {side}"
            )

    for row in pairs:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError("a row is two sides and a shift")
        check_side(row[0])
        check_side(row[1])
        if not _whole(row[2]):
            raise ValueError("a shift is a whole number")

    def fits(side: str, glyph: str) -> bool:
        if len(side) == 1:
            return side == glyph
        return glyph in groups[BRACED.fullmatch(side).group(1)]

    def shift_for(left: str, right: str) -> int:
        for row in pairs:
            if fits(row[0], left) and fits(row[1], right):
                return row[2]
        return 0

    for glyph in text:
        if glyph not in advances:
            raise ValueError(f"no advance for {glyph}")

    positions: list[int] = []
    pen = 0
    for at, glyph in enumerate(text):
        if at > 0:
            pen += advances[text[at - 1]] + shift_for(text[at - 1], glyph)
        if pen < 0:
            raise ValueError(f"the pen falls below zero at glyph {at}")
        positions.append(pen)
    total = 0 if text == "" else pen + advances[text[-1]]
    if total < 0:
        raise ValueError("the total falls below zero")
    return {"positions": positions, "total": total}
