from solution import sift_down_run

assert sift_down_run([9, 2, 4, 5, 3, 7, 6], 0) == [
    [2, 3, 4, 5, 9, 7, 6],
    [0, 1, 4],
], "sinks two levels"
assert sift_down_run([1, 2, 3], 0) == [[1, 2, 3], [0]], "already settled"
assert sift_down_run([5, 3, 3], 0) == [[3, 5, 3], [0, 1]], "tie takes the left"
assert sift_down_run([8, 9, 1, 10, 11], 0) == [
    [1, 9, 8, 10, 11],
    [0, 2],
], "smaller right child wins"
assert sift_down_run([1, 4, 3, 7], 3) == [[1, 4, 3, 7], [3]], "leaf start"
assert sift_down_run([0, 9, 2, 3, 4, 5, 6, 7, 8], 1) == [
    [0, 3, 2, 7, 4, 5, 6, 9, 8],
    [1, 3, 7],
], "start below the root"
assert sift_down_run([5, 1], 0) == [[1, 5], [0, 1]], "only a left child"
assert sift_down_run([3, -1, -2], 0) == [[-2, -1, 3], [0, 2]], "negatives"
assert sift_down_run([7], 0) == [[7], [0]], "lone slot"

caller = [9, 2, 4]
sift_down_run(caller, 0)
assert caller == [9, 2, 4], "caller's array untouched"


def rejects(heap, start):
    try:
        sift_down_run(heap, start)
    except ValueError:
        return True
    return False


assert rejects([], 0), "empty array rejected"
assert rejects([1, 2], -1), "negative start rejected"
assert rejects([1, 2], 2), "start past the end rejected"
assert rejects([1, 2.5], 0), "fraction entry rejected"
assert rejects([1, 2], 0.5), "fractional start rejected"
print("ok")
