import assert from "node:assert/strict";
import { readTagAttributes } from "./solution.ts";

assert.deepEqual(
  readTagAttributes("[panel]"),
  { stem: "panel", marks: [] },
  "a bare tag carries no marks",
);
assert.deepEqual(
  readTagAttributes("[panel wide id=main]"),
  {
    stem: "panel",
    marks: [
      { name: "wide", setting: "" },
      { name: "id", setting: "main" },
    ],
  },
  "a lone name settles to the empty string",
);
assert.deepEqual(
  readTagAttributes(`[note text="hello there" sign='a"b']`),
  {
    stem: "note",
    marks: [
      { name: "text", setting: "hello there" },
      { name: "sign", setting: 'a"b' },
    ],
  },
  "the opposite quote means itself inside a fence",
);
assert.deepEqual(
  readTagAttributes(String.raw`[a s="say \"hi\"" b='c\\d']`),
  {
    stem: "a",
    marks: [
      { name: "s", setting: 'say "hi"' },
      { name: "b", setting: "c\\d" },
    ],
  },
  "a backslash means the one character behind it",
);
assert.deepEqual(
  readTagAttributes("[a k=1 k=1]"),
  { stem: "a", marks: [{ name: "k", setting: "1" }] },
  "the same setting twice folds into one mark",
);
assert.deepEqual(
  readTagAttributes(`[a k="" j=x]`),
  {
    stem: "a",
    marks: [
      { name: "k", setting: "" },
      { name: "j", setting: "x" },
    ],
  },
  "a fenced setting may be empty",
);
assert.deepEqual(
  readTagAttributes("[x-1 src=file_name.v2-b]"),
  { stem: "x-1", marks: [{ name: "src", setting: "file_name.v2-b" }] },
  "a plain setting spans dots, underscores and hyphens",
);
assert.deepEqual(
  readTagAttributes(`[row cell='a]b' end]`),
  {
    stem: "row",
    marks: [
      { name: "cell", setting: "a]b" },
      { name: "end", setting: "" },
    ],
  },
  "a bracket inside a fence does not close the tag",
);
assert.throws(() => readTagAttributes(9), Error, "a tag that is not a string is rejected");
assert.throws(() => readTagAttributes(""), Error, "an empty tag is rejected");
assert.throws(() => readTagAttributes("panel]"), Error, "a missing opening bracket is rejected");
assert.throws(() => readTagAttributes("[panel"), Error, "a missing closing bracket is rejected");
assert.throws(() => readTagAttributes("[panel] extra"), Error, "text after the closing bracket is rejected");
assert.throws(() => readTagAttributes("[]"), Error, "an empty stem is rejected");
assert.throws(() => readTagAttributes("[1bad]"), Error, "a stem opening with a digit is rejected");
assert.throws(() => readTagAttributes("[a  b]"), Error, "two spaces running are rejected");
assert.throws(() => readTagAttributes("[a ]"), Error, "a space before the closing bracket is rejected");
assert.throws(() => readTagAttributes("[a Key=1]"), Error, "a capital in a mark name is rejected");
assert.throws(() => readTagAttributes("[a =1]"), Error, "an equals sign with no name is rejected");
assert.throws(() => readTagAttributes("[a k=]"), Error, "an equals sign with no setting is rejected");
assert.throws(() => readTagAttributes(`[a k="open]`), Error, "a fence never closed is rejected");
assert.throws(() => readTagAttributes(String.raw`[a k="bad\z"]`), Error, "a stray backslash escape is rejected");
assert.throws(() => readTagAttributes("[a k=v#w]"), Error, "a stray character after a plain setting is rejected");
assert.throws(() => readTagAttributes("[a k=1 k=2]"), Error, "one name with two settings is rejected");
console.log("ok");
