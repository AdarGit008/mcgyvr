from solution import judge_key_rotation

# The digests below are four-character stand-ins made up here, not real ones.
past = [
    {"digest": "aa11", "step": 0},
    {"digest": "bb22", "step": 5},
    {"digest": "cc33", "step": 9},
]
house = {"keep": 2, "gap": 2, "span": 30, "runs": 3, "window": 12}


def bent(base, **changes):
    made = dict(base)
    made.update(changes)
    return made


assert judge_key_rotation(past, {"digest": "dd44", "step": 12}, house) == {
    "verdict": "accept",
    "broken": [],
}, "a fresh digest at a sensible step is accepted"
assert judge_key_rotation(past, {"digest": "aa11", "step": 12}, house) == {
    "verdict": "accept",
    "broken": [],
}, "a digest older than the keep window may come round again"
assert judge_key_rotation(past, {"digest": "cc33", "step": 12}, house) == {
    "verdict": "refuse",
    "broken": ["reused"],
}, "the newest digest is still inside the keep window"
assert judge_key_rotation(past, {"digest": "bb22", "step": 12}, house) == {
    "verdict": "refuse",
    "broken": ["reused"],
}, "the keep window reaches back exactly two digests"
assert judge_key_rotation(past, {"digest": "dd44", "step": 10}, house) == {
    "verdict": "refuse",
    "broken": ["toosoon", "churn"],
}, "a hurried offer breaks the gap rule and the run rule together"
assert judge_key_rotation(past, {"digest": "dd44", "step": 50}, house) == {
    "verdict": "refuse",
    "broken": ["stale"],
}, "a difference above span is stale and no longer counts as churn"
assert judge_key_rotation(past, {"digest": "bb22", "step": 50}, house) == {
    "verdict": "refuse",
    "broken": ["reused", "stale"],
}, "reused is always named before stale"

roomy = bent(house, runs=9)
assert judge_key_rotation(past, {"digest": "dd44", "step": 11}, roomy) == {
    "verdict": "accept",
    "broken": [],
}, "a difference exactly equal to gap passes"
assert judge_key_rotation(past, {"digest": "dd44", "step": 10}, roomy) == {
    "verdict": "refuse",
    "broken": ["toosoon"],
}, "one step short of gap is too soon"
assert judge_key_rotation(past, {"digest": "dd44", "step": 39}, roomy) == {
    "verdict": "accept",
    "broken": [],
}, "a difference exactly equal to span passes"
assert judge_key_rotation(past, {"digest": "dd44", "step": 40}, roomy) == {
    "verdict": "refuse",
    "broken": ["stale"],
}, "one step past span is stale"

assert judge_key_rotation([], {"digest": "aa11", "step": 0}, house) == {
    "verdict": "accept",
    "broken": [],
}, "an empty ledger has no gap, no staleness and no churn"
assert judge_key_rotation(
    past, {"digest": "cc33", "step": 12}, bent(house, keep=0)
) == {"verdict": "accept", "broken": []}, "a keep of zero lets any digest through"
assert judge_key_rotation(
    past, {"digest": "aa11", "step": 12}, bent(house, keep=9)
) == {
    "verdict": "refuse",
    "broken": ["reused"],
}, "a keep past the ledger length reaches the whole ledger"
assert judge_key_rotation(
    [{"digest": "aa11", "step": 0}],
    {"digest": "bb22", "step": 1},
    {"keep": 1, "gap": 0, "span": 100, "runs": 1, "window": 5},
) == {
    "verdict": "refuse",
    "broken": ["churn"],
}, "a runs of one refuses any second change inside the window"
assert judge_key_rotation(
    [{"digest": "aa11", "step": 0}],
    {"digest": "bb22", "step": 5},
    {"keep": 1, "gap": 0, "span": 100, "runs": 1, "window": 5},
) == {
    "verdict": "accept",
    "broken": [],
}, "an entry exactly a window back has already left the window"


def rejects(one, two, three):
    try:
        judge_key_rotation(one, two, three)
    except ValueError:
        return True
    return False


assert rejects("aa11", {"digest": "bb22", "step": 1}, house), (
    "a ledger given as a string is rejected"
)
assert rejects([{"digest": "aa11"}], {"digest": "bb22", "step": 1}, house), (
    "an entry without a step is rejected"
)
assert rejects([{"digest": "AA11", "step": 0}], {"digest": "bb22", "step": 1}, house), (
    "a digest with capitals is rejected"
)
assert rejects([{"digest": "", "step": 0}], {"digest": "bb22", "step": 1}, house), (
    "an empty digest is rejected"
)
assert rejects(
    [{"digest": "aa11", "step": 4}, {"digest": "bb22", "step": 4}],
    {"digest": "cc33", "step": 9},
    house,
), "a ledger whose steps do not rise is rejected"
assert rejects(past, {"digest": "dd44", "step": 9}, house), (
    "an offer level with the newest ledger step is rejected"
)
assert rejects(
    past, {"digest": "dd44", "step": 12}, {"keep": 2, "gap": 2, "span": 30, "runs": 3}
), "rules without window is rejected"
assert rejects(past, {"digest": "dd44", "step": 12}, bent(house, keep=-1)), (
    "a negative keep is rejected"
)
assert rejects(past, {"digest": "dd44", "step": 12}, bent(house, runs=0)), (
    "a runs of zero is rejected"
)
assert rejects(past, {"digest": "dd44", "step": 12}, bent(house, window=True)), (
    "a window given as a boolean is rejected"
)
assert rejects(past, {"digest": "dd44", "step": 12}, bent(house, gap=40)), (
    "a gap larger than span is rejected"
)
print("ok")
