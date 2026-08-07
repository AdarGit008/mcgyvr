from solution import audit_mail_run

PLAN = [
    {"bin": "alpha", "grades": "PL", "offices": ["AB"]},
    {"bin": "beta", "grades": "P", "offices": ["AB", "CD"]},
    {"bin": "gamma", "grades": "E", "offices": ["MN"]},
]

assert audit_mail_run([], PLAN) == {
    "misrouted": [],
    "tally": [],
}, "an empty night audits to nothing"
assert audit_mail_run([{"code": "PAB126", "stamped": "alpha"}], PLAN) == {
    "misrouted": [],
    "tally": [{"bin": "alpha", "count": 1}],
}, "a sound code stamped as planned"
assert audit_mail_run([{"code": "PCD007", "stamped": "beta"}], PLAN) == {
    "misrouted": [],
    "tally": [{"bin": "beta", "count": 1}],
}, "the first entry is skipped when its offices do not hold the code's"
assert audit_mail_run([{"code": "PAB123", "stamped": "alpha"}], PLAN) == {
    "misrouted": [{"code": "PAB123", "stamped": "alpha", "correct": "QUERY"}],
    "tally": [{"bin": "QUERY", "count": 1}],
}, "an unsound check digit outranks the plan"
assert audit_mail_run([{"code": "LZZ406", "stamped": "gamma"}], PLAN) == {
    "misrouted": [{"code": "LZZ406", "stamped": "gamma", "correct": "SPARE"}],
    "tally": [{"bin": "SPARE", "count": 1}],
}, "a sound code no entry claims falls to SPARE"
assert audit_mail_run(
    [
        {"code": "PAB126", "stamped": "alpha"},
        {"code": "LAB991", "stamped": "beta"},
        {"code": "PCD007", "stamped": "beta"},
        {"code": "EMN074", "stamped": "gamma"},
        {"code": "LZZ406", "stamped": "gamma"},
        {"code": "PAB123", "stamped": "alpha"},
    ],
    PLAN,
) == {
    "misrouted": [
        {"code": "LAB991", "stamped": "beta", "correct": "alpha"},
        {"code": "LZZ406", "stamped": "gamma", "correct": "SPARE"},
        {"code": "PAB123", "stamped": "alpha", "correct": "QUERY"},
    ],
    "tally": [
        {"bin": "QUERY", "count": 1},
        {"bin": "SPARE", "count": 1},
        {"bin": "alpha", "count": 2},
        {"bin": "beta", "count": 1},
        {"bin": "gamma", "count": 1},
    ],
}, "a whole night, tallied by true bin with capitals sorting first"
assert audit_mail_run(
    [{"code": "EMN074", "stamped": "gamma"}],
    [{"bin": "wide", "grades": "PLE", "offices": ["MN", "AB"]}],
) == {
    "misrouted": [{"code": "EMN074", "stamped": "gamma", "correct": "wide"}],
    "tally": [{"bin": "wide", "count": 1}],
}, "one entry may hold every grade"


def rejects(items, plan):
    try:
        audit_mail_run(items, plan)
    except ValueError:
        return True
    return False


assert rejects([], []), "an empty plan"
assert rejects(
    [],
    [
        {"bin": "x", "grades": "P", "offices": ["AB"]},
        {"bin": "x", "grades": "L", "offices": ["CD"]},
    ],
), "repeated bin"
assert rejects([], [{"bin": "SPARE", "grades": "P", "offices": ["AB"]}]), (
    "a plan bin named for a mark"
)
assert rejects([], [{"bin": "x", "grades": "PP", "offices": ["AB"]}]), (
    "a repeated grade letter"
)
assert rejects([], [{"bin": "x", "grades": "PX", "offices": ["AB"]}]), (
    "an unknown grade letter"
)
assert rejects([], [{"bin": "x", "grades": "P", "offices": ["Ab"]}]), (
    "an office that is not two capitals"
)
assert rejects([], [{"bin": "x", "grades": "P", "offices": ["AB", "AB"]}]), (
    "a repeated office"
)
assert rejects([{"code": "PAB12", "stamped": "alpha"}], PLAN), (
    "a code of the wrong length"
)
assert rejects([{"code": "XAB126", "stamped": "alpha"}], PLAN), (
    "an unknown grade letter in a code"
)
assert rejects([{"code": "PAB126", "stamped": ""}], PLAN), "an empty stamped bin"
print("ok")
