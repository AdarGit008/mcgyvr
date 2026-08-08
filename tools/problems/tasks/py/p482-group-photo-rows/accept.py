from solution import group_photo_rows

SHEET = {"width": 100, "band": 20, "gap": 4}
MIXED = [
    {"tag": "A", "wide": 10, "high": 20},
    {"tag": "B", "wide": 40, "high": 20},
    {"tag": "C", "wide": 20, "high": 20},
    {"tag": "D", "wide": 5, "high": 20},
    {"tag": "E", "wide": 30, "high": 10},
]

assert group_photo_rows(MIXED, SHEET) == [
    {"family": "upright", "tags": ["A", "D"], "run": 19, "spare": 81},
    {"family": "oblong", "tags": ["B"], "run": 40, "spare": 60},
    {"family": "oblong", "tags": ["E"], "run": 60, "spare": 40},
    {"family": "square", "tags": ["C"], "run": 20, "spare": 80},
], "families are laid upright, oblong, square and never share a band"

assert group_photo_rows(
    [
        {"tag": "P", "wide": 10, "high": 10},
        {"tag": "Q", "wide": 10, "high": 10},
        {"tag": "R", "wide": 10, "high": 10},
        {"tag": "S", "wide": 10, "high": 10},
    ],
    {"width": 30, "band": 10, "gap": 0},
) == [
    {"family": "square", "tags": ["P", "Q", "R"], "run": 30, "spare": 0},
    {"family": "square", "tags": ["S"], "run": 10, "spare": 20},
], "a band filled to the width leaves no spare and the next picture opens a band"

assert group_photo_rows(
    [
        {"tag": "F", "wide": 7, "high": 3},
        {"tag": "G", "wide": 3, "high": 7},
    ],
    {"width": 200, "band": 20, "gap": 2},
) == [
    {"family": "upright", "tags": ["G"], "run": 8, "spare": 192},
    {"family": "oblong", "tags": ["F"], "run": 46, "spare": 154},
], "printed widths round down and family order beats arrival order"

assert group_photo_rows(
    [{"tag": "solo", "wide": 4, "high": 8}], {"width": 50, "band": 16, "gap": 3}
) == [
    {"family": "upright", "tags": ["solo"], "run": 8, "spare": 42}
], "one picture makes one band"

ROOMY = group_photo_rows(MIXED, {"width": 300, "band": 20, "gap": 5})
assert len(ROOMY) == 3, "a roomy sheet gives one band per family"
assert [
    "".join(row["tags"]) for row in ROOMY
] == ["AD", "BE", "C"], "each family keeps arrival order on its own band"


def rejects(photos, sheet):
    try:
        group_photo_rows(photos, sheet)
    except ValueError:
        return True
    return False


assert rejects("nope", SHEET), "photos must be a list"
assert rejects([], SHEET), "an empty list is rejected"
assert rejects([7], SHEET), "a photo must be a record"
assert rejects([{"tag": "", "wide": 4, "high": 4}], SHEET), "an empty tag is rejected"
assert rejects(
    [{"tag": "T", "wide": 4, "high": 4}, {"tag": "T", "wide": 5, "high": 5}], SHEET
), "a repeated tag is rejected"
assert rejects([{"tag": "T", "wide": 0, "high": 4}], SHEET), "a side of nought is rejected"
assert rejects(
    [{"tag": "T", "wide": 4, "high": 2.5}], SHEET
), "a fractional side is rejected"
assert rejects([{"tag": "T", "wide": 4, "high": 4}], [100, 20, 4]), "sheet must be a record"
assert rejects(
    [{"tag": "T", "wide": 4, "high": 4}], {"width": 0, "band": 20, "gap": 4}
), "a width of nought is rejected"
assert rejects(
    [{"tag": "T", "wide": 4, "high": 4}], {"width": 100, "band": 20, "gap": -1}
), "a negative gap is rejected"
assert rejects(
    [{"tag": "T", "wide": 1, "high": 30}], SHEET
), "a picture printing to nothing is rejected"
assert rejects(
    [{"tag": "T", "wide": 200, "high": 20}], SHEET
), "a picture wider than the sheet is rejected"
print("ok")
