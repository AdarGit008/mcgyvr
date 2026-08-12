from solution import clip_text


def rejects(text, start, end):
    try:
        clip_text(text, start, end)
    except Exception:
        return True
    return False


assert clip_text("abcdef", 1, 3) == "bc", "the second place is left out"
assert clip_text("abc", 0, 3) == "abc", "the whole text"
assert clip_text("abc", 1, 99) == "bc", "a place past the end is brought back"
assert clip_text("abc", 2, 2) == "", "the two places are the same"
assert clip_text("", 0, 5) == "", "an empty text"
assert rejects("abc", 3, 1), "an upside-down clip is rejected"
print("ok")
