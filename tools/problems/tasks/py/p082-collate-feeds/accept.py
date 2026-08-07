from solution import collate_feeds

assert collate_feeds([[[1, 5], [4, 7]], [[2, 6], [3, 7]]]) == [
    [1, 5],
    [2, 6],
    [3, 7],
], "interleave, then drop the repeated reading at tick 4"
assert collate_feeds([[[5, 1]], [[5, 2]]]) == [[5, 1]], "tick tie goes to the earliest feed"
assert collate_feeds([[[5, 9]], [[5, 2]], [[5, 4]]]) == [
    [5, 9]
], "three-way tie still goes to feed 0"
assert collate_feeds([[[1, 5], [3, 6]], [[2, 5]]]) == [
    [1, 5],
    [3, 6],
], "a reading repeated across feeds is thinned"
assert collate_feeds([[[1, 4], [2, 4], [3, 5]]]) == [
    [1, 4],
    [3, 5],
], "a reading repeated within one feed is thinned"
assert collate_feeds([[], [[7, 3]], []]) == [[7, 3]], "empty feeds contribute nothing"
assert collate_feeds([]) == [], "no feeds at all"
assert collate_feeds([[], []]) == [], "only empty feeds"
assert collate_feeds([[[1, 2], [2, 3], [3, 2]]]) == [
    [1, 2],
    [2, 3],
    [3, 2],
], "a reading may return after an intervening change"


def rejects(feeds):
    try:
        collate_feeds(feeds)
    except ValueError:
        return True
    return False


assert rejects([[[3, 1], [3, 2]]]), "equal ticks inside one feed are rejected"
assert rejects([[[1, 1]], [[5, 2], [4, 3]]]), "decreasing ticks inside one feed are rejected"
print("ok")
