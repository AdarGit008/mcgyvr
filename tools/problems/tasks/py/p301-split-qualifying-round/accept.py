from solution import split_qualifying_round


def field(count):
    return [f"s{n:02d}" for n in range(1, count + 1)]


def rejects(entrants):
    try:
        split_qualifying_round(entrants)
    except ValueError:
        return True
    return False


assert split_qualifying_round(["a", "b"]) == {
    "direct": ["a", "b"],
    "qualifying": [],
}, "two entrants are already a power of two"
assert split_qualifying_round(["a", "b", "c"]) == {
    "direct": ["a"],
    "qualifying": [["b", "c"]],
}, "a surplus of one sends the two weakest to qualifying"
assert split_qualifying_round(["a", "b", "c", "d"]) == {
    "direct": ["a", "b", "c", "d"],
    "qualifying": [],
}, "four walk in untroubled"
assert split_qualifying_round(["a", "b", "c", "d", "e"]) == {
    "direct": ["a", "b", "c"],
    "qualifying": [["d", "e"]],
}, "five leaves a surplus of one over a draw of four"
assert split_qualifying_round(["a", "b", "c", "d", "e", "f"]) == {
    "direct": ["a", "b"],
    "qualifying": [["c", "f"], ["d", "e"]],
}, "six draws two qualifying matches from the weakest four"
assert split_qualifying_round(["a", "b", "c", "d", "e", "f", "g"]) == {
    "direct": ["a"],
    "qualifying": [["b", "g"], ["c", "f"], ["d", "e"]],
}, "seven leaves only the top seed walking in"
assert split_qualifying_round(field(8)) == {
    "direct": field(8),
    "qualifying": [],
}, "eight is a power of two and plays nothing"
assert split_qualifying_round(field(9)) == {
    "direct": field(7),
    "qualifying": [["s08", "s09"]],
}, "nine sends only the last two down"
assert split_qualifying_round(field(12)) == {
    "direct": field(4),
    "qualifying": [
        ["s05", "s12"],
        ["s06", "s11"],
        ["s07", "s10"],
        ["s08", "s09"],
    ],
}, "twelve draws four matches inward from the weakest eight"

assert rejects("ab"), "the field is a list"
assert rejects(["a"]), "one entrant is no field"
assert rejects([]), "an empty field is no field"
assert rejects(["a", 2]), "a name is a string"
assert rejects(["a", "a"]), "a name is listed once"
print("ok")
