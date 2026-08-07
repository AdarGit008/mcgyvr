from solution import align_border_motifs


def rejects(widths, pattern_length):
    try:
        align_border_motifs(widths, pattern_length)
    except ValueError:
        return True
    return False


assert align_border_motifs([3, 5, 2, 6], 4) == {
    "edges": [0, 3, 0, 2],
    "freshAt": 3,
}, "the running total is reduced against the run at every edge"
assert align_border_motifs([4, 4, 4], 4) == {"edges": [0, 0, 0], "freshAt": 2}, (
    "a strip as wide as the run starts every strip fresh"
)
assert align_border_motifs([5], 3) == {"edges": [0], "freshAt": 0}, (
    "a lone strip has no strip after it"
)
assert align_border_motifs([2, 3, 4], 10) == {"edges": [0, 2, 5], "freshAt": 0}, (
    "a long run may never come back round"
)
assert align_border_motifs([3, 4], 1) == {"edges": [0, 0], "freshAt": 2}, (
    "a run of one motif starts fresh everywhere"
)
assert align_border_motifs([6, 9, 5], 4) == {"edges": [0, 2, 3], "freshAt": 0}, (
    "wide strips still report a motif inside the run"
)
assert align_border_motifs([7, 3, 4, 7], 7) == {
    "edges": [0, 0, 3, 0],
    "freshAt": 2,
}, "the earliest fresh start after the leading strip is the one reported"
assert align_border_motifs([100, 100, 100], 7) == {
    "edges": [0, 2, 4],
    "freshAt": 0,
}, "large widths reduce the same way"

assert rejects("3,4", 4), "the widths must be a list"
assert rejects([], 4), "an empty wall is rejected"
assert rejects([3, 0], 4), "a strip of no motifs is rejected"
assert rejects([3, -2], 4), "a negative width is rejected"
assert rejects([3, 2.5], 4), "a fractional width is rejected"
assert rejects([3, "4"], 4), "a written width is rejected"
assert rejects([3, 4], 0), "a run of no motifs is rejected"
assert rejects([3, 4], 2.5), "a fractional run is rejected"
print("ok")
