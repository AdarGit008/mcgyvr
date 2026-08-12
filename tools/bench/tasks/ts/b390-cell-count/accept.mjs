import assert from "node:assert/strict";
import { cellCount } from "./solution.ts";

assert.equal(cellCount([[1, 2], [2, 3]], 2), 2, "twice across two rows");
assert.equal(cellCount([[1]], 9), 0, "the value is absent");
assert.equal(cellCount([], 1), 0, "no rows at all");
assert.equal(cellCount([[]], 1), 0, "a row holding nothing");
assert.equal(cellCount([[1, 1], [1, 1]], 1), 4, "every cell matches");
assert.equal(cellCount([[0]], 0), 1, "a cell holding nothing still matches");
console.log("ok");
