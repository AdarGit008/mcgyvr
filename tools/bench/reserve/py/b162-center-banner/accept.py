from solution import center_banner

assert center_banner("OPEN", 10, " ") == "   OPEN   ", "even spare cells split in half"
assert center_banner("OPEN", 11, ".") == "...OPEN....", "the odd spare cell goes right"
assert center_banner("EXIT", 4, "*") == "EXIT", "an exact fit needs no fill"
assert center_banner("", 3, "-") == "---", "an empty label yields fill alone"
assert center_banner("x", 2, "_") == "x_", "a single spare cell goes right"
assert center_banner("no vacancy", 12, " ") == " no vacancy ", "inner spaces belong to the label"


def rejects(*args):
    try:
        center_banner(*args)
    except Exception:
        return True
    return False


assert rejects(7, 5, " "), "a non-string label is rejected"
assert rejects("a\nb", 9, " "), "a label holding a newline is rejected"
assert rejects("hi", 0, " "), "a zero width is rejected"
assert rejects("overflow", 3, " "), "a label wider than the board is rejected"
assert rejects("hi", 6, "--"), "a two-character fill is rejected"
print("ok")
