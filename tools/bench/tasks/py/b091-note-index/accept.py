from solution import build_word_index, words_of_line

assert words_of_line("Ship-Shape, 2nd try!") == [
    "ship",
    "shape",
    "2nd",
    "try",
], "the helper splits and lowercases"
assert words_of_line("...") == [], "the helper finds nothing in punctuation"
assert build_word_index("tea time") == {"tea": [1], "time": [1]}, "one line, two words"
assert build_word_index("tea tea tea") == {"tea": [1]}, "a word repeating on a line lists it once"
assert build_word_index("milk\nmilk sugar\nsugar") == {
    "milk": [1, 2],
    "sugar": [2, 3],
}, "line numbers accumulate in increasing order"
assert build_word_index("jam\n\njam") == {"jam": [1, 3]}, "a blank line still counts in the numbering"
assert build_word_index("Tea\nTEA tea") == {"tea": [1, 2]}, "case folds before indexing"
assert build_word_index("") == {}, "an empty note has an empty index"
assert build_word_index("\n\n") == {}, "blank lines alone index nothing"
assert build_word_index("to-do: buy jam\nbuy milk, buy bread") == {
    "to": [1],
    "do": [1],
    "buy": [1, 2],
    "jam": [1],
    "milk": [2],
    "bread": [2],
}, "punctuation separates words on every line"


def rejects(value):
    try:
        build_word_index(value)
    except ValueError:
        return True
    return False


assert rejects(42), "a number is rejected"
assert rejects(None), "None is rejected"
assert rejects(["tea"]), "a list is rejected"
print("ok")
