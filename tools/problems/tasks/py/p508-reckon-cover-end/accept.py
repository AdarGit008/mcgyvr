from solution import reckon_cover_end

assert reckon_cover_end(
    {"bought": "2020-01-31", "months": 12, "extensions": [], "repairs": [], "claim": "2020-06-01"}
) == {
    "ends": "2021-01-31",
    "suspended": 0,
    "verdict": "covered",
    "left": 245,
}, "a plain year of cover lands on the same day number"
assert reckon_cover_end(
    {"bought": "2020-01-31", "months": 1, "extensions": [], "repairs": [], "claim": "2020-02-29"}
) == {
    "ends": "2020-02-29",
    "suspended": 0,
    "verdict": "covered",
    "left": 1,
}, "a short leap month takes the landing to its last day"
assert reckon_cover_end(
    {"bought": "2021-01-31", "months": 1, "extensions": [], "repairs": [], "claim": "2021-03-01"}
) == {
    "ends": "2021-02-28",
    "suspended": 0,
    "verdict": "lapsed",
    "left": 0,
}, "the same month outside a leap year is a day shorter"
assert reckon_cover_end(
    {"bought": "2019-03-15", "months": 24, "extensions": [6, 6], "repairs": [], "claim": "2022-03-15"}
) == {
    "ends": "2022-03-15",
    "suspended": 0,
    "verdict": "covered",
    "left": 1,
}, "extension blocks pile on to the sold months"
assert reckon_cover_end(
    {
        "bought": "2022-01-01",
        "months": 6,
        "extensions": [],
        "repairs": [{"in": "2022-02-10", "out": "2022-02-19"}],
        "claim": "2022-07-11",
    }
) == {
    "ends": "2022-07-11",
    "suspended": 10,
    "verdict": "covered",
    "left": 1,
}, "a workshop visit counts both its ends"
assert reckon_cover_end(
    {
        "bought": "2022-01-01",
        "months": 6,
        "extensions": [3],
        "repairs": [
            {"in": "2022-02-10", "out": "2022-02-19"},
            {"in": "2022-05-01", "out": "2022-05-31"},
        ],
        "claim": "2021-12-31",
    }
) == {
    "ends": "2022-11-11",
    "suspended": 41,
    "verdict": "early",
    "left": 0,
}, "two visits add up and a claim before the purchase is early"
assert reckon_cover_end(
    {"bought": "1999-12-01", "months": 3, "extensions": [], "repairs": [], "claim": "2000-03-02"}
) == {
    "ends": "2000-03-01",
    "suspended": 0,
    "verdict": "lapsed",
    "left": 0,
}, "cover reaching over a century boundary still lands correctly"
assert reckon_cover_end(
    {"bought": "2020-08-31", "months": 6, "extensions": [], "repairs": [], "claim": "2021-01-01"}
) == {
    "ends": "2021-02-28",
    "suspended": 0,
    "verdict": "covered",
    "left": 59,
}, "the days still in front of the claim are counted inclusively"

SOUND = {
    "bought": "2020-01-01",
    "months": 12,
    "extensions": [],
    "repairs": [],
    "claim": "2020-06-01",
}


def rejects(**changes):
    policy = dict(SOUND)
    policy.update(changes)
    try:
        reckon_cover_end(policy)
    except ValueError:
        return True
    return False


def rejects_value(policy):
    try:
        reckon_cover_end(policy)
    except ValueError:
        return True
    return False


assert rejects_value([]), "a list is not a policy"
assert rejects(bought="2020-2-01"), "an unpadded month"
assert rejects(bought="2021-02-29"), "a day that never was"
assert rejects(bought="1899-01-01"), "a year before 1900"
assert rejects(months=0), "no months of cover"
assert rejects(extensions=[61]), "an oversized block"
assert rejects(repairs={}), "the repairs must be a list"
assert rejects(repairs=[{"in": "2020-03-05", "out": "2020-03-01"}]), "back before it went"
assert rejects(repairs=[{"in": "2019-12-31", "out": "2020-01-05"}]), "open before the purchase"
assert rejects(
    repairs=[{"in": "2020-03-01", "out": "2020-03-10"}, {"in": "2020-03-10", "out": "2020-03-12"}]
), "two visits may not touch or overlap"
assert rejects(claim="nope"), "a claim must be a date"
print("ok")
