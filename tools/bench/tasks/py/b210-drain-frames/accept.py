from solution import drain_frames

assert drain_frames(["ab|cd", "e|f"], "|") == {"frames": ["ab", "cde"], "pending": "f"}, "a frame may span two chunks"
assert drain_frames(["abc"], "|") == {"frames": [], "pending": "abc"}, "text with no marker is all pending"
assert drain_frames(["a||b|c"], "|") == {"frames": ["a|b"], "pending": "c"}, "a doubled marker is one literal marker"
assert drain_frames(["|x"], "|") == {"frames": [""], "pending": "x"}, "an opening marker ends an empty frame"
assert drain_frames(["ab|"], "|") == {"frames": [], "pending": "ab|"}, "a marker with nothing after it stays unresolved"
assert drain_frames(["ab||"], "|") == {"frames": [], "pending": "ab|"}, "a doubled marker at the end folds to a literal"


def rejects(*args):
    try:
        drain_frames(*args)
    except Exception:
        return True
    return False


assert rejects(["ab"], "--"), "a marker of two characters is rejected"
print("ok")
