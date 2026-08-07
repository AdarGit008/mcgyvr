from solution import replay_loan_desk

assert replay_loan_desk(
    {"d": 1},
    3,
    [
        ["borrow", "a", "d"],
        ["borrow", "b", "d"],
        ["hold", "b", "d"],
        ["hold", "c", "d"],
        ["hold", "b", "d"],
        ["renew", "a", "d"],
        ["return", "a", "d"],
        ["borrow", "c", "d"],
        ["borrow", "b", "d"],
        ["return", "b", "d"],
        ["borrow", "c", "d"],
    ],
) == [
    "ok",
    "no:none-left",
    "ok",
    "ok",
    "no:in-queue",
    "no:on-hold",
    "ok",
    "no:queued-ahead",
    "ok",
    "ok",
    "ok",
], "the hold queue gates who may borrow next"
assert replay_loan_desk(
    {"r": 1},
    1,
    [
        ["borrow", "a", "r"],
        ["renew", "a", "r"],
        ["renew", "a", "r"],
        ["renew", "a", "r"],
        ["return", "a", "r"],
        ["borrow", "a", "r"],
        ["renew", "a", "r"],
    ],
) == [
    "ok",
    "ok",
    "ok",
    "no:renew-cap",
    "ok",
    "ok",
    "ok",
], "two renewals per loan, reset by a fresh borrow"
assert replay_loan_desk(
    {"x": 1, "y": 1, "z": 1},
    2,
    [
        ["borrow", "a", "x"],
        ["borrow", "a", "y"],
        ["borrow", "a", "z"],
        ["return", "b", "x"],
        ["renew", "b", "x"],
        ["borrow", "a", "q"],
        ["hold", "a", "x"],
        ["hold", "b", "y"],
        ["hold", "b", "z"],
    ],
) == [
    "ok",
    "ok",
    "no:member-cap",
    "no:not-out",
    "no:not-out",
    "no:unknown-title",
    "no:own-loan",
    "ok",
    "no:take-it",
], "member cap, holder checks and hold preconditions"
assert replay_loan_desk(
    {"m": 2},
    5,
    [
        ["borrow", "a", "m"],
        ["borrow", "b", "m"],
        ["borrow", "c", "m"],
        ["hold", "c", "m"],
        ["return", "a", "m"],
        ["borrow", "d", "m"],
        ["borrow", "c", "m"],
    ],
) == [
    "ok",
    "ok",
    "no:none-left",
    "ok",
    "ok",
    "no:queued-ahead",
    "ok",
], "two copies circulate through one queue"
assert replay_loan_desk({"s": 1}, 1, [["borrow", "a", "s"], ["borrow", "a", "s"]]) == [
    "ok",
    "no:already-out",
], "already-out beats member-cap in check order"
assert replay_loan_desk({"s": 1}, 1, []) == [], "no events, no answers"


def rejects(*args):
    try:
        replay_loan_desk(*args)
    except ValueError:
        return True
    return False


assert rejects({"s": 1}, 1, [["steal", "a", "s"]]), "unknown action throws"
assert rejects({"s": 0}, 1, []), "zero copies throws"
assert rejects({"s": 1}, 0, []), "zero cap throws"
assert rejects({"s": 1}, 1, [["borrow", "a"]]), "short event throws"
print("ok")
