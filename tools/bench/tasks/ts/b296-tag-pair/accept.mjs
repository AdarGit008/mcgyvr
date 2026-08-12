import assert from "node:assert/strict";
import { tagOpen, tagPair } from "./solution.ts";

assert.equal(tagOpen("<p>"), "p", "an opening marker names itself");
assert.equal(tagOpen("</p>"), "p", "the slash is dropped");
assert.equal(tagPair("<div>", "</div>"), true, "a matched pair");
assert.equal(tagPair("<div>", "</span>"), false, "a mismatched pair");
assert.throws(() => tagOpen("p"), Error, "an unbracketed marker is rejected");
assert.throws(() => tagPair("<p>", "p"), Error, "either side may be rejected");
console.log("ok");
