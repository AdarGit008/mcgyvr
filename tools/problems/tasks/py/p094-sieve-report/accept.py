from solution import sieve_report

rules = [
    {"name": "needs-badge", "field": "badge", "op": "present"},
    {"name": "tier-cap", "field": "tier", "op": "lt", "value": 3},
    {"name": "not-parked", "field": "state", "op": "ne", "value": "parked"},
]
assert sieve_report(
    [
        {"badge": 1, "tier": 2, "state": "live"},
        {"tier": 2, "state": "live"},
        {"badge": 1, "tier": 5, "state": "live"},
        {"badge": 1, "tier": 2, "state": "parked"},
        {"badge": 1, "state": "live"},
        {"badge": 1, "tier": "high", "state": "live"},
    ],
    rules,
) == [
    "pass",
    "needs-badge",
    "tier-cap",
    "not-parked",
    "tier-cap",
    "tier-cap",
], "first failing rule is named; missing and non-number fields fail"
assert sieve_report(
    [{"flag": 1}], [{"name": "no-flag", "field": "flag", "op": "absent"}]
) == ["no-flag"], "absent fails when the field exists"
assert sieve_report(
    [{}], [{"name": "no-flag", "field": "flag", "op": "absent"}]
) == ["pass"], "absent passes when the field is missing"
assert sieve_report(
    [{"kind": "ore"}, {"kind": "ash"}],
    [{"name": "ore-only", "field": "kind", "op": "eq", "value": "ore"}],
) == ["pass", "ore-only"], "eq compares exactly"
assert sieve_report(
    [{"mass": 8}], [{"name": "heavy", "field": "mass", "op": "gt", "value": 8}]
) == ["heavy"], "gt is strict"
assert sieve_report([{"a": 1}, {}], []) == ["pass", "pass"], "no rules, all pass"
assert sieve_report([], rules) == [], "no items, no verdicts"


def rejects(items, rules_arg):
    try:
        sieve_report(items, rules_arg)
    except ValueError:
        return True
    return False


assert rejects([], [{"name": "r", "field": "a", "op": "ge", "value": 1}]), "unknown op is rejected"
assert rejects(
    [],
    [
        {"name": "r", "field": "a", "op": "eq", "value": 1},
        {"name": "r", "field": "b", "op": "eq", "value": 2},
    ],
), "repeated rule name is rejected"
assert rejects([], [{"name": "", "field": "a", "op": "eq", "value": 1}]), "empty rule name is rejected"
print("ok")
