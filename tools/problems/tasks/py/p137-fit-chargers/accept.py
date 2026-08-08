from solution import fit_chargers

BENCH = [
    {"plug": "A", "low": 5, "high": 10},
    {"plug": "B", "low": 5, "high": 10},
    {"plug": "A", "low": 0, "high": 100},
]

assert fit_chargers(BENCH, [{"plug": "A", "draw": 5}]) == [
    0
], "the low boundary is safe, and the lowest index wins"
assert fit_chargers(BENCH, [{"plug": "A", "draw": 10}]) == [
    0
], "the high boundary is safe too"
assert fit_chargers(
    BENCH, [{"plug": "A", "draw": 7}, {"plug": "A", "draw": 7}]
) == [0, 2], "a handed-out charger is never handed out again"
assert fit_chargers(BENCH, [{"plug": "B", "draw": 7}]) == [
    1
], "the plug must match, not just the range"
assert fit_chargers(BENCH, [{"plug": "C", "draw": 7}]) == [
    -1
], "an unknown plug gets -1"
assert fit_chargers(BENCH, [{"plug": "A", "draw": 999}]) == [
    -1
], "a draw beyond every range gets -1"
assert fit_chargers(BENCH, []) == [], "no devices, no entries"
assert fit_chargers(
    BENCH,
    [
        {"plug": "A", "draw": 5},
        {"plug": "B", "draw": 5},
        {"plug": "A", "draw": 6},
        {"plug": "A", "draw": 6},
    ],
) == [0, 1, 2, -1], "the bench empties in order and the last device goes without"
print("ok")
