from solution import ladder_convert

LADDER = [["cup", "tbsp", 16], ["tbsp", "tsp", 3]]

assert ladder_convert(LADDER, 2, "cup", "tbsp") == 32, "one hop downward multiplies"
assert (
    ladder_convert(LADDER, 1, "cup", "tsp") == 48
), "a downward conversion crosses the whole ladder"
assert ladder_convert(LADDER, 96, "tsp", "cup") == 2, "an exact upward conversion divides"
assert ladder_convert(LADDER, 7, "tbsp", "tbsp") == 7, "same unit returns the amount"
assert ladder_convert(LADDER, 0, "tsp", "cup") == 0, "zero converts to zero"
assert (
    ladder_convert(
        [["tbsp", "tsp", 3], ["gal", "cup", 16], ["cup", "tbsp", 16]], 1, "gal", "tsp"
    )
    == 768
), "rule order does not matter"


def rejects(rules, amount, source, goal):
    try:
        ladder_convert(rules, amount, source, goal)
    except ValueError:
        return True
    return False


assert rejects(LADDER, -1, "cup", "tsp"), "negative amount is rejected"
assert rejects([["pack", "piece", 1]], 1, "pack", "piece"), "a factor below two is rejected"
assert rejects(
    [["case", "box", 2], ["case", "tray", 3]], 1, "case", "box"
), "a unit on the bigger side of two rules is rejected"
assert rejects(
    [["case", "box", 2], ["pallet", "crate", 3]], 1, "case", "box"
), "disconnected rules are rejected"
assert rejects(LADDER, 1, "cup", "oz"), "an unknown unit is rejected"
assert rejects(LADDER, 5, "tsp", "tbsp"), "an inexact upward conversion is rejected"
print("ok")
