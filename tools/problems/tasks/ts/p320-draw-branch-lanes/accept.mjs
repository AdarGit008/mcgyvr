import assert from "node:assert/strict";
import { drawBranchLanes } from "./solution.ts";

const of = (pairs) => pairs.map(([id, branch]) => ({ id, branch }));

assert.deepEqual(
  drawBranchLanes(of([["only", "trunk"]])),
  ["* only"],
  "one entry on one lane",
);
assert.deepEqual(
  drawBranchLanes(of([["a", "trunk"], ["b", "trunk"], ["c", "trunk"]])),
  ["* a", "* b", "* c"],
  "a history with no branching at all",
);
assert.deepEqual(
  drawBranchLanes(
    of([
      ["a", "trunk"],
      ["b", "trunk"],
      ["c", "spur"],
      ["d", "trunk"],
      ["e", "spur"],
    ]),
  ),
  ["* a", "* b", "| * c", "* | d", "  * e"],
  "a spur beside the trunk, and the trunk's lane left empty once it ends",
);
assert.deepEqual(
  drawBranchLanes(
    of([
      ["r1", "trunk"],
      ["r2", "side"],
      ["r3", "trunk"],
      ["r4", "side"],
      ["r5", "hot"],
      ["r6", "hot"],
    ]),
  ),
  ["* r1", "| * r2", "* | r3", "  * r4", "* r5", "* r6"],
  "a lane let go of is handed to the next branch to arrive",
);
assert.deepEqual(
  drawBranchLanes(
    of([
      ["p", "one"],
      ["q", "two"],
      ["s", "three"],
      ["t", "one"],
      ["u", "two"],
      ["v", "three"],
    ]),
  ),
  ["* p", "| * q", "| | * s", "* | | t", "  * | u", "    * v"],
  "three lanes held at once and released from the left",
);
assert.deepEqual(
  drawBranchLanes(of([["x", "alpha"], ["y", "beta"]])),
  ["* x", "* y"],
  "a branch of one entry is gone before the next branch arrives",
);
assert.throws(() => drawBranchLanes([]), Error, "an empty list is rejected");
assert.throws(() => drawBranchLanes("nope"), Error, "a bare string is rejected");
assert.throws(() => drawBranchLanes([7]), Error, "an entry that is not a mapping");
assert.throws(
  () => drawBranchLanes([{ id: "a" }]),
  Error,
  "an entry with no branch is rejected",
);
assert.throws(
  () => drawBranchLanes([{ id: "", branch: "trunk" }]),
  Error,
  "an empty id is rejected",
);
assert.throws(
  () => drawBranchLanes([{ id: "a", branch: 5 }]),
  Error,
  "a branch that is not a string is rejected",
);
assert.throws(
  () => drawBranchLanes(of([["a", "trunk"], ["a", "spur"]])),
  Error,
  "a repeated id is rejected",
);
console.log("ok");
