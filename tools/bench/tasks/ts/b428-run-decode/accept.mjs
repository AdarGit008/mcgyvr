import assert from "node:assert/strict";
import { runDecode } from "./solution.ts";

assert.equal(runDecode("A3B1"), "AAAB", "two runs written out");
assert.equal(runDecode("A1"), "A", "a run of one");
assert.equal(runDecode(""), "", "nothing to decode");
assert.equal(runDecode("X10"), "XXXXXXXXXX", "a count of two digits");
assert.equal(runDecode("A0B2"), "BB", "a run of none disappears");
assert.equal(runDecode("Z2"), "ZZ", "a single run");
console.log("ok");
