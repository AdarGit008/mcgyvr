import assert from "node:assert/strict";
import { bracketDepth } from "./solution.ts";

assert.equal(bracketDepth("a(b)c"), 1, "one bracket nests once");
assert.equal(bracketDepth("((x))"), 2, "two brackets nest twice");
assert.equal(bracketDepth("(a)(b)"), 1, "side by side does not deepen");
assert.equal(bracketDepth("(()(()))"), 3, "the deepest run is reported");
assert.equal(bracketDepth("plain"), 0, "a text with no brackets");
assert.equal(bracketDepth(""), 0, "an empty text");
assert.throws(() => bracketDepth(")("), Error, "a close before an open is rejected");
assert.throws(() => bracketDepth("(("), Error, "a bracket left open is rejected");
console.log("ok");
