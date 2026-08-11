from solution import tag_trim

assert tag_trim("#draft:") == "draft", "both markers go"
assert tag_trim("#draft") == "draft", "a leading marker alone"
assert tag_trim("draft:") == "draft", "a trailing marker alone"
assert tag_trim("draft") == "draft", "no markers, no change"
assert tag_trim("##draft::") == "#draft:", "only one of each is stripped"
assert tag_trim("#") == "", "a bare marker leaves nothing"
assert tag_trim("") == "", "an empty tag stays empty"
print("ok")
