import assert from "node:assert/strict";
import { canHop } from "./solution.ts";

const pond = [
  "F.G..",
  ".H...",
  "..F..",
  ".....",
  "...KK",
];

assert.equal(canHop(pond, [2, 2], [2, 3]), true, "a step sideways onto open water");
assert.equal(canHop(pond, [2, 2], [1, 2]), true, "a step upward");
assert.equal(canHop(pond, [0, 2], [2, 0]), true, "a diagonal vault over an occupied midpoint");
assert.equal(canHop(pond, [4, 4], [4, 2]), true, "a horizontal vault over a neighbour");
assert.equal(canHop(pond, [4, 3], [4, 4]), false, "the to square must be open water");
assert.equal(canHop(pond, [3, 3], [3, 4]), false, "the from square must be occupied");
assert.equal(canHop(pond, [2, 2], [2, 4]), false, "a vault needs its midpoint occupied");
assert.equal(canHop(pond, [2, 2], [0, 2]), false, "a vertical vault over open water fails");
assert.equal(canHop(pond, [2, 2], [3, 3]), false, "a one-square diagonal is not a step");
assert.equal(canHop(pond, [0, 0], [0, 3]), false, "three squares is out of reach");
assert.equal(canHop(pond, [0, 0], [1, 2]), false, "a knight-shaped move is neither shape");
assert.throws(() => canHop(pond.slice(1), [0, 0], [0, 1]), Error, "four rows are rejected");
assert.throws(
  () => canHop(["F.G..", ".H...", "..F..", ".....", "...K"], [0, 0], [0, 1]),
  Error,
  "a short row is rejected",
);
assert.throws(() => canHop(pond, [0, 5], [0, 1]), Error, "a coordinate above 4 is rejected");
assert.throws(() => canHop(pond, [0, 0], [0, 1.5]), Error, "a fractional coordinate is rejected");
assert.throws(() => canHop(pond, [0], [0, 1]), Error, "a one-number square is rejected");
console.log("ok");
