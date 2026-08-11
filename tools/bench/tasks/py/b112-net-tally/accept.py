from solution import net_tally

assert net_tally(["mug|4|1"]) == "mug    3\ntotal  3", "a single row reports"
assert net_tally(["mug|4|1", "mug|2|0"]) == "mug    5\ntotal  5", "an item sums across sheets"
assert net_tally(["pot|5|0\ncup|3|1"]) == "cup    2\npot    5\ntotal  7", "items sort by name"
assert (
    net_tally(["espresso|10|4"]) == "espresso  6\ntotal     6"
), "the longest name sets the padding width"
assert (
    net_tally(["\n  mug | 4 | 1  \n\n"]) == "mug    3\ntotal  3"
), "blank rows are skipped and fields are trimmed"
assert net_tally(["jar|2|2"]) == "jar    0\ntotal  0", "a zero net renders"
assert net_tally([]) == "", "no sheets yields the empty string"
assert net_tally(["\n   \n"]) == "", "only blank rows yields the empty string"


def rejects(value):
    try:
        net_tally(value)
    except ValueError:
        return True
    return False


assert rejects(7), "a non-list argument is rejected"
assert rejects([3]), "a non-string sheet is rejected"
assert rejects(["mug|4"]), "a two-field row is rejected"
assert rejects(["|1|0"]), "an empty item name is rejected"
assert rejects(["mug|4.5|0"]), "a fractional count is rejected"
assert rejects(["mug|1|0", "mug|0|3"]), "returns exceeding sales are rejected"
print("ok")
