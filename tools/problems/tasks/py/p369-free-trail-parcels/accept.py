from solution import free_trail_parcels


def rejects(depth, issued):
    try:
        free_trail_parcels(depth, issued)
    except ValueError:
        return True
    return False


assert free_trail_parcels(3, ["LL"]) == [
    "LR",
    "R",
], "the sibling of an issued parcel stands, and the far half folds up whole"
assert free_trail_parcels(3, []) == [
    ""
], "an estate with nothing issued is one free parcel, the empty run"
assert free_trail_parcels(3, [""]) == [], "issuing the empty run leaves nothing at all"
assert free_trail_parcels(2, ["LL", "LR", "RL"]) == [
    "RR"
], "a parent both of whose halves are issued is not free itself"
assert free_trail_parcels(3, ["LLL"]) == [
    "LLR",
    "LR",
    "R",
], "the free remainder climbs back up one level at a time"
assert free_trail_parcels(1, ["L"]) == [
    "R"
], "the shallowest estate has just the one sibling left"
assert free_trail_parcels(3, ["R", "LL"]) == [
    "LR"
], "two issued parcels at different depths leave a single gap"
assert free_trail_parcels(4, ["LLL", "LR", "RRRR"]) == [
    "LLR",
    "RL",
    "RRL",
    "RRRL",
], "the report runs from the first address held to the last"

assert rejects(0, []), "a depth below one is rejected"
assert rejects(9, []), "a depth past eight is rejected"
assert rejects(2.5, []), "a fractional depth is rejected"
assert rejects(3, ["LX"]), "a letter outside L and R is rejected"
assert rejects(2, ["LLL"]), "a parcel longer than the depth is rejected"
assert rejects(3, ["L", "LL"]), "an issued parcel holding another is rejected"
assert rejects(3, ["LR", "LR"]), "the same parcel issued twice is rejected"
assert rejects(3, [7]), "a parcel that is not a string is rejected"
assert rejects(3, "LL"), "issued parcels that are not a list are rejected"
print("ok")
