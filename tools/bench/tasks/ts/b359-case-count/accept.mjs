import assert from "node:assert/strict";
import { caseCount } from "./solution.ts";

assert.deepEqual(caseCount("aB"), [1, 1], "one of each");
assert.deepEqual(caseCount("ABC"), [3, 0], "all capitals");
assert.deepEqual(caseCount("abc"), [0, 3], "all small");
assert.deepEqual(caseCount(""), [0, 0], "nothing at all");
assert.deepEqual(caseCount("12-!"), [0, 0], "no letters among them");
assert.deepEqual(caseCount("Hi There"), [2, 5], "a space counts as neither");
console.log("ok");
