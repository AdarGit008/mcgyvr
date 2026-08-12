import assert from "node:assert/strict";
import { skipTake } from "./solution.ts";

assert.deepEqual(skipTake(["a", "b", "c", "d"], 1, 1), ["a", "c"], "one on, one off");
assert.deepEqual(
  skipTake(["a", "b", "c", "d", "e"], 2, 1),
  ["a", "b", "d", "e"],
  "two on, one off",
);
assert.deepEqual(skipTake(["a", "b"], 5, 1), ["a", "b"], "taking more than there is");
assert.deepEqual(skipTake([], 1, 1), [], "an empty list");
assert.deepEqual(skipTake(["a", "b"], 0, 1), [], "taking none");
assert.deepEqual(skipTake(["a", "b", "c"], 3, 0), ["a", "b", "c"], "taking everything");
console.log("ok");
