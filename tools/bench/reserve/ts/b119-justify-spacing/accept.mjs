import assert from "node:assert/strict";
import { justifySpacing } from "./solution.ts";

assert.deepEqual(
  justifySpacing(10, [["a", "bb", "c"], ["done"]]),
  [[3, 3], []],
  "a body line spreads its spare width evenly",
);
assert.deepEqual(
  justifySpacing(11, [["ab", "cd", "ef"], ["end"]]),
  [[3, 2], []],
  "the leftmost gap takes the extra space",
);
assert.deepEqual(
  justifySpacing(8, [["to", "go", "up"], ["x"]]),
  [[1, 1], []],
  "an exactly fitting body line keeps single spaces",
);
assert.deepEqual(
  justifySpacing(20, [["all", "done", "here"]]),
  [[1, 1]],
  "a one-line paragraph is its own last line, set ragged",
);
assert.deepEqual(
  justifySpacing(9, [["stretch"], ["on"]]),
  [[], []],
  "a lone word on a body line yields no gaps",
);
assert.deepEqual(
  justifySpacing(12, [["fill", "me", "up"], ["the", "end"]]),
  [[2, 2], [1]],
  "the last line keeps single spaces however wide the column",
);
assert.deepEqual(
  justifySpacing(12, [["a", "b", "c", "d"], ["e"]]),
  [[3, 3, 2], []],
  "extra space lands on the leftmost of three gaps",
);
assert.throws(() => justifySpacing(0, [["a"]]), Error, "a zero width is rejected");
assert.throws(() => justifySpacing(2.5, [["a"]]), Error, "a fractional width is rejected");
assert.throws(() => justifySpacing(5, []), Error, "an empty paragraph is rejected");
assert.throws(() => justifySpacing(5, [[]]), Error, "an empty line is rejected");
assert.throws(() => justifySpacing(5, [["", "a"]]), Error, "an empty word is rejected");
assert.throws(() => justifySpacing(9, [["a b"]]), Error, "a word with a space is rejected");
assert.throws(
  () => justifySpacing(3, [["abc", "d"], ["x"]]),
  Error,
  "an overrun body line is rejected",
);
assert.throws(() => justifySpacing(3, [["abcd"]]), Error, "an overrun last line is rejected");
console.log("ok");
