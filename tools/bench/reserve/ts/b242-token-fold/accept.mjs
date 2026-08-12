import assert from "node:assert/strict";
import { tokenFold } from "./solution.ts";

assert.equal(tokenFold("hello WORLD"), "Hello World", "case is normalised");
assert.equal(tokenFold("  spaced   out  "), "Spaced Out", "runs collapse and ends trim");
assert.equal(tokenFold("a"), "A", "a single letter");
assert.equal(tokenFold("mIxEd CaSe here"), "Mixed Case Here", "mixed input");
assert.equal(tokenFold("ONE"), "One", "a shouted word");
assert.equal(tokenFold(""), "", "an empty phrase");
assert.equal(tokenFold("   "), "", "whitespace only");
console.log("ok");
