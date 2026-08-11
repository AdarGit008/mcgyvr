from solution import run_press

assert run_press([["flyer", 2], ["poster", 3]], 10) == {"printed": ["flyer", "poster"], "waiting": [], "pages": 5}, "a queue that fits prints whole"
assert run_press([["memo", 4], ["book", 5], ["card", 1]], 6) == {"printed": ["memo"], "waiting": ["book", "card"], "pages": 4}, "the first misfit stops serving even when a later job would fit"
assert run_press([["memo", 3], ["card", 3]], 6) == {"printed": ["memo", "card"], "waiting": [], "pages": 6}, "an exact fit spends the whole budget"
assert run_press([["book", 7]], 6) == {"printed": [], "waiting": ["book"], "pages": 0}, "a first job too big prints nothing"
assert run_press([["card", 1]], 0) == {"printed": [], "waiting": ["card"], "pages": 0}, "a zero budget serves nobody"
assert run_press([], 4) == {"printed": [], "waiting": [], "pages": 0}, "an empty queue spends nothing"


def rejects(*args):
    try:
        run_press(*args)
    except ValueError:
        return True
    return False


assert rejects(42, 5), "a non-list queue is rejected"
assert rejects([["solo"]], 5), "a job that is not a pair is rejected"
assert rejects([["", 2]], 5), "an empty job name is rejected"
assert rejects([["big", 9], ["late", 0]], 5), "a bad page count is rejected even past the stopping point"
assert rejects([["card", 1]], -1), "a negative budget is rejected"
print("ok")
