import assert from "node:assert/strict";
import { rawTally } from "./solution.ts";

assert.deepEqual(rawTally({}, "bolt", 1), { bolt: 1 }, "an item without a recipe is raw");
assert.deepEqual(
  rawTally({ cart: ["wheel", "wheel", "frame"] }, "cart", 1),
  { wheel: 2, frame: 1 },
  "repeated components add up",
);
const shop = {
  cart: ["wheel", "wheel", "frame"],
  wheel: ["rim", "spoke", "spoke"],
};
assert.deepEqual(
  rawTally(shop, "cart", 1),
  { rim: 2, spoke: 4, frame: 1 },
  "nested recipes expand to raw parts",
);
assert.deepEqual(
  rawTally(shop, "cart", 3),
  { rim: 6, spoke: 12, frame: 3 },
  "batches scale the whole tally",
);
assert.deepEqual(
  rawTally({ kit: ["axle", "axle"], axle: ["rod", "cap"] }, "kit", 1),
  { rod: 2, cap: 2 },
  "a shared subassembly is charged once per use",
);
const chain = {};
for (let level = 1; level <= 40; level += 1) {
  chain["p" + level] = ["p" + (level - 1), "p" + (level - 1)];
}
assert.deepEqual(
  rawTally(chain, "p40", 1),
  { p0: 1099511627776 },
  "a forty-level doubling chain resolves inside the time limit",
);
assert.throws(() => rawTally({ a: ["a"] }, "a", 1), Error, "a self-recipe is rejected");
assert.throws(
  () => rawTally({ gear: ["hub"], hub: ["gear"] }, "gear", 1),
  Error,
  "a mutual cycle is rejected",
);
assert.throws(() => rawTally({ a: [] }, "a", 1), Error, "an empty component list is rejected");
assert.throws(() => rawTally({ a: [7] }, "a", 1), Error, "a non-string component is rejected");
assert.throws(() => rawTally({}, "", 1), Error, "an empty item name is rejected");
assert.throws(() => rawTally({}, 9, 1), Error, "a non-string item is rejected");
assert.throws(() => rawTally({}, "bolt", 0), Error, "zero batches is rejected");
assert.throws(() => rawTally({}, "bolt", 1.5), Error, "fractional batches is rejected");
console.log("ok");
