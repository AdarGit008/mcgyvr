import assert from "node:assert/strict";
import { topChar } from "./solution.ts";

assert.equal(topChar("aab"), "a", "the commonest character");
assert.equal(topChar("ab"), "a", "a tie goes to the first");
assert.equal(topChar(""), "", "an empty text");
assert.equal(topChar("x"), "x", "a single character");
assert.equal(topChar("abbb"), "b", "the later character wins on count");
assert.equal(topChar("baab"), "b", "a tie between two, the earlier wins");
console.log("ok");
