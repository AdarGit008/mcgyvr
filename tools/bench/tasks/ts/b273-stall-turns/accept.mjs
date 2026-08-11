import assert from "node:assert/strict";
import { stallTurns } from "./solution.ts";

assert.equal(stallTurns([2, 2], 2), 2, "one turn each");
assert.equal(stallTurns([3], 2), 2, "a spillover takes another turn");
assert.equal(stallTurns([1, 1, 1], 5), 3, "a turn is never shared");
assert.equal(stallTurns([0, 4], 4), 1, "wanting nothing takes no turn");
assert.equal(stallTurns([], 3), 0, "no customers, no turns");
assert.equal(stallTurns([7], 3), 3, "three turns for seven items");
console.log("ok");
