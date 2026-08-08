from solution import flatline_spans

assert flatline_spans([1, 1, 1, 2, 2, 3], 2) == [
    [0, 2],
    [3, 4],
], "a stretch exactly as long as least counts"
assert flatline_spans([4, 4, 4], 3) == [[0, 2]], "a stretch may fill the channel"
assert flatline_spans([4, 4, 4], 4) == [], "a stretch shorter than least is dropped"
assert flatline_spans([2, 2, 3, 3, 3], 3) == [[2, 4]], "the stretch closing the channel is reported"
assert flatline_spans([2, 2, 2, 3, 4, 4], 2) == [
    [0, 2],
    [4, 5],
], "several stretches come back in opening order"
assert flatline_spans([0, 0, 0, 0], 2) == [[0, 3]], "one maximal stretch, not many"
assert flatline_spans([7, 8, 9], 2) == [], "a channel that never repeats is flat nowhere"
assert flatline_spans([], 2) == [], "an empty channel reports nothing"
assert flatline_spans([5], 2) == [], "a single sample is too short"
assert flatline_spans([-3, -3, -3, -3, 6], 4) == [
    [0, 3]
], "negative samples repeat like any other"


def rejects(channel, least):
    try:
        flatline_spans(channel, least)
    except ValueError:
        return True
    return False


assert rejects([1, 1], 1), "a least of one is rejected"
assert rejects([1, 1], 2.5), "a fractional least is rejected"
assert rejects([1, 1], "3"), "a non-numeric least is rejected"
print("ok")
