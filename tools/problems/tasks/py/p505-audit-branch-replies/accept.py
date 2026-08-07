from solution import audit_branch_replies

ITEMS = [
    {"tag": "own"},
    {"tag": "kind", "when": {"tag": "own", "is": "yes"}},
    {"tag": "years", "when": {"tag": "kind", "is": "flat"}},
    {"tag": "why", "when": {"tag": "own", "is": "no"}},
    {"tag": "end"},
]


def audit(given):
    return audit_branch_replies({"items": ITEMS, "given": given})


assert audit({"own": "yes", "kind": "flat", "years": "3", "end": "z"}) == {
    "due": ["own", "kind", "years", "end"],
    "extra": [],
    "gap": [],
}, "a branch taken all the way down owes every entry on it"
assert audit({"own": "no", "why": "cost", "end": "z"}) == {
    "due": ["own", "why", "end"],
    "extra": [],
    "gap": [],
}, "the other branch owes its own entries and nothing else"
assert audit({"own": "no", "kind": "flat", "years": "3", "end": "z"}) == {
    "due": ["own", "why", "end"],
    "extra": ["kind", "years"],
    "gap": ["why"],
}, "an entry two levels under an untaken branch is spurious, not owed"
assert audit({"own": "yes"}) == {
    "due": ["own", "kind", "end"],
    "extra": [],
    "gap": ["kind", "end"],
}, "an owed entry left empty is a gap"
assert audit({}) == {
    "due": ["own", "end"],
    "extra": [],
    "gap": ["own", "end"],
}, "an empty sheet owes only its unguarded entries"
assert audit({"own": "yes", "kind": "house", "end": "z"}) == {
    "due": ["own", "kind", "end"],
    "extra": [],
    "gap": [],
}, "a guard whose is does not match closes the branch below it"
assert audit({"own": "no", "kind": "flat", "years": "3", "why": "cost", "end": "z"}) == {
    "due": ["own", "why", "end"],
    "extra": ["kind", "years"],
    "gap": [],
}, "spurious entries never turn into owed ones"


def rejects(sheet):
    try:
        audit_branch_replies(sheet)
    except ValueError:
        return True
    return False


assert rejects([]), "a list is not a sheet"
assert rejects({"items": [], "given": {}}), "no items at all"
assert rejects({"items": [{"tag": "a"}, {"tag": "a"}], "given": {}}), "a shared tag"
assert rejects(
    {"items": [{"tag": "a", "when": {"tag": "b", "is": "x"}}, {"tag": "b"}], "given": {}}
), "a when may not lean on a later item"
assert rejects(
    {"items": [{"tag": "a"}, {"tag": "b", "when": {"tag": "a", "is": ""}}], "given": {}}
), "a when needs a non-empty is"
assert rejects({"items": [{"tag": "a"}], "given": {"z": "x"}}), "an answer to no item"
assert rejects({"items": [{"tag": "a"}], "given": {"a": 7}}), "an answer must be a string"
print("ok")
