from solution import run_buffered_line

assert run_buffered_line([5, 3], [4], 3) == {
    "made": 6,
    "left": [4],
}, "two stations: warm-up tick then steady flow of 3"
assert run_buffered_line([2, 5, 1], [3, 2], 4) == {
    "made": 2,
    "left": [3, 2],
}, "three stations: the slow tail backs the line up"
assert run_buffered_line([1, 1], [1], 3) == {
    "made": 2,
    "left": [1],
}, "downstream-first order: a piece needs a full tick per hop"
assert run_buffered_line([10, 1], [2], 4) == {
    "made": 3,
    "left": [2],
}, "a full buffer blocks the eager upstream station"
assert run_buffered_line([4], [], 3) == {
    "made": 12,
    "left": [],
}, "a single station just streams stock to the bin"
assert run_buffered_line([3, 3], [5], 0) == {
    "made": 0,
    "left": [0],
}, "zero ticks moves nothing"


def rejects(*args):
    try:
        run_buffered_line(*args)
    except ValueError:
        return True
    return False


assert rejects([], [], 2), "empty line is rejected"
assert rejects([2, 2], [], 2), "missing buffer is rejected"
assert rejects([2, 0], [1], 2), "zero per-tick limit is rejected"
assert rejects([2, 2], [1.5], 2), "fractional buffer size is rejected"
assert rejects([2, 2], [1], -1), "negative tick count is rejected"
print("ok")
