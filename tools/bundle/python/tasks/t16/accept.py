import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

for n, want in [(0, 0), (1, 1), (2, 1), (10, 55), (20, 6765)]:
    got = solution.fib(n)
    check(got == want, f"fib({n}) = {got}, want {want}")

got = solution.fib(90)
check(got == 2880067194370816120, f"fib(90) = {got}, want 2880067194370816120")

try:
    solution.fib(-1)
    print("FAIL: fib(-1) should raise ValueError")
    raise SystemExit(1)
except ValueError:
    pass
print("OK")
