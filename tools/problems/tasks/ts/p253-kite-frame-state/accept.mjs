import assert from "node:assert/strict";
import { kiteFrameState } from "./solution.ts";

const traded = (times) => Array.from({ length: times * 2 }, (_, i) => (i % 2 === 0 ? "left" : "right"));

assert.deepEqual(
  kiteFrameState([]),
  { left: 0, right: 0, winner: "" },
  "an unplayed frame is level and live",
);
assert.deepEqual(
  kiteFrameState(["right", "right", "left"]),
  { left: 1, right: 2, winner: "" },
  "every rally is a point for its winner",
);
assert.deepEqual(
  kiteFrameState(Array.from({ length: 15 }, () => "left")),
  { left: 15, right: 0, winner: "left" },
  "15-0 claims the frame",
);
assert.deepEqual(
  kiteFrameState([...traded(14), "left"]),
  { left: 15, right: 14, winner: "" },
  "15-14 is one clear, not two, so the frame is live",
);
assert.deepEqual(
  kiteFrameState([...traded(14), "left", "left"]),
  { left: 16, right: 14, winner: "left" },
  "two clear at or past 15 claims the frame",
);
assert.deepEqual(
  kiteFrameState(traded(19)),
  { left: 19, right: 19, winner: "" },
  "traded rallies never let either side pull two clear",
);
assert.deepEqual(
  kiteFrameState([...traded(19), "right"]),
  { left: 19, right: 20, winner: "right" },
  "20 claims the frame on a single-point gap",
);
assert.deepEqual(
  kiteFrameState([...traded(19), "right", "left", "left", "right"]),
  { left: 19, right: 20, winner: "right" },
  "rallies after the claim leave both totals alone",
);
assert.deepEqual(
  kiteFrameState([...Array.from({ length: 15 }, () => "left"), "right", "right"]),
  { left: 15, right: 0, winner: "left" },
  "a closed frame absorbs nothing further",
);
assert.throws(() => kiteFrameState(["left", "up"]), Error, "an unknown side is rejected");
assert.throws(
  () => kiteFrameState([...Array.from({ length: 15 }, () => "left"), "middle"]),
  Error,
  "an unknown side after the claim is still rejected",
);
assert.throws(() => kiteFrameState("left"), Error, "a string argument is rejected");
console.log("ok");
