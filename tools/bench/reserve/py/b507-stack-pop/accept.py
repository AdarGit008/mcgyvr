from solution import stack_pop


def rejects(orders):
    try:
        stack_pop(orders)
    except Exception:
        return True
    return False


assert stack_pop(["a", "b", "take"]) == ["a"], "the last on comes off first"
assert stack_pop(["a", "b"]) == ["a", "b"], "orders that only put on"
assert stack_pop(["a", "take", "b"]) == ["b"], "taking then putting on again"
assert stack_pop(["a", "take"]) == [], "the pile is emptied"
assert stack_pop([]) == [], "no orders at all"
assert rejects(["take"]), "taking from an empty pile is rejected"
assert rejects(["a", "take", "take"]), "taking one time too many is rejected"
print("ok")
