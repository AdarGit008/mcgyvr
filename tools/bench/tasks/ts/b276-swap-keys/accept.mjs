import assert from "node:assert/strict";
import { swapKeys } from "./solution.ts";

assert.deepEqual(
  swapKeys({ ann: "a1", bob: "b2" }),
  { a1: "ann", b2: "bob" },
  "each code finds its name",
);
assert.deepEqual(swapKeys({ zoe: "x", amy: "x" }), { x: "amy" }, "the first name wins");
assert.deepEqual(swapKeys({ ann: "" }), {}, "an empty code is left out");
assert.deepEqual(swapKeys({}), {}, "nothing maps to nothing");
assert.deepEqual(
  swapKeys({ bob: "b2", ann: "a1" }),
  { a1: "ann", b2: "bob" },
  "the order it arrives in does not matter",
);
assert.deepEqual(
  swapKeys({ ann: "a1", bob: "a1", cat: "c3" }),
  { a1: "ann", c3: "cat" },
  "a shared code keeps one name",
);
console.log("ok");
