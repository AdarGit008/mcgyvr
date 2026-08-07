from solution import clip_label

assert clip_label("short", 10) == "short", "a fitting label is untouched"
assert clip_label("exactly10!", 10) == "exactly10!", "an exact fit is untouched"
assert clip_label("abcdefghijk", 10) == "abcdefg...", (
    "an overlong label keeps budget-minus-3 characters plus the dots"
)
assert clip_label("hello there world", 9) == "hello...", (
    "spaces at the cut are dropped before the dots"
)
assert clip_label("abcdefgh", 4) == "a...", "the minimum budget keeps one character"
assert clip_label("ab cdefghij", 7) == "ab c...", (
    "a space inside the kept part survives"
)
assert clip_label("", 4) == "", "the empty label fits any budget"


def rejects(label, budget):
    try:
        clip_label(label, budget)
    except ValueError:
        return True
    return False


assert rejects("abcdef", 3), "budget 3 is rejected"
assert rejects("abcdef", 4.5), "fractional budget is rejected"
assert rejects(123, 8), "non-string label is rejected"
print("ok")
