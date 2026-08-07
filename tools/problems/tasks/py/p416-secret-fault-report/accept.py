from solution import report_secret_faults

# Every phrase below is nonsense stitched together here for the check.
head = "Ab3"
house = {
    "least": 8,
    "most": 16,
    "needs": ["lower", "upper", "digit"],
    "forbidden": ["woof", "meow"],
}

assert report_secret_faults(head + "defgh", house) == [], (
    "a phrase meeting every rule breaks none"
)
assert report_secret_faults(head, house) == ["short"], (
    "a phrase under least is short"
)
assert report_secret_faults(head + "defghijklmnopq", house) == ["long"], (
    "a phrase over most is long"
)
assert report_secret_faults("abcdefgh", house) == ["upper", "digit"], (
    "missing classes come out in the fixed class order"
)
assert report_secret_faults("ABCDEFGH", house) == ["lower", "digit"], (
    "lower is named before digit however needs was written"
)
assert report_secret_faults(head + " defgh", house) == ["stray"], (
    "a space belongs to no class"
)
assert report_secret_faults(head + "woofxx", house) == ["forbidden"], (
    "a forbidden word inside the phrase is caught"
)
assert report_secret_faults(head + "WOOFxx", house) == ["forbidden"], (
    "the phrase is lowered before the forbidden words are sought"
)
assert report_secret_faults("ab", house) == ["short", "upper", "digit"], (
    "length comes before the classes"
)
assert report_secret_faults("ab~", house) == [
    "short",
    "stray",
    "upper",
    "digit",
], "stray sits between the length rules and the classes"
assert report_secret_faults("ab" + "meow" + "~", house) == [
    "short",
    "stray",
    "upper",
    "digit",
    "forbidden",
], "forbidden is always last on the list"

marky = {"least": 1, "most": 20, "needs": ["mark"], "forbidden": []}
assert report_secret_faults("abcdefgh", marky) == ["mark"], (
    "a policy needing a mark reports its absence"
)
assert report_secret_faults("abcdefg!", marky) == [], (
    "an exclamation counts as a mark"
)
assert report_secret_faults(head + "-", marky) == [], (
    "the hyphen is one of the ten marks"
)
assert report_secret_faults("", marky) == ["short", "mark"], (
    "an empty phrase is short and classless"
)


def rejects(one, two):
    try:
        report_secret_faults(one, two)
    except ValueError:
        return True
    return False


assert rejects(42, house), "a phrase that is a number is rejected"
assert rejects("abcdefgh", {"least": 8, "most": 16, "needs": ["lower"]}), (
    "a policy without forbidden is rejected"
)
assert rejects(
    "abcdefgh", {"least": 0, "most": 16, "needs": ["lower"], "forbidden": []}
), "a least of zero is rejected"
assert rejects(
    "abcdefgh", {"least": 9, "most": 8, "needs": ["lower"], "forbidden": []}
), "a most below least is rejected"
assert rejects(
    "abcdefgh", {"least": 1, "most": 8, "needs": [], "forbidden": []}
), "an empty needs list is rejected"
assert rejects(
    "abcdefgh", {"least": 1, "most": 8, "needs": ["vowel"], "forbidden": []}
), "a class outside the four is rejected"
assert rejects(
    "abcdefgh", {"least": 1, "most": 8, "needs": ["lower", "lower"], "forbidden": []}
), "one class named twice is rejected"
assert rejects(
    "abcdefgh", {"least": 1, "most": 8, "needs": ["lower"], "forbidden": ["Woof"]}
), "a forbidden word with a capital is rejected"
assert rejects(
    "abcdefgh", {"least": 1, "most": 8, "needs": ["lower"], "forbidden": [""]}
), "an empty forbidden word is rejected"
assert rejects("abcdefgh", ["lower"]), "a policy given as a list is rejected"
print("ok")
