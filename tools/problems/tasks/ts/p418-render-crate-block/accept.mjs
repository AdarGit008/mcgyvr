import assert from "node:assert/strict";
import { renderCrateBlock } from "./solution.ts";

const block = (...lines) => lines.join("\n");

assert.equal(
  renderCrateBlock({
    size: 3,
    name: "kite",
    parts: ["rod", 7],
    box: { lid: "tin" },
  }),
  block(
    "{",
    "..name -> <kite>",
    "..size -> 3",
    "..box ->",
    "....{",
    "......lid -> <tin>",
    "....}",
    "..parts ->",
    "....[",
    "......<rod>",
    "......7",
    "....]",
    "}",
  ),
  "flat fields lead, then the deep ones, each group shortest name first",
);
assert.equal(renderCrateBlock({}), "{}", "a crate with no fields is two braces");
assert.equal(
  renderCrateBlock({ b: {}, a: [] }),
  block("{", "..a ->", "....[]", "..b ->", "....{}", "}"),
  "empty holdings still sit one level deeper than their field",
);
assert.equal(
  renderCrateBlock({ zz: 1, a: "x", yyy: 2, bb: { q: 1 }, c: [1] }),
  block(
    "{",
    "..a -> <x>",
    "..zz -> 1",
    "..yyy -> 2",
    "..c ->",
    "....[",
    "......1",
    "....]",
    "..bb ->",
    "....{",
    "......q -> 1",
    "....}",
    "}",
  ),
  "name length decides before the alphabet does",
);
assert.equal(
  renderCrateBlock({ bb: 1, aa: 2 }),
  block("{", "..aa -> 2", "..bb -> 1", "}"),
  "names of equal length fall into alphabetical order",
);
assert.equal(
  renderCrateBlock({ row: [{ k: 1 }, [2, 3]] }),
  block(
    "{",
    "..row ->",
    "....[",
    "......{",
    "........k -> 1",
    "......}",
    "......[",
    "........2",
    "........3",
    "......]",
    "....]",
    "}",
  ),
  "a list keeps its own order and nests crates and lists alike",
);
assert.equal(
  renderCrateBlock({ t: -5 }),
  block("{", "..t -> -5", "}"),
  "a number below zero keeps its hyphen",
);
assert.equal(
  renderCrateBlock({ t: "a b" }),
  block("{", "..t -> <a b>", "}"),
  "a string is wrapped in angle brackets, spaces and all",
);
assert.equal(
  renderCrateBlock({ t: "" }),
  block("{", "..t -> <>", "}"),
  "an empty string is a bare pair of angle brackets",
);

assert.throws(() => renderCrateBlock("hi"), Error, "a string argument is rejected");
assert.throws(() => renderCrateBlock([1]), Error, "a list argument is rejected");
assert.throws(() => renderCrateBlock(null), Error, "a null argument is rejected");
assert.throws(
  () => renderCrateBlock({ Big: 1 }),
  Error,
  "a field name with a capital is rejected",
);
assert.throws(
  () => renderCrateBlock({ "": 1 }),
  Error,
  "an empty field name is rejected",
);
assert.throws(
  () => renderCrateBlock({ t: 1.5 }),
  Error,
  "a number that is not whole is rejected",
);
assert.throws(
  () => renderCrateBlock({ t: true }),
  Error,
  "a value that is a boolean is rejected",
);
assert.throws(
  () => renderCrateBlock({ t: null }),
  Error,
  "a value that is null is rejected",
);
assert.throws(
  () => renderCrateBlock({ t: "a<b" }),
  Error,
  "a string holding an angle bracket is rejected",
);
assert.throws(
  () => renderCrateBlock({ t: "a\nb" }),
  Error,
  "a string holding a line break is rejected",
);
assert.throws(
  () => renderCrateBlock({ box: { Bad: 1 } }),
  Error,
  "a bad name deep inside is rejected too",
);
assert.throws(
  () => renderCrateBlock({ row: [true] }),
  Error,
  "a boolean inside a list is rejected",
);
console.log("ok");
