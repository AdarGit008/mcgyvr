import assert from "node:assert/strict";
import { buildPickWaves } from "./solution.ts";

const day = [
  { ref: "o1", lines: 4, zones: ["a"] },
  { ref: "o2", lines: 3, zones: ["b"] },
  { ref: "o3", lines: 2, zones: ["c"] },
  { ref: "o4", lines: 9, zones: ["c"] },
  { ref: "o5", lines: 12, zones: ["a"] },
  { ref: "o6", lines: 1, zones: ["a", "b", "c"] },
  { ref: "o7", lines: 1, zones: ["c"] },
  { ref: "o8", lines: 1, zones: ["c"] },
  { ref: "o9", lines: 1, zones: ["c"] },
  { ref: "o10", lines: 1, zones: ["d"] },
  { ref: "o11", lines: 1, zones: ["c"] },
];

assert.deepEqual(
  buildPickWaves(day, { lines: 10, orders: 3, zones: 2 }),
  {
    waves: [
      { name: "w1", refs: ["o1", "o2"], lines: 7, zones: ["a", "b"] },
      { name: "w2", refs: ["o3"], lines: 2, zones: ["c"] },
      { name: "w3", refs: ["o4", "o7"], lines: 10, zones: ["c"] },
      { name: "w4", refs: ["o8", "o9", "o10"], lines: 3, zones: ["c", "d"] },
      { name: "w5", refs: ["o11"], lines: 1, zones: ["c"] },
    ],
    refused: ["o5", "o6"],
  },
  "all three limits bite in turn and the refusals leave the open wave alone",
);
assert.deepEqual(
  buildPickWaves([], { lines: 5, orders: 2, zones: 1 }),
  { waves: [], refused: [] },
  "no orders release no waves",
);
assert.deepEqual(
  buildPickWaves([{ ref: "a1", lines: 2, zones: ["b", "a"] }], { lines: 9, orders: 9, zones: 9 }),
  { waves: [{ name: "w1", refs: ["a1"], lines: 2, zones: ["a", "b"] }], refused: [] },
  "a wave's letters come out alphabetical whatever order the order gave them",
);
assert.deepEqual(
  buildPickWaves(day.slice(0, 2), { lines: 100, orders: 100, zones: 6 }),
  { waves: [{ name: "w1", refs: ["o1", "o2"], lines: 7, zones: ["a", "b"] }], refused: [] },
  "generous limits keep everything in one wave",
);
assert.deepEqual(
  buildPickWaves(
    [
      { ref: "x1", lines: 5, zones: ["e"] },
      { ref: "x2", lines: 5, zones: ["e"] },
      { ref: "x3", lines: 5, zones: ["e"] },
    ],
    { lines: 5, orders: 4, zones: 1 },
  ),
  {
    waves: [
      { name: "w1", refs: ["x1"], lines: 5, zones: ["e"] },
      { name: "w2", refs: ["x2"], lines: 5, zones: ["e"] },
      { name: "w3", refs: ["x3"], lines: 5, zones: ["e"] },
    ],
    refused: [],
  },
  "an order filling the line limit exactly still opens its own wave next time",
);
assert.deepEqual(
  buildPickWaves(
    [
      { ref: "y1", lines: 1, zones: ["a", "b"] },
      { ref: "y2", lines: 1, zones: ["b", "c"] },
    ],
    { lines: 9, orders: 9, zones: 3 },
  ),
  { waves: [{ name: "w1", refs: ["y1", "y2"], lines: 2, zones: ["a", "b", "c"] }], refused: [] },
  "letters shared between orders are counted once",
);

const limits = { lines: 5, orders: 2, zones: 2 };
assert.throws(() => buildPickWaves(day, []), Error, "the limits must be a mapping");
assert.throws(() => buildPickWaves(day, { lines: 0, orders: 2, zones: 2 }), Error, "a limit of zero");
assert.throws(() => buildPickWaves("orders", limits), Error, "the orders must be a list");
assert.throws(() => buildPickWaves(["o1"], limits), Error, "an order must be a mapping");
assert.throws(
  () => buildPickWaves([{ ref: "a", lines: 1, zones: ["a"] }, { ref: "a", lines: 1, zones: ["a"] }], limits),
  Error,
  "two orders may not share a ref",
);
assert.throws(
  () => buildPickWaves([{ ref: "a", lines: 1.5, zones: ["a"] }], limits),
  Error,
  "lines must be whole",
);
assert.throws(
  () => buildPickWaves([{ ref: "a", lines: 1, zones: [] }], limits),
  Error,
  "an order needs a zone",
);
assert.throws(
  () => buildPickWaves([{ ref: "a", lines: 1, zones: ["g"] }], limits),
  Error,
  "a letter past f is refused",
);
assert.throws(
  () => buildPickWaves([{ ref: "a", lines: 1, zones: ["a", "a"] }], limits),
  Error,
  "a repeated zone is refused",
);
console.log("ok");
