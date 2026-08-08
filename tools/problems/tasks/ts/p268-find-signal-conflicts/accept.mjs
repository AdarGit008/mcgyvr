import assert from "node:assert/strict";
import { findSignalConflicts } from "./solution.ts";

const junction = [
  { name: "north", offset: 0, green: 20, amber: 4 },
  { name: "south", offset: 0, green: 20, amber: 4 },
  { name: "east", offset: 26, green: 20, amber: 4 },
  { name: "west", offset: 55, green: 8, amber: 2 },
];
const ring = [
  { name: "loop", offset: 18, green: 4, amber: 0 },
  { name: "gate", offset: 15, green: 5, amber: 0 },
  { name: "spur", offset: 2, green: 2, amber: 0 },
];
const tight = [
  { name: "a", offset: 0, green: 10, amber: 0 },
  { name: "b", offset: 10, green: 10, amber: 0 },
  { name: "c", offset: 9, green: 5, amber: 0 },
];

assert.deepEqual(findSignalConflicts(60, junction, []), [], "no watched pairs, no report");
assert.deepEqual(
  findSignalConflicts(60, junction, [["north", "east"], ["east", "west"]]),
  [],
  "approaches that never share a second"
);
assert.deepEqual(
  findSignalConflicts(60, junction, [["north", "south"]]),
  ["north~south@0"],
  "two approaches running the same stage"
);
assert.deepEqual(
  findSignalConflicts(60, junction, [["west", "north"]]),
  ["west~north@0"],
  "a stage that wraps past the end of the cycle"
);
assert.deepEqual(
  findSignalConflicts(60, junction, [["north", "south"], ["west", "east"], ["west", "south"]]),
  ["north~south@0", "west~south@0"],
  "two clashes at the same second sort by their text"
);
assert.deepEqual(
  findSignalConflicts(20, ring, [["loop", "gate"]]),
  ["loop~gate@18"],
  "the earliest shared second sits before the wrap"
);
assert.deepEqual(findSignalConflicts(20, ring, [["loop", "spur"]]), [], "a wrapped tail that still clears");
assert.deepEqual(
  findSignalConflicts(20, tight, [["a", "b"], ["a", "c"], ["b", "c"]]),
  ["a~c@9", "b~c@10"],
  "two clashes reported in second order"
);
assert.deepEqual(
  findSignalConflicts(20, tight, [["b", "a"], ["c", "a"]]),
  ["c~a@9"],
  "a pair keeps the order it was written in"
);
assert.deepEqual(
  findSignalConflicts(20, [{ name: "x", offset: 0, green: 20, amber: 0 }, { name: "y", offset: 5, green: 1, amber: 0 }], [["x", "y"]]),
  ["x~y@5"],
  "an approach green for the whole cycle"
);
assert.deepEqual(
  findSignalConflicts(20, [{ name: "solo", offset: 0, green: 1, amber: 0 }], []),
  [],
  "a single approach with nothing to clash with"
);

assert.throws(() => findSignalConflicts(1.5, ring, []), Error, "a fractional cycle");
assert.throws(() => findSignalConflicts(1, ring, []), Error, "a cycle under two seconds");
assert.throws(() => findSignalConflicts(3601, ring, []), Error, "a cycle past the ceiling");
assert.throws(() => findSignalConflicts(20, [], []), Error, "an empty approach list");
assert.throws(() => findSignalConflicts(20, "ring", []), Error, "approaches given as text");
assert.throws(() => findSignalConflicts(20, [{ name: "a", offset: 0, green: 5 }], []), Error, "an approach missing amber");
assert.throws(() => findSignalConflicts(20, [{ name: "", offset: 0, green: 5, amber: 0 }], []), Error, "an empty approach name");
assert.throws(() => findSignalConflicts(20, [{ name: "a", offset: 20, green: 5, amber: 0 }], []), Error, "an offset equal to the cycle");
assert.throws(() => findSignalConflicts(20, [{ name: "a", offset: 0, green: 0, amber: 0 }], []), Error, "a stage with no green at all");
assert.throws(() => findSignalConflicts(20, [{ name: "a", offset: 0, green: 15, amber: 6 }], []), Error, "green plus amber outrunning the cycle");
assert.throws(
  () => findSignalConflicts(20, [{ name: "a", offset: 0, green: 5, amber: 0 }, { name: "a", offset: 6, green: 2, amber: 0 }], []),
  Error,
  "a repeated approach name"
);
assert.throws(() => findSignalConflicts(20, ring, [["loop"]]), Error, "a pair naming only one approach");
assert.throws(() => findSignalConflicts(20, ring, [["loop", "nope"]]), Error, "a pair naming an undeclared approach");
assert.throws(() => findSignalConflicts(20, ring, [["loop", "loop"]]), Error, "a pair naming one approach twice");
assert.throws(() => findSignalConflicts(20, ring, [["loop", "gate"], ["gate", "loop"]]), Error, "the same pair listed twice");
assert.throws(() => findSignalConflicts(20, ring, "pairs"), Error, "pairs given as text");
console.log("ok");
