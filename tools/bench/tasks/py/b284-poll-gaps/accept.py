from solution import poll_gaps

assert poll_gaps([1, 2, 4]) == [3], "one minute missed"
assert poll_gaps([1, 2, 3]) == [], "an unbroken run"
assert poll_gaps([5, 9]) == [6, 7, 8], "a long silence"
assert poll_gaps([7]) == [], "one run reports nothing"
assert poll_gaps([]) == [], "no runs at all"
assert poll_gaps([2, 5, 6, 9]) == [3, 4, 7, 8], "two silences in order"
print("ok")
