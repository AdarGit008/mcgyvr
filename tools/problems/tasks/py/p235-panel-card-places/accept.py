from solution import place_cards

panel = {
    "width": 100,
    "height": 60,
    "bleed": 5,
    "cardWidth": 20,
    "cardHeight": 10,
    "seam": 5,
}
tight = {
    "width": 60,
    "height": 20,
    "bleed": 0,
    "cardWidth": 20,
    "cardHeight": 10,
    "seam": 0,
}


def rejects(sheet, count, taken):
    try:
        place_cards(sheet, count, taken)
    except ValueError:
        return True
    return False


assert place_cards(panel, 0, []) == [], "asking for none lays none"
assert place_cards(panel, 4, []) == [[5, 5], [30, 5], [55, 5], [5, 20]], (
    "reading order wraps to the row beneath after the last column"
)
assert place_cards(panel, 2, [1, 3]) == [[30, 5], [5, 20]], (
    "spoken-for cells are stepped over"
)
assert place_cards(panel, 1, [9, 9, 2, 2]) == [[5, 5]], (
    "a cell named twice is still one cell"
)
assert place_cards(panel, 8, [5])[7] == [55, 35], (
    "the bottom-right cell sits a full grid from the bleed"
)
assert len(place_cards(panel, 9, [])) == 9, "the grid here holds nine"
assert place_cards(tight, 5, []) == [
    [0, 0],
    [20, 0],
    [40, 0],
    [0, 10],
    [20, 10],
], "no bleed and no seam puts the first corner at the origin"

assert rejects(panel, 9, [5]), "one cell spoken for leaves too few for nine"
assert rejects(panel, 1, [10]), "a cell number past the grid is rejected"
assert rejects(panel, 1, [0]), "cells are numbered from one, so zero is rejected"
assert rejects(
    {"width": 10, "height": 10, "bleed": 1, "cardWidth": 20, "cardHeight": 5, "seam": 0},
    1,
    [],
), "a panel too small for a single card is refused"
assert rejects(panel, -1, []), "a negative count is rejected"
assert rejects({**panel, "seam": -2}, 1, []), "a negative seam is rejected"
print("ok")
