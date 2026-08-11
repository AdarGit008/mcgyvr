import assert from "node:assert/strict";
import { badgeRuns } from "./solution.ts";

assert.equal(badgeRuns("AAAB"), "A3B1", "a long run then a single");
assert.equal(badgeRuns("A"), "A1", "a lone letter still carries its count");
assert.equal(badgeRuns("AB"), "A1B1", "two singles");
assert.equal(badgeRuns("AABBA"), "A2B2A1", "a letter may return later");
assert.equal(badgeRuns("ZZZZ"), "Z4", "one run spanning the whole string");
assert.throws(() => badgeRuns(""), Error, "the empty string is rejected");
console.log("ok");
