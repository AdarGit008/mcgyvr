from solution import free_windows

assert free_windows(9, 17, []) == [[9, 17]], "untouched window is one gap"
assert free_windows(9, 17, [[12, 13]]) == [
    [9, 12],
    [13, 17],
], "one busy interval splits the window"
assert free_windows(0, 100, [[50, 60], [10, 30], [25, 40]]) == [
    [0, 10],
    [40, 50],
    [60, 100],
], "unsorted and overlapping busy intervals"
assert free_windows(10, 20, [[0, 12], [18, 25]]) == [
    [12, 18]
], "busy intervals are clipped to the window"
assert free_windows(10, 20, [[0, 5], [30, 40]]) == [
    [10, 20]
], "busy intervals wholly outside are ignored"
assert free_windows(0, 10, [[0, 10]]) == [], "fully booked window"
assert free_windows(0, 10, [[2, 8], [3, 4]]) == [
    [0, 2],
    [8, 10],
], "a contained interval adds no gap"
assert free_windows(0, 10, [[2, 4], [4, 6]]) == [
    [0, 2],
    [6, 10],
], "touching busy intervals leave no gap between them"


def rejects(*args):
    try:
        free_windows(*args)
    except ValueError:
        return True
    return False


assert rejects(7, 7, []), "empty window is rejected"
assert rejects(5, 3, []), "reversed window is rejected"
assert rejects(0, 10, [[4, 2]]), "reversed busy interval is rejected"
assert rejects(0, 10, [[1, 2.5]]), "fractional endpoint is rejected"
print("ok")
