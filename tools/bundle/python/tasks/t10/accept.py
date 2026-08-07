from pathlib import Path
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

src = Path("solution.py").read_text().replace(" ", "")
check(".index(" not in src, "contract forbids a.index()")

a = [1, 3, 5, 7, 9, 11]
for x in a:
    got = solution.binary_search(a, x)
    check(got == a.index(x), f"binary_search({a}, {x}) = {got}, want {a.index(x)}")
for x in [0, 4, 12]:
    got = solution.binary_search(a, x)
    check(got == -1, f"binary_search({a}, {x}) = {got}, want -1")
check(solution.binary_search([], 5) == -1, "empty list -> -1")
check(solution.binary_search([2], 2) == 0, "single element found")
check(solution.binary_search([2], 3) == -1, "single element missing")
print("OK")
