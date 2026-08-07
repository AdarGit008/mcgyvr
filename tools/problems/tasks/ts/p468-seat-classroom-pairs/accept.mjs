import assert from "node:assert/strict";
import { seatClassroom } from "./solution.ts";

assert.deepEqual(
  seatClassroom({
    rows: 2,
    cols: 3,
    pupils: ["ann", "bob", "cid"],
    together: [["ann", "cid"]],
    apart: [["ann", "bob"]],
  }),
  {
    seated: true,
    grid: [
      ["ann", "cid", "bob"],
      ["", "", ""],
    ],
  },
  "a glued pair sits side by side while a split pair is kept off it",
);

assert.deepEqual(
  seatClassroom({
    rows: 2,
    cols: 2,
    pupils: ["w", "x", "y", "z"],
    together: [["w", "z"]],
    apart: [],
  }),
  {
    seated: true,
    grid: [
      ["w", "x"],
      ["z", "y"],
    ],
  },
  "a glued pair may sit one above the other",
);

assert.deepEqual(
  seatClassroom({
    rows: 1,
    cols: 3,
    pupils: ["a", "b"],
    together: [],
    apart: [["a", "b"]],
  }),
  { seated: true, grid: [["a", "", "b"]] },
  "an empty desk is left between two who must be kept apart",
);

assert.deepEqual(
  seatClassroom({
    rows: 1,
    cols: 2,
    pupils: ["zed", "amy"],
    together: [],
    apart: [],
  }),
  { seated: true, grid: [["amy", "zed"]] },
  "the earliest name alphabetically takes the first desk",
);

assert.deepEqual(
  seatClassroom({
    rows: 2,
    cols: 2,
    pupils: [],
    together: [],
    apart: [],
  }),
  {
    seated: true,
    grid: [
      ["", ""],
      ["", ""],
    ],
  },
  "an empty roster fills nothing and still seats",
);

assert.deepEqual(
  seatClassroom({
    rows: 1,
    cols: 2,
    pupils: ["ann", "bob"],
    together: [],
    apart: [["ann", "bob"]],
  }),
  { seated: false, grid: [] },
  "two desks, two pupils and one split pairing cannot be done",
);

assert.deepEqual(
  seatClassroom({
    rows: 2,
    cols: 1,
    pupils: ["m", "n"],
    together: [],
    apart: [["m", "n"]],
  }),
  { seated: false, grid: [] },
  "desks stacked in a column neighbour each other too",
);

assert.deepEqual(
  seatClassroom({
    rows: 1,
    cols: 3,
    pupils: ["a", "b", "c"],
    together: [["a", "c"]],
    apart: [
      ["a", "b"],
      ["b", "c"],
    ],
  }),
  { seated: false, grid: [] },
  "a row of three cannot satisfy all three pairings at once",
);

assert.throws(
  () => seatClassroom({ rows: 1, cols: 1, pupils: [] }),
  Error,
  "a room short of keys is rejected",
);
assert.throws(
  () =>
    seatClassroom({
      rows: 0,
      cols: 3,
      pupils: [],
      together: [],
      apart: [],
    }),
  Error,
  "a grid with no rows is rejected",
);
assert.throws(
  () =>
    seatClassroom({
      rows: 1,
      cols: 1,
      pupils: ["a", "b"],
      together: [],
      apart: [],
    }),
  Error,
  "more pupils than desks is rejected",
);
assert.throws(
  () =>
    seatClassroom({
      rows: 2,
      cols: 2,
      pupils: ["a", "a"],
      together: [],
      apart: [],
    }),
  Error,
  "two pupils sharing a name are rejected",
);
assert.throws(
  () =>
    seatClassroom({
      rows: 2,
      cols: 2,
      pupils: ["a", "b"],
      together: [["a", "q"]],
      apart: [],
    }),
  Error,
  "a pairing naming an outsider is rejected",
);
assert.throws(
  () =>
    seatClassroom({
      rows: 2,
      cols: 2,
      pupils: ["a", "b"],
      together: [["a", "a"]],
      apart: [],
    }),
  Error,
  "a pairing naming one pupil twice is rejected",
);
assert.throws(
  () =>
    seatClassroom({
      rows: 2,
      cols: 2,
      pupils: ["a", "b"],
      together: [
        ["a", "b"],
        ["b", "a"],
      ],
      apart: [],
    }),
  Error,
  "the same pairing listed twice is rejected",
);
assert.throws(
  () =>
    seatClassroom({
      rows: 2,
      cols: 2,
      pupils: ["a", "b"],
      together: [["a", "b"]],
      apart: [["b", "a"]],
    }),
  Error,
  "a pairing in both lists is rejected",
);
assert.throws(
  () =>
    seatClassroom({
      rows: 2,
      cols: 2,
      pupils: ["a", "b"],
      together: [["a"]],
      apart: [],
    }),
  Error,
  "a pairing of one name is rejected",
);
console.log("ok");
