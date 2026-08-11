import assert from "node:assert/strict";
import { binRotate } from "./solution.ts";

assert.deepEqual(binRotate(["a", "b", "c", "d"], 1), ["d", "a", "b", "c"], "one place forward");
assert.deepEqual(binRotate(["a", "b", "c", "d"], 2), ["c", "d", "a", "b"], "two places forward");
assert.deepEqual(binRotate(["a", "b"], 1), ["b", "a"], "a run of two");
assert.deepEqual(binRotate(["a", "b", "c"], 0), ["a", "b", "c"], "a move of nothing");
assert.deepEqual(binRotate(["a", "b", "c"], 3), ["a", "b", "c"], "a move as long as the run");
assert.deepEqual(binRotate([], 2), [], "an empty run");
console.log("ok");
