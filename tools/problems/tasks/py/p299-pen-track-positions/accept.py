from solution import pen_track_positions

font = {
    "advances": {"T": 6, "o": 5, "e": 5, ".": 3, "A": 7, "V": 7, "i": 1},
    "groups": {"round": "oe", "cap": "TAV"},
    "pairs": [
        ["T", "{round}", -2],
        ["{cap}", "{round}", -1],
        ["o", ".", -3],
    ],
}

bare = {"advances": {"A": 1, "B": 1}, "groups": {}, "pairs": []}


def rejects(text, face):
    try:
        pen_track_positions(text, face)
    except ValueError:
        return True
    return False


assert pen_track_positions("", font) == {"positions": [], "total": 0}, (
    "an empty text lays no glyph"
)
assert pen_track_positions("A", font) == {"positions": [0], "total": 7}, (
    "one glyph sits at pen zero"
)
assert pen_track_positions("To", font) == {"positions": [0, 4], "total": 9}, (
    "two rows fit T beside o and only the topmost is granted"
)
assert pen_track_positions("Toe.", font) == {
    "positions": [0, 4, 9, 14],
    "total": 17,
}, "one shift among three pairs moves every pen after it"
assert pen_track_positions("Ao", font) == {"positions": [0, 6], "total": 11}, (
    "a row with a group on both sides fits A beside o"
)
assert pen_track_positions("Ae", font) == {"positions": [0, 6], "total": 11}, (
    "the round group holds e as well as o"
)
assert pen_track_positions("o.", font) == {"positions": [0, 2], "total": 5}, (
    "a row of two plain glyphs still fits"
)
assert pen_track_positions("oo", font) == {"positions": [0, 5], "total": 10}, (
    "no row fits o beside o, so the pen only advances"
)
assert pen_track_positions("VVo", font) == {"positions": [0, 7, 13], "total": 18}, (
    "the group row fits the second V beside o but not V beside V"
)

assert rejects(5, font), "a text is a string"
assert rejects("A", "font"), "a font is an object"
assert rejects("A", {"advances": [], "groups": {}, "pairs": []}), (
    "advances is a plain mapping"
)
assert rejects("A", {"advances": {"A": -1}, "groups": {}, "pairs": []}), (
    "an advance is never negative"
)
assert rejects("A", {"advances": {"A": 1}, "groups": {"cap": 5}, "pairs": []}), (
    "a group holds a string"
)
assert rejects("A", {"advances": {"A": 1}, "groups": {}, "pairs": "x"}), (
    "pairs is a list"
)
assert rejects("A", {"advances": {"A": 1}, "groups": {}, "pairs": [["A", "A"]]}), (
    "a row carries a shift as well"
)
assert rejects("A", {**bare, "pairs": [["{tall}", "A", 1]]}), (
    "no group is named tall"
)
assert rejects("A", {**bare, "pairs": [["AB", "A", 1]]}), (
    "a side of two plain glyphs is no side"
)
assert rejects("A", {**bare, "pairs": [["A", "A", 0.5]]}), "a shift is whole"
assert rejects("Z", font), "Z has no advance"
assert rejects(
    "ii", {"advances": {"i": 1}, "groups": {}, "pairs": [["i", "i", -5]]}
), "the pen may not fall below zero"
print("ok")
