import assert from "node:assert/strict";
import { hugText } from "./solution.ts";

assert.equal(hugText("abc", "*"), "*abc*", "a bare text takes a mark at each end");
assert.equal(hugText("*abc*", "*"), "*abc*", "a text already marked at both ends");
assert.equal(hugText("*abc", "*"), "**abc*", "marked at the opening only");
assert.equal(hugText("abc*", "*"), "*abc**", "marked at the closing only");
assert.equal(hugText("**", "*"), "**", "a text that is two marks");
assert.equal(hugText("", "*"), "**", "a text holding nothing");
console.log("ok");
