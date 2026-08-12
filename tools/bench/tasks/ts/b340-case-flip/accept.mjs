import assert from "node:assert/strict";
import { swapCase } from "./solution.ts";

assert.equal(swapCase("aB"), "Ab", "both letters turn");
assert.equal(swapCase("abc"), "ABC", "lower becomes upper");
assert.equal(swapCase("ABC"), "abc", "upper becomes lower");
assert.equal(swapCase(""), "", "nothing to turn");
assert.equal(swapCase("a1B"), "A1b", "a digit is left alone");
assert.equal(swapCase("Hello"), "hELLO", "a whole word turns");
console.log("ok");
