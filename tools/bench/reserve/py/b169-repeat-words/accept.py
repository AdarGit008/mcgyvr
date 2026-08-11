from solution import repeat_words

assert repeat_words("the cat and the hat", 2) == ["the"], "one word reaches the bar"
assert repeat_words("Sun sun SUN moon", 2) == ["sun"], "counting folds case and lowercases the answer"
assert repeat_words("red blue red", 1) == ["red", "blue"], "least one lists every distinct word once"
assert repeat_words("one two three", 2) == [], "no word reaching the bar yields the empty list"
assert repeat_words("", 2) == [], "an empty text yields the empty list"
assert repeat_words("b a b a a c", 2) == ["b", "a"], "winners keep first-appearance order"
assert repeat_words("hi  hi", 2) == ["hi"], "a run of spaces is one separator"


def rejects(*args):
    try:
        repeat_words(*args)
    except ValueError:
        return True
    return False


assert rejects(42, 2), "a non-string text is rejected"
assert rejects("big deal!", 2), "a character outside letters and spaces is rejected"
assert rejects("big deal", 0), "a least below one is rejected"
assert rejects("big deal", 2.5), "a fractional least is rejected"
print("ok")
