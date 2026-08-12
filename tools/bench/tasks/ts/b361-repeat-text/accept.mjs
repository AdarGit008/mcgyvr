import assert from "node:assert/strict";
import { repeatText } from "./solution.ts";

assert.equal(repeatText("ha", 3, "-"), "ha-ha-ha", "three copies joined");
assert.equal(repeatText("ha", 1, "-"), "ha", "one copy takes no separator");
assert.equal(repeatText("ha", 0, "-"), "", "no copies at all");
assert.equal(repeatText("ha", -2, "-"), "", "fewer than none is still none");
assert.equal(repeatText("", 3, "-"), "--", "an empty phrase still separates");
assert.equal(repeatText("x", 2, ", "), "x, x", "a longer separator");
console.log("ok");
