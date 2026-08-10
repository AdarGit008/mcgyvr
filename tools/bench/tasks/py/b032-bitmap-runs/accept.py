from solution import bit_at, find_free_run, occupy_run

assert find_free_run([0], 32, 1) == 0, "empty map allocates at zero"
assert find_free_run([9], 32, 2) == 1, "gap between occupied blocks"
assert find_free_run([2147483647, 0], 64, 3) == 31, "run crossing a word boundary"
assert find_free_run([4294967295], 32, 1) == -1, "full map has no run"
assert find_free_run([0], 10, 10) == 0, "run exactly filling the capacity"
assert find_free_run([0], 10, 11) == -1, "run longer than the capacity"
assert find_free_run([51], 32, 2) == 2, "smallest start wins"
assert find_free_run([4294967295, 6], 64, 2) == 35, "gap inside the second word"
assert find_free_run(occupy_run([0, 0], 0, 40), 64, 3) == 40, "search after occupation"
assert bit_at([6], 1) == 1, "set bit reads one"
assert bit_at([0, 8], 35) == 1, "bit in the second word"
assert occupy_run([0], 2, 3) == [28], "run marked in one word"
assert occupy_run([0, 0], 30, 4) == [3221225472, 3], "run marked across words"
base = [0]
occupy_run(base, 0, 1)
assert base == [0], "occupation does not modify its argument"


def rejects(fn, *args):
    try:
        fn(*args)
    except ValueError:
        return True
    return False


assert rejects(find_free_run, [4294967296], 32, 1), "word above the maximum"
assert rejects(find_free_run, [1.5], 32, 1), "fractional word"
assert rejects(find_free_run, [0], 0, 1), "capacity of zero"
assert rejects(find_free_run, [0, 0], 32, 1), "word count disagrees with capacity"
assert rejects(find_free_run, [1024], 10, 1), "stray bit beyond the capacity"
assert rejects(find_free_run, [0], 32, 0), "run length of zero"
assert rejects(bit_at, [0], 32), "index outside the words"
assert rejects(occupy_run, [1], 0, 1), "run touching an occupied block"
assert rejects(occupy_run, [0], 30, 3), "run leaving the words"
print("ok")
