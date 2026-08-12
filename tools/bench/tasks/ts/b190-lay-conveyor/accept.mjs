import assert from "node:assert/strict";
import { layConveyor } from "./solution.ts";

const floor = ["....", ".#..", "...."];

assert.deepEqual(layConveyor(floor, 0, 0, 4), ["====", ".#..", "...."], "a run spans a whole open row");
assert.deepEqual(layConveyor(floor, 1, 2, 2), ["....", ".#==", "...."], "a run laid east of a machine leaves the machine standing");
assert.deepEqual(layConveyor(floor, 2, 1, 1), ["....", ".#..", ".=.."], "a run of one cell marks one cell");
assert.deepEqual(floor, ["....", ".#..", "...."], "the plan handed in is left as it was");
assert.throws(() => layConveyor(floor, 0, 2, 3), Error, "a run passing the last column is rejected");
assert.throws(() => layConveyor(floor, 1, 0, 3), Error, "a run covering a machine is rejected");
console.log("ok");
