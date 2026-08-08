from solution import audit_swap_board


def shift(code, day, holder):
    return {"code": code, "day": day, "holder": holder}


def claim(code, bidder):
    return {"code": code, "bidder": bidder}


def opening():
    return [
        shift("m1", 1, "ada"),
        shift("m2", 2, "ada"),
        shift("m3", 1, "ben"),
        shift("m4", 3, "ben"),
        shift("m5", 2, "cleo"),
    ]


assert audit_swap_board(
    {
        "shifts": opening(),
        "claims": [
            claim("m1", "cleo"),
            claim("m3", "cleo"),
            claim("m4", "cleo"),
            claim("m3", "ada"),
            claim("m1", "ben"),
            claim("m5", "ada"),
            claim("m9", "ada"),
            claim("m2", "ada"),
        ],
    },
    2,
) == {
    "verdicts": ["taken", "busy", "full", "taken", "gone", "busy", "unknown", "self"],
    "loads": ["ada 2", "ben 1", "cleo 2"],
}, "every refusal reason over one walk of the board"

assert audit_swap_board({"shifts": opening(), "claims": []}, 3) == {
    "verdicts": [],
    "loads": ["ada 2", "ben 2", "cleo 1"],
}, "no claims leaves the opening loads"

assert audit_swap_board(
    {"shifts": [shift("a", 1, "kim"), shift("b", 2, "lou")], "claims": [claim("a", "lou")]},
    1,
) == {
    "verdicts": ["full"],
    "loads": ["kim 1", "lou 1"],
}, "a ceiling of one refuses anybody already holding one"

assert audit_swap_board(
    {"shifts": [shift("a", 1, "kim"), shift("b", 2, "lou")], "claims": [claim("a", "lou")]},
    2,
) == {
    "verdicts": ["taken"],
    "loads": ["lou 2"],
}, "somebody stripped of every shift drops off the loads"

assert audit_swap_board(
    {
        "shifts": [shift("a", 4, "kim"), shift("b", 4, "lou"), shift("c", 6, "kim")],
        "claims": [claim("a", "lou"), claim("c", "lou")],
    },
    5,
) == {
    "verdicts": ["busy", "taken"],
    "loads": ["kim 1", "lou 2"],
}, "two shifts on one day cannot land on one person"

assert audit_swap_board(
    {"shifts": [shift("a", 1, "kim")], "claims": [claim("a", "lou"), claim("a", "kim")]},
    4,
) == {
    "verdicts": ["taken", "gone"],
    "loads": ["lou 1"],
}, "a shift that has moved once will not move again"


def rejects(*args):
    try:
        audit_swap_board(*args)
    except ValueError:
        return True
    return False


assert rejects("no", 1), "the board must be a record"
assert rejects({"shifts": []}, 1), "a missing board key is refused"
assert rejects({"shifts": "no", "claims": []}, 1), "shifts must be a list"
assert rejects({"shifts": [{"code": "a", "day": 1}], "claims": []}, 1), "a shift missing a key is refused"
assert rejects(
    {"shifts": [shift("a", 1, "kim"), shift("a", 2, "lou")], "claims": []}, 1
), "a repeated code is refused"
assert rejects({"shifts": [shift("a", 8, "kim")], "claims": []}, 1), "a day of eight is refused"
assert rejects({"shifts": [shift("a", 1, "")], "claims": []}, 1), "an empty holder is refused"
assert rejects({"shifts": [], "claims": [claim("a", "")]}, 1), "an empty bidder is refused"
assert rejects({"shifts": [], "claims": []}, 0), "a ceiling of nought is refused"
print("ok")
