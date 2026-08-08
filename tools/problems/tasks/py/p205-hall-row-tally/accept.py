from solution import tally_hall_rows

assert tally_hall_rows(["oxo", "=oo"]) == [
    "tier0 held=1 open=2",
    "tier1 held=0 open=2",
    "hall held=1 open=4 widest=tier0",
], "a tie in open chairs falls to the lower tier"
assert tally_hall_rows(["ooo"]) == [
    "tier0 held=0 open=3",
    "hall held=0 open=3 widest=tier0",
], "a single tier still gets a closing line"
assert tally_hall_rows(["xxx", "=o=", "xox"]) == [
    "tier0 held=3 open=0",
    "tier1 held=0 open=1",
    "tier2 held=2 open=1",
    "hall held=5 open=2 widest=tier1",
], "steps are counted as neither held nor open"
assert tally_hall_rows(["xxxx"]) == [
    "tier0 held=4 open=0",
    "hall held=4 open=0 widest=tier0",
], "a full hall still names a widest tier"
assert tally_hall_rows(["=x=", "=o="]) == [
    "tier0 held=1 open=0",
    "tier1 held=0 open=1",
    "hall held=1 open=1 widest=tier1",
], "the widest tier need not be the first"
assert len(tally_hall_rows(["ox", "xo", "oo"])) == 4, "one line per tier plus the closing line"
assert (
    tally_hall_rows(["ox", "xo", "oo"])[-1] == "hall held=2 open=4 widest=tier2"
), "the closing line sums the hall"


def rejects(hall):
    try:
        tally_hall_rows(hall)
    except ValueError:
        return True
    return False


assert rejects("xox"), "a hall that is not a list is rejected"
assert rejects([]), "an empty hall is rejected"
assert rejects([7]), "a tier that is not a string is rejected"
assert rejects([""]), "an empty tier is rejected"
assert rejects(["xo", "x"]), "tiers of differing width are rejected"
assert rejects(["xoz"]), "a stray character is rejected"
assert rejects(["===", "xox"]), "a tier with no chair is rejected"
print("ok")
