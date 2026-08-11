from solution import gloss_find, gloss_terms

assert gloss_find({"Ash": "a tree"}, "ash") == "a tree", "lower case finds it"
assert gloss_find({"Ash": "a tree"}, "ASH") == "a tree", "upper case finds it"
assert gloss_find({"Ash": "a tree"}, "oak") is None, "an absent term"
assert gloss_find({}, "any") is None, "an empty glossary"
assert gloss_terms({"birch": "", "alder": ""}) == ["alder", "birch"], "sorted"
assert gloss_terms({}) == [], "no terms to list"
print("ok")
