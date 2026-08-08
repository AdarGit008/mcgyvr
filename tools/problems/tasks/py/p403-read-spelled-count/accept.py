from solution import read_spelled_count

assert read_spelled_count("zero") == 0, "the lone word zero"
assert read_spelled_count("seven") == 7, "a one-to-nine spelling alone"
assert read_spelled_count("nineteen") == 19, "the top of the small range"
assert read_spelled_count("sixty") == 60, "a multiple of ten alone"
assert read_spelled_count("forty-two") == 42, "a hyphenated tail"
assert read_spelled_count("one hundred") == 100, "a head with no tail"
assert read_spelled_count("three hundred forty-five") == 345, "head and hyphenated tail"
assert read_spelled_count("nine hundred ninety-nine") == 999, "the biggest block"
assert read_spelled_count("six hundred four") == 604, "head and small tail"
assert read_spelled_count("one thousand") == 1000, "a block and the scale word"
assert read_spelled_count("two thousand fifteen") == 2015, "a further block after the scale"
assert read_spelled_count("seven hundred thousand") == 700000, "a head-only high block"
assert (
    read_spelled_count("nine hundred ninety-nine thousand nine hundred ninety-nine") == 999999
), "both blocks at their fullest"


def rejects(value):
    try:
        read_spelled_count(value)
    except ValueError:
        return True
    return False


assert rejects(""), "an empty phrase is refused"
assert rejects(" one"), "a leading blank is refused"
assert rejects("one  two"), "two blanks running are refused"
assert rejects("eleventy"), "a word outside the vocabulary"
assert rejects("hundred"), "hundred with nothing ahead of it"
assert rejects("twelve hundred"), "a head above nine is refused"
assert rejects("one hundred hundred"), "hundred twice in a block"
assert rejects("one thousand two thousand"), "thousand twice"
assert rejects("thousand five"), "thousand with no block ahead"
assert rejects("zero one"), "zero beside another word"
assert rejects("one hundred zero"), "zero used as a tail"
assert rejects("twenty-eleven"), "a hyphenated tail above nine"
assert rejects("five-two"), "a hyphen with no multiple of ten"
assert rejects("one hundred twenty one"), "a two-word tail"
assert rejects(7), "a non-string is refused"
print("ok")
