import assert from "node:assert/strict";
import { seatBlock } from "./solution.ts";

assert.deepEqual(seatBlock("12C"), [12, "C"], "a two-digit row");
assert.deepEqual(seatBlock("1A"), [1, "A"], "a single-digit row");
assert.deepEqual(seatBlock("100Z"), [100, "Z"], "a three-digit row");
assert.throws(() => seatBlock("C12"), Error, "the letter cannot lead");
assert.throws(() => seatBlock("12"), Error, "a row alone is not a seat");
assert.throws(() => seatBlock(""), Error, "an empty label is rejected");
console.log("ok");
