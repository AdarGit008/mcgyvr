from solution import read_index_block

assert read_index_block([0]) == [], "a block promising nothing yields nothing"
assert read_index_block([1, 2, 97, 98, 0, 16, 1, 0]) == [["ab", 16, 256]], "one entry with a two-byte name"
assert read_index_block([2, 1, 97, 0, 0, 0, 5, 3, 98, 50, 122, 0, 5, 2, 1]) == [
    ["a", 0, 5],
    ["b2z", 5, 513],
], "two entries of unequal name width follow one another"
assert read_index_block([1, 4, 108, 111, 103, 57, 255, 255, 255, 255]) == [["log9", 65535, 65535]], (
    "an offset and a length that fill their two bytes"
)
assert read_index_block([1, 1, 122, 0, 0, 0, 0]) == [["z", 0, 0]], "an entry of no length at the very front"
assert read_index_block([3, 1, 97, 0, 1, 0, 1, 1, 98, 0, 2, 0, 1, 1, 99, 0, 3, 0, 1]) == [
    ["a", 1, 1],
    ["b", 2, 1],
    ["c", 3, 1],
], "three single-letter entries in rising order"


def rejects(block):
    try:
        read_index_block(block)
    except ValueError:
        return True
    return False


assert rejects(7), "an argument that is not a list is refused"
assert rejects([]), "a block with not even a count is refused"
assert rejects([1, 2, 97, 98, 0, 16, 1]), "a block ending inside an entry is refused"
assert rejects([2, 1, 97, 0, 0, 0, 5]), "a promised entry that never arrives is refused"
assert rejects([1, 0, 0, 0, 0, 0]), "a name of no bytes is refused"
assert rejects([1, 1, 65, 0, 0, 0, 0]), "a capital letter in a name is refused"
assert rejects([1, 1, 45, 0, 0, 0, 0]), "a dash in a name is refused"
assert rejects([2, 1, 98, 0, 0, 0, 1, 1, 97, 0, 1, 0, 1]), "entries out of rising name order are refused"
assert rejects([2, 1, 97, 0, 0, 0, 1, 1, 97, 0, 1, 0, 1]), "one name appearing twice is refused"
assert rejects([0, 9]), "a byte past the last entry is refused"
assert rejects([1, 1, 97, 0, 0, 0, 0, 4]), "a stray tail byte is refused"
assert rejects([0.5]), "a fractional byte is refused"
assert rejects([256]), "a byte above 255 is refused"
assert rejects([-3]), "a byte below nought is refused"
print("ok")
