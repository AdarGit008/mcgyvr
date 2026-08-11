from solution import tidy_path

assert tidy_path("notes/april") == "notes/april", "a plain path is unchanged"
assert tidy_path("./notes/./april") == "notes/april", "current-directory dots are dropped"
assert tidy_path("notes/drafts/../april") == "notes/april", "a step up discards the last kept segment"
assert tidy_path("logs/..") == ".", "a path that cancels out is a single dot"
assert tidy_path(".") == ".", "a lone dot stays a dot"
assert tidy_path("a/b/../../c") == "c", "steps up chain one after another"


def rejects(value):
    try:
        tidy_path(value)
    except ValueError:
        return True
    return False


assert rejects(9), "a non-string path is rejected"
assert rejects(""), "an empty path is rejected"
assert rejects("/notes"), "a leading slash is rejected"
assert rejects("notes//april"), "a doubled slash is rejected"
assert rejects("notes/../.."), "climbing above the start is rejected"
print("ok")
