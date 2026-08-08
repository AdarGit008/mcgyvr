import assert from "node:assert/strict";
import { expandFoldString } from "./solution.ts";

assert.deepEqual(
  expandFoldString("an(t(-|e)|vil)|bee"),
  ["ant", "ante", "anvil", "bee"],
  "a nested bracket unpacks without being torn apart",
);
assert.deepEqual(
  expandFoldString("ca(r(-|d|e)|t)"),
  ["car", "card", "care", "cat"],
  "a hyphen among the branches yields the bare stem",
);
assert.deepEqual(expandFoldString("a"), ["a"], "a bare stem unpacks to itself");
assert.deepEqual(
  expandFoldString("a|b|z"),
  ["a", "b", "z"],
  "branches come back in the order they stand",
);
assert.deepEqual(expandFoldString("a(-|b)"), ["a", "ab"], "the hyphen comes first here");
assert.deepEqual(
  expandFoldString("d(o(-|g|t|ze)|ust)"),
  ["do", "dog", "dot", "doze", "dust"],
  "two levels of bracket unpack in the enclosed order",
);
assert.deepEqual(
  expandFoldString("ox(-|en|ide)|pea(-|r|t)"),
  ["ox", "oxen", "oxide", "pea", "pear", "peat"],
  "two bracketed branches side by side",
);
assert.deepEqual(
  expandFoldString("mist(-|er|le|y)"),
  ["mist", "mister", "mistle", "misty"],
  "one stem with four endings",
);

assert.throws(() => expandFoldString(""), Error, "an empty line is rejected");
assert.throws(() => expandFoldString(7), Error, "a line must be a string");
assert.throws(() => expandFoldString("A(b)"), Error, "a capital letter is rejected");
assert.throws(() => expandFoldString("a b"), Error, "a blank is rejected");
assert.throws(() => expandFoldString("-"), Error, "a hyphen alone at the top is rejected");
assert.throws(() => expandFoldString("a|-"), Error, "a hyphen outside a bracket is rejected");
assert.throws(() => expandFoldString("a(-x)"), Error, "a hyphen must stand alone");
assert.throws(() => expandFoldString("a||b"), Error, "an empty branch is rejected");
assert.throws(() => expandFoldString("|a"), Error, "a leading bar is rejected");
assert.throws(() => expandFoldString("a|"), Error, "a trailing bar is rejected");
assert.throws(() => expandFoldString("(a|b)"), Error, "a bracket with no stem is rejected");
assert.throws(() => expandFoldString("a()"), Error, "an empty bracket is rejected");
assert.throws(() => expandFoldString("a(b"), Error, "an unclosed bracket is rejected");
assert.throws(() => expandFoldString("a(b))"), Error, "a spare closing bracket is rejected");
assert.throws(() => expandFoldString("a(b)c"), Error, "text after a bracket is rejected");
assert.throws(() => expandFoldString("a-b"), Error, "a hyphen mid-stem is rejected");
console.log("ok");
