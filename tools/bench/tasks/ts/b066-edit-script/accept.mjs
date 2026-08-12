import assert from "node:assert/strict";
import { applyEditScript } from "./solution.ts";

assert.equal(
  applyEditScript("hello world", [["copy", 6], ["skip", 5], ["insert", "there"]]),
  "hello there",
  "replace the tail",
);
assert.equal(applyEditScript("abcdef", [["skip", 3], ["copy", 3]]), "def", "drop the head");
assert.equal(applyEditScript("", [["insert", "fresh"]]), "fresh", "insert into an empty original");
assert.throws(() => applyEditScript(42, []), Error, "non-string original is rejected");
assert.throws(() => applyEditScript("ab", [["paste", "x"], ["copy", 2]]), Error, "unknown op is rejected");
assert.throws(() => applyEditScript("ab", [["copy", 0], ["copy", 2]]), Error, "zero count is rejected");
assert.throws(() => applyEditScript("ab", [["insert", ""], ["copy", 2]]), Error, "empty insert text is rejected");
assert.throws(() => applyEditScript("ab", [["copy", 3]]), Error, "reading past the end is rejected");
assert.throws(() => applyEditScript("ab", [["copy", 1]]), Error, "stopping short is rejected");
console.log("ok");
