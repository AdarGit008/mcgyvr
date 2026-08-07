from solution import expand_shorthand

BOOK = {
    "asap": "as soon as possible",
    "bldg": "building",
    "n": "north",
    "rd": "road",
}

assert (
    expand_shorthand("asap", BOOK) == "as soon as possible"
), "a lowercase word takes the value as written"
assert (
    expand_shorthand("ASAP", BOOK) == "AS SOON AS POSSIBLE"
), "an uppercase word raises every letter of the value"
assert (
    expand_shorthand("Asap", BOOK) == "As soon as possible"
), "a capitalised word raises only the opening character"
assert expand_shorthand("AsAp", BOOK) == "AsAp", "a word cased any other way is left alone"
assert (
    expand_shorthand("Meet at bldg 4 ASAP.", BOOK)
    == "Meet at building 4 AS SOON AS POSSIBLE."
), "a whole line is rewritten word by word"
assert (
    expand_shorthand("re-asap", BOOK) == "re-as soon as possible"
), "a hyphen breaks a word so the tail is looked up"
assert (
    expand_shorthand("asaply", BOOK) == "asaply"
), "a longer word holding the shorthand is not touched"
assert (
    expand_shorthand("bldg9", BOOK) == "bldg9"
), "trailing digits make a different word"
assert (
    expand_shorthand("N and n and Rd", BOOK) == "NORTH and north and Road"
), "a lone capital follows the uppercase rule"
assert (
    expand_shorthand("a b", {"a": "b", "b": "c"}) == "b c"
), "what a value writes into the text is never looked up again"
assert expand_shorthand("", BOOK) == "", "empty text stays empty"
assert (
    expand_shorthand("Bldg 7, off the RD.", BOOK) == "Building 7, off the ROAD."
), "punctuation around a word survives the rewrite"
assert (
    expand_shorthand("constructor toString", {"asap": "x"}) == "constructor toString"
), "a word the table never held is not fetched from anywhere else"


def rejects(text, table):
    try:
        expand_shorthand(text, table)
    except ValueError:
        return True
    return False


assert rejects(42, BOOK), "a text that is not a string is rejected"
assert rejects("asap", ["asap"]), "a table that is not a mapping is rejected"
assert rejects("asap", {"AS": "alongside"}), "an uppercase key is rejected"
assert rejects("asap", {"1st": "first"}), "a key beginning with a digit is rejected"
assert rejects("asap", {"as ap": "x"}), "a key holding a space is rejected"
assert rejects("asap", {"asap": ""}), "an empty value is rejected"
assert rejects("asap", {"asap": 7}), "a value that is not a string is rejected"
print("ok")
