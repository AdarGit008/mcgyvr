from solution import normalize_rel_path

assert normalize_rel_path("a/b/c") == "a/b/c", "already clean"
assert normalize_rel_path("a//b") == "a/b", "doubled slash collapses"
assert normalize_rel_path("./a/./b") == "a/b", "single dots drop"
assert normalize_rel_path("a/b/../c") == "a/c", "double dot removes one segment"
assert normalize_rel_path("a/b/../../c") == "c", "double dots stack"
assert normalize_rel_path("a/") == "a", "trailing slash drops"
assert normalize_rel_path("a/..") == ".", "full cancellation gives dot"
assert normalize_rel_path("./.") == ".", "dots alone give dot"
assert (
    normalize_rel_path("a/./b/../../c/d/") == "c/d"
), "mixed dots, doubles and trailing slash"


def rejects(value):
    try:
        normalize_rel_path(value)
    except ValueError:
        return True
    return False


assert rejects(".."), "climbing above start is rejected"
assert rejects("a/../.."), "late climb is rejected"
assert rejects("/a"), "absolute path is rejected"
assert rejects(""), "empty path is rejected"
assert rejects(5), "non-string is rejected"
print("ok")
