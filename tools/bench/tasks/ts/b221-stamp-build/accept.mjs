import assert from "node:assert/strict";
import { stampBuild } from "./solution.ts";

assert.equal(stampBuild(0, 0, 0), 0, "the first release stamps as zero");
assert.equal(stampBuild(0, 0, 1), 1, "a patch step is worth one");
assert.equal(stampBuild(0, 1, 0), 1000, "a minor step is worth a thousand");
assert.equal(stampBuild(1, 0, 0), 1000000, "a major step is worth a million");
assert.equal(stampBuild(2, 14, 3), 2014003, "the three components pack together");
assert.equal(stampBuild(1, 9, 9), 1009009, "a minor below ten keeps its field");
assert.equal(stampBuild(1, 10, 0), 1010000, "the later release stamps higher");
assert.throws(() => stampBuild(1.5, 0, 0), Error, "a fractional component is rejected");
assert.throws(() => stampBuild("1", 0, 0), Error, "a string component is rejected");
assert.throws(() => stampBuild(true, 0, 0), Error, "a boolean component is rejected");
assert.throws(() => stampBuild(-1, 0, 0), Error, "a negative component is rejected");
assert.throws(() => stampBuild(0, 1000, 0), Error, "a minor beyond its field is rejected");
console.log("ok");
