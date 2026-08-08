import assert from "node:assert/strict";
import { printExprTree } from "./solution.ts";

const node = (op, left, right) => ({ op, left, right });

assert.equal(
  printExprTree(node("*", node("+", "a", "b"), "c")),
  "(a + b) * c",
  "a loose left child under a tight parent needs brackets",
);
assert.equal(
  printExprTree(node("+", node("*", "a", "b"), "c")),
  "a * b + c",
  "a tight left child under a loose parent needs none",
);
assert.equal(printExprTree(42), "42", "a literal renders as its digits");
assert.equal(printExprTree("total"), "total", "a name renders as itself");
assert.equal(printExprTree(node("+", "a", "b")), "a + b", "a plain pair takes no brackets");
assert.equal(
  printExprTree(node("-", "a", node("-", "b", "c"))),
  "a - (b - c)",
  "an equally tight right child is bracketed because the operators gather left",
);
assert.equal(
  printExprTree(node("-", node("-", "a", "b"), "c")),
  "a - b - c",
  "an equally tight left child is left bare",
);
assert.equal(
  printExprTree(node("/", "a", node("*", "b", "c"))),
  "a / (b * c)",
  "division brackets a multiplying right side",
);
assert.equal(
  printExprTree(node("*", node("/", "a", "b"), "c")),
  "a / b * c",
  "division on the left of a product stands unbracketed",
);
assert.equal(
  printExprTree(node("+", node("+", "a", "b"), node("+", "c", "d"))),
  "a + b + (c + d)",
  "only the right of two equal sums is bracketed",
);
assert.equal(
  printExprTree(node("*", node("+", 1, 2), node("-", "x", 3))),
  "(1 + 2) * (x - 3)",
  "both sides may need brackets at once",
);
assert.equal(
  printExprTree(node("+", "a", node("*", "b", node("+", "c", "d")))),
  "a + b * (c + d)",
  "brackets are added only where the depth demands them",
);

assert.throws(() => printExprTree(node("%", "a", "b")), Error, "an unknown operator is rejected");
assert.throws(() => printExprTree({ op: "+", left: "a" }), Error, "a record missing a side is rejected");
assert.throws(() => printExprTree(-1), Error, "a negative literal is rejected");
assert.throws(() => printExprTree(1.5), Error, "a fractional literal is rejected");
assert.throws(() => printExprTree("a1"), Error, "a name with a digit is rejected");
assert.throws(() => printExprTree(""), Error, "an empty name is rejected");
assert.throws(() => printExprTree(null), Error, "a missing node is rejected");
assert.throws(() => printExprTree(["+", "a", "b"]), Error, "a node given as a list is rejected");
assert.throws(() => printExprTree(node("+", "a", -2)), Error, "a bad literal deep in the tree is rejected");
console.log("ok");
