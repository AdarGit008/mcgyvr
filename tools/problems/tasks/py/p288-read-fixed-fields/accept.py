from solution import read_fixed_fields

LAYOUT = [
    {"name": "code", "start": 1, "width": 4},
    {"name": "town", "start": 5, "width": 8},
    {"name": "note", "start": 13, "width": 6},
]

assert read_fixed_fields(["AB12Harwell early "], LAYOUT) == [
    {"code": "AB12", "town": "Harwell", "note": "early"}
], "three values packed out with spaces"
assert read_fixed_fields([" X9 Ely     "], LAYOUT) == [
    {"code": " X9", "town": "Ely", "note": ""}
], "a leading space survives, a short line supplies spaces"
assert read_fixed_fields([""], LAYOUT) == [
    {"code": "", "town": "", "note": ""}
], "an empty line yields empty values throughout"
assert read_fixed_fields(["    Harwell       "], LAYOUT) == [
    {"code": "", "town": "Harwell", "note": ""}
], "a run of nothing but spaces is the empty value"
assert read_fixed_fields(
    ["AB12Harwell early ", " X9 Ely     ", "ZZ99Rye     late  "], LAYOUT
) == [
    {"code": "AB12", "town": "Harwell", "note": "early"},
    {"code": " X9", "town": "Ely", "note": ""},
    {"code": "ZZ99", "town": "Rye", "note": "late"},
], "one record per line, in line order"
assert read_fixed_fields([], LAYOUT) == [], "no lines, no records"
assert read_fixed_fields(["one  two"], [{"name": "tail", "start": 6, "width": 3}]) == [
    {"tail": "two"}
], "a layout may begin part way along the line"
assert read_fixed_fields(["  a  "], [{"name": "only", "start": 1, "width": 5}]) == [
    {"only": "  a"}
], "spaces inside and before a value are kept"


def rejects(lines, layout):
    try:
        read_fixed_fields(lines, layout)
    except ValueError:
        return True
    return False


assert rejects(["x"], []), "an empty layout"
assert rejects(
    ["x"],
    [{"name": "a", "start": 1, "width": 2}, {"name": "a", "start": 3, "width": 2}],
), "repeated field name"
assert rejects(
    ["x"],
    [{"name": "a", "start": 1, "width": 4}, {"name": "b", "start": 3, "width": 2}],
), "two fields over one column"
assert rejects(["x"], [{"name": "a", "start": 0, "width": 2}]), (
    "a start left of the first column"
)
assert rejects(["x"], [{"name": "a", "start": 1, "width": 0}]), "a width of no columns"
assert rejects(["a\tb"], LAYOUT), "a tab on the grid"
assert rejects([5], LAYOUT), "a line that is not a string"
assert rejects("AB12", LAYOUT), "lines is not a list"
print("ok")
