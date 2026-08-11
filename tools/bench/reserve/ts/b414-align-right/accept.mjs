import assert from "node:assert/strict";
import { widestOf, alignRight } from "./solution.ts";

assert.equal(widestOf(["a", "bbb"]), 3, "the longest entry");
assert.equal(widestOf([]), 0, "no entries at all");
assert.deepEqual(alignRight(["1", "100"]), ["  1", "100"], "aligned to the widest");
assert.deepEqual(alignRight([]), [], "nothing to align");
assert.deepEqual(alignRight(["ab", "cd"]), ["ab", "cd"], "already the same width");
assert.deepEqual(alignRight(["x"]), ["x"], "one entry needs no spaces");
console.log("ok");
