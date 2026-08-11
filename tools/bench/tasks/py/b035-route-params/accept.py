from solution import first_route, match_route, split_segments

assert split_segments("/a/b") == ["a", "b"], "plain segments"
assert split_segments("/") == [], "the root has no segments"
assert match_route("/health", "/health") == {}, "literal match captures nothing"
assert match_route("/health", "/status") is None, "literal mismatch"
assert match_route("/users/:id", "/users/7") == {"id": "7"}, "one capture"
assert match_route("/users/:id/orders/:oid", "/users/7/orders/b12") == {
    "id": "7",
    "oid": "b12",
}, "two captures"
assert match_route("/logs/*/tail", "/logs/2026/tail") == {}, "star spans one segment"
assert match_route("/logs/*", "/logs") is None, "star needs its segment"
assert match_route("/api/**", "/api") == {}, "double star spans nothing"
assert match_route("/api/**", "/api/v1/users/7") == {}, "double star spans many"
assert match_route("/a/**/z", "/a/b/c/z") == {}, "double star in the middle"
assert match_route("/a/**/z", "/a/b") is None, "double star cannot drop the tail"
assert match_route("/**/:leaf", "/x/y/z") == {"leaf": "z"}, "capture after double star"
assert first_route(["/a", "/:x", "/**"], "/q") == 1, "first matching pattern wins"
assert first_route(["/a/b"], "/c") == -1, "no pattern matches"


def rejects(fn, *args):
    try:
        fn(*args)
    except Exception:
        return True
    return False


assert rejects(split_segments, 7), "non-string path"
assert rejects(split_segments, ""), "empty path"
assert rejects(split_segments, "a/b"), "missing leading slash"
assert rejects(split_segments, "/a//b"), "empty segment"
assert rejects(split_segments, "/a/"), "trailing slash"
assert rejects(match_route, "/:9bad", "/x"), "malformed capture name"
assert rejects(match_route, "/:a/:a", "/x/y"), "repeated capture name"
assert rejects(match_route, "/**/a/**", "/a"), "double star twice"
assert rejects(match_route, "/a", "b"), "path rejection propagates"
print("ok")
