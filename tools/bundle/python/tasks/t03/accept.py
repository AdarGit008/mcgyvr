import solution

def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        raise SystemExit(1)

good = [
    ("1.2.3", (1, 2, 3, None)),
    ("0.0.1", (0, 0, 1, None)),
    ("10.20.30", (10, 20, 30, None)),
    ("1.2.3-beta.1", (1, 2, 3, "beta.1")),
    ("2.0.0-rc-1", (2, 0, 0, "rc-1")),
]
for arg, want in good:
    got = solution.parse_semver(arg)
    check(tuple(got) == want, f"parse_semver({arg!r}) = {got!r}, want {want!r}")

bad = ["1.2", "1.2.3.4", "x.2.3", "1.2.3+meta", "", "1..3", "1.2.three"]
for arg in bad:
    try:
        got = solution.parse_semver(arg)
    except ValueError:
        continue
    print(f"FAIL: parse_semver({arg!r}) should raise ValueError, got {got!r}")
    raise SystemExit(1)
print("OK")
