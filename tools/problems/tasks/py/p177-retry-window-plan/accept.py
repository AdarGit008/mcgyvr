from solution import plan_retry_window


def policy(base, factor, ceiling, tries, deadline):
    return {
        "base": base,
        "factor": factor,
        "ceiling": ceiling,
        "tries": tries,
        "deadline": deadline,
    }


assert plan_retry_window(policy(10, 2, 100, 5, 1000), ["won"]) == {
    "times": [0],
    "verdict": "succeeded",
}, "an opening win closes the plan at moment zero"
assert plan_retry_window(
    policy(10, 2, 100, 4, 1000), ["lost", "lost", "lost", "lost"]
) == {
    "times": [0, 10, 30, 70],
    "verdict": "exhausted",
}, "the allowance runs out after the fourth attempt is read"
assert plan_retry_window(
    policy(10, 2, 100, 9, 50), ["lost", "lost", "lost", "lost", "lost"]
) == {
    "times": [0, 10, 30],
    "verdict": "expired",
}, "an attempt pencilled past the deadline never happens"
assert plan_retry_window(
    policy(10, 3, 100, 6, 10000), ["lost", "held", "lost", "won"]
) == {
    "times": [0, 10, 110, 120],
    "verdict": "succeeded",
}, "held waits the full ceiling and forgets the run of losses"
assert plan_retry_window(
    policy(5, 4, 50, 6, 10000), ["lost", "lost", "lost", "lost", "lost", "lost"]
) == {
    "times": [0, 5, 25, 75, 125, 175],
    "verdict": "exhausted",
}, "the widening gap is held at the ceiling once it would pass it"
assert plan_retry_window(policy(10, 2, 100, 1, 1000), ["lost"]) == {
    "times": [0],
    "verdict": "exhausted",
}, "an allowance of one leaves no room for a second attempt"
assert plan_retry_window(policy(100, 2, 100, 5, 50), ["lost", "lost"]) == {
    "times": [0],
    "verdict": "expired",
}, "a first gap landing past the deadline closes the plan after one attempt"
assert plan_retry_window(policy(7, 2, 30, 4, 1000), ["held", "held", "won"]) == {
    "times": [0, 30, 60],
    "verdict": "succeeded",
}, "consecutive holds each wait exactly the ceiling"
assert plan_retry_window(
    policy(4, 2, 64, 8, 1000), ["lost", "held", "lost", "lost", "won"]
) == {
    "times": [0, 4, 68, 72, 80],
    "verdict": "succeeded",
}, "the first loss after a hold pays base again, not the widened gap"


def rejects(given, outcomes):
    try:
        plan_retry_window(given, outcomes)
    except ValueError:
        return True
    return False


assert rejects(policy(10, 2, 100, 5, 1000), ["lost"]), "an outcome list that runs out is rejected"
assert rejects(policy(10, 2, 100, 5, 1000), ["won", "maybe"]), "an unknown outcome name is rejected"
assert rejects({"base": 10, "factor": 2, "ceiling": 100, "tries": 5}, ["won"]), "a policy missing deadline is rejected"
assert rejects(policy(10, 2, 9, 5, 1000), ["won"]), "a ceiling under base is rejected"
assert rejects(policy(10, 0, 100, 5, 1000), ["won"]), "a factor of zero is rejected"
assert rejects(policy(10, 2, 100, 0, 1000), ["won"]), "an allowance of zero is rejected"
assert rejects(policy(10, 2, 100, 5, 1000), "won"), "a non-list outcome list is rejected"
assert rejects("policy", ["won"]), "a policy given as text is rejected"
print("ok")
