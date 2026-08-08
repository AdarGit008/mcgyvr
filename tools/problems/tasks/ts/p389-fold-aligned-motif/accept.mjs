import assert from "node:assert/strict";
import { foldAlignedMotif } from "./solution.ts";

assert.deepEqual(
  foldAlignedMotif(["ACGT", "ACGA", "ACGT"], 2),
  { pattern: "ACGT", outliers: [3] },
  "a lone stray letter is thrown away and its column is an outlier",
);
assert.deepEqual(
  foldAlignedMotif(["AC", "GT"], 1),
  { pattern: "RY", outliers: [] },
  "a least of one keeps everything and names the pairs",
);
assert.deepEqual(
  foldAlignedMotif(["A", "C", "G", "T"], 2),
  { pattern: "N", outliers: [] },
  "a column no letter carries far enough falls back to all of them",
);
assert.deepEqual(
  foldAlignedMotif(["AAC", "AGC", "ATC", "AAC"], 2),
  { pattern: "AAC", outliers: [1] },
  "two strays in one column still make one outlier",
);
assert.deepEqual(
  foldAlignedMotif(["ACGTA", "AGGTC", "ACGTG", "ACTTA"], 3),
  { pattern: "ACGTV", outliers: [1, 2] },
  "outliers come back in ascending order beside a rescued column",
);
assert.deepEqual(
  foldAlignedMotif(["A", "C", "G", "A", "C", "G"], 2),
  { pattern: "V", outliers: [] },
  "three surviving letters name a triple code",
);
assert.deepEqual(
  foldAlignedMotif(["C", "G", "T", "C", "G", "T"], 2),
  { pattern: "B", outliers: [] },
  "the triple without A is B",
);
assert.deepEqual(
  foldAlignedMotif(["A", "G", "T", "A", "G", "T"], 2),
  { pattern: "D", outliers: [] },
  "the triple without C is D",
);
assert.deepEqual(
  foldAlignedMotif(["A", "C", "T", "A", "C", "T"], 2),
  { pattern: "H", outliers: [] },
  "the triple without G is H",
);
assert.deepEqual(
  foldAlignedMotif(["CGAT", "GCTA"], 1),
  { pattern: "SSWW", outliers: [] },
  "every pair code is reachable",
);
assert.deepEqual(
  foldAlignedMotif(["GA", "TC"], 1),
  { pattern: "KM", outliers: [] },
  "K and M name their own pairs",
);
assert.deepEqual(
  foldAlignedMotif(["AC", "AT"], 5),
  { pattern: "AY", outliers: [] },
  "a least beyond the row count rescues every column",
);
assert.deepEqual(
  foldAlignedMotif(["GATTACA"], 1),
  { pattern: "GATTACA", outliers: [] },
  "one row folds to itself",
);

assert.throws(() => foldAlignedMotif([], 1), Error, "an empty alignment is rejected");
assert.throws(() => foldAlignedMotif("ACGT", 1), Error, "a non-list alignment is rejected");
assert.throws(() => foldAlignedMotif(["ACGT", ""], 1), Error, "an empty row is rejected");
assert.throws(() => foldAlignedMotif(["ACGT", "AC"], 1), Error, "rows of unequal length are rejected");
assert.throws(() => foldAlignedMotif(["ACGT", 5], 1), Error, "a row that is not a string is rejected");
assert.throws(() => foldAlignedMotif(["ACGN"], 1), Error, "a code inside a row is rejected");
assert.throws(() => foldAlignedMotif(["ACGT"], 0), Error, "a least of zero is rejected");
assert.throws(() => foldAlignedMotif(["ACGT"], 1.5), Error, "a fractional least is rejected");
console.log("ok");
