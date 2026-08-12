from solution import drop_mark

assert drop_mark("a-b-c", "-") == "abc", "the dashes go"
assert drop_mark("abc", "-") == "abc", "nothing to remove"
assert drop_mark("", "-") == "", "an empty text"
assert drop_mark("---", "-") == "", "everything goes"
assert drop_mark("a", "a") == "", "the only character goes"
assert drop_mark("aXbXc", "X") == "abc", "a capital marker"
print("ok")
