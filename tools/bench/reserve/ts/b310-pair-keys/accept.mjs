import assert from "node:assert/strict";
import { pairKeys } from "./solution.ts";

assert.deepEqual(pairKeys(["a", "b"], ["1", "2"]), { a: "1", b: "2" }, "paired in order");
assert.deepEqual(pairKeys(["a"], ["1", "2"]), { a: "1" }, "a spare code is left out");
assert.deepEqual(pairKeys(["a", "b"], ["1"]), { a: "1" }, "a spare name is left out");
assert.deepEqual(pairKeys([], []), {}, "nothing to pair");
assert.deepEqual(pairKeys(["a", "a"], ["1", "2"]), { a: "2" }, "the later code wins");
assert.deepEqual(pairKeys(["x"], []), {}, "no codes at all");
console.log("ok");
