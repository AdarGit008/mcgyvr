from solution import count_leaflet_picks


def rejects(value):
    try:
        count_leaflet_picks(value)
    except ValueError:
        return True
    return False


assert count_leaflet_picks("7") == 1, "a bare figure names one page"
assert count_leaflet_picks("3-7") == 5, "a hyphen item counts both ends"
assert count_leaflet_picks("12+4") == 5, "a plus item counts the page and its followers"
assert count_leaflet_picks("4-4") == 1, "a hyphen item may name one page"
assert count_leaflet_picks("4+1") == 2, "the smallest plus item"
assert count_leaflet_picks("1,2,3") == 3, "three bare figures"
assert count_leaflet_picks("1-5,4-8") == 8, "overlapping spans count once"
assert count_leaflet_picks("1-3,3-5") == 5, "spans touching at one page"
assert count_leaflet_picks("10,10,10") == 1, "a page repeated is still one page"
assert count_leaflet_picks("20-24,22+5") == 8, "a plus item reaching past a span"
assert count_leaflet_picks("1-9999") == 9999, "the whole leaflet"
assert count_leaflet_picks("9999") == 1, "the last page alone"
assert count_leaflet_picks("9995+4") == 5, "a plus item ending on the last page"
assert count_leaflet_picks("100,7-9,2") == 5, "items need not be in order"

assert rejects(""), "an empty list is refused"
assert rejects(42), "a non-string is refused"
assert rejects("1, 2"), "a blank is refused"
assert rejects("1,,2"), "an empty item is refused"
assert rejects("1,"), "a trailing comma is refused"
assert rejects("1;2"), "an outside character is refused"
assert rejects("03"), "a leading nought is refused"
assert rejects("0"), "a page of nought is refused"
assert rejects("7-3"), "a backwards span is refused"
assert rejects("5+0"), "a plus item carrying nothing is refused"
assert rejects("9999+1"), "a plus item past the last page is refused"
assert rejects("9998-10001"), "a span past the last page is refused"
assert rejects("1-2-3"), "two hyphens in one item are refused"
assert rejects("1-2+3"), "two operators in one item are refused"
assert rejects("-4"), "an item opening with a hyphen is refused"
print("ok")
