import assert from "node:assert/strict";
import { drainLanes } from "./solution.ts";

assert.deepEqual(
  drainLanes([["only", 2]], [["x", "only"], ["y", "only"], ["z", "only"]]),
  { order: ["x", "y", "z"], rounds: 2 },
  "one lane drains in arrival order",
);
assert.deepEqual(
  drainLanes(
    [["express", 1], ["bulk", 1]],
    [["e1", "express"], ["e2", "express"], ["b1", "bulk"]],
  ),
  { order: ["e1", "b1", "e2"], rounds: 2 },
  "lanes alternate in plan order",
);
assert.deepEqual(
  drainLanes(
    [["a", 2], ["b", 1]],
    [["a1", "a"], ["a2", "a"], ["a3", "a"], ["b1", "b"], ["b2", "b"]],
  ),
  { order: ["a1", "a2", "b1", "a3", "b2"], rounds: 2 },
  "a quota takes several labels per visit",
);
assert.deepEqual(
  drainLanes([["a", 1], ["b", 1]], [["a1", "a"], ["b1", "b"], ["b2", "b"], ["b3", "b"]]),
  { order: ["a1", "b1", "b2", "b3"], rounds: 3 },
  "an exhausted lane never strands the others",
);
assert.deepEqual(
  drainLanes([["a", 3]], [["a1", "a"], ["a2", "a"]]),
  { order: ["a1", "a2"], rounds: 1 },
  "a short take drains what is there",
);
assert.deepEqual(
  drainLanes([["a", 1], ["b", 2]], [["b1", "b"], ["b2", "b"]]),
  { order: ["b1", "b2"], rounds: 1 },
  "a lane that never held items is skipped over",
);
assert.deepEqual(drainLanes([["a", 1]], []), { order: [], rounds: 0 }, "nothing to drain");
assert.throws(() => drainLanes([], []), Error, "empty plan is rejected");
assert.throws(() => drainLanes([["a", 0]], []), Error, "zero quota is rejected");
assert.throws(() => drainLanes([["a", 1.5]], []), Error, "fractional quota is rejected");
assert.throws(() => drainLanes([["a", 1], ["a", 2]], []), Error, "duplicate lane is rejected");
assert.throws(() => drainLanes([["", 1]], []), Error, "empty lane name is rejected");
assert.throws(() => drainLanes([["a"]], []), Error, "lone plan entry is rejected");
assert.throws(() => drainLanes([["a", 1]], [["solo"]]), Error, "lone item is rejected");
assert.throws(() => drainLanes([["a", 1]], [[7, "a"]]), Error, "non-string label is rejected");
assert.throws(() => drainLanes([["a", 1]], [["x", "ghost"]]), Error, "undeclared lane is rejected");
console.log("ok");
