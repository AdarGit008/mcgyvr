from solution import step_allowed, step_plan

MOVES = [["a", "b"], ["b", "c"]]


def rejects(states, allowed):
    try:
        step_plan(states, allowed)
    except Exception:
        return True
    return False


assert step_allowed("a", "b", MOVES) is True, "a listed move"
assert step_allowed("a", "c", MOVES) is False, "an unlisted move"
assert step_plan(["a", "b", "c"], MOVES) == -1, "every move is allowed"
assert step_plan(["a", "c"], MOVES) == 1, "the first move is not allowed"
assert step_plan(["a"], MOVES) == -1, "one state makes no move"
assert rejects([], MOVES), "an empty run is rejected"
print("ok")
