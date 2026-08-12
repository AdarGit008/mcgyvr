import assert from "node:assert/strict";
import { chargePercent, bandLabel } from "./solution.ts";

assert.equal(chargePercent(3400, 3000, 3800), 50, "midpoint reads fifty");
assert.equal(chargePercent(3404, 3000, 3800), 51, "half a percent rounds up");
assert.equal(chargePercent(3000, 3000, 3800), 0, "the empty bound reads zero");
assert.equal(chargePercent(3800, 3000, 3800), 100, "the full bound reads one hundred");
assert.equal(chargePercent(2500, 3000, 3800), 0, "below empty clamps to zero");
assert.equal(chargePercent(4100, 3000, 3800), 100, "above full clamps to one hundred");
assert.equal(bandLabel(14), "low", "fourteen percent is low");
assert.equal(bandLabel(85), "full", "eighty-five percent is full");
assert.throws(() => chargePercent(3400.5, 3000, 3800), Error, "fractional reading is rejected");
assert.throws(() => chargePercent(3400, 3800, 3800), Error, "empty bound at full bound is rejected");
console.log("ok");
