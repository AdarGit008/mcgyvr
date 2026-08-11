import assert from "node:assert/strict";
import { spanMerge } from "./solution.ts";

assert.deepEqual(spanMerge([[1, 3], [2, 5]]), [[1, 5]], "two overlapping spans");
assert.deepEqual(spanMerge([[1, 2], [2, 4]]), [[1, 4]], "touching end to start");
assert.deepEqual(spanMerge([[5, 6], [1, 2]]), [[1, 2], [5, 6]], "sorted by start");
assert.deepEqual(spanMerge([[1, 10], [2, 3]]), [[1, 10]], "one span swallows another");
assert.deepEqual(spanMerge([[1, 2], [4, 5]]), [[1, 2], [4, 5]], "a real gap survives");
assert.deepEqual(spanMerge([]), [], "no spans at all");
console.log("ok");
