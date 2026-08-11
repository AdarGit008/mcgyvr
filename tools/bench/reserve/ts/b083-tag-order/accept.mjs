import assert from "node:assert/strict";
import { orderReleases } from "./solution.ts";

assert.deepEqual(orderReleases([]), [], "no tags");
assert.deepEqual(
  orderReleases(["1.2.10", "1.2.9", "1.2.2"]),
  ["1.2.2", "1.2.9", "1.2.10"],
  "patch numbers compare numerically",
);
assert.deepEqual(
  orderReleases(["1.4.0", "1.4.0-rc.1"]),
  ["1.4.0-rc.1", "1.4.0"],
  "a candidate precedes its finished release",
);
assert.deepEqual(
  orderReleases(["1.4.0-rc.10", "1.4.0-rc.2"]),
  ["1.4.0-rc.2", "1.4.0-rc.10"],
  "candidate numbers compare numerically",
);
assert.deepEqual(
  orderReleases(["0.9.0", "1.0.0-rc.2", "1.0.0", "1.0.0-rc.10", "2.0.0"]),
  ["0.9.0", "1.0.0-rc.2", "1.0.0-rc.10", "1.0.0", "2.0.0"],
  "majors, candidates and releases interleave correctly",
);
const kept = ["2.0.0", "1.0.0"];
orderReleases(kept);
assert.deepEqual(kept, ["2.0.0", "1.0.0"], "the given list is left untouched");
assert.throws(() => orderReleases("1.0.0"), Error, "non-list argument is rejected");
assert.throws(() => orderReleases([7]), Error, "non-string tag is rejected");
assert.throws(() => orderReleases(["1.2"]), Error, "two-number tag is rejected");
assert.throws(() => orderReleases(["1.02.3"]), Error, "leading zero is rejected");
assert.throws(() => orderReleases(["1.2.3-rc.0"]), Error, "candidate zero is rejected");
assert.throws(() => orderReleases(["1.0.0", "1.0.0"]), Error, "repeated tag is rejected");
console.log("ok");
