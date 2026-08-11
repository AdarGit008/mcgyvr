from solution import glob_path

assert glob_path("b?g/*.txt", "bag/note.txt") is True, "wildcards match inside their segments"
assert glob_path("src/*.ts", "src/lib/main.ts") is False, "star stops at a slash"
assert glob_path("a?b", "a/b") is False, "question mark refuses a slash"
assert glob_path("rel*", "rel") is True, "star may match nothing"
assert glob_path("notes.txt", "notes.md") is False, "literals must match exactly"


def rejects(pattern, path):
    try:
        glob_path(pattern, path)
    except ValueError:
        return True
    return False


assert rejects(7, "a"), "non-string pattern is rejected"
assert rejects("a", 7), "non-string path is rejected"
assert rejects("", "a"), "empty pattern is rejected"
assert rejects("a", ""), "empty path is rejected"
print("ok")
