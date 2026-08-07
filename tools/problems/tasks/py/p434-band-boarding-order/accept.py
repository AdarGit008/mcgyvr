from solution import order_boarding_bands


def rejects(layout, rows, band, passengers):
    try:
        order_boarding_bands(layout, rows, band, passengers)
    except ValueError:
        return True
    return False


assert order_boarding_bands(
    "ABC|DEF",
    10,
    3,
    [["ann", "10A"], ["bob", "10C"], ["cid", "8F"], ["dot", "7B"], ["eve", "1D"]],
) == ["ann", "cid", "bob", "dot", "eve"], (
    "bands run tail first and windows precede aisles inside a band"
)

assert order_boarding_bands(
    "ABC|DEF",
    3,
    3,
    [["p1", "3A"], ["p2", "3B"], ["p3", "3C"], ["p4", "3D"], ["p5", "3E"], ["p6", "3F"]],
) == ["p1", "p6", "p2", "p5", "p3", "p4"], (
    "one row sorts window, middle, aisle and then by layout place"
)

assert order_boarding_bands("ABC|DEF", 5, 5, [["far", "5F"], ["near", "5A"]]) == [
    "near",
    "far",
], "a tie on band, class and row falls to the layout order"

assert order_boarding_bands("ABC|DEF", 10, 3, [["front", "7A"], ["back", "8C"]]) == [
    "back",
    "front",
], "an aisle seat in the rear band is called before a window seat ahead of it"

assert order_boarding_bands(
    "A|BC", 2, 2, [["mid", "2B"], ["nook", "2C"], ["odd", "1A"]]
) == ["nook", "odd", "mid"], (
    "a one-seat side still yields a window seat at each far end"
)

assert order_boarding_bands("AB|CD", 4, 2, []) == [], "nobody to call"

assert order_boarding_bands(
    "AB|CD", 5, 2, [["q1", "1A"], ["q2", "5D"], ["q3", "4C"]]
) == ["q2", "q3", "q1"], "the frontmost band comes up short and is called last"

assert rejects(7, 4, 2, []), "the layout must be a string"
assert rejects("ABCDEF", 4, 2, []), "no aisle bar is rejected"
assert rejects("A|B|C", 4, 2, []), "two aisle bars are rejected"
assert rejects("|ABC", 4, 2, []), "an empty side is rejected"
assert rejects("Ab|CD", 4, 2, []), "a lowercase letter is rejected"
assert rejects("AB|BC", 4, 2, []), "a repeated letter is rejected"
assert rejects("AB|CD", 0, 2, []), "a cabin without rows is rejected"
assert rejects("AB|CD", 4, 0, []), "a band of no rows is rejected"
assert rejects("AB|CD", 4, 2, "x"), "the passengers must be a list"
assert rejects("AB|CD", 4, 2, [["solo"]]), "a one-part passenger is rejected"
assert rejects("AB|CD", 4, 2, [["", "1A"]]), "an empty name is rejected"
assert rejects("AB|CD", 4, 2, [["twin", "1A"], ["twin", "2A"]]), "a shared name is rejected"
assert rejects("AB|CD", 4, 2, [["x", "A1"]]), "a reversed seat is rejected"
assert rejects("AB|CD", 4, 2, [["x", "9A"]]), "a row past the tail is rejected"
assert rejects("AB|CD", 4, 2, [["x", "1Z"]]), "an unknown letter is rejected"
assert rejects("AB|CD", 4, 2, [["x", "2C"], ["y", "2C"]]), "two passengers in one seat are rejected"
print("ok")
