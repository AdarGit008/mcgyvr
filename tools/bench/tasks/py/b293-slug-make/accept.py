from solution import slug_word, slug_make

assert slug_word("Hello!") == "hello", "punctuation is dropped"
assert slug_word("--") == "", "a word may slug away entirely"
assert slug_make("Hello, World!") == "hello-world", "joined with a hyphen"
assert slug_make("a -- b") == "a-b", "an empty slug is left out"
assert slug_make("") == "", "nothing to slug"
assert slug_make("Top 10 Tips") == "top-10-tips", "digits survive"
print("ok")
