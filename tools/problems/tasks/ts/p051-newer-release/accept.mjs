import assert from "node:assert/strict";
import { newerRelease } from "./solution.ts";

assert.equal(newerRelease("1.10", "1.9"), 1, "minor compares numerically");
assert.equal(newerRelease("2.0", "1.99"), 1, "major dominates minor");
assert.equal(newerRelease("1.2", "1.2-rc.3"), 1, "stable beats its own release candidate");
assert.equal(newerRelease("1.2-rc.3", "1.2"), -1, "and the mirror image agrees");
assert.equal(
  newerRelease("1.2-alpha.1", "1.2-dev.9"),
  1,
  "alpha outranks dev whatever the builds",
);
assert.equal(newerRelease("1.2-beta.1", "1.2-rc.1"), -1, "rc outranks beta");
assert.equal(
  newerRelease("0.4-rc.10", "0.4-rc.9"),
  1,
  "builds inside one channel compare numerically",
);
assert.equal(newerRelease("3.7", "3.7"), 0, "identical stables are the same release");
assert.equal(
  newerRelease("1.2-beta.4", "1.2-beta.4"),
  0,
  "identical prereleases are the same release",
);
assert.equal(
  newerRelease("1.3-dev.1", "1.2"),
  1,
  "any prerelease of a later minor beats an earlier stable",
);
assert.throws(() => newerRelease("1", "1.0"), Error, "a bare major is rejected");
assert.throws(
  () => newerRelease("1.2-gamma.1", "1.0"),
  Error,
  "an unknown channel is rejected",
);
assert.throws(() => newerRelease("1.2-rc", "1.0"), Error, "a channel without a build is rejected");
assert.throws(() => newerRelease("01.2", "1.0"), Error, "a leading zero is rejected");
assert.throws(() => newerRelease(12, "1.0"), Error, "a non-string argument is rejected");
console.log("ok");
