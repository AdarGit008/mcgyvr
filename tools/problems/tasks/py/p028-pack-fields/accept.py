from solution import pack_fields

assert pack_fields([4, 4], [10, 3]) == 163, "two nibbles, high then low"
assert pack_fields([4, 4], [3, 10]) == 58, "swapped values change the result"
assert pack_fields([1, 3, 4], [1, 5, 9]) == 217, "mixed widths"
assert pack_fields([8], [255]) == 255, "single full byte"
assert pack_fields([4, 4], [0, 15]) == 15, "leading zero field keeps its width"
assert pack_fields([3, 3], [0, 0]) == 0, "all-zero fields pack to zero"
assert pack_fields([15, 15], [32767, 32767]) == 1073741823, "full 30 bits"
assert pack_fields([2, 2, 2], [1, 2, 3]) == 27, "three two-bit fields"


def rejects(widths, values):
    try:
        pack_fields(widths, values)
    except ValueError:
        return True
    return False


assert rejects([4, 4], [1]), "unequal lengths are rejected"
assert rejects([], []), "empty lists are rejected"
assert rejects([0, 4], [0, 1]), "zero width is rejected"
assert rejects([16, 15], [0, 0]), "31 combined bits are rejected"
assert rejects([4], [16]), "oversized value is rejected"
assert rejects([4], [-1]), "negative value is rejected"
assert rejects([4], [1.5]), "fractional value is rejected"
print("ok")
