from solution import grade_bars

assert grade_bars("q q q q", 4, 4) == ["exact"], "four quarters fill 4/4"
assert grade_bars("q q q|q q q q|h h h", 4, 4) == [
    "short",
    "exact",
    "long",
], "the three verdicts in one line"
assert grade_bars("q. e", 2, 4) == ["exact"], "a dot adds half again"
assert grade_bars("h.", 3, 4) == ["exact"], "a dotted half fills 3/4"
assert grade_bars("e e e e e e e", 7, 8) == ["exact"], "seven eighths fill 7/8"
assert grade_bars("w", 1, 1) == ["exact"], "one whole fills 1/1"
assert grade_bars("s s s", 1, 16) == ["long"], "three sixteenths overrun"
assert grade_bars("s", 1, 8) == ["short"], "a sixteenth underfills 1/8"
assert grade_bars("h h|w.", 1, 2) == [
    "long",
    "long",
], "both bars run past a half-bar meter"
assert grade_bars("q e. s|q q q q", 4, 4) == [
    "short",
    "exact",
], "dots inside a mixed bar"


def rejects(line, beats=4, unit=4):
    try:
        grade_bars(line, beats, unit)
    except ValueError:
        return True
    return False


assert rejects("q x"), "an unknown letter is rejected"
assert rejects("q.."), "two full stops are rejected"
assert rejects("q||q"), "an empty bar is rejected"
assert rejects("q q q q", 4, 3), "an odd unit is rejected"
assert rejects("q q q q", 0, 4), "zero beats is rejected"
assert rejects(9), "a non-string line is rejected"
print("ok")
