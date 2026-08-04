import assert from "node:assert/strict";
import { fibMod } from "./solution.ts";

assert.equal(fibMod(0), 0, "the sequence starts at zero");
assert.equal(fibMod(1), 1, "the second term");
assert.equal(fibMod(2), 1, "the third term");
assert.equal(fibMod(10), 55, "a small known value");
assert.equal(fibMod(50), 12586269025 % 1000000007, "past the point recursion gets slow");

// The contract's bound. A recursive solution exhausts the stack here.
assert.equal(typeof fibMod(200000), "number", "n = 200000 must return a number");
assert.ok(fibMod(200000) >= 0 && fibMod(200000) < 1000000007, "the result stays in range");

for (const bad of [-1, 1.5, "3"]) {
  assert.throws(() => fibMod(bad), Error, `n ${JSON.stringify(bad)} throws`);
}
