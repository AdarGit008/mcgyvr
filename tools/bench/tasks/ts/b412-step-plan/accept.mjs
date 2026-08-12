import assert from "node:assert/strict";
import { stepAllowed, stepPlan } from "./solution.ts";

const MOVES = [["a", "b"], ["b", "c"]];

assert.equal(stepAllowed("a", "b", MOVES), true, "a listed move");
assert.equal(stepAllowed("a", "c", MOVES), false, "an unlisted move");
assert.equal(stepPlan(["a", "b", "c"], MOVES), -1, "every move is allowed");
assert.equal(stepPlan(["a", "c"], MOVES), 1, "the first move is not allowed");
assert.equal(stepPlan(["a"], MOVES), -1, "one state makes no move");
assert.throws(() => stepPlan([], MOVES), Error, "an empty run is rejected");
console.log("ok");
