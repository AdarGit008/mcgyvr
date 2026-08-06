import assert from "node:assert/strict";
import { schedule } from "./solution.ts";

assert.deepEqual(schedule([], 3), [], "no work");
assert.deepEqual(
  schedule(["A", "A", "A", "B", "B", "C"], 2),
  ["A", "B", "C", "A", "B", "idle", "A"],
  "mixed counts with one forced idle",
);
assert.deepEqual(
  schedule(["A", "A", "A", "B", "B", "B"], 2),
  ["A", "B", "idle", "A", "B", "idle", "A", "B"],
  "two labels, idles in the middle but not at the end",
);
assert.deepEqual(
  schedule(["A", "A", "A"], 2),
  ["A", "idle", "idle", "A", "idle", "idle", "A"],
  "single label pays the full cooldown twice",
);
assert.deepEqual(
  schedule(["B", "A", "B"], 0),
  ["B", "A", "B"],
  "count outranks alphabet, then the tie goes to 'A'",
);
assert.deepEqual(
  schedule(["B", "A"], 5),
  ["A", "B"],
  "different labels never idle regardless of cooldown",
);
assert.deepEqual(
  schedule(["A", "B", "A"], 1),
  ["A", "B", "A"],
  "cooldown exactly satisfied needs no idle",
);
assert.deepEqual(
  schedule(["A", "A"], 1),
  ["A", "idle", "A"],
  "cooldown 1 forces exactly one idle tick",
);
assert.deepEqual(
  schedule(["C", "C", "B", "A"], 1),
  ["C", "A", "B", "C"],
  "highest remaining count first, lexicographic only on ties",
);
assert.deepEqual(
  schedule(["A", "A", "B"], 0),
  ["A", "A", "B"],
  "cooldown 0 allows consecutive runs and count still leads",
);
