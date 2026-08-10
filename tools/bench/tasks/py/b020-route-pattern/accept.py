from solution import match_route

assert match_route("api/health", "api/health") == {}, "literal match"
assert match_route("api/health", "api/metrics") is None, "literal mismatch"
assert match_route("api", "api/health") is None, "a longer path does not match"
assert match_route("users/:id", "users/42") == {
    "id": "42"
}, "a capture records its segment"
assert match_route("users/:id/posts/:post", "users/7/posts/99") == {
    "id": "7",
    "post": "99",
}, "two captures record both segments"
assert match_route("a/**/b", "a/b") == {}, (
    "a double star spans zero segments in the middle"
)
assert match_route("a/**/b", "a/x/y/b") == {}, "a double star spans several segments"
assert match_route("assets/**", "assets") == {}, (
    "a trailing double star matches an exhausted path"
)
assert match_route("assets/**", "assets/img/logo.png") == {}, (
    "a trailing double star swallows the rest"
)
assert match_route("**", "") == {}, "a double star alone matches no segments"
assert match_route("**/:file", "docs/img/pic.png") == {
    "file": "pic.png"
}, "a capture after a double star lands on the last segment"
assert match_route("", "") == {}, "empty pattern matches empty path"
assert match_route("", "x") is None, "empty pattern rejects a real path"


def rejects(pattern, path):
    try:
        match_route(pattern, path)
    except ValueError:
        return True
    return False


assert rejects("a//b", "a/b"), "empty pattern segment"
assert rejects("a/:", "a/x"), "a bare colon has no name"
print("ok")
