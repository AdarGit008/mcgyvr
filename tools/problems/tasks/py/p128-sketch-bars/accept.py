from solution import sketch_bars

assert sketch_bars([10, 5, 0], 4) == ["####", "##..", "...."], (
    "largest fills the budget, zero draws nothing"
)
assert sketch_bars([3, 1], 4) == ["####", "#..."], "1.33 cells rounds down to one"
assert sketch_bars([4, 1], 2) == ["##", "#."], "a half cell rounds upward"
assert sketch_bars([100, 1], 5) == ["#####", "#...."], "a nonzero value never vanishes"
assert sketch_bars([0, 0], 3) == ["...", "..."], "all zeros are all dots"
assert sketch_bars([2], 1) == ["#"], "budget of one"
assert sketch_bars([7, 6, 2], 10) == ["##########", "#########.", "###......."], (
    "proportions over a wider budget"
)


def rejects(readings, budget):
    try:
        sketch_bars(readings, budget)
    except ValueError:
        return True
    return False


assert rejects([], 4), "empty value list is rejected"
assert rejects([1, 2], 0), "budget below one is rejected"
assert rejects([3, -1], 4), "negative value is rejected"
print("ok")
