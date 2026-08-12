import assert from "node:assert/strict";
import { firstRepeat } from "./solution.ts";

assert.equal(firstRepeat(["a", "b", "a", "c"]), "a", "the first entry arrives twice");
assert.equal(firstRepeat(["a", "b", "c", "b"]), "b", "the second arrival decides, not the first");
assert.equal(firstRepeat(["x", "x"]), "x", "a run of two that match");
assert.equal(firstRepeat(["a", "b", "c"]), "", "every entry arrives once");
assert.equal(firstRepeat(["a"]), "", "a lone entry");
assert.equal(firstRepeat([]), "", "a run holding nothing");
console.log("ok");
