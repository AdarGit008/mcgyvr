from solution import mask_word, mask_line

assert mask_word("hello") == "h...o", "the middle is dotted"
assert mask_word("hi") == "hi", "two characters are left alone"
assert mask_word("") == "", "nothing to mask"
assert mask_line("hello there") == "h...o t...e", "every word is masked"
assert mask_line("") == "", "an empty line"
assert mask_line("a bb ccc") == "a bb c.c", "short words survive"
print("ok")
