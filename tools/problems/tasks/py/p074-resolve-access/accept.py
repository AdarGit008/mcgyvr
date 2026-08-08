from solution import resolve_access

assert resolve_access([], {"action": "read", "path": ["docs"]}) == {
    "decision": "deny",
    "rule": -1,
}, "no rules means default deny"

assert resolve_access(
    [
        {"effect": "allow", "action": "read", "path": []},
        {"effect": "deny", "action": "read", "path": ["vault"]},
    ],
    {"action": "read", "path": ["vault", "keys"]},
) == {"decision": "deny", "rule": 1}, "longer path prefix wins over the catch-all"

assert resolve_access(
    [
        {"effect": "deny", "action": "any", "path": ["docs"]},
        {"effect": "allow", "action": "read", "path": ["docs"]},
    ],
    {"action": "read", "path": ["docs"]},
) == {"decision": "allow", "rule": 1}, (
    "exact action beats the any action at equal path length"
)

assert resolve_access(
    [
        {"effect": "allow", "action": "write", "path": ["a"]},
        {"effect": "deny", "action": "write", "path": ["a"]},
    ],
    {"action": "write", "path": ["a", "b"]},
) == {"decision": "deny", "rule": 1}, "deny beats allow when fully tied"

assert resolve_access(
    [
        {"effect": "allow", "action": "read", "path": ["x"]},
        {"effect": "allow", "action": "read", "path": ["x"]},
    ],
    {"action": "read", "path": ["x"]},
) == {"decision": "allow", "rule": 0}, "earlier rule wins between identical rules"

assert resolve_access(
    [{"effect": "allow", "action": "read", "path": ["a", "b"]}],
    {"action": "read", "path": ["a"]},
) == {"decision": "deny", "rule": -1}, (
    "a rule path longer than the request is not a prefix"
)

assert resolve_access(
    [{"effect": "allow", "action": "write", "path": ["a"]}],
    {"action": "read", "path": ["a"]},
) == {"decision": "deny", "rule": -1}, "action mismatch means no match"


def rejects(rules, request):
    try:
        resolve_access(rules, request)
    except ValueError:
        return True
    return False


assert rejects(
    [{"effect": "block", "action": "read", "path": []}],
    {"action": "read", "path": []},
), "unknown effect is rejected"

assert rejects(
    [{"effect": "allow", "action": "", "path": []}],
    {"action": "read", "path": []},
), "empty rule action is rejected"

print("ok")
