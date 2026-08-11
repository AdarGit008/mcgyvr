from solution import tags_of, tag_index


def rejects(line):
    try:
        tags_of(line)
    except Exception:
        return True
    return False


assert tags_of("a, b") == ["a", "b"], "the spaces are trimmed"
assert tags_of("a,,b") == ["a", "b"], "an empty tag is left out"
assert tags_of("") == [], "no tags at all"
assert tag_index(["a,b", "b"]) == {
    "a": ["a,b"],
    "b": ["a,b", "b"],
}, "each tag names its lines"
assert tag_index([]) == {}, "no lines at all"
assert rejects(7), "a line that is not text is rejected"
print("ok")
