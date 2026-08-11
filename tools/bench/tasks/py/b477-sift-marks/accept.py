from solution import sift_marks

assert sift_marks(["ax", "b", "ay"], "a") == [["ax", "ay"], ["b"]], "both runs keep their order"
assert sift_marks(["b", "c"], "a") == [[], ["b", "c"]], "nothing carries the mark"
assert sift_marks(["ab", "ac"], "a") == [["ab", "ac"], []], "everything carries the mark"
assert sift_marks(["ba", "ab"], "ab") == [["ab"], ["ba"]], "a mark of more than one character"
assert sift_marks(["a"], "a") == [["a"], []], "an entry that is the mark itself"
assert sift_marks(["a", "abc"], "ab") == [["abc"], ["a"]], "an entry shorter than the mark"
assert sift_marks([], "a") == [[], []], "no entries at all"
print("ok")
