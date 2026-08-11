from solution import billed_airtime

assert billed_airtime(0, 30, 6) == 0, "a zero-second call bills nothing"
assert billed_airtime(1, 30, 6) == 30, "a short call bills the whole initial block"
assert billed_airtime(30, 30, 6) == 30, "the initial boundary bills exactly itself"
assert billed_airtime(31, 30, 6) == 36, "one second past the block starts a step"
assert billed_airtime(42, 30, 6) == 42, "a step boundary bills exactly itself"
assert billed_airtime(61, 60, 10) == 70, "another tariff bills its own steps"


def rejects(*args):
    try:
        billed_airtime(*args)
    except Exception:
        return True
    return False


assert rejects(-1, 30, 6), "negative duration is rejected"
assert rejects(10.5, 30, 6), "fractional duration is rejected"
assert rejects(10, 0, 6), "zero initial block is rejected"
assert rejects(10, 30, 0), "zero step is rejected"
print("ok")
