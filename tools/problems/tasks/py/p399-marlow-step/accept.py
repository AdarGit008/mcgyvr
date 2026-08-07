from solution import marlow_step

assert marlow_step("A", 0) == "A", "nought shifted by nothing"
assert marlow_step("A", 1) == "B", "nought up to one"
assert marlow_step("B", -1) == "A", "one back down to nought"
assert marlow_step("A", -1) == "BG", "nought down to minus one"
assert marlow_step("BG", 0) == "BG", "minus one recorded back unchanged"
assert marlow_step("BA", 7) == "A", "minus seven lifted to nought"
assert marlow_step("A", 7) == "BGA", "seven needs three columns"
assert marlow_step("G", 1) == "BGA", "six plus one is seven"
assert marlow_step("G", -6) == "A", "six back to nought"
assert marlow_step("CD", 0) == "CD", "minus eleven survives the round trip"
assert marlow_step("CD", 11) == "A", "minus eleven lifted to nought"
assert marlow_step("GG", 0) == "GG", "minus thirty-six survives too"
assert marlow_step("BAA", 0) == "BAA", "forty-nine is one heavy column"
assert marlow_step("DEF", 100) == "FDA", "a hundred and twenty-four plus a hundred"
assert marlow_step("A", 1000) == "BEAFG", "a thousand from nothing"
assert marlow_step("A", -1000) == "DBDB", "minus a thousand from nothing"


def rejects(*args):
    try:
        marlow_step(*args)
    except ValueError:
        return True
    return False


assert rejects("", 0), "an empty rung-count is rejected"
assert rejects("BH", 0), "a capital past G is rejected"
assert rejects("bg", 0), "lower case is rejected"
assert rejects("AB", 0), "a padding A is rejected"
assert rejects(5, 0), "a number is not a rung-count"
assert rejects("BAAAAAAAAAAA", 0), "eleven capitals is too long"
assert rejects("B", 1.5), "a fractional lift is rejected"
assert rejects("B", 1001), "an oversized lift is rejected"
print("ok")
