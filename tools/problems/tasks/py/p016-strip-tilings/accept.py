from solution import count_strip_tilings

assert count_strip_tilings(0) == 1, "empty strip has the empty covering"
assert count_strip_tilings(1) == 1, "one column takes one upright domino"
assert count_strip_tilings(2) == 3, "two columns: two uprights, two flats, or a square"
assert count_strip_tilings(3) == 5, "three columns"
assert count_strip_tilings(4) == 11, "four columns"
assert count_strip_tilings(5) == 21, "five columns"
assert count_strip_tilings(7) == 85, "seven columns"
assert count_strip_tilings(12) == 2731, "twelve columns"
assert count_strip_tilings(20) == 699051, "twenty columns"
assert count_strip_tilings(40) == 733007751851, (
    "forty columns needs better than blind recursion"
)


def rejects(width):
    try:
        count_strip_tilings(width)
    except ValueError:
        return True
    return False


assert rejects(-1), "negative width rejected"
assert rejects(2.5), "fractional width rejected"
print("ok")
