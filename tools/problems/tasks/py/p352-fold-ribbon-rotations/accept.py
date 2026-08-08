from solution import fold_ribbon_rotations

assert fold_ribbon_rotations("banana") == {
    "line": "annb|aa",
    "home": 4,
}, "the stated banana example"
assert fold_ribbon_rotations("a") == {"line": "a|", "home": 1}, "a single letter"
assert fold_ribbon_rotations("ribbon") == {
    "line": "nibrob|",
    "home": 6,
}, "the glued ribbon can seat last"
assert fold_ribbon_rotations("abab") == {
    "line": "bb|aa",
    "home": 2,
}, "a repeating ribbon"
assert fold_ribbon_rotations("sea shell") == {
    "line": "laeshsle| ",
    "home": 8,
}, "the space ranks under every letter"
assert fold_ribbon_rotations("zab") == {
    "line": "bza|",
    "home": 3,
}, "the marker must rank ahead of z"
assert (
    fold_ribbon_rotations("mississippi")["line"] == "ipssm|pissii"
), "only the closing symbols are joined"


def rejects(value):
    try:
        fold_ribbon_rotations(value)
    except ValueError:
        return True
    return False


assert rejects(17), "a ribbon that is not a string is thrown out"
assert rejects(""), "an empty ribbon is thrown out"
assert rejects("ba|na"), "a ribbon already carrying the marker is thrown out"
assert rejects("Banana"), "an uppercase symbol is thrown out"
assert rejects("one-two"), "punctuation is thrown out"
print("ok")
