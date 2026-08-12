import assert from "node:assert/strict";
import { netTally } from "./solution.ts";

assert.equal(netTally(["mug|4|1"]), "mug    3\ntotal  3", "a single row reports");
assert.equal(
  netTally(["mug|4|1", "mug|2|0"]),
  "mug    5\ntotal  5",
  "an item sums across sheets",
);
assert.equal(
  netTally(["pot|5|0\ncup|3|1"]),
  "cup    2\npot    5\ntotal  7",
  "items sort by name",
);
assert.equal(
  netTally(["espresso|10|4"]),
  "espresso  6\ntotal     6",
  "the longest name sets the padding width",
);
assert.equal(
  netTally(["\n  mug | 4 | 1  \n\n"]),
  "mug    3\ntotal  3",
  "blank rows are skipped and fields are trimmed",
);
assert.equal(netTally(["jar|2|2"]), "jar    0\ntotal  0", "a zero net renders");
assert.equal(netTally([]), "", "no sheets yields the empty string");
assert.equal(netTally(["\n   \n"]), "", "only blank rows yields the empty string");
assert.throws(() => netTally(7), Error, "a non-list argument is rejected");
assert.throws(() => netTally([3]), Error, "a non-string sheet is rejected");
assert.throws(() => netTally(["mug|4"]), Error, "a two-field row is rejected");
assert.throws(() => netTally(["|1|0"]), Error, "an empty item name is rejected");
assert.throws(() => netTally(["mug|4.5|0"]), Error, "a fractional count is rejected");
assert.throws(
  () => netTally(["mug|1|0", "mug|0|3"]),
  Error,
  "returns exceeding sales are rejected",
);
console.log("ok");
