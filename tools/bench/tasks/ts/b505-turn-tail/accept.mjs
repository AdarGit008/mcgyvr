import assert from "node:assert/strict";
import { turnTail } from "./solution.ts";

assert.deepEqual(turnTail(["a", "b", "c", "d"], 2), ["a", "b", "d", "c"], "only the closing pair turns");
assert.deepEqual(turnTail(["a", "b", "c", "d"], 3), ["a", "d", "c", "b"], "a longer closing stretch");
assert.deepEqual(turnTail(["a", "b", "c"], 3), ["c", "b", "a"], "the whole run turns");
assert.deepEqual(turnTail(["a", "b", "c"], 5), ["c", "b", "a"], "a count reaching past the run");
assert.deepEqual(turnTail(["a", "b", "c"], 0), ["a", "b", "c"], "a count of nothing");
assert.deepEqual(turnTail([], 2), [], "a run holding nothing");
console.log("ok");
