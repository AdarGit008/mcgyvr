import assert from "node:assert/strict";
import { checkManifest } from "./solution.ts";

assert.deepEqual(
  checkManifest({ sku: " ab-12 ", count: 3, note: "chipped" }),
  { sku: "AB-12", count: 3, note: "chipped" },
  "a full line files uppercased and trimmed",
);
assert.deepEqual(
  checkManifest({ sku: "zz9", count: 1 }),
  { sku: "ZZ9", count: 1, note: "" },
  "an absent note files as the empty string",
);
assert.deepEqual(
  checkManifest({ sku: "a1", count: 5, note: " as found " }),
  { sku: "A1", count: 5, note: " as found " },
  "a note keeps the spaces it was given",
);
const filed = { sku: "q7", count: 2 };
checkManifest(filed);
assert.deepEqual(filed, { sku: "q7", count: 2 }, "the line handed in is untouched");
assert.throws(() => checkManifest({ sku: "a1", count: 1, colour: "red" }), Error, "a fourth key is rejected");
assert.throws(() => checkManifest({ count: 1 }), Error, "a missing sku is rejected");
assert.throws(() => checkManifest({ sku: "   ", count: 1 }), Error, "a blank sku is rejected");
assert.throws(() => checkManifest({ sku: "a1", count: 0 }), Error, "a count of zero is rejected");
assert.throws(() => checkManifest({ sku: "a1", count: 1, note: 9 }), Error, "a note that is not a string is rejected");
console.log("ok");
