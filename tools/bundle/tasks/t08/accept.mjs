import assert from "node:assert/strict";
import { topologicalSort } from "./solution.ts";

assert.deepEqual(
  topologicalSort(["a", "b", "c"], [["a", "b"], ["b", "c"]]),
  ["a", "b", "c"],
  "a straight chain",
);
assert.deepEqual(topologicalSort([], []), [], "no nodes");
assert.deepEqual(topologicalSort(["only"], []), ["only"], "one node, no edges");
assert.deepEqual(
  topologicalSort(["a", "b", "c"], []),
  ["a", "b", "c"],
  "no edges keeps input order",
);
assert.deepEqual(
  topologicalSort(["c", "a", "b"], [["a", "b"]]),
  ["c", "a", "b"],
  "ties resolve by input order, not alphabetically",
);
assert.deepEqual(
  topologicalSort(["a", "b", "c", "d"], [["a", "c"], ["b", "c"], ["c", "d"]]),
  ["a", "b", "c", "d"],
  "a node waits for every dependency",
);

const order = topologicalSort(["x", "y", "z"], [["z", "x"], ["z", "y"]]);
assert.equal(order[0], "z", "the only free node goes first");
assert.deepEqual(order.slice(1), ["x", "y"], "then input order among the freed nodes");

assert.throws(() => topologicalSort(["a", "b"], [["a", "b"], ["b", "a"]]), Error, "cycle throws");
assert.throws(() => topologicalSort(["a"], [["a", "ghost"]]), Error, "unknown node throws");
