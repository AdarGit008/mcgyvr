from solution import newer_release

assert newer_release("1.10", "1.9") == 1, "minor compares numerically"
assert newer_release("2.0", "1.99") == 1, "major dominates minor"
assert newer_release("1.2", "1.2-rc.3") == 1, "stable beats its own release candidate"
assert newer_release("1.2-rc.3", "1.2") == -1, "and the mirror image agrees"
assert newer_release("1.2-alpha.1", "1.2-dev.9") == 1, (
    "alpha outranks dev whatever the builds"
)
assert newer_release("1.2-beta.1", "1.2-rc.1") == -1, "rc outranks beta"
assert newer_release("0.4-rc.10", "0.4-rc.9") == 1, (
    "builds inside one channel compare numerically"
)
assert newer_release("3.7", "3.7") == 0, "identical stables are the same release"
assert newer_release("1.2-beta.4", "1.2-beta.4") == 0, (
    "identical prereleases are the same release"
)
assert newer_release("1.3-dev.1", "1.2") == 1, (
    "any prerelease of a later minor beats an earlier stable"
)


def rejects(a, b):
    try:
        newer_release(a, b)
    except ValueError:
        return True
    return False


assert rejects("1", "1.0"), "a bare major is rejected"
assert rejects("1.2-gamma.1", "1.0"), "an unknown channel is rejected"
assert rejects("1.2-rc", "1.0"), "a channel without a build is rejected"
assert rejects("01.2", "1.0"), "a leading zero is rejected"
assert rejects(12, "1.0"), "a non-string argument is rejected"
print("ok")
