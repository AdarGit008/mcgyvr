from solution import pair_columns

assert pair_columns(["ab", "c"], ["1", "2"], 2) == ["ab  1", "c   2"], "the left block is padded to its widest line"
assert pair_columns(["ab", "c"], ["1"], 1) == ["ab 1", "c"], "a row past the right block keeps only the left text"
assert pair_columns(["ab"], ["1", "2"], 1) == ["ab 1", "   2"], "a row past the left block keeps the full padding"
assert pair_columns(["ab", "c"], ["1", "2"], 0) == ["ab1", "c 2"], "a gap of zero butts the blocks together"
assert pair_columns([], ["x"], 3) == ["   x"], "an absent left block leaves the gap alone"
assert pair_columns([], [], 4) == [], "two empty blocks give no lines"
assert pair_columns(["long", ""], ["1", ""], 2) == ["long  1", ""], "a row empty on both sides comes out empty"


def rejects(*args):
    try:
        pair_columns(*args)
    except ValueError:
        return True
    return False


assert rejects(["a"], ["b"], -1), "a negative gap is rejected"
print("ok")
