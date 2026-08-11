import assert from "node:assert/strict";
import { topKeys } from "./solution.ts";

assert.deepEqual(topKeys({ a: 1, b: 3 }), ["b"], "one clear leader");
assert.deepEqual(topKeys({ b: 2, a: 2 }), ["a", "b"], "a tie in alphabetical order");
assert.deepEqual(topKeys({}), [], "an empty mapping");
assert.deepEqual(topKeys({ x: 5 }), ["x"], "one name is the leader");
assert.deepEqual(topKeys({ a: 0, b: 0 }), ["a", "b"], "everything ties at nothing");
assert.deepEqual(topKeys({ c: 1, a: 4, b: 4 }), ["a", "b"], "two share the top");
console.log("ok");
