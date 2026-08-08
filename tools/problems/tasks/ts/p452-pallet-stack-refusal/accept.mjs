import assert from "node:assert/strict";
import { stackPallet } from "./solution.ts";

const it = (name, mass, bears, high, wide, top) => ({ name, mass, bears, high, wide, top });
const roomy = { deck: 200, roof: 100 };

assert.deepEqual(
  stackPallet([it("base", 40, 100, 20, 12, false), it("mid", 30, 50, 15, 10, false), it("cap", 10, 0, 5, 8, true)], roomy),
  { stacked: ["base", "mid", "cap"], refused: "", reason: "", mass: 80, high: 40 },
  "a lawful column of three goes up whole",
);
assert.deepEqual(
  stackPallet([it("base", 40, 100, 20, 12, false), it("cap", 10, 0, 5, 8, true), it("extra", 5, 0, 3, 6, false)], roomy),
  { stacked: ["base", "cap"], refused: "extra", reason: "capped", mass: 50, high: 25 },
  "nothing may ride on a carton flagged top",
);
assert.deepEqual(
  stackPallet([it("base", 40, 100, 20, 10, false), it("wide", 5, 10, 4, 11, false)], roomy),
  { stacked: ["base"], refused: "wide", reason: "overhang", mass: 40, high: 20 },
  "a broader carton may not sit on a narrower one",
);
assert.deepEqual(
  stackPallet([it("base", 40, 20, 20, 12, false), it("mid", 30, 50, 15, 10, false)], roomy),
  { stacked: ["base"], refused: "mid", reason: "crush", mass: 40, high: 20 },
  "the carton directly beneath refuses the load",
);
assert.deepEqual(
  stackPallet(
    [it("base", 40, 45, 20, 12, false), it("mid", 30, 80, 15, 10, false), it("top", 20, 0, 5, 8, false)],
    { deck: 500, roof: 500 },
  ),
  { stacked: ["base", "mid"], refused: "top", reason: "crush", mass: 70, high: 35 },
  "a carton two rungs down is crushed although its neighbour is not",
);
assert.deepEqual(
  stackPallet([it("base", 40, 100, 20, 12, false), it("mid", 30, 50, 15, 10, false)], { deck: 60, roof: 100 }),
  { stacked: ["base"], refused: "mid", reason: "deck", mass: 40, high: 20 },
  "the deck rating stops the column",
);
assert.deepEqual(
  stackPallet([it("base", 40, 100, 20, 12, false), it("mid", 30, 50, 15, 10, false)], { deck: 200, roof: 30 }),
  { stacked: ["base"], refused: "mid", reason: "roof", mass: 40, high: 20 },
  "the doorway rating stops the column",
);
assert.deepEqual(
  stackPallet([], { deck: 10, roof: 10 }),
  { stacked: [], refused: "", reason: "", mass: 0, high: 0 },
  "no cartons at all leaves a bare pallet",
);
assert.deepEqual(
  stackPallet([it("base", 1, 100, 1, 4, false), it("bad", 99, 0, 1, 9, false)], { deck: 10, roof: 10 }),
  { stacked: ["base"], refused: "bad", reason: "overhang", mass: 1, high: 1 },
  "overhang is named ahead of the deck rating",
);
assert.deepEqual(
  stackPallet([it("base", 1, 2, 1, 4, false), it("bad", 99, 0, 1, 4, false)], { deck: 10, roof: 10 }),
  { stacked: ["base"], refused: "bad", reason: "crush", mass: 1, high: 1 },
  "crushing is named ahead of the deck rating",
);
assert.deepEqual(
  stackPallet([it("base", 9, 100, 9, 4, false), it("bad", 9, 0, 9, 4, false)], { deck: 10, roof: 10 }),
  { stacked: ["base"], refused: "bad", reason: "deck", mass: 9, high: 9 },
  "the deck rating is named ahead of the doorway",
);
assert.deepEqual(
  stackPallet([it("only", 7, 0, 3, 5, false)], { deck: 10, roof: 10 }),
  { stacked: ["only"], refused: "", reason: "", mass: 7, high: 3 },
  "a carton that bears nothing is fine with nothing on it",
);
assert.deepEqual(
  stackPallet([it("a", 5, 5, 5, 5, false), it("b", 5, 0, 5, 5, false)], { deck: 10, roof: 10 }),
  { stacked: ["a", "b"], refused: "", reason: "", mass: 10, high: 10 },
  "sitting exactly on every rating is allowed",
);

assert.throws(() => stackPallet("nope", roomy), Error, "items that are not a list are refused");
assert.throws(() => stackPallet([it("a", 1, 1, 1, 1, false)], null), Error, "limits that are not a record are refused");
assert.throws(() => stackPallet([], { deck: 0, roof: 10 }), Error, "a deck rating of nought is refused");
assert.throws(() => stackPallet([], { roof: 10 }), Error, "a missing deck rating is refused");
assert.throws(() => stackPallet([], { deck: 10, roof: 1.5 }), Error, "a fractional doorway rating is refused");
assert.throws(() => stackPallet([["a"]], roomy), Error, "an item that is not a record is refused");
assert.throws(() => stackPallet([it("", 1, 1, 1, 1, false)], roomy), Error, "an empty name is refused");
assert.throws(
  () => stackPallet([it("a", 1, 1, 1, 1, false), it("a", 2, 1, 1, 1, false)], roomy),
  Error,
  "two cartons answering to one name are refused",
);
assert.throws(() => stackPallet([it("a", 0, 1, 1, 1, false)], roomy), Error, "a mass of nought is refused");
assert.throws(() => stackPallet([it("a", 1, -1, 1, 1, false)], roomy), Error, "a negative bearing is refused");
assert.throws(() => stackPallet([it("a", 1, 1, 0, 1, false)], roomy), Error, "a height of nought is refused");
assert.throws(() => stackPallet([it("a", 1, 1, 1, 1.5, false)], roomy), Error, "a fractional width is refused");
assert.throws(() => stackPallet([it("a", 1, 1, 1, 1, "yes")], roomy), Error, "a top flag that is not a boolean is refused");
console.log("ok");
