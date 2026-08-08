import assert from "node:assert/strict";
import { assignHomeWaves } from "./solution.ts";

const waves = [
  { name: "north", home: "a", cap: 2 },
  { name: "mid", home: "b", cap: 1 },
  { name: "south", home: "c", cap: 3 },
];

assert.deepEqual(
  assignHomeWaves(waves, [
    { ref: "r1", zones: ["a"] },
    { ref: "r2", zones: ["b", "c"] },
    { ref: "r3", zones: ["b"] },
    { ref: "r4", zones: ["a", "c"] },
    { ref: "r5", zones: ["a"] },
    { ref: "r6", zones: ["d"] },
    { ref: "r7", zones: ["c", "a"] },
  ]),
  {
    loads: [
      { name: "north", refs: ["r1", "r4"] },
      { name: "mid", refs: ["r2"] },
      { name: "south", refs: ["r7"] },
    ],
    spill: ["r3", "r5", "r6"],
  },
  "the earliest suitable wave with room takes the order, the rest spill",
);
assert.deepEqual(
  assignHomeWaves(waves, []),
  {
    loads: [
      { name: "north", refs: [] },
      { name: "mid", refs: [] },
      { name: "south", refs: [] },
    ],
    spill: [],
  },
  "every standing wave is reported even when it carries nothing",
);
assert.deepEqual(
  assignHomeWaves([{ name: "solo", home: "z", cap: 1 }], [
    { ref: "q1", zones: ["z"] },
    { ref: "q2", zones: ["z"] },
  ]),
  { loads: [{ name: "solo", refs: ["q1"] }], spill: ["q2"] },
  "a full wave sends the next order to the spill sheet",
);
assert.deepEqual(
  assignHomeWaves(waves, [{ ref: "s1", zones: ["c", "b", "a"] }]),
  {
    loads: [
      { name: "north", refs: ["s1"] },
      { name: "mid", refs: [] },
      { name: "south", refs: [] },
    ],
    spill: [],
  },
  "an order wanting three homes goes to the earliest released of them",
);
assert.deepEqual(
  assignHomeWaves(waves, [{ ref: "s2", zones: ["e", "f"] }]),
  {
    loads: [
      { name: "north", refs: [] },
      { name: "mid", refs: [] },
      { name: "south", refs: [] },
    ],
    spill: ["s2"],
  },
  "an order wanting no home aisle spills at once",
);
assert.deepEqual(
  assignHomeWaves([{ name: "wide", home: "a", cap: 3 }], [
    { ref: "t1", zones: ["a"] },
    { ref: "t2", zones: ["a"] },
    { ref: "t3", zones: ["a"] },
  ]),
  { loads: [{ name: "wide", refs: ["t1", "t2", "t3"] }], spill: [] },
  "a cap is a ceiling, not a target",
);

const one = [{ name: "n", home: "a", cap: 1 }];
assert.throws(() => assignHomeWaves([], []), Error, "no standing waves at all");
assert.throws(() => assignHomeWaves(["n"], []), Error, "a wave must be a mapping");
assert.throws(
  () => assignHomeWaves([{ name: "n", home: "a", cap: 1 }, { name: "n", home: "b", cap: 1 }], []),
  Error,
  "two waves may not share a name",
);
assert.throws(
  () => assignHomeWaves([{ name: "n", home: "a", cap: 1 }, { name: "m", home: "a", cap: 1 }], []),
  Error,
  "two waves may not share a home",
);
assert.throws(() => assignHomeWaves([{ name: "n", home: "A", cap: 1 }], []), Error, "a capital home");
assert.throws(() => assignHomeWaves([{ name: "n", home: "a", cap: 0 }], []), Error, "a cap of zero");
assert.throws(() => assignHomeWaves(one, "orders"), Error, "the orders must be a list");
assert.throws(
  () => assignHomeWaves(one, [{ ref: "x", zones: ["a"] }, { ref: "x", zones: ["a"] }]),
  Error,
  "two orders may not share a ref",
);
assert.throws(() => assignHomeWaves(one, [{ ref: "x", zones: [] }]), Error, "an order needs a zone");
assert.throws(
  () => assignHomeWaves(one, [{ ref: "x", zones: ["a", "a"] }]),
  Error,
  "an order may not name an aisle twice",
);
console.log("ok");
