from solution import swipe_dedupe

assert swipe_dedupe(["a", "a", "b"]) == ["a", "b"], "a repeat is dropped"
assert swipe_dedupe(["a", "b", "a"]) == ["a", "b", "a"], "a return is kept"
assert swipe_dedupe(["a"]) == ["a"], "a single swipe"
assert swipe_dedupe([]) == [], "no swipes at all"
assert swipe_dedupe(["a", "a", "a"]) == ["a"], "a long run collapses"
assert swipe_dedupe(["a", "b", "b", "a"]) == ["a", "b", "a"], "only adjacent repeats go"
print("ok")
