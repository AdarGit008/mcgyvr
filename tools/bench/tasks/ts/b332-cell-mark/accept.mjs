import assert from "node:assert/strict";
import { liveCount, liveNext } from "./solution.ts";

assert.equal(liveCount([true, false, true]), 2, "two of three are alive");
assert.equal(liveCount([]), 0, "no neighbours at all");
assert.equal(liveNext(true, [true, true]), true, "two neighbours keep it alive");
assert.equal(liveNext(true, [true]), false, "one is too lonely");
assert.equal(liveNext(false, [true, true, true]), true, "three bring it to life");
assert.equal(liveNext(false, [true, true]), false, "two are not enough to start");
assert.equal(liveNext(true, [true, true, true, true]), false, "four is crowded");
console.log("ok");
