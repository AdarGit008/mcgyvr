from solution import count_lane_span


def rejects(claims):
    try:
        count_lane_span(claims)
    except ValueError:
        return True
    return False


assert count_lane_span(["A:A"]) == 1, "a claim on one lane counts one"
assert count_lane_span(["A:C"]) == 3, "both ends of a claim are kept"
assert count_lane_span(["Z:AA"]) == 2, "AA follows Z however the text sorts"
assert count_lane_span(["A:Z", "AA:AB"]) == 28, "two claims that abut"
assert count_lane_span(["A:C", "E:F"]) == 5, "two claims with a gap between"
assert count_lane_span(["A:C", "B:E"]) == 5, "overlapping claims merge"
assert count_lane_span(["A:E", "B:C"]) == 5, "a nested claim adds nothing"
assert count_lane_span(["A:A", "A:A"]) == 1, "the same claim twice counts once"
assert count_lane_span(["C:E", "A:B"]) == 5, "claims arrive out of order"
assert (
    count_lane_span(["B:D", "A:A", "F:G", "C:H"]) == 8
), "four claims that knit into one run"
assert count_lane_span(["A:ZZZ"]) == 18278, "one claim over the whole sheet"

assert rejects("A:C"), "a bare string is not a batch"
assert rejects([]), "an empty batch is rejected"
assert rejects([5]), "a number is not a claim"
assert rejects(["AC"]), "a claim without a colon"
assert rejects(["A:B:C"]), "a claim with two colons"
assert rejects([":C"]), "a claim with a blank end"
assert rejects(["a:c"]), "lower case is refused"
assert rejects(["AAAA:B"]), "four capitals overrun"
assert rejects(["C:A"]), "a backwards claim is refused"
print("ok")
