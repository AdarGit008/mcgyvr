from solution import staffed_posts

assert staffed_posts([[0, 1], [0]], 2) == 2, "first applicant must be moved along"
assert staffed_posts([[0], [0, 1], [1, 2], [2]], 3) == 3, "chain of reassignments"
assert staffed_posts([[0, 1], [1, 2], [0, 2]], 3) == 3, "everyone fits"
assert staffed_posts([[0], [0], [0]], 2) == 1, "one post cannot take three"
assert staffed_posts([], 3) == 0, "no applicants staffs nothing"
assert staffed_posts([[], [1]], 2) == 1, "an applicant with no posts sits out"
assert (
    staffed_posts([[0, 1], [0, 2], [0, 3], [0]], 4) == 4
), "the picky applicant displaces a whole cascade"
assert staffed_posts([[1, 2], [0, 1], [0], [2], [2, 3]], 4) == 4, "dense overlap"


def rejects(*args):
    try:
        staffed_posts(*args)
    except ValueError:
        return True
    return False


assert rejects([[0]], 0), "zero posts rejected"
assert rejects([[0]], 2.5), "fractional posts rejected"
assert rejects([[7]], 3), "out-of-range post rejected"
assert rejects([[-1]], 3), "negative post rejected"
assert rejects([[0.5]], 3), "fractional post rejected"
print("ok")
