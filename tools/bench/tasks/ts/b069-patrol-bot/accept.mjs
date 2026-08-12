import assert from "node:assert/strict";
import { runPatrol, clampMove } from "./solution.ts";

assert.deepEqual(runPatrol(5, 2, []), { position: 2, bumps: 0, visited: 1 }, "no moves stays put");
assert.deepEqual(runPatrol(4, 1, [9]), { position: 3, bumps: 1, visited: 2 }, "a long move stops at the far wall");
assert.deepEqual(runPatrol(3, 1, [-5, 6]), { position: 2, bumps: 2, visited: 3 }, "both walls cut moves short");
assert.deepEqual(runPatrol(5, 2, [1, -1]), { position: 2, bumps: 0, visited: 2 }, "returning to a cell adds nothing");
assert.deepEqual(clampMove(2, 10, 5), [4, true], "helper clamps at the far wall");
assert.throws(() => runPatrol(0, 0, [1]), Error, "zero width is rejected");
assert.throws(() => runPatrol(4, 4, [1]), Error, "start outside the corridor is rejected");
assert.throws(() => runPatrol(4, 2, [0]), Error, "zero move is rejected");
assert.throws(() => runPatrol(4, 2, "east"), Error, "non-list moves argument is rejected");
console.log("ok");
