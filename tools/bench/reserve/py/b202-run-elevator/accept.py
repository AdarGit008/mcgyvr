from solution import run_elevator

assert run_elevator(6, [[0, 4], [0, 2]]) == {"stops": [2, 4], "travel": 3}, "the nearer floor going up is served first"
assert run_elevator(6, [[0, 5], [0, 3], [6, 1]]) == {"stops": [3, 5, 1], "travel": 8}, "the lift waits idle and then turns for a late call"
assert run_elevator(6, [[0, 3], [0, 3]]) == {"stops": [3, 3], "travel": 2}, "two calls for one floor are two stops"
assert run_elevator(8, [[0, 6], [2, 4]]) == {"stops": [4, 6], "travel": 5}, "a call pressed ahead of the lift is picked up in passing"
assert run_elevator(4, [[0, 1]]) == {"stops": [1], "travel": 0}, "a call for the starting floor costs no travel"


def rejects(*args):
    try:
        run_elevator(*args)
    except Exception:
        return True
    return False


assert rejects(4, [[0, 5]]), "a call above the top floor is rejected"
print("ok")
