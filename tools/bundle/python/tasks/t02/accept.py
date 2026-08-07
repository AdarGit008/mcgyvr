import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [
    ([[1, 3], [2, 6], [8, 10]], [[1, 6], [8, 10]]),
    ([[1, 2], [2, 3]], [[1, 3]]),
    ([[5, 7], [1, 3]], [[1, 3], [5, 7]]),
    ([], []),
    ([[4, 4]], [[4, 4]]),
    ([[1, 10], [2, 3], [4, 5]], [[1, 10]]),
]
for arg, want in cases:
    got = solution.merge_intervals(arg)
    got = [list(iv) for iv in got]
    check(got == want, f"merge_intervals({arg}) = {got}, want {want}")

original = [[2, 6], [1, 3]]
snapshot = [list(iv) for iv in original]
solution.merge_intervals(original)
check(original == snapshot, f"input was mutated: {original} != {snapshot}")
print("OK")
