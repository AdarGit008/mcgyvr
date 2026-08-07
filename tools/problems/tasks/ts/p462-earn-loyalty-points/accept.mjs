import assert from "node:assert/strict";
import { earnLoyaltyPoints } from "./solution.ts";

const ladder = [
  { from: 0, per: 1 },
  { from: 50000, per: 2 },
  { from: 200000, per: 3 },
];

assert.deepEqual(
  earnLoyaltyPoints([10000, 45000, 100000, 60000], ladder),
  [10, 45, 200, 120],
  "each receipt earns at the rung its opening outlay falls in",
);
assert.deepEqual(
  earnLoyaltyPoints([50000], ladder),
  [50],
  "the outlay grows only after the receipt has earned",
);
assert.deepEqual(
  earnLoyaltyPoints([49999, 1, 1000], ladder),
  [49, 0, 2],
  "the rung lifts once the running outlay reaches it",
);
assert.deepEqual(
  earnLoyaltyPoints([1999, 999], [{ from: 0, per: 3 }]),
  [5, 2],
  "a part of a thousand cents is thrown away",
);
assert.deepEqual(
  earnLoyaltyPoints([1000, 0, 7000], [{ from: 0, per: 0 }]),
  [0, 0, 0],
  "a rung paying nothing awards nothing",
);
assert.deepEqual(earnLoyaltyPoints([], ladder), [], "no receipts, no awards");
assert.deepEqual(
  earnLoyaltyPoints([200000, 10], ladder),
  [200, 0],
  "a receipt never straddles two rungs",
);

assert.throws(() => earnLoyaltyPoints([100], []), Error, "empty ladder");
assert.throws(
  () => earnLoyaltyPoints([100], [{ from: 5, per: 1 }]),
  Error,
  "the opening rung must sit at nought",
);
assert.throws(
  () => earnLoyaltyPoints([100], [{ from: 0, per: 1 }, { from: 0, per: 2 }]),
  Error,
  "from values must climb strictly",
);
assert.throws(
  () => earnLoyaltyPoints([100], [{ from: 0, per: 1, bonus: 4 }]),
  Error,
  "a rung carries exactly two keys",
);
assert.throws(
  () => earnLoyaltyPoints([100], [{ from: 0 }]),
  Error,
  "a rung missing per is rejected",
);
assert.throws(
  () => earnLoyaltyPoints([-1], ladder),
  Error,
  "a receipt below nought is rejected",
);
assert.throws(
  () => earnLoyaltyPoints([12.5], ladder),
  Error,
  "a receipt that is not whole is rejected",
);
assert.throws(
  () => earnLoyaltyPoints([100], [{ from: 0, per: -2 }]),
  Error,
  "a per below nought is rejected",
);
assert.throws(
  () => earnLoyaltyPoints("nope", ladder),
  Error,
  "a non-list of receipts is rejected",
);
console.log("ok");
