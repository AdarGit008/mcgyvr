import assert from "node:assert/strict";
import { checkLine, lineTag } from "./solution.ts";

assert.equal(checkLine("ping~ae"), "ping", "a well-tagged line yields its body");
assert.equal(checkLine("a~b~41"), "a~b", "the body may itself contain a tilde");
assert.equal(checkLine("~00"), "", "an empty body verifies");
assert.throws(() => checkLine("ping~41"), Error, "a wrong tag is rejected");
assert.throws(() => checkLine("ping00"), Error, "a missing separator is rejected");
assert.throws(() => checkLine("xy"), Error, "a line too short for a tag is rejected");
assert.throws(() => checkLine(42), Error, "a non-string line is rejected");
assert.equal(lineTag("ping"), "ae", "the tag is the char-code sum modulo 256 in hex");
assert.throws(() => lineTag(7), Error, "a non-string body is rejected");
console.log("ok");
