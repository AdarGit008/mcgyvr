from solution import base_write


def rejects(value, base):
    try:
        base_write(value, base)
    except Exception:
        return True
    return False


assert base_write(5, 2) == "101", "a count in base two"
assert base_write(255, 16) == "ff", "letters carry the values above nine"
assert base_write(8, 8) == "10", "a count that rolls to the next place"
assert base_write(9, 10) == "9", "a single figure"
assert base_write(0, 2) == "0", "a count of nothing"
assert rejects(5, 1), "a base below two is rejected"
assert rejects(5, 17), "a base above sixteen is rejected"
print("ok")
