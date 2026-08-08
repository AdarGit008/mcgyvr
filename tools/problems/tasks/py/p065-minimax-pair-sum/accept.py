from solution import minimax_pair_sum

assert minimax_pair_sum([1, 2, 3], [1, 2, 3]) == 4, "beats in-order pairing's 6"
left = [5, 1, 8]
right = [3, 9, 2]
assert minimax_pair_sum(left, right) == 10, "small carries the big partner"
assert left == [5, 1, 8], "first list is left unmodified"
assert right == [3, 9, 2], "second list is left unmodified"
assert minimax_pair_sum([-5, 0, 5], [10, -10, 0]) == 5, "negatives absorb peaks"
assert minimax_pair_sum([7], [7]) == 14, "single pair has no choice"
assert minimax_pair_sum([4, 4, 4, 4], [1, 2, 3, 4]) == 8, "duplicates on one side"


def rejects(*args):
    try:
        minimax_pair_sum(*args)
    except ValueError:
        return True
    return False


assert rejects([1, 2], [1]), "unequal lengths rejected"
assert rejects([], []), "empty lists rejected"
assert rejects([1, 2.5], [3, 4]), "fractional entry rejected"
assert rejects([1, 2], [3, "4"]), "string entry rejected"
print("ok")
