import assert from "node:assert/strict";
import { bracketSeedOrder } from "./solution.ts";

assert.deepEqual(bracketSeedOrder(2), [1, 2], "two entrants meet at once");
assert.deepEqual(bracketSeedOrder(4), [1, 4, 2, 3], "four entrants split the halves");
assert.deepEqual(
  bracketSeedOrder(8),
  [1, 8, 4, 5, 2, 7, 3, 6],
  "eight entrants, seed 2 anchors the bottom half",
);
assert.deepEqual(
  bracketSeedOrder(16),
  [1, 16, 8, 9, 4, 13, 5, 12, 2, 15, 7, 10, 3, 14, 6, 11],
  "sixteen entrants in canonical order",
);
const sheet = bracketSeedOrder(8);
assert.ok(sheet.indexOf(2) >= 4, "seeds 1 and 2 sit in opposite halves");
assert.ok(
  sheet.indexOf(3) >= 4 && sheet.indexOf(4) < 4,
  "seeds 3 and 4 land opposite seeds 2 and 1",
);
assert.throws(() => bracketSeedOrder(3), Error, "non-power count rejected");
assert.throws(() => bracketSeedOrder(0), Error, "zero rejected");
assert.throws(() => bracketSeedOrder(1), Error, "a lone entrant rejected");
assert.throws(() => bracketSeedOrder(2.5), Error, "fractional count rejected");
console.log("ok");
