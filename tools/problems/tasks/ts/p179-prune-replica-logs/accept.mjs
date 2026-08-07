import assert from "node:assert/strict";
import { pruneReplicaLogs } from "./solution.ts";

const one = (name, acked, weight) => ({ name, acked, weight });

assert.deepEqual(
  pruneReplicaLogs([one("a", 3, 1), one("b", 1, 1), one("c", 0, 1)], 3),
  { committed: 1, discardable: 0, laggards: ["c"] },
  "two votes of three settle position one and no further",
);
assert.deepEqual(
  pruneReplicaLogs([one("a", 2, 1), one("b", 0, 1)], 2),
  { committed: 0, discardable: 0, laggards: [] },
  "exactly half the weight settles nothing at all",
);
assert.deepEqual(
  pruneReplicaLogs([one("big", 5, 3), one("small", 2, 1), one("tiny", 1, 1)], 5),
  { committed: 5, discardable: 1, laggards: ["small", "tiny"] },
  "one heavy replica outvotes two light ones",
);
assert.deepEqual(
  pruneReplicaLogs([one("a", 3, 2), one("b", 1, 2)], 3),
  { committed: 1, discardable: 1, laggards: [] },
  "an evenly weighted pair settles only where both agree",
);
assert.deepEqual(
  pruneReplicaLogs([one("solo", 7, 2)], 7),
  { committed: 7, discardable: 7, laggards: [] },
  "a lone replica carries every position it has accepted",
);
assert.deepEqual(
  pruneReplicaLogs([one("a", 0, 1), one("b", 0, 1)], 0),
  { committed: 0, discardable: 0, laggards: [] },
  "a coordinator holding nothing settles nothing",
);
assert.deepEqual(
  pruneReplicaLogs(
    [one("r1", 9, 1), one("r2", 8, 1), one("r3", 7, 1), one("r4", 2, 1), one("r5", 0, 1)],
    9,
  ),
  { committed: 7, discardable: 0, laggards: ["r4", "r5"] },
  "three of five equal votes settle the seventh position",
);
assert.deepEqual(
  pruneReplicaLogs([one("h", 1, 5), one("a", 9, 1), one("b", 9, 1)], 9),
  { committed: 1, discardable: 1, laggards: [] },
  "a heavy replica far behind pins the settled point to its own position",
);
assert.deepEqual(
  pruneReplicaLogs([one("a", 4, 1), one("b", 4, 1), one("c", 4, 1)], 4),
  { committed: 4, discardable: 4, laggards: [] },
  "replicas in perfect agreement leave nothing to keep",
);

assert.throws(() => pruneReplicaLogs([], 3), Error, "an empty replica list is rejected");
assert.throws(() => pruneReplicaLogs("abc", 3), Error, "a non-list of replicas is rejected");
assert.throws(() => pruneReplicaLogs([{ name: "a", acked: 1 }], 3), Error, "a missing weight is rejected");
assert.throws(() => pruneReplicaLogs([one("", 1, 1)], 3), Error, "an empty name is rejected");
assert.throws(() => pruneReplicaLogs([one("a", 1, 1), one("a", 2, 1)], 3), Error, "a repeated name is rejected");
assert.throws(() => pruneReplicaLogs([one("a", 1, 0)], 3), Error, "a weightless replica is rejected");
assert.throws(() => pruneReplicaLogs([one("a", 4, 1)], 3), Error, "an acked position past the hold is rejected");
assert.throws(() => pruneReplicaLogs([one("a", -1, 1)], 3), Error, "a negative acked position is rejected");
assert.throws(() => pruneReplicaLogs([one("a", 1, 1)], -2), Error, "a negative hold is rejected");
console.log("ok");
