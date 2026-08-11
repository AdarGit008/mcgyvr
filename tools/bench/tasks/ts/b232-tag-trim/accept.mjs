import assert from "node:assert/strict";
import { tagTrim } from "./solution.ts";

assert.equal(tagTrim("#draft:"), "draft", "both markers go");
assert.equal(tagTrim("#draft"), "draft", "a leading marker alone");
assert.equal(tagTrim("draft:"), "draft", "a trailing marker alone");
assert.equal(tagTrim("draft"), "draft", "no markers, no change");
assert.equal(tagTrim("##draft::"), "#draft:", "only one of each is stripped");
assert.equal(tagTrim("#"), "", "a bare marker leaves nothing");
assert.equal(tagTrim(""), "", "an empty tag stays empty");
console.log("ok");
