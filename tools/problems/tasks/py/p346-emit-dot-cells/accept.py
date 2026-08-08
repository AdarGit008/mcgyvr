from solution import emit_dot_cells


def rejects(value):
    try:
        emit_dot_cells(value)
    except ValueError:
        return True
    return False


assert emit_dot_cells("abc") == "1-12-14", "the first three patterns"
assert emit_dot_cells("ij") == "24-245", "the ninth and tenth patterns"
assert emit_dot_cells("klm") == "13-123-134", "dot 3 added, kept in order"
assert emit_dot_cells("qt") == "12345-2345", "later members of the second ten"
assert emit_dot_cells("w") == "2456", "w stands apart"
assert emit_dot_cells("uvxyz") == "136-1236-1346-13456-1356", "dots 3 and 6 added"
assert emit_dot_cells("Ab") == "6-1-12", "a capital carries its own cell first"
assert emit_dot_cells("Za") == "6-1356-1", "a capital late in the alphabet"
assert emit_dot_cells("a b") == "1-0-12", "a space is the empty frame"
assert emit_dot_cells(" ") == "0", "a lone space"
assert emit_dot_cells("12") == "3456-1-12", "one opener for a run of two digits"
assert emit_dot_cells("90") == "3456-24-245", "nine and zero"
assert emit_dot_cells("a1b") == "1-3456-1-12", "a letter closes the run"
assert emit_dot_cells("1 2") == "3456-1-0-3456-12", "a space closes the run"

assert rejects(42), "not a string"
assert rejects(""), "empty argument"
assert rejects("a-b"), "a hyphen cannot be rendered"
assert rejects("a_b"), "an underscore cannot be rendered"
assert rejects("a  b"), "two spaces side by side"
print("ok")
