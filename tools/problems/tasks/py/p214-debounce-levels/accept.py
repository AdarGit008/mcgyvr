from solution import debounce_levels


def rejects(samples, hold):
    try:
        debounce_levels(samples, hold)
    except ValueError:
        return True
    return False


assert debounce_levels([1], 3) == [1], "a single sample settles itself"
assert debounce_levels([0, 1, 1, 0, 1, 1, 1, 0], 1) == [
    0,
    1,
    1,
    0,
    1,
    1,
    1,
    0,
], "a hold of one believes everything"
assert debounce_levels([0, 1, 1, 0, 1, 1, 1, 0], 2) == [
    0,
    0,
    1,
    1,
    1,
    1,
    1,
    1,
], "two samples in a row are believed"
assert debounce_levels([1, 0, 0, 0, 1], 3) == [
    1,
    1,
    1,
    0,
    0,
], "the flip lands on the sample that completes the run"
assert debounce_levels([0, 1, 1, 1, 1], 5) == [
    0,
    0,
    0,
    0,
    0,
], "a run that never reaches hold changes nothing"
assert debounce_levels([0, 1, 0, 1, 0, 1], 2) == [
    0,
    0,
    0,
    0,
    0,
    0,
], "chatter clears the tally every other sample"
assert debounce_levels([0, 0, 0], 2) == [0, 0, 0], "a quiet line stays put"
assert debounce_levels([1, 0, 0, 1, 1, 0, 0], 2) == [
    1,
    1,
    0,
    0,
    1,
    1,
    0,
], "the level flips back and forth when each run is long enough"

assert rejects("0101", 2), "a sample list that is not a list is rejected"
assert rejects([], 2), "an empty line is rejected"
assert rejects([0, 2, 1], 2), "a sample outside 0 and 1 is rejected"
assert rejects([0, "1"], 2), "a sample that is not a number is rejected"
assert rejects([0, 1], 0), "a hold of zero is rejected"
assert rejects([0, 1], -3), "a negative hold is rejected"
assert rejects([0, 1], 2.5), "a hold that is not whole is rejected"

print("ok")
