import assert from "node:assert/strict";
import { runOf, groupRuns } from "./solution.ts";

assert.equal(runOf(["a", "a", "b"], 0), 2, "two in a row");
assert.equal(runOf(["a"], 0), 1, "a run of one");
assert.deepEqual(
  groupRuns(["a", "a", "b"]),
  [["a", "a"], ["b"]],
  "the final run is kept",
);
assert.deepEqual(groupRuns([]), [], "nothing breaks into nothing");
assert.deepEqual(groupRuns(["a"]), [["a"]], "one entry is one run");
assert.deepEqual(groupRuns(["a", "b", "b"]), [["a"], ["b", "b"]], "two runs");
console.log("ok");
