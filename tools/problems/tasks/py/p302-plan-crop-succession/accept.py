from solution import plan_crop_succession

TABLE = [
    ["wheat", "barley"],
    ["wheat", "clover"],
    ["wheat", "beet"],
    ["barley", "clover"],
    ["barley", "beet"],
    ["clover", "wheat"],
    ["clover", "barley"],
    ["beet", "wheat"],
    ["beet", "barley"],
    ["wheat", "fallow"],
]
RANKING = ["clover", "wheat", "barley", "beet", "fallow"]
CYCLE = [["rye", "oat"], ["oat", "rye"]]


def rejects(*args):
    try:
        plan_crop_succession(*args)
    except ValueError:
        return True
    return False


assert plan_crop_succession(["wheat"], TABLE, RANKING, 1) == [
    ["clover"]
], "one plot takes the highest ranked legal follower"
assert plan_crop_succession(["wheat"], TABLE, RANKING, 3) == [
    ["clover", "barley", "beet"]
], "the two-season memory pushes the plot down the ranking"
assert plan_crop_succession(["wheat", "wheat"], TABLE, RANKING, 2) == [
    ["clover", "barley"],
    ["barley", "clover"],
], "the allowance of one splits two plots apart"
assert plan_crop_succession(["wheat", "wheat", "wheat"], TABLE, RANKING, 1) == [
    ["clover"],
    ["clover"],
    ["barley"],
], "three plots allow two of a kind before the allowance bites"
assert (
    plan_crop_succession(["fallow"], TABLE, RANKING, 1) == []
), "a crop the table never leads out of collapses the plan"
assert (
    plan_crop_succession(["rye"], CYCLE, ["rye", "oat"], 3) == []
), "a two-crop cycle cannot survive the two-season memory"
assert plan_crop_succession(["rye"], CYCLE, ["rye", "oat"], 1) == [
    ["oat"]
], "the same cycle plans a single season perfectly well"

assert rejects([], TABLE, RANKING, 1), "a farm with no plots is rejected"
assert rejects(["wheat", ""], TABLE, RANKING, 1), "a blank plot name is rejected"
assert rejects(
    "wheat", TABLE, RANKING, 1
), "a plot list that is not a list is rejected"
assert rejects(
    ["wheat"], [["wheat", "barley", "beet"]], RANKING, 1
), "a table row of three is rejected"
assert rejects(
    ["wheat"], [["wheat", "barley"], ["wheat", "barley"]], RANKING, 1
), "the same pair stated twice is rejected"
assert rejects(
    ["wheat"], TABLE, ["clover", "clover"], 1
), "a ranking that repeats a crop is rejected"
assert rejects(
    ["wheat"], TABLE, ["clover", "wheat"], 1
), "a table crop missing from the ranking is rejected"
assert rejects(["wheat"], TABLE, RANKING, 0), "planning no seasons is rejected"
assert rejects(["wheat"], TABLE, RANKING, 2.5), "a fractional season count is rejected"
print("ok")
