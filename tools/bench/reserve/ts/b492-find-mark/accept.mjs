import assert from "node:assert/strict";
import { findMark } from "./solution.ts";

assert.equal(findMark([1, 3, 5, 7], 5), 2, "a mark in the later half");
assert.equal(findMark([1, 3, 5, 7], 1), 0, "the opening mark");
assert.equal(findMark([1, 3, 5, 7], 7), 3, "the closing mark");
assert.equal(findMark([2], 2), 0, "a run of one holding the mark");
assert.equal(findMark([1, 3, 5, 7], 4), -1, "a mark the run does not hold");
assert.equal(findMark([], 1), -1, "a run holding nothing");
console.log("ok");
