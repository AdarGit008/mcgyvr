import assert from "node:assert/strict";
import { runEditor } from "./solution.ts";

assert.equal(runEditor([["type", "ab"], ["type", "cd"]]), "abcd", "typing appends");
assert.equal(runEditor([["type", "hello"], ["erase", 3]]), "he", "erase drops the tail");
assert.equal(runEditor([["type", "ab"], ["undo"]]), "", "undo reverts a type");
assert.equal(
  runEditor([["type", "ab"], ["type", "cd"], ["undo"], ["undo"], ["redo"]]),
  "ab",
  "redo reinstates one undone edit",
);
assert.equal(
  runEditor([["type", "ab"], ["erase", 1], ["undo"], ["redo"]]),
  "a",
  "an erase can be undone and redone",
);
assert.equal(
  runEditor([["type", "ab"], ["undo"], ["type", "cd"], ["redo"]]),
  "cd",
  "a fresh edit makes redo a no-op",
);
assert.equal(
  runEditor([["type", "ab"], ["type", "cd"], ["undo"], ["type", "xy"], ["redo"], ["redo"]]),
  "abxy",
  "the whole redo history dies at a divergence",
);
assert.equal(runEditor([["undo"], ["redo"], ["type", "a"]]), "a", "empty history is silent");
assert.throws(() => runEditor([["type", "ab"], ["erase", 3]]), Error, "erase past the start is rejected");
assert.throws(() => runEditor([["type", "ab"], ["erase", 0]]), Error, "zero erase is rejected");
assert.throws(() => runEditor([["paste", "x"]]), Error, "an unknown operation is rejected");
console.log("ok");
