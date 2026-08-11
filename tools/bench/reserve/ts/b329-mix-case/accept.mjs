import assert from "node:assert/strict";
import { mixCase } from "./solution.ts";

assert.equal(mixCase("abc"), "AbC", "the letters alternate");
assert.equal(mixCase("a-b-c"), "A-b-C", "a dash does not move it along");
assert.equal(mixCase(""), "", "nothing to case");
assert.equal(mixCase("AB"), "Ab", "already-capital letters still alternate");
assert.equal(mixCase("1a2b"), "1A2b", "digits are left alone");
assert.equal(mixCase("hello"), "HeLlO", "a longer word");
console.log("ok");
