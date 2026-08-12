import assert from "node:assert/strict";
import { replayNotepad } from "./solution.ts";

assert.equal(replayNotepad([]), "", "no commands leave an empty buffer");
assert.equal(
  replayNotepad([["type", "hello "], ["type", "world"]]),
  "hello world",
  "typed texts concatenate",
);
assert.equal(
  replayNotepad([["type", "carrots"], ["erase", 3]]),
  "carr",
  "erase removes the tail",
);
assert.equal(
  replayNotepad([["type", "ab"], ["erase", 2]]),
  "",
  "erase may drain the whole buffer",
);
assert.equal(
  replayNotepad([["type", "one two one"], ["replace", "one", "three"]]),
  "one two three",
  "replace rewrites the last occurrence",
);
assert.equal(
  replayNotepad([["type", "draft"], ["undo", 1]]),
  "",
  "undo reverts a type",
);
assert.equal(
  replayNotepad([["type", "a"], ["type", "b"], ["undo", 2]]),
  "",
  "undo may revert several edits at once",
);
assert.equal(
  replayNotepad([["type", "x"], ["type", "y"], ["undo", 1], ["redo", 1]]),
  "xy",
  "redo re-applies the undone edit",
);
assert.equal(
  replayNotepad([["type", "a"], ["undo", 1], ["type", "b"]]),
  "b",
  "a fresh edit after undo wins",
);
assert.equal(
  replayNotepad([["type", "note"], ["erase", 2], ["undo", 1]]),
  "note",
  "undo restores erased text",
);
assert.equal(
  replayNotepad([
    ["type", "alpha"],
    ["type", " beta"],
    ["replace", "beta", "gamma"],
    ["undo", 1],
    ["redo", 1],
    ["erase", 6],
  ]),
  "alpha",
  "replace, undo and redo interleave",
);
assert.throws(() => replayNotepad([["poke", "x"]]), Error, "unknown action");
assert.throws(() => replayNotepad([["type", 3]]), Error, "type of a non-string");
assert.throws(() => replayNotepad([["type", ""]]), Error, "type of an empty text");
assert.throws(() => replayNotepad([["type", "ab"], ["erase", 0]]), Error, "erase count of zero");
assert.throws(
  () => replayNotepad([["type", "ab"], ["erase", 3]]),
  Error,
  "erase count exceeding the buffer",
);
assert.throws(() => replayNotepad([["undo", 1]]), Error, "undo with no edits");
assert.throws(() => replayNotepad([["type", "a"], ["redo", 1]]), Error, "redo with nothing undone");
assert.throws(
  () => replayNotepad([["type", "a"], ["undo", 1], ["type", "b"], ["redo", 1]]),
  Error,
  "redo after a fresh edit",
);
assert.throws(
  () => replayNotepad([["type", "abc"], ["replace", "zz", "q"]]),
  Error,
  "replace of an absent text",
);
assert.throws(
  () => replayNotepad([["type", "abc"], ["replace", "", "q"]]),
  Error,
  "replace of an empty text",
);
assert.throws(() => replayNotepad([["erase"]]), Error, "command without its payload");
assert.throws(() => replayNotepad([["type", "a"], ["undo", 0]]), Error, "undo count of zero");
console.log("ok");
