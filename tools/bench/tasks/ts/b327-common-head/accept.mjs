import assert from "node:assert/strict";
import { commonHead } from "./solution.ts";

assert.equal(commonHead(["flow", "flower", "flight"]), "fl", "two shared letters");
assert.equal(commonHead(["one"]), "one", "one word shares itself");
assert.equal(commonHead([]), "", "no words at all");
assert.equal(commonHead(["a", "b"]), "", "nothing in common");
assert.equal(commonHead(["same", "same"]), "same", "the whole word is shared");
assert.equal(commonHead(["prefix", "pre"]), "pre", "the shorter word bounds it");
console.log("ok");
