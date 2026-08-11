import assert from "node:assert/strict";
import { drawTreeLines } from "./solution.ts";

assert.deepEqual(drawTreeLines({ name: "attic", children: [] }), ["attic"], "a lone root is one line");
assert.deepEqual(
  drawTreeLines({ name: "attic", children: [{ name: "box", children: [] }] }),
  ["attic", "'-- box"],
  "an only child takes the closing connector",
);
assert.deepEqual(
  drawTreeLines({
    name: "attic",
    children: [{ name: "box", children: [] }, { name: "trunk", children: [] }],
  }),
  ["attic", "|-- box", "'-- trunk"],
  "only the last child closes its branch",
);
assert.deepEqual(
  drawTreeLines({
    name: "attic",
    children: [
      { name: "box", children: [{ name: "photos", children: [] }] },
      { name: "trunk", children: [] },
    ],
  }),
  ["attic", "|-- box", "|   '-- photos", "'-- trunk"],
  "an open branch keeps its bar in front of deeper lines",
);
assert.deepEqual(
  drawTreeLines({
    name: "attic",
    children: [
      { name: "box", children: [] },
      { name: "trunk", children: [{ name: "coats", children: [] }] },
    ],
  }),
  ["attic", "|-- box", "'-- trunk", "    '-- coats"],
  "a closed branch indents with spaces",
);
assert.deepEqual(
  drawTreeLines({
    name: "a",
    children: [{ name: "b", children: [{ name: "c", children: [{ name: "d", children: [] }] }] }],
  }),
  ["a", "'-- b", "    '-- c", "        '-- d"],
  "a chain of only children steps four spaces per level",
);
assert.deepEqual(
  drawTreeLines({
    name: "root",
    children: [
      {
        name: "src",
        children: [
          { name: "app", children: [{ name: "main", children: [] }] },
          { name: "lib", children: [] },
        ],
      },
      { name: "docs", children: [{ name: "guide", children: [] }] },
    ],
  }),
  ["root", "|-- src", "|   |-- app", "|   |   '-- main", "|   '-- lib", "'-- docs", "    '-- guide"],
  "bars trace exactly the branches still open",
);
assert.throws(() => drawTreeLines({ name: "", children: [] }), Error, "an empty name is rejected");
assert.throws(() => drawTreeLines({ name: 7, children: [] }), Error, "a numeric name is rejected");
assert.throws(
  () => drawTreeLines({ name: "att\nic", children: [] }),
  Error,
  "a name spanning lines is rejected",
);
assert.throws(() => drawTreeLines({ name: "attic", children: null }), Error, "children must be a list");
assert.throws(
  () => drawTreeLines({ name: "attic", children: [{ name: "", children: [] }] }),
  Error,
  "a bad node deep in the tree is rejected",
);
console.log("ok");
