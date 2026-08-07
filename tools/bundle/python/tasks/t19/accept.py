import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

check(solution.safe_divide(6, 3) == 2.0, "safe_divide(6,3) should be 2.0")
check(solution.safe_divide(7, 2) == 3.5, "safe_divide(7,2) should be 3.5")
check(solution.safe_divide(-9, 3.0) == -3.0, "float divisor should work")
check(solution.safe_divide(1, 0) is None, "b=0 -> None")
check(solution.safe_divide(1, 0.0) is None, "b=0.0 -> None")
check(solution.safe_divide(0, 5) == 0.0, "a=0 is fine")

for a, b in [("x", 1), (1, "x"), (None, 1), (1, None), ([1], 2),
             (True, 2), (4, False)]:
    try:
        got = solution.safe_divide(a, b)
    except TypeError:
        continue
    print(f"FAIL: safe_divide({a!r}, {b!r}) should raise TypeError, got {got!r}")
    raise SystemExit(1)
print("OK")
