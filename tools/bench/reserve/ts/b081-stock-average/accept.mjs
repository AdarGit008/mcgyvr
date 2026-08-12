import assert from "node:assert/strict";
import { receiptCents, runStockbook } from "./solution.ts";

assert.deepEqual(runStockbook([]), { held: 0, worth: 0, issued: 0 }, "empty book");
assert.deepEqual(
  runStockbook([["receive", 10, 100]]),
  { held: 10, worth: 1000, issued: 0 },
  "one receive stocks the book",
);
assert.deepEqual(
  runStockbook([["receive", 10, 100], ["receive", 10, 200], ["issue", 5]]),
  { held: 15, worth: 2250, issued: 750 },
  "an issue relieves the moving average, not the latest price",
);
assert.deepEqual(
  runStockbook([["receive", 1, 50], ["receive", 2, 25], ["issue", 1]]),
  { held: 2, worth: 67, issued: 33 },
  "an uneven relief floors to whole cents",
);
assert.deepEqual(
  runStockbook([["receive", 1, 50], ["receive", 2, 25], ["issue", 1], ["issue", 2]]),
  { held: 0, worth: 0, issued: 100 },
  "issuing everything empties the book exactly",
);
assert.equal(receiptCents(3, 250), 750, "a receipt costs quantity times unit cost");
assert.throws(
  () => runStockbook([["receive", 2, 10], ["issue", 3]]),
  Error,
  "issuing more than is held is rejected",
);
assert.throws(
  () => runStockbook([["receive", 2, 10], ["issue", 0]]),
  Error,
  "a zero issue is rejected",
);
assert.throws(
  () => runStockbook([["receive", 4, 10], ["issue", 1.5]]),
  Error,
  "a fractional issue is rejected",
);
assert.throws(
  () => runStockbook([["receive", 0, 10]]),
  Error,
  "a zero receive is rejected",
);
assert.throws(
  () => runStockbook([["receive", 2, -5]]),
  Error,
  "a negative unit cost is rejected",
);
assert.throws(() => receiptCents(1.5, 10), Error, "a fractional receive is rejected");
console.log("ok");
