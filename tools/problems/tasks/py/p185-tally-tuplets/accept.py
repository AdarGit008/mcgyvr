from solution import tally_tuplets

assert tally_tuplets("1/4 1/4 1/4 1/4", "4/4") == [0], "a measure that lands"
assert tally_tuplets("1/2 1/4", "4/4") == [-16], "a hungry measure"
assert tally_tuplets("1/1 1/4", "4/4") == [16], "an overflowing measure"
assert tally_tuplets("3{1/8+1/8+1/8} 1/4 1/2", "4/4") == [
    0
], "a figure of three squeezes three eighths into one quarter"
assert tally_tuplets("5{1/16+1/16+1/16+1/16+1/16} 1/4 1/4 1/4", "4/4") == [
    0
], "a figure of five"
assert tally_tuplets("7{1/16+1/16+1/16+1/16+1/16+1/16+1/16}", "3/8") == [
    0
], "a figure of seven fills three eighths"
assert tally_tuplets("3/8 1/8", "2/4") == [0], "a numerator above one"
assert tally_tuplets("1/8 1/8 1/8 1/8 1/8 1/8 1/8", "7/8") == [0], "an odd meter"
assert tally_tuplets("1/4 1/4;1/4", "2/4") == [0, -16], "two measures, one short"
assert tally_tuplets("1/4 1/4 1/4 1/4;3{1/4+1/4+1/4};1/2", "4/4") == [
    0,
    -32,
    -32,
], "a squeeze of quarters is worth two of them"
assert tally_tuplets("2{1/8+1/8}", "1/8") == [0], "a figure of two halves the pair"


def rejects(score, meter="4/4"):
    try:
        tally_tuplets(score, meter)
    except ValueError:
        return True
    return False


assert rejects("1/4 1/3"), "a bad denominator is rejected"
assert rejects("1/4 2/4/8"), "a misshapen entry is rejected"
assert rejects("1/4 0/4"), "a zero numerator is rejected"
assert rejects("1/4 01/4"), "a padded numerator is rejected"
assert rejects("1{1/8+1/8}"), "a figure of one is rejected"
assert rejects("3{}"), "an empty squeeze is rejected"
assert rejects("3{1/64+1/64}"), "a fractional squeeze is rejected"
assert rejects("3{1/8+1/8"), "an unclosed brace is rejected"
assert rejects("1/4;;1/4"), "an empty measure is rejected"
assert rejects("1/4", "4/3"), "a bad meter is rejected"
assert rejects("1/4", "0/4"), "a zero meter is rejected"
assert rejects(5), "a non-string score is rejected"
print("ok")
