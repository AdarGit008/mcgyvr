import assert from "node:assert/strict";
import { unpackFrames } from "./solution.ts";

assert.deepEqual(unpackFrames("#0;"), [], "empty stream is just the trailer");
assert.deepEqual(unpackFrames("5:hello;#1;"), ["hello"], "one frame decodes");
assert.deepEqual(unpackFrames("3:abc;2:de;#2;"), ["abc", "de"], "frames in order");
assert.deepEqual(unpackFrames("0:;#1;"), [""], "zero-length payload");
assert.deepEqual(
  unpackFrames("5:a;b:c;#1;"),
  ["a;b:c"],
  "payload may hold ';' and ':'",
);
assert.deepEqual(unpackFrames("2:12;#1;"), ["12"], "payload may hold digits");
assert.deepEqual(
  unpackFrames("0:;3:xyz;#2;"),
  ["", "xyz"],
  "empty and full frames mix",
);
assert.throws(() => unpackFrames(""), Error, "empty string lacks the trailer");
assert.throws(() => unpackFrames("5:hello;"), Error, "missing trailer");
assert.throws(() => unpackFrames("9:abc;#1;"), Error, "truncated payload");
assert.throws(() => unpackFrames("3:abc"), Error, "unterminated frame");
assert.throws(() => unpackFrames("3:abc#1;"), Error, "frame closed by wrong char");
assert.throws(() => unpackFrames("03:abc;#1;"), Error, "leading-zero length");
assert.throws(() => unpackFrames(":abc;#1;"), Error, "missing length");
assert.throws(() => unpackFrames("3;abc;#1;"), Error, "length without ':'");
assert.throws(() => unpackFrames(42), Error, "non-string stream");
assert.throws(() => unpackFrames("3:abc;#2;"), Error, "count mismatch");
assert.throws(() => unpackFrames("3:abc;#1;x"), Error, "text after the trailer");
console.log("ok");
