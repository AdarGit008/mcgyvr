import assert from "node:assert/strict";
import { applyDiscountBands } from "./solution.ts";

const rule = (code, band, mode, amount, floor, solo) => ({
  code,
  band,
  mode,
  amount,
  floor,
  solo,
});

const CART = [["mug", 450, 2], ["pot", 1200, 1]];

assert.deepEqual(
  applyDiscountBands(CART, []),
  { total: 2100, applied: [] },
  "no rules leaves the subtotal alone",
);
assert.deepEqual(
  applyDiscountBands(CART, [
    rule("WELCOME", "intro", "share", 10, 0, false),
    rule("HELLO", "intro", "share", 25, 0, false),
    rule("BULK", "volume", "flat", 500, 2000, false),
    rule("CHIP", "volume", "flat", 300, 1500, false),
    rule("CLOSE", "final", "share", 5, 0, true),
    rule("EXTRA", "bonus", "flat", 100, 0, false),
  ]),
  { total: 1511, applied: ["WELCOME", "CHIP", "CLOSE"] },
  "bands, floors and a solo rule together",
);
assert.deepEqual(
  applyDiscountBands([["x", 300, 1]], [rule("BIG", "a", "flat", 500, 0, false)]),
  { total: 0, applied: ["BIG"] },
  "a flat cut never digs past the running figure",
);
assert.deepEqual(
  applyDiscountBands([], [
    rule("A", "b1", "share", 10, 0, false),
    rule("B", "b1", "flat", 700, 0, false),
    rule("C", "b2", "flat", 700, 0, false),
  ]),
  { total: 0, applied: ["A", "C"] },
  "a bite claims its band even when the cut is nothing",
);
assert.deepEqual(
  applyDiscountBands([["x", 1000, 1]], [
    rule("P", "z", "flat", 900, 5000, false),
    rule("Q", "z", "share", 20, 0, false),
  ]),
  { total: 800, applied: ["Q"] },
  "a rule held back by its floor does not claim the band",
);
assert.deepEqual(
  applyDiscountBands([["x", 999, 1]], [rule("R", "a", "share", 33, 0, false)]),
  { total: 670, applied: ["R"] },
  "a part of a cent is dropped from a share cut",
);
assert.deepEqual(
  applyDiscountBands([["x", 1000, 1]], [
    rule("S", "a", "share", 50, 0, true),
    rule("T", "b", "flat", 100, 0, false),
  ]),
  { total: 500, applied: ["S"] },
  "a solo bite passes over every rule behind it",
);
assert.deepEqual(
  applyDiscountBands([["x", 1000, 1]], [
    rule("S", "a", "flat", 100, 5000, true),
    rule("T", "b", "flat", 100, 0, false),
  ]),
  { total: 900, applied: ["T"] },
  "a solo rule that never bites blocks nothing",
);
assert.deepEqual(
  applyDiscountBands([["x", 500, 2]], [
    rule("A", "a", "share", 50, 0, false),
    rule("B", "b", "flat", 100, 600, false),
  ]),
  { total: 500, applied: ["A"] },
  "a floor is read against the running figure, not the subtotal",
);
assert.deepEqual(
  applyDiscountBands([["x", 100, 3], ["x", 50, 2]], []),
  { total: 400, applied: [] },
  "one sku may appear on two lines",
);

const ONE = [rule("A", "a", "flat", 100, 0, false)];
assert.throws(() => applyDiscountBands([["x", 300]], ONE), Error, "a basket line that is not a triple is refused");
assert.throws(() => applyDiscountBands([["", 300, 1]], ONE), Error, "an empty sku is refused");
assert.throws(() => applyDiscountBands([["x", -1, 1]], ONE), Error, "negative unit cents are refused");
assert.throws(() => applyDiscountBands([["x", 1.5, 1]], ONE), Error, "fractional unit cents are refused");
assert.throws(() => applyDiscountBands([["x", 300, 0]], ONE), Error, "a count under one is refused");
assert.throws(
  () => applyDiscountBands(CART, [{ code: "A", band: "a", mode: "flat", amount: 1, floor: 0 }]),
  Error,
  "a rule missing a key is refused",
);
assert.throws(
  () => applyDiscountBands(CART, [{ ...rule("A", "a", "flat", 1, 0, false), extra: 1 }]),
  Error,
  "a rule carrying an extra key is refused",
);
assert.throws(
  () => applyDiscountBands(CART, [rule("A", "a", "flat", 1, 0, false), rule("A", "b", "flat", 1, 0, false)]),
  Error,
  "two rules sharing a code are refused",
);
assert.throws(() => applyDiscountBands(CART, [rule("A", "a", "half", 1, 0, false)]), Error, "an unknown mode is refused");
assert.throws(() => applyDiscountBands(CART, [rule("A", "a", "share", 0, 0, false)]), Error, "a share of nought is refused");
assert.throws(() => applyDiscountBands(CART, [rule("A", "a", "share", 101, 0, false)]), Error, "a share past 100 is refused");
assert.throws(() => applyDiscountBands(CART, [rule("A", "a", "flat", 0, 0, false)]), Error, "a flat amount of nought is refused");
assert.throws(() => applyDiscountBands(CART, [rule("A", "a", "flat", 1, -1, false)]), Error, "a negative floor is refused");
assert.throws(() => applyDiscountBands(CART, [rule("A", "a", "flat", 1, 0, "yes")]), Error, "a solo flag that is not a boolean is refused");
assert.throws(() => applyDiscountBands(CART, [["A", "a", "flat", 1, 0, false]]), Error, "a rule that is not a mapping is refused");
console.log("ok");
