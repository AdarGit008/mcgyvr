import assert from "node:assert/strict";
import { firstUnbalanced } from "./solution.ts";

assert.equal(firstUnbalanced(""), -1, "empty string is balanced");
assert.equal(firstUnbalanced("([]{})"), -1, "nested mix is balanced");
assert.equal(firstUnbalanced("ab(c)d"), -1, "non-brackets are ignored");
assert.equal(firstUnbalanced("no brackets at all"), -1, "no brackets is balanced");
assert.equal(firstUnbalanced(")"), 0, "closer with no opener");
assert.equal(firstUnbalanced("()]"), 2, "stray closer after balanced pair");
assert.equal(firstUnbalanced("([)]"), 2, "cross-nesting reports the bad closer");
assert.equal(firstUnbalanced("{[}"), 2, "wrong closer kind");
assert.equal(firstUnbalanced("(([]"), 0, "earliest unclosed opener wins");
assert.equal(firstUnbalanced("()("), 2, "unclosed opener after balanced pair");
assert.equal(firstUnbalanced("x[y(z"), 1, "earliest opener among several, non-brackets skipped");
assert.equal(firstUnbalanced("({})]"), 4, "closer after fully balanced prefix");
assert.equal(firstUnbalanced("(]"), 1, "mismatched closer at index 1");
