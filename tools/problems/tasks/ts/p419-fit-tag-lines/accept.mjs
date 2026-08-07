import assert from "node:assert/strict";
import { fitTagLines } from "./solution.ts";

const lines = (...rows) => rows.join("\n");

const box = { head: "box", items: ["red", { head: "tin", items: ["a", "b"] }] };
const row = { head: "row", items: ["one", "two"] };
const deep = { head: "a", items: [{ head: "b", items: ["c"] }] };

assert.equal(
  fitTagLines(box, 19),
  "box(red, tin(a, b))",
  "a tight form measuring exactly the width stays on one line",
);
assert.equal(
  fitTagLines(box, 18),
  lines("box(", "  red,", "  tin(a, b)", ")"),
  "one character over the width spreads the outer tag only",
);
assert.equal(
  fitTagLines(box, 10),
  lines("box(", "  red,", "  tin(", "    a,", "    b", "  )", ")"),
  "the inner tag spreads once its own opening spaces are counted",
);
assert.equal(
  fitTagLines(row, 13),
  "row(one, two)",
  "items are parted by a comma and a space",
);
assert.equal(
  fitTagLines(row, 12),
  lines("row(", "  one,", "  two", ")"),
  "the last item carries no comma",
);
assert.equal(fitTagLines(deep, 7), "a(b(c))", "a tag nested tight enough fits");
assert.equal(
  fitTagLines(deep, 6),
  lines("a(", "  b(c)", ")"),
  "a child that still fits at its own depth is left tight",
);
assert.equal(
  fitTagLines(deep, 5),
  lines("a(", "  b(", "    c", "  )", ")"),
  "two spaces of depth are enough to push the child over",
);
assert.equal(
  fitTagLines({ head: "nil", items: [] }, 5),
  "nil()",
  "a tag with no items is an empty pair of brackets",
);
assert.equal(
  fitTagLines({ head: "q", items: ["abcdefghij"] }, 3),
  lines("q(", "  abcdefghij", ")"),
  "a word longer than the width is never spread",
);

assert.throws(() => fitTagLines("red", 10), Error, "a bare word is rejected");
assert.throws(
  () => fitTagLines({ head: "Box", items: [] }, 10),
  Error,
  "a head with a capital is rejected",
);
assert.throws(
  () => fitTagLines({ head: "", items: [] }, 10),
  Error,
  "an empty head is rejected",
);
assert.throws(
  () => fitTagLines({ head: "box" }, 10),
  Error,
  "a tag without items is rejected",
);
assert.throws(
  () => fitTagLines({ head: "box", items: "red" }, 10),
  Error,
  "items given as a string is rejected",
);
assert.throws(
  () => fitTagLines({ head: "box", items: [7] }, 10),
  Error,
  "an item that is a number is rejected",
);
assert.throws(
  () => fitTagLines({ head: "box", items: [""] }, 10),
  Error,
  "an empty word is rejected",
);
assert.throws(
  () => fitTagLines({ head: "box", items: [{ head: "Bad", items: [] }] }, 10),
  Error,
  "a bad head deeper down is rejected too",
);
assert.throws(
  () => fitTagLines(row, 0),
  Error,
  "a width of zero is rejected",
);
assert.throws(
  () => fitTagLines(row, 1.5),
  Error,
  "a fractional width is rejected",
);
assert.throws(
  () => fitTagLines(row, "10"),
  Error,
  "a width given as a string is rejected",
);
console.log("ok");
