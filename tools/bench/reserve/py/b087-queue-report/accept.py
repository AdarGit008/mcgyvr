from solution import queue_report

assert queue_report([]) == {"waited": 0, "longest": 0, "idle": 0}, "empty list is all zeroes"
assert queue_report([[5, 3]]) == {"waited": 0, "longest": 0, "idle": 5}, (
    "opening gap counts as idle"
)
assert queue_report([[0, 2], [2, 2]]) == {"waited": 0, "longest": 0, "idle": 0}, (
    "back-to-back orders never idle"
)
assert queue_report([[0, 4], [1, 2], [2, 1]]) == {"waited": 7, "longest": 4, "idle": 0}, (
    "a backlog accumulates waits"
)
assert queue_report([[0, 2], [5, 1]]) == {"waited": 0, "longest": 0, "idle": 3}, (
    "a lull between orders is idle"
)
assert queue_report([[3, 2], [3, 2]]) == {"waited": 2, "longest": 2, "idle": 3}, (
    "same-minute orders queue up"
)
assert queue_report([[1, 3], [2, 1], [9, 2]]) == {"waited": 2, "longest": 2, "idle": 5}, (
    "waits and idle in one run"
)


def rejects(value):
    try:
        queue_report(value)
    except Exception:
        return True
    return False


assert rejects(42), "non-list is rejected"
assert rejects([[1]]), "a lone minute is rejected"
assert rejects([[-1, 2]]), "negative placement is rejected"
assert rejects([[0, 0]]), "zero hand-over is rejected"
assert rejects([[4, 1], [2, 1]]), "decreasing placement is rejected"
print("ok")
