import assert from "node:assert/strict";
import { crateOverflowPath } from "./solution.ts";

const crate = (tag, weight, cap, inside = []) => ({ tag, weight, cap, inside });

assert.equal(crateOverflowPath(crate("box", 3, 5)), "", "a light lone crate sits fine");
assert.equal(
  crateOverflowPath(crate("box", 5, 5)),
  "",
  "sitting exactly on the cap is fine"
);
assert.equal(crateOverflowPath(crate("box", 9, 5)), "box", "a lone crate can spill");

assert.equal(
  crateOverflowPath(
    crate("ship", 1, 100, [crate("a", 2, 10), crate("b", 3, 10)])
  ),
  "",
  "a roomy nesting spills nowhere"
);

assert.equal(
  crateOverflowPath(crate("ship", 1, 100, [crate("a", 20, 10)])),
  "ship.a",
  "a packed crate over its own cap is named with its trail"
);

assert.equal(
  crateOverflowPath(crate("ship", 5, 6, [crate("a", 2, 10)])),
  "ship",
  "the outer crate carries the weight of what it holds"
);

assert.equal(
  crateOverflowPath(crate("r", 1, 2, [crate("m", 1, 10, [crate("z", 1, 10)])])),
  "r",
  "gross rolls up through every level"
);

assert.equal(
  crateOverflowPath(crate("r", 0, 50, [crate("m", 0, 50, [crate("z", 99, 50)])])),
  "r.m.z",
  "a trail three deep"
);

assert.equal(
  crateOverflowPath(
    crate("r", 0, 5, [
      crate("a", 0, 10, [crate("a1", 99, 10)]),
      crate("b", 99, 1),
    ])
  ),
  "r.a.a1",
  "the earlier branch is searched to the bottom first"
);

assert.throws(
  () => crateOverflowPath([1, 2]),
  Error,
  "an outermost crate that is not a mapping is rejected"
);
assert.throws(
  () => crateOverflowPath(crate("", 1, 5)),
  Error,
  "an empty tag is rejected"
);
assert.throws(
  () => crateOverflowPath(crate("a.b", 1, 5)),
  Error,
  "a tag carrying a full stop is rejected"
);
assert.throws(
  () =>
    crateOverflowPath(crate("r", 0, 5, [crate("twin", 1, 5), crate("twin", 1, 5)])),
  Error,
  "two crates side by side sharing a tag are rejected"
);
assert.throws(
  () => crateOverflowPath(crate("r", -1, 5)),
  Error,
  "a negative weight is rejected"
);
assert.throws(
  () => crateOverflowPath(crate("r", 1, 0)),
  Error,
  "a cap of zero is rejected"
);
assert.throws(
  () => crateOverflowPath({ tag: "r", weight: 1, cap: 5, inside: "none" }),
  Error,
  "an inside that is not a list is rejected"
);

console.log("ok");
