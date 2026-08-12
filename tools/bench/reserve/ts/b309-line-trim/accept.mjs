import assert from "node:assert/strict";
import { lineTrim } from "./solution.ts";

assert.equal(lineTrim("a  \nb"), "a\nb", "the tail goes");
assert.equal(lineTrim("  a"), "  a", "a leading space stays");
assert.equal(lineTrim("a\n  \nb"), "a\n\nb", "a line of spaces empties");
assert.equal(lineTrim(""), "", "nothing to trim");
assert.equal(lineTrim("no trailing"), "no trailing", "already clean");
assert.equal(lineTrim("x   "), "x", "the last line counts too");
console.log("ok");
