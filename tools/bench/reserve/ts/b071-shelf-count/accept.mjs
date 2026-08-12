import assert from "node:assert/strict";
import { shelfCount } from "./solution.ts";

assert.deepEqual(shelfCount(5, []), { ending: 5, peak: 5 }, "empty ledger");
assert.deepEqual(
  shelfCount(0, [["receive", 3], ["issue", 1]]),
  { ending: 2, peak: 3 },
  "receive then issue",
);
assert.deepEqual(
  shelfCount(4, [["issue", 1], ["issue", 3]]),
  { ending: 0, peak: 4 },
  "peak is the starting count under issues alone",
);
assert.deepEqual(
  shelfCount(2, [["receive", 5], ["issue", 6], ["receive", 1]]),
  { ending: 2, peak: 7 },
  "peak sits mid-ledger",
);
assert.deepEqual(
  shelfCount(3, [["issue", 3]]),
  { ending: 0, peak: 3 },
  "an issue may empty the shelf exactly",
);
assert.throws(() => shelfCount(-1, []), Error, "negative starting count");
assert.throws(() => shelfCount(1.5, []), Error, "fractional starting count");
assert.throws(() => shelfCount(3, [["receive"]]), Error, "one-item move");
assert.throws(() => shelfCount(3, [["receive", 0]]), Error, "zero qty");
assert.throws(() => shelfCount(3, [["donate", 2]]), Error, "unknown kind");
assert.throws(() => shelfCount(3, [["issue", 4]]), Error, "overdraw is rejected");
console.log("ok");
