import assert from "node:assert/strict";
import { plotterPose } from "./solution.ts";

assert.deepEqual(
  plotterPose("F3"),
  { x: 0, y: 3, facing: "N" },
  "forward from the start heads up the +y axis",
);
assert.deepEqual(
  plotterPose("RF2"),
  { x: 2, y: 0, facing: "E" },
  "a right spin points east and forward follows it",
);
assert.deepEqual(
  plotterPose("F1RF1RF1RF1"),
  { x: 0, y: 0, facing: "W" },
  "a square lap returns home facing west",
);
assert.deepEqual(
  plotterPose("B2"),
  { x: 0, y: -2, facing: "N" },
  "backward moves against the facing without changing it",
);
assert.deepEqual(
  plotterPose("LLF3"),
  { x: 0, y: -3, facing: "S" },
  "two left spins face south",
);
assert.deepEqual(
  plotterPose(""),
  { x: 0, y: 0, facing: "N" },
  "the empty program is the resting pose",
);
assert.deepEqual(
  plotterPose("F12L"),
  { x: 0, y: 12, facing: "W" },
  "distances may span several digits",
);
assert.deepEqual(
  plotterPose("LB4"),
  { x: 4, y: 0, facing: "W" },
  "backward while facing west drifts east",
);
assert.throws(() => plotterPose("F0"), Error, "a zero distance is rejected");
assert.throws(() => plotterPose("F"), Error, "a drive without digits is rejected");
assert.throws(() => plotterPose("X3"), Error, "an unknown letter is rejected");
assert.throws(() => plotterPose("f2"), Error, "lowercase commands are rejected");
assert.throws(() => plotterPose(42), Error, "a non-string program is rejected");
console.log("ok");
