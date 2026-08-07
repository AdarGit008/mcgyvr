import assert from "node:assert/strict";
import { restoreFrontShift } from "./solution.ts";

const LETTERS = "abcdefghijklmnopqrstuvwxyz";

assert.equal(
  restoreFrontShift("abcd", [3, 1, 2]),
  "dab",
  "the stated dab example",
);
assert.equal(
  restoreFrontShift(LETTERS, [1, 1, 13, 1, 1, 1]),
  "banana",
  "a long ring rearranged six times",
);
assert.equal(
  restoreFrontShift(LETTERS, [1, 1, 13, 1, 1, 1, 0, 0]),
  "bananaaa",
  "slot zero repeats the last character",
);
assert.equal(restoreFrontShift("abc", []), "", "an empty code list");
assert.equal(restoreFrontShift("abc", [0, 0, 0]), "aaa", "the front stays put");
assert.equal(
  restoreFrontShift("abc", [2, 2, 2]),
  "cba",
  "the tail slot walks forward",
);
assert.equal(
  restoreFrontShift("xyz", [2, 0, 1]),
  "zzx",
  "the ring keeps its order behind the front",
);
assert.equal(
  restoreFrontShift(".-#", [2, 1, 2, 2]),
  "#.-#",
  "the alphabet need not be letters",
);
assert.throws(
  () => restoreFrontShift(5, [0]),
  Error,
  "an alphabet that is not a string is thrown out",
);
assert.throws(
  () => restoreFrontShift("", []),
  Error,
  "an empty alphabet is thrown out",
);
assert.throws(
  () => restoreFrontShift("abca", [0]),
  Error,
  "a repeated alphabet character is thrown out",
);
assert.throws(
  () => restoreFrontShift("abc", "0"),
  Error,
  "codes that are not a list are thrown out",
);
assert.throws(
  () => restoreFrontShift("abc", [0, 1.5]),
  Error,
  "a code that is not whole is thrown out",
);
assert.throws(
  () => restoreFrontShift("abc", [3]),
  Error,
  "a code naming no slot is thrown out",
);
console.log("ok");
