import assert from "node:assert/strict";
import { describeAncestry } from "./solution.ts";

const trail = {
  init: [],
  alpha: ["init"],
  beta: ["alpha"],
  gamma: ["alpha"],
  delta: ["beta", "gamma"],
  solo: [],
};

assert.equal(describeAncestry(trail, "alpha", "alpha"), "same", "a checkpoint and itself");
assert.equal(describeAncestry(trail, "init", "beta"), "behind:2", "two steps back");
assert.equal(describeAncestry(trail, "beta", "init"), "ahead:2", "two steps forward");
assert.equal(describeAncestry(trail, "beta", "gamma"), "apart", "two strands of one fork");
assert.equal(describeAncestry(trail, "alpha", "delta"), "behind:2", "through a fold");
assert.equal(describeAncestry(trail, "delta", "alpha"), "ahead:2", "the fold seen the other way");
assert.equal(describeAncestry(trail, "gamma", "delta"), "behind:1", "a single step back");
assert.equal(describeAncestry(trail, "init", "delta"), "behind:3", "the shortest of two routes");
assert.equal(describeAncestry(trail, "solo", "init"), "apart", "two openings never meet");
assert.equal(describeAncestry(trail, "init", "solo"), "apart", "and neither way round");
assert.throws(() => describeAncestry(trail, "init", "zeta"), Error, "an unknown checkpoint");
assert.throws(
  () => describeAncestry({ a: ["z"] }, "a", "a"),
  Error,
  "an unknown predecessor",
);
assert.throws(
  () => describeAncestry({ a: [], b: [7] }, "a", "b"),
  Error,
  "a predecessor that is not a name",
);
assert.throws(() => describeAncestry({ a: "b" }, "a", "a"), Error, "a value that is not a list");
assert.throws(() => describeAncestry([], "a", "a"), Error, "a history that is not a mapping");
console.log("ok");
