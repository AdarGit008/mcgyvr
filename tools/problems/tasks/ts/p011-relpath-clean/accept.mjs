import assert from "node:assert/strict";
import { normalizeRelPath } from "./solution.ts";

assert.equal(normalizeRelPath("a/b/c"), "a/b/c", "already clean");
assert.equal(normalizeRelPath("a//b"), "a/b", "doubled slash collapses");
assert.equal(normalizeRelPath("./a/./b"), "a/b", "single dots drop");
assert.equal(normalizeRelPath("a/b/../c"), "a/c", "double dot removes one segment");
assert.equal(normalizeRelPath("a/b/../../c"), "c", "double dots stack");
assert.equal(normalizeRelPath("a/"), "a", "trailing slash drops");
assert.equal(normalizeRelPath("a/.."), ".", "full cancellation gives dot");
assert.equal(normalizeRelPath("./."), ".", "dots alone give dot");
assert.equal(
  normalizeRelPath("a/./b/../../c/d/"),
  "c/d",
  "mixed dots, doubles and trailing slash",
);
assert.throws(() => normalizeRelPath(".."), Error, "climbing above start rejected");
assert.throws(() => normalizeRelPath("a/../.."), Error, "late climb is rejected");
assert.throws(() => normalizeRelPath("/a"), Error, "absolute path is rejected");
assert.throws(() => normalizeRelPath(""), Error, "empty path is rejected");
assert.throws(() => normalizeRelPath(5), Error, "non-string is rejected");
console.log("ok");
