from solution import common_head

assert common_head(["flow", "flower", "flight"]) == "fl", "two shared letters"
assert common_head(["one"]) == "one", "one word shares itself"
assert common_head([]) == "", "no words at all"
assert common_head(["a", "b"]) == "", "nothing in common"
assert common_head(["same", "same"]) == "same", "the whole word is shared"
assert common_head(["prefix", "pre"]) == "pre", "the shorter word bounds it"
print("ok")
