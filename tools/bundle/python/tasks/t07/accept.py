import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

cases = [
    ([1, [2, [3, 4]], 5], [1, 2, 3, 4, 5]),
    ([], []),
    ([[], [[]]], []),
    (["ab", ["cd"]], ["ab", "cd"]),
    ([(1, 2), [3]], [(1, 2), 3]),
    ([[[[1]]]], [1]),
]
for arg, want in cases:
    got = solution.flatten(arg)
    check(got == want, f"flatten({arg}) = {got}, want {want}")

deep = [0]
for _ in range(60):
    deep = [deep, 1]
got = solution.flatten(deep)
check(got == [0] + [1] * 60, f"60-level nesting failed: got {got[:5]}... len={len(got)}")
print("OK")
