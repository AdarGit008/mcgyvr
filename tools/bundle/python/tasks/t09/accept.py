import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

for n, want in [(0, 1), (1, 1), (5, 120), (10, 3628800)]:
    got = solution.factorial(n)
    check(got == want, f"factorial({n}) = {got}, want {want}")

try:
    solution.factorial(-1)
    print("FAIL: factorial(-1) should raise ValueError")
    raise SystemExit(1)
except ValueError:
    pass
print("OK")
