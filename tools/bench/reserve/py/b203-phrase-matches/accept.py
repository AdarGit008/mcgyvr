from solution import phrase_matches

assert phrase_matches("raise the mast", ["raise", "the", "mast"]) is True, "plain tokens match word for word"
assert phrase_matches("raise * mast", ["raise", "the", "second", "mast"]) is True, "a star spans several words"
assert phrase_matches("raise * mast", ["raise", "mast"]) is True, "a star also spans no words at all"
assert phrase_matches("raise ? mast", ["raise", "mast"]) is False, "a question mark demands one word"
assert phrase_matches("* mast", ["mast", "hoist"]) is False, "words left over after the tokens fail"
assert phrase_matches("raise|lower the ?", ["lower", "the", "gaff"]) is True, "a barred token takes any of its pieces"
assert phrase_matches("raise|lower the ?", ["furl", "the", "gaff"]) is False, "a word outside the pieces fails"
print("ok")
