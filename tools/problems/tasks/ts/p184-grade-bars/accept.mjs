import assert from "node:assert/strict";
import { gradeBars } from "./solution.ts";

assert.deepEqual(gradeBars("q q q q", 4, 4), ["exact"], "four quarters fill 4/4");
assert.deepEqual(
  gradeBars("q q q|q q q q|h h h", 4, 4),
  ["short", "exact", "long"],
  "the three verdicts in one line",
);
assert.deepEqual(gradeBars("q. e", 2, 4), ["exact"], "a dot adds half again");
assert.deepEqual(gradeBars("h.", 3, 4), ["exact"], "a dotted half fills 3/4");
assert.deepEqual(
  gradeBars("e e e e e e e", 7, 8),
  ["exact"],
  "seven eighths fill 7/8",
);
assert.deepEqual(gradeBars("w", 1, 1), ["exact"], "one whole fills 1/1");
assert.deepEqual(gradeBars("s s s", 1, 16), ["long"], "three sixteenths overrun");
assert.deepEqual(gradeBars("s", 1, 8), ["short"], "a sixteenth underfills 1/8");
assert.deepEqual(
  gradeBars("h h|w.", 1, 2),
  ["long", "long"],
  "both bars run past a half-bar meter",
);
assert.deepEqual(
  gradeBars("q e. s|q q q q", 4, 4),
  ["short", "exact"],
  "dots inside a mixed bar",
);

assert.throws(() => gradeBars("q x", 4, 4), Error, "an unknown letter is rejected");
assert.throws(() => gradeBars("q..", 4, 4), Error, "two full stops are rejected");
assert.throws(() => gradeBars("q||q", 4, 4), Error, "an empty bar is rejected");
assert.throws(() => gradeBars("q q q q", 4, 3), Error, "an odd unit is rejected");
assert.throws(() => gradeBars("q q q q", 0, 4), Error, "zero beats is rejected");
assert.throws(() => gradeBars(9, 4, 4), Error, "a non-string line is rejected");
console.log("ok");
