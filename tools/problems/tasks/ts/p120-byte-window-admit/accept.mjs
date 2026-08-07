import assert from "node:assert/strict";
import { admitBytes } from "./solution.ts";

assert.deepEqual(admitBytes(10, 20, 5, []), [], "no entries, no labels");
assert.deepEqual(
  admitBytes(10, 20, 5, [[0, "a", 6], [1, "a", 6]]),
  ["pass", "drop"],
  "the per-key ceiling sheds the second burst"
);
assert.deepEqual(
  admitBytes(10, 12, 5, [[0, "a", 8], [0, "b", 8], [0, "c", 4]]),
  ["pass", "drop", "pass"],
  "the shared ceiling binds even when each key is fine"
);
assert.deepEqual(
  admitBytes(10, 20, 5, [[0, "a", 8], [1, "a", 5], [2, "a", 2]]),
  ["pass", "drop", "pass"],
  "a shed entry consumes nothing, so a smaller one squeezes in"
);
assert.deepEqual(
  admitBytes(10, 20, 5, [[0, "a", 10], [4, "a", 1], [5, "a", 10]]),
  ["pass", "drop", "pass"],
  "an entry ages out at exactly span"
);
assert.deepEqual(
  admitBytes(6, 20, 3, [[0, "a", 6], [1, "b", 6], [2, "b", 1], [3, "a", 6]]),
  ["pass", "pass", "drop", "pass"],
  "keys are metered independently inside the window"
);
assert.deepEqual(
  admitBytes(5, 20, 4, [[0, "a", 9]]),
  ["drop"],
  "an oversized entry is shed, not an error"
);
assert.throws(() => admitBytes(0, 20, 5, []), Error, "zero perKey");
assert.throws(() => admitBytes(10, 20, 0, []), Error, "zero span");
assert.throws(() => admitBytes(10, 20, 5, [[0, "a", 0]]), Error, "zero size");
assert.throws(() => admitBytes(10, 20, 5, [[-1, "a", 1]]), Error, "negative time");
assert.throws(
  () => admitBytes(10, 20, 5, [[3, "a", 1], [2, "a", 1]]),
  Error,
  "times running backwards"
);
assert.throws(() => admitBytes(10, 20, 5, [[0, "", 1]]), Error, "empty key");
console.log("ok");
