from solution import flip_tips

assert flip_tips("abc") == "cba", "the two tips change places"
assert flip_tips("hello world") == "oellh dorlw", "every word is turned"
assert flip_tips("go on") == "og no", "words of exactly two characters"
assert flip_tips("ab") == "ba", "a lone word of two"
assert flip_tips("a") == "a", "a word too short to turn"
assert flip_tips("") == "", "a line holding nothing"
print("ok")
