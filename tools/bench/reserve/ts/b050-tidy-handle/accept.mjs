import assert from "node:assert/strict";
import { normalizeHandle } from "./solution.ts";

assert.equal(normalizeHandle("Dev Team"), "dev-team", "a space becomes a hyphen");
assert.equal(normalizeHandle("  Big  Cat "), "big-cat", "trims and collapses a space run");
assert.equal(normalizeHandle("user_01-beta"), "user-01-beta", "underscores and hyphens unify");
assert.equal(normalizeHandle("a _- b"), "a-b", "a mixed separator run is one hyphen");
assert.equal(normalizeHandle("abcde_fghij_klmno_pq"), "abcde-fghij-klmno-pq", "twenty characters pass");
assert.throws(() => normalizeHandle(42), Error, "non-string is rejected");
assert.throws(() => normalizeHandle("   "), Error, "whitespace-only is rejected");
assert.throws(() => normalizeHandle("dev!team"), Error, "an illegal character is rejected");
assert.throws(() => normalizeHandle("-devs"), Error, "a leading hyphen is rejected");
assert.throws(() => normalizeHandle("ab"), Error, "two characters are too short");
assert.throws(() => normalizeHandle("abcdefghij0abcdefghij"), Error, "twenty-one characters are too long");
console.log("ok");
