import assert from "node:assert/strict";
import { stitchTables } from "./solution.ts";

const crew = [
  { badge: "b1", post: "deck" },
  { badge: "b2", post: "helm" },
  { badge: "b3", post: "galley" },
];
const shifts = [
  { badge: "b2", watch: 4 },
  { badge: "b1", watch: 2 },
];

assert.deepEqual(
  stitchTables(crew, shifts, "badge", "inner"),
  [
    { badge: "b1", post: "deck", watch: 2 },
    { badge: "b2", post: "helm", watch: 4 },
  ],
  "inner keeps matched records in left order",
);
assert.deepEqual(
  stitchTables(crew, shifts, "badge", "left"),
  [
    { badge: "b1", post: "deck", watch: 2 },
    { badge: "b2", post: "helm", watch: 4 },
    { badge: "b3", post: "galley", watch: null },
  ],
  "left mode keeps the unmatched record with a null column",
);
assert.deepEqual(
  stitchTables(
    [{ badge: "b1" }, { badge: "b1", post: "bow" }],
    [{ badge: "b1", watch: 7, berth: "aft" }],
    "badge",
    "inner",
  ),
  [
    { badge: "b1", watch: 7, berth: "aft" },
    { badge: "b1", post: "bow", watch: 7, berth: "aft" },
  ],
  "repeated left keys each join, ragged records keep their own columns",
);
assert.deepEqual(
  stitchTables(
    [{ badge: "b9", post: "deck" }],
    [{ badge: "b1", watch: 1 }, { badge: "b2" }],
    "badge",
    "left",
  ),
  [{ badge: "b9", post: "deck", watch: null }],
  "null filling covers every right column seen anywhere",
);
assert.deepEqual(
  stitchTables([{ badge: "b9" }], shifts, "badge", "inner"),
  [],
  "inner with no matches is empty",
);
assert.deepEqual(stitchTables([], shifts, "badge", "left"), [], "an empty left table");
const before = JSON.stringify(crew);
stitchTables(crew, shifts, "badge", "left");
assert.equal(JSON.stringify(crew), before, "the left table is not modified");
assert.throws(
  () => stitchTables(crew, [{ badge: "b1" }, { badge: "b1" }], "badge", "inner"),
  Error,
  "a repeated right key is rejected",
);
assert.throws(
  () => stitchTables(crew, [{ badge: "b1", post: "aft" }], "badge", "inner"),
  Error,
  "a shared non-key column is rejected",
);
assert.throws(
  () =>
    stitchTables(
      [{ badge: "b8", post: "x" }],
      [{ badge: "b1", post: "aft" }],
      "badge",
      "inner",
    ),
  Error,
  "the column clash is detected even with no matching keys",
);
assert.throws(
  () => stitchTables([{ post: "deck" }], shifts, "badge", "inner"),
  Error,
  "a record missing the key column is rejected",
);
assert.throws(
  () => stitchTables([{ badge: 7 }], shifts, "badge", "inner"),
  Error,
  "a non-string key value is rejected",
);
assert.throws(
  () => stitchTables(crew, shifts, "badge", "outer"),
  Error,
  "an unknown mode is rejected",
);
console.log("ok");
