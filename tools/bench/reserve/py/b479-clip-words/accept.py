from solution import clip_words

assert clip_words(["alpha", "be"], 3) == "alp. be", "only the long word is cut"
assert clip_words(["one", "two"], 3) == "one two", "words at the width are left whole"
assert clip_words(["longer"], 2) == "lo.", "a lone word is cut"
assert clip_words(["a", "b", "c"], 5) == "a b c", "short words join with single spaces"
assert clip_words(["abcd", "efgh"], 1) == "a. e.", "every word is cut"
assert clip_words([], 4) == "", "a run holding no words"
print("ok")
