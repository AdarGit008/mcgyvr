from solution import hex_ring_walk

assert hex_ring_walk([0, 0], 1) == [
    [-1, 1],
    [0, 1],
    [1, 0],
    [1, -1],
    [0, -1],
    [-1, 0],
], "radius one opens southwest of the centre and runs east first"
assert hex_ring_walk([3, -2], 0) == [[3, -2]], "radius zero is the centre alone"
assert hex_ring_walk([2, -1], 1) == [
    [1, 0],
    [2, 0],
    [3, -1],
    [3, -2],
    [2, -2],
    [1, -1],
], "the walk translates with the centre"
assert hex_ring_walk([0, 0], 2) == [
    [-2, 2],
    [-1, 2],
    [0, 2],
    [1, 1],
    [2, 0],
    [2, -1],
    [2, -2],
    [1, -2],
    [0, -2],
    [-1, -1],
    [-2, 0],
    [-2, 1],
], "radius two visits twelve cells, two per direction"

wide = hex_ring_walk([0, 0], 3)
assert len(wide) == 18, "a ring of radius three holds eighteen cells"
assert wide[0] == [-3, 3], "the walk opens three southwest steps out"
assert wide[17] == [-3, 2], "the final cell neighbours the opening cell"
assert len({tuple(cell) for cell in wide}) == 18, "no cell is recorded twice"
assert all(
    (abs(q) + abs(r) + abs(q + r)) // 2 == 3 for q, r in wide
), "every recorded cell stands three steps from the centre"

off = hex_ring_walk([-4, 7], 2)
assert off[0] == [-6, 9], "a far centre still opens southwest"
assert len(off) == 12, "a far centre keeps the twelve-cell count"


def rejects(center, radius):
    try:
        hex_ring_walk(center, radius)
    except ValueError:
        return True
    return False


assert rejects([0], 1), "a one-element centre is rejected"
assert rejects([0, 0, 0], 1), "a three-element centre is rejected"
assert rejects([0, 1.5], 1), "a fractional coordinate is rejected"
assert rejects("00", 1), "a non-address centre is rejected"
assert rejects([0, 0], -1), "a negative radius is rejected"
assert rejects([0, 0], 2.5), "a fractional radius is rejected"
assert rejects([0, 0], True), "a boolean radius is rejected"
assert rejects([True, 0], 1), "a boolean coordinate is rejected"
print("ok")
