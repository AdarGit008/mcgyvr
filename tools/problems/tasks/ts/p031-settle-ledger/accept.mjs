import assert from "node:assert/strict";
import { settleLedger } from "./solution.ts";

assert.deepEqual(
  settleLedger([
    { account: "x", amount: -5, seq: 2 },
    { account: "x", amount: 10, seq: 1 },
  ]),
  [["x", 5]],
  "entries replay in seq order, not list order",
);
assert.deepEqual(
  settleLedger([
    { account: "b", amount: 7, seq: 10 },
    { account: "a", amount: 3, seq: 20 },
    { account: "c", amount: 1, seq: 30 },
  ]),
  [["a", 3], ["b", 7], ["c", 1]],
  "output sorts by account name, seq gaps allowed",
);
assert.deepEqual(
  settleLedger([
    { account: "x", amount: 5, seq: 1 },
    { account: "x", amount: -5, seq: 2 },
    { account: "y", amount: 2, seq: 3 },
  ]),
  [["y", 2]],
  "an account settling to zero is omitted",
);
assert.deepEqual(
  settleLedger([
    { account: "a", amount: 10, seq: 1 },
    { account: "b", amount: 4, seq: 2 },
    { account: "a", amount: -3, seq: 3 },
    { account: "b", amount: -4, seq: 4 },
  ]),
  [["a", 7]],
  "interleaved accounts settle independently",
);
assert.deepEqual(settleLedger([]), [], "empty ledger settles empty");
assert.throws(
  () =>
    settleLedger([
      { account: "x", amount: 5, seq: 1 },
      { account: "x", amount: -6, seq: 2 },
    ]),
  Error,
  "overdraft is rejected",
);
assert.throws(
  () =>
    settleLedger([
      { account: "x", amount: 5, seq: 1 },
      { account: "x", amount: -6, seq: 2 },
      { account: "x", amount: 10, seq: 3 },
    ]),
  Error,
  "mid-replay overdraft is rejected despite later deposit",
);
assert.throws(
  () =>
    settleLedger([
      { account: "x", amount: 1, seq: 1 },
      { account: "y", amount: 1, seq: 1 },
    ]),
  Error,
  "duplicate seq is rejected",
);
assert.throws(
  () => settleLedger([{ account: "x", seq: 1 }]),
  Error,
  "missing amount is rejected",
);
assert.throws(
  () => settleLedger([{ account: "", amount: 1, seq: 1 }]),
  Error,
  "empty account name is rejected",
);
assert.throws(
  () => settleLedger([{ account: "x", amount: 1.5, seq: 1 }]),
  Error,
  "fractional amount is rejected",
);
assert.throws(
  () => settleLedger([{ account: 9, amount: 1, seq: 1 }]),
  Error,
  "non-string account is rejected",
);
console.log("ok");
