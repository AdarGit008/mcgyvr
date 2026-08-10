import assert from "node:assert/strict";
import { firstRoute, matchRoute, splitSegments } from "./solution.ts";

assert.deepEqual(splitSegments("/a/b"), ["a", "b"], "plain segments");
assert.deepEqual(splitSegments("/"), [], "the root has no segments");
assert.deepEqual(matchRoute("/health", "/health"), {}, "literal match captures nothing");
assert.equal(matchRoute("/health", "/status"), null, "literal mismatch");
assert.deepEqual(matchRoute("/users/:id", "/users/7"), { id: "7" }, "one capture");
assert.deepEqual(
  matchRoute("/users/:id/orders/:oid", "/users/7/orders/b12"),
  { id: "7", oid: "b12" },
  "two captures",
);
assert.deepEqual(
  matchRoute("/logs/*/tail", "/logs/2026/tail"),
  {},
  "star spans one segment",
);
assert.equal(matchRoute("/logs/*", "/logs"), null, "star needs its segment");
assert.deepEqual(matchRoute("/api/**", "/api"), {}, "double star spans nothing");
assert.deepEqual(matchRoute("/api/**", "/api/v1/users/7"), {}, "double star spans many");
assert.deepEqual(matchRoute("/a/**/z", "/a/b/c/z"), {}, "double star in the middle");
assert.equal(matchRoute("/a/**/z", "/a/b"), null, "double star cannot drop the tail");
assert.deepEqual(
  matchRoute("/**/:leaf", "/x/y/z"),
  { leaf: "z" },
  "capture after double star",
);
assert.equal(firstRoute(["/a", "/:x", "/**"], "/q"), 1, "first matching pattern wins");
assert.equal(firstRoute(["/a/b"], "/c"), -1, "no pattern matches");
assert.throws(() => splitSegments(7), Error, "non-string path");
assert.throws(() => splitSegments(""), Error, "empty path");
assert.throws(() => splitSegments("a/b"), Error, "missing leading slash");
assert.throws(() => splitSegments("/a//b"), Error, "empty segment");
assert.throws(() => splitSegments("/a/"), Error, "trailing slash");
assert.throws(() => matchRoute("/:9bad", "/x"), Error, "malformed capture name");
assert.throws(() => matchRoute("/:a/:a", "/x/y"), Error, "repeated capture name");
assert.throws(() => matchRoute("/**/a/**", "/a"), Error, "double star twice");
assert.throws(() => matchRoute("/a", "b"), Error, "path rejection propagates");
console.log("ok");
