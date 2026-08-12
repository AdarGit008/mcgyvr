import assert from "node:assert/strict";
import { driveBridge } from "./solution.ts";

assert.equal(driveBridge([]), "lowered", "no commands leaves the span lowered");
assert.equal(driveBridge(["raise"]), "raised", "raise lifts a lowered span");
assert.equal(driveBridge(["raise", "lower"]), "lowered", "lower drops a raised span");
assert.equal(driveBridge(["raise", "lock"]), "locked", "lock pins a raised span");
assert.equal(driveBridge(["raise", "lock", "unlock"]), "raised", "unlock frees a locked span");
assert.equal(driveBridge(["raise", "lock", "unlock", "lower"]), "lowered", "a full cycle comes back down");
assert.throws(() => driveBridge(42), Error, "a non-list is rejected");
assert.throws(() => driveBridge(["open"]), Error, "an unknown command word is rejected");
assert.throws(() => driveBridge(["lower"]), Error, "lowering a lowered span is rejected");
assert.throws(() => driveBridge(["raise", "raise"]), Error, "raising a raised span is rejected");
assert.throws(() => driveBridge(["raise", "lock", "lower"]), Error, "lowering a locked span is rejected");
console.log("ok");
