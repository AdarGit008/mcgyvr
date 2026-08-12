import assert from "node:assert/strict";
import { tallyBar } from "./solution.ts";

assert.equal(tallyBar(3, 5), "###", "a bar well inside the width");
assert.equal(tallyBar(5, 5), "#####", "a bar exactly on the width");
assert.equal(tallyBar(9, 5), "####>", "a cut bar is marked");
assert.equal(tallyBar(0, 5), "", "nothing to draw");
assert.equal(tallyBar(1, 5), "#", "a bar of one");
assert.equal(tallyBar(6, 2), "#>", "a short width");
console.log("ok");
