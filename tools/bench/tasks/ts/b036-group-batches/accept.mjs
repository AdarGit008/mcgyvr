import assert from "node:assert/strict";
import { groupBatches } from "./solution.ts";

assert.deepEqual(groupBatches([], 3), [], "no jobs yields no batches");
assert.deepEqual(
  groupBatches([["solo", "g1", 2, 1]], 3),
  [["solo"]],
  "a single job is its own batch",
);
assert.deepEqual(
  groupBatches(
    [["a", "g", 1, 1], ["b", "g", 9, 1], ["c", "g", 5, 1]],
    10,
  ),
  [["a"], ["b"], ["c"]],
  "one group runs in arrival order whatever the priorities",
);
assert.deepEqual(
  groupBatches(
    [["x", "g1", 1, 1], ["y", "g2", 5, 1], ["z", "g3", 3, 1]],
    3,
  ),
  [["y", "z", "x"]],
  "distinct groups that all fit make one batch in priority order",
);
assert.deepEqual(
  groupBatches([["a", "g1", 2, 1], ["b", "g2", 2, 1]], 2),
  [["a", "b"]],
  "a priority tie goes to the earlier arrival",
);
assert.deepEqual(
  groupBatches([["a", "g1", 5, 2], ["b", "g2", 4, 1]], 2),
  [["a"], ["b"]],
  "a head that does not fit waits for the next round",
);
assert.deepEqual(
  groupBatches(
    [["a", "g1", 5, 2], ["b", "g2", 4, 2], ["c", "g3", 3, 1]],
    3,
  ),
  [["a", "c"], ["b"]],
  "a passed-over head lets a lighter, less urgent head in",
);
assert.deepEqual(
  groupBatches(
    [["a", "g1", 1, 1], ["b", "g1", 9, 1], ["c", "g2", 5, 1]],
    10,
  ),
  [["c", "a"], ["b"]],
  "an urgent job stays stuck behind its group's slower head",
);
assert.deepEqual(
  groupBatches(
    [["a", "g1", 5, 2], ["b", "g2", 4, 2], ["c", "g3", 3, 2]],
    4,
  ),
  [["a", "b"], ["c"]],
  "a batch may be filled to exactly its capacity",
);
assert.deepEqual(
  groupBatches([["a", "g1", -1, 1], ["b", "g2", -5, 1]], 2),
  [["a", "b"]],
  "negative priorities still rank correctly",
);
assert.deepEqual(
  groupBatches([["a", "g1", 3, 3]], 3),
  [["a"]],
  "a job weighing the whole capacity is scheduled alone",
);
assert.deepEqual(
  groupBatches(
    [
      ["ingest", "etl", 3, 2],
      ["clean", "etl", 8, 1],
      ["train", "ml", 6, 3],
      ["eval", "ml", 2, 1],
      ["ship", "ops", 6, 2],
    ],
    4,
  ),
  [["train"], ["ship", "ingest"], ["clean", "eval"]],
  "three groups, weights and ties interleave over three rounds",
);
assert.throws(() => groupBatches("x", 3), Error, "non-list jobs is rejected");
assert.throws(
  () => groupBatches([["a", "g", 1]], 3),
  Error,
  "a three-item job is rejected",
);
assert.throws(
  () => groupBatches([["", "g", 1, 1]], 3),
  Error,
  "an empty name is rejected",
);
assert.throws(
  () => groupBatches([[5, "g", 1, 1]], 3),
  Error,
  "a non-string name is rejected",
);
assert.throws(
  () => groupBatches([["a", "", 1, 1]], 3),
  Error,
  "an empty group is rejected",
);
assert.throws(
  () => groupBatches([["a", "g", 2.5, 1]], 3),
  Error,
  "a fractional priority is rejected",
);
assert.throws(
  () => groupBatches([["a", "g", 1, 0]], 3),
  Error,
  "a zero weight is rejected",
);
assert.throws(
  () => groupBatches([["a", "g", 1, 5]], 3),
  Error,
  "a weight above the capacity is rejected",
);
assert.throws(
  () => groupBatches([["a", "g", 1, 1], ["a", "h", 2, 1]], 3),
  Error,
  "a duplicate name is rejected",
);
assert.throws(
  () => groupBatches([["a", "g", 1, 1]], 0),
  Error,
  "a zero capacity is rejected",
);
assert.throws(
  () => groupBatches([["a", "g", 1, 1]], 2.5),
  Error,
  "a fractional capacity is rejected",
);
console.log("ok");
