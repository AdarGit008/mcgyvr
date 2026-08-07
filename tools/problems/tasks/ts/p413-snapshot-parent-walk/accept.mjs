import assert from "node:assert/strict";
import { orderSnapshotLoad } from "./solution.ts";

const shelf = [
  { name: "jan", parent: "" },
  { name: "feb", parent: "jan" },
  { name: "mar", parent: "feb" },
  { name: "side", parent: "jan" },
];

assert.deepEqual(
  orderSnapshotLoad(shelf, "mar"),
  { found: "yes", order: ["jan", "feb", "mar"], why: "" },
  "the whole image comes first and the wanted snapshot last",
);
assert.deepEqual(
  orderSnapshotLoad(shelf, "jan"),
  { found: "yes", order: ["jan"], why: "" },
  "a whole image needs nothing else",
);
assert.deepEqual(
  orderSnapshotLoad(shelf, "side"),
  { found: "yes", order: ["jan", "side"], why: "" },
  "a branch off the whole image loads in two steps",
);
assert.deepEqual(
  orderSnapshotLoad(shelf, "nope"),
  { found: "no", order: [], why: "unknown" },
  "a wanted name the archive lacks is unknown",
);
assert.deepEqual(
  orderSnapshotLoad([{ name: "apr", parent: "gone" }], "apr"),
  { found: "no", order: [], why: "unknown" },
  "a parent the archive lacks is unknown, not a shorter chain",
);
assert.deepEqual(
  orderSnapshotLoad(
    [
      { name: "one", parent: "two" },
      { name: "two", parent: "one" },
    ],
    "one",
  ),
  { found: "no", order: [], why: "cycle" },
  "two snapshots pointing at each other are a cycle",
);
assert.deepEqual(
  orderSnapshotLoad([{ name: "loop", parent: "loop" }], "loop"),
  { found: "no", order: [], why: "cycle" },
  "a snapshot naming itself is a cycle",
);
assert.deepEqual(
  orderSnapshotLoad([], "mar"),
  { found: "no", order: [], why: "unknown" },
  "an empty archive holds nothing wanted",
);

assert.throws(
  () => orderSnapshotLoad("mar", "mar"),
  Error,
  "an archive that is a string is rejected",
);
assert.throws(
  () => orderSnapshotLoad([{ name: "jan" }], "jan"),
  Error,
  "a snapshot without parent is rejected",
);
assert.throws(
  () => orderSnapshotLoad([{ name: "", parent: "" }], "jan"),
  Error,
  "an empty name is rejected",
);
assert.throws(
  () => orderSnapshotLoad([{ name: "jan", parent: 3 }], "jan"),
  Error,
  "a parent that is a number is rejected",
);
assert.throws(
  () =>
    orderSnapshotLoad(
      [
        { name: "jan", parent: "" },
        { name: "jan", parent: "feb" },
      ],
      "jan",
    ),
  Error,
  "a repeated name is rejected",
);
assert.throws(
  () => orderSnapshotLoad(shelf, ""),
  Error,
  "an empty wanted name is rejected",
);
assert.throws(
  () => orderSnapshotLoad(shelf, 7),
  Error,
  "a wanted name that is a number is rejected",
);
console.log("ok");
