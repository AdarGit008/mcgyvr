import assert from "node:assert/strict";
import { crateDepth, unpackCrates } from "./solution.ts";

assert.deepEqual(unpackCrates([]), [], "an empty crate unpacks to nothing");
assert.deepEqual(
  unpackCrates(["bolts", "nuts"]),
  ["bolts", "nuts"],
  "a flat crate keeps its order",
);
assert.deepEqual(
  unpackCrates(["tape", ["glue", "twine"], "shears"]),
  ["tape", "glue", "twine", "shears"],
  "a nested crate unpacks in place",
);
assert.deepEqual(
  unpackCrates([["clips", ["pins"]], "labels"]),
  ["clips", "pins", "labels"],
  "deep nesting unpacks depth first",
);
assert.deepEqual(
  unpackCrates(["felt", [], "cord"]),
  ["felt", "cord"],
  "an empty inner crate adds nothing",
);
assert.throws(() => unpackCrates(["felt", 3]), Error, "a numeric entry is rejected");
assert.throws(() => unpackCrates([""]), Error, "an empty name is rejected");
assert.throws(() => unpackCrates(["felt", [null]]), Error, "an invalid nested entry is rejected");
assert.equal(crateDepth(["felt", "cord"]), 1, "a flat crate has depth 1");
assert.equal(crateDepth(["a", ["b", ["c"]]]), 3, "each nesting level adds one");
console.log("ok");
