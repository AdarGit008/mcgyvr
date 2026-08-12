import assert from "node:assert/strict";
import { runElevator } from "./solution.ts";

assert.deepEqual(runElevator(6, [[0, 4], [0, 2]]), { stops: [2, 4], travel: 3 }, "the nearer floor going up is served first");
assert.deepEqual(runElevator(6, [[0, 5], [0, 3], [6, 1]]), { stops: [3, 5, 1], travel: 8 }, "the lift waits idle and then turns for a late call");
assert.deepEqual(runElevator(6, [[0, 3], [0, 3]]), { stops: [3, 3], travel: 2 }, "two calls for one floor are two stops");
assert.deepEqual(runElevator(8, [[0, 6], [2, 4]]), { stops: [4, 6], travel: 5 }, "a call pressed ahead of the lift is picked up in passing");
assert.deepEqual(runElevator(4, [[0, 1]]), { stops: [1], travel: 0 }, "a call for the starting floor costs no travel");
assert.throws(() => runElevator(4, [[0, 5]]), Error, "a call above the top floor is rejected");
console.log("ok");
