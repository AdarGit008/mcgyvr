from solution import order_skein_hands

assert order_skein_hands([["3m", "3r", "3s", "3v", "8m"]]) == {
    "grades": ["monolith"],
    "order": [0],
}, "two pips make a monolith"
assert order_skein_hands(
    [
        ["1m", "3r", "5s", "7v", "9m"],
        ["1m", "2m", "3m", "4r", "5r"],
        ["1m", "2m", "4m", "7m", "10m"],
        ["4m", "4r", "7s", "7v", "9m"],
        ["5m", "5r", "6s", "8v", "10m"],
    ]
) == {
    "grades": ["prism", "chain", "drift", "echo", "twin"],
    "order": [0, 1, 3, 4, 2],
}, "one hand of each remaining grade"
assert order_skein_hands(
    [["3m", "3r", "3s", "8m", "8v"], ["2m", "2r", "9s", "9v", "9m"]]
) == {
    "grades": ["monolith", "monolith"],
    "order": [1, 0],
}, "the ladder leads with the pip most cards carry"
assert order_skein_hands(
    [["4v", "4s", "6v", "8s", "10v"], ["4m", "4r", "6s", "8v", "10m"]]
) == {
    "grades": ["twin", "twin"],
    "order": [1, 0],
}, "matching ladders fall to the house weights"
assert order_skein_hands(
    [["1m", "2r", "4s", "7v", "9m"], ["1m", "2r", "4s", "7v", "9m"]]
) == {
    "grades": ["prism", "prism"],
    "order": [0, 1],
}, "level hands keep the order they arrived in"
assert order_skein_hands([["2s", "3s", "4v", "5v", "6m"]]) == {
    "grades": ["chain"],
    "order": [0],
}, "three houses cannot make a prism"
assert order_skein_hands(
    [["1m", "2m", "4m", "7m", "10m"], ["5m", "5r", "6s", "8v", "10m"]]
) == {
    "grades": ["drift", "twin"],
    "order": [1, 0],
}, "drift sits below every named grade"


def rejects(value):
    try:
        order_skein_hands(value)
    except ValueError:
        return True
    return False


assert rejects("hands"), "a non-list argument is rejected"
assert rejects([]), "an empty list of hands is rejected"
assert rejects([["1m", "2m", "3m", "4m"]]), "a hand of four cards is rejected"
assert rejects(["1m2m3m"]), "a hand that is not a list is rejected"
assert rejects([["1m", "2m", "3m", "4m", "11m"]]), "a pip above ten is rejected"
assert rejects([["1m", "2m", "3m", "4m", "5x"]]), "an unknown house letter is rejected"
assert rejects([["01m", "2m", "3m", "4m", "5m"]]), "a padded pip is rejected"
assert rejects([["1m", "1m", "2m", "3m", "4m"]]), "a card written twice is rejected"
assert rejects([["1m", "2m", "3m", "4m", 5]]), "a card that is not a string is rejected"
print("ok")
