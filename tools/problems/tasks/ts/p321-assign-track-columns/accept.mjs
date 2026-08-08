import assert from "node:assert/strict";
import { assignTrackColumns } from "./solution.ts";

const of = (rows) => rows.map(([label, first, last]) => ({ label, first, last }));

assert.deepEqual(assignTrackColumns([]), [], "nothing to lay out");
assert.deepEqual(assignTrackColumns(of([["a", 0, 0]])), [0], "one span on the first track");
assert.deepEqual(
  assignTrackColumns(of([["a", 0, 2], ["b", 3, 4]])),
  [0, 0],
  "spans that never share a row reuse the track",
);
assert.deepEqual(
  assignTrackColumns(of([["a", 0, 2], ["b", 2, 4]])),
  [0, 1],
  "one shared row is enough to force a second track",
);
assert.deepEqual(
  assignTrackColumns(of([["a", 0, 1], ["b", 1, 2], ["c", 2, 3]])),
  [0, 1, 0],
  "a chain of spans overlapping only at their edges",
);
assert.deepEqual(
  assignTrackColumns(of([["a", 0, 4], ["b", 1, 2], ["c", 3, 4]])),
  [0, 1, 1],
  "the second track is free again below the span that held it",
);
assert.deepEqual(
  assignTrackColumns(of([["a", 0, 5], ["b", 0, 5], ["c", 0, 5]])),
  [0, 1, 2],
  "three spans covering the same rows need three tracks",
);
assert.deepEqual(
  assignTrackColumns(of([["a", 0, 3], ["b", 1, 4], ["c", 2, 5], ["d", 6, 7]])),
  [0, 1, 2, 0],
  "a staircase of overlaps and then a clear span",
);
assert.deepEqual(
  assignTrackColumns(of([["a", 4, 5], ["b", 0, 1], ["c", 2, 3]])),
  [0, 0, 0],
  "spans arriving out of order still stack on one track",
);
assert.throws(() => assignTrackColumns("nope"), Error, "a bare string is rejected");
assert.throws(() => assignTrackColumns([7]), Error, "a span that is not a mapping");
assert.throws(
  () => assignTrackColumns([{ first: 0, last: 1 }]),
  Error,
  "a span with no label is rejected",
);
assert.throws(
  () => assignTrackColumns([{ label: "a", first: 0.5, last: 1 }]),
  Error,
  "a fractional row is rejected",
);
assert.throws(
  () => assignTrackColumns(of([["a", -1, 1]])),
  Error,
  "a row below zero is rejected",
);
assert.throws(
  () => assignTrackColumns(of([["a", 3, 1]])),
  Error,
  "a span ending before it starts is rejected",
);
assert.throws(
  () => assignTrackColumns(of([["a", 0, 1], ["a", 2, 3]])),
  Error,
  "a repeated label is rejected",
);
console.log("ok");
