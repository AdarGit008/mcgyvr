import assert from "node:assert/strict";
import { tilesAcross, tilesNeeded } from "./solution.ts";

assert.equal(tilesAcross(100, 10), 10, "an exact fit");
assert.equal(tilesAcross(101, 10), 11, "a part tile counts as one");
assert.equal(tilesAcross(0, 10), 0, "no length, no tiles");
assert.equal(tilesNeeded(100, 100, 10, 0), 100, "no allowance");
assert.equal(tilesNeeded(100, 100, 10, 5), 105, "an exact allowance");
assert.equal(tilesNeeded(30, 20, 10, 10), 7, "the allowance rounds up");
assert.equal(tilesNeeded(0, 50, 10, 10), 0, "no wall, no tiles");
console.log("ok");
