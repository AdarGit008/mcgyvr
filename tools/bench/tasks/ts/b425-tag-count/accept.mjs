import assert from "node:assert/strict";
import { tagCount } from "./solution.ts";

assert.equal(tagCount("<a>"), 1, "one marker");
assert.equal(tagCount("<a><b>"), 2, "two markers");
assert.equal(tagCount("plain"), 0, "no markers at all");
assert.equal(tagCount(""), 0, "an empty line");
assert.equal(tagCount("<a"), 0, "an unclosed bracket is not a marker");
assert.throws(() => tagCount("a>"), Error, "an unmatched closing bracket is rejected");
console.log("ok");
