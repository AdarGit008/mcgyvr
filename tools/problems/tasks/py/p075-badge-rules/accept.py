from solution import evaluate_rules

assert evaluate_rules([], {"role": "guest", "door": "lab"}) == "deny", (
    "no rules defaults to deny"
)

assert evaluate_rules(
    [
        {"effect": "allow", "role": "guest", "door": "lab"},
        {"effect": "deny", "role": "everyone", "door": "all"},
    ],
    {"role": "guest", "door": "lab"},
) == "allow", "the first matching rule decides, not the last"

assert evaluate_rules(
    [
        {"effect": "deny", "role": "guest", "door": "all"},
        {"effect": "allow", "role": "everyone", "door": "lab"},
    ],
    {"role": "guest", "door": "lab"},
) == "deny", "a deny first stays a deny"

assert evaluate_rules(
    [{"effect": "allow", "role": "everyone", "door": "archive"}],
    {"role": "clerk", "door": "archive"},
) == "allow", "everyone covers any role"

assert evaluate_rules(
    [{"effect": "allow", "role": "clerk", "door": "all"}],
    {"role": "clerk", "door": "roof"},
) == "allow", "all covers any door"

assert evaluate_rules(
    [{"effect": "allow", "role": "clerk", "door": "roof"}],
    {"role": "guest", "door": "roof"},
) == "deny", "a role mismatch falls through to deny"

assert evaluate_rules(
    [
        {"effect": "deny", "role": "everyone", "door": "vault"},
        {"effect": "allow", "role": "manager", "door": "vault"},
    ],
    {"role": "manager", "door": "vault"},
) == "deny", "an earlier broad deny shadows a later allow"

print("ok")
