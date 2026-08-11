from solution import thaw_row

assert thaw_row("###", 0) == "###", "zero steps returns the row unchanged"
assert thaw_row("###", 1) == ".#.", "both ends melt in one step"
assert thaw_row("###", 2) == "...", "the core goes on the second step"
assert thaw_row("#####", 1) == ".###.", "only the exposed ends melt"
assert thaw_row("##.##", 1) == ".....", "a water pocket melts both of its walls"
assert thaw_row("...", 4) == "...", "meltwater never refreezes"
assert thaw_row("#", 1) == ".", "a lone ice cell melts at once"


def rejects(row, steps):
    try:
        thaw_row(row, steps)
    except ValueError:
        return True
    return False


assert rejects(42, 1), "a non-string row is rejected"
assert rejects("", 1), "an empty row is rejected"
assert rejects("#x#", 1), "a stray character is rejected"
assert rejects("##", 1.5), "a fractional step count is rejected"
print("ok")
