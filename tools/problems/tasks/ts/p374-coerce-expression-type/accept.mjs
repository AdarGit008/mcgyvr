import assert from "node:assert/strict";
import { coerceExpressionType } from "./solution.ts";

const leaf = (name) => ({ type: name });
const node = (op, left, right) => ({ op, left, right });

assert.equal(coerceExpressionType(leaf("tally")), "tally", "a bare leaf carries its own type");
assert.equal(coerceExpressionType(leaf("void")), "void", "a void leaf is still a void");
assert.equal(
  coerceExpressionType(node("+", leaf("tally"), leaf("tally"))),
  "tally",
  "two tallies fuse to a tally",
);
assert.equal(
  coerceExpressionType(node("+", leaf("tally"), leaf("measure"))),
  "measure",
  "measure is the broader quantity",
);
assert.equal(
  coerceExpressionType(node("+", leaf("glyph"), leaf("measure"))),
  "glyph",
  "a glyph swallows a quantity",
);
assert.equal(
  coerceExpressionType(node("+", leaf("glyph"), leaf("glyph"))),
  "glyph",
  "two glyphs fuse to a glyph",
);
assert.equal(
  coerceExpressionType(node("<", node("+", leaf("tally"), leaf("measure")), leaf("tally"))),
  "flag",
  "ordering two quantities gives a flag",
);
assert.equal(
  coerceExpressionType(node("<", leaf("glyph"), leaf("glyph"))),
  "flag",
  "two glyphs may be ordered",
);
assert.equal(
  coerceExpressionType(node("=", leaf("flag"), leaf("flag"))),
  "flag",
  "two flags may be matched",
);
assert.equal(
  coerceExpressionType(node("=", leaf("void"), leaf("glyph"))),
  "flag",
  "a void matches whatever stands opposite",
);
assert.equal(
  coerceExpressionType(node("=", leaf("flag"), leaf("void"))),
  "flag",
  "a void even matches a flag",
);
assert.equal(
  coerceExpressionType(
    node("=", node("+", leaf("tally"), leaf("tally")), node("+", leaf("measure"), leaf("tally"))),
  ),
  "flag",
  "the two sides are worked out before the match",
);
assert.equal(
  coerceExpressionType(node("+", leaf("glyph"), node("+", leaf("tally"), node("+", leaf("measure"), leaf("tally"))))),
  "glyph",
  "a deeper fuse still ends in a glyph",
);

const chain = (levels) => {
  let built = leaf("tally");
  for (let i = 0; i < levels; i++) {
    built = node("+", leaf("tally"), built);
  }
  return built;
};

assert.equal(coerceExpressionType(chain(11)), "tally", "eleven branches still fit the cap");

const rejects = (value) => {
  try {
    coerceExpressionType(value);
  } catch {
    return true;
  }
  return false;
};

assert.ok(rejects(chain(12)), "twelve branches nest too deeply");
assert.ok(rejects(node("+", leaf("flag"), leaf("tally"))), "a flag cannot be fused");
assert.ok(rejects(node("+", leaf("void"), leaf("tally"))), "a void cannot be fused");
assert.ok(rejects(node("<", leaf("glyph"), leaf("tally"))), "a glyph has no order against a quantity");
assert.ok(rejects(node("<", leaf("flag"), leaf("flag"))), "flags have no order");
assert.ok(rejects(node("=", leaf("glyph"), leaf("measure"))), "a glyph does not match a quantity");
assert.ok(rejects(node("=", leaf("flag"), leaf("tally"))), "a flag matches nothing but a flag");
assert.ok(rejects(leaf("rune")), "a type outside the five is refused");
assert.ok(rejects(node("*", leaf("tally"), leaf("tally"))), "an op outside the three is refused");
assert.ok(rejects({ op: "+", left: leaf("tally") }), "a branch wanting its right is refused");
assert.ok(rejects({ type: "tally", op: "+" }), "a node carrying both is refused");
assert.ok(rejects({}), "a node carrying neither is refused");
assert.ok(rejects([leaf("tally")]), "a node that is not a mapping is refused");
console.log("ok");
