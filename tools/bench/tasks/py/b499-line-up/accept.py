from solution import line_up


def rejects(links, start):
    try:
        line_up(links, start)
    except Exception:
        return True
    return False


assert line_up({"b": "a"}, "b") == ["b", "a"], "one step up the line"
assert line_up({"c": "b", "b": "a"}, "c") == ["c", "b", "a"], "the line runs to the top"
assert line_up({"b": "a"}, "a") == ["a"], "a name with nobody above it"
assert line_up({"b": "a"}, "z") == ["z"], "a name the book does not know"
assert line_up({}, "a") == ["a"], "a book holding no links"
assert rejects({"a": "b", "b": "a"}, "a"), "links running in a circle are rejected"
print("ok")
