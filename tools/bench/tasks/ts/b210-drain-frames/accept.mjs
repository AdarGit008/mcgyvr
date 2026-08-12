import assert from "node:assert/strict";
import { drainFrames } from "./solution.ts";

assert.deepEqual(drainFrames(["ab|cd", "e|f"], "|"), { frames: ["ab", "cde"], pending: "f" }, "a frame may span two chunks");
assert.deepEqual(drainFrames(["abc"], "|"), { frames: [], pending: "abc" }, "text with no marker is all pending");
assert.deepEqual(drainFrames(["a||b|c"], "|"), { frames: ["a|b"], pending: "c" }, "a doubled marker is one literal marker");
assert.deepEqual(drainFrames(["|x"], "|"), { frames: [""], pending: "x" }, "an opening marker ends an empty frame");
assert.deepEqual(drainFrames(["ab|"], "|"), { frames: [], pending: "ab|" }, "a marker with nothing after it stays unresolved");
assert.deepEqual(drainFrames(["ab||"], "|"), { frames: [], pending: "ab|" }, "a doubled marker at the end folds to a literal");
assert.throws(() => drainFrames(["ab"], "--"), Error, "a marker of two characters is rejected");
console.log("ok");
