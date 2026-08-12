import assert from "node:assert/strict";
import { meterCharge } from "./solution.ts";

assert.equal(meterCharge(0, [[100, 2500]]), 0, "no consumption bills nothing");
assert.equal(meterCharge(10, [[100, 2500]]), 25, "a partial tier bills its exact cents");
assert.equal(meterCharge(3, [[100, 2500]]), 8, "half a cent rounds up");
assert.equal(meterCharge(2, [[1, 1499], [1, 1499]]), 2, "every tier rounds on its own");
assert.equal(
  meterCharge(150, [[100, 1000], [200, 500]]),
  125,
  "consumption spills into the next tier",
);
assert.equal(
  meterCharge(3, [[2, 1000], [1, 2000]]),
  4,
  "consumption may fill the ladder exactly",
);
assert.throws(() => meterCharge(2.5, [[10, 100]]), Error, "fractional units are rejected");
assert.throws(
  () => meterCharge(4, [[2, 100], [1, 100]]),
  Error,
  "consumption past the ladder is rejected",
);
assert.throws(() => meterCharge(0, []), Error, "an empty ladder is rejected");
assert.throws(() => meterCharge(1, [[0, 100]]), Error, "a zero span is rejected");
assert.throws(() => meterCharge(1, [[5, -1]]), Error, "a negative rate is rejected");
assert.throws(() => meterCharge(1, [[5, 10.5]]), Error, "a fractional rate is rejected");
console.log("ok");
