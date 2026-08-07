import assert from "node:assert/strict";
import { expiryCache } from "./solution.ts";

assert.deepEqual(
  expiryCache(2, [
    ["set", 0, "a", 1, 10],
    ["set", 1, "b", 2, 3],
    ["get", 2, "a"],
    ["get", 4, "b"],
    ["set", 5, "c", 3, 10],
    ["get", 5, "c"],
    ["get", 5, "a"],
  ]),
  [1, -1, 3, 1],
  "expiry hides an entry and a purge frees its slot",
);
assert.deepEqual(
  expiryCache(2, [
    ["set", 0, "a", 7, 100],
    ["set", 0, "b", 8, 50],
    ["set", 1, "c", 9, 100],
    ["get", 1, "b"],
    ["get", 1, "a"],
    ["get", 1, "c"],
  ]),
  [-1, 7, 9],
  "the live entry with the earliest expiry is evicted",
);
assert.deepEqual(
  expiryCache(2, [
    ["set", 0, "x", 1, 10],
    ["set", 0, "m", 2, 10],
    ["set", 1, "z", 3, 10],
    ["get", 1, "m"],
    ["get", 1, "x"],
    ["get", 1, "z"],
  ]),
  [-1, 1, 3],
  "an expiry tie evicts the smallest key",
);
assert.deepEqual(
  expiryCache(1, [
    ["set", 0, "a", 1, 5],
    ["set", 1, "a", 2, 5],
    ["get", 5, "a"],
    ["get", 6, "a"],
  ]),
  [2, -1],
  "a live overwrite extends the lifetime and death lands exactly at expiry",
);
assert.deepEqual(
  expiryCache(1, [
    ["set", 0, "a", 1, 2],
    ["set", 2, "b", 2, 5],
    ["get", 2, "a"],
    ["get", 3, "b"],
  ]),
  [-1, 2],
  "a dead entry gives way without touching the newcomer",
);
assert.throws(() => expiryCache(0, []), Error, "zero capacity is rejected");
assert.throws(
  () => expiryCache(2, [["set", 0, "a", 1, 0]]),
  Error,
  "zero ttl is rejected",
);
assert.throws(
  () => expiryCache(2, [["set", 5, "a", 1, 5], ["get", 4, "a"]]),
  Error,
  "a backwards clock is rejected",
);
assert.throws(
  () => expiryCache(2, [["put", 0, "a", 1, 5]]),
  Error,
  "an unknown operation is rejected",
);
console.log("ok");
