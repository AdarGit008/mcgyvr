import assert from "node:assert/strict";
import { steerForklift } from "./solution.ts";

assert.deepEqual(steerForklift(3, 2, []), [0, 0], "no moves stays parked");
assert.deepEqual(steerForklift(3, 2, ["east", "east", "south"]), [2, 1], "east then south");
assert.deepEqual(
  steerForklift(2, 2, ["east", "west", "east", "west"]),
  [0, 0],
  "backtracking returns to the corner",
);
assert.deepEqual(
  steerForklift(3, 3, ["east", "east", "south", "south"]),
  [2, 2],
  "the far corner is reachable",
);
assert.deepEqual(
  steerForklift(1, 5, ["south", "south", "south", "south"]),
  [0, 4],
  "a single aisle allows only southward travel",
);
assert.throws(() => steerForklift(3, 2, ["west"]), Error, "west off the start corner");
assert.throws(() => steerForklift(3, 2, ["north"]), Error, "north off the start corner");
assert.throws(() => steerForklift(2, 2, ["east", "east"]), Error, "past the east edge");
assert.throws(() => steerForklift(3, 2, ["up"]), Error, "unknown move word");
assert.throws(() => steerForklift(0, 2, []), Error, "zero aisles is rejected");
assert.throws(() => steerForklift(3, 2.5, []), Error, "fractional bay count is rejected");
console.log("ok");
