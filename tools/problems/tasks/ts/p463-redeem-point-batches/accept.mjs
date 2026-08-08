import assert from "node:assert/strict";
import { redeemPointBatches } from "./solution.ts";

assert.deepEqual(
  redeemPointBatches([
    { kind: "earn", day: 1, points: 100, life: 9 },
    { kind: "earn", day: 2, points: 50, life: 30 },
    { kind: "earn", day: 3, points: 30, life: 5 },
    { kind: "burn", day: 4, points: 60 },
    { kind: "burn", day: 9, points: 200 },
    { kind: "burn", day: 11, points: 40 },
    { kind: "earn", day: 11, points: 5, life: 0 },
    { kind: "burn", day: 12, points: 1 },
  ]),
  { taken: [60, 0, 40, 1], lapsed: 75, balance: 9 },
  "the soonest batch to lapse is drawn from first",
);

assert.deepEqual(
  redeemPointBatches([
    { kind: "earn", day: 0, points: 10, life: 3 },
    { kind: "burn", day: 3, points: 10 },
  ]),
  { taken: [10], lapsed: 0, balance: 0 },
  "a batch is still spendable on its last spendable day",
);

assert.deepEqual(
  redeemPointBatches([
    { kind: "earn", day: 0, points: 10, life: 3 },
    { kind: "burn", day: 4, points: 10 },
  ]),
  { taken: [0], lapsed: 10, balance: 0 },
  "a batch is struck out the day after its last spendable day",
);

assert.deepEqual(
  redeemPointBatches([
    { kind: "earn", day: 0, points: 10, life: 10 },
    { kind: "earn", day: 0, points: 10, life: 10 },
    { kind: "burn", day: 0, points: 12 },
    { kind: "burn", day: 0, points: 8 },
  ]),
  { taken: [12, 8], lapsed: 0, balance: 0 },
  "batches lapsing on one day are drawn oldest first",
);

assert.deepEqual(
  redeemPointBatches([
    { kind: "earn", day: 0, points: 5, life: 0 },
    { kind: "burn", day: 0, points: 6 },
    { kind: "burn", day: 1, points: 1 },
  ]),
  { taken: [0, 0], lapsed: 5, balance: 0 },
  "a burn the account cannot cover draws nothing at all",
);

assert.deepEqual(
  redeemPointBatches([]),
  { taken: [], lapsed: 0, balance: 0 },
  "an empty ledger settles to nothing",
);

assert.deepEqual(
  redeemPointBatches([
    { kind: "earn", day: 5, points: 40, life: 100 },
    { kind: "earn", day: 6, points: 7, life: 1 },
    { kind: "burn", day: 7, points: 12 },
  ]),
  { taken: [12], lapsed: 0, balance: 35 },
  "a short-lived batch is emptied before a long-lived one",
);

assert.throws(
  () => redeemPointBatches("nope"),
  Error,
  "a non-list argument is rejected",
);
assert.throws(
  () => redeemPointBatches([{ kind: "spend", day: 1, points: 2 }]),
  Error,
  "an unknown kind is rejected",
);
assert.throws(
  () => redeemPointBatches([{ kind: "earn", day: 1, points: 2 }]),
  Error,
  "an earn without a life is rejected",
);
assert.throws(
  () => redeemPointBatches([{ kind: "burn", day: 1, points: 2, life: 0 }]),
  Error,
  "a burn carrying a life is rejected",
);
assert.throws(
  () =>
    redeemPointBatches([
      { kind: "burn", day: 4, points: 1 },
      { kind: "burn", day: 3, points: 1 },
    ]),
  Error,
  "a day that steps backwards is rejected",
);
assert.throws(
  () => redeemPointBatches([{ kind: "earn", day: 1, points: 0, life: 1 }]),
  Error,
  "points below one are rejected",
);
assert.throws(
  () => redeemPointBatches([{ kind: "earn", day: 1, points: 5, life: -1 }]),
  Error,
  "a life below nought is rejected",
);
assert.throws(
  () => redeemPointBatches([{ kind: "earn", day: 1.5, points: 5, life: 1 }]),
  Error,
  "a day that is not whole is rejected",
);
console.log("ok");
