import assert from "node:assert/strict";
import { nestOutline } from "./solution.ts";

assert.deepEqual(nestOutline("solo"), [["solo", []]], "one line, one item");
assert.deepEqual(
  nestOutline("a\nb"),
  [["a", []], ["b", []]],
  "two level-zero items"
);
assert.deepEqual(
  nestOutline("a\n  b\n    c"),
  [["a", [["b", [["c", []]]]]]],
  "a straight descent nests three deep"
);
assert.deepEqual(
  nestOutline("root\n  kid\n    grand\n  kid2\nsecond\n  x"),
  [
    ["root", [["kid", [["grand", []]]], ["kid2", []]]],
    ["second", [["x", []]]],
  ],
  "siblings after a dedent attach to the right parent"
);
assert.deepEqual(
  nestOutline("a\n  b\n    c\nd"),
  [["a", [["b", [["c", []]]]]], ["d", []]],
  "a dedent may drop several levels at once"
);
assert.deepEqual(
  nestOutline("top item\n  sub item"),
  [["top item", [["sub item", []]]]],
  "internal spaces in the text survive"
);
assert.deepEqual(
  nestOutline("a\n  b\n"),
  [["a", [["b", []]]]],
  "a single final newline is tolerated"
);
assert.throws(() => nestOutline(""), Error, "empty input");
assert.throws(() => nestOutline("a\n\tb"), Error, "tab character");
assert.throws(() => nestOutline(" a"), Error, "odd indentation");
assert.throws(() => nestOutline("  a"), Error, "opening line indented");
assert.throws(() => nestOutline("a\n    b"), Error, "two-level jump");
assert.throws(() => nestOutline("a\n\nb"), Error, "blank line inside");
assert.throws(() => nestOutline("a\n  "), Error, "all-space line");
console.log("ok");
