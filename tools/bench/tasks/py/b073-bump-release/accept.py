from solution import bump_release

assert bump_release("1.2.3", "major") == "2.0.0", "major resets the rest"
assert bump_release("1.2.3", "minor") == "1.3.0", "minor resets patch"
assert bump_release("1.2.3", "patch") == "1.2.4", "patch advances alone"
assert bump_release("2.9.4", "minor") == "2.10.0", "components carry past 9"
assert bump_release("0.0.0", "major") == "1.0.0", "zero components are valid"


def rejects(*args):
    try:
        bump_release(*args)
    except Exception:
        return True
    return False


assert rejects(42, "major"), "non-string tag is rejected"
assert rejects("1.2", "patch"), "two components are rejected"
assert rejects("1..3", "patch"), "empty component is rejected"
assert rejects("1.02.3", "patch"), "leading zero is rejected"
assert rejects("1.2.x", "patch"), "non-digit component is rejected"
assert rejects("1.2.3", "micro"), "unknown part name is rejected"
print("ok")
