import assert from "node:assert/strict";
import { fewestPayments } from "./solution.ts";

assert.deepEqual(fewestPayments([]), [], "no dues means no payments");
assert.deepEqual(
  fewestPayments([
    ["ana", "bern", 10],
    ["bern", "ana", 10],
  ]),
  [],
  "two people who owe each other the same net to nothing",
);
assert.deepEqual(
  fewestPayments([
    ["ana", "bern", 30],
    ["bern", "cid", 30],
  ]),
  [["ana", "cid", 30]],
  "the middle person drops out of the chain",
);
assert.deepEqual(
  fewestPayments([
    ["ana", "bern", 10],
    ["bern", "ana", 4],
  ]),
  [["ana", "bern", 6]],
  "opposing dues net before anything is drawn up",
);
assert.deepEqual(
  fewestPayments([
    ["ana", "bern", 5],
    ["bern", "cid", 5],
    ["cid", "dov", 5],
  ]),
  [["ana", "dov", 5]],
  "a three link chain collapses to one payment",
);
assert.deepEqual(
  fewestPayments([
    ["ana", "cleo", 40],
    ["ana", "dov", 10],
    ["bern", "dov", 20],
  ]),
  [
    ["ana", "cleo", 40],
    ["bern", "dov", 20],
    ["ana", "dov", 10],
  ],
  "deepest red against fullest black, twice, then an exact pair",
);
assert.deepEqual(
  fewestPayments([
    ["ana", "dov", 30],
    ["ana", "edda", 30],
    ["bern", "cleo", 25],
  ]),
  [
    ["bern", "cleo", 25],
    ["ana", "dov", 30],
    ["ana", "edda", 30],
  ],
  "the exact pair is paid off before the deeper position",
);
assert.deepEqual(
  fewestPayments([
    ["ana", "dov", 20],
    ["bran", "cleo", 20],
  ]),
  [
    ["ana", "cleo", 20],
    ["bran", "dov", 20],
  ],
  "among four exact pairs the first names decide",
);
assert.deepEqual(
  fewestPayments([
    ["ana", "bern", 30],
    ["ana", "cleo", 70],
  ]),
  [
    ["ana", "cleo", 70],
    ["ana", "bern", 30],
  ],
  "one red position pays the fullest black position first",
);

assert.throws(() => fewestPayments("dues"), Error, "a non-list is rejected");
assert.throws(
  () => fewestPayments([["ana", "bern"]]),
  Error,
  "a due of two items is rejected",
);
assert.throws(
  () => fewestPayments([["ana", "ana", 5]]),
  Error,
  "one person on both sides is rejected",
);
assert.throws(
  () => fewestPayments([["ana", "bern", 0]]),
  Error,
  "an amount of zero is rejected",
);
assert.throws(
  () => fewestPayments([["ana", "bern", 2.5]]),
  Error,
  "a fractional amount is rejected",
);
assert.throws(
  () => fewestPayments([["", "bern", 5]]),
  Error,
  "an empty name is rejected",
);
assert.throws(
  () => fewestPayments([{ payer: "ana", payee: "bern", amount: 5 }]),
  Error,
  "a due that is not a list is rejected",
);
console.log("ok");
