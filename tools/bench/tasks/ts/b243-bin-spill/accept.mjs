import assert from "node:assert/strict";
import { binSpill, binAdd } from "./solution.ts";

assert.deepEqual(binSpill({ a: 5, b: 2 }, 3), ["a"], "only the bin above the limit");
assert.deepEqual(binSpill({ a: 3 }, 3), [], "a bin exactly at the limit stays");
assert.deepEqual(binSpill({}, 1), [], "no bins, nothing spills");
assert.deepEqual(binSpill({ a: 9, b: 8 }, 1), ["a", "b"], "in the order added");
assert.deepEqual(binAdd({}, "a", 2), { a: 2 }, "a new bin takes the count");
assert.deepEqual(binAdd({ a: 2 }, "a", 3), { a: 5 }, "an existing bin accumulates");
console.log("ok");
