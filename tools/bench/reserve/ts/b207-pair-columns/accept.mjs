import assert from "node:assert/strict";
import { pairColumns } from "./solution.ts";

assert.deepEqual(pairColumns(["ab", "c"], ["1", "2"], 2), ["ab  1", "c   2"], "the left block is padded to its widest line");
assert.deepEqual(pairColumns(["ab", "c"], ["1"], 1), ["ab 1", "c"], "a row past the right block keeps only the left text");
assert.deepEqual(pairColumns(["ab"], ["1", "2"], 1), ["ab 1", "   2"], "a row past the left block keeps the full padding");
assert.deepEqual(pairColumns(["ab", "c"], ["1", "2"], 0), ["ab1", "c 2"], "a gap of zero butts the blocks together");
assert.deepEqual(pairColumns([], ["x"], 3), ["   x"], "an absent left block leaves the gap alone");
assert.deepEqual(pairColumns([], [], 4), [], "two empty blocks give no lines");
assert.deepEqual(pairColumns(["long", ""], ["1", ""], 2), ["long  1", ""], "a row empty on both sides comes out empty");
assert.throws(() => pairColumns(["a"], ["b"], -1), Error, "a negative gap is rejected");
console.log("ok");
