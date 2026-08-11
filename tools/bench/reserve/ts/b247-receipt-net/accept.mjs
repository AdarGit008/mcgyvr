import assert from "node:assert/strict";
import { receiptNet } from "./solution.ts";

assert.equal(
  receiptNet([
    { amount: 10, voided: false },
    { amount: 5, voided: true },
  ]),
  10,
  "the voided line is left out",
);
assert.equal(
  receiptNet([{ amount: 3, voided: false }, { amount: 4, voided: false }]),
  7,
  "nothing voided, everything counts",
);
assert.equal(receiptNet([{ amount: 9, voided: true }]), 0, "every line voided");
assert.equal(receiptNet([]), 0, "an empty receipt");
assert.equal(receiptNet([{ amount: 0, voided: false }]), 0, "a zero line");
assert.equal(
  receiptNet([{ amount: -2, voided: false }, { amount: 5, voided: false }]),
  3,
  "a refund line still counts",
);
console.log("ok");
