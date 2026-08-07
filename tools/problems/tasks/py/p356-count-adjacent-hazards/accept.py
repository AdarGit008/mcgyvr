from solution import count_adjacent_hazards

assert count_adjacent_hazards(["#..", "...", "..#"]) == {
    "chart": ["#10", "121", "01#"],
    "hazards": 2,
    "clear": 7,
}, "the stated three-row field"
assert count_adjacent_hazards(["...", "..."]) == {
    "chart": ["000", "000"],
    "hazards": 0,
    "clear": 6,
}, "a field with nothing in it"
assert count_adjacent_hazards(["##", "##"]) == {
    "chart": ["##", "##"],
    "hazards": 4,
    "clear": 0,
}, "a field of nothing but hazards"
assert count_adjacent_hazards(["#"]) == {
    "chart": ["#"],
    "hazards": 1,
    "clear": 0,
}, "one square holding a hazard"
assert count_adjacent_hazards(["."]) == {
    "chart": ["0"],
    "hazards": 0,
    "clear": 1,
}, "one square holding nothing"
assert count_adjacent_hazards(["#.#.#"]) == {
    "chart": ["#2#2#"],
    "hazards": 3,
    "clear": 2,
}, "a single row counts on both hands"
assert count_adjacent_hazards([".#.", "#.#", ".#."]) == {
    "chart": ["2#2", "#4#", "2#2"],
    "hazards": 4,
    "clear": 5,
}, "the middle square touches four hazards"


def rejects(field):
    try:
        count_adjacent_hazards(field)
    except ValueError:
        return True
    return False


assert rejects("#.."), "a field that is not a list is thrown out"
assert rejects([]), "a field with no rows is thrown out"
assert rejects([["#", "."]]), "a row that is not a string is thrown out"
assert rejects(["#.", ""]), "an empty row is thrown out"
assert rejects(["#..", ".."]), "rows of unequal length are thrown out"
assert rejects(["#.x"]), "a symbol outside hash and dot is thrown out"
print("ok")
