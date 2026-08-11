import assert from "node:assert/strict";
import { markList } from "./solution.ts";

assert.deepEqual(markList([1, 5], 3), ["1", "5*"], "only the high one is marked");
assert.deepEqual(markList([3], 3), ["3*"], "reaching the floor counts");
assert.deepEqual(markList([1], 3), ["1"], "below the floor is unmarked");
assert.deepEqual(markList([], 3), [], "nothing to mark");
assert.deepEqual(markList([5, 6], 3), ["5*", "6*"], "everything is marked");
assert.deepEqual(markList([1, 2], 3), ["1", "2"], "nothing is marked");
console.log("ok");
