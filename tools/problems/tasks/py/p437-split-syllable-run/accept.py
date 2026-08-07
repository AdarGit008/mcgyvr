from solution import split_syllables


def rejects(word, min_letters):
    try:
        split_syllables(word, min_letters)
    except ValueError:
        return True
    return False


assert split_syllables("basket", 1) == ["bas", "ket"], "two consonants part"
assert split_syllables("mother", 1) == ["mo", "ther"], "th never parts"
assert split_syllables("lemon", 1) == ["le", "mon"], "a lone consonant goes right"
assert split_syllables("yellow", 1) == ["yel", "low"], "a leading y is a consonant"
assert split_syllables("happy", 1) == ["hap", "py"], "a trailing y is a vowel"
assert split_syllables("rhythm", 1) == ["rhythm"], "one nucleus leaves the word whole"
assert split_syllables("sky", 1) == ["sky"], "y alone carries the only nucleus"
assert split_syllables("monster", 1) == ["mon", "ster"], (
    "a run of three keeps its first letter on the left"
)
assert split_syllables("bathtub", 1) == ["ba", "thtub"], (
    "a run opening with th goes right entire"
)
assert split_syllables("elephant", 1) == ["e", "le", "phant"], (
    "three nuclei make three syllables"
)
assert split_syllables("elephant", 2) == ["ele", "phant"], (
    "the leading syllable joins the one after it"
)
assert split_syllables("banana", 2) == ["ba", "na", "na"], (
    "two letters each is long enough"
)
assert split_syllables("banana", 3) == ["banana"], (
    "joining cascades until one syllable stands"
)

assert rejects(5, 1), "a non-string word is rejected"
assert rejects("", 1), "an empty word is rejected"
assert rejects("Basket", 1), "a capital letter is rejected"
assert rejects("bas ket", 1), "a space is rejected"
assert rejects("basket", 0), "a minimum below one is rejected"
assert rejects("basket", 2.5), "a fractional minimum is rejected"
print("ok")
