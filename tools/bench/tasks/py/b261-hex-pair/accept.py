from solution import hex_split, hex_join


def rejects(value):
    try:
        hex_split(value)
    except Exception:
        return True
    return False


assert hex_split("#aabbcc") == ["aa", "bb", "cc"], "three parts in order"
assert hex_split("#ABCDEF") == ["AB", "CD", "EF"], "upper case is kept"
assert rejects("#abc"), "too few digits"
assert rejects("aabbcc"), "the hash is required"
assert hex_join(["AA", "BB", "CC"]) == "#aabbcc", "joined and lower-cased"
assert hex_join(["00", "00", "00"]) == "#000000", "all zeroes"
print("ok")
