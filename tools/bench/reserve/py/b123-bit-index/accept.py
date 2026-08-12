from solution import build_bit_index, rank_ones, select_one

idx = build_bit_index([2147487753, 4098], 45)
assert idx == {
    "words": [2147487753, 4098],
    "length": 45,
    "prefix": [0, 4, 6],
}, "prefix counts the set bits word by word"
assert build_bit_index([], 0) == {
    "words": [],
    "length": 0,
    "prefix": [0],
}, "a zero-length bitmap has no words"


def rejects(fn, *args):
    try:
        fn(*args)
    except Exception:
        return True
    return False


assert rejects(build_bit_index, [4294967296], 32), "word too wide"
assert rejects(build_bit_index, [0, 0], 32), "word count mismatch"
assert rejects(build_bit_index, [256], 8), "stray bit past length"
assert rank_ones(idx, 13) == 3, "rank inside the first word"
assert rank_ones(idx, 32) == 4, "rank at a word boundary"
assert rank_ones(idx, 45) == 6, "rank at length counts everything"
assert rejects(rank_ones, idx, 46), "rank past length"
assert select_one(idx, 0) == 0, "zeroth set bit"
assert select_one(idx, 1) == 3, "next set bit in the same word"
assert select_one(idx, 2) == 12, "third set bit"
assert select_one(idx, 3) == 31, "set bit at the top of a word"
assert select_one(idx, 4) == 33, "select crosses into the second word"
assert select_one(idx, 5) == 44, "last set bit of the bitmap"
assert rejects(select_one, idx, 6), "rank beyond the total"
assert rejects(select_one, build_bit_index([], 0), 0), "empty bitmap has no ones"
print("ok")
