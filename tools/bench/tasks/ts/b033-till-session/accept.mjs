import assert from "node:assert/strict";
import { runTillSession } from "./solution.ts";

const prices = { tea: 250, bun: 180, jam: 320 };

assert.deepEqual(
  runTillSession([], prices),
  { state: "open", items: [], total: 0, paid: 0, change: 0 },
  "empty session stays open",
);
assert.deepEqual(
  runTillSession([["scan", "tea"], ["scan", "bun"], ["scan", "tea"]], prices),
  { state: "open", items: [["bun", 1], ["tea", 2]], total: 0, paid: 0, change: 0 },
  "scans accumulate and items sort by name",
);
assert.deepEqual(
  runTillSession([["scan", "tea"], ["scan", "bun"], ["void", "tea"]], prices),
  { state: "open", items: [["bun", 1]], total: 0, paid: 0, change: 0 },
  "a void at one unit drops the item",
);
assert.deepEqual(
  runTillSession([["scan", "tea"], ["scan", "tea"], ["void", "tea"]], prices),
  { state: "open", items: [["tea", 1]], total: 0, paid: 0, change: 0 },
  "a void above one unit decrements",
);
assert.deepEqual(
  runTillSession([["scan", "tea"], ["scan", "bun"], ["close"]], prices),
  { state: "payment", items: [["bun", 1], ["tea", 1]], total: 430, paid: 0, change: 0 },
  "close fixes the total",
);
assert.deepEqual(
  runTillSession([["scan", "tea"], ["scan", "bun"], ["close"], ["pay", 200]], prices),
  { state: "payment", items: [["bun", 1], ["tea", 1]], total: 430, paid: 200, change: 0 },
  "a partial payment keeps the session in payment",
);
assert.deepEqual(
  runTillSession([["scan", "bun"], ["close"], ["pay", 180]], prices),
  { state: "paid", items: [["bun", 1]], total: 180, paid: 180, change: 0 },
  "an exact payment closes with no change",
);
assert.deepEqual(
  runTillSession([["scan", "tea"], ["close"], ["pay", 300]], prices),
  { state: "paid", items: [["tea", 1]], total: 250, paid: 300, change: 50 },
  "an overpayment returns change",
);
assert.deepEqual(
  runTillSession([["scan", "jam"], ["close"], ["pay", 100], ["pay", 300]], prices),
  { state: "paid", items: [["jam", 1]], total: 320, paid: 400, change: 80 },
  "payments accumulate across events",
);
assert.deepEqual(
  runTillSession([["scan", "tea"], ["cancel"]], prices),
  { state: "cancelled", items: [["tea", 1]], total: 0, paid: 0, change: 0 },
  "cancel from open keeps the cart",
);
assert.deepEqual(
  runTillSession([["scan", "tea"], ["close"], ["pay", 100], ["cancel"]], prices),
  { state: "cancelled", items: [["tea", 1]], total: 250, paid: 100, change: 0 },
  "cancel during payment keeps the cents received",
);
assert.throws(() => runTillSession([], { tea: 0 }), Error, "price of zero");
assert.throws(() => runTillSession([["grab", "tea"]], prices), Error, "unknown action");
assert.throws(() => runTillSession([["scan"]], prices), Error, "scan without an item");
assert.throws(() => runTillSession([["scan", "ale"]], prices), Error, "scan of an unpriced item");
assert.throws(() => runTillSession([["void", "tea"]], prices), Error, "void of an item not in the cart");
assert.throws(() => runTillSession([["pay", 100]], prices), Error, "pay while open");
assert.throws(
  () => runTillSession([["scan", "tea"], ["close"], ["scan", "bun"]], prices),
  Error,
  "scan during payment",
);
assert.throws(
  () => runTillSession([["scan", "tea"], ["close"], ["pay", 0]], prices),
  Error,
  "pay amount of zero",
);
assert.throws(
  () => runTillSession([["scan", "tea"], ["close"], ["pay", 99.5]], prices),
  Error,
  "fractional pay amount",
);
assert.throws(
  () => runTillSession([["scan", "bun"], ["close"], ["pay", 180], ["scan", "tea"]], prices),
  Error,
  "event after the session is paid",
);
assert.throws(
  () => runTillSession([["cancel"], ["scan", "tea"]], prices),
  Error,
  "event after the session is cancelled",
);
assert.throws(() => runTillSession([["close"]], prices), Error, "close with an empty cart");
console.log("ok");
