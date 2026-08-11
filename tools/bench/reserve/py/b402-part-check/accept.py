from solution import part_check

assert part_check(10, [5, 5], 0) is True, "an exact match"
assert part_check(10, [5, 4], 0) is False, "one short with no tolerance"
assert part_check(10, [5, 4], 1) is True, "one short within tolerance"
assert part_check(0, [], 0) is True, "nothing matches nothing"
assert part_check(1, [], 0) is False, "nothing does not match one"
assert part_check(10, [11], 1) is True, "one over is within tolerance too"
print("ok")
