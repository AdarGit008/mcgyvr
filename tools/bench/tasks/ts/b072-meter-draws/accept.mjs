import assert from "node:assert/strict";
import { meterDraws, remainingFor } from "./solution.ts";

assert.deepEqual(meterDraws([], 10), { used: {}, denied: [] }, "no draws");
assert.deepEqual(
  meterDraws([["a", 6], ["a", 5]], 10),
  { used: { a: 6 }, denied: [1] },
  "a draw past the allowance is refused",
);
assert.deepEqual(
  meterDraws([["a", 6], ["b", 8], ["a", 4]], 10),
  { used: { a: 10, b: 8 }, denied: [] },
  "keys meter separately and an exact fill is allowed",
);
assert.deepEqual(
  meterDraws([["a", 11], ["a", 2]], 10),
  { used: { a: 2 }, denied: [0] },
  "a refused draw leaves later draws unharmed",
);
assert.deepEqual(
  meterDraws([["z", 11]], 10),
  { used: { z: 0 }, denied: [0] },
  "a fully refused key still enters the ledger at zero",
);
assert.equal(remainingFor({}, "a", 10), 10, "unseen key has the full allowance");
assert.equal(remainingFor({ a: 3 }, "a", 10), 7, "helper subtracts recorded spend");
assert.throws(() => meterDraws([], 0), Error, "zero allowance is rejected");
assert.throws(() => meterDraws([["", 1]], 10), Error, "empty key is rejected");
assert.throws(() => meterDraws([["a", 0]], 10), Error, "zero units is rejected");
assert.throws(() => meterDraws([["a", 1.5]], 10), Error, "fractional units");
console.log("ok");
