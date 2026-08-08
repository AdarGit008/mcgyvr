from solution import trace_breaker_states

patient = {"trip": 2, "cool": 2, "proof": 2}

assert trace_breaker_states(
    ["fail", "fail", "pass", "fail", "pass", "pass"], patient
) == ["closed", "open", "open", "half", "half", "closed"], (
    "the guard trips, waits out the countdown and earns its way back"
)
assert trace_breaker_states(["fail", "fail", "pass", "pass", "fail"], patient) == [
    "closed",
    "open",
    "open",
    "half",
    "open",
], "one fail while half sends the guard back with a fresh countdown"
assert trace_breaker_states(
    ["fail", "pass", "fail", "fail", "fail", "pass", "pass"],
    {"trip": 3, "cool": 1, "proof": 1},
) == ["closed", "closed", "closed", "closed", "open", "half", "closed"], (
    "a pass wipes the losing streak so three separated fails never trip"
)
assert trace_breaker_states(
    ["pass", "pass", "pass"], {"trip": 1, "cool": 1, "proof": 1}
) == ["closed", "closed", "closed"], "nothing but passes leaves the guard closed"
assert trace_breaker_states(["fail"], {"trip": 1, "cool": 1, "proof": 1}) == [
    "open"
], "a trip of one opens on the first fail"
assert trace_breaker_states(
    ["fail", "pass", "pass"], {"trip": 1, "cool": 1, "proof": 2}
) == ["open", "half", "half"], "the outcome read while open is thrown away"
assert trace_breaker_states(
    ["fail", "fail", "fail", "fail"], {"trip": 1, "cool": 3, "proof": 1}
) == ["open", "open", "open", "half"], (
    "a long countdown ignores every outcome it swallows"
)
assert trace_breaker_states([], patient) == [], "no steps give no postures"


def rejects(one, two):
    try:
        trace_breaker_states(one, two)
    except ValueError:
        return True
    return False


assert rejects("fail", patient), "outcomes given as a string is rejected"
assert rejects(["skip"], patient), "an outcome outside the two words is rejected"
assert rejects(["fail"], {"trip": 2, "cool": 2}), "settings without proof is rejected"
assert rejects(["fail"], {"trip": 0, "cool": 2, "proof": 2}), (
    "a trip of zero is rejected"
)
assert rejects(["fail"], {"trip": 2, "cool": -1, "proof": 2}), (
    "a negative cool is rejected"
)
assert rejects(["fail"], {"trip": 2, "cool": 2, "proof": 1.5}), (
    "a fractional proof is rejected"
)
assert rejects(["fail"], {"trip": True, "cool": 2, "proof": 2}), (
    "a trip given as a boolean is rejected"
)
assert rejects(["fail"], [2, 2, 2]), "settings given as a list is rejected"
print("ok")
