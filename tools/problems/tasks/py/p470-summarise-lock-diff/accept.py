from solution import summarise_lock_diff

BEFORE = {
    "alpha": "1.9",
    "bravo": "2.0.0",
    "delta": "0.1",
    "echo": "1.2",
    "foxtrot": "3.4.5",
    "hotel": "5.0",
    "india": "1.0.0",
}
AFTER = {
    "bravo": "2.0.0",
    "charlie": "0.0.1",
    "delta": "0.0.9",
    "echo": "1.2.0",
    "alpha": "1.10",
    "zulu": "1.0",
    "golf": "2.2",
    "hotel": "4.9.9",
    "india": "1.0.1",
}

assert summarise_lock_diff(BEFORE, AFTER) == {
    "added": ["charlie", "golf", "zulu"],
    "dropped": ["foxtrot"],
    "lifted": ["alpha", "india"],
    "lowered": ["delta", "hotel"],
}, "the four buckets, each sorted, over a record that moved every way at once"

assert summarise_lock_diff({}, {}) == {
    "added": [],
    "dropped": [],
    "lifted": [],
    "lowered": [],
}, "two empty records differ in nothing"

assert summarise_lock_diff({"pkg": "1"}, {"pkg": "1.0.0"}) == {
    "added": [],
    "dropped": [],
    "lifted": [],
    "lowered": [],
}, "trailing noughts do not make a new release"

assert summarise_lock_diff({"pkg": "1.9"}, {"pkg": "1.10"}) == {
    "added": [],
    "dropped": [],
    "lifted": ["pkg"],
    "lowered": [],
}, "groups rank as numbers, not as text"

assert summarise_lock_diff({"pkg": "1.10"}, {"pkg": "1.9"}) == {
    "added": [],
    "dropped": [],
    "lifted": [],
    "lowered": ["pkg"],
}, "the same comparison read the other way round"

assert summarise_lock_diff({"pkg": "0.0.0"}, {"pkg": "0.0.1"}) == {
    "added": [],
    "dropped": [],
    "lifted": ["pkg"],
    "lowered": [],
}, "a lone nought is a legal group"

assert summarise_lock_diff({"zeta": "1.0", "alfa": "1.0"}, {}) == {
    "added": [],
    "dropped": ["alfa", "zeta"],
    "lifted": [],
    "lowered": [],
}, "the dropped list is sorted too"

assert summarise_lock_diff({"pkg": "2.0.0.1"}, {"pkg": "2.0.0.0"}) == {
    "added": [],
    "dropped": [],
    "lifted": [],
    "lowered": ["pkg"],
}, "a fourth group ranks like any other"


def rejects(before, after):
    try:
        summarise_lock_diff(before, after)
    except ValueError:
        return True
    return False


assert rejects("nope", {}), "a record that is not a mapping is rejected"
assert rejects({"pkg": "01.2"}, {}), "a leading nought in a group is rejected"
assert rejects({"pkg": ""}, {}), "an empty release is rejected"
assert rejects({"pkg": "1.2."}, {}), "a trailing full stop is rejected"
assert rejects({"pkg": "1.2-beta"}, {}), "anything but digits and full stops is rejected"
assert rejects({"pkg": 12}, {}), "a release that is not a string is rejected"
assert rejects({"": "1.0"}, {}), "an empty package name is rejected"
print("ok")
