import assert from "node:assert/strict";
import { writeTagMarks } from "./solution.ts";

assert.equal(writeTagMarks("box", []), "<box>", "no fields means no spaces at all");
assert.equal(
  writeTagMarks("box", [
    ["id", "a1"],
    ["title", "hello world"],
    ["note", 'say "hi"'],
    ["flag", ""],
  ]),
  `<box id=a1 title="hello world" note='say "hi"' flag>`,
  "each field picks its own writing",
);
assert.equal(
  writeTagMarks("x", [["k", `it's "both"`]]),
  String.raw`<x k="it's \"both\"">`,
  "both quotes present means the double quote wins and gets escaped",
);
assert.equal(
  writeTagMarks("x", [["k", String.raw`back\slash`]]),
  String.raw`<x k="back\\slash">`,
  "a backslash is doubled inside the wrapping",
);
assert.equal(writeTagMarks("x", [["src", "a-b.c"]]), "<x src=a-b.c>", "hyphens and full stops stay naked");
assert.equal(writeTagMarks("x", [["k", "a>b"]]), `<x k="a>b">`, "an angle bracket forces wrapping");
assert.equal(writeTagMarks("x", [["k", "on'ly"]]), `<x k="on'ly">`, "a lone single quote keeps the double quote fence");
assert.equal(writeTagMarks("x2", [["a1", ""], ["b2", ""]]), "<x2 a1 b2>", "two empty texts give two bare keys");
assert.throws(() => writeTagMarks("Box", []), Error, "a capital in the label is rejected");
assert.throws(() => writeTagMarks("1x", []), Error, "a label opening with a digit is rejected");
assert.throws(() => writeTagMarks(5, []), Error, "a label that is not a string is rejected");
assert.throws(() => writeTagMarks("x", "k=v"), Error, "fields that are not a list are rejected");
assert.throws(() => writeTagMarks("x", [["k"]]), Error, "a field of one is rejected");
assert.throws(() => writeTagMarks("x", ["k=v"]), Error, "a field that is not a list is rejected");
assert.throws(() => writeTagMarks("x", [["K", "v"]]), Error, "a capital in a key is rejected");
assert.throws(() => writeTagMarks("x", [["", "v"]]), Error, "an empty key is rejected");
assert.throws(() => writeTagMarks("x", [["k", 5]]), Error, "a text that is not a string is rejected");
assert.throws(() => writeTagMarks("x", [["k", "a"], ["k", "b"]]), Error, "one key arriving twice is rejected");
console.log("ok");
