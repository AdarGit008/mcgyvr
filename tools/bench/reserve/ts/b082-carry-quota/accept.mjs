import assert from "node:assert/strict";
import { billOverage } from "./solution.ts";

assert.deepEqual(billOverage(10, 5, []), { billed: [], carried: 0 }, "no periods");
assert.deepEqual(
  billOverage(10, 5, [4]),
  { billed: [0], carried: 5 },
  "unspent units carry up to the cap",
);
assert.deepEqual(
  billOverage(10, 5, [12]),
  { billed: [2], carried: 0 },
  "consumption past the allowance is billed",
);
assert.deepEqual(
  billOverage(10, 5, [10]),
  { billed: [0], carried: 0 },
  "an exactly spent period bills and carries nothing",
);
assert.deepEqual(
  billOverage(10, 5, [4, 9]),
  { billed: [0, 0], carried: 5 },
  "carried units cover a later period",
);
assert.deepEqual(
  billOverage(10, 3, [0, 0]),
  { billed: [0, 0], carried: 3 },
  "the cap holds the carry down",
);
assert.deepEqual(
  billOverage(10, 5, [15, 2]),
  { billed: [5, 0], carried: 5 },
  "an overdrawn period carries nothing forward",
);
assert.deepEqual(
  billOverage(10, 0, [4, 11]),
  { billed: [0, 1], carried: 0 },
  "a zero cap never carries",
);
assert.throws(() => billOverage(-1, 5, [1]), Error, "negative allowance is rejected");
assert.throws(() => billOverage(10, 2.5, [1]), Error, "fractional carry cap is rejected");
assert.throws(() => billOverage(10, 5, "heavy"), Error, "non-list usage is rejected");
assert.throws(() => billOverage(10, 5, [3, -1]), Error, "negative usage entry is rejected");
console.log("ok");
