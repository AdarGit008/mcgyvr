import assert from "node:assert/strict";
import { partWays } from "./solution.ts";

assert.equal(partWays(["a", "b", "c"], ["a", "x", "c"]), 1, "they part in the middle");
assert.equal(partWays(["x"], ["y"]), 0, "they part at the opening");
assert.equal(partWays(["a", "b"], ["a", "b", "c"]), 2, "one run carries on");
assert.equal(partWays(["a", "b", "c"], ["a", "b"]), 2, "the longer run may come first");
assert.equal(partWays(["a"], ["a"]), -1, "the two runs agree");
assert.equal(partWays([], []), -1, "two runs holding nothing agree");
assert.equal(partWays([], ["a"]), 0, "one run holds nothing");
console.log("ok");
