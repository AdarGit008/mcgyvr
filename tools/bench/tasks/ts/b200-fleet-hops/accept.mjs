import assert from "node:assert/strict";
import { fleetHops } from "./solution.ts";

assert.equal(fleetHops(4, [], [0], 3), 1, "a hop that reaches the newest release ends the climb");
assert.equal(fleetHops(6, [], [0], 2), 3, "a short hop crosses five releases in three moves");
assert.equal(fleetHops(5, [1], [0], 3), 2, "a long-term-support release cuts the first hop short");
assert.equal(fleetHops(5, [], [4], 3), 0, "a device on the newest release stays put");
assert.equal(fleetHops(6, [2, 4], [0, 3], 5), 5, "two devices past two support releases sum their hops");
assert.equal(fleetHops(3, [], [0, 1], 10), 2, "a hop reaching beyond the newest release lands on it");
assert.throws(() => fleetHops(4, [], [7], 2), Error, "a device above the published run is rejected");
console.log("ok");
