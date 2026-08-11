import assert from "node:assert/strict";
import { keyOf, groupSum } from "./solution.ts";

assert.equal(keyOf({ name: "a" }), "a", "the name is the group");
assert.equal(keyOf({}), "", "no name, no group");
assert.deepEqual(
  groupSum([{ name: "a", amount: 1 }, { name: "a", amount: 2 }]),
  { a: 3 },
  "one group totalled",
);
assert.deepEqual(groupSum([{ amount: 5 }]), {}, "a nameless record is passed over");
assert.deepEqual(groupSum([]), {}, "no records at all");
assert.deepEqual(
  groupSum([{ name: "a", amount: 1 }, { name: "b", amount: 2 }]),
  { a: 1, b: 2 },
  "two groups",
);
console.log("ok");
