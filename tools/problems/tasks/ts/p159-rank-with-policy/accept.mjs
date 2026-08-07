import assert from "node:assert/strict";
import { rankWithPolicy } from "./solution.ts";

const scores = [40, 10, 30, 30, 10];
assert.deepEqual(
  rankWithPolicy(scores, "dense", "asc"),
  [3, 1, 2, 2, 1],
  "dense ascending never skips",
);
assert.deepEqual(
  rankWithPolicy(scores, "gapped", "asc"),
  [5, 1, 3, 3, 1],
  "gapped ascending opens gaps after ties",
);
assert.deepEqual(
  rankWithPolicy(scores, "entry", "asc"),
  [5, 1, 3, 4, 2],
  "entry ascending breaks ties by input order",
);
assert.deepEqual(
  rankWithPolicy(scores, "dense", "desc"),
  [1, 3, 2, 2, 3],
  "dense descending",
);
assert.deepEqual(
  rankWithPolicy(scores, "gapped", "desc"),
  [1, 4, 2, 2, 4],
  "gapped descending",
);
assert.deepEqual(
  rankWithPolicy(scores, "entry", "desc"),
  [1, 4, 2, 3, 5],
  "entry descending",
);
assert.deepEqual(
  rankWithPolicy([7, 7, 7], "entry", "asc"),
  [1, 2, 3],
  "entry splits an all-equal field by position",
);
assert.deepEqual(
  rankWithPolicy([7, 7, 7], "gapped", "desc"),
  [1, 1, 1],
  "gapped keeps an all-equal field at one",
);
assert.throws(() => rankWithPolicy([], "dense", "asc"), Error, "empty list");
assert.throws(
  () => rankWithPolicy([1, 2.5], "dense", "asc"),
  Error,
  "fractional score",
);
assert.throws(
  () => rankWithPolicy([1, 2], "standard", "asc"),
  Error,
  "unknown policy",
);
assert.throws(
  () => rankWithPolicy([1, 2], "dense", "down"),
  Error,
  "unknown direction",
);
console.log("ok");
