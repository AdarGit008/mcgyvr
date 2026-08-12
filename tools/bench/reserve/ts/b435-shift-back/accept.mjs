import assert from "node:assert/strict";
import { shiftBack } from "./solution.ts";

assert.equal(shiftBack("d", 3), "a", "three places back");
assert.equal(shiftBack("a", 1), "z", "round from the front to the end");
assert.equal(shiftBack("abc", 0), "abc", "no places at all");
assert.equal(shiftBack("", 3), "", "an empty text");
assert.equal(shiftBack("a-b", 1), "z-a", "a dash is left alone");
assert.equal(shiftBack("Az", 1), "Ay", "a capital is not a small letter");
console.log("ok");
