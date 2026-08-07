import assert from "node:assert/strict";
import { buildWeightCode } from "./solution.ts";

assert.deepEqual(
  buildWeightCode([["zed", 7]]),
  { codes: { zed: "0" }, bits: 7, tallest: 1 },
  "a lone token takes the bits 0",
);
assert.deepEqual(
  buildWeightCode([
    ["b", 1],
    ["a", 1],
  ]),
  { codes: { a: "0", b: "1" }, bits: 2, tallest: 1 },
  "two tokens of equal tally go by letter order",
);
assert.deepEqual(
  buildWeightCode([
    ["a", 5],
    ["b", 2],
    ["c", 1],
    ["d", 1],
  ]),
  { codes: { a: "1", b: "00", c: "010", d: "011" }, bits: 15, tallest: 3 },
  "a lopsided tally makes a lopsided walk",
);
assert.deepEqual(
  buildWeightCode([
    ["s", 1],
    ["r", 1],
    ["q", 1],
    ["p", 1],
  ]),
  { codes: { p: "00", q: "01", r: "10", s: "11" }, bits: 8, tallest: 2 },
  "four equal tallies give four bits of two",
);
assert.deepEqual(
  buildWeightCode([
    ["x", 1],
    ["y", 1],
    ["z", 2],
  ]),
  { codes: { x: "10", y: "11", z: "0" }, bits: 6, tallest: 2 },
  "a leaf bud outranks a fresh bud of the same load",
);
assert.deepEqual(
  buildWeightCode([
    ["m", 3],
    ["n", 3],
    ["o", 3],
  ]),
  { codes: { m: "10", n: "11", o: "0" }, bits: 15, tallest: 2 },
  "three equal tallies leave the last token shortest",
);
assert.deepEqual(
  buildWeightCode([
    ["ab", 2],
    ["b", 3],
  ]),
  { codes: { ab: "0", b: "1" }, bits: 5, tallest: 1 },
  "multi-letter tokens sort as words",
);
assert.throws(() => buildWeightCode("abc"), Error, "a non-list argument is rejected");
assert.throws(() => buildWeightCode([]), Error, "an empty entry list is rejected");
assert.throws(() => buildWeightCode([["a"]]), Error, "an entry of one thing is rejected");
assert.throws(() => buildWeightCode([["A", 1]]), Error, "a capital token is rejected");
assert.throws(() => buildWeightCode([["", 1]]), Error, "an empty token is rejected");
assert.throws(
  () =>
    buildWeightCode([
      ["a", 1],
      ["a", 2],
    ]),
  Error,
  "a repeated token is rejected",
);
assert.throws(() => buildWeightCode([["a", 0]]), Error, "a tally of zero is rejected");
assert.throws(() => buildWeightCode([["a", 1.5]]), Error, "a fractional tally is rejected");
console.log("ok");
