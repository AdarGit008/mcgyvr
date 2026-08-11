import assert from "node:assert/strict";
import { tallyMarks } from "./solution.ts";

assert.equal(tallyMarks("abc"), 6, "no mark follows its own kind");
assert.equal(tallyMarks("aab"), 5, "one mark doubles");
assert.equal(tallyMarks("bb"), 6, "a weightier mark doubles");
assert.equal(tallyMarks("aaa"), 5, "each following mark doubles the usual value");
assert.equal(tallyMarks("z"), 0, "a mark worth nothing");
assert.equal(tallyMarks(""), 0, "a line holding no marks");
console.log("ok");
