from solution import order_releases

assert order_releases([]) == [], "no tags"
assert order_releases(["1.2.10", "1.2.9", "1.2.2"]) == [
    "1.2.2",
    "1.2.9",
    "1.2.10",
], "patch numbers compare numerically"
assert order_releases(["1.4.0", "1.4.0-rc.1"]) == [
    "1.4.0-rc.1",
    "1.4.0",
], "a candidate precedes its finished release"
assert order_releases(["1.4.0-rc.10", "1.4.0-rc.2"]) == [
    "1.4.0-rc.2",
    "1.4.0-rc.10",
], "candidate numbers compare numerically"
assert order_releases(["0.9.0", "1.0.0-rc.2", "1.0.0", "1.0.0-rc.10", "2.0.0"]) == [
    "0.9.0",
    "1.0.0-rc.2",
    "1.0.0-rc.10",
    "1.0.0",
    "2.0.0",
], "majors, candidates and releases interleave correctly"
kept = ["2.0.0", "1.0.0"]
order_releases(kept)
assert kept == ["2.0.0", "1.0.0"], "the given list is left untouched"


def rejects(tags):
    try:
        order_releases(tags)
    except Exception:
        return True
    return False


assert rejects("1.0.0"), "non-list argument is rejected"
assert rejects([7]), "non-string tag is rejected"
assert rejects(["1.2"]), "two-number tag is rejected"
assert rejects(["1.02.3"]), "leading zero is rejected"
assert rejects(["1.2.3-rc.0"]), "candidate zero is rejected"
assert rejects(["1.0.0", "1.0.0"]), "repeated tag is rejected"
print("ok")
