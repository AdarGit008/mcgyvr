from solution import pick_flag_variant

flag = {
    "rules": [
        {"match": [["plan", "is", "gold"]], "split": [["full", 100]]},
        {
            "match": [["region", "in", ["eu", "uk"]], ["plan", "not", "free"]],
            "split": [["full", 25], ["lite", 75]],
        },
        {"match": [], "split": [["full", 10], ["off", 0], ["lite", 90]]},
    ],
    "fallback": "off",
}

assert pick_flag_variant(flag, {"traits": {"plan": "gold"}, "bucket": 99}) == {
    "variant": "full",
    "rule": 0,
}, "the first rule takes a gold plan whatever its bucket"
assert pick_flag_variant(
    flag, {"traits": {"region": "eu", "plan": "pro"}, "bucket": 24}
) == {"variant": "full", "rule": 1}, "the last bucket inside the first share"
assert pick_flag_variant(
    flag, {"traits": {"region": "eu", "plan": "pro"}, "bucket": 25}
) == {"variant": "lite", "rule": 1}, "one past the running total crosses to the next entry"
assert pick_flag_variant(flag, {"traits": {"region": "eu"}, "bucket": 0}) == {
    "variant": "full",
    "rule": 1,
}, "a missing trait satisfies a not test"
assert pick_flag_variant(
    flag, {"traits": {"region": "eu", "plan": "free"}, "bucket": 0}
) == {"variant": "full", "rule": 2}, "a free plan falls past the second rule"
assert pick_flag_variant(flag, {"traits": {"region": "us"}, "bucket": 10}) == {
    "variant": "lite",
    "rule": 2,
}, "the zero share is stepped over"
assert pick_flag_variant(flag, {"traits": {}, "bucket": 99}) == {
    "variant": "lite",
    "rule": 2,
}, "the catch-all rule takes a subject with no traits at all"
assert pick_flag_variant(
    {"rules": [], "fallback": "held"}, {"traits": {}, "bucket": 0}
) == {"variant": "held", "rule": -1}, "a flag with no rules answers with its fallback"
assert pick_flag_variant(
    {
        "rules": [{"match": [["plan", "is", "gold"]], "split": [["full", 100]]}],
        "fallback": "held",
    },
    {"traits": {"plan": "pro"}, "bucket": 0},
) == {"variant": "held", "rule": -1}, "no rule taking the subject falls to the fallback"

bad = {"traits": {}, "bucket": 0}


def rejects(one, two):
    try:
        pick_flag_variant(one, two)
    except ValueError:
        return True
    return False


assert rejects({"rules": []}, bad), "a flag without a fallback is rejected"
assert rejects({"rules": {}, "fallback": "off"}, bad), "rules that are not a list are rejected"
assert rejects(
    {"rules": [{"match": [], "split": [["a", 60], ["b", 30]]}], "fallback": "off"}, bad
), "shares adding to 90 are rejected"
assert rejects(
    {"rules": [{"match": [], "split": [["a", 110], ["b", -10]]}], "fallback": "off"}, bad
), "a negative share is rejected"
assert rejects(
    {"rules": [{"match": [], "split": [["a", 50], ["a", 50]]}], "fallback": "off"}, bad
), "a variant named twice in one split is rejected"
assert rejects(
    {"rules": [{"match": [], "split": []}], "fallback": "off"}, bad
), "an empty split is rejected"
assert rejects(
    {
        "rules": [{"match": [["plan", "over", "gold"]], "split": [["a", 100]]}],
        "fallback": "off",
    },
    bad,
), "an unknown test word is rejected"
assert rejects(
    {"rules": [{"match": [["plan", "in", []]], "split": [["a", 100]]}], "fallback": "off"},
    bad,
), "an in test with nothing listed is rejected"
assert rejects(
    {"rules": [{"match": [["plan", "is"]], "split": [["a", 100]]}], "fallback": "off"},
    bad,
), "a two-element test is rejected"
assert rejects(flag, {"traits": {}, "bucket": 100}), "a bucket of 100 is rejected"
assert rejects(flag, {"traits": {}, "bucket": -1}), "a negative bucket is rejected"
assert rejects(flag, {"traits": {"plan": 7}, "bucket": 0}), "a trait holding a number is rejected"
assert rejects(flag, {"bucket": 0}), "a subject without traits is rejected"
print("ok")
