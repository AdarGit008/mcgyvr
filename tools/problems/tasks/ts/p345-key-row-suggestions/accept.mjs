import assert from "node:assert/strict";
import { keyRowSuggestions } from "./solution.ts";

const board = ["qwert", "asdfg", "zxcvb"];

assert.deepEqual(
  keyRowSuggestions(board, "sat", ["cat", "wat", "zat", "dat", "fat"]),
  ["dat", "wat", "zat", "cat"],
  "compass order, and a two-column gap never touches",
);
assert.deepEqual(
  keyRowSuggestions(board, "df", ["sf", "ff"]),
  ["sf", "ff"],
  "straight left comes before straight right",
);
assert.deepEqual(
  keyRowSuggestions(board, "ss", ["ds", "sd"]),
  ["ds", "sd"],
  "the same step is ordered leftmost place first",
);
assert.deepEqual(
  keyRowSuggestions(board, "cat", ["cat", "bat"]),
  [],
  "an accepted typed word yields nothing",
);
assert.deepEqual(
  keyRowSuggestions(board, "qq", ["zz"]),
  [],
  "no accepted word is one step away",
);
assert.deepEqual(
  keyRowSuggestions(["ab", "cde"], "ae", ["be", "ab"]),
  ["be", "ab"],
  "ragged rows and a diagonal step",
);
assert.throws(() => keyRowSuggestions("qwert", "sat", ["cat"]), Error, "not a list");
assert.throws(() => keyRowSuggestions([], "sat", ["cat"]), Error, "no rows");
assert.throws(() => keyRowSuggestions(["qwe", ""], "q", ["w"]), Error, "empty row");
assert.throws(() => keyRowSuggestions(["QWE"], "q", ["w"]), Error, "uppercase row");
assert.throws(() => keyRowSuggestions(["qw", "wa"], "q", ["w"]), Error, "letter drawn twice");
assert.throws(() => keyRowSuggestions(board, "", ["cat"]), Error, "empty typed word");
assert.throws(() => keyRowSuggestions(board, "Sat", ["cat"]), Error, "uppercase typed");
assert.throws(() => keyRowSuggestions(board, "sap", ["cat"]), Error, "letter off the drawing");
assert.throws(() => keyRowSuggestions(board, "sat", "cat"), Error, "accepted not a list");
assert.throws(() => keyRowSuggestions(board, "sat", [""]), Error, "empty accepted word");
console.log("ok");
