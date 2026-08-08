import assert from "node:assert/strict";
import { clipLabel } from "./solution.ts";

assert.equal(clipLabel("short", 10), "short", "a fitting label is untouched");
assert.equal(clipLabel("exactly10!", 10), "exactly10!", "an exact fit is untouched");
assert.equal(
  clipLabel("abcdefghijk", 10),
  "abcdefg...",
  "an overlong label keeps budget-minus-3 characters plus the dots",
);
assert.equal(
  clipLabel("hello there world", 9),
  "hello...",
  "spaces at the cut are dropped before the dots",
);
assert.equal(clipLabel("abcdefgh", 4), "a...", "the minimum budget keeps one character");
assert.equal(
  clipLabel("ab cdefghij", 7),
  "ab c...",
  "a space inside the kept part survives",
);
assert.equal(clipLabel("", 4), "", "the empty label fits any budget");
assert.throws(() => clipLabel("abcdef", 3), Error, "budget 3 is rejected");
assert.throws(() => clipLabel("abcdef", 4.5), Error, "fractional budget is rejected");
assert.throws(() => clipLabel(123, 8), Error, "non-string label is rejected");
console.log("ok");
