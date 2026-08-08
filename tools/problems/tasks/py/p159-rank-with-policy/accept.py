from solution import rank_with_policy

scores = [40, 10, 30, 30, 10]
assert rank_with_policy(scores, "dense", "asc") == [
    3,
    1,
    2,
    2,
    1,
], "dense ascending never skips"
assert rank_with_policy(scores, "gapped", "asc") == [
    5,
    1,
    3,
    3,
    1,
], "gapped ascending opens gaps after ties"
assert rank_with_policy(scores, "entry", "asc") == [
    5,
    1,
    3,
    4,
    2,
], "entry ascending breaks ties by input order"
assert rank_with_policy(scores, "dense", "desc") == [
    1,
    3,
    2,
    2,
    3,
], "dense descending"
assert rank_with_policy(scores, "gapped", "desc") == [
    1,
    4,
    2,
    2,
    4,
], "gapped descending"
assert rank_with_policy(scores, "entry", "desc") == [
    1,
    4,
    2,
    3,
    5,
], "entry descending"
assert rank_with_policy([7, 7, 7], "entry", "asc") == [
    1,
    2,
    3,
], "entry splits an all-equal field by position"
assert rank_with_policy([7, 7, 7], "gapped", "desc") == [
    1,
    1,
    1,
], "gapped keeps an all-equal field at one"


def rejects(*args):
    try:
        rank_with_policy(*args)
    except ValueError:
        return True
    return False


assert rejects([], "dense", "asc"), "empty list"
assert rejects([1, 2.5], "dense", "asc"), "fractional score"
assert rejects([1, 2], "standard", "asc"), "unknown policy"
assert rejects([1, 2], "dense", "down"), "unknown direction"
print("ok")
