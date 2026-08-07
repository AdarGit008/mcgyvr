from solution import slice_repeating_band


def rejects(motifs, strip_width, strip_count):
    try:
        slice_repeating_band(motifs, strip_width, strip_count)
    except ValueError:
        return True
    return False


assert slice_repeating_band([3, 1, 2], 4, 4) == [
    {"motif": 0, "into": 0, "joins": 1, "runs": 0},
    {"motif": 2, "into": 0, "joins": 1, "runs": 0},
    {"motif": 0, "into": 2, "joins": 2, "runs": 1},
    {"motif": 0, "into": 0, "joins": 1, "runs": 2},
], "a three-motif run cut into four-long strips"

assert slice_repeating_band([5], 5, 3) == [
    {"motif": 0, "into": 0, "joins": 0, "runs": 0},
    {"motif": 0, "into": 0, "joins": 0, "runs": 1},
    {"motif": 0, "into": 0, "joins": 0, "runs": 2},
], "one motif as wide as the strip opens every strip afresh"

assert slice_repeating_band([10], 3, 3) == [
    {"motif": 0, "into": 0, "joins": 0, "runs": 0},
    {"motif": 0, "into": 3, "joins": 0, "runs": 0},
    {"motif": 0, "into": 6, "joins": 0, "runs": 0},
], "a strip narrower than the motif never meets a join"

assert slice_repeating_band([2, 3], 12, 1) == [
    {"motif": 0, "into": 0, "joins": 4, "runs": 0}
], "a strip wider than the run swallows several joins"

assert slice_repeating_band([4, 4], 3, 0) == [], "no strips are cut at all"

assert slice_repeating_band([1, 1, 1], 2, 3) == [
    {"motif": 0, "into": 0, "joins": 1, "runs": 0},
    {"motif": 2, "into": 0, "joins": 1, "runs": 0},
    {"motif": 1, "into": 0, "joins": 1, "runs": 1},
], "every unit boundary is a join when the motifs are one long"

assert slice_repeating_band([4, 4], 3, 3) == [
    {"motif": 0, "into": 0, "joins": 0, "runs": 0},
    {"motif": 0, "into": 3, "joins": 1, "runs": 0},
    {"motif": 1, "into": 2, "joins": 1, "runs": 0},
], "the strip opening deep in a motif reports how far into it stands"

assert rejects("3,1", 4, 2), "the motifs must be a list"
assert rejects([], 4, 2), "a run of no motifs is rejected"
assert rejects([3, 0], 4, 2), "a motif of no length is rejected"
assert rejects([3, 1.5], 4, 2), "a fractional motif is rejected"
assert rejects([3, "1"], 4, 2), "a written motif is rejected"
assert rejects([3, 1], 0, 2), "a strip of no width is rejected"
assert rejects([3, 1], 1001, 2), "too wide a strip is rejected"
assert rejects([3, 1], 4, -1), "a negative count is rejected"
assert rejects([3, 1], 4, 501), "too many strips are rejected"
assert rejects([3, 1], 4, 2.5), "a fractional count is rejected"
print("ok")
