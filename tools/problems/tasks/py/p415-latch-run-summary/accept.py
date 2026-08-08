from solution import summarise_latch_run

assert summarise_latch_run(
    ["bad", "good", "bad", "good", "good", "bad", "bad", "good", "good", "good"],
    {"span": 3, "sour": 2, "wait": 2, "trials": 2},
) == {"mode": "shut", "tried": 6, "shed": 4, "trips": 2}, (
    "two trips, four shed steps, and the latch earns its way back"
)
assert summarise_latch_run(
    ["bad", "good", "good", "good", "bad"],
    {"span": 3, "sour": 2, "wait": 1, "trials": 1},
) == {"mode": "shut", "tried": 5, "shed": 0, "trips": 0}, (
    "the oldest word leaves the ledger, so an early bad cannot trip a later one"
)
assert summarise_latch_run(
    ["bad", "bad"], {"span": 4, "sour": 2, "wait": 1, "trials": 1}
) == {"mode": "shut", "tried": 2, "shed": 0, "trips": 0}, (
    "a ledger short of span never trips however sour it is"
)
assert summarise_latch_run(
    ["bad", "good", "good", "good", "good"],
    {"span": 1, "sour": 1, "wait": 3, "trials": 1},
) == {"mode": "shut", "tried": 2, "shed": 3, "trips": 1}, (
    "three steps pass with no call while the countdown runs"
)
assert summarise_latch_run(
    ["bad", "good"], {"span": 1, "sour": 1, "wait": 5, "trials": 1}
) == {"mode": "tripped", "tried": 1, "shed": 1, "trips": 1}, (
    "a run ending mid countdown reports the tripped mode"
)
assert summarise_latch_run(
    ["bad", "good", "bad", "bad", "good", "good"],
    {"span": 2, "sour": 2, "wait": 1, "trials": 1},
) == {"mode": "shut", "tried": 5, "shed": 1, "trips": 1}, (
    "the ledger is emptied on tripping, so it refills from scratch"
)
assert summarise_latch_run([], {"span": 2, "sour": 1, "wait": 1, "trials": 1}) == {
    "mode": "shut",
    "tried": 0,
    "shed": 0,
    "trips": 0,
}, "an empty run leaves the latch untouched"
assert summarise_latch_run(
    ["good", "good", "good"], {"span": 2, "sour": 1, "wait": 1, "trials": 1}
) == {"mode": "shut", "tried": 3, "shed": 0, "trips": 0}, (
    "nothing bad ever trips the latch"
)


def rejects(one, two):
    try:
        summarise_latch_run(one, two)
    except ValueError:
        return True
    return False


assert rejects("bad", {"span": 2, "sour": 1, "wait": 1, "trials": 1}), (
    "a run given as a string is rejected"
)
assert rejects(["slow"], {"span": 2, "sour": 1, "wait": 1, "trials": 1}), (
    "a word outside the two is rejected"
)
assert rejects(["bad"], {"span": 2, "sour": 1, "wait": 1}), (
    "a dial without trials is rejected"
)
assert rejects(["bad"], {"span": 2, "sour": 3, "wait": 1, "trials": 1}), (
    "a sour larger than span is rejected"
)
assert rejects(["bad"], {"span": 0, "sour": 1, "wait": 1, "trials": 1}), (
    "a span of zero is rejected"
)
assert rejects(["bad"], {"span": 2, "sour": 1, "wait": 1.5, "trials": 1}), (
    "a fractional wait is rejected"
)
assert rejects(["bad"], {"span": 2, "sour": 1, "wait": True, "trials": 1}), (
    "a wait given as a boolean is rejected"
)
assert rejects(["bad"], [2, 1, 1, 1]), "a dial given as a list is rejected"
print("ok")
