import assert from "node:assert/strict";
import { redeemCouponSlips } from "./solution.ts";

assert.deepEqual(
  redeemCouponSlips([["gate", 1000], ["boat", 500]], [["s1", "gate", 10], ["s2", "gate", 10], ["s3", "raft", 50]], 100000),
  { due: 1310, saved: 190, ignored: ["s3"] },
  "a second slip bites into what the first left behind",
);
assert.deepEqual(
  redeemCouponSlips([["gate", 1000], ["boat", 500]], [["a", "gate", 10], ["b", "gate", 10], ["c", "gate", 10]], 100000),
  { due: 1310, saved: 190, ignored: ["c"] },
  "a third slip on one ticket is passed over",
);
assert.deepEqual(
  redeemCouponSlips([["gate", 1000]], [["a", "gate", 10], ["b", "gate", 10]], 195),
  { due: 810, saved: 190, ignored: [] },
  "a compounded saving fits under a ceiling the opening price would break",
);
assert.deepEqual(
  redeemCouponSlips([["gate", 1000]], [["a", "gate", 10], ["b", "gate", 10]], 150),
  { due: 900, saved: 100, ignored: ["b"] },
  "a slip past the ceiling is passed over whole",
);
assert.deepEqual(
  redeemCouponSlips([["gate", 1000], ["boat", 500]], [["a", "gate", 50], ["b", "boat", 10], ["c", "gate", 5]], 100),
  { due: 1400, saved: 100, ignored: ["a"] },
  "a slip stopped by the ceiling neither strikes nor stops those behind it",
);
assert.deepEqual(
  redeemCouponSlips([["free", 0], ["gate", 1000]], [["a", "gate", 10], ["b", "free", 50]], 0),
  { due: 1000, saved: 0, ignored: ["a"] },
  "a saving of nothing clears even a ceiling of nought",
);
assert.deepEqual(
  redeemCouponSlips([["gate", 1000]], [], 500),
  { due: 1000, saved: 0, ignored: [] },
  "no slips leaves the tickets whole",
);
assert.deepEqual(
  redeemCouponSlips([], [["a", "gate", 10]], 500),
  { due: 0, saved: 0, ignored: ["a"] },
  "a slip naming no ticket at all is passed over",
);
assert.deepEqual(
  redeemCouponSlips([["odd", 999]], [["a", "odd", 33]], 10000),
  { due: 670, saved: 329, ignored: [] },
  "a part of a cent is dropped",
);
assert.deepEqual(
  redeemCouponSlips([["gate", 800]], [["a", "gate", 100]], 10000),
  { due: 0, saved: 800, ignored: [] },
  "a share of the whole leaves nothing standing",
);

assert.throws(() => redeemCouponSlips([["gate"]], [], 100), Error, "a ticket that is not a pair is refused");
assert.throws(() => redeemCouponSlips([["", 100]], [], 100), Error, "an empty label is refused");
assert.throws(() => redeemCouponSlips([["gate", 100], ["gate", 200]], [], 100), Error, "two tickets sharing a label are refused");
assert.throws(() => redeemCouponSlips([["gate", -1]], [], 100), Error, "a negative price is refused");
assert.throws(() => redeemCouponSlips([["gate", 1.5]], [], 100), Error, "a fractional price is refused");
assert.throws(() => redeemCouponSlips([["gate", 100]], [["a", "gate"]], 100), Error, "a slip that is not a triple is refused");
assert.throws(() => redeemCouponSlips([["gate", 100]], [["", "gate", 10]], 100), Error, "an empty tag is refused");
assert.throws(
  () => redeemCouponSlips([["gate", 100]], [["a", "gate", 10], ["a", "gate", 20]], 100),
  Error,
  "two slips sharing a tag are refused",
);
assert.throws(() => redeemCouponSlips([["gate", 100]], [["a", "gate", 0]], 100), Error, "a share of nought is refused");
assert.throws(() => redeemCouponSlips([["gate", 100]], [["a", "gate", 101]], 100), Error, "a share past 100 is refused");
assert.throws(() => redeemCouponSlips([["gate", 100]], [["a", "gate", 1.5]], 100), Error, "a fractional share is refused");
assert.throws(() => redeemCouponSlips([["gate", 100]], [], -1), Error, "a negative ceiling is refused");
assert.throws(() => redeemCouponSlips([["gate", 100]], [], 2.5), Error, "a fractional ceiling is refused");
console.log("ok");
