import assert from "node:assert/strict";
import { applyEditScript } from "./solution.ts";

assert.equal(applyEditScript("", []), "", "empty doc and empty script");
assert.equal(
  applyEditScript("hello", [["keep", "hello"]]),
  "hello",
  "keeping the whole document returns it unchanged",
);
assert.equal(
  applyEditScript("hello world", [["keep", "hello"], ["drop", " world"]]),
  "hello",
  "a drop removes its run",
);
assert.equal(
  applyEditScript("ab", [["keep", "a"], ["add", "XY"], ["keep", "b"]]),
  "aXYb",
  "an add inserts between kept runs",
);
assert.equal(
  applyEditScript("hi", [["keep", "hi"], ["add", "!"]]),
  "hi!",
  "an add after the last kept character appends",
);
assert.equal(applyEditScript("gone", [["drop", "gone"]]), "", "dropping everything");
assert.equal(
  applyEditScript("", [["add", "new"], ["add", "file"]]),
  "newfile",
  "adds alone build a document from nothing",
);
assert.equal(
  applyEditScript("abcdef", [
    ["keep", "ab"],
    ["drop", "cd"],
    ["add", "Z"],
    ["keep", "ef"],
  ]),
  "abZef",
  "keep, drop and add combine into a replacement",
);
assert.throws(() => applyEditScript(42, []), Error, "non-string document");
assert.throws(() => applyEditScript("abc", 7), Error, "script is not a list");
assert.throws(
  () => applyEditScript("a", [["copy", "a"]]),
  Error,
  "unknown tag is rejected",
);
assert.throws(
  () => applyEditScript("a", [["keep", ""]]),
  Error,
  "empty edit text is rejected",
);
assert.throws(
  () => applyEditScript("abc", [["keep", "abx"]]),
  Error,
  "keep text must match the document",
);
assert.throws(
  () => applyEditScript("ab", [["keep", "abc"]]),
  Error,
  "an edit past the end is rejected",
);
assert.throws(
  () => applyEditScript("abc", [["keep", "a"]]),
  Error,
  "unconsumed tail is rejected",
);
console.log("ok");
