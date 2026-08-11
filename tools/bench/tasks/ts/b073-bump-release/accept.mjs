import assert from "node:assert/strict";
import { bumpRelease } from "./solution.ts";

assert.equal(bumpRelease("1.2.3", "major"), "2.0.0", "major resets the rest");
assert.equal(bumpRelease("1.2.3", "minor"), "1.3.0", "minor resets patch");
assert.equal(bumpRelease("1.2.3", "patch"), "1.2.4", "patch advances alone");
assert.equal(bumpRelease("2.9.4", "minor"), "2.10.0", "components carry past 9");
assert.equal(bumpRelease("0.0.0", "major"), "1.0.0", "zero components are valid");
assert.throws(() => bumpRelease(42, "major"), Error, "non-string tag");
assert.throws(() => bumpRelease("1.2", "patch"), Error, "two components");
assert.throws(() => bumpRelease("1..3", "patch"), Error, "empty component");
assert.throws(() => bumpRelease("1.02.3", "patch"), Error, "leading zero");
assert.throws(() => bumpRelease("1.2.x", "patch"), Error, "non-digit component");
assert.throws(() => bumpRelease("1.2.3", "micro"), Error, "unknown part name");
console.log("ok");
