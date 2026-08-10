import assert from "node:assert/strict";
import { matchRoute } from "./solution.ts";

assert.deepEqual(matchRoute("api/health", "api/health"), {}, "literal match");
assert.equal(matchRoute("api/health", "api/metrics"), null, "literal mismatch");
assert.equal(matchRoute("api", "api/health"), null, "a longer path does not match");
assert.deepEqual(
  matchRoute("users/:id", "users/42"),
  { id: "42" },
  "a capture records its segment",
);
assert.deepEqual(
  matchRoute("users/:id/posts/:post", "users/7/posts/99"),
  { id: "7", post: "99" },
  "two captures record both segments",
);
assert.deepEqual(
  matchRoute("a/**/b", "a/b"),
  {},
  "a double star spans zero segments in the middle",
);
assert.deepEqual(
  matchRoute("a/**/b", "a/x/y/b"),
  {},
  "a double star spans several segments",
);
assert.deepEqual(
  matchRoute("assets/**", "assets"),
  {},
  "a trailing double star matches an exhausted path",
);
assert.deepEqual(
  matchRoute("assets/**", "assets/img/logo.png"),
  {},
  "a trailing double star swallows the rest",
);
assert.deepEqual(matchRoute("**", ""), {}, "a double star alone matches no segments");
assert.deepEqual(
  matchRoute("**/:file", "docs/img/pic.png"),
  { file: "pic.png" },
  "a capture after a double star lands on the last segment",
);
assert.deepEqual(matchRoute("", ""), {}, "empty pattern matches empty path");
assert.equal(matchRoute("", "x"), null, "empty pattern rejects a real path");
assert.throws(() => matchRoute("a//b", "a/b"), Error, "empty pattern segment");
assert.throws(() => matchRoute("a/:", "a/x"), Error, "a bare colon has no name");
console.log("ok");
