import assert from "node:assert/strict";
import { findSplitParcels } from "./solution.ts";

assert.deepEqual(findSplitParcels(["AAB", "AAB", "CCB"]), [], "three whole parcels");
assert.deepEqual(
  findSplitParcels(["AAAA", "A..A", "AAAA"]),
  [],
  "a ring around unclaimed ground is still whole",
);
assert.deepEqual(
  findSplitParcels(["..A..", ".AAA.", "..A.."]),
  [],
  "a cross is whole",
);
assert.deepEqual(
  findSplitParcels(["ABA", "BBB", "ABA"]),
  ["A:4"],
  "corners of one letter are four pieces while the letter between them holds",
);
assert.deepEqual(
  findSplitParcels(["AB", "BA"]),
  ["A:2", "B:2"],
  "diagonal neighbours do not touch",
);
assert.deepEqual(
  findSplitParcels(["A.A"]),
  ["A:2"],
  "unclaimed ground cuts a parcel in two",
);
assert.deepEqual(
  findSplitParcels(["ABCA"]),
  ["A:2"],
  "a single row with the same letter at both ends",
);
assert.deepEqual(
  findSplitParcels(["AABBB", "A.B.B", "AABBB"]),
  [],
  "two whole parcels side by side",
);
assert.throws(() => findSplitParcels([]), Error, "a map with no rows is rejected");
assert.throws(() => findSplitParcels(["AB", "A"]), Error, "a ragged map is rejected");
assert.throws(() => findSplitParcels(["Ab"]), Error, "a lowercase marking is rejected");
assert.throws(() => findSplitParcels(["A1"]), Error, "a digit marking is rejected");
assert.throws(() => findSplitParcels([".."]), Error, "a map claiming nothing is rejected");
assert.throws(() => findSplitParcels("AB"), Error, "a bare string is rejected");
console.log("ok");
