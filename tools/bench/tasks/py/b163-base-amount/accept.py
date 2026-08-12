from solution import base_amount

DEFS = {"bale": [4, "ream"], "ream": [20, "quire"], "quire": [25, "sheet"]}

assert base_amount(7, "sheet", DEFS, "sheet") == 7, "the base unit is already converted"
assert base_amount(3, "quire", DEFS, "sheet") == 75, "one definition unwinds"
assert base_amount(2, "ream", DEFS, "sheet") == 1000, "two definitions unwind"
assert base_amount(1, "bale", DEFS, "sheet") == 2000, "the whole chain unwinds"
assert base_amount(0, "bale", DEFS, "sheet") == 0, "zero of any unit is zero"
assert base_amount(5, "sheet", {}, "sheet") == 5, "empty defs still serve the base unit"


def rejects(*args):
    try:
        base_amount(*args)
    except Exception:
        return True
    return False


assert rejects(-1, "ream", DEFS, "sheet"), "a negative amount is rejected"
assert rejects(2.5, "ream", DEFS, "sheet"), "a fractional amount is rejected"
assert rejects(1, "box", DEFS, "sheet"), "an unknown unit is rejected"
assert rejects(1, "sack", {"sack": [0, "sheet"]}, "sheet"), "a zero factor is rejected"
assert rejects(1, "loop", {"loop": [2, "loop"]}, "sheet"), "a chain that loops is rejected"
print("ok")
