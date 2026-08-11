import assert from "node:assert/strict";
import { rootDigit } from "./solution.ts";

assert.equal(rootDigit(38), 2, "the folding runs more than once");
assert.equal(rootDigit(99), 9, "a second fold is needed");
assert.equal(rootDigit(12345), 6, "a longer count folds twice");
assert.equal(rootDigit(10), 1, "a count that folds to one figure at once");
assert.equal(rootDigit(9), 9, "a count already standing as one figure");
assert.equal(rootDigit(0), 0, "a count of nothing");
console.log("ok");
