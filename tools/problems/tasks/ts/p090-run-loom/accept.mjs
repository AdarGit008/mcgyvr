import assert from "node:assert/strict";
import { runLoom } from "./solution.ts";

assert.deepEqual(
  runLoom([["put", 2], ["put", 3], ["fuse"], ["weave"]]),
  { status: "done", output: [5] },
  "fuse adds the top two",
);
assert.deepEqual(
  runLoom([["put", 4], ["twin"], ["scale"], ["weave"]]),
  { status: "done", output: [16] },
  "twin then scale squares the top",
);
assert.deepEqual(
  runLoom([["put", 1], ["put", 2], ["flip"], ["weave"], ["weave"]]),
  { status: "done", output: [1, 2] },
  "flip swaps the top two before weaving",
);
assert.deepEqual(
  runLoom([["put", 1], ["put", 2], ["weave"], ["weave"]]),
  { status: "done", output: [2, 1] },
  "weaving pops top first",
);
assert.deepEqual(
  runLoom([["put", 7], ["weave"], ["fuse"]]),
  { status: "starved", output: [7], step: 2 },
  "fuse on one value starves, keeping earlier output",
);
assert.deepEqual(
  runLoom([["twin"]]),
  { status: "starved", output: [], step: 0 },
  "twin on an empty stack starves at step 0",
);
assert.deepEqual(
  runLoom([["put", 1], ["snip"]]),
  { status: "lost", output: [], step: 1 },
  "an unknown instruction is lost, not starved",
);
assert.deepEqual(runLoom([]), { status: "done", output: [] }, "the empty program is done");
assert.deepEqual(
  runLoom([["put", 5], ["flip"]]),
  { status: "starved", output: [], step: 1 },
  "flip needs two values",
);
console.log("ok");
