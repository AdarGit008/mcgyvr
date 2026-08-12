import assert from "node:assert/strict";
import { fieldMean } from "./solution.ts";

assert.equal(fieldMean([{ a: 1 }, { a: 3 }], "a"), 2, "the mean of two");
assert.equal(fieldMean([{ a: 1 }], "a"), 1, "one record");
assert.equal(fieldMean([], "a"), 0, "no records at all");
assert.equal(fieldMean([{ b: 1 }], "a"), 0, "no record carries the field");
assert.equal(fieldMean([{ a: 1 }, { b: 2 }], "a"), 1, "the other record is passed over");
assert.equal(fieldMean([{ a: 1 }, { a: 2 }], "a"), 1, "the mean is rounded down");
console.log("ok");
