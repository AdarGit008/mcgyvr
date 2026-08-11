from solution import render_tabbed

assert render_tabbed("total", [[8, "left"]]) == "total", "no tabs, no change"
assert render_tabbed("id\tname", [[6, "left"]]) == "id    name", "a left stop pads to its column"
assert render_tabbed("a\tbb\tccc", [[4, "left"], [10, "left"]]) == "a   bb    ccc", (
    "successive pieces take successive stops"
)
assert render_tabbed("item\t42", [[9, "right"]]) == "item   42", (
    "a right stop ends the piece at its column"
)
assert render_tabbed("lineup\t88", [[4, "left"], [12, "right"]]) == "lineup    88", (
    "a stop already passed is skipped over"
)
assert render_tabbed("ledger\t123456", [[8, "right"]]) == "ledger 123456", (
    "a right piece too wide falls back to one space"
)
assert render_tabbed("totals\tdue", [[4, "left"]]) == "totals due", (
    "no stop left falls back to one space"
)
assert render_tabbed("a\t\tb", [[3, "left"], [6, "left"]]) == "a     b", "an empty piece still advances"
assert render_tabbed("\ttitle", [[5, "left"]]) == "     title", "a leading tab indents the first piece"
assert render_tabbed("", []) == "", "an empty line stays empty"


def rejects(line, stops):
    try:
        render_tabbed(line, stops)
    except ValueError:
        return True
    return False


assert rejects(42, []), "a non-string line is rejected"
assert rejects("a\nb", []), "a newline in the line is rejected"
assert rejects("a", "nope"), "non-list stops are rejected"
assert rejects("a", [[4]]), "a one-item stop is rejected"
assert rejects("a", [[0, "left"]]), "a zero column is rejected"
assert rejects("a", [[4, "center"]]), "an unknown kind is rejected"
assert rejects("a", [[6, "left"], [4, "right"]]), "non-increasing columns are rejected"
print("ok")
