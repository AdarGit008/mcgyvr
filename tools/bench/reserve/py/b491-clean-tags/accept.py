from solution import clean_tags

assert clean_tags(["Red", "red", "blue"]) == ["red", "blue"], "a repeat after lowering is dropped"
assert clean_tags(["a1", "ok"]) == ["ok"], "a tag holding a figure is turned away"
assert clean_tags(["one-two"]) == ["one-two"], "a dash is allowed"
assert clean_tags(["A", "B", "a"]) == ["a", "b"], "the arriving order is held"
assert clean_tags([""]) == [], "a tag holding nothing is turned away"
assert clean_tags([]) == [], "no tags at all"
print("ok")
