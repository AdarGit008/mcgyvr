import assert from "node:assert/strict";
import { sortBy } from "./solution.ts";

const tags = (rows) => rows.map((r) => r.tag);

const people = [
  { name: "b", n: 2, tag: 0 },
  { name: "a", n: 2, tag: 1 },
  { name: "a", n: 10, tag: 2 },
  { name: "b", n: 2, tag: 3 },
];
assert.deepEqual(
  tags(sortBy(people, [{ key: "name", dir: "asc" }])),
  [1, 2, 0, 3],
  "stable within equal names",
);
assert.deepEqual(
  tags(sortBy(people, [{ key: "name", dir: "asc" }, { key: "n", dir: "desc" }])),
  [2, 1, 0, 3],
  "secondary key applies only inside primary ties",
);
assert.deepEqual(
  tags(sortBy(people, [{ key: "n", dir: "asc" }, { key: "name", dir: "desc" }])),
  [0, 3, 1, 2],
  "descending string tie-break stays stable for equal names",
);

const mixed = [
  { v: "b", tag: 0 },
  { v: 2, tag: 1 },
  { v: "a", tag: 2 },
  { v: 10, tag: 3 },
  { tag: 4 },
];
assert.deepEqual(
  tags(sortBy(mixed, [{ key: "v", dir: "asc" }])),
  [1, 3, 2, 0, 4],
  "asc: numbers, then strings, then missing",
);
assert.deepEqual(
  tags(sortBy(mixed, [{ key: "v", dir: "desc" }])),
  [4, 0, 2, 3, 1],
  "desc is the exact reverse, missing first",
);

const numericVsLexical = [
  { v: "10", tag: 0 },
  { v: "2", tag: 1 },
  { v: 10, tag: 2 },
  { v: 2, tag: 3 },
];
assert.deepEqual(
  tags(sortBy(numericVsLexical, [{ key: "v", dir: "asc" }])),
  [3, 2, 0, 1],
  "numbers numerically, strings by code units",
);

const original = [{ v: 3, tag: 0 }, { v: 1, tag: 1 }];
const snapshot = JSON.stringify(original);
const sorted = sortBy(original, [{ key: "v", dir: "asc" }]);
assert.equal(JSON.stringify(original), snapshot, "input array is not mutated");
assert.notEqual(sorted, original, "a new array is returned");
assert.deepEqual(tags(sortBy(original, [])), [0, 1], "empty keys keeps order");
