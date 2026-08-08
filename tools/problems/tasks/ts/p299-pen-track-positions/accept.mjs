import assert from "node:assert/strict";
import { penTrackPositions } from "./solution.ts";

const font = {
  advances: { T: 6, o: 5, e: 5, ".": 3, A: 7, V: 7, i: 1 },
  groups: { round: "oe", cap: "TAV" },
  pairs: [
    ["T", "{round}", -2],
    ["{cap}", "{round}", -1],
    ["o", ".", -3],
  ],
};

assert.deepEqual(
  penTrackPositions("", font),
  { positions: [], total: 0 },
  "an empty text lays no glyph",
);
assert.deepEqual(
  penTrackPositions("A", font),
  { positions: [0], total: 7 },
  "one glyph sits at pen zero",
);
assert.deepEqual(
  penTrackPositions("To", font),
  { positions: [0, 4], total: 9 },
  "two rows fit T beside o and only the topmost is granted",
);
assert.deepEqual(
  penTrackPositions("Toe.", font),
  { positions: [0, 4, 9, 14], total: 17 },
  "one shift among three pairs moves every pen after it",
);
assert.deepEqual(
  penTrackPositions("Ao", font),
  { positions: [0, 6], total: 11 },
  "a row with a group on both sides fits A beside o",
);
assert.deepEqual(
  penTrackPositions("Ae", font),
  { positions: [0, 6], total: 11 },
  "the round group holds e as well as o",
);
assert.deepEqual(
  penTrackPositions("o.", font),
  { positions: [0, 2], total: 5 },
  "a row of two plain glyphs still fits",
);
assert.deepEqual(
  penTrackPositions("oo", font),
  { positions: [0, 5], total: 10 },
  "no row fits o beside o, so the pen only advances",
);
assert.deepEqual(
  penTrackPositions("VVo", font),
  { positions: [0, 7, 13], total: 18 },
  "the group row fits the second V beside o but not V beside V",
);

const bare = { advances: { A: 1, B: 1 }, groups: {}, pairs: [] };
assert.throws(() => penTrackPositions(5, font), Error, "a text is a string");
assert.throws(() => penTrackPositions("A", "font"), Error, "a font is an object");
assert.throws(
  () => penTrackPositions("A", { advances: [], groups: {}, pairs: [] }),
  Error,
  "advances is a plain mapping",
);
assert.throws(
  () => penTrackPositions("A", { advances: { A: -1 }, groups: {}, pairs: [] }),
  Error,
  "an advance is never negative",
);
assert.throws(
  () => penTrackPositions("A", { advances: { A: 1 }, groups: { cap: 5 }, pairs: [] }),
  Error,
  "a group holds a string",
);
assert.throws(
  () => penTrackPositions("A", { advances: { A: 1 }, groups: {}, pairs: "x" }),
  Error,
  "pairs is a list",
);
assert.throws(
  () => penTrackPositions("A", { advances: { A: 1 }, groups: {}, pairs: [["A", "A"]] }),
  Error,
  "a row carries a shift as well",
);
assert.throws(
  () => penTrackPositions("A", { ...bare, pairs: [["{tall}", "A", 1]] }),
  Error,
  "no group is named tall",
);
assert.throws(
  () => penTrackPositions("A", { ...bare, pairs: [["AB", "A", 1]] }),
  Error,
  "a side of two plain glyphs is no side",
);
assert.throws(
  () => penTrackPositions("A", { ...bare, pairs: [["A", "A", 0.5]] }),
  Error,
  "a shift is whole",
);
assert.throws(() => penTrackPositions("Z", font), Error, "Z has no advance");
assert.throws(
  () =>
    penTrackPositions("ii", {
      advances: { i: 1 },
      groups: {},
      pairs: [["i", "i", -5]],
    }),
  Error,
  "the pen may not fall below zero",
);
console.log("ok");
