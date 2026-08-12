import assert from "node:assert/strict";
import { codeHash } from "./solution.ts";

assert.equal(codeHash("a", 10), 1, "a is one");
assert.equal(codeHash("z", 100), 26, "z is twenty-six");
assert.equal(codeHash("ab", 10), 3, "the letters add up");
assert.equal(codeHash("", 5), 0, "no letters, no total");
assert.equal(codeHash("a1b", 10), 3, "a digit adds nothing");
assert.equal(codeHash("AB", 10), 3, "case is ignored");
assert.throws(() => codeHash("a", 0), Error, "no buckets is rejected");
console.log("ok");
