from solution import hex_groups

assert hex_groups([10], 4) == "0a", "one byte renders two digits"
assert hex_groups([0, 255], 2) == "00ff", "zero pads and the top byte fits"
assert hex_groups([10, 255, 3], 2) == "0aff 03", "a short last group stands alone"
assert hex_groups([10, 255, 3], 1) == "0a ff 03", "width one spaces every byte"
assert hex_groups([1, 2, 3], 8) == "010203", "width past the end makes one group"
assert hex_groups([], 4) == "", "no bytes yield the empty string"


def rejects(*args):
    try:
        hex_groups(*args)
    except Exception:
        return True
    return False


assert rejects("ff", 2), "non-list is rejected"
assert rejects([256], 2), "a byte past 255 is rejected"
assert rejects([2.5], 2), "a fractional byte is rejected"
assert rejects([10], 0), "zero width is rejected"
print("ok")
