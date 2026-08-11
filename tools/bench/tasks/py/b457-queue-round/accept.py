from solution import served_by, queue_round


def rejects(queue, turns):
    try:
        queue_round(queue, turns)
    except Exception:
        return True
    return False


assert served_by(["a", "b"], 0) == "a", "the first turn"
assert served_by(["a", "b"], 2) == "a", "the queue comes round"
assert queue_round(["a", "b"], 3) == ["a", "b", "a"], "past the end and round"
assert queue_round(["a", "b"], 2) == ["a", "b"], "exactly one pass"
assert queue_round(["a"], 0) == [], "no turns at all"
assert rejects([], 1), "an empty queue is rejected"
print("ok")
