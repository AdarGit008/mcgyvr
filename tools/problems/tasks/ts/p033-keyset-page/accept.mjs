import assert from "node:assert/strict";
import { keysetPage } from "./solution.ts";

assert.deepEqual(
  keysetPage([1, 3, 5, 7, 9], 0, 2),
  { items: [1, 3], done: false },
  "first page",
);
assert.deepEqual(
  keysetPage([1, 3, 5, 7, 9], 3, 2),
  { items: [5, 7], done: false },
  "middle page from a present cursor",
);
assert.deepEqual(
  keysetPage([1, 3, 5, 7, 9], 7, 2),
  { items: [9], done: true },
  "short final page",
);
assert.deepEqual(
  keysetPage([1, 3, 5, 7, 9], 9, 2),
  { items: [], done: true },
  "cursor at the end",
);
assert.deepEqual(
  keysetPage([1, 3, 5], 4, 10),
  { items: [5], done: true },
  "cursor between ids",
);
assert.deepEqual(
  keysetPage([2, 4, 6], 3, 1),
  { items: [4], done: false },
  "limit exactly consumed with more beyond",
);
assert.deepEqual(keysetPage([], 5, 3), { items: [], done: true }, "empty ids");
assert.throws(() => keysetPage([1, 2], 0, 0), Error, "zero limit is rejected");
assert.throws(() => keysetPage([1, 2], 1.5, 1), Error, "fractional cursor is rejected");
assert.throws(() => keysetPage([1, 2, 2], 0, 1), Error, "repeated id is rejected");
assert.throws(() => keysetPage([3, 1], 0, 1), Error, "descending ids are rejected");
console.log("ok");
