import assert from "node:assert/strict";
import { classifyHumpCars } from "./solution.ts";

assert.deepEqual(
  classifyHumpCars(
    [
      ["c1", "north"],
      ["c2", "south"],
      ["c3", "north"],
      ["c4", "east"],
    ],
    { north: 3, south: 1, east: 3 },
  ),
  { train: ["c2", "c1", "c3", "c4"], unrouted: [] },
  "track 1 is drawn before track 3 and each track keeps arrival order",
);

assert.deepEqual(
  classifyHumpCars(
    [
      ["a", "x"],
      ["b", "x"],
      ["c", "x"],
    ],
    { x: 2 },
  ),
  { train: ["a", "b", "c"], unrouted: [] },
  "one track is drawn off in the order the cars arrived",
);

assert.deepEqual(
  classifyHumpCars(
    [
      ["a", "far"],
      ["b", "near"],
    ],
    { far: 9, near: 2 },
  ),
  { train: ["b", "a"], unrouted: [] },
  "the track used first is not drawn first",
);

assert.deepEqual(
  classifyHumpCars(
    [
      ["a", "x"],
      ["b", "unknown"],
      ["c", "x"],
    ],
    { x: 1 },
  ),
  { train: ["a", "c"], unrouted: ["b"] },
  "an unchalked destination goes to the rejection track",
);

assert.deepEqual(
  classifyHumpCars([["a", "q"]], {}),
  { train: [], unrouted: ["a"] },
  "an empty routing table rejects everything",
);

assert.deepEqual(
  classifyHumpCars(
    [
      ["w1", "ore"],
      ["w2", "coal"],
      ["w3", "ore"],
      ["w4", "grain"],
      ["w5", "coal"],
    ],
    { ore: 12, coal: 4, grain: 7 },
  ),
  { train: ["w2", "w5", "w4", "w1", "w3"], unrouted: [] },
  "track numbers order numerically, not as written",
);

assert.throws(() => classifyHumpCars("c1", { x: 1 }), Error, "the cut must be a list");
assert.throws(() => classifyHumpCars([], { x: 1 }), Error, "an empty cut is rejected");
assert.throws(() => classifyHumpCars([["a"]], { x: 1 }), Error, "a one-part entry is rejected");
assert.throws(() => classifyHumpCars([["a", ""]], { x: 1 }), Error, "an empty destination is rejected");
assert.throws(() => classifyHumpCars([[5, "x"]], { x: 1 }), Error, "a non-string car number is rejected");
assert.throws(
  () =>
    classifyHumpCars(
      [
        ["a", "x"],
        ["a", "x"],
      ],
      { x: 1 },
    ),
  Error,
  "a repeated car number is rejected",
);
assert.throws(() => classifyHumpCars([["a", "x"]], [1, 2]), Error, "a list is no routing table");
assert.throws(() => classifyHumpCars([["a", "x"]], { x: 0 }), Error, "track zero is rejected");
assert.throws(() => classifyHumpCars([["a", "x"]], { x: 1.5 }), Error, "a fractional track is rejected");
console.log("ok");
