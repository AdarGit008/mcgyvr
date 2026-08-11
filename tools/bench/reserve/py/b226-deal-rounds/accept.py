from solution import deal_rounds

assert deal_rounds("abcdef", 2) == ["ace", "bdf"], "an even deck across two piles"
assert deal_rounds("abcdef", 3) == ["ad", "be", "cf"], "an even deck across three piles"
assert deal_rounds("abcde", 2) == ["ace", "bd"], "an odd card leaves the second pile short"
assert deal_rounds("xyz", 1) == ["xyz"], "one pile takes the deck in order"
assert deal_rounds("", 4) == ["", "", "", ""], "an empty deck yields one empty pile per hand"
assert deal_rounds("ab", 5) == ["a", "b", "", "", ""], "more piles than cards leaves later piles empty"
assert deal_rounds("aabb", 2) == ["ab", "ab"], "repeated cards keep their dealt places"


def rejects(*args):
    try:
        deal_rounds(*args)
    except Exception:
        return True
    return False


assert rejects(42, 2), "a deck that is not a string is rejected"
assert rejects("abc", 0), "a hand count below one is rejected"
assert rejects("abc", 2.5), "a fractional hand count is rejected"
print("ok")
