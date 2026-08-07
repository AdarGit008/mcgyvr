from solution import read_vault_header

assert read_vault_header([86, 76, 84, 1, 0, 0, 0]) == {
    "version": 1,
    "size": 0,
    "sealed": False,
    "packed": False,
    "stamp": 0,
}, "an old-edition header with no body at all"
assert read_vault_header([86, 76, 84, 1, 0, 3, 1, 9, 9, 9]) == {
    "version": 1,
    "size": 3,
    "sealed": True,
    "packed": False,
    "stamp": 0,
}, "the low flag reads as sealed"
assert read_vault_header([86, 76, 84, 1, 0, 1, 2, 7]) == {
    "version": 1,
    "size": 1,
    "sealed": False,
    "packed": True,
    "stamp": 0,
}, "the next flag reads as packed"
assert read_vault_header([86, 76, 84, 1, 0, 0, 3]) == {
    "version": 1,
    "size": 0,
    "sealed": True,
    "packed": True,
    "stamp": 0,
}, "both flags may stand together"
assert read_vault_header([86, 76, 84, 2, 0, 2, 0, 0, 0, 1, 44, 5, 6]) == {
    "version": 2,
    "size": 2,
    "sealed": False,
    "packed": False,
    "stamp": 300,
}, "the new edition carries a four-byte stamp"
assert read_vault_header([86, 76, 84, 2, 1, 0, 3, 255, 255, 255, 255] + [0] * 256) == {
    "version": 2,
    "size": 256,
    "sealed": True,
    "packed": True,
    "stamp": 4294967295,
}, "a size and a stamp that fill their fields"


def rejects(run):
    try:
        read_vault_header(run)
    except ValueError:
        return True
    return False


assert rejects("VLT"), "an argument that is not a list is refused"
assert rejects([86, 76, 84, 1, 0, 0, 256]), "a value above 255 is refused"
assert rejects([86, 76, 84, 1, 0, 0, -1]), "a value below nought is refused"
assert rejects([86, 76, 84, 1, 0, 0, 1.5]), "a fractional value is refused"
assert rejects([86, 76]), "a run too short for the marker is refused"
assert rejects([86, 76, 85, 1, 0, 0, 0]), "the wrong marker is refused"
assert rejects([86, 76, 84, 3, 0, 0, 0]), "an edition the reader does not know is refused"
assert rejects([86, 76, 84, 1, 0, 0]), "an old header cut short is refused"
assert rejects([86, 76, 84, 2, 0, 0, 0, 0, 0, 0]), "a new header cut short is refused"
assert rejects([86, 76, 84, 1, 0, 0, 4]), "a flag the reader does not know is refused"
assert rejects([86, 76, 84, 1, 0, 0, 128]), "the top flag bit is refused"
assert rejects([86, 76, 84, 1, 0, 3, 0, 9, 9]), "a body shorter than declared is refused"
assert rejects([86, 76, 84, 1, 0, 1, 0, 9, 9]), "a body longer than declared is refused"
assert rejects([86, 76, 84, 2, 0, 1, 0, 0, 0, 0, 0]), "a new-edition body missing altogether is refused"
print("ok")
