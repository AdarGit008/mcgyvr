import assert from "node:assert/strict";
import { planTerms } from "./solution.ts";

assert.deepEqual(planTerms([], [], 3), [], "no courses, no terms");
assert.deepEqual(planTerms(["welding"], [], 2), [["welding"]], "a lone course");
assert.deepEqual(
  planTerms(["forging", "casting", "milling"], [], 2),
  [["casting", "forging"], ["milling"]],
  "independent courses fill terms to capacity",
);
assert.deepEqual(
  planTerms(["ore", "ingot", "blade"], [["ingot", "ore"], ["blade", "ingot"]], 3),
  [["ore"], ["ingot"], ["blade"]],
  "a chain stretches over terms despite room",
);
assert.deepEqual(
  planTerms(["saw", "wood"], [["saw", "wood"]], 2),
  [["wood"], ["saw"]],
  "a prerequisite never shares its course's term",
);
assert.deepEqual(
  planTerms(
    ["base", "left", "right", "top"],
    [["left", "base"], ["right", "base"], ["top", "left"], ["top", "right"]],
    2,
  ),
  [["base"], ["left", "right"], ["top"]],
  "a diamond of prerequisites",
);
assert.deepEqual(
  planTerms(["zinc", "alloy", "brass"], [], 2),
  [["alloy", "brass"], ["zinc"]],
  "capacity defers the alphabetically last",
);
assert.deepEqual(
  planTerms(["cut", "polish", "zebra"], [["polish", "cut"]], 1),
  [["cut"], ["polish"], ["zebra"]],
  "a deferred course competes alphabetically with the newly unlocked",
);
assert.throws(() => planTerms("welding", [], 1), Error, "non-list courses rejected");
assert.throws(() => planTerms([""], [], 1), Error, "empty course name rejected");
assert.throws(() => planTerms([7], [], 1), Error, "non-string course rejected");
assert.throws(() => planTerms(["kiln", "kiln"], [], 1), Error, "duplicate course rejected");
assert.throws(() => planTerms(["kiln"], [["kiln"]], 1), Error, "one-item prereq rejected");
assert.throws(() => planTerms(["kiln"], [["kiln", "glaze"]], 1), Error, "unknown course rejected");
assert.throws(() => planTerms(["kiln"], [], 0), Error, "zero capacity rejected");
assert.throws(() => planTerms(["kiln"], [], 1.5), Error, "fractional capacity rejected");
assert.throws(
  () => planTerms(["kiln", "glaze"], [["kiln", "glaze"], ["glaze", "kiln"]], 1),
  Error,
  "a prerequisite cycle is rejected",
);
assert.throws(() => planTerms(["kiln"], [["kiln", "kiln"]], 1), Error, "self-prerequisite rejected");
console.log("ok");
