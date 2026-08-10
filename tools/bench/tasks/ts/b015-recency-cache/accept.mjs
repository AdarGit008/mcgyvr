import assert from "node:assert/strict";
import { newCache, cacheWrite, cacheRead } from "./solution.ts";

assert.deepEqual(newCache(2), { limit: 2, keys: [], store: {} }, "fresh cache");
const cache = newCache(2);
assert.deepEqual(cacheWrite(cache, "a", 1), [], "a write with room spills nothing");
cacheWrite(cache, "b", 2);
assert.deepEqual(
  cache,
  { limit: 2, keys: ["a", "b"], store: { a: 1, b: 2 } },
  "state after two writes",
);
assert.deepEqual(cacheWrite(cache, "c", 3), ["a"], "a full write spills the oldest");
assert.deepEqual(
  cache,
  { limit: 2, keys: ["b", "c"], store: { b: 2, c: 3 } },
  "the spilled key is gone from keys and store",
);
assert.deepEqual(cacheWrite(cache, "b", 9), [], "rewriting a held key spills nothing");
assert.deepEqual(
  cache,
  { limit: 2, keys: ["c", "b"], store: { c: 3, b: 9 } },
  "a rewrite refreshes recency",
);
assert.deepEqual(
  cacheWrite(cache, "d", 4),
  ["c"],
  "the refreshed key survives the next spill",
);
const other = newCache(2);
cacheWrite(other, "x", 7);
cacheWrite(other, "y", 8);
assert.equal(cacheRead(other, "x"), 7, "read returns the held value");
assert.deepEqual(
  cacheWrite(other, "z", 9),
  ["y"],
  "reading x refreshed it, so y spills",
);
assert.throws(() => cacheRead(other, "q"), Error, "reading a missing key");
assert.throws(() => newCache(0), Error, "zero limit is rejected");
assert.throws(() => newCache(2.5), Error, "fractional limit is rejected");
assert.throws(() => cacheWrite(other, 42, 1), Error, "non-string key is rejected");
console.log("ok");
