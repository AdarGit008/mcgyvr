import assert from "node:assert/strict";
import { firstBrokenRule } from "./solution.ts";

const node = (key, count, left = null, right = null) => ({
  key,
  count,
  left,
  right,
});
const leaf = (key, count = 1) => node(key, count);

assert.deepEqual(
  firstBrokenRule(leaf(5)),
  { path: "", rule: "sound" },
  "a lone node breaks nothing"
);

assert.deepEqual(
  firstBrokenRule(node(10, 4, node(5, 2, null, leaf(7)), leaf(20))),
  { path: "", rule: "sound" },
  "a well-formed little tree breaks nothing"
);

assert.deepEqual(
  firstBrokenRule(leaf(5, 2)),
  { path: "root", rule: "count" },
  "a lone node claiming two is caught"
);

assert.deepEqual(
  firstBrokenRule(node(5, 2, leaf(7))),
  { path: "root", rule: "order" },
  "a left child above its parent breaks order"
);

assert.deepEqual(
  firstBrokenRule(node(5, 2, leaf(5))),
  { path: "root", rule: "order" },
  "an equal key on the left is not strictly smaller"
);

assert.deepEqual(
  firstBrokenRule(node(10, 4, node(5, 2, null, leaf(12)), leaf(20))),
  { path: "root", rule: "order" },
  "order looks the whole subtree down, not only at the children"
);

assert.deepEqual(
  firstBrokenRule(node(10, 4, node(5, 2, null, leaf(3)), leaf(20))),
  { path: "root/L", rule: "order" },
  "a sound root does not excuse a broken child"
);

assert.deepEqual(
  firstBrokenRule(node(10, 3, node(5, 2, leaf(1)))),
  { path: "root", rule: "balance" },
  "one side two deeper than the other breaks balance"
);

assert.deepEqual(
  firstBrokenRule(node(10, 3, leaf(5), leaf(20, 2))),
  { path: "root/R", rule: "count" },
  "a child overstating its subtree is caught"
);

assert.deepEqual(
  firstBrokenRule(node(5, 3, node(9, 2, leaf(8)))),
  { path: "root", rule: "order" },
  "order is tested before balance at the same node"
);

assert.deepEqual(
  firstBrokenRule(node(10, 99, node(5, 2, leaf(1)))),
  { path: "root", rule: "balance" },
  "balance is tested before count at the same node"
);

assert.deepEqual(
  firstBrokenRule(
    node(10, 5, node(5, 2, null, leaf(3)), node(20, 2, leaf(25)))
  ),
  { path: "root/L", rule: "order" },
  "the left side is walked before the right"
);

assert.throws(
  () => firstBrokenRule(null),
  Error,
  "an absent root is rejected"
);
assert.throws(() => firstBrokenRule(7), Error, "a root that is not a mapping is rejected");
assert.throws(
  () => firstBrokenRule({ count: 1, left: null, right: null }),
  Error,
  "a node with no key entry is rejected"
);
assert.throws(
  () => firstBrokenRule(node("5", 1)),
  Error,
  "a key that is not a whole number is rejected"
);
assert.throws(
  () => firstBrokenRule(node(5, 0)),
  Error,
  "a count of zero is rejected"
);
assert.throws(
  () => firstBrokenRule({ key: 5, count: 1, right: null }),
  Error,
  "a node with no left entry is rejected"
);
assert.throws(
  () => firstBrokenRule(node(5, 2, 3)),
  Error,
  "a side that is neither a node nor nothing is rejected"
);

console.log("ok");
