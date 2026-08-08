import assert from "node:assert/strict";
import { reorderQuantities } from "./solution.ts";

assert.deepEqual(
  reorderQuantities([
    { sku: "BOLT", shelf: 2, due: 0, low: 5, high: 20, pack: 6 },
  ]),
  [{ sku: "BOLT", units: 18 }],
  "a want of eighteen against a pack of six buys three packs",
);

assert.deepEqual(
  reorderQuantities([
    { sku: "BOLT", shelf: 9, due: 0, low: 5, high: 20, pack: 6 },
  ]),
  [],
  "a shelf above the low buys nothing",
);

assert.deepEqual(
  reorderQuantities([{ sku: "NUT", shelf: 5, due: 0, low: 5, high: 12, pack: 1 }]),
  [{ sku: "NUT", units: 7 }],
  "sitting exactly on the low trips the buy",
);

assert.deepEqual(
  reorderQuantities([{ sku: "NUT", shelf: 1, due: 9, low: 5, high: 20, pack: 1 }]),
  [],
  "units already bought hold the cover above the low",
);

assert.deepEqual(
  reorderQuantities([{ sku: "WASHER", shelf: 0, due: 0, low: 0, high: 10, pack: 4 }]),
  [{ sku: "WASHER", units: 12 }],
  "a want of ten against a pack of four buys twelve",
);

assert.deepEqual(
  reorderQuantities([{ sku: "SHIM", shelf: 5, due: 0, low: 5, high: 5, pack: 3 }]),
  [],
  "a want of nought buys nothing even on the low",
);

assert.deepEqual(
  reorderQuantities([
    { sku: "BOLT", shelf: 2, due: 0, low: 5, high: 20, pack: 6 },
    { sku: "NUT", shelf: 40, due: 0, low: 5, high: 20, pack: 6 },
    { sku: "SHIM", shelf: 0, due: 1, low: 3, high: 9, pack: 2 },
  ]),
  [
    { sku: "BOLT", units: 18 },
    { sku: "SHIM", units: 8 },
  ],
  "only the lines that trip appear, in the order given",
);

assert.deepEqual(reorderQuantities([]), [], "an empty storeroom buys nothing");

assert.throws(
  () => reorderQuantities("BOLT"),
  Error,
  "a lines argument that is not a list is rejected",
);
assert.throws(
  () => reorderQuantities([["BOLT", 1]]),
  Error,
  "a line that is not a mapping is rejected",
);
assert.throws(
  () => reorderQuantities([{ sku: "BOLT", shelf: 1, due: 0, low: 1, high: 2 }]),
  Error,
  "a line missing its pack is rejected",
);
assert.throws(
  () =>
    reorderQuantities([
      { sku: "BOLT", shelf: 1, due: 0, low: 1, high: 2, pack: 1, bin: "A" },
    ]),
  Error,
  "a line carrying a spare key is rejected",
);
assert.throws(
  () => reorderQuantities([{ sku: "", shelf: 1, due: 0, low: 1, high: 2, pack: 1 }]),
  Error,
  "an empty sku is rejected",
);
assert.throws(
  () =>
    reorderQuantities([
      { sku: "BOLT", shelf: 1, due: 0, low: 1, high: 2, pack: 1 },
      { sku: "BOLT", shelf: 1, due: 0, low: 1, high: 2, pack: 1 },
    ]),
  Error,
  "a repeated sku is rejected",
);
assert.throws(
  () => reorderQuantities([{ sku: "BOLT", shelf: -1, due: 0, low: 1, high: 2, pack: 1 }]),
  Error,
  "a shelf below nought is rejected",
);
assert.throws(
  () => reorderQuantities([{ sku: "BOLT", shelf: 1, due: 0, low: 5, high: 4, pack: 1 }]),
  Error,
  "a high below the low is rejected",
);
assert.throws(
  () => reorderQuantities([{ sku: "BOLT", shelf: 1, due: 0, low: 1, high: 2, pack: 0 }]),
  Error,
  "a pack below one is rejected",
);
assert.throws(
  () => reorderQuantities([{ sku: "BOLT", shelf: 1.5, due: 0, low: 1, high: 2, pack: 1 }]),
  Error,
  "a shelf that is not whole is rejected",
);
console.log("ok");
