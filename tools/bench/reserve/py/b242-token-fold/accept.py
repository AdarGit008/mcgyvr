from solution import token_fold

assert token_fold("hello WORLD") == "Hello World", "case is normalised"
assert token_fold("  spaced   out  ") == "Spaced Out", "runs collapse and ends trim"
assert token_fold("a") == "A", "a single letter"
assert token_fold("mIxEd CaSe here") == "Mixed Case Here", "mixed input"
assert token_fold("ONE") == "One", "a shouted word"
assert token_fold("") == "", "an empty phrase"
assert token_fold("   ") == "", "whitespace only"
print("ok")
