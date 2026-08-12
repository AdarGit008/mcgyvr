from solution import sentence_split

assert sentence_split("One. Two.") == ["One", "Two"], "full stops break"
assert sentence_split("Who? Me!") == ["Who", "Me"], "the other marks break too"
assert sentence_split("No ending") == ["No ending"], "an unfinished sentence"
assert sentence_split("") == [], "nothing to break"
assert sentence_split("...") == [], "empty pieces are left out"
assert sentence_split("A! B. C?") == ["A", "B", "C"], "all three marks"
print("ok")
