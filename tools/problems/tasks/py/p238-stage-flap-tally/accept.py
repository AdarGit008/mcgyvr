from solution import tally_stage_retries


def stage(name, outcomes):
    return {"name": name, "outcomes": outcomes}


def rejects(stages, budget=3):
    try:
        tally_stage_retries(stages, budget)
    except ValueError:
        return True
    return False


assert tally_stage_retries([], 3) == ["* 0 0 0 0 0"], (
    "an empty pipeline still reports its rollup"
)
assert tally_stage_retries([stage("a", ["pass"])], 3) == [
    "a 1 0 0 0 green",
    "* 1 0 0 0 1",
], "one clean attempt costs no retry"
assert tally_stage_retries([stage("a", ["flap", "pass"])], 3) == [
    "a 2 1 1 0 green",
    "* 2 1 1 0 1",
], "a wobble that came good is still green"
assert tally_stage_retries([stage("a", ["flap", "halt"])], 3) == [
    "a 2 1 1 1 dead",
    "* 2 1 1 1 0",
], "a halt after a flap counts on both columns"
assert tally_stage_retries([stage("a", ["flap", "flap", "flap"])], 3) == [
    "a 3 2 3 0 spent",
    "* 3 2 3 0 0",
], "flapping to the last allowed attempt is spent"
assert tally_stage_retries([stage("a", ["flap"])], 3) == [
    "a 1 0 1 0 open",
    "* 1 0 1 0 0",
], "flapping with budget to spare is open"
assert tally_stage_retries([stage("a", ["flap"])], 1) == [
    "a 1 0 1 0 spent",
    "* 1 0 1 0 0",
], "a budget of one makes the first flap the last"
assert tally_stage_retries(
    [
        stage("build", ["flap", "pass"]),
        stage("test", ["halt"]),
        stage("ship", ["flap"]),
    ],
    2,
) == [
    "build 2 1 1 0 green",
    "test 1 0 0 1 dead",
    "ship 1 0 1 0 open",
    "* 4 1 2 1 1",
], "stages keep their order and the rollup sums every column"

assert rejects([stage("a", ["pass", "flap"])]), "nothing may follow a pass"
assert rejects([stage("a", ["halt", "flap"])]), "nothing may follow a halt"
assert rejects([stage("a", ["flap", "flap", "flap", "flap"])]), (
    "a stage over budget could never have happened"
)
assert rejects([stage("a", [])]), "a stage with no outcomes is rejected"
assert rejects([stage("a", ["boom"])]), "a word outside the three is rejected"
assert rejects([stage("a", ["pass"]), stage("a", ["pass"])]), (
    "a repeated stage name is rejected"
)
assert rejects([stage("two words", ["pass"])]), "a name holding a space is rejected"
assert rejects([stage("a", ["pass"])], 0), "a budget below one is rejected"
print("ok")
