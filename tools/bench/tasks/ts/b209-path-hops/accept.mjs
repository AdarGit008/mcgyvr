import assert from "node:assert/strict";
import { pathHops } from "./solution.ts";

assert.equal(pathHops("a/b/c", "a/b/c"), 0, "the same directory is no hops away");
assert.equal(pathHops("a/b", "a/b/c/d"), 2, "walking down costs one hop per segment");
assert.equal(pathHops("a/b/c", "a"), 2, "walking up costs one hop per segment");
assert.equal(pathHops("a/b/c", "a/x/y"), 4, "a sibling branch costs the climb and the descent");
assert.equal(pathHops("a/./b/../c", "a/c"), 0, "dot and two-dot segments are reduced first");
assert.equal(pathHops("", "a"), 1, "the empty path is the root");
assert.throws(() => pathHops("a/../..", "a"), Error, "climbing above the root is rejected");
console.log("ok");
