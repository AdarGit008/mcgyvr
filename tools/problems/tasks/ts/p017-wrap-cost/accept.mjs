import assert from "node:assert/strict";
import { wrapCost } from "./solution.ts";

assert.equal(wrapCost(["ab", "cd"], 5), 0, "a perfect single line costs nothing");
assert.equal(wrapCost(["ab", "cd"], 4), 8, "forced onto two lines");
assert.equal(wrapCost(["a", "b", "c"], 3), 4, "pair one line, leave one word");
assert.equal(
  wrapCost(["aaa", "bb", "cc", "ddddd"], 6),
  11,
  "greedy packing gives 17 here; the best split gives 11",
);
assert.equal(wrapCost(["hello"], 5), 0, "one word, exact fit");
assert.equal(wrapCost(["hi"], 5), 9, "one short word pays its slack");
assert.equal(wrapCost(["a", "bb", "c"], 6), 0, "all words on one full line");
assert.throws(() => wrapCost(["toolong"], 3), Error, "an oversized word is rejected");
assert.throws(() => wrapCost(["a"], 0), Error, "zero width rejected");
assert.throws(() => wrapCost(["a"], 2.5), Error, "fractional width rejected");
assert.throws(() => wrapCost([], 5), Error, "empty word list rejected");
assert.throws(() => wrapCost(["a", ""], 5), Error, "empty word rejected");
console.log("ok");
