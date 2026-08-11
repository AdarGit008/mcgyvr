from solution import run_index


def rejects(entries, value, nth):
    try:
        run_index(entries, value, nth)
    except Exception:
        return True
    return False


assert run_index(["a", "b", "a"], "a", 2) == 2, "the second appearance"
assert run_index(["a", "b", "a"], "a", 1) == 0, "the first appearance"
assert run_index(["a", "b", "a"], "a", 3) == -1, "it never appears that often"
assert run_index([], "a", 1) == -1, "an empty list"
assert run_index(["a"], "b", 1) == -1, "the value is absent"
assert rejects(["a"], "a", 0), "a count of zero is rejected"
print("ok")
