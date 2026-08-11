import assert from "node:assert/strict";
import { escapeTag } from "./solution.ts";

assert.equal(escapeTag("shelf"), "shelf", "letters stand for themselves");
assert.equal(escapeTag("bay-3_A"), "bay-3_A", "digits, hyphens and underscores pass through");
assert.equal(escapeTag("row 4"), "row%204", "a space is encoded");
assert.equal(escapeTag("50%"), "50%25", "a percent sign is encoded");
assert.equal(escapeTag("a/b"), "a%2Fb", "a slash takes uppercase hex digits");
assert.equal(escapeTag("\t"), "%09", "a low code is padded to two digits");
assert.equal(escapeTag("~"), "%7E", "a tilde is not a safe character");
assert.throws(() => escapeTag(42), Error, "a label that is not a string is rejected");
assert.throws(() => escapeTag(""), Error, "an empty label is rejected");
assert.throws(() => escapeTag("café"), Error, "a character past 127 is rejected");
console.log("ok");
