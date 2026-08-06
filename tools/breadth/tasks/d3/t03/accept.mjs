import assert from "node:assert/strict";
import { schedule } from "./solution.ts";

assert.deepEqual(schedule([]), { total: 0, chosen: [] }, "empty input");

assert.deepEqual(
  schedule([{ start: 0, end: 3, weight: 5 }, { start: 3, end: 6, weight: 5 }]),
  { total: 10, chosen: [0, 1] },
  "touching intervals are compatible",
);

assert.deepEqual(
  schedule([
    { start: 1, end: 10, weight: 8 },
    { start: 1, end: 4, weight: 5 },
    { start: 4, end: 10, weight: 5 },
  ]),
  { total: 10, chosen: [1, 2] },
  "two lighter intervals beat one heavy interval",
);

assert.deepEqual(
  schedule([
    { start: 0, end: 2, weight: 1 },
    { start: 2, end: 4, weight: 1 },
    { start: 4, end: 6, weight: 1 },
    { start: 0, end: 6, weight: 10 },
  ]),
  { total: 10, chosen: [3] },
  "one heavy interval beats three light ones",
);

assert.deepEqual(
  schedule([
    { start: 0, end: 5, weight: 4 },
    { start: 5, end: 8, weight: 4 },
    { start: 4, end: 8, weight: 7 },
  ]),
  { total: 8, chosen: [0, 1] },
  "an interval starting one tick before another's end is incompatible",
);

assert.deepEqual(
  schedule([
    { start: 6, end: 9, weight: 3 },
    { start: 0, end: 3, weight: 4 },
    { start: 3, end: 6, weight: 5 },
  ]),
  { total: 12, chosen: [0, 1, 2] },
  "unsorted input maps back to original indices",
);

assert.deepEqual(
  schedule([
    { start: 1, end: 4, weight: 2 },
    { start: 3, end: 5, weight: 4 },
    { start: 0, end: 6, weight: 4 },
    { start: 4, end: 7, weight: 7 },
    { start: 3, end: 9, weight: 2 },
    { start: 5, end: 10, weight: 3 },
    { start: 8, end: 11, weight: 2 },
  ]),
  { total: 11, chosen: [0, 3, 6] },
  "optimum skips locally attractive intervals",
);

const input = [{ start: 5, end: 7, weight: 1 }, { start: 0, end: 2, weight: 1 }];
const snapshot = JSON.stringify(input);
schedule(input);
assert.equal(JSON.stringify(input), snapshot, "the input array is not mutated");
