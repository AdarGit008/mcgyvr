import assert from "node:assert/strict";
import { enterCount } from "./solution.ts";

assert.equal(enterCount(["a", "a", "b", "a"], "a"), 2, "held then re-entered");
assert.equal(enterCount(["a"], "a"), 1, "entered at the start");
assert.equal(enterCount([], "a"), 0, "no states at all");
assert.equal(enterCount(["b"], "a"), 0, "never entered");
assert.equal(enterCount(["a", "b", "a", "b", "a"], "a"), 3, "entered three times");
assert.equal(enterCount(["a", "a"], "a"), 1, "holding is not re-entering");
console.log("ok");
