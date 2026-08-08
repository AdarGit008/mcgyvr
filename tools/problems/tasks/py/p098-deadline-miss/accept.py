from solution import first_deadline_miss

assert first_deadline_miss(
    [{"name": "A", "work": 3, "due": 5}, {"name": "B", "work": 2, "due": 9}]
) == "", "a fitting plan misses nothing"
assert first_deadline_miss(
    [{"name": "B", "work": 4, "due": 10}, {"name": "A", "work": 2, "due": 2}]
) == "", "the earliest due minute runs first, whatever the list order"
assert first_deadline_miss(
    [{"name": "A", "work": 3, "due": 2}]
) == "A", "one overloaded job misses"
assert first_deadline_miss(
    [
        {"name": "A", "work": 5, "due": 5},
        {"name": "B", "work": 1, "due": 5},
        {"name": "C", "work": 1, "due": 6},
    ]
) == "B", "on a due tie the earlier-listed job runs first, and the miss is found in running order"
assert first_deadline_miss(
    [{"name": "A", "work": 2, "due": 4}, {"name": "B", "work": 5, "due": 6}]
) == "B", "the miss need not be the first job run"
assert first_deadline_miss([]) == "", "an empty list is on time"


def rejects(jobs):
    try:
        first_deadline_miss(jobs)
    except ValueError:
        return True
    return False


assert rejects([{"name": "A", "work": 0, "due": 3}]), "work 0 is rejected"
assert rejects([{"name": "A", "work": 2, "due": 0}]), "due 0 is rejected"
assert rejects([{"name": "A", "work": 1.5, "due": 3}]), "fractional work is rejected"
assert rejects(
    [{"name": "A", "work": 1, "due": 3}, {"name": "A", "work": 2, "due": 4}]
), "a repeated name is rejected"
assert rejects([{"name": 5, "work": 1, "due": 3}]), "a non-string name is rejected"
print("ok")
