import assert from "node:assert/strict";
import { fuelLegs } from "./solution.ts";

assert.equal(fuelLegs(10, 3), 3, "the remainder buys no leg");
assert.equal(fuelLegs(9, 3), 3, "an exact tank");
assert.equal(fuelLegs(2, 3), 0, "not enough for one");
assert.equal(fuelLegs(0, 5), 0, "an empty tank");
assert.throws(() => fuelLegs(10, 0), Error, "a burn of zero is rejected");
assert.throws(() => fuelLegs(10, -2), Error, "a negative burn is rejected");
console.log("ok");
