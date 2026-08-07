import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [
    (([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]),
    (([1, 2, 3, 4], 2), [[1, 2], [3, 4]]),
    (([], 3), []),
    (([1], 5), [[1]]),
    ((["a", "b", "c"], 1), [["a"], ["b"], ["c"]]),
]
for (items, size), want in cases:
    got = solution.chunk_list(items, size)
    got = [list(c) for c in got]
    check(got == want, f"chunk_list({items}, {size}) = {got}, want {want}")

for bad in (0, -2):
    try:
        solution.chunk_list([1, 2], bad)
        print(f"FAIL: chunk_list(_, {bad}) should raise ValueError")
        raise SystemExit(1)
    except ValueError:
        pass
print("OK")
