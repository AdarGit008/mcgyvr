import assert from "node:assert/strict";
import { sliceRepeatingBand } from "./solution.ts";

assert.deepEqual(
  sliceRepeatingBand([3, 1, 2], 4, 4),
  [
    { motif: 0, into: 0, joins: 1, runs: 0 },
    { motif: 2, into: 0, joins: 1, runs: 0 },
    { motif: 0, into: 2, joins: 2, runs: 1 },
    { motif: 0, into: 0, joins: 1, runs: 2 },
  ],
  "a three-motif run cut into four-long strips",
);
assert.deepEqual(
  sliceRepeatingBand([5], 5, 3),
  [
    { motif: 0, into: 0, joins: 0, runs: 0 },
    { motif: 0, into: 0, joins: 0, runs: 1 },
    { motif: 0, into: 0, joins: 0, runs: 2 },
  ],
  "one motif as wide as the strip opens every strip afresh",
);
assert.deepEqual(
  sliceRepeatingBand([10], 3, 3),
  [
    { motif: 0, into: 0, joins: 0, runs: 0 },
    { motif: 0, into: 3, joins: 0, runs: 0 },
    { motif: 0, into: 6, joins: 0, runs: 0 },
  ],
  "a strip narrower than the motif never meets a join",
);
assert.deepEqual(
  sliceRepeatingBand([2, 3], 12, 1),
  [{ motif: 0, into: 0, joins: 4, runs: 0 }],
  "a strip wider than the run swallows several joins",
);
assert.deepEqual(sliceRepeatingBand([4, 4], 3, 0), [], "no strips are cut at all");
assert.deepEqual(
  sliceRepeatingBand([1, 1, 1], 2, 3),
  [
    { motif: 0, into: 0, joins: 1, runs: 0 },
    { motif: 2, into: 0, joins: 1, runs: 0 },
    { motif: 1, into: 0, joins: 1, runs: 1 },
  ],
  "every unit boundary is a join when the motifs are one long",
);
assert.deepEqual(
  sliceRepeatingBand([4, 4], 3, 3),
  [
    { motif: 0, into: 0, joins: 0, runs: 0 },
    { motif: 0, into: 3, joins: 1, runs: 0 },
    { motif: 1, into: 2, joins: 1, runs: 0 },
  ],
  "the strip opening deep in a motif reports how far into it stands",
);

assert.throws(() => sliceRepeatingBand("3,1", 4, 2), Error, "the motifs must be a list");
assert.throws(() => sliceRepeatingBand([], 4, 2), Error, "a run of no motifs is rejected");
assert.throws(() => sliceRepeatingBand([3, 0], 4, 2), Error, "a motif of no length is rejected");
assert.throws(() => sliceRepeatingBand([3, 1.5], 4, 2), Error, "a fractional motif is rejected");
assert.throws(() => sliceRepeatingBand([3, "1"], 4, 2), Error, "a written motif is rejected");
assert.throws(() => sliceRepeatingBand([3, 1], 0, 2), Error, "a strip of no width is rejected");
assert.throws(() => sliceRepeatingBand([3, 1], 1001, 2), Error, "too wide a strip is rejected");
assert.throws(() => sliceRepeatingBand([3, 1], 4, -1), Error, "a negative count is rejected");
assert.throws(() => sliceRepeatingBand([3, 1], 4, 501), Error, "too many strips are rejected");
assert.throws(() => sliceRepeatingBand([3, 1], 4, 2.5), Error, "a fractional count is rejected");
console.log("ok");
