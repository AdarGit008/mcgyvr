from solution import slot_fill


def rejects(labels, slots):
    try:
        slot_fill(labels, slots)
    except Exception:
        return True
    return False


assert slot_fill(["a"], 3) == ["a", "", ""], "the spare slots stay empty"
assert slot_fill(["a", "b"], 2) == ["a", "b"], "the board is exactly filled"
assert slot_fill(["a", "b", "c"], 2) == ["a", "b"], "the spare label is left off"
assert slot_fill([], 2) == ["", ""], "an empty board of two slots"
assert slot_fill(["a"], 1) == ["a"], "one slot, one label"
assert rejects([""], 2), "an empty label is rejected"
print("ok")
