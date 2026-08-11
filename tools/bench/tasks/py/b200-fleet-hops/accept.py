from solution import fleet_hops


def rejects(count, lts, builds, hop):
    try:
        fleet_hops(count, lts, builds, hop)
    except ValueError:
        return True
    return False


assert fleet_hops(4, [], [0], 3) == 1, "a hop that reaches the newest release ends the climb"
assert fleet_hops(6, [], [0], 2) == 3, "a short hop crosses five releases in three moves"
assert fleet_hops(5, [1], [0], 3) == 2, "a long-term-support release cuts the first hop short"
assert fleet_hops(5, [], [4], 3) == 0, "a device on the newest release stays put"
assert fleet_hops(6, [2, 4], [0, 3], 5) == 5, "two devices past two support releases sum their hops"
assert fleet_hops(3, [], [0, 1], 10) == 2, "a hop reaching beyond the newest release lands on it"
assert rejects(4, [], [7], 2), "a device above the published run is rejected"
print("ok")
