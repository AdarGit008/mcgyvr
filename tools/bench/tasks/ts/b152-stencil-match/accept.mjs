import assert from "node:assert/strict";
import { matchesStencil } from "./solution.ts";

assert.equal(matchesStencil("FR-##", "FR-07"), true, "digit slots take digits");
assert.equal(matchesStencil("FR-##", "FR-x7"), false, "a letter cannot fill a digit slot");
assert.equal(matchesStencil("@@-#", "Ab-4"), true, "letter slots take either case");
assert.equal(matchesStencil("@@-#", "a2-4"), false, "a digit cannot fill a letter slot");
assert.equal(matchesStencil("bay?", "bay7"), true, "the wildcard takes any character");
assert.equal(matchesStencil("bay", "bay"), true, "plain characters match themselves");
assert.equal(matchesStencil("Bay", "bay"), false, "literal matching is case-sensitive");
assert.equal(matchesStencil("##", "123"), false, "a longer code never matches");
assert.throws(() => matchesStencil(9, "9"), Error, "a non-string stencil is rejected");
assert.throws(() => matchesStencil("", ""), Error, "an empty stencil is rejected");
assert.throws(() => matchesStencil("##", 12), Error, "a non-string code is rejected");
console.log("ok");
