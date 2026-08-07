import assert from "node:assert/strict";
import { scanSource } from "./solution.ts";

assert.deepEqual(
  scanSource("x = 42"),
  [["id", "x"], ["op", "="], ["num", "42"]],
  "identifier, assignment, number",
);
assert.deepEqual(
  scanSource("a<=b"),
  [["id", "a"], ["op", "<="], ["id", "b"]],
  "two-character operator wins over < then =",
);
assert.deepEqual(
  scanSource("_tmp2 != done"),
  [["id", "_tmp2"], ["op", "!="], ["id", "done"]],
  "underscore identifiers and !=",
);
assert.deepEqual(
  scanSource("12abc"),
  [["num", "12"], ["id", "abc"]],
  "a digit run then letters is num then id",
);
assert.deepEqual(
  scanSource("(a||b)&&c"),
  [
    ["op", "("], ["id", "a"], ["op", "||"], ["id", "b"], ["op", ")"],
    ["op", "&&"], ["id", "c"],
  ],
  "logical operators and parentheses",
);
assert.deepEqual(
  scanSource("n\t*  n"),
  [["id", "n"], ["op", "*"], ["id", "n"]],
  "tabs and repeated spaces are skipped",
);
assert.deepEqual(scanSource(""), [], "the empty line has no tokens");
assert.deepEqual(
  scanSource("a==b==c"),
  [["id", "a"], ["op", "=="], ["id", "b"], ["op", "=="], ["id", "c"]],
  "consecutive == pairs never merge",
);
assert.throws(() => scanSource("a ! b"), Error, "a lone ! is rejected");
assert.throws(() => scanSource("x@y"), Error, "an unknown character is rejected");
console.log("ok");
