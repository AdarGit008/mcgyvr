import assert from "node:assert/strict";
import { planHoistTrips } from "./solution.ts";

assert.deepEqual(
  planHoistTrips(
    [
      { tag: "north", level: 0 },
      { tag: "south", level: 6 },
    ],
    [3, 3, 0],
  ),
  ["south", "south", "north"],
  "descending is the cheap direction",
);
assert.deepEqual(
  planHoistTrips(
    [
      { tag: "a", level: 0 },
      { tag: "b", level: 10 },
    ],
    [5],
  ),
  ["b"],
  "a five-level drop beats a five-level climb",
);
assert.deepEqual(
  planHoistTrips(
    [
      { tag: "west", level: 4 },
      { tag: "east", level: 4 },
    ],
    [4],
  ),
  ["east"],
  "an equal cost falls to the earlier tag, not the earlier position",
);
assert.deepEqual(
  planHoistTrips([{ tag: "solo", level: 0 }], [6, 1]),
  ["solo", "idle"],
  "reaching twelve rope retires the hoist",
);
assert.deepEqual(
  planHoistTrips([{ tag: "solo", level: 0 }], [5, 4, 3]),
  ["solo", "solo", "solo"],
  "eleven rope leaves a hoist in service",
);
assert.deepEqual(
  planHoistTrips(
    [
      { tag: "a", level: 0 },
      { tag: "b", level: 10 },
    ],
    [5, 5, 0, 10, 10, 10],
  ),
  ["b", "b", "a", "b", "a", "idle"],
  "the bank wears out one hoist at a time",
);
assert.deepEqual(planHoistTrips([{ tag: "solo", level: 2 }], []), [], "no stops");

assert.throws(() => planHoistTrips([], [1]), Error, "empty bank");
assert.throws(
  () =>
    planHoistTrips(
      [
        { tag: "a", level: 0 },
        { tag: "a", level: 1 },
      ],
      [1],
    ),
  Error,
  "repeated tag",
);
assert.throws(
  () => planHoistTrips([{ tag: "idle", level: 0 }], [1]),
  Error,
  "the word idle cannot be a tag",
);
assert.throws(
  () => planHoistTrips([{ tag: "", level: 0 }], [1]),
  Error,
  "an empty tag",
);
assert.throws(
  () => planHoistTrips([{ tag: "a", level: -1 }], [1]),
  Error,
  "a level below the ground",
);
assert.throws(
  () => planHoistTrips([{ tag: "a", level: 0 }], [1.5]),
  Error,
  "a fractional stop",
);
assert.throws(
  () => planHoistTrips([{ tag: "a", level: 0 }], "3"),
  Error,
  "stops is not a list",
);
console.log("ok");
