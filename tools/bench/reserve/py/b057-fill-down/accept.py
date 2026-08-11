from solution import blank_cells, fill_down

assert fill_down([["x"], [""], [""]]) == [
    ["x"],
    ["x"],
    ["x"],
], "a run of blanks all inherit the value above the run"
assert fill_down([["a"], [""], ["b"], [""]]) == [
    ["a"],
    ["a"],
    ["b"],
    ["b"],
], "a fresh value resets what later blanks inherit"
assert fill_down([["a", "1"], ["", ""], ["c", ""]]) == [
    ["a", "1"],
    ["a", "1"],
    ["c", "1"],
], "columns fill independently"
assert fill_down([]) == [], "an empty grid stays empty"
grid = [["k"], [""]]
fill_down(grid)
assert grid == [["k"], [""]], "the input grid is left unmodified"
assert blank_cells([["", ""], ["a", ""]]) == 3, "blank_cells counts the blanks"


def rejects(rows):
    try:
        fill_down(rows)
    except ValueError:
        return True
    return False


assert rejects([["a", "b"], ["c"]]), "ragged rows are rejected"
assert rejects([[""]]), "a top blank with nothing above is rejected"
print("ok")
