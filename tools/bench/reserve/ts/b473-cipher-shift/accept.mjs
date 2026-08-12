import assert from "node:assert/strict";
import { cipherShift } from "./solution.ts";

assert.equal(cipherShift("abc", 1), "bcd", "each letter moves one on");
assert.equal(cipherShift("xyz", 3), "abc", "the end runs back to the start");
assert.equal(cipherShift("z", 1), "a", "the last letter wraps");
assert.equal(cipherShift("a b", 1), "b c", "a space is left alone");
assert.equal(cipherShift("Hello", 1), "Hfmmp", "a capital is left alone");
assert.equal(cipherShift("abc", 0), "abc", "a step of nothing changes nothing");
assert.equal(cipherShift("", 5), "", "an empty text");
console.log("ok");
