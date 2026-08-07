import assert from "node:assert/strict";
import { printOperatorTree } from "./solution.ts";

const op = (name, left, right) => ({ op: name, left, right });
const neg = (inner) => ({ negate: inner });
const call = (word, args) => ({ call: word, args });

assert.equal(
  printOperatorTree(op("+", op("*", "a", "b"), "c")),
  "a * b + c",
  "a tighter operand under a looser operator stands bare",
);
assert.equal(
  printOperatorTree(op("^", "a", op("^", "b", "c"))),
  "a ^ b ^ c",
  "the gathering side of ^ needs no parentheses",
);
assert.equal(
  printOperatorTree(op("^", op("^", "a", "b"), "c")),
  "(a ^ b) ^ c",
  "the other side of ^ does",
);
assert.equal(
  printOperatorTree(neg(op("+", "a", "b"))),
  "-(a + b)",
  "a sum under a minus sign is parenthesised",
);
assert.equal(
  printOperatorTree(op("^", neg("a"), "b")),
  "(-a) ^ b",
  "a negate under ^ binds too loosely to stand bare",
);
assert.equal(
  printOperatorTree(neg(op("^", "a", "b"))),
  "-a ^ b",
  "a power under a minus sign binds tightly enough to stand bare",
);
assert.equal(
  printOperatorTree(neg(neg("a"))),
  "-(-a)",
  "a negate directly under a negate is always parenthesised",
);
assert.equal(
  printOperatorTree(op("and", op("or", "p", "q"), "r")),
  "(p or q) and r",
  "or is looser than and and must be fenced off",
);
assert.equal(
  printOperatorTree(op("or", "p", op("and", "q", "r"))),
  "p or q and r",
  "and under or needs nothing",
);
assert.equal(
  printOperatorTree(op("or", "p", op("or", "q", "r"))),
  "p or (q or r)",
  "equal power on the non-gathering side takes parentheses",
);
assert.equal(
  printOperatorTree(call("max", ["a", op("+", "b", 1), neg("c")])),
  "max(a, b + 1, -c)",
  "arguments are separated by a comma and a space and never fenced",
);
assert.equal(printOperatorTree(call("now", [])), "now()", "a call may take nothing");
assert.equal(
  printOperatorTree(op("*", call("max", ["a", "b"]), "c")),
  "max(a, b) * c",
  "a call stands alone and binds tightest",
);
assert.equal(
  printOperatorTree(op("-", "a", op("+", "b", "c"))),
  "a - (b + c)",
  "a sum on the right of a subtraction is fenced off",
);
assert.equal(
  printOperatorTree(op("/", op("*", "a", "b"), op("/", "c", "d"))),
  "a * b / (c / d)",
  "equal power is bare on the left and fenced on the right",
);
assert.equal(
  printOperatorTree(op("and", neg(op("or", "a", "b")), op("^", "c", neg("d")))),
  "-(a or b) and c ^ (-d)",
  "each depth decides its own parentheses",
);
assert.equal(printOperatorTree(op("+", 0, 12)), "0 + 12", "zero is an ordinary number");

assert.throws(() => printOperatorTree(op("%", "a", "b")), Error, "an operator outside the seven is rejected");
assert.throws(() => printOperatorTree({ op: "+", left: "a" }), Error, "a record missing right is rejected");
assert.throws(() => printOperatorTree({ size: 3 }), Error, "a record carrying none of the three is rejected");
assert.throws(() => printOperatorTree({ call: "max", args: "a" }), Error, "args given as text is rejected");
assert.throws(() => printOperatorTree(call("Max", [])), Error, "an upper-case call word is rejected");
assert.throws(() => printOperatorTree("a1"), Error, "a word with a digit is rejected");
assert.throws(() => printOperatorTree(-3), Error, "a negative number is rejected");
assert.throws(() => printOperatorTree(neg(null)), Error, "a missing operand is rejected");
assert.throws(() => printOperatorTree(["+", "a", "b"]), Error, "a node given as a list is rejected");
console.log("ok");
