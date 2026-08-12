import assert from "node:assert/strict";
import { stripTags } from "./solution.ts";

assert.equal(stripTags("a<b>c"), "ac", "the marker goes");
assert.equal(stripTags("<p>hi</p>"), "hi", "markers at both ends");
assert.equal(stripTags("plain"), "plain", "no markers at all");
assert.equal(stripTags(""), "", "an empty line");
assert.equal(stripTags("a<b"), "a", "an unclosed marker eats the rest");
assert.equal(stripTags("<a><b>x"), "x", "two markers in a row");
console.log("ok");
