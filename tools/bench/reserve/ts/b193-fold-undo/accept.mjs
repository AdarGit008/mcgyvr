import assert from "node:assert/strict";
import { foldUndo } from "./solution.ts";

assert.deepEqual(foldUndo([], 4), [], "no changes leave the stack empty");
assert.deepEqual(foldUndo([["title", "a", "b"], ["body", "x", "y"]], 4), [["title", "a", "b"], ["body", "x", "y"]], "changes to different fields stack up");
assert.deepEqual(foldUndo([["title", "a", "b"], ["title", "b", "c"]], 4), [["title", "a", "c"]], "two changes to one field merge into one entry");
assert.deepEqual(foldUndo([["title", "a", "b"], ["title", "b", "a"]], 4), [], "a merge back to the old value records nothing");
assert.deepEqual(foldUndo([["body", "x", "y"], ["title", "a", "b"], ["title", "b", "a"], ["body", "y", "z"]], 4), [["body", "x", "z"]], "a change merges with the entry a removal uncovered");
assert.deepEqual(foldUndo([["one", "1", "2"], ["two", "1", "2"], ["six", "1", "2"]], 2), [["two", "1", "2"], ["six", "1", "2"]], "the bottom entry falls off a full stack");
console.log("ok");
