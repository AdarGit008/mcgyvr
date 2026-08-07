from solution import split_even_bands

LEAGUE = [
    {"who": "a", "mark": 90},
    {"who": "b", "mark": 80},
    {"who": "c", "mark": 80},
    {"who": "d", "mark": 80},
    {"who": "e", "mark": 50},
    {"who": "f", "mark": 10},
]

assert split_even_bands(LEAGUE, 3) == [
    {"who": "a", "band": 1},
    {"who": "b", "band": 1},
    {"who": "c", "band": 1},
    {"who": "d", "band": 1},
    {"who": "e", "band": 3},
    {"who": "f", "band": 3},
], "a tie drags its whole group into the lowest band any of them was handed"

assert split_even_bands(
    [
        {"who": "p", "mark": 40},
        {"who": "q", "mark": 30},
        {"who": "r", "mark": 20},
        {"who": "s", "mark": 10},
    ],
    2,
) == [
    {"who": "p", "band": 1},
    {"who": "q", "band": 1},
    {"who": "r", "band": 2},
    {"who": "s", "band": 2},
], "four members with no ties split cleanly in two"

assert split_even_bands(LEAGUE, 1) == [
    {"who": member["who"], "band": 1} for member in LEAGUE
], "one band holds everybody"

assert split_even_bands(
    [{"who": "zed", "mark": 5}, {"who": "ash", "mark": 5}, {"who": "moe", "mark": 9}], 3
) == [
    {"who": "zed", "band": 2},
    {"who": "ash", "band": 2},
    {"who": "moe", "band": 1},
], "a tie is settled by the name and then bound together again"

assert split_even_bands(
    [{"who": "one", "mark": 7}, {"who": "two", "mark": 3}, {"who": "six", "mark": 0}], 3
) == [
    {"who": "one", "band": 1},
    {"who": "two", "band": 2},
    {"who": "six", "band": 3},
], "as many bands as members gives each its own"

assert split_even_bands([{"who": "solo", "mark": 0}], 1) == [
    {"who": "solo", "band": 1}
], "one member fills the only band"


def rejects(entries, bands):
    try:
        split_even_bands(entries, bands)
    except ValueError:
        return True
    return False


assert rejects("league", 2), "entries must be a list"
assert rejects([], 1), "an empty league is rejected"
assert rejects(["a"], 1), "an entry must be a record"
assert rejects([{"who": "", "mark": 4}], 1), "an empty who is rejected"
assert rejects(
    [{"who": "twin", "mark": 4}, {"who": "twin", "mark": 5}], 1
), "a repeated who is rejected"
assert rejects([{"who": "a", "mark": -3}], 1), "a negative mark is rejected"
assert rejects([{"who": "a", "mark": 1.5}], 1), "a fractional mark is rejected"
assert rejects(LEAGUE, 0), "a band count of nought is rejected"
assert rejects(LEAGUE, 7), "more bands than members is rejected"
assert rejects(LEAGUE, 2.5), "a fractional band count is rejected"
print("ok")
