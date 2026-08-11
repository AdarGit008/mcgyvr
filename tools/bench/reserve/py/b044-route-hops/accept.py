from solution import route_hops

assert route_hops([], "hub", "hub") == 0, "staying put costs zero links"
assert route_hops([["north", "mill"]], "mill", "north") == 1, "a link is ridden backwards too"
assert route_hops([["a", "b"], ["b", "c"], ["c", "a"]], "a", "c") == 1, "a ring does not trap the search"
assert route_hops(
    [["a", "b"], ["b", "d"], ["a", "c"], ["c", "e"], ["e", "d"]], "a", "d"
) == 2, "the shorter of two routes wins"
assert route_hops([["a", "b"], ["c", "d"]], "a", "d") == -1, "an unreachable goal is -1"


def rejects(*args):
    try:
        route_hops(*args)
    except ValueError:
        return True
    return False


assert rejects([], "", "hub"), "an empty origin is rejected"
assert rejects([], "hub", 7), "a non-string goal is rejected"
assert rejects([["a", "b", "c"]], "a", "b"), "a three-station link is rejected"
assert rejects([["a", ""]], "a", "b"), "an unnamed link station is rejected"
print("ok")
