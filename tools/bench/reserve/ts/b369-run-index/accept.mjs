import assert from "node:assert/strict";
import { runIndex } from "./solution.ts";

assert.equal(runIndex(["a", "b", "a"], "a", 2), 2, "the second appearance");
assert.equal(runIndex(["a", "b", "a"], "a", 1), 0, "the first appearance");
assert.equal(runIndex(["a", "b", "a"], "a", 3), -1, "it never appears that often");
assert.equal(runIndex([], "a", 1), -1, "an empty list");
assert.equal(runIndex(["a"], "b", 1), -1, "the value is absent");
assert.throws(() => runIndex(["a"], "a", 0), Error, "a count of zero is rejected");
console.log("ok");
