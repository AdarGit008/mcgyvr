from pathlib import Path
import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

src = Path("solution.py").read_text().replace(" ", "")
check("range(len(" not in src, "refactor must remove range(len(...)) indexing")

users = [
    {"name": "ann", "active": True, "age": 30},
    {"name": "bob", "active": False, "age": 40},
    {"name": "kid", "active": True, "age": 12},
    {"name": "cat", "active": True, "age": 18},
]
got = solution.select_active(users)
check(got == ["ann", "cat"], f"select_active = {got}, want ['ann', 'cat']")
check(solution.select_active([]) == [], "empty input -> []")
print("OK")
