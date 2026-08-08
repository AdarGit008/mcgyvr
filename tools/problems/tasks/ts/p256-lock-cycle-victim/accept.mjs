import assert from "node:assert/strict";
import { lockCycleVictim } from "./solution.ts";

assert.deepEqual(
  lockCycleVictim([], []),
  { victim: "", cycle: [] },
  "an idle manager has no ring",
);
assert.deepEqual(
  lockCycleVictim([["r1", "t1"], ["r2", "t2"]], [["t1", "r2"]]),
  { victim: "", cycle: [] },
  "one worker waiting on a worker that waits on nothing",
);
assert.deepEqual(
  lockCycleVictim([["r1", "t1"]], [["t1", "spare"], ["t2", "r1"]]),
  { victim: "", cycle: [] },
  "a request for an unheld resource draws no arrow",
);
assert.deepEqual(
  lockCycleVictim([["r1", "t1"], ["r2", "t2"]], [["t1", "r2"], ["t2", "r1"]]),
  { victim: "t1", cycle: ["t1", "t2"] },
  "equal holdings break to the first name",
);
assert.deepEqual(
  lockCycleVictim(
    [["r1", "ann"], ["r2", "ann"], ["r3", "bob"]],
    [["ann", "r3"], ["bob", "r1"]],
  ),
  { victim: "bob", cycle: ["bob", "ann"] },
  "the lighter holder is thrown out and the ring starts at it",
);
assert.deepEqual(
  lockCycleVictim(
    [["a1", "x"], ["a2", "y"], ["a3", "z"], ["a4", "w"]],
    [["x", "a2"], ["y", "a3"], ["z", "a1"], ["w", "a1"]],
  ),
  { victim: "x", cycle: ["x", "y", "z"] },
  "a worker queued behind the ring stays out of it",
);
assert.deepEqual(
  lockCycleVictim(
    [["p1", "p"], ["p2", "q"], ["m1", "m"], ["m2", "n"], ["m3", "n"]],
    [["p", "p2"], ["q", "p1"], ["m", "m2"], ["n", "m1"]],
  ),
  { victim: "m", cycle: ["m", "n"] },
  "the victim is chosen across every ring at once",
);
assert.deepEqual(
  lockCycleVictim([["k1", "solo"]], [["drifter", "k1"]]),
  { victim: "", cycle: [] },
  "a queue behind an unblocked holder is not a ring",
);

assert.throws(
  () => lockCycleVictim([["r1", "t1"], ["r1", "t2"]], []),
  Error,
  "a doubly granted resource is rejected",
);
assert.throws(
  () => lockCycleVictim([["r1", "t1"], ["r2", "t2"]], [["t3", "r1"], ["t3", "r2"]]),
  Error,
  "a worker blocked twice is rejected",
);
assert.throws(
  () => lockCycleVictim([["r1", "t1"]], [["t1", "r1"]]),
  Error,
  "blocking on your own lock is rejected",
);
assert.throws(() => lockCycleVictim([["r1"]], []), Error, "a one-entry pair is rejected");
assert.throws(() => lockCycleVictim([[1, "t1"]], []), Error, "a non-string name is rejected");
assert.throws(() => lockCycleVictim([["", "t1"]], []), Error, "an empty name is rejected");
assert.throws(() => lockCycleVictim("r1", []), Error, "a string argument is rejected");
console.log("ok");
