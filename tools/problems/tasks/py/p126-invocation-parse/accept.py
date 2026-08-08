from solution import parse_invocation

CAT = [
    {"name": "verbose", "kind": "toggle", "alias": "v"},
    {"name": "out", "kind": "single", "alias": "o"},
    {"name": "tag", "kind": "repeat"},
]

assert parse_invocation(CAT, []) == {
    "options": {"verbose": False, "out": None, "tag": []},
    "operands": [],
}, "defaults when nothing is mentioned"
assert parse_invocation(CAT, ["-v", "build", "--out=dist"]) == {
    "options": {"verbose": True, "out": "dist", "tag": []},
    "operands": ["build"],
}, "alias toggle, operand, inline single"
assert parse_invocation(CAT, ["--tag", "a", "--tag=b", "c"]) == {
    "options": {"verbose": False, "out": None, "tag": ["a", "b"]},
    "operands": ["c"],
}, "repeat collects both forms in order"
assert parse_invocation(CAT, ["-o", "-v", "x"]) == {
    "options": {"verbose": False, "out": "-v", "tag": []},
    "operands": ["x"],
}, "the next token is consumed as the value no matter what"
assert parse_invocation(CAT, ["--", "--out", "late"]) == {
    "options": {"verbose": False, "out": None, "tag": []},
    "operands": ["--out", "late"],
}, "everything after bare -- is an operand"
assert parse_invocation(CAT, ["-v", "--verbose"]) == {
    "options": {"verbose": True, "out": None, "tag": []},
    "operands": [],
}, "a toggle mentioned twice stays true"
assert parse_invocation(CAT, ["--out="]) == {
    "options": {"verbose": False, "out": "", "tag": []},
    "operands": [],
}, "inline empty value is a value"
assert parse_invocation(CAT, ["-", "-xy"]) == {
    "options": {"verbose": False, "out": None, "tag": []},
    "operands": ["-", "-xy"],
}, "lone dash and multi-letter clusters are operands"


def rejects(tokens):
    try:
        parse_invocation(CAT, tokens)
    except ValueError:
        return True
    return False


assert rejects(["--depth", "2"]), "unknown long name"
assert rejects(["-z"]), "unknown alias"
assert rejects(["--verbose=yes"]), "inline on toggle"
assert rejects(["--out", "a", "-o", "b"]), "single mentioned twice"
assert rejects(["--out"]), "missing value at the end"
print("ok")
