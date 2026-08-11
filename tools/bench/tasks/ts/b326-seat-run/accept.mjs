import assert from "node:assert/strict";
import { seatRun } from "./solution.ts";

assert.equal(seatRun("..x...", 3), 3, "the run past the taken seat");
assert.equal(seatRun("..x...", 2), 0, "the earliest run wins");
assert.equal(seatRun("xxx", 1), -1, "the row is full");
assert.equal(seatRun("", 1), -1, "there is no row");
assert.equal(seatRun("...", 3), 0, "the whole row fits");
assert.equal(seatRun("x.x.x", 1), 1, "a single seat between two taken");
console.log("ok");
