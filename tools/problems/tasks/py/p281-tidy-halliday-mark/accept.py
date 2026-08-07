from solution import tidy_shelf_mark

assert tidy_shelf_mark("GB-207.5-k3") == "GB-207.5-k3", "a tidy mark is left alone"
assert tidy_shelf_mark("gb-207.5-K3") == "GB-207.5-k3", "wing up, peg down"
assert tidy_shelf_mark("  GB - 007.50 - k3  ") == "GB-7.5-k3", "spaces and padding go"
assert tidy_shelf_mark("GB-207.00-k3") == "GB-207-k3", "an empty fraction loses the dot"
assert tidy_shelf_mark("GB-012-a9") == "GB-12-a9", "left padding falls away"
assert tidy_shelf_mark("ZZ-999.99-z1") == "ZZ-999.99-z1", "the far end of the range"
assert tidy_shelf_mark("Mn-000042.100-Q7") == "MN-42.1-q7", "every tidying at once"


def rejects(raw):
    try:
        tidy_shelf_mark(raw)
    except ValueError:
        return True
    return False


assert rejects("G-1-a1"), "a one-letter wing is rejected"
assert rejects("GBC-1-a1"), "a three-letter wing is rejected"
assert rejects("GB-0-a1"), "a bay of nought is rejected"
assert rejects("GB-1000-a1"), "a bay past 999 is rejected"
assert rejects("GB-1.234-a1"), "a fraction of three digits is rejected"
assert rejects("GB-1.-a1"), "a dangling dot is rejected"
assert rejects("GB-1-a0"), "a peg digit of nought is rejected"
assert rejects("GB-1-ab"), "a peg of two letters is rejected"
assert rejects("GB-1"), "a mark of two parts is rejected"
assert rejects("GB-1-a1-x"), "a mark of four parts is rejected"
assert rejects(5), "a mark that is not a string is rejected"
print("ok")
