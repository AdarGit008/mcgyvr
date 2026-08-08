import assert from "node:assert/strict";
import { expandRunTag } from "./solution.ts";

assert.deepEqual(
  expandRunTag("cam-[2-10/4]"),
  ["cam-10", "cam-2", "cam-6"],
  "stepped run, sorted as strings",
);
assert.deepEqual(
  expandRunTag("led[red,green,blue].cfg"),
  ["ledblue.cfg", "ledgreen.cfg", "ledred.cfg"],
  "comma listing keeps stem and tail",
);
assert.deepEqual(expandRunTag("[7-9]"), ["7", "8", "9"], "bare run");
assert.deepEqual(expandRunTag("x[a,a]"), ["xa"], "duplicates collapse");
assert.deepEqual(expandRunTag("[0-0]"), ["0"], "one-value run");
assert.deepEqual(
  expandRunTag("n[1-3]s"),
  ["n1s", "n2s", "n3s"],
  "slashless run steps by one",
);
assert.throws(() => expandRunTag("nope"), Error, "pattern without a group");
assert.throws(() => expandRunTag("a[b"), Error, "unclosed bracket");
assert.throws(() => expandRunTag("]x["), Error, "reversed brackets");
assert.throws(() => expandRunTag("a[]b"), Error, "empty body");
assert.throws(() => expandRunTag("a[x,,y]"), Error, "empty comma item");
assert.throws(() => expandRunTag("[3-1]"), Error, "descending run");
assert.throws(() => expandRunTag("[1-9/0]"), Error, "zero step");
assert.throws(() => expandRunTag("[1-2][3-4]"), Error, "two groups");
assert.throws(() => expandRunTag(5), Error, "non-string argument");
console.log("ok");
