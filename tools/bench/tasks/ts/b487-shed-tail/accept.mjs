import assert from "node:assert/strict";
import { shedTail } from "./solution.ts";

assert.equal(shedTail("filename..", "."), "filename", "the piece comes off again and again");
assert.equal(shedTail("report", "."), "report", "the text never closes with the piece");
assert.equal(shedTail("aXYXY", "XY"), "a", "a piece of more than one character");
assert.equal(shedTail("keep.", "."), "keep", "a single closing piece");
assert.equal(shedTail("hold", ""), "hold", "a piece holding nothing");
assert.equal(shedTail("", "."), "", "a text holding nothing");
console.log("ok");
