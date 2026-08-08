import assert from "node:assert/strict";
import { orderSections } from "./solution.ts";

assert.deepEqual(
  orderSections(["10", "9", "1"]),
  ["1", "9", "10"],
  "components compare numerically, not lexicographically",
);
assert.deepEqual(
  orderSections(["1.2.10", "1.2.9", "1.2.2"]),
  ["1.2.2", "1.2.9", "1.2.10"],
  "deep components compare numerically too",
);
assert.deepEqual(
  orderSections(["2.1", "2", "2.1.1"]),
  ["2", "2.1", "2.1.1"],
  "a prefix label precedes its extensions",
);
assert.deepEqual(
  orderSections(["3.2", "1.10", "3", "1.9", "2"]),
  ["1.9", "1.10", "2", "3", "3.2"],
  "a mixed bag sorts like a table of contents",
);
assert.deepEqual(
  orderSections(["0", "0.1", "1"]),
  ["0", "0.1", "1"],
  "a lone zero component is legal",
);
assert.deepEqual(orderSections([]), [], "no labels, no output");
assert.deepEqual(orderSections(["7"]), ["7"], "a single label survives alone");
assert.throws(() => orderSections(["1.1", "1.1"]), Error, "a duplicate label is rejected");
assert.throws(() => orderSections(["2.01"]), Error, "a zero-padded component is rejected");
assert.throws(() => orderSections(["1..2"]), Error, "an empty component is rejected");
assert.throws(() => orderSections(["1.2."]), Error, "a trailing dot is rejected");
assert.throws(() => orderSections([""]), Error, "the empty label is rejected");
assert.throws(() => orderSections([3]), Error, "a non-string label is rejected");
console.log("ok");
