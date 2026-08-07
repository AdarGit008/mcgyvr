from solution import spell_count_words

assert spell_count_words(0) == "zero", "zero is its own small word"
assert spell_count_words(7) == "seven", "single figure"
assert spell_count_words(13) == "thirteen", "teens are small words"
assert spell_count_words(19) == "nineteen", "last small word"
assert spell_count_words(20) == "twenty", "round word alone"
assert spell_count_words(42) == "forty-two", "round word hyphenated"
assert spell_count_words(90) == "ninety", "highest round word"
assert spell_count_words(100) == "one hundred", "bare hundred"
assert spell_count_words(305) == "three hundred and five", "hundred with small leftover"
assert spell_count_words(760) == "seven hundred and sixty", "hundred with round leftover"
assert spell_count_words(999) == "nine hundred and ninety-nine", "largest under a thousand"
assert spell_count_words(1000) == "one thousand", "bare thousand"
assert spell_count_words(1005) == "one thousand and five", "small leftover takes the word and"
assert spell_count_words(1200) == "one thousand two hundred", "big leftover takes a plain blank"
assert spell_count_words(21015) == "twenty-one thousand and fifteen", "hyphenated thousands"
assert spell_count_words(100000) == "one hundred thousand", "hundred thousand exactly"
assert (
    spell_count_words(999999)
    == "nine hundred and ninety-nine thousand nine hundred and ninety-nine"
), "the ceiling"


def rejects(value):
    try:
        spell_count_words(value)
    except ValueError:
        return True
    return False


assert rejects(-1), "below zero is refused"
assert rejects(1000000), "above the ceiling is refused"
assert rejects(3.5), "a fraction is refused"
assert rejects("12"), "a string is refused"
assert rejects(None), "a missing value is refused"
print("ok")
