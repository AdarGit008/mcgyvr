import assert from "node:assert/strict";
import { alignBorderMotifs } from "./solution.ts";

assert.deepEqual(
  alignBorderMotifs([3, 5, 2, 6], 4),
  { edges: [0, 3, 0, 2], freshAt: 3 },
  "the running total is reduced against the run at every edge",
);
assert.deepEqual(
  alignBorderMotifs([4, 4, 4], 4),
  { edges: [0, 0, 0], freshAt: 2 },
  "a strip as wide as the run starts every strip fresh",
);
assert.deepEqual(
  alignBorderMotifs([5], 3),
  { edges: [0], freshAt: 0 },
  "a lone strip has no strip after it",
);
assert.deepEqual(
  alignBorderMotifs([2, 3, 4], 10),
  { edges: [0, 2, 5], freshAt: 0 },
  "a long run may never come back round",
);
assert.deepEqual(
  alignBorderMotifs([3, 4], 1),
  { edges: [0, 0], freshAt: 2 },
  "a run of one motif starts fresh everywhere",
);
assert.deepEqual(
  alignBorderMotifs([6, 9, 5], 4),
  { edges: [0, 2, 3], freshAt: 0 },
  "wide strips still report a motif inside the run",
);
assert.deepEqual(
  alignBorderMotifs([7, 3, 4, 7], 7),
  { edges: [0, 0, 3, 0], freshAt: 2 },
  "the earliest fresh start after the leading strip is the one reported",
);
assert.deepEqual(
  alignBorderMotifs([100, 100, 100], 7),
  { edges: [0, 2, 4], freshAt: 0 },
  "large widths reduce the same way",
);

assert.throws(() => alignBorderMotifs("3,4", 4), Error, "the widths must be a list");
assert.throws(() => alignBorderMotifs([], 4), Error, "an empty wall is rejected");
assert.throws(() => alignBorderMotifs([3, 0], 4), Error, "a strip of no motifs is rejected");
assert.throws(() => alignBorderMotifs([3, -2], 4), Error, "a negative width is rejected");
assert.throws(() => alignBorderMotifs([3, 2.5], 4), Error, "a fractional width is rejected");
assert.throws(() => alignBorderMotifs([3, "4"], 4), Error, "a written width is rejected");
assert.throws(() => alignBorderMotifs([3, 4], 0), Error, "a run of no motifs is rejected");
assert.throws(() => alignBorderMotifs([3, 4], 2.5), Error, "a fractional run is rejected");
console.log("ok");
