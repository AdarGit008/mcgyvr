from solution import rescale_recipe

assert rescale_recipe(["1 tsp salt"], 3, 2) == [
    "1 1/2 tsp salt"
], "a whole count can grow into a whole count and a part"
assert rescale_recipe(["1/3 cup oats"], 1, 1) == [
    "3/8 cup oats"
], "a third of a cup lands on the nearest eighth"
assert rescale_recipe(["2 egg white"], 1, 2) == ["1 egg white"], "eggs round on a whole"
assert rescale_recipe(["1 tsp salt"], 1, 100) == [
    "1/4 tsp salt"
], "nothing at all becomes one grain"
assert rescale_recipe(["1 tsp salt"], 1, 8) == [
    "1/4 tsp salt"
], "exactly half a grain rounds upward"
assert rescale_recipe(["3 g yeast"], 1, 2) == [
    "2 g yeast"
], "one and a half grams rounds up to two"
assert rescale_recipe(["1 1/2 cup flour"], 2, 1) == [
    "3 cup flour"
], "a mixed amount can double into a bare count"
assert rescale_recipe(["2 tbsp oil"], 1, 3) == [
    "1/2 tbsp oil"
], "two thirds of a tablespoon falls to a half"
assert rescale_recipe(["3/4 cup sugar"], 3, 1) == [
    "2 1/4 cup sugar"
], "a part can grow past one and be respelled"
assert rescale_recipe(["1/4 cup cocoa"], 4, 1) == [
    "1 cup cocoa"
], "a part can land exactly on a whole"
assert rescale_recipe(["1 tsp salt", "2 egg white", "1/2 cup milk"], 3, 2) == [
    "1 1/2 tsp salt",
    "3 egg white",
    "3/4 cup milk",
], "every row is pulled by the same ratio"
assert rescale_recipe([], 2, 1) == [], "an empty recipe stays empty"


def rejects(lines, num, den):
    try:
        rescale_recipe(lines, num, den)
    except ValueError:
        return True
    return False


assert rejects("1 tsp salt", 1, 1), "a recipe that is not a list is rejected"
assert rejects([7], 1, 1), "a row that is not a string is rejected"
assert rejects(["2 cups salt"], 1, 1), "an unknown unit is rejected"
assert rejects(["0 tsp salt"], 1, 1), "a whole count of zero is rejected"
assert rejects(["01 tsp salt"], 1, 1), "a padded count is rejected"
assert rejects(["2/4 tsp salt"], 1, 1), "a part that is not reduced is rejected"
assert rejects(["5/4 tsp salt"], 1, 1), "a part that is not below one is rejected"
assert rejects(["1 2 tsp salt"], 1, 1), "a whole count followed by another is rejected"
assert rejects(["2 tsp salt2"], 1, 1), "a digit in the ingredient is rejected"
assert rejects(["2 tsp  salt"], 1, 1), "a doubled space is rejected"
assert rejects(["1 tsp salt", "2 tsp salt"], 1, 1), "two rows carrying one ingredient are rejected"
assert rejects(["1 tsp salt"], 0, 1), "a numerator of zero is rejected"
assert rejects(["1 tsp salt"], 1, 0), "a denominator of zero is rejected"
assert rejects(["1 tsp salt"], 1.5, 1), "a fractional ratio side is rejected"
assert rejects(["1 tsp salt"], 1, "2"), "a ratio side that is not a number is rejected"
print("ok")
