import assert from "node:assert/strict";
import { mendRowBlocks } from "./solution.ts";

const sheet = ["r1", "r2", "r3", "r4", "r5"];

assert.deepEqual(
  mendRowBlocks(sheet, []),
  { rows: ["r1", "r2", "r3", "r4", "r5"], rejected: [] },
  "no blocks leaves the sheet alone",
);
assert.deepEqual(
  mendRowBlocks(sheet, [{ start: 2, drop: 1, insert: ["R2"], guard: "r2" }]),
  { rows: ["r1", "R2", "r3", "r4", "r5"], rejected: [] },
  "one row swapped for one row",
);
assert.deepEqual(
  mendRowBlocks(sheet, [{ start: 3, drop: 0, insert: ["x"], guard: "r3" }]),
  { rows: ["r1", "r2", "x", "r3", "r4", "r5"], rejected: [] },
  "a block that drops nothing pushes its rows in ahead of start",
);
assert.deepEqual(
  mendRowBlocks(sheet, [{ start: 6, drop: 0, insert: ["r6"], guard: null }]),
  { rows: ["r1", "r2", "r3", "r4", "r5", "r6"], rejected: [] },
  "a start one past the sheet adds at the foot",
);
assert.deepEqual(
  mendRowBlocks(sheet, [
    { start: 1, drop: 1, insert: ["A", "B"], guard: "r1" },
    { start: 4, drop: 1, insert: ["D"], guard: "r4" },
  ]),
  { rows: ["A", "B", "r2", "r3", "D", "r5"], rejected: [] },
  "a block that grew the sheet does not drag the next one along",
);
assert.deepEqual(
  mendRowBlocks(sheet, [
    { start: 1, drop: 2, insert: [], guard: "r1" },
    { start: 4, drop: 1, insert: ["D"], guard: "r4" },
  ]),
  { rows: ["r3", "D", "r5"], rejected: [] },
  "a block that shrank the sheet does not drag the next one back",
);
assert.deepEqual(
  mendRowBlocks(sheet, [
    { start: 1, drop: 1, insert: ["A", "B"], guard: "r1" },
    { start: 3, drop: 1, insert: ["C"], guard: "nope" },
    { start: 5, drop: 1, insert: ["E"], guard: "r5" },
  ]),
  { rows: ["A", "B", "r2", "r3", "r4", "E"], rejected: [1] },
  "a turned-away block adds no offset of its own",
);
assert.deepEqual(
  mendRowBlocks(sheet, [{ start: 2, drop: 1, insert: ["X"], guard: "nope" }]),
  { rows: ["r1", "r2", "r3", "r4", "r5"], rejected: [0] },
  "a guard that names the wrong row turns the block away",
);
assert.deepEqual(
  mendRowBlocks(sheet, [{ start: 5, drop: 3, insert: [], guard: "r5" }]),
  { rows: ["r1", "r2", "r3", "r4", "r5"], rejected: [0] },
  "a reach past the foot of the sheet turns the block away",
);
assert.deepEqual(
  mendRowBlocks([], [{ start: 1, drop: 0, insert: ["only"], guard: null }]),
  { rows: ["only"], rejected: [] },
  "an empty sheet may still be written into",
);

const rejects = (rows, blocks) => {
  try {
    mendRowBlocks(rows, blocks);
  } catch {
    return true;
  }
  return false;
};

assert.ok(rejects(sheet, [{ start: 0, drop: 0, insert: [], guard: null }]), "a start below one is refused");
assert.ok(rejects(sheet, [{ start: 1, drop: -1, insert: [], guard: null }]), "a drop below none is refused");
assert.ok(rejects(sheet, [{ start: 1, drop: 0, insert: [], guard: 7 }]), "a guard that is neither null nor a string is refused");
assert.ok(
  rejects(sheet, [
    { start: 3, drop: 0, insert: [], guard: null },
    { start: 2, drop: 0, insert: [], guard: null },
  ]),
  "starts that do not climb are refused",
);
assert.ok(
  rejects(sheet, [
    { start: 1, drop: 2, insert: [], guard: null },
    { start: 2, drop: 0, insert: [], guard: null },
  ]),
  "a block reaching into the next is refused",
);
assert.ok(rejects(sheet, [{ start: 1, drop: 0, insert: "row", guard: null }]), "an insert that is not a list is refused");
assert.ok(rejects(["a", 2], []), "a sheet holding a non-string is refused");
assert.ok(rejects(sheet, ["block"]), "a block that is not a mapping is refused");
console.log("ok");
