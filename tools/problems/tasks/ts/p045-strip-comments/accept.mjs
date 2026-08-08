import assert from "node:assert/strict";
import { stripComments } from "./solution.ts";

assert.equal(
  stripComments("a = 1 // note\nb = 2"),
  "a = 1 \nb = 2",
  "a line comment vanishes but its newline survives",
);
assert.equal(
  stripComments('s = "http://x" // real'),
  's = "http://x" ',
  "a marker inside a string literal is not a comment",
);
assert.equal(
  stripComments("x /* mid */ y"),
  "x  y",
  "a block comment on one line is removed",
);
assert.equal(
  stripComments("a\n/* one\ntwo */\nb"),
  "a\n\nb",
  "a block comment spanning lines is removed entirely",
);
assert.equal(
  stripComments("q /* * */ r"),
  "q  r",
  "a stray star inside a block comment does not end it early",
);
assert.equal(
  stripComments('t = "a\\"b" // c'),
  't = "a\\"b" ',
  "an escaped quote does not close the string",
);
assert.equal(
  stripComments('p = "x\\\\" // y'),
  'p = "x\\\\" ',
  "a double backslash leaves the closing quote closing",
);
assert.equal(
  stripComments("const x = 5;\n"),
  "const x = 5;\n",
  "comment-free code is untouched",
);
assert.equal(
  stripComments("// whole line\ncode"),
  "\ncode",
  "a full-line comment leaves an empty line",
);
assert.throws(() => stripComments("/* never ends"), Error, "open block comment throws");
assert.throws(() => stripComments('v = "never ends'), Error, "open string throws");
console.log("ok");
