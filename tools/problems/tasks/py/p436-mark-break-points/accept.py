from solution import hyphenate_word


def rejects(word, rules, min_piece):
    try:
        hyphenate_word(word, rules, min_piece)
    except ValueError:
        return True
    return False


assert hyphenate_word("ledger", ["d-g", "e-r"], 2) == ["led", "ger"], (
    "one break is taken and the late one would leave a single letter"
)
assert hyphenate_word("ledger", ["d-g", "e-r"], 4) == ["ledger"], (
    "a demanding minimum leaves the word whole"
)
assert hyphenate_word("vacation", ["a-tion"], 2) == ["vaca", "tion"], (
    "a pattern may name several letters on a side"
)
assert hyphenate_word("contrast", ["n-t", "t-r"], 2) == ["con", "trast"], (
    "the second place is passed over: it would close a one-letter piece"
)
assert hyphenate_word("contrast", ["n-t", "t-r"], 1) == ["con", "t", "rast"], (
    "a minimum of one lets both places break"
)
assert hyphenate_word("banana", ["a-n"], 1) == ["ba", "na", "na"], (
    "one pattern may permit several places"
)
assert hyphenate_word("banana", ["a-n"], 3) == ["banana"], (
    "every permitted place would leave too short a tail"
)
assert hyphenate_word("stone", [], 1) == ["stone"], "an empty table breaks nothing"
assert hyphenate_word("stone", ["x-y"], 1) == ["stone"], (
    "a pattern the word never matches breaks nothing"
)
assert hyphenate_word("aa", ["a-a"], 1) == ["a", "a"], (
    "the shortest breakable word breaks once"
)

assert rejects(12, ["a-b"], 1), "the word must be a string"
assert rejects("", ["a-b"], 1), "an empty word is rejected"
assert rejects("Word", ["a-b"], 1), "a capital letter is rejected"
assert rejects("we ll", ["a-b"], 1), "a space is rejected"
assert rejects("word", "a-b", 1), "the rules must be a list"
assert rejects("word", [7], 1), "a non-string pattern is rejected"
assert rejects("word", ["ab"], 1), "a pattern without a hyphen is rejected"
assert rejects("word", ["a-b-c"], 1), "two hyphens are rejected"
assert rejects("word", ["-b"], 1), "an empty left side is rejected"
assert rejects("word", ["a-"], 1), "an empty right side is rejected"
assert rejects("word", ["A-b"], 1), "a capital in a pattern is rejected"
assert rejects("word", ["a-b"], 0), "a minimum below one is rejected"
assert rejects("word", ["a-b"], 1.5), "a fractional minimum is rejected"
print("ok")
