import assert from "node:assert/strict";
import { traceCache } from "./solution.ts";

const empty = {
  hits: 0,
  misses: 0,
  dropped: 0,
  evictions: [],
  contents: [],
  hotKey: null,
  peak: 0,
};
assert.deepEqual(traceCache(2, []), empty, "an empty trace yields zeros");
assert.deepEqual(
  traceCache(2, [["get", "a"]]),
  { ...empty, misses: 1 },
  "a get of an absent key is a miss and stores nothing",
);
assert.deepEqual(
  traceCache(2, [["put", "a"], ["get", "a"]]),
  { ...empty, hits: 1, contents: ["a"], hotKey: "a", peak: 1 },
  "a put then get is a hit",
);
assert.deepEqual(
  traceCache(2, [["put", "a"], ["put", "b"], ["put", "c"]]),
  { ...empty, evictions: ["a"], contents: ["c", "b"], peak: 2 },
  "overflow evicts the least recently used key",
);
assert.deepEqual(
  traceCache(2, [["put", "a"], ["put", "b"], ["get", "a"], ["put", "c"]]),
  { ...empty, hits: 1, evictions: ["b"], contents: ["c", "a"], hotKey: "a", peak: 2 },
  "a get refreshes recency and saves its key from eviction",
);
assert.deepEqual(
  traceCache(2, [["put", "a"], ["put", "b"], ["put", "a"], ["put", "c"]]),
  { ...empty, evictions: ["b"], contents: ["c", "a"], peak: 2 },
  "a repeated put refreshes rather than duplicates",
);
assert.deepEqual(
  traceCache(2, [["put", "a"], ["put", "b"], ["del", "a"], ["put", "c"]]),
  { ...empty, dropped: 1, contents: ["c", "b"], peak: 2 },
  "a del frees a slot so the next put evicts nothing",
);
assert.deepEqual(
  traceCache(2, [["del", "x"]]),
  empty,
  "a del of an absent key is a no-op",
);
assert.deepEqual(
  traceCache(1, [["put", "a"], ["put", "b"], ["get", "a"]]),
  { ...empty, misses: 1, evictions: ["a"], contents: ["b"], peak: 1 },
  "an evicted key misses on its next get",
);
assert.deepEqual(
  traceCache(1, [["put", "a"], ["put", "b"], ["put", "c"]]),
  { ...empty, evictions: ["a", "b"], contents: ["c"], peak: 1 },
  "capacity one evicts on every new put",
);
assert.deepEqual(
  traceCache(3, [["put", "a"], ["put", "b"], ["put", "c"], ["get", "b"]]),
  { ...empty, hits: 1, contents: ["b", "c", "a"], hotKey: "b", peak: 3 },
  "contents come back most recently used first",
);
assert.deepEqual(
  traceCache(2, [["put", "a"], ["del", "a"], ["put", "a"]]),
  { ...empty, dropped: 1, contents: ["a"], peak: 1 },
  "a key may be stored again after a del",
);
assert.deepEqual(
  traceCache(2, [
    ["put", "u1"],
    ["get", "u1"],
    ["put", "u2"],
    ["get", "u3"],
    ["put", "u3"],
    ["get", "u1"],
    ["del", "u2"],
    ["put", "u4"],
    ["get", "u3"],
  ]),
  {
    hits: 2,
    misses: 2,
    dropped: 1,
    evictions: ["u1"],
    contents: ["u3", "u4"],
    hotKey: "u1",
    peak: 2,
  },
  "a mixed trace: a hit tie goes to the alphabetically first key",
);
assert.deepEqual(
  traceCache(3, [["put", "a"], ["put", "b"], ["put", "c"]]),
  { ...empty, contents: ["c", "b", "a"], peak: 3 },
  "filling to exactly capacity evicts nothing",
);
assert.deepEqual(
  traceCache(3, [["put", "a"], ["put", "b"], ["get", "b"], ["get", "b"], ["get", "a"]]),
  { ...empty, hits: 3, contents: ["a", "b"], hotKey: "b", peak: 2 },
  "the hottest key is the one with the most hits",
);
assert.throws(() => traceCache(0, []), Error, "zero capacity is rejected");
assert.throws(() => traceCache(2.5, []), Error, "fractional capacity is rejected");
assert.throws(() => traceCache(2, "x"), Error, "non-list trace is rejected");
assert.throws(() => traceCache(2, [["get"]]), Error, "a one-item entry is rejected");
assert.throws(
  () => traceCache(2, [["peek", "a"]]),
  Error,
  "an unknown operation is rejected",
);
assert.throws(() => traceCache(2, [["get", ""]]), Error, "an empty key is rejected");
assert.throws(() => traceCache(2, [["get", 7]]), Error, "a non-string key is rejected");
console.log("ok");
